# app/api/api_email_notifications.py

from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required
from app import db, mail
from app.models import Log  # 必要に応じて他のモデルをインポート
from flask_mail import Message
import os
import logging

# Blueprintの定義
api_email_notifications_bp = Blueprint('api_email_notifications', __name__, url_prefix='/api/email_notifications')

# ロガーの設定
logger = logging.getLogger(__name__)

# 既存のemail_notifications.pyの機能をインポート
from app.blueprints.email_notifications import (
    send_email_safe,
    send_welcome_email,
    send_material_registration_email,
    send_wanted_material_registration_email,
    send_request_email,
    send_new_request_received_email,
    send_accept_request_email,
    send_accept_request_to_sender_email,
    send_reject_request_email,
    send_reject_request_to_sender_email,
    send_reservation_confirmation_email,
    send_lecture_confirmation_email,
    send_cancel_reservation_email,
    send_new_message_email
)

# 各エンドポイントの実装

@api_email_notifications_bp.route('/send_welcome_email', methods=['POST'])
@login_required
def api_send_welcome_email():
    """
    ユーザーにウェルカムメールを送信します。
    リクエストボディ例:
    {
        "user_email": "user@example.com"
    }
    """
    data = request.get_json()
    user_email = data.get('user_email')

    if not user_email:
        return jsonify({'status': 'error', 'message': 'ユーザーのメールアドレスが指定されていません。'}), 400

    try:
        success = send_welcome_email(user_email)
        if success:
            return jsonify({'status': 'success', 'message': 'ウェルカムメールが送信されました。'}), 200
        else:
            return jsonify({'status': 'error', 'message': 'ウェルカムメールの送信に失敗しました。'}), 500
    except Exception as e:
        logger.error(f"ウェルカムメール送信中にエラーが発生しました: {e}")
        return jsonify({'status': 'error', 'message': 'ウェルカムメールの送信中にエラーが発生しました。'}), 500


@api_email_notifications_bp.route('/send_material_registration_email', methods=['POST'])
@login_required
def api_send_material_registration_email():
    """
    ユーザーに端材登録メールを送信します。
    リクエストボディ例:
    {
        "user_email": "user@example.com",
        "material": {
            "type": "金属",
            "size_1": "5.0",
            "size_2": "4.5",
            "size_3": "3.0",
            "location": "倉庫A",
            "quantity": "10",
            "note": "新しい備考"
        }
    }
    """
    data = request.get_json()
    user_email = data.get('user_email')
    material = data.get('material')

    if not user_email or not material:
        return jsonify({'status': 'error', 'message': '必要なフィールドが不足しています。'}), 400

    try:
        success = send_material_registration_email(user_email, material)
        if success:
            return jsonify({'status': 'success', 'message': '端材登録メールが送信されました。'}), 200
        else:
            return jsonify({'status': 'error', 'message': '端材登録メールの送信に失敗しました。'}), 500
    except Exception as e:
        logger.error(f"端材登録メール送信中にエラーが発生しました: {e}")
        return jsonify({'status': 'error', 'message': '端材登録メールの送信中にエラーが発生しました。'}), 500


@api_email_notifications_bp.route('/send_wanted_material_registration_email', methods=['POST'])
@login_required
def api_send_wanted_material_registration_email():
    """
    ユーザーに欲しい端材登録メールを送信します。
    リクエストボディ例:
    {
        "user_email": "user@example.com",
        "wanted_material": {
            "type": "プラスチック",
            "size_1": "2.0",
            "size_2": "3.5",
            "size_3": "1.5",
            "location": "倉庫B",
            "quantity": "5",
            "note": "必要な備考"
        }
    }
    """
    data = request.get_json()
    user_email = data.get('user_email')
    wanted_material = data.get('wanted_material')

    if not user_email or not wanted_material:
        return jsonify({'status': 'error', 'message': '必要なフィールドが不足しています。'}), 400

    try:
        success = send_wanted_material_registration_email(user_email, wanted_material)
        if success:
            return jsonify({'status': 'success', 'message': '欲しい端材登録メールが送信されました。'}), 200
        else:
            return jsonify({'status': 'error', 'message': '欲しい端材登録メールの送信に失敗しました。'}), 500
    except Exception as e:
        logger.error(f"欲しい端材登録メール送信中にエラーが発生しました: {e}")
        return jsonify({'status': 'error', 'message': '欲しい端材登録メールの送信中にエラーが発生しました。'}), 500


