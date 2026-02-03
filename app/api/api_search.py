# app/api/api_search.py

import traceback
from flask import Blueprint, request, jsonify, current_app, url_for
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import Material, WantedMaterial, User, GroupMembership, UserGroup
from app.blueprints.utils import log_user_activity
from datetime import datetime, timedelta
from sqlalchemy import desc, or_
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import SQLAlchemyError
import pytz
import logging
from app.utils.s3_uploader import build_s3_url
from app import db
import re
import traceback

api_search_bp = Blueprint('api_search', __name__, url_prefix='/api/search')
JST = pytz.timezone('Asia/Tokyo')
now = datetime.now(JST)

logger = logging.getLogger(__name__)

def validate_material_search_data(data):
    """
    材料検索の入力データをバリデーションします。
    必須:
      - material_type  または keyword のどちらか一方
    Optional:
      - size_1, size_2, size_3, m_prefecture, m_city,
        wood_type, board_material_type, panel_type, keyword
    """
    has_material_type = 'material_type' in data and str(data['material_type']).strip() != ''
    has_keyword = 'keyword' in data and str(data['keyword']).strip() != ''

    if not (has_material_type or has_keyword):
        raise ValueError("material_type か keyword のいずれかを指定してください。")

    # 数値型のチェック（空文字は 0.0 とみなす）
    for size_field in ['size_1', 'size_2', 'size_3']:
        if size_field in data:
            try:
                value = data[size_field]
                if value == "" or value is None:
                    data[size_field] = 0.0
                else:
                    data[size_field] = float(value)
            except ValueError:
                raise ValueError(f"{size_field} は数値でなければなりません。")

    # 文字列型のチェック
    for field in ['m_prefecture', 'm_city', 'wood_type',
                  'board_material_type', 'panel_type', 'keyword']:
        if field in data and not isinstance(data[field], str):
            raise ValueError(f"{field} は文字列でなければなりません。")

def _extract_distance_km(keyword: str):
    """
    keyword 文字列から `{数字}km` を抽出。
    例:
      "3km" -> (3.0, "")
      "3km 杉" -> (3.0, "杉")
      "杉 3km" -> (3.0, "杉")
      "杉" -> (None, "杉")
    """
    if not keyword:
        return None, ""

    m = re.search(r'(\d+(?:\.\d+)?)\s*km', keyword, flags=re.IGNORECASE)
    if not m:
        return None, keyword.strip()

    try:
        km = float(m.group(1))
    except Exception:
        km = None

    # kmトークンを除去した“文字検索用キーワード”
    keyword_text = re.sub(r'(\d+(?:\.\d+)?)\s*km', '', keyword, flags=re.IGNORECASE).strip()

    return km, keyword_text

def validate_wanted_material_search_data(data):
    """
    希望材料検索の入力データをバリデーションします。
    必須項目: material_type
    Optional: size_1, size_2, size_3, location, city, wood_type, board_material_type, panel_type
    """
    required_fields = ['material_type']
    for field in required_fields:
        if field not in data:
            raise ValueError(f"{field} が必要です。")
    # 数値型のチェック
    for size_field in ['size_1', 'size_2', 'size_3']:
        if size_field in data and not isinstance(data[size_field], (int, float)):
            raise ValueError(f"{size_field} は数値でなければなりません。")
    # 文字列型のチェック
    for field in ['location', 'city', 'wood_type', 'board_material_type', 'panel_type']:
        if field in data and not isinstance(data[field], str):
            raise ValueError(f"{field} は文字列でなければなりません。")

def material_to_give_json(m: Material, include_user: bool = True):
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

    # --- storage_place 空対策 ---
    d["storage_place"] = m.storage_place or ""

    # --- group_name を補完 ---
    grp = getattr(m, "group", None)
    d["group_name"] = getattr(grp, "name", None) if grp else None

    return d

