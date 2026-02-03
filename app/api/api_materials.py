# app/api/api_materials.py

from flask import Flask, Blueprint, request, jsonify, current_app, url_for
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
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import SQLAlchemyError
from app.image_processing import process_image_ai
from app.blueprints.utils import log_user_activity
from app.utils.s3_uploader import upload_file_to_s3, build_s3_url, convert_heic_to_jpeg
import requests
from math import radians, cos, sin, asin, sqrt

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

# 住所→緯度経度
def geocode_address(address: str) -> tuple[float, float] | None:
    """
    Google Geocoding APIで住所を座標化。
    .env / 設定: GOOGLE_API_KEY を使用
    """
    try:
        key = (
            current_app.config.get("GOOGLE_API_KEY")
            or os.environ.get("GOOGLE_API_KEY", "")
        )
        if not address.strip() or not key:
            return None
        url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {"address": address, "key": key, "language": "ja"}
        r = requests.get(url, params=params, timeout=10)
        if r.status_code != 200:
            current_app.logger.warning(f"Geocode HTTP {r.status_code}: {r.text[:200]}")
            return None
        data = r.json()
        if not data.get("results"):
            return None
        loc = data["results"][0]["geometry"]["location"]
        return float(loc["lat"]), float(loc["lng"])
    except Exception as e:
        current_app.logger.error(f"geocode_address error: {e}")
        return None

# ─────────────────────────────
# Haversine: 2点間の距離(km)
# ─────────────────────────────
def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0  # 地球半径 km
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    return R * c

def normalize_tags(tags_value):
    """
    Flutter から配列 or カンマ区切り文字列で来ても、
    DB 側では 1 本の文字列として保存するためのヘルパー。
    """
    if tags_value is None:
        return None
    # 配列で来た場合: ["木材", "端材", "無料"] → "木材,端材,無料"
    if isinstance(tags_value, list):
        cleaned = [str(t).strip() for t in tags_value if str(t).strip()]
        return ",".join(cleaned) if cleaned else None
    # 文字列で来た場合: "木材, 端材 , 無料"
    if isinstance(tags_value, str):
        t = tags_value.strip()
        return t or None
    # それ以外の型は無視
    return None

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

    # サイズが数値でない場合もバリデーションエラーとして返す
    if errors:
        current_app.logger.error("Validation errors (sizes): %s", errors)
        return jsonify({
            "status": "error",
            "message": "Validation errors",
            "errors": errors
        }), 422

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
        storage_place = (data.get("storage_place") or "").strip()

        # AI 位置情報（ai_location）があればそちらを優先したい場合はここで処理
        # 今回の例ではフォーム優先にしているため省略。
        current_app.logger.debug("Using form location: '%s'", location)
    except Exception as e:
        current_app.logger.error("Error processing location data: %s", e)
        return jsonify({"status": "error", "message": "Error processing location data."}), 500

    # 7.5 住所→座標（lat/lng）を自動付与
    # 👉 Flutter から送られてくる lat/lng には頼らず、
    #    フォームに入力された住所からのみジオコーディングする
    lat = None
    lng = None
    try:
        geo = geocode_address(location)
        if geo:
            lat, lng = geo
            current_app.logger.debug(
                f"Geocoded lat/lng from address: {lat}, {lng}"
            )
        else:
            current_app.logger.warning(
                f"Geocoding failed or empty address. location='{location}'"
            )
    except Exception as e:
        current_app.logger.error(
            f"Geocoding / lat-lng resolving exception: {e}"
        )

    # ③ どちらでも取れなかった場合はフォームバリデーションエラーとして扱う
    #    → フロント側で住所フィールドに「詳細な住所に修正してください」と表示する想定
    if lat is None or lng is None:
        errors.append("location: 詳細な住所（番地・建物名まで）を入力してください。")
        current_app.logger.warning(
            "Lat/Lng could not be resolved from address: %s", location
        )
        return jsonify({
            "status": "error",
            "message": "Validation errors",
            "errors": errors
        }), 422

    # ---------------------------------------------------
    # 7.8 タイトル・タグの取得
    # ---------------------------------------------------
    title_val = (data.get("title") or "").strip()
    tags_val  = normalize_tags(data.get("tags"))
    # 収納場所（例: 1st Floor）を受け取る
    # Flutter 側からは storagePlace で送っても OK にしておく
    storage_place_val = (
        data.get("storage_place")
        or data.get("storagePlace")
        or ""
    ).strip()

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
            latitude = lat,
            longitude = lng,
            quantity = quantity_val,
            deadline = deadline_val,
            exclude_weekends = (
                bool(data.get("exclude_weekends"))
                if isinstance(data.get("exclude_weekends"), bool)
                else str(data.get("exclude_weekends")).lower() in ['true', '1']
            ),
            image = image_key,
            note = data.get("note"),
            title = title_val,
            tags = tags_val,
            storage_place = storage_place_val,
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