@api_email_notifications_bp.route('/send_request_email', methods=['POST'])
@login_required
def api_send_request_email():
    """
    ユーザーにリクエストメールを送信します。
    リクエストボディ例:
    {
        "user_email": "user@example.com"
    }
    """
    data = request.get_json()
    user_email = data.get('user_email')

    if not user_email:
        return jsonify({'status': 'error', 'message': 'ユーザーのメールアドレスが指定されていません。'}), 400

    try:
        success = send_request_email(user_email)
        if success:
            return jsonify({'status': 'success', 'message': 'リクエストメールが送信されました。'}), 200
        else:
            return jsonify({'status': 'error', 'message': 'リクエストメールの送信に失敗しました。'}), 500
    except Exception as e:
        logger.error(f"リクエストメール送信中にエラーが発生しました: {e}")
        return jsonify({'status': 'error', 'message': 'リクエストメールの送信中にエラーが発生しました。'}), 500


@api_email_notifications_bp.route('/send_new_request_received_email', methods=['POST'])
@login_required
def api_send_new_request_received_email():
    """
    レクチャー担当者に新規リクエスト受信メールを送信します。
    リクエストボディ例:
    {
        "user_email": "lecturer@example.com"
    }
    """
    data = request.get_json()
    user_email = data.get('user_email')

    if not user_email:
        return jsonify({'status': 'error', 'message': 'レクチャー担当者のメールアドレスが指定されていません。'}), 400

    try:
        success = send_new_request_received_email(user_email)
        if success:
            return jsonify({'status': 'success', 'message': '新規リクエスト受信メールが送信されました。'}), 200
        else:
            return jsonify({'status': 'error', 'message': '新規リクエスト受信メールの送信に失敗しました。'}), 500
    except Exception as e:
        logger.error(f"新規リクエスト受信メール送信中にエラーが発生しました: {e}")
        return jsonify({'status': 'error', 'message': '新規リクエスト受信メールの送信中にエラーが発生しました。'}), 500


@api_email_notifications_bp.route('/send_accept_request_email', methods=['POST'])
@login_required
def api_send_accept_request_email():
    """
    リクエスト承認者に承認メールを送信します。
    リクエストボディ例:
    {
        "requester": {
            "company_name": "株式会社ABC",
            "email": "requester@example.com",
            "contact_name": "田中 太郎",
            "prefecture": "東京都",
            "city": "新宿区",
            "address": "西新宿2-8-1",
            "industry": "IT",
            "job_title": "マネージャー",
            "contact_phone": "03-1234-5678"
        },
        "material": {
            "type": "金属",
            "size_1": "5.0",
            "size_2": "4.5",
            "size_3": "3.0",
            "location": "倉庫A",
            "quantity": "10",
            "note": "新しい備考"
        },
        "accepted_user": {
            "company_name": "株式会社XYZ",
            "email": "accepted_user@example.com",
            "contact_name": "佐藤 花子",
            "prefecture": "大阪府",
            "city": "大阪市",
            "address": "梅田1-1-1",
            "industry": "製造",
            "job_title": "主任",
            "contact_phone": "06-8765-4321"
        }
    }
    """
    data = request.get_json()
    requester = data.get('requester')
    material = data.get('material')
    accepted_user = data.get('accepted_user')

    if not requester or not material or not accepted_user:
        return jsonify({'status': 'error', 'message': '必要なフィールドが不足しています。'}), 400

    try:
        success = send_accept_request_email(requester, material, accepted_user)
        if success:
            return jsonify({'status': 'success', 'message': 'リクエスト承認メールが送信されました。'}), 200
        else:
            return jsonify({'status': 'error', 'message': 'リクエスト承認メールの送信に失敗しました。'}), 500
    except Exception as e:
        logger.error(f"リクエスト承認メール送信中にエラーが発生しました: {e}")
        return jsonify({'status': 'error', 'message': 'リクエスト承認メールの送信中にエラーが発生しました。'}), 500


