from flask import Blueprint, request, jsonify, current_app
from flask_login import current_user
from app import db, bcrypt, csrf
from app.models import User, Material, WantedMaterial
from flask_jwt_extended import (
    JWTManager, create_access_token, jwt_required, get_jwt_identity, create_refresh_token
)
from app.blueprints.utils import log_user_activity, send_reset_email, send_welcome_email
from twilio.rest import Client
from datetime import datetime, timedelta
import pytz
import os

api_auth = Blueprint('api_auth', __name__)
jwt = JWTManager()

# JWTの初期化
def init_jwt(app):
    jwt.init_app(app)

# タイムゾーンの設定
JST = pytz.timezone('Asia/Tokyo')

@csrf.exempt
@api_auth.route("/login", methods=['POST'])
def api_login():
    data = request.get_json()
    if not data or not data.get('email') or not data.get('password'):
        return jsonify({"msg": "メールアドレスとパスワードが必要です。"}), 400

    email = data['email']
    password = data['password']

    user = User.query.filter_by(email=email).first()
    if user and bcrypt.check_password_hash(user.password, password):
        access_token = create_access_token(identity=user.id, expires_delta=timedelta(hours=24))
        refresh_token = create_refresh_token(identity=user.id, expires_delta=timedelta(days=30))
        log_user_activity(user.id, 'ログイン', 'ユーザーがAPI経由でログインしました。', request.remote_addr, request.user_agent.string, 'N/A')
        return jsonify({
            "access_token": access_token,
            "refresh_token": refresh_token,
            "msg": "ログイン成功しました。",
            "user": user.to_dict()
        }), 200
    else:
        return jsonify({"msg": "ログインに失敗しました。メールアドレスかパスワードが違います。"}), 401

@api_auth.route("/register", methods=['POST'])
def api_register():
    data = request.get_json()
    required_fields = [
        'email', 'password', 'company_name', 'prefecture', 'city', 'address',
        'company_phone', 'industry', 'job_title', 'contact_name', 'contact_phone',
        'business_structure'
    ]

    if not data:
        return jsonify({"msg": "リクエストデータが必要です。"}), 400

    missing_fields = [field for field in required_fields if field not in data]
    if missing_fields:
        return jsonify({"msg": f"以下のフィールドが不足しています: {', '.join(missing_fields)}"}), 400

    email = data['email']
    password = data['password']
    company_name = data['company_name']
    prefecture = data['prefecture']
    city = data['city']
    address = data['address']
    company_phone = data['company_phone']
    industry = data['industry']
    job_title = data['job_title']
    contact_name = data['contact_name']
    contact_phone = data['contact_phone']

    try:
        # business_structure を int にキャストする
        business_structure = int(data['business_structure'])
    except (ValueError, TypeError):
        return jsonify({"msg": "有効な登録形態を選択してください。"}), 400

    if business_structure not in [0, 1, 2]:
        return jsonify({"msg": "有効な登録形態を選択してください。"}), 400

    # メールアドレスと電話番号の重複チェック
    existing_user_by_email = User.query.filter_by(email=email).first()
    existing_user_by_contact_phone = User.query.filter_by(contact_phone=contact_phone).first()

    if existing_user_by_email:
        return jsonify({"msg": "このメールアドレスは既に使用されています。別のメールアドレスを使用してください。"}), 400

    if existing_user_by_contact_phone:
        return jsonify({"msg": "この電話番号は既に使用されています。別の電話番号を使用してください。"}), 400

    # business_structure に基づいて company_name などを設定
    if business_structure == 0:  # 法人
        industry_value = industry
        job_title_value = job_title
    elif business_structure == 1:  # 個人事業主
        industry_value = industry
        job_title_value = job_title
    elif business_structure == 2:  # 個人
        industry_value = '業種なし'
        job_title_value = '職種なし'

    hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

    if business_structure in [0, 1]:
        user = User(
            email=email, 
            password=hashed_password,
            company_name=company_name,
            prefecture=prefecture,
            city=city,
            address=address,
            company_phone=company_phone,
            industry=industry_value,
            job_title=job_title_value,
            without_approval=data.get('without_approval', False),
            contact_name=contact_name,
            contact_phone=contact_phone,
            business_structure=business_structure
        )
    else:
        # 個人の場合は別の処理（例: 電話番号を company_phone として設定）
        user = User(
            email=email, 
            password=hashed_password,
            company_name=company_name,
            prefecture=prefecture,
            city=city,
            address=address,
            company_phone=contact_phone,
            industry=industry_value,
            job_title=job_title_value,
            without_approval=data.get('without_approval', False),
            contact_name=contact_name,
            contact_phone=contact_phone,
            business_structure=business_structure
        )

    db.session.add(user)
    try:
        db.session.commit()
        log_user_activity(user.id, 'ユーザー登録', 'ユーザーがAPI経由で新規登録しました。', request.remote_addr, request.user_agent.string, 'N/A')
    except Exception as e:
        db.session.rollback()
        return jsonify({"msg": "ユーザー登録中にエラーが発生しました。もう一度やり直してください。"}), 500

    if not send_welcome_email(user.email):
        db.session.delete(user)
        db.session.commit()
        return jsonify({"msg": "ウェルカムメールの送信に失敗しました。ユーザー登録が取り消されました。"}), 500

    return jsonify({"msg": "ユーザー登録が完了しました！"}), 201