@api_materials_bp.route('/material_list', methods=['GET'])
@jwt_required()
def material_list():
    current_user_obj = get_current_user()
    business_structure = current_user_obj.business_structure

    try:
        if business_structure in [0, 1]:
            # 法人：同じ会社 & 同じ住所の資材を対象
            unmatched_materials = (
                Material.query.options(
                    joinedload(Material.owner),
                    joinedload(Material.group),
                )
                .join(User, Material.user_id == User.id)
                .filter(
                    Material.matched == False,
                    Material.completed == False,
                    Material.deleted == False,
                    Material.pre_completed == False,   # ✅ 追加
                    User.company_name == current_user_obj.company_name,
                    User.prefecture == current_user_obj.prefecture,
                    User.city == current_user_obj.city,
                    User.address == current_user_obj.address,
                )
                .all()
            )

            matched_uncompleted_materials = (
                Material.query.options(
                    joinedload(Material.owner),
                    joinedload(Material.group),
                )
                .join(Request, Material.id == Request.material_id)
                .join(User, Material.user_id == User.id)
                .filter(
                    Material.matched == True,
                    Material.completed == False,
                    Material.deleted == False,
                    Material.pre_completed == False,   # ✅ 追加
                    User.company_name == current_user_obj.company_name,
                    User.prefecture == current_user_obj.prefecture,
                    User.city == current_user_obj.city,
                    User.address == current_user_obj.address,
                )
                .all()
            )

            completed_materials = (
                Material.query.options(
                    joinedload(Material.owner),
                    joinedload(Material.group),
                )
                .join(User, Material.user_id == User.id)
                .filter(
                    Material.completed == True,
                    Material.deleted == False,
                    Material.pre_completed == False,   # ✅ 追加
                    User.company_name == current_user_obj.company_name,
                    User.prefecture == current_user_obj.prefecture,
                    User.city == current_user_obj.city,
                    User.address == current_user_obj.address,
                )
                .all()
            )

        elif business_structure == 2:
            # 個人：自分の資材だけ
            unmatched_materials = (
                Material.query.options(
                    joinedload(Material.owner),
                    joinedload(Material.group),
                )
                .filter_by(
                    user_id=current_user_obj.id,
                    matched=False,
                    completed=False,
                    deleted=False,
                    pre_completed=False,  # ✅ 追加
                )
                .all()
            )

            matched_uncompleted_materials = (
                Material.query.options(
                    joinedload(Material.owner),
                    joinedload(Material.group),
                )
                .join(Request, Material.id == Request.material_id)
                .filter(
                    Material.matched == True,
                    Material.completed == False,
                    Material.deleted == False,
                    Material.pre_completed == False,  # ✅ 追加
                    Material.user_id == current_user_obj.id,
                )
                .all()
            )

            completed_materials = (
                Material.query.options(
                    joinedload(Material.owner),
                    joinedload(Material.group),
                )
                .filter_by(
                    user_id=current_user_obj.id,
                    completed=True,
                    deleted=False,
                    pre_completed=False,  # ✅ 追加
                )
                .all()
            )

        else:
            unmatched_materials = []
            matched_uncompleted_materials = []
            completed_materials = []

        # ✅ Flutter GiveMaterial に必要な形へ統一（user / image_url / group_name / lat / lng）
        response_data = {
            'unmatched_materials': [
                material_to_give_json(m, include_user=True)
                for m in unmatched_materials
            ],
            'matched_uncompleted_materials': [
                material_to_give_json(m, include_user=True)
                for m in matched_uncompleted_materials
            ],
            'completed_materials': [
                material_to_give_json(m, include_user=True)
                for m in completed_materials
            ],
        }

        return jsonify({'status': 'success', 'data': response_data}), 200

    except Exception as e:
        current_app.logger.error(f"Error fetching material list: {e}", exc_info=True)
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
        title = data.get('title', '').strip()
        tags_raw = data.get('tags')
        tags = normalize_tags(tags_raw)

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
        material.title = title
        material.tags = tags

        # 住所が変わった場合は、lat/lng も更新
        try:
            new_location = material.location.strip()
            geo = geocode_address(new_location) if new_location else None
            if geo:
                material.latitude, material.longitude = geo
                current_app.logger.debug(
                    f"[edit] Geocoded lat/lng: {material.latitude}, {material.longitude}"
                )
            else:
                # 失敗時は既存値を維持（NULL のままでも可）
                current_app.logger.info("[edit] Geocoding failed. Keep existing lat/lng.")
        except Exception as e:
            current_app.logger.error(f"[edit] Geocoding exception: {e}")

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