@api_email_notifications_bp.route('/send_accept_request_to_sender_email', methods=['POST'])
@login_required
def api_send_accept_request_to_sender_email():
    """
    リクエスト送信者に承認メールを送信します。
    リクエストボディ例:
    {
        "requester_email": "requester@example.com",
        "reservation": {
            "date": "2024-05-01",
            "start_time": "10:00",
            "end_time": "12:00"
        },
        "accepted_user_email": "accepted_user@example.com"
    }
    """
    data = request.get_json()
    requester_email = data.get('requester_email')
    reservation = data.get('reservation')
    accepted_user_email = data.get('accepted_user_email')

    if not requester_email or not reservation or not accepted_user_email:
        return jsonify({'status': 'error', 'message': '必要なフィールドが不足しています。'}), 400

    try:
        success = send_accept_request_to_sender_email(requester_email, reservation, accepted_user_email)
        if success:
            return jsonify({'status': 'success', 'message': 'リクエスト承認者へのメールが送信されました。'}), 200
        else:
            return jsonify({'status': 'error', 'message': 'リクエスト承認者へのメールの送信に失敗しました。'}), 500
    except Exception as e:
        logger.error(f"リクエスト承認者へのメール送信中にエラーが発生しました: {e}")
        return jsonify({'status': 'error', 'message': 'リクエスト承認者へのメール送信中にエラーが発生しました。'}), 500


@api_email_notifications_bp.route('/send_reject_request_email', methods=['POST'])
@login_required
def api_send_reject_request_email():
    """
    リクエスト拒否者に拒否メールを送信します。
    リクエストボディ例:
    {
        "user_email": "user@example.com",
        "reservation": {
            "date": "2024-05-01",
            "start_time": "10:00",
            "end_time": "12:00"
        },
        "rejected_user": {
            "company_name": "株式会社XYZ",
            "email": "rejected_user@example.com",
            "contact_name": "佐藤 花子",
            "prefecture": "大阪府",
            "city": "大阪市",
            "address": "梅田1-1-1",
            "industry": "製造",
            "job_title": "主任",
            "contact_phone": "06-8765-4321"
        }
    }
    """
    data = request.get_json()
    user_email = data.get('user_email')
    reservation = data.get('reservation')
    rejected_user = data.get('rejected_user')

    if not user_email or not reservation or not rejected_user:
        return jsonify({'status': 'error', 'message': '必要なフィールドが不足しています。'}), 400

    try:
        success = send_reject_request_email(user_email, reservation, rejected_user)
        if success:
            return jsonify({'status': 'success', 'message': 'リクエスト拒否メールが送信されました。'}), 200
        else:
            return jsonify({'status': 'error', 'message': 'リクエスト拒否メールの送信に失敗しました。'}), 500
    except Exception as e:
        logger.error(f"リクエスト拒否メール送信中にエラーが発生しました: {e}")
        return jsonify({'status': 'error', 'message': 'リクエスト拒否メールの送信中にエラーが発生しました。'}), 500


@api_email_notifications_bp.route('/send_reject_request_to_sender_email', methods=['POST'])
@login_required
def api_send_reject_request_to_sender_email():
    """
    リクエスト送信者に拒否メールを送信します。
    リクエストボディ例:
    {
        "requester_email": "requester@example.com",
        "reservation": {
            "date": "2024-05-01",
            "start_time": "10:00",
            "end_time": "12:00"
        },
        "rejected_user_email": "rejected_user@example.com"
    }
    """
    data = request.get_json()
    requester_email = data.get('requester_email')
    reservation = data.get('reservation')
    rejected_user_email = data.get('rejected_user_email')

    if not requester_email or not reservation or not rejected_user_email:
        return jsonify({'status': 'error', 'message': '必要なフィールドが不足しています。'}), 400

    try:
        success = send_reject_request_to_sender_email(requester_email, reservation, rejected_user_email)
        if success:
            return jsonify({'status': 'success', 'message': 'リクエスト送信者への拒否メールが送信されました。'}), 200
        else:
            return jsonify({'status': 'error', 'message': 'リクエスト送信者への拒否メールの送信に失敗しました。'}), 500
    except Exception as e:
        logger.error(f"リクエスト送信者への拒否メール送信中にエラーが発生しました: {e}")
        return jsonify({'status': 'error', 'message': 'リクエスト送信者への拒否メール送信中にエラーが発生しました。'}), 500