@csrf.exempt
@api_auth.route("/refresh", methods=['POST'])
@jwt_required(refresh=True)
def refresh_token():
    current_user_id = get_jwt_identity()
    access_token = create_access_token(identity=current_user_id, expires_delta=timedelta(hours=24))
    return jsonify({"access_token": access_token}), 200

@csrf.exempt
@api_auth.route("/reset_password", methods=['POST'])
def api_reset_request():
    data  = request.get_json() or {}
    email = data.get('email')

    if not email:
        return jsonify({"msg": "メールアドレスが必要です。"}), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"msg": "該当アカウントがありません。"}), 404

    # ★ HTTPS 未整備につき “for_mobile=False” 固定
    if send_reset_email(user, for_mobile=False):
        log_user_activity(
            user.id,
            'API パスワードリセット',
            'モバイルアプリ経由リセットリクエスト',
            request.remote_addr,
            request.user_agent.string,
            'N/A'
        )
        return jsonify({"msg": "リセットメールを送信しました。"}), 200

    return jsonify({"msg": "メール送信に失敗しました。"}), 500

@csrf.exempt
@api_auth.route("/reset_password/<token>", methods=['POST'])
def api_reset_token(token):
    data = request.get_json()
    if not data or not data.get('password'):
        return jsonify({"msg": "新しいパスワードが必要です。"}), 400

    new_password = data['password']
    user = User.verify_reset_token(token)
    if not user:
        return jsonify({"msg": "トークンが無効です。"}), 400

    hashed_password = bcrypt.generate_password_hash(new_password).decode('utf-8')
    user.password = hashed_password
    db.session.commit()
    log_user_activity(user.id, 'パスワードリセット', 'パスワードがAPI経由でリセットされました。', request.remote_addr, request.user_agent.string, 'N/A')
    return jsonify({"msg": "パスワードが更新されました！"}), 200

@csrf.exempt
@api_auth.route("/logout", methods=['POST'])
@jwt_required()
def api_logout():
    current_user_id = get_jwt_identity()
    log_user_activity(current_user_id, 'ログアウト', 'ユーザーがAPI経由でログアウトしました。', request.remote_addr, request.user_agent.string, 'N/A')
    return jsonify({"msg": "ログアウトしました。"}), 200

def send_reset_sms(user):
    account_sid = os.getenv('TWILIO_ACCOUNT_SID')
    auth_token = os.getenv('TWILIO_AUTH_TOKEN')
    client = Client(account_sid, auth_token)

    token = user.get_reset_token()
    reset_url = f"{request.host_url}api_auth/reset_password/{token}"

    message_body = f"こんにちは、{user.contact_name}様。パスワードリセットのリクエストがありました。\n以下のリンクをクリックしてパスワードをリセットしてください: {reset_url}"

    try:
        message = client.messages.create(
            body=message_body,
            from_=os.getenv('TWILIO_PHONE_NUMBER'),
            to=user.contact_phone
        )
        return True
    except Exception as e:
        current_app.logger.error(f"SMS送信に失敗しました: {e}")
        return False

# ------------------------------------------------------------
# デバイストークン登録
# POST /api/auth/device_token/register
# Expect: { "device_token": "<FCM トークン文字列>" }
# ------------------------------------------------------------
@csrf.exempt
@api_auth.route('/device_token/register', methods=['POST'])
@jwt_required()                          # ← アクセストークン必須
def register_device_token():
    data = request.get_json() or {}
    fcm_token = data.get('device_token')
    current_app.logger.info(f"★Device token received: {fcm_token}")

    if not fcm_token:
        return jsonify({'msg': 'FCMトークンが必要です。'}), 400

    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if user is None:
        return jsonify({'msg': 'ユーザーが見つかりません。'}), 404

    # device_tokens カラム（Array ⸺ JSON/Text 等）の存在を想定
    if user.device_tokens is None:
        user.device_tokens = []

    if fcm_token not in user.device_tokens:
        user.device_tokens.append(fcm_token)
        db.session.commit()

    return jsonify({'msg': 'FCMトークンを登録しました。'}), 200

@csrf.exempt
@api_auth.route("/my_match_count", methods=['GET'])
@jwt_required()
def my_match_count():
    """
    ログインユーザーの
    - 提供材料(Material)で matched=True の数
    - 希望材料(WantedMaterial)で matched=True の数
    を合算して返す
    """
    current_user_id = get_jwt_identity()
    user = User.query.get_or_404(current_user_id)

    matched_materials_count = Material.query.filter_by(
        user_id=user.id, matched=True
    ).count()

    matched_wanted_materials_count = WantedMaterial.query.filter_by(
        user_id=user.id, matched=True
    ).count()

    total_matched_count = matched_materials_count + matched_wanted_materials_count

    return jsonify({
        'status': 'success',
        'total_matched_count': total_matched_count
    }), 200

@csrf.exempt
@api_auth.route("/delete_account", methods=['DELETE'])
@jwt_required()
def api_delete_account():
    """
    現在ログイン中（トークン所有）のユーザーアカウントを削除するAPI
    """
    current_user_id = get_jwt_identity()
    user = User.query.get(current_user_id)

    if not user:
        return jsonify({"msg": "アカウントが見つかりません。"}), 404

    try:
        db.session.delete(user)
        db.session.commit()
        current_app.logger.info(f"User {user.email} (ID: {user.id}) was deleted via API.")
        return jsonify({"msg": "アカウントを削除しました。"}), 200
    except Exception as e:
        current_app.logger.error(f"アカウント削除エラー: {str(e)}")
        db.session.rollback()
        return jsonify({"msg": "アカウントの削除に失敗しました。"}), 500