@api_search_bp.route('/materials', methods=['POST'])
@jwt_required(optional=True)  # ✅ 未ログインでもOK
def search_public_materials():
    try:
        payload = request.get_json(silent=True) or {}

        # -----------------------------
        # 1) JWTがあれば user_id を取る（無ければ None）
        # -----------------------------
        user_id = get_jwt_identity()

        # -----------------------------
        # 2) 検索パラメータ
        # -----------------------------
        material_type = (payload.get("material_type") or "").strip()
        keyword = (payload.get("keyword") or "").strip()

        def safe_float(v):
            try:
                return float(v)
            except Exception:
                return 0.0

        size_1 = safe_float(payload.get("size_1") or 0.0)
        size_2 = safe_float(payload.get("size_2") or 0.0)
        size_3 = safe_float(payload.get("size_3") or 0.0)

        m_prefecture = (payload.get("m_prefecture") or "").strip()
        m_city = (payload.get("m_city") or "").strip()

        # -----------------------------
        # 3) 「ログイン済みなら所属グループID」を取得
        # -----------------------------
        allowed_group_ids = []
        if user_id:
            memberships = (
                GroupMembership.query
                .join(UserGroup, GroupMembership.group_id == UserGroup.id)
                .filter(
                    GroupMembership.user_id == user_id,
                    UserGroup.deleted_at.is_(None),
                )
                .all()
            )
            allowed_group_ids = [
                int(m.group_id) for m in memberships
                if m.group_id is not None
            ]

        current_app.logger.debug(
            f"[search/materials] user_id={user_id}, allowed_group_ids={allowed_group_ids}"
        )

        # -----------------------------
        # 4) ベースクエリ（public検索）
        # -----------------------------
        today = datetime.now(JST).date()

        query = (
            Material.query
            .options(
                joinedload(Material.owner),
                joinedload(Material.group),
            )
            .join(User, Material.user_id == User.id)
            .filter(
                Material.matched.is_(False),
                Material.deleted.is_(False),
                Material.deadline >= today,
            )
        )

        # ✅✅✅ 今回の要件：
        # ログイン済み → public + 所属グループ
        # 未ログイン → publicのみ
        if allowed_group_ids:
            query = query.filter(
                or_(
                    Material.group_id.is_(None),
                    Material.group_id == 0,
                    Material.group_id.in_(allowed_group_ids),
                )
            )
        else:
            query = query.filter(
                or_(
                    Material.group_id.is_(None),
                    Material.group_id == 0,
                )
            )

        # -----------------------------
        # 5) サイズフィルタ（>= 条件）
        # -----------------------------
        query = query.filter(
            Material.size_1 >= size_1,
            Material.size_2 >= size_2,
            Material.size_3 >= size_3,
        )

        # -----------------------------
        # 6) 都道府県 / 市区町村フィルタ
        # -----------------------------
        if m_prefecture:
            query = query.filter(Material.m_prefecture == m_prefecture)
        if m_city:
            query = query.filter(Material.m_city.ilike(f"%{m_city}%"))

        # -----------------------------
        # 7) material_type フィルタ
        # -----------------------------
        if material_type:
            query = query.filter(Material.type == material_type)

        # -----------------------------
        # 8) keyword フィルタ
        # -----------------------------
        if keyword:
            like = f"%{keyword}%"
            query = query.filter(
                or_(
                    Material.title.ilike(like),
                    Material.tags.ilike(like),
                    Material.type.ilike(like),
                    Material.m_prefecture.ilike(like),
                    Material.m_city.ilike(like),
                    Material.m_address.ilike(like),
                    Material.wood_type.ilike(like),
                    Material.board_material_type.ilike(like),
                    Material.panel_type.ilike(like),
                    User.company_name.ilike(like),
                )
            )

        # -----------------------------
        # 9) ソート & 取得
        # -----------------------------
        query = query.order_by(Material.created_at.desc())
        mats = query.all()

        # ✅✅✅ ここで「登録ユーザーの法人コード」を必ず付与する
        materials_json = []
        for m in mats:
            d = material_to_give_json(m, include_user=True)

            owner = getattr(m, "owner", None)
            company_code = getattr(owner, "company_code", None) if owner else None

            # トップレベルにも付与（Flutter側が拾いやすい）
            d["company_code"] = company_code or ""

            # include_user=True のとき user dict があればそこにも付与
            if isinstance(d.get("user"), dict):
                d["user"]["company_code"] = company_code or ""

            materials_json.append(d)

        return jsonify({
            "success": True,
            "data": {
                "distance_km": None,
                "materials": materials_json,
            }
        }), 200

    except SQLAlchemyError as e:
        current_app.logger.error(f"DB error in /api/search/materials: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "message": "Database error occurred."
        }), 500

    except Exception as e:
        current_app.logger.error(f"Error in /api/search/materials: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "message": "Internal server error."
        }), 500

