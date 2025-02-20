# app/api/api_profile.py

from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from app import db
from app.models import User
from app.forms import EditProfileForm  # フォームがAPIで使用される場合はフォームバリデーションを再検討
from app.blueprints.utils import log_user_activity
from werkzeug.exceptions import BadRequest

api_profile_bp = Blueprint('api_profile', __name__, url_prefix='/api/profile')

def validate_edit_profile_data(data):
    """
    JSONデータのバリデーションを行います。
    必要なフィールドが存在し、適切な型であることを確認します。
    """
    required_fields = ['company_name', 'prefecture', 'city', 'address',
                       'without_approval', 'contact_name', 'contact_phone']
    
    # 個人以外のユーザーの場合に必要な追加フィールド
    additional_fields = ['company_phone', 'industry', 'job_title']
    
    for field in required_fields:
        if field not in data:
            raise BadRequest(f"{field} が必要です。")
    
    # business_structure による追加フィールドのチェック
    if current_user.business_structure != 2:
        for field in additional_fields:
            if field not in data:
                raise BadRequest(f"{field} が必要です。")

    # 他のバリデーション（例: 電話番号の形式など）をここに追加可能

@api_profile_bp.route('/<int:user_id>', methods=['GET'])
@login_required
def get_user_profile(user_id):
    """
    指定されたユーザーのプロフィールを取得します。
    """
    user = User.query.get_or_404(user_id)
    
    # アクティビティログの記録
    log_user_activity(
        current_user.id,
        'ユーザープロフィール取得',
        f'ユーザーがユーザーID: {user_id} のプロフィールを取得しました。',
        request.remote_addr,
        request.user_agent.string,
        'N/A'
    )
    
    user_data = {
        'id': user.id,
        'email': user.email,
        'company_name': user.company_name,
        'prefecture': user.prefecture,
        'city': user.city,
        'address': user.address,
        'without_approval': user.without_approval,
        'contact_name': user.contact_name,
        'contact_phone': user.contact_phone,
        'line_id': user.line_id,
        'business_structure': user.business_structure
    }
    
    # 個人以外のユーザーの場合のみ追加フィールドを含める
    if user.business_structure != 2:
        user_data.update({
            'company_phone': user.company_phone,
            'industry': user.industry,
            'job_title': user.job_title
        })
    
    return jsonify({
        'success': True,
        'data': {
            'user': user_data
        }
    }), 200

@api_profile_bp.route('/', methods=['GET'])
@login_required
def get_current_user_profile():
    """
    現在のユーザーのプロフィールを取得します。
    """
    user = current_user
    
    user_data = {
        'id': user.id,
        'email': user.email,
        'company_name': user.company_name,
        'prefecture': user.prefecture,
        'city': user.city,
        'address': user.address,
        'without_approval': user.without_approval,
        'contact_name': user.contact_name,
        'contact_phone': user.contact_phone,
        'line_id': user.line_id,
        'business_structure': user.business_structure
    }
    
    # 個人以外のユーザーの場合のみ追加フィールドを含める
    if user.business_structure != 2:
        user_data.update({
            'company_phone': user.company_phone,
            'industry': user.industry,
            'job_title': user.job_title
        })
    
    return jsonify({
        'success': True,
        'data': {
            'user': user_data
        }
    }), 200

@api_profile_bp.route('/edit', methods=['PUT'])
@login_required
def edit_profile_api():
    """
    現在のユーザーのプロフィールを編集します。
    """
    if not request.is_json:
        return jsonify({'success': False, 'message': 'JSON形式のデータを送信してください。'}), 400
    
    data = request.get_json()
    
    try:
        validate_edit_profile_data(data)
    except BadRequest as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    
    try:
        # フィールドの更新
        current_user.company_name = data['company_name']
        current_user.prefecture = data['prefecture']
        current_user.city = data['city']
        current_user.address = data['address']
        current_user.without_approval = data['without_approval']
        current_user.contact_name = data['contact_name']
        current_user.contact_phone = data['contact_phone']
        current_user.line_id = data.get('line_id')  # オプショナル
        
        # 個人以外の場合のみ追加フィールドを更新
        if current_user.business_structure != 2:
            current_user.company_phone = data['company_phone']
            current_user.industry = data['industry']
            current_user.job_title = data['job_title']
        
        db.session.commit()
        
        # セッションの再読み込み
        db.session.refresh(current_user)
        
        # アクティビティログの記録
        log_user_activity(
            current_user.id,
            'プロフィール編集',
            'ユーザーがプロフィールを編集しました。',
            request.remote_addr,
            request.user_agent.string,
            'N/A'
        )
        
        return jsonify({
            'success': True,
            'message': 'プロフィールが更新されました。',
            'data': {
                'user': {
                    'id': current_user.id,
                    'email': current_user.email,
                    'company_name': current_user.company_name,
                    'prefecture': current_user.prefecture,
                    'city': current_user.city,
                    'address': current_user.address,
                    'without_approval': current_user.without_approval,
                    'contact_name': current_user.contact_name,
                    'contact_phone': current_user.contact_phone,
                    'line_id': current_user.line_id,
                    'business_structure': current_user.business_structure
                }
            }
        }), 200
    except Exception as e:
        current_app.logger.error(f"プロフィール更新中にエラーが発生しました: {e}")
        return jsonify({'success': False, 'message': 'プロフィールの更新中にエラーが発生しました。'}), 500