@api_email_notifications_bp.route('/send_reservation_confirmation_email', methods=['POST'])
@login_required
def api_send_reservation_confirmation_email():
    """
    ユーザーに予約確認メールを送信します。
    リクエストボディ例:
    {
        "user_email": "user@example.com",
        "date": "2024-05-01",
        "time_slot": "10:00 ~ 12:00"
    }
    """
    data = request.get_json()
    user_email = data.get('user_email')
    date = data.get('date')
    time_slot = data.get('time_slot')

    if not user_email or not date or not time_slot:
        return jsonify({'status': 'error', 'message': '必要なフィールドが不足しています。'}), 400

    try:
        success = send_reservation_confirmation_email(user_email, date, time_slot)
        if success:
            return jsonify({'status': 'success', 'message': '予約確認メールが送信されました。'}), 200
        else:
            return jsonify({'status': 'error', 'message': '予約確認メールの送信に失敗しました。'}), 500
    except Exception as e:
        logger.error(f"予約確認メール送信中にエラーが発生しました: {e}")
        return jsonify({'status': 'error', 'message': '予約確認メールの送信中にエラーが発生しました。'}), 500


@api_email_notifications_bp.route('/send_lecture_confirmation_email', methods=['POST'])
@login_required
def api_send_lecture_confirmation_email():
    """
    レクチャー担当者にレクチャー確認メールを送信します。
    リクエストボディ例:
    {
        "lecturer_email": "lecturer@example.com",
        "date": "2024-05-01",
        "time_slot": "10:00 ~ 12:00"
    }
    """
    data = request.get_json()
    lecturer_email = data.get('lecturer_email')
    date = data.get('date')
    time_slot = data.get('time_slot')

    if not lecturer_email or not date or not time_slot:
        return jsonify({'status': 'error', 'message': '必要なフィールドが不足しています。'}), 400

    try:
        success = send_lecture_confirmation_email(lecturer_email, date, time_slot)
        if success:
            return jsonify({'status': 'success', 'message': 'レクチャー確認メールが送信されました。'}), 200
        else:
            return jsonify({'status': 'error', 'message': 'レクチャー確認メールの送信に失敗しました。'}), 500
    except Exception as e:
        logger.error(f"レクチャー確認メール送信中にエラーが発生しました: {e}")
        return jsonify({'status': 'error', 'message': 'レクチャー確認メールの送信中にエラーが発生しました。'}), 500


@api_email_notifications_bp.route('/send_cancel_reservation_email', methods=['POST'])
@login_required
def api_send_cancel_reservation_email():
    """
    ユーザーに予約キャンセルメールを送信します。
    リクエストボディ例:
    {
        "user_email": "user@example.com",
        "reservation": {
            "date": "2024-05-01",
            "start_time": "10:00",
            "end_time": "12:00"
        }
    }
    """
    data = request.get_json()
    user_email = data.get('user_email')
    reservation = data.get('reservation')

    if not user_email or not reservation:
        return jsonify({'status': 'error', 'message': '必要なフィールドが不足しています。'}), 400

    try:
        success = send_cancel_reservation_email(user_email, reservation)
        if success:
            return jsonify({'status': 'success', 'message': '予約キャンセルメールが送信されました。'}), 200
        else:
            return jsonify({'status': 'error', 'message': '予約キャンセルメールの送信に失敗しました。'}), 500
    except Exception as e:
        logger.error(f"予約キャンセルメール送信中にエラーが発生しました: {e}")
        return jsonify({'status': 'error', 'message': '予約キャンセルメールの送信中にエラーが発生しました。'}), 500


@api_email_notifications_bp.route('/send_new_message_email', methods=['POST'])
@login_required
def api_send_new_message_email():
    """
    ユーザーに新規メッセージメールを送信します。
    リクエストボディ例:
    {
        "to_email": "recipient@example.com",
        "company_name": "株式会社ABC"
    }
    """
    data = request.get_json()
    to_email = data.get('to_email')
    company_name = data.get('company_name')

    if not to_email or not company_name:
        return jsonify({'status': 'error', 'message': '必要なフィールドが不足しています。'}), 400

    try:
        success = send_new_message_email(to_email, company_name)
        if success:
            return jsonify({'status': 'success', 'message': '新規メッセージメールが送信されました。'}), 200
        else:
            return jsonify({'status': 'error', 'message': '新規メッセージメールの送信に失敗しました。'}), 500
    except Exception as e:
        logger.error(f"新規メッセージメール送信中にエラーが発生しました: {e}")
        return jsonify({'status': 'error', 'message': '新規メッセージメールの送信中にエラーが発生しました。'}), 500