@api_search_bp.route('/wanted_materials', methods=['POST'])
@jwt_required()
def search_wanted_materials_api():
    """
    希望材料を検索するAPIエンドポイント。
    JSON形式で検索条件を受け取り、検索結果を返します。
    JWT認証により、トークンからユーザー情報を取得します。
    """
    # JWTからユーザーIDを取得し、DBからユーザー情報をロード
    user_id = get_jwt_identity()
    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({'success': False, 'message': 'ユーザーが見つかりません。'}), 404

    if not request.is_json:
        return jsonify({'success': False, 'message': 'JSON形式のデータを送信してください。'}), 400

    data = request.get_json()

    try:
        validate_wanted_material_search_data(data)
    except ValueError as e:
        return jsonify({'success': False, 'message': str(e)}), 400

    # 検索パラメータの抽出
    material_type = data.get('material_type')
    size_1 = data.get('size_1', 0.0)
    size_2 = data.get('size_2', 0.0)
    size_3 = data.get('size_3', 0.0)
    location = data.get('location', '').strip()  # 都道府県（User.prefecture）
    city = data.get('city', '').strip()          # 市区町村（WantedMaterial側: wm_city）
    wood_type = data.get('wood_type', '').strip()
    board_material_type = data.get('board_material_type', '').strip()
    panel_type = data.get('panel_type', '').strip()

    current_date = (datetime.now(JST) - timedelta(days=1)).date()

    try:
        # 基本のフィルタリング
        query = WantedMaterial.query.join(User, WantedMaterial.user_id == User.id).filter(
            WantedMaterial.type == material_type,
            WantedMaterial.matched == False,
            WantedMaterial.deadline >= current_date,
            WantedMaterial.user_id != current_user.id
        )

        # サイズフィルタ（OR条件）
        query = query.filter(
            (WantedMaterial.size_1 >= size_1) |
            (WantedMaterial.size_2 >= size_2) |
            (WantedMaterial.size_3 >= size_3)
        )

        # 市区町村フィルタ（WantedMaterial側）
        if city:
            query = query.filter(WantedMaterial.wm_city.ilike(f"%{city}%"))
        # 都道府県フィルタ（User側）
        if location:
            query = query.filter(User.prefecture == location)
        
        # サブタイプによるフィルタ
        if material_type == "木材" and wood_type:
            query = query.filter(WantedMaterial.wood_type == wood_type)
        elif material_type == "ボード材" and board_material_type:
            query = query.filter(WantedMaterial.board_material_type == board_material_type)
        elif material_type == "パネル材" and panel_type:
            query = query.filter(WantedMaterial.panel_type == panel_type)
        
        # 同一会社の希望材料を除外（business_structureが0または1の場合）
        if current_user.business_structure in [0, 1]:
            query = query.filter(User.company_name != current_user.company_name)

        results = query.all()
        logger.debug(f"希望材料検索結果数: {len(results)}")

        wanted_materials_data = []
        for wanted in results:
            try:
                # owner リレーションシップの利用
                owner = wanted.owner
                logger.debug(f"WantedMaterial id {wanted.id} - owner属性取得成功")
            except Exception as ex:
                logger.error(f"Error accessing 'owner' attribute for WantedMaterial id {wanted.id}: {ex}")
                logger.error(f"Attributes of wanted: {dir(wanted)}")
                # owner が取得できなければこのレコードはスキップ
                continue

            # モデル側の to_dict() で必要なフィールドをまとめる（created_at, quantity も含む）
            data = wanted.to_dict()
            # ユーザー情報を追加（wanted.user ではなく、取得済みの owner を利用）
            data['user'] = {
                'id': owner.id,
                'email': owner.email,
                'company_name': owner.company_name,
                'prefecture': owner.prefecture,
                'city': owner.city,
                'address': owner.address,
                'business_structure': owner.business_structure,
                'industry': owner.industry,
                'job_title': owner.job_title
            }
            wanted_materials_data.append(data)

        log_user_activity(
            current_user.id,
            '希望材料検索',
            'ユーザーが希望材料を検索しました。',
            request.remote_addr,
            request.user_agent.string,
            'N/A'
        )

        return jsonify({
            'success': True,
            'data': {
                'wanted_materials': wanted_materials_data
            }
        }), 200

    except Exception as e:
        current_app.logger.error(f"希望材料検索中にエラーが発生しました: {e}")
        return jsonify({'success': False, 'message': '希望材料検索中にエラーが発生しました。'}), 500


