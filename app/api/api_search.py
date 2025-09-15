# app/api/api_search.py

import traceback
from flask import Blueprint, request, jsonify, current_app, url_for
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import Material, WantedMaterial, User, GroupMembership, UserGroup
from app.blueprints.utils import log_user_activity
from datetime import datetime, timedelta
from sqlalchemy import desc, or_
import pytz
import logging
from app.utils.s3_uploader import build_s3_url
from app import db

api_search_bp = Blueprint('api_search', __name__, url_prefix='/api/search')
JST = pytz.timezone('Asia/Tokyo')
now = datetime.now(JST)

logger = logging.getLogger(__name__)

def validate_material_search_data(data):
    """
    材料検索の入力データをバリデーションします。
    必須項目: material_type
    Optional: size_1, size_2, size_3, m_prefecture, m_city, wood_type, board_material_type, panel_type
    """
    required_fields = ['material_type']
    for field in required_fields:
        if field not in data:
            raise ValueError(f"{field} が必要です。")

    # 数値型のチェック（空文字は 0.0 とみなす）
    for size_field in ['size_1', 'size_2', 'size_3']:
        if size_field in data:
            try:
                value = data[size_field]
                # 空文字またはNoneなら 0.0 として扱う
                if value == "" or value is None:
                    data[size_field] = 0.0
                else:
                    data[size_field] = float(value)
            except ValueError:
                raise ValueError(f"{size_field} は数値でなければなりません。")

    # 文字列型のチェック
    for field in ['m_prefecture', 'm_city', 'wood_type', 'board_material_type', 'panel_type']:
        if field in data and not isinstance(data[field], str):
            raise ValueError(f"{field} は文字列でなければなりません。")

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