@api_materials_bp.route('/nearby', methods=['POST'])
def nearby_materials():
    """
    ユーザーの現在地(lat/lng)から指定距離以内の資材を検索して返す。
    DB に保存されている lat/lng を利用。
    認証不要。
    """
    payload = request.get_json(silent=True) or {}
    try:
        base_lat = float(payload.get("lat"))
        base_lng = float(payload.get("lng"))
        radius = float(payload.get("radius", 10.0))  # デフォルト10km
    except Exception:
        return jsonify({"status": "error", "message": "lat/lng は数値で送ってください"}), 400

    try:
        # ✅ 未削除 & pre_completed除外 & 緯度経度ありの資材を取得
        mats = (
            Material.query
            .options(joinedload(Material.owner), joinedload(Material.group))
            .filter(
                Material.deleted == False,
                Material.pre_completed == False,   # ✅ 追加（pre_completed を返さない）
                Material.latitude.isnot(None),
                Material.longitude.isnot(None)
            )
            .all()
        )

        results = []
        for m in mats:
            lat, lng = m.latitude, m.longitude
            if lat is None or lng is None:
                continue

            dist_km = haversine(base_lat, base_lng, lat, lng)

            if dist_km <= radius:
                # ✅ 共通整形で返す（pre_completed も含まれる）
                material_dict = material_to_give_json(m, include_user=True)

                results.append({
                    "material": material_dict,
                    "distance_km": round(dist_km, 2),
                })

        results.sort(key=lambda x: x["distance_km"])

        return jsonify({
            "status": "success",
            "count": len(results),
            "materials": results,
        }), 200

    except Exception as e:
        current_app.logger.error(f"/nearby error: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "サーバー内部でエラーが発生しました"}), 500

# ---------------------------------------------------
# 特定ユーザーの資材一覧取得
# ---------------------------------------------------
@api_materials_bp.route('/user/<int:user_id>', methods=['GET'])
def materials_by_user(user_id):
    """
    MainExploreMaterialUserScreen 用
    指定ユーザーの資材を返す。
    - deleted は除外
    - matched/completed は含める（フロントのフィルタで使う）
    - user 情報を埋め込む
    - image_url/lat/lng/group_name を補完
    ※ 認証不要（未ログインでも利用可）
    """
    try:
        # 将来権限制御する場合は、ここで「任意JWT」を見るようにする想定
        # 例）verify_jwt_in_request(optional=True) など
        # 現状は使わないのでコメントアウト
        # _current = get_current_user()

        mats = (
            Material.query
            .options(
                joinedload(Material.owner),
                joinedload(Material.group),
            )
            .filter(
                Material.user_id == user_id,
                Material.deleted == False,
            )
            .order_by(Material.created_at.desc())
            .all()
        )

        materials_json = [
            material_to_give_json(m, include_user=True)
            for m in mats
        ]

        return jsonify({
            "status": "success",
            "count": len(materials_json),
            "materials": materials_json,
        }), 200

    except Exception as e:
        current_app.logger.error(
            f"Error fetching materials by user: {e}",
            exc_info=True
        )
        return jsonify({
            "status": "error",
            "message": "Error fetching user materials."
        }), 500

# ─────────────────────────────
# Storage Place List (API)
# ─────────────────────────────
@api_materials_bp.route('/storage_place', methods=['GET'])
@jwt_required()
def get_storage_place_list():
    """
    自分が過去に登録した資材の storage_place を一覧で返す。
    - deleted は除外
    - 空文字は除外
    - DISTINCT で重複排除
    """
    current_user_obj = get_current_user()
    if not current_user_obj:
        return jsonify({"status": "error", "message": "認証情報が無効です。"}), 401

    try:
        rows = (
            db.session.query(Material.storage_place)
            .filter(
                Material.user_id == current_user_obj.id,
                Material.deleted == False,
                Material.storage_place.isnot(None),
            )
            .distinct()
            .all()
        )

        storage_places = []
        for (sp,) in rows:
            if sp and str(sp).strip():
                storage_places.append(str(sp).strip())

        # 念のため set + sort
        storage_places = sorted(list(set(storage_places)))

        return jsonify({
            "status": "success",
            "count": len(storage_places),
            "storage_places": storage_places,
        }), 200

    except Exception as e:
        current_app.logger.error(f"Error fetching storage_place list: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": "storage_place の取得でエラーが発生しました。"
        }), 500

