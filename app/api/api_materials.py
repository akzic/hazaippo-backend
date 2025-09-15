# app/api/api_materials.py

from flask import Flask, Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models import Material, WantedMaterial, User, Site, Request, UserGroup, GroupMembership
from datetime import datetime
import pytz
import os
import re
import logging
from werkzeug.utils import secure_filename
from uuid import uuid4
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import SQLAlchemyError
from app.image_processing import process_image_ai
from app.blueprints.utils import log_user_activity
from app.utils.s3_uploader import upload_file_to_s3, build_s3_url, convert_heic_to_jpeg

logger = logging.getLogger(__name__)
JST = pytz.timezone('Asia/Tokyo')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'heic', 'heif'}

api_materials_bp = Blueprint('api_materials', __name__, url_prefix='/api/materials')

def allowed_file(filename):
    """指定されたファイル名が許可された拡張子かどうかを判定する"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def parse_japanese_address(location):
    """住所文字列から都道府県、市区町村、住所を抽出する"""
    try:
        logger.debug(f"Original location: {location}")
        # 国名除去
        location = re.sub(r'^日本[、,]\s*', '', location)
        logger.debug(f"After removing country: {location}")
        # 郵便番号除去
        location = re.sub(r'〒\d{3}-\d{4}\s*', '', location)
        logger.debug(f"After removing postal code: {location}")

        prefectures = [
            '北海道', '青森県', '岩手県', '宮城県', '秋田県', '山形県', '福島県',
            '茨城県', '栃木県', '群馬県', '埼玉県', '千葉県', '東京都', '神奈川県',
            '新潟県', '富山県', '石川県', '福井県', '山梨県', '長野県', '岐阜県',
            '静岡県', '愛知県', '三重県', '滋賀県', '京都府', '大阪府', '兵庫県',
            '奈良県', '和歌山県', '鳥取県', '島根県', '岡山県', '広島県', '山口県',
            '徳島県', '香川県', '愛媛県', '高知県',
            '福岡県', '佐賀県', '長崎県', '熊本県', '大分県', '宮崎県', '鹿児島県',
            '沖縄県'
        ]

        prefecture = None
        for pref in prefectures:
            if location.startswith(pref):
                prefecture = pref
                break

        if not prefecture:
            logger.warning("Prefecture not found.")
            return None

        logger.debug(f"Extracted prefecture: {prefecture}")
        remaining = location[len(prefecture):].strip()
        logger.debug(f"Remaining location: {remaining}")
        city_match = re.match(r'^([^市区町村]*[市区町村]+)', remaining)
        city = city_match.group(1) if city_match else ''
        address = remaining[len(city):].strip() if city_match else remaining
        logger.debug(f"Extracted city: {city}")
        logger.debug(f"Extracted address: {address}")
        return {'prefecture': prefecture, 'city': city, 'address': address}
    except Exception as e:
        logger.error(f"Error parsing address: {e}")
        return None

def get_current_user():
    """JWT からユーザーIDを取得し、DBからユーザー情報をロードする"""
    user_id = get_jwt_identity()
    return User.query.get(user_id)

# ─────────────────────────────
# Material Registration (API)
# ─────────────────────────────
@api_materials_bp.route('/register_material', methods=['POST'])
@jwt_required()
def register_material():
    current_app.logger.debug("---- 登録処理開始 ----")

    # 0. current_user_obj の取得
    try:
        current_user_obj = get_current_user()
        current_app.logger.debug("Current user obtained: %s", current_user_obj)
        current_app.logger.debug("Current user ID: %s", current_user_obj.id)
    except Exception as e:
        current_app.logger.error("Error obtaining current user: %s", e)
        return jsonify({"status": "error", "message": "Error obtaining current user."}), 500

    # ---------------------------------------------------
    # 1. リクエストデータの取得（JSON or multipart）
    # ---------------------------------------------------
    data = {}
    try:
        # Content-Type で JSON かどうかをざっくり判定
        if request.is_json:
            data = request.get_json() or {}
            current_app.logger.debug("Received JSON data: %s", data)
        else:
            # multipart/form-data の場合は request.form
            data = request.form.to_dict()
            current_app.logger.debug("Received form data: %s", data)
    except Exception as e:
        current_app.logger.error("Error retrieving request data: %s", e)
        return jsonify({"status": "error", "message": "Error retrieving request data."}), 500

    # ---------------------------------------------------
    # 2. 画像ファイルの取得（multipart時のみ送信される想定）
    # ---------------------------------------------------
    image_key  = None
    try:
        if 'image' in request.files:
            file = request.files['image']
            if file and allowed_file(file.filename):
                # ---------- ❶ S3 へアップ ----------
                image_key = upload_file_to_s3(
                    file,
                    folder="materials"
                )
                current_app.logger.debug("S3 upload 完了: key=%s", image_key)
            else:
                if file:
                    current_app.logger.debug("Invalid file format: %s", file.filename)
                return jsonify({"status": "error", "message": "Invalid file format."}), 400
        else:
            current_app.logger.debug("No image file provided; using default.")
    except Exception as e:
        current_app.logger.error("Error processing image: %s", e)
        return jsonify({"status": "error", "message": "Error processing image."}), 500

    # ---------------------------------------------------
    # 3. 必須パラメータのチェック
    # ---------------------------------------------------
    # Flutter 側で選択済み値が飛んでくる想定。
    # delivery_option は別画面で扱うため除外
    required_fields = [
        "material_type",
        "quantity",
        "deadline",
        "m_prefecture",
        "m_city",
        "m_address"
    ]
    group_id_raw = data.get("group_id", "0")
    try:
        group_id_val = int(group_id_raw)
    except ValueError:
        return jsonify({"status": "error", "message": "group_id must be integer."}), 400

    errors = []
    for field in required_fields:
        # data[field] が存在しなかったり空文字のとき
        if field not in data or not data[field]:
            errors.append(f"{field} is missing or empty.")

    # サイズフィールドが空の場合は "0.0" を自動設定する
    for size_field in ["material_size_1", "material_size_2", "material_size_3"]:
        if size_field not in data or data[size_field] == "":
            data[size_field] = "0.0"

    if errors:
        current_app.logger.error("Validation errors: %s", errors)
        return jsonify({"status": "error", "message": "Validation errors", "errors": errors}), 422
    else:
        current_app.logger.debug("All required parameters present.")

    for s in ["material_size_1", "material_size_2", "material_size_3"]:
        try:
            float(data.get(s, "0"))
        except ValueError:
            errors.append(f"{s} must be numeric.")

    # ---------------------------------------------------
    # 4. AI 処理は /analyze_material に移譲したため完全にスキップ
    # ---------------------------------------------------
    material_type_val = data.get("material_type")

    # ---------------------------------------------------
    # 5. business_structure による会社名チェック
    # ---------------------------------------------------
    try:
        business_structure = current_user_obj.business_structure
        if business_structure in [0, 1] and not current_user_obj.company_name.strip():
            current_app.logger.debug("Company name required for business structure 0 or 1.")
            return jsonify({"status": "error", "message": "Company name is required."}), 400
        # personal ユーザー (business_structure 2 以上) は group_id を指定できない
        if business_structure not in [0, 1] and group_id_val != 0:
            return jsonify({"status": "error", "message": "Personal users cannot set group_id."}), 400

        # group_id が 0 以外なら存在チェック & メンバーシップチェック
        selected_group = None
        if group_id_val != 0:
            selected_group = UserGroup.query.filter(
                UserGroup.id == group_id_val,
                UserGroup.deleted_at.is_(None)
            ).first()
            if not selected_group:
                return jsonify({"status": "error", "message": "Group not found or inactive."}), 404
            # 自分がメンバーか確認
            membership = GroupMembership.query.filter_by(
                group_id=group_id_val,
                user_id=current_user_obj.id
            ).first()
            if not membership:
                return jsonify({"status": "error", "message": "You are not a member of this group."}), 403

    except Exception as e:
        current_app.logger.error("Error checking company name: %s", e)
        return jsonify({"status": "error", "message": "Error checking company name."}), 500

    # ---------------------------------------------------
    # 6. 型変換・日付変換
    # ---------------------------------------------------
    try:
        quantity_val = int(data.get("quantity", 0))
        current_app.logger.debug("Converted quantity: %d", quantity_val)
    except Exception as e:
        current_app.logger.error("Error converting quantity: %s", e)
        quantity_val = 0

    try:
        deadline_str = data.get("deadline")
        deadline_val = datetime.fromisoformat(deadline_str) if deadline_str else datetime.now(JST)
        current_app.logger.debug("Converted deadline: %s", deadline_val)
    except Exception as e:
        current_app.logger.error("Error converting deadline: %s", e)
        deadline_val = datetime.now(JST)

    # ---------------------------------------------------
    # 7. 位置情報のセット
    # ---------------------------------------------------
    try:
        m_prefecture = data.get("m_prefecture", "").strip()
        m_city = data.get("m_city", "").strip()
        m_address = data.get("m_address", "").strip()
        location = f"{m_prefecture} {m_city} {m_address}"

        # AI 位置情報（ai_location）があればそちらを優先したい場合はここで処理
        # 今回の例ではフォーム優先にしているため省略。
        current_app.logger.debug("Using form location: '%s'", location)
    except Exception as e:
        current_app.logger.error("Error processing location data: %s", e)
        return jsonify({"status": "error", "message": "Error processing location data."}), 500

    # ---------------------------------------------------
    # 8. Material オブジェクトの作成
    # ---------------------------------------------------
    try:
        new_material = Material(
            user_id = current_user_obj.id,
            type = material_type_val,
            size_1 = float(data.get("material_size_1", 0.0)),
            size_2 = float(data.get("material_size_2", 0.0)),
            size_3 = float(data.get("material_size_3", 0.0)),
            location = location,
            m_prefecture = m_prefecture,
            m_city = m_city,
            m_address = m_address,
            quantity = quantity_val,
            deadline = deadline_val,
            exclude_weekends = (
                bool(data.get("exclude_weekends"))
                if isinstance(data.get("exclude_weekends"), bool)
                else str(data.get("exclude_weekends")).lower() in ['true', '1']
            ),
            image = image_key,
            note = data.get("note"),
            wood_type = data.get("wood_type") \
                if material_type_val == "木材" else None,
            board_material_type = data.get("board_material_type") \
                if material_type_val == "ボード材" else None,
            panel_type = data.get("panel_type") \
                if material_type_val == "パネル材" else None,
            group_id   = group_id_val if group_id_val != 0 else None
        )
        current_app.logger.debug("New Material object details: user_id=%s, deadline=%s, quantity=%s, location=%s",
            new_material.user_id, new_material.deadline, new_material.quantity, new_material.location)
    except Exception as e:
        current_app.logger.error("Error creating Material object: %s", e)
        return jsonify({"status": "error", "message": "Error creating Material object."}), 500

    # ---------------------------------------------------
    # 9. サイト情報の処理
    # ---------------------------------------------------
    try:
        if location:
            site = Site.query.filter(
                Site.site_prefecture.ilike(m_prefecture),
                Site.site_city.ilike(m_city),
                Site.site_address.ilike(m_address)
            ).first()
            if site:
                new_material.site_id = site.id
                current_app.logger.debug("Site found. site_id set to %s", site.id)
            else:
                new_material.site_id = None
                current_app.logger.debug("Site not found. site_id set to None.")
        else:
            new_material.site_id = None
            current_app.logger.debug("Location is empty. site_id not set.")
    except Exception as e:
        current_app.logger.error("Error processing site data: %s", e)
        return jsonify({"status": "error", "message": "Error processing site data."}), 500

    # ---------------------------------------------------
    # 10. データベースへのコミット
    # ---------------------------------------------------
    try:
        db.session.add(new_material)
        db.session.commit()
        current_app.logger.debug("Material registered. ID: %s", new_material.id)
    except Exception as e:
        db.session.rollback()
        current_app.logger.error("Error committing Material to database: %s", e)
        return jsonify({"status": "error", "message": "Error registering material."}), 500

    # ---------------------------------------------------
    # 11. メール送信（失敗しても処理は続行する例）
    # ---------------------------------------------------
    try:
        send_material_registration_email(current_user_obj, new_material)
        current_app.logger.debug("Registration email sent.")
    except Exception as e:
        current_app.logger.error("Error sending registration email: %s", e)

    current_app.logger.debug("---- 登録処理終了 ----")
    return jsonify({
        "status": "success",
        "message": "Material registered successfully.",
        "material_id": new_material.id,
        "image_key": new_material.image,           # ← デバッグ用
        "image_url": build_s3_url(new_material.image),
        "group_id": new_material.group_id
    }), 200

@api_materials_bp.route('/analyze_material', methods=['POST'])
@jwt_required()
def analyze_material():
    """
    Flutter から送られた画像 1 枚を Gemini Flash 2.0 に掛け
    ・前処理あり  ・前処理なし
    2 通りの JSON を返すだけの軽量 API
    例外やタイムアウト・サイズ超過も詳細ログで調査しやすい
    """
    import time

    try:
        # ① 受信内容をログ出力
        current_app.logger.info(f"[analyze_material] called. content_length={request.content_length} files={list(request.files.keys())}")

        if 'image' not in request.files:
            current_app.logger.error("[analyze_material] image file required")
            return jsonify({"status": "error", "message": "image file required"}), 400

        img = request.files['image']
        current_app.logger.info(f"[analyze_material] image filename: {img.filename}, content_type: {img.content_type}, content_length: {getattr(img, 'content_length', 'N/A')}")

        if not (img and allowed_file(img.filename)):
            current_app.logger.error("[analyze_material] invalid image: %s", img.filename)
            return jsonify({"status": "error", "message": "invalid image"}), 400

        # ② 一時保存
        fname = secure_filename(img.filename)
        ext = os.path.splitext(fname)[1].lower()

        tmpdir = os.path.join(current_app.root_path, 'tmp')
        os.makedirs(tmpdir, exist_ok=True)

        # ---------- HEIC/HEIF ⇒ JPEG 変換 ----------
        if ext in ('.heic', '.heif'):
            jpeg_io, _ = _convert_heic_to_jpeg(img)
            tmp = os.path.join(tmpdir, f"{uuid4().hex}.jpg")
            with open(tmp, "wb") as fh:
                fh.write(jpeg_io.getbuffer())
        else:
            tmp = os.path.join(tmpdir, f"{uuid4().hex}_{fname}")
            img.save(tmp)
        file_size = os.path.getsize(tmp)
        current_app.logger.info(f"[analyze_material] image saved to {tmp}, file size: {file_size} bytes")

        # ③ AI処理
        t0 = time.time()
        pre = None
        raw = None
        ai_error = None
        try:
            pre = process_image_ai(tmp, preprocess=True)
            t1 = time.time()
            current_app.logger.info(f"[analyze_material] AI preprocess time: {t1 - t0:.2f}秒")
            raw = process_image_ai(tmp, preprocess=False)
            t2 = time.time()
            current_app.logger.info(f"[analyze_material] AI non-preprocess time: {t2 - t1:.2f}秒")
        except Exception as ai_e:
            ai_error = str(ai_e)
            current_app.logger.error(f"[analyze_material] AI processing error: {ai_e}", exc_info=True)
        finally:
            try:
                os.remove(tmp)
                current_app.logger.info(f"[analyze_material] tmp file removed: {tmp}")
            except Exception as rm_e:
                current_app.logger.warning(f"[analyze_material] tmp file remove failed: {tmp} {rm_e}")

        # ④ AI処理に失敗した場合もエラーレスポンス
        if ai_error:
            return jsonify({"status": "error", "message": f"AI processing error: {ai_error}"}), 500

        # ⑤ 正常レスポンス
        return jsonify({
            "status": "success",
            "preprocessed": pre,
            "non_preprocessed": raw
        }), 200

    except Exception as e:
        current_app.logger.error(f"[analyze_material] Exception: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Internal error occurred in analyze_material"}), 500


# ---- Flask アプリ共通部に413エラーハンドラもつけておく ----
def register_error_handlers(app: Flask):
    @app.errorhandler(413)
    def too_large(e):
        current_app.logger.error("[errorhandler 413] Payload too large (MAX_CONTENT_LENGTH 超過)")
        return jsonify({"status": "error", "message": "ファイルサイズが大きすぎます"}), 413

# ─────────────────────────────
# Get Cities & Addresses (API)
# ─────────────────────────────
@api_materials_bp.route('/get_cities/<prefecture>', methods=['GET'])
@jwt_required()
def get_cities(prefecture):
    try:
        user_sites = Site.query.filter(
            (Site.registered_user_id == get_current_user().id) | 
            Site.participants.any(get_current_user().id)
        ).filter(Site.site_prefecture.ilike(prefecture)).all()
        cities = sorted(list({site.site_city for site in user_sites}))
        return jsonify({'status': 'success', 'cities': cities}), 200
    except Exception as e:
        logger.error(f"Error fetching cities: {e}")
        return jsonify({'status': 'error', 'message': 'Error fetching cities.'}), 500

@api_materials_bp.route('/get_addresses/<prefecture>/<city>', methods=['GET'])
@jwt_required()
def get_addresses(prefecture, city):
    try:
        user_sites = Site.query.filter(
            (Site.registered_user_id == get_current_user().id) | 
            Site.participants.any(get_current_user().id)
        ).filter(Site.site_prefecture.ilike(prefecture), Site.site_city.ilike(city)).all()
        addresses = sorted(list({site.site_address for site in user_sites}))
        return jsonify({'status': 'success', 'addresses': addresses}), 200
    except Exception as e:
        logger.error(f"Error fetching addresses: {e}")
        return jsonify({'status': 'error', 'message': 'Error fetching addresses.'}), 500

# ─────────────────────────────
# Wanted Material Registration (API)
# ─────────────────────────────
@api_materials_bp.route('/register_wanted', methods=['POST'])
@jwt_required()
def register_wanted():
    current_app.logger.debug("Register wanted material API called.")

    # ログインユーザーの取得（状況に応じてメソッドが異なる）
    current_user_obj = get_current_user()
    if not current_user_obj:
        return jsonify({'status': 'error', 'message': '認証情報が無効です。'}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({
            'status': 'error',
            'message': 'リクエストボディは valid JSON で送ってください。'
        }), 400

    # == 1) フィールドごとのバリデーション ==
    # material_type は、"material_type" または "type" のどちらかで受け取る
    material_type = data.get('material_type') or data.get('type')
    if not material_type:
        return jsonify({'status': 'error', 'message': 'material_type は必須です。'}), 400

    # float変換を安全に行うためのヘルパー
    def safe_float(val):
        if val is None or val == '':
            return 0.0
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    # サイズについても "material_size_1" か "size_1" で受け取るように修正
    size_1 = safe_float(data.get('material_size_1') or data.get('size_1'))
    if size_1 is None:
        return jsonify({'status': 'error', 'message': 'material_size_1 は数値を指定してください。'}), 400
    size_2 = safe_float(data.get('material_size_2') or data.get('size_2'))
    if size_2 is None:
        return jsonify({'status': 'error', 'message': 'material_size_2 は数値を指定してください。'}), 400
    size_3 = safe_float(data.get('material_size_3') or data.get('size_3'))
    if size_3 is None:
        return jsonify({'status': 'error', 'message': 'material_size_3 は数値を指定してください。'}), 400

    # location は文字列に限定
    location_raw = data.get('location', "")
    if not isinstance(location_raw, str):
        return jsonify({'status': 'error', 'message': 'location は文字列で送ってください。'}), 400
    location = location_raw.strip()

    # quantity は整数チェック
    quantity_raw = data.get('quantity')
    if quantity_raw is None:
        return jsonify({'status': 'error', 'message': 'quantity は必須です。'}), 400
    try:
        quantity = int(quantity_raw)
    except (TypeError, ValueError):
        return jsonify({'status': 'error', 'message': 'quantity は整数を指定してください。'}), 400

    # deadline は ISO8601 形式か
    deadline_str = data.get('deadline')
    if not deadline_str:
        return jsonify({'status': 'error', 'message': '締め切り日時 (deadline) は必須です。'}), 400
    try:
        deadline = datetime.fromisoformat(deadline_str)
    except ValueError:
        return jsonify({'status': 'error', 'message': '締め切り日時は ISO8601 形式(YYYY-MM-DDTHH:MM:SS)で送ってください。'}), 400

    exclude_weekends = data.get('exclude_weekends') in [True, 'true', 'True', 1]
    note = data.get('note', None)

    # サブタイプ: material_type が木材なら wood_type、ボード材なら board_material_type など
    wood_type = data.get('wood_type') if material_type == "木材" else None
    board_material_type = data.get('board_material_type') if material_type == "ボード材" else None
    panel_type = data.get('panel_type') if material_type == "パネル材" else None

    # == 2) DB書き込み ==
    try:
        created_at = datetime.now(JST)
        new_wanted = WantedMaterial(
            user_id=current_user_obj.id,
            type=material_type,
            size_1=size_1,
            size_2=size_2,
            size_3=size_3,
            location=location,
            quantity=quantity,
            deadline=deadline,
            exclude_weekends=exclude_weekends,
            note=note,
            wood_type=wood_type,
            board_material_type=board_material_type,
            panel_type=panel_type,
            created_at=created_at,
            wm_prefecture='',
            wm_city='',
            wm_address='',
            completed=False,
            deleted=False
        )
        db.session.add(new_wanted)
        db.session.commit()

        # == 3) アクティビティログ ==
        log_user_activity(
            user_id=current_user_obj.id,
            action='Wanted Material Registration',
            details='User registered wanted material.',
            ip_address=request.remote_addr,
            device_info=request.user_agent.string,
            location='N/A'
        )

        # == 4) 成功レスポンス ==
        return jsonify({
            'status': 'success',
            'message': 'Wanted material registered successfully.',
            'wanted_material_id': new_wanted.id
        }), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error during wanted material registration: {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': 'サーバ内部でエラーが発生しました。'
        }), 500

# ─────────────────────────────
# Detail Endpoints
# ─────────────────────────────
@api_materials_bp.route('/detail/<int:material_id>', methods=['GET'])
@jwt_required()
def detail(material_id):
    material = Material.query.get_or_404(material_id)
    user = User.query.get_or_404(material.user_id)
    matched_materials_count = Material.query.filter_by(user_id=user.id, matched=True).count()
    return jsonify({
        'status': 'success',
        'material': material.to_dict(),
        'user': user.to_dict(),
        'total_matched_count': matched_materials_count
    }), 200

@api_materials_bp.route('/detail_wanted/<int:wanted_material_id>', methods=['GET'])
@jwt_required()
def detail_wanted(wanted_material_id):
    wanted_material = WantedMaterial.query.get_or_404(wanted_material_id)
    user = User.query.get_or_404(wanted_material.user_id)
    matched_count = WantedMaterial.query.filter_by(user_id=user.id, matched=True).count()
    return jsonify({
        'status': 'success',
        'wanted_material': wanted_material.to_dict(),
        'user': user.to_dict(),
        'total_matched_count': matched_count
    }), 200

# ─────────────────────────────
# Material List (API)
# ─────────────────────────────
@api_materials_bp.route('/material_list', methods=['GET'])
@jwt_required()
def material_list():
    current_user_obj = get_current_user()
    business_structure = current_user_obj.business_structure
    try:
        if business_structure in [0, 1]:
            unmatched_materials = Material.query.options(joinedload('owner')).join(User, Material.user_id == User.id).filter(
                Material.matched == False,
                Material.completed == False,
                Material.deleted == False,
                User.company_name == current_user_obj.company_name,
                User.prefecture == current_user_obj.prefecture,
                User.city == current_user_obj.city,
                User.address == current_user_obj.address
            ).all()
            matched_uncompleted_materials = Material.query.options(joinedload('owner')).join(Request, Material.id == Request.material_id).join(User, Material.user_id == User.id).filter(
                Material.matched == True,
                Material.completed == False,
                Material.deleted == False,
                User.company_name == current_user_obj.company_name,
                User.prefecture == current_user_obj.prefecture,
                User.city == current_user_obj.city,
                User.address == current_user_obj.address
            ).all()
            completed_materials = Material.query.options(joinedload('owner')).join(User, Material.user_id == User.id).filter(
                Material.completed == True,
                Material.deleted == False,
                User.company_name == current_user_obj.company_name,
                User.prefecture == current_user_obj.prefecture,
                User.city == current_user_obj.city,
                User.address == current_user_obj.address
            ).all()
        elif business_structure == 2:
            unmatched_materials = Material.query.options(joinedload('owner')).filter_by(
                user_id=current_user_obj.id,
                matched=False,
                completed=False,
                deleted=False
            ).all()
            matched_uncompleted_materials = Material.query.options(joinedload('owner')).join(Request, Material.id == Request.material_id).filter(
                Material.matched == True,
                Material.completed == False,
                Material.deleted == False,
                Material.user_id == current_user_obj.id
            ).all()
            completed_materials = Material.query.options(joinedload('owner')).filter_by(
                user_id=current_user_obj.id,
                completed=True,
                deleted=False
            ).all()
        else:
            unmatched_materials = []
            matched_uncompleted_materials = []
            completed_materials = []

        response_data = {
            'unmatched_materials': [m.to_dict() for m in unmatched_materials],
            'matched_uncompleted_materials': [m.to_dict() for m in matched_uncompleted_materials],
            'completed_materials': [m.to_dict() for m in completed_materials]
        }
        return jsonify({'status': 'success', 'data': response_data}), 200
    except Exception as e:
        current_app.logger.error(f"Error fetching material list: {e}")
        return jsonify({'status': 'error', 'message': 'Error fetching material list.'}), 500

# ─────────────────────────────
# Edit Material via AJAX (API)
# ─────────────────────────────
@api_materials_bp.route('/edit_material_ajax/<int:material_id>', methods=['POST'])
@jwt_required()
def edit_material_ajax(material_id):
    try:
        material = Material.query.get_or_404(material_id)
        current_user_obj = get_current_user()
        business_structure = current_user_obj.business_structure
        if business_structure in [0, 1]:
            owner = material.owner
            if (current_user_obj.company_name != owner.company_name or
                current_user_obj.prefecture != owner.prefecture or
                current_user_obj.city != owner.city or
                current_user_obj.address != owner.address):
                return jsonify({'status': 'error', 'message': 'Unauthorized.'}), 403
        elif business_structure == 2:
            if current_user_obj.id != material.user_id:
                return jsonify({'status': 'error', 'message': 'Unauthorized.'}), 403
        else:
            return jsonify({'status': 'error', 'message': 'Unauthorized.'}), 403

        data = request.get_json()
        type_field = data.get('type', '').strip()
        category = data.get('category', '').strip()
        quantity = data.get('quantity', 0)
        size_1 = data.get('size_1', 0.0)
        size_2 = data.get('size_2', 0.0)
        size_3 = data.get('size_3', 0.0)
        m_prefecture = data.get('m_prefecture', '').strip()
        m_city = data.get('m_city', '').strip()
        m_address = data.get('m_address', '').strip()
        deadline_str = data.get('deadline', '').strip()
        note = data.get('note', '').strip()

        try:
            deadline = datetime.strptime(deadline_str, '%Y-%m-%dT%H:%M')
            deadline = JST.localize(deadline)
            if deadline < datetime.now(JST):
                return jsonify({'status': 'error', 'message': 'Deadline cannot be in the past.'}), 400
        except ValueError:
            return jsonify({'status': 'error', 'message': 'Invalid deadline.'}), 400

        if type_field == "木材":
            wood_type = category
            board_material_type = ""
            panel_type = ""
        elif type_field == "ボード材":
            wood_type = ""
            board_material_type = category
            panel_type = ""
        elif type_field == "パネル材":
            wood_type = ""
            board_material_type = ""
            panel_type = category
        else:
            wood_type = ""
            board_material_type = ""
            panel_type = ""

        try:
            size_1 = float(size_1)
            size_2 = float(size_2)
            size_3 = float(size_3)
        except ValueError:
            return jsonify({'status': 'error', 'message': 'Sizes must be numeric.'}), 400

        material.type = type_field
        material.wood_type = wood_type
        material.board_material_type = board_material_type
        material.panel_type = panel_type
        material.quantity = quantity
        material.size_1 = size_1
        material.size_2 = size_2
        material.size_3 = size_3
        material.m_prefecture = m_prefecture
        material.m_city = m_city
        material.m_address = m_address
        material.location = f"{m_prefecture}{m_city}{m_address}"
        material.deadline = deadline
        material.note = note

        db.session.commit()
        return jsonify({'status': 'success', 'message': 'Material updated successfully.', 'material': material.to_dict()}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error editing material: {e}")
        return jsonify({'status': 'error', 'message': 'Error updating material.'}), 500

# ─────────────────────────────
# Delete Material via AJAX (API)
# ─────────────────────────────
@api_materials_bp.route('/delete_material_ajax/<int:material_id>', methods=['POST'])
@jwt_required()
def delete_material_ajax(material_id):
    try:
        material = Material.query.get_or_404(material_id)
        current_user_obj = get_current_user()
        business_structure = current_user_obj.business_structure
        if business_structure in [0, 1]:
            owner = material.owner
            if (current_user_obj.company_name != owner.company_name or
                current_user_obj.prefecture != owner.prefecture or
                current_user_obj.city != owner.city or
                current_user_obj.address != owner.address):
                return jsonify({'status': 'error', 'message': 'Unauthorized.'}), 403
        elif business_structure == 2:
            if current_user_obj.id != material.user_id:
                return jsonify({'status': 'error', 'message': 'Unauthorized.'}), 403
        else:
            return jsonify({'status': 'error', 'message': 'Unauthorized.'}), 403

        db.session.delete(material)
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'Material deleted successfully.'}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting material: {e}")
        return jsonify({'status': 'error', 'message': 'Error deleting material.'}), 500

# ─────────────────────────────
# Material Wanted List (API)
# ─────────────────────────────
@api_materials_bp.route('/material_wanted_list', methods=['GET'])
@jwt_required()
def material_wanted_list():
    current_user_obj = get_current_user()
    try:
        unmatched_wanted = WantedMaterial.query.filter(
            WantedMaterial.user_id == current_user_obj.id,
            WantedMaterial.matched == False,
            WantedMaterial.deleted == False
        ).all()
        matched_uncompleted_wanted = db.session.query(WantedMaterial, Request).join(
            Request, WantedMaterial.id == Request.wanted_material_id
        ).filter(
            Request.requested_user_id == current_user_obj.id,
            WantedMaterial.matched == True,
            WantedMaterial.completed == False,
            WantedMaterial.deleted == False
        ).all()
        completed_wanted = WantedMaterial.query.filter(
            WantedMaterial.user_id == current_user_obj.id,
            WantedMaterial.completed == True,
            WantedMaterial.deleted == False
        ).all()

        response_data = {
            'unmatched_wanted_materials': [wm.to_dict() for wm in unmatched_wanted],
            'matched_uncompleted_wanted_materials': [wm.to_dict() for wm, req in matched_uncompleted_wanted],
            'completed_wanted_materials': [wm.to_dict() for wm in completed_wanted]
        }
        log_user_activity(
            current_user_obj.id, 
            'Wanted Material List Display', 
            'User viewed wanted material list.', 
            request.remote_addr, 
            request.user_agent.string, 
            'N/A'
        )
        return jsonify({'status': 'success', 'data': response_data}), 200
    except Exception as e:
        current_app.logger.error(f"Error fetching wanted material list: {e}")
        return jsonify({'status': 'error', 'message': 'Error fetching wanted material list.'}), 500

# ─────────────────────────────
# Edit Wanted Material via AJAX (API)
# ─────────────────────────────
@api_materials_bp.route('/edit_wanted_material_ajax/<int:material_id>', methods=['POST'])
@jwt_required()
def edit_wanted_material_ajax(material_id):
    wanted_material = WantedMaterial.query.get_or_404(material_id)
    current_user_obj = get_current_user()
    if current_user_obj.id != wanted_material.user_id:
        return jsonify({'status': 'error', 'message': 'Unauthorized.'}), 403

    data = request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': 'Invalid data.'}), 400

    try:
        required_fields = ['type', 'quantity', 'deadline']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'status': 'error', 'message': f'{field} is required.'}), 400

        material_type = data['type']
        category_input = data.get('category', '').strip()
        if material_type in ["木材", "ボード材", "パネル材"] and not category_input:
            return jsonify({'status': 'error', 'message': 'Category is required for the selected material type.'}), 400

        quantity = int(data['quantity'])
        size_1 = float(data.get('size_1', 0.0))
        size_2 = float(data.get('size_2', 0.0))
        size_3 = float(data.get('size_3', 0.0))
        deadline_str = data['deadline'].strip()
        note = data.get('note', '').strip()

        try:
            deadline = datetime.strptime(deadline_str, '%Y-%m-%dT%H:%M')
            deadline = JST.localize(deadline)
            if deadline < datetime.now(JST):
                return jsonify({'status': 'error', 'message': 'Deadline cannot be in the past.'}), 400
        except ValueError:
            return jsonify({'status': 'error', 'message': 'Invalid deadline format.'}), 400

        if material_type == "木材":
            wood_type = category_input
            board_material_type = ""
            panel_type = ""
        elif material_type == "ボード材":
            wood_type = ""
            board_material_type = category_input
            panel_type = ""
        elif material_type == "パネル材":
            wood_type = ""
            board_material_type = ""
            panel_type = category_input
        else:
            wood_type = ""
            board_material_type = ""
            panel_type = ""

        wanted_material.type = material_type
        wanted_material.quantity = quantity
        wanted_material.size_1 = size_1
        wanted_material.size_2 = size_2
        wanted_material.size_3 = size_3
        wanted_material.deadline = deadline
        wanted_material.note = note
        wanted_material.wood_type = wood_type
        wanted_material.board_material_type = board_material_type
        wanted_material.panel_type = panel_type

        db.session.commit()

        formatted_deadline = wanted_material.deadline.isoformat() if wanted_material.deadline else 'Not set'

        return jsonify({
            'status': 'success',
            'message': 'Wanted material updated successfully.',
            'wanted_material': {
                'type': wanted_material.type,
                'quantity': wanted_material.quantity,
                'size_1': wanted_material.size_1,
                'size_2': wanted_material.size_2,
                'size_3': wanted_material.size_3,
                'deadline': formatted_deadline,
                'note': wanted_material.note or "",
                'wood_type': wanted_material.wood_type,
                'board_material_type': wanted_material.board_material_type,
                'panel_type': wanted_material.panel_type
            }
        }), 200

    except ValueError as ve:
        current_app.logger.error(f"Value error during update: {ve}")
        return jsonify({'status': 'error', 'message': 'Numeric fields must be valid numbers.'}), 400
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating wanted material: {e}")
        return jsonify({'status': 'error', 'message': 'Error updating wanted material.'}), 500

# ─────────────────────────────
# Delete Wanted Material via AJAX (API)
# ─────────────────────────────
@api_materials_bp.route('/delete_wanted_material_ajax/<int:wanted_material_id>', methods=['POST'])
@jwt_required()
def delete_wanted_material_ajax(wanted_material_id):
    current_user_obj = get_current_user()
    wanted_material = WantedMaterial.query.get_or_404(wanted_material_id)
    if current_user_obj.id != wanted_material.user_id:
        return jsonify({'status': 'error', 'message': 'Unauthorized.'}), 403
    try:
        db.session.delete(wanted_material)
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'Wanted material deleted successfully.'}), 200
    except Exception as e:
        logger.error(f"Error deleting wanted material: {e}")
        return jsonify({'status': 'error', 'message': 'Error deleting wanted material.'}), 500

# ─────────────────────────────
# Delete Material History (API)
# ─────────────────────────────
@api_materials_bp.route('/delete_history_material/<int:material_id>', methods=['POST'])
@jwt_required()
def delete_history_material(material_id):
    try:
        current_user_obj = get_current_user()
        material = Material.query.get_or_404(material_id)
        if current_user_obj.id != material.user_id:
            return jsonify({'status': 'error', 'message': 'Unauthorized to delete history.'}), 403
        material.deleted = True
        material.deleted_at = datetime.now(JST)
        db.session.commit()
        log_user_activity(
            current_user_obj.id, 
            'History Delete', 
            f'User deleted history for material ID: {material_id}.', 
            request.remote_addr, 
            request.user_agent.string, 
            'N/A'
        )
        return jsonify({'status': 'success', 'message': 'History deleted successfully.'}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting material history: {e}")
        return jsonify({'status': 'error', 'message': 'Error deleting material history.'}), 500

# ─────────────────────────────
# Delete Wanted Material History (API)
# ─────────────────────────────
@api_materials_bp.route('/delete_history_wanted_material/<int:material_id>', methods=['POST'])
@jwt_required()
def delete_history_wanted_material(material_id):
    try:
        current_user_obj = get_current_user()
        wanted_material = WantedMaterial.query.get_or_404(material_id)
        if current_user_obj.id != wanted_material.user_id:
            return jsonify({'status': 'error', 'message': 'Unauthorized to delete history.'}), 403
        wanted_material.deleted = True
        wanted_material.deleted_at = datetime.now(JST)
        db.session.commit()
        log_user_activity(
            current_user_obj.id, 
            'History Delete', 
            f'User deleted history for wanted material ID: {material_id}.', 
            request.remote_addr, 
            request.user_agent.string, 
            'N/A'
        )
        return jsonify({'status': 'success', 'message': 'History deleted successfully.'}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting wanted material history: {e}")
        return jsonify({'status': 'error', 'message': 'Error deleting wanted material history.'}), 500

# ─────────────────────────────
# Bulk Register Wanted Materials (API)
# ─────────────────────────────
@api_materials_bp.route('/bulk_register_wanted', methods=['POST'])
@jwt_required()
def bulk_register_wanted():
    current_user_obj = get_current_user()
    try:
        data = request.get_json()
        materials_list = data.get('materials', [])
        for entry in materials_list:
            new_wanted = WantedMaterial(
                user_id=current_user_obj.id,
                type=entry.get('material_type'),
                size_1=entry.get('material_size_1') or 0.0,
                size_2=entry.get('material_size_2') or 0.0,
                size_3=entry.get('material_size_3') or 0.0,
                location=f"{entry.get('m_prefecture','')} {entry.get('m_city','')} {entry.get('m_address','')}",
                quantity=entry.get('quantity'),
                deadline=entry.get('deadline'),
                exclude_weekends=entry.get('exclude_weekends'),
                note=entry.get('note'),
                wood_type=entry.get('wood_type'),
                board_material_type=entry.get('board_material_type'),
                panel_type=entry.get('panel_type')
            )
            db.session.add(new_wanted)
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'Bulk wanted materials registered successfully.'}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Bulk wanted registration error: {e}")
        return jsonify({'status': 'error', 'message': 'Error during bulk registration.'}), 500
