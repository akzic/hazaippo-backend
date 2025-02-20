# app/api/api_utils.py

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from app import db
from app.models import Log
from sqlalchemy.exc import SQLAlchemyError
import logging

api_utils_bp = Blueprint('api_utils', __name__, url_prefix='/api/utils')

# ロガーの設定
logger = logging.getLogger(__name__)


@api_utils_bp.route('/log_activity', methods=['POST'])
@login_required
def log_activity():
    """
    ユーザーの活動をログとして記録します。
    リクエストボディ例:
    {
        "action": "update_profile",
        "details": "ユーザープロファイルを更新しました。",
        "ip_address": "192.168.1.1",
        "device_info": "Chrome on Windows 10",
        "location": "Tokyo"
    }
    """
    data = request.get_json()

    action = data.get('action')
    details = data.get('details')
    ip_address = data.get('ip_address')
    device_info = data.get('device_info')
    location = data.get('location', 'N/A')  # デフォルト値

    if not action or not details or not ip_address or not device_info:
        return jsonify({'status': 'error', 'message': '必要なフィールドが不足しています。'}), 400

    try:
        log_entry = Log(
            user_id=current_user.id,
            action=action,
            details=details,
            ip_address=ip_address,
            device_info=device_info,
            location=location
        )
        db.session.add(log_entry)
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'ユーザー活動が正常にログされました。'}), 201
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"ユーザー活動のログ記録中にエラーが発生しました: {e}")
        return jsonify({'status': 'error', 'message': 'ログの記録中にエラーが発生しました。'}), 500