@api_search_bp.route('/materials/latest', methods=['GET'])
@jwt_required()
def latest_materials_api():
    """最新の材料 10 件を取得（GET /api/search/materials/latest）"""
    user_id = get_jwt_identity()
    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({'success': False, 'message': 'ユーザーが見つかりません。'}), 404

    now = datetime.now(JST)
    include_user = request.args.get('include_user') == '1'

    materials = (
        Material.query
        .options(
            joinedload(Material.owner),
            joinedload(Material.group),
        )
        .join(User, Material.user_id == User.id)
        .filter(
            Material.matched.is_(False),
            Material.deleted.is_(False),
            Material.deadline >= now,
            Material.m_prefecture == current_user.prefecture,
            db.or_(
                Material.group_id.is_(None),
                Material.group_id == 0,
                Material.group_id.in_(
                    db.session.query(GroupMembership.group_id)
                              .filter_by(user_id=current_user.id)
                ),
            )
        )
        .order_by(desc(Material.created_at))
        .limit(10)
        .all()
    )

    materials_data = []
    for m in materials:
        d = m.to_dict(include_user=include_user)

        # 表示用補完
        d['title'] = m.title
        d['image_url'] = (
            m.image if m.image and m.image.startswith(("http://", "https://"))
            else build_s3_url(m.image) if m.image
            else build_s3_url('materials/no_image.png')
        )
        d['group_id'] = m.group_id
        d['group_name'] = m.group.name if m.group_id and m.group else None

        # ✅✅✅ 追加：登録ユーザー（owner）の法人コードを返す
        owner = getattr(m, "owner", None)
        company_code = getattr(owner, "company_code", None) if owner else None

        # トップレベルにも付与（Flutter側が拾いやすい）
        d["company_code"] = company_code or ""

        # include_user=1 のとき user dict があればそこにも付与
        if isinstance(d.get("user"), dict):
            d["user"]["company_code"] = company_code or ""

        materials_data.append(d)

    log_user_activity(
        current_user.id,
        '最新材料一覧取得',
        'ユーザーが最新の材料 10 件を取得しました。',
        request.remote_addr,
        request.user_agent.string,
        'N/A'
    )

    return jsonify({'success': True, 'data': {'materials': materials_data}}), 200