@api_search_bp.route('/materials', methods=['POST'])
@jwt_required()
def search_materials_api():
    """材料を検索する API（POST /api/search/materials）"""
    user_id = get_jwt_identity()
    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({'success': False, 'message': 'ユーザーが見つかりません。'}), 404

    if not request.is_json:
        return jsonify({'success': False, 'message': 'JSON形式のデータを送信してください。'}), 400

    data = request.get_json()

    # ---- バリデーション -------------------------------------------------
    try:
        validate_material_search_data(data)
    except ValueError as e:
        return jsonify({'success': False, 'message': str(e)}), 400

    # ---- 検索パラメータ -------------------------------------------------
    material_type        = data.get('material_type')
    size_1               = data.get('size_1', 0.0)
    size_2               = data.get('size_2', 0.0)
    size_3               = data.get('size_3', 0.0)
    m_prefecture         = data.get('m_prefecture', '').strip()
    m_city               = data.get('m_city', '').strip()
    wood_type            = data.get('wood_type', '').strip()
    board_material_type  = data.get('board_material_type', '').strip()
    panel_type           = data.get('panel_type', '').strip()

    current_date = (datetime.now(JST) - timedelta(days=1)).date()

    try:
        # ---- ベースクエリ ------------------------------------------------
        query = (
            Material.query
            .join(User, Material.user_id == User.id)
            .filter(
                Material.type == material_type,
                Material.matched.is_(False),
                Material.deadline >= current_date,
                Material.user_id != current_user.id        # 自分以外
            )
        )

        # ── グループ制御 ─────────────────────────────────────────────
        from app.models import GroupMembership          # ★追加
        my_group_ids = [
            m.group_id for m in GroupMembership.query
                                   .filter_by(user_id=current_user.id)
                                   .all()
        ]
        if my_group_ids:      # 所属グループがある
            query = query.filter(
                db.or_(Material.group_id.is_(None),
                       Material.group_id == 0,
                       Material.group_id.in_(my_group_ids))
            )
        else:                 # ない場合 → group_id>0 を除外
            query = query.filter(
                db.or_(Material.group_id.is_(None),
                       Material.group_id == 0)
            )

        # ---- サイズ ------------------------------------------------------
        query = query.filter(
            Material.size_1 >= size_1,
            Material.size_2 >= size_2,
            Material.size_3 >= size_3
        )

        # ---- 住所 --------------------------------------------------------
        if m_prefecture:
            query = query.filter(Material.m_prefecture == m_prefecture)
        if m_city:
            query = query.filter(Material.m_city.ilike(f"%{m_city}%"))

        # ---- サブタイプ ---------------------------------------------------
        if material_type == "木材" and wood_type:
            query = query.filter(Material.wood_type == wood_type)
        elif material_type == "ボード材" and board_material_type:
            query = query.filter(Material.board_material_type == board_material_type)
        elif material_type == "パネル材" and panel_type:
            query = query.filter(Material.panel_type == panel_type)

        # ---- 同一会社除外 -------------------------------------------------
        if current_user.business_structure in [0, 1]:
            query = query.filter(User.company_name != current_user.company_name)

        # ---- グループ制御  ---------------------------------------------- ★
        my_group_ids = [
            m.group_id for m in GroupMembership.query
                                   .filter_by(user_id=current_user.id)
                                   .all()
        ]
        current_app.logger.debug(f"ユーザー所属グループ: {my_group_ids}")

        if my_group_ids:      # 所属グループあり
            query = query.filter(or_(Material.group_id.is_(None),
                                     Material.group_id == 0,
                                     Material.group_id.in_(my_group_ids)))
        else:                 # 所属なし → group_id>0 を除外
            query = query.filter(or_(Material.group_id.is_(None),
                                     Material.group_id == 0))

        current_app.logger.debug("Final query: %s",
            query.statement.compile(compile_kwargs={'literal_binds': True})
        )

        results = query.all()
        current_app.logger.debug(f"Query returned {len(results)} results")

        # ---- シリアライズ -------------------------------------------------
        materials_data = []
        for material in results:
            image_url = (
                material.image if material.image.startswith(("http://", "https://"))
                else build_s3_url(material.image)           # キー → URL
                if material.image
                else build_s3_url('materials/no_image.png') # 画像無し
            )

            materials_data.append({
                'id'         : material.id,
                'type'       : material.type,
                'size_1'     : material.size_1,
                'size_2'     : material.size_2,
                'size_3'     : material.size_3,
                'm_prefecture': material.m_prefecture,
                'm_city'     : material.m_city,
                'm_address'  : material.m_address,
                'quantity'   : material.quantity,
                'image_url'  : image_url,                   # ★ ここだけあればOK
                'deadline'   : material.deadline.strftime('%Y-%m-%d %H:%M'),
                'wood_type'  : material.wood_type,
                'board_material_type': material.board_material_type,
                'panel_type' : material.panel_type,
                'created_at' : material.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'exclude_weekends': material.exclude_weekends,
                # ---★ グループ情報を追加 -----------------------------
                'group_id'   : material.group_id,
                'group_name' : (
                    material.group.name if material.group_id else None
                ),
                'user'       : {
                    'id'               : material.owner.id,
                    'email'            : material.owner.email,
                    'company_name'     : material.owner.company_name,
                    'prefecture'       : material.owner.prefecture,
                    'city'             : material.owner.city,
                    'address'          : material.owner.address,
                    'business_structure': material.owner.business_structure,
                    'industry'         : material.owner.industry,
                    'job_title'        : material.owner.job_title
                }
            })

        # ---- アクティビティログ ------------------------------------------
        log_user_activity(
            current_user.id,
            '材料検索',
            'ユーザーが材料を検索しました。',
            request.remote_addr,
            request.user_agent.string,
            'N/A'
        )

        return jsonify({'success': True, 'data': {'materials': materials_data}}), 200

    except Exception as e:
        current_app.logger.error(f"材料検索中にエラーが発生しました: {e}")
        current_app.logger.debug(traceback.format_exc())
        return jsonify({'success': False, 'message': '材料検索中にエラーが発生しました。'}), 500

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
        .join(User, Material.user_id == User.id)
        .filter(
            Material.matched.is_(False),
            Material.deleted.is_(False),
            Material.user_id != current_user.id,
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
        d['image_url'] = (
            m.image if m.image.startswith(("http://", "https://"))
            else build_s3_url(m.image) if m.image else build_s3_url('materials/no_image.png')
        )
        d['group_id']   = m.group_id
        d['group_name'] = m.group.name if m.group_id else None
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


# ------------------------------------------------------------
# 公開: 条件検索
# POST /api/search/public/materials
# ------------------------------------------------------------
@api_search_bp.route('/public/materials', methods=['POST'])
def search_materials_public_api():
    """
    認証不要で材料を検索する公開 API。
    ・締切切れ／マッチ済み／削除済みは除外
    ・自分投稿や同一会社除外など会員専用のフィルタは行わない
    ・ユーザー情報は ID と company_name のみ公開
    Body JSON 仕様は /materials と同一
    """
    if not request.is_json:
        return jsonify({'success': False, 'message': 'JSON形式のデータを送信してください。'}), 400

    data = request.get_json()

    try:
        validate_material_search_data(data)
    except ValueError as e:
        return jsonify({'success': False, 'message': str(e)}), 400

    # ── パラメータ抽出 ───────────────────────
    material_type        = data.get('material_type')
    size_1               = data.get('size_1', 0.0)
    size_2               = data.get('size_2', 0.0)
    size_3               = data.get('size_3', 0.0)
    m_prefecture         = data.get('m_prefecture', '').strip()
    m_city               = data.get('m_city', '').strip()
    wood_type            = data.get('wood_type', '').strip()
    board_material_type  = data.get('board_material_type', '').strip()
    panel_type           = data.get('panel_type', '').strip()

    current_date = (datetime.now(JST) - timedelta(days=1)).date()

    try:
        # ── 基本フィルタ ───────────────────
        query = (
            Material.query
            .join(User, Material.user_id == User.id)
            .filter(
                Material.type == material_type,
                Material.matched.is_(False),
                Material.deleted.is_(False),
                Material.deadline >= current_date
            )
        )

        # ── サイズ（AND 条件）────────────────
        query = query.filter(
            Material.size_1 >= size_1,
            Material.size_2 >= size_2,
            Material.size_3 >= size_3
        )

        # ── 都道府県・市区町村 ────────────────
        if m_prefecture:
            query = query.filter(Material.m_prefecture == m_prefecture)
        if m_city:
            query = query.filter(Material.m_city.ilike(f"%{m_city}%"))

        # ── サブタイプ（木材／ボード材／パネル材） ─
        if material_type == "木材" and wood_type:
            query = query.filter(Material.wood_type == wood_type)
        elif material_type == "ボード材" and board_material_type:
            query = query.filter(Material.board_material_type == board_material_type)
        elif material_type == "パネル材" and panel_type:
            query = query.filter(Material.panel_type == panel_type)

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