def material_to_give_json(m: Material, include_user: bool = True):
    # ✅ to_dict() から必ず pre_completed が入る
    d = m.to_dict(include_user=include_user)

    # --- image_url を必ず付与 ---
    img = getattr(m, "image", None)
    if img:
        if isinstance(img, str) and img.startswith(("http://", "https://")):
            d["image_url"] = img
        else:
            d["image_url"] = build_s3_url(img)
    else:
        d["image_url"] = build_s3_url("materials/no_image.png")

    # --- Flutter側は lat/lng を読むので合わせる ---
    d["lat"] = m.latitude
    d["lng"] = m.longitude

    # --- storage_place はモデルにあるので念のため空対策 ---
    d["storage_place"] = m.storage_place or ""

    # =========================================================
    # ✅ グループ情報（削除済みグループは “表示しない + group_idも返さない”）
    # =========================================================
    grp = getattr(m, "group", None)

    # deleted_at があるグループは削除済みなので無視する
    is_active_group = bool(grp) and getattr(grp, "deleted_at", None) is None

    if is_active_group:
        d["group_name"] = getattr(grp, "name", None)
        # 必要なら追加で返してもOK（Flutter側で使える）
        d["group"] = {
            "id": getattr(grp, "id", None),
            "name": getattr(grp, "name", None),
            "deleted_at": None,
        }
    else:
        # ✅ 削除済み or そもそも無所属
        d["group_name"] = None
        d["group"] = None
        d["group_id"] = None  # ✅ 追加：削除済みグループは痕跡ごと消す

    # ✅ 念のため camelCase も返す（GiveMaterial.fromJson 対策）
    d["preCompleted"] = bool(d.get("pre_completed", False))

    return d


def user_to_wanted_user_dict(u: User) -> dict:
    return {
        "id": u.id,
        "email": getattr(u, "email", None),
        "company_name": getattr(u, "company_name", None),
        "prefecture": getattr(u, "prefecture", None),
        "city": getattr(u, "city", None),
        "address": getattr(u, "address", None),
        "business_structure": getattr(u, "business_structure", None),
        "industry": getattr(u, "industry", None),
        "job_title": getattr(u, "job_title", None),
    }