@api_search_bp.route('/wanted_materials/latest', methods=['GET'])
@jwt_required()
def latest_wanted_materials_api():
    """
    最新の欲しい材料 10 件を取得（タイプ無関係）
    GET /api/search/wanted_materials/latest
    """
    user_id = get_jwt_identity()
    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({'success': False, 'message': 'ユーザーが見つかりません。'}), 404

    now = datetime.now(JST)
    include_user = request.args.get('include_user') == '1'

    wanted_materials = (
        WantedMaterial.query
        .join(User, WantedMaterial.user_id == User.id)
        .filter(
            WantedMaterial.matched.is_(False),
            WantedMaterial.deleted.is_(False),
            WantedMaterial.user_id != current_user.id,   # 自分が登録したものを除外
            WantedMaterial.deadline >= now               # 締切切れを除外
        )
        .order_by(desc(WantedMaterial.created_at))
        .limit(10)
        .all()
    )

    wanted_materials_data = [w.to_dict(include_user=include_user) for w in wanted_materials]

    log_user_activity(
        current_user.id,
        '最新希望材料一覧取得',
        'ユーザーが最新の希望材料 10 件を取得しました。',
        request.remote_addr,
        request.user_agent.string,
        'N/A'
    )

    return jsonify({'success': True, 'data': {'wanted_materials': wanted_materials_data}}), 200


# ------------------------------------------------------------
# 公開: 最新 10 件取得
# GET /api/search/public/materials/latest
# ------------------------------------------------------------
@api_search_bp.route('/public/materials/latest', methods=['GET'])
def latest_materials_public_api():
    """
    認証不要で最新の材料 10 件を返す公開 API。
    ・自分投稿の除外や会社判定は行わない
    ・締切切れ・削除・マッチ済みは除外
    ・ユーザー情報は ID と会社名のみに制限
    """
    now = datetime.now(JST)

    materials = (
        Material.query
        .join(User, Material.user_id == User.id)
        .filter(
            Material.matched.is_(False),
            Material.deleted.is_(False),
            Material.deadline >= now,
            Material.m_prefecture == User.prefecture
        )
        .order_by(desc(Material.created_at))
        .limit(10)
        .all()
    )

    materials_data = []
    for m in materials:
        image_url = (
            m.image if m.image and m.image.startswith(("http://", "https://"))
            else build_s3_url(m.image) if m.image
            else build_s3_url('materials/no_image.png')
        )

        materials_data.append({
            'id'          : m.id,
            'type'        : m.type,
            'title'       : m.title,
            'size_1'      : m.size_1,
            'size_2'      : m.size_2,
            'size_3'      : m.size_3,
            'quantity'    : m.quantity,
            'm_prefecture': m.m_prefecture,
            'm_city'      : m.m_city,
            'm_address'   : m.m_address,
            'deadline'    : m.deadline.strftime('%Y-%m-%d %H:%M'),
            'image_url'   : image_url,      # ★ URL のみ公開
            'created_at'  : m.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'group_id'    : m.group_id,
            'group_name'  : m.group.name if m.group_id else None,
            'user': {
                'id'          : m.owner.id,
                'company_name': m.owner.company_name,
            }
        })

    return jsonify({'success': True, 'data': {'materials': materials_data}}), 200



