# app/api/api_profile.py

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models import User
from app.blueprints.utils import log_user_activity
from flask_login import login_user

api_profile_bp = Blueprint('api_profile', __name__, url_prefix='/api/profile')

def get_current_user():
    """JWTからユーザーIDを取得し、DBからユーザー情報をロードする"""
    user_id = get_jwt_identity()
    return User.query.get(user_id)

@api_profile_bp.route("/<int:user_id>", methods=['GET'])
@jwt_required()
def user_profile(user_id):
    """
    指定されたユーザーIDのプロフィール情報を JSON で返す。
    ログにも表示します。
    """
    current_user_obj = get_current_user()
    user = User.query.get_or_404(user_id)
    log_user_activity(
        current_user_obj.id,
        'ユーザープロフィール表示',
        f'ユーザーがユーザーID: {user_id} のプロフィールを表示しました。',
        request.remote_addr,
        request.user_agent.string,
        'N/A'
    )
    profile_data = {
        'id': user.id,
        'company_name': user.company_name,
        'prefecture': user.prefecture,
        'city': user.city,
        'address': user.address,
        'without_approval': user.without_approval,
        'contact_name': user.contact_name,
        'contact_phone': user.contact_phone,
        'line_id': user.line_id,
        'business_structure': user.business_structure,
        'company_phone': user.company_phone if user.business_structure != 2 else None,
        'industry': user.industry if user.business_structure != 2 else None,
        'job_title': user.job_title if user.business_structure != 2 else None
    }
    return jsonify({'status': 'success', 'profile': profile_data}), 200

@api_profile_bp.route("", methods=['GET'])
@jwt_required()
def view_profile():
    """
    現在ログイン中のユーザーのプロフィール情報を JSON で返す。
    """
    current_user_obj = get_current_user()
    profile_data = {
        'id': current_user_obj.id,
        'company_name': current_user_obj.company_name,
        'prefecture': current_user_obj.prefecture,
        'city': current_user_obj.city,
        'address': current_user_obj.address,
        'without_approval': current_user_obj.without_approval,
        'contact_name': current_user_obj.contact_name,
        'contact_phone': current_user_obj.contact_phone,
        'line_id': current_user_obj.line_id,
        'business_structure': current_user_obj.business_structure,
        'company_phone': current_user_obj.company_phone if current_user_obj.business_structure != 2 else None,
        'industry': current_user_obj.industry if current_user_obj.business_structure != 2 else None,
        'job_title': current_user_obj.job_title if current_user_obj.business_structure != 2 else None
    }
    return jsonify({'status': 'success', 'profile': profile_data}), 200

@api_profile_bp.route("/edit_profile", methods=['POST'])
@jwt_required()
def edit_profile():
    """
    現在ログイン中のユーザーのプロフィール情報を更新する API エンドポイント。
    リクエストボディは JSON 形式で、更新したいフィールドを含むものとします。
    """
    current_user_obj = get_current_user()
    data = request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': '更新するデータがありません。'}), 400

    try:
        current_app.logger.debug(f"Edit profile request data: {data}")
        current_user_obj.company_name = data.get('company_name', current_user_obj.company_name)
        current_user_obj.prefecture = data.get('prefecture', current_user_obj.prefecture)
        current_user_obj.city = data.get('city', current_user_obj.city)
        current_user_obj.address = data.get('address', current_user_obj.address)
        current_user_obj.without_approval = data.get('without_approval', current_user_obj.without_approval)
        current_user_obj.contact_name = data.get('contact_name', current_user_obj.contact_name)
        current_user_obj.contact_phone = data.get('contact_phone', current_user_obj.contact_phone)
        # 空文字は None として扱う
        current_user_obj.line_id = data.get('line_id') if data.get('line_id') else None

        # 個人以外の場合のみ追加フィールドを更新
        if current_user_obj.business_structure != 2:
            current_user_obj.company_phone = data.get('company_phone', current_user_obj.company_phone)
            current_user_obj.industry = data.get('industry', current_user_obj.industry)
            current_user_obj.job_title = data.get('job_title', current_user_obj.job_title)

        db.session.commit()
        db.session.refresh(current_user_obj)
        # セッションの再読み込み
        login_user(current_user_obj, force=True)
        return jsonify({'status': 'success', 'message': 'プロフィールが更新されました！'}), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating profile: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': 'プロフィールの更新に失敗しました。'}), 500