def wanted_material_to_json(
    wm: WantedMaterial,
    user_dict: dict,
    group_name_map: dict[int, str]
):
    raw_gid = getattr(wm, "group_id", None)
    group_name = group_name_map.get(raw_gid) if raw_gid else None

    # ✅ 削除済みグループは group_name_map に存在しない → group_id も潰す
    group_id = raw_gid if group_name else None

    return {
        "id": wm.id,
        "type": wm.type,
        "wood_type": getattr(wm, "wood_type", None),
        "board_material_type": getattr(wm, "board_material_type", None),
        "panel_type": getattr(wm, "panel_type", None),

        "size_1": float(getattr(wm, "size_1", 0.0) or 0.0),
        "size_2": float(getattr(wm, "size_2", 0.0) or 0.0),
        "size_3": float(getattr(wm, "size_3", 0.0) or 0.0),

        "quantity": int(getattr(wm, "quantity", 0) or 0),

        "deadline": wm.deadline.isoformat() if getattr(wm, "deadline", None) else None,
        "created_at": wm.created_at.isoformat() if getattr(wm, "created_at", None) else None,

        "exclude_weekends": bool(getattr(wm, "exclude_weekends", False)),
        "note": (getattr(wm, "note", None) or ""),
        "location": (getattr(wm, "location", None) or ""),

        # ✅ フィルターに必要
        "matched": bool(getattr(wm, "matched", False)),
        "completed": bool(getattr(wm, "completed", False)),
        "deleted": bool(getattr(wm, "deleted", False)),

        # ✅ グループ（Flutterが無視してもOK）
        "group_id": group_id,
        "group_name": group_name,

        # ✅ user（WantedUserモデルで読む）
        "user": user_dict,
    }


@api_materials_bp.route('/my-provided', methods=['GET'])
@jwt_required()
def my_provided_materials():
    current_user_obj = get_current_user()
    if not current_user_obj:
        return jsonify({"status": "error", "message": "認証情報が無効です。"}), 401

    try:
        mats = (
            Material.query
            .options(joinedload(Material.owner), joinedload(Material.group))
            .filter(
                Material.user_id == current_user_obj.id,
                Material.deleted == False,
                Material.pre_completed == False,
            )
            .order_by(Material.created_at.desc())
            .all()
        )

        materials_json = [
            material_to_give_json(m, include_user=True)
            for m in mats
        ]

        return jsonify({
            "status": "success",
            "count": len(materials_json),
            "materials": materials_json,
        }), 200

    except Exception as e:
        current_app.logger.error(f"Error fetching my-provided: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": "提供した資材一覧の取得でエラーが発生しました。"
        }), 500


@api_materials_bp.route('/my-wanted', methods=['GET'])
@jwt_required()
def my_wanted_materials():
    current_user_obj = get_current_user()
    if not current_user_obj:
        return jsonify({"status": "error", "message": "認証情報が無効です。"}), 401

    try:
        wms = (
            WantedMaterial.query
            .filter(
                WantedMaterial.user_id == current_user_obj.id,
                WantedMaterial.deleted == False,
            )
            .order_by(WantedMaterial.created_at.desc())
            .all()
        )

        # ✅ group_id がある場合だけまとめて group_name を取る（N+1防止）
        group_ids = []
        for wm in wms:
            gid = getattr(wm, "group_id", None)
            if gid:
                group_ids.append(gid)

        group_name_map = {}
        if group_ids:
            groups = (
                UserGroup.query
                .filter(
                    UserGroup.id.in_(list(set(group_ids))),
                    UserGroup.deleted_at.is_(None)
                )
                .all()
            )
            group_name_map = {g.id: g.name for g in groups}

        user_dict = user_to_wanted_user_dict(current_user_obj)

        materials_json = [
            wanted_material_to_json(wm, user_dict, group_name_map)
            for wm in wms
        ]

        return jsonify({
            "status": "success",
            "count": len(materials_json),
            "materials": materials_json,
        }), 200

    except Exception as e:
        current_app.logger.error(f"Error fetching my-wanted: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": "ほしい資材一覧の取得でエラーが発生しました。"
        }), 500