@api_search_bp.route('/public/materials', methods=['POST'])
def search_materials_public_api():
    ...
    try:
        validate_material_search_data(data)
    except ValueError as e:
        return jsonify({'success': False, 'message': str(e)}), 400

    material_type        = data.get('material_type', '').strip()
    size_1               = data.get('size_1', 0.0)
    size_2               = data.get('size_2', 0.0)
    size_3               = data.get('size_3', 0.0)
    m_prefecture         = data.get('m_prefecture', '').strip()
    m_city               = data.get('m_city', '').strip()
    wood_type            = data.get('wood_type', '').strip()
    board_material_type  = data.get('board_material_type', '').strip()
    panel_type           = data.get('panel_type', '').strip()
    keyword              = data.get('keyword', '').strip()

    current_date = (datetime.now(JST) - timedelta(days=1)).date()

    try:
        query = (
            Material.query
            .join(User, Material.user_id == User.id)
            .filter(
                Material.matched.is_(False),
                Material.deleted.is_(False),
                Material.deadline >= current_date
            )
        )

        if material_type:
            query = query.filter(Material.type == material_type)

        # サイズ
        query = query.filter(
            Material.size_1 >= size_1,
            Material.size_2 >= size_2,
            Material.size_3 >= size_3
        )

        # 都道府県・市区町村
        if m_prefecture:
            query = query.filter(Material.m_prefecture == m_prefecture)
        if m_city:
            query = query.filter(Material.m_city.ilike(f"%{m_city}%"))

        # サブタイプ
        if material_type == "木材" and wood_type:
            query = query.filter(Material.wood_type == wood_type)
        elif material_type == "ボード材" and board_material_type:
            query = query.filter(Material.board_material_type == board_material_type)
        elif material_type == "パネル材" and panel_type:
            query = query.filter(Material.panel_type == panel_type)

        # キーワード
        if keyword:
            like = f"%{keyword}%"
            query = query.filter(
                or_(
                    Material.title.ilike(like),
                    Material.tags.ilike(like),
                    Material.m_prefecture.ilike(like),
                    Material.m_city.ilike(like),
                    Material.m_address.ilike(like),
                )
            )

        results = query.all()

        # ── シリアライズ ────────────────────
        materials_data = []
        for m in results:
            image_url = (
                m.image if m.image and m.image.startswith(("http://", "https://"))
                else build_s3_url(m.image) if m.image
                else build_s3_url('materials/no_image.png')
            )

            materials_data.append({
                'id'          : m.id,
                'type'        : m.type,
                'size_1'      : m.size_1,
                'size_2'      : m.size_2,
                'size_3'      : m.size_3,
                'm_prefecture': m.m_prefecture,
                'm_city'      : m.m_city,
                'm_address'   : m.m_address,
                'storage_place': m.storage_place,
                'quantity'    : m.quantity,
                'deadline'    : m.deadline.strftime('%Y-%m-%d %H:%M'),
                'image_url'   : image_url,    # ★ URL のみ公開
                'created_at'  : m.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'group_id'    : m.group_id,
                'group_name'  : m.group.name if m.group_id else None,
                'user': {
                    'id'          : m.owner.id,
                    'company_name': m.owner.company_name,
                }
            })

        return jsonify({'success': True, 'data': {'materials': materials_data}}), 200

    except Exception as e:
        logger.error(f"公開材料検索エラー: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': '公開材料検索中にエラーが発生しました。'}), 500

@api_search_bp.route('/materials/explore', methods=['POST'])
@jwt_required(optional=True)  # ✅ 未ログインでもOK
def search_materials_explore_api():
    """
    MainExploreSearchScreen 専用の検索API
    - 未ログイン: public のみ (group_id None or 0)
    - ログイン済み: public + 所属グループ
    - groupIds が指定されたら: そのグループだけに絞る（所属グループ内で）
    """
    try:
        payload = request.get_json(silent=True) or {}

        # -----------------------------
        # 1) JWT があれば user_id を取得
        # -----------------------------
        user_id = get_jwt_identity()

        # -----------------------------
        # 2) 入力値
        # -----------------------------
        keyword_raw = (payload.get("keyword") or "").strip()

        # ✅ keyword に "3km" が混ざっててもOK（あっても動くように）
        distance_km, keyword = _extract_distance_km(keyword_raw)

        # -----------------------------
        # 3) groupIds（Flutterから来るやつ）
        # -----------------------------
        raw_group_ids = payload.get("groupIds") or []
        requested_group_ids = []
        if isinstance(raw_group_ids, list):
            for x in raw_group_ids:
                try:
                    requested_group_ids.append(int(x))
                except Exception:
                    pass

        # -----------------------------
        # 4) ログイン済みなら所属グループIDを取得
        # -----------------------------
        allowed_group_ids = []
        if user_id:
            memberships = (
                GroupMembership.query
                .join(UserGroup, GroupMembership.group_id == UserGroup.id)
                .filter(
                    GroupMembership.user_id == user_id,
                    UserGroup.deleted_at.is_(None),
                )
                .all()
            )
            allowed_group_ids = [
                int(m.group_id) for m in memberships
                if m.group_id is not None
            ]

        current_app.logger.debug(
            f"[search/materials/explore] user_id={user_id}, "
            f"allowed_group_ids={allowed_group_ids}, requested_group_ids={requested_group_ids}"
        )

        # -----------------------------
        # 5) ベース条件（Explore用）
        # -----------------------------
        today = datetime.now(JST).date()

        query = (
            Material.query
            .options(
                joinedload(Material.owner),
                joinedload(Material.group),
            )
            .join(User, Material.user_id == User.id)
            .filter(
                Material.matched.is_(False),
                Material.deleted.is_(False),
                Material.deadline >= today,
            )
        )

        # -----------------------------
        # 6) 表示範囲ルール
        # -----------------------------
        # ✅ 未ログイン：publicのみ
        # ✅ ログイン：public + 所属グループ
        if allowed_group_ids:
            query = query.filter(
                or_(
                    Material.group_id.is_(None),
                    Material.group_id == 0,
                    Material.group_id.in_(allowed_group_ids),
                )
            )
        else:
            query = query.filter(
                or_(
                    Material.group_id.is_(None),
                    Material.group_id == 0,
                )
            )

        # -----------------------------
        # 7) ✅ グループ絞り込み（ここが今回の肝）
        # -----------------------------
        # groupIds が指定されていたら、そのグループだけに絞る
        if requested_group_ids:
            if not allowed_group_ids:
                # 未ログインは groupIds 指定が来ても見せない（安全）
                mats = []
                return jsonify({
                    "success": True,
                    "data": {
                        "distance_km": distance_km,
                        "materials": [],
                    }
                }), 200

            # 所属グループの範囲内だけ許可
            filtered_ids = list(set(requested_group_ids) & set(allowed_group_ids))

            if not filtered_ids:
                # 指定グループが全部NGなら結果0件
                return jsonify({
                    "success": True,
                    "data": {
                        "distance_km": distance_km,
                        "materials": [],
                    }
                }), 200

            # ✅ グループ資材のみ返す（public混ぜない）
            query = query.filter(Material.group_id.in_(filtered_ids))

        # -----------------------------
        # 8) keyword フィルタ
        # -----------------------------
        if keyword:
            like = f"%{keyword}%"
            query = query.filter(
                or_(
                    Material.title.ilike(like),
                    Material.tags.ilike(like),
                    Material.type.ilike(like),
                    Material.m_prefecture.ilike(like),
                    Material.m_city.ilike(like),
                    Material.m_address.ilike(like),
                    Material.wood_type.ilike(like),
                    Material.board_material_type.ilike(like),
                    Material.panel_type.ilike(like),
                    User.company_name.ilike(like),
                )
            )

        # -----------------------------
        # 9) ソート & 取得
        # -----------------------------
        mats = query.order_by(Material.created_at.desc()).all()

        materials_json = [
            material_to_give_json(m, include_user=True)
            for m in mats
        ]

        return jsonify({
            "success": True,
            "data": {
                "distance_km": distance_km,
                "materials": materials_json,
            }
        }), 200

    except SQLAlchemyError as e:
        current_app.logger.error(f"DB error in /api/search/materials/explore: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "message": "Database error occurred."
        }), 500

    except Exception as e:
        current_app.logger.error(f"Error in /api/search/materials/explore: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "message": "Internal server error."
        }), 500
