# app/api/api_dashboard.py

from flask import Blueprint, jsonify, current_app, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import User, Reservation, Lecture
from app import db
from datetime import datetime
import logging

api_dashboard = Blueprint('api_dashboard', __name__)

logger = logging.getLogger(__name__)

def success_response(data, message="", status=200):
    return jsonify({
        'success': True,
        'message': message,
        'data': data
    }), status

def error_response(message, status=400):
    return jsonify({
        'success': False,
        'message': message
    }), status

@api_dashboard.route('/dashboard_stats', methods=['GET'])
@jwt_required()
def get_dashboard_stats():
    """
    ダッシュボードの統計情報を取得します。
    例:
    - ユーザーの総数
    - 予約の数
    - 講義の数
    """
    try:
        user_id = get_jwt_identity()
        current_user = User.query.get(user_id)

        if not current_user:
            return error_response("ユーザーが見つかりません。", 404)

        total_users = User.query.count()
        total_reservations = Reservation.query.count()
        total_lectures = Lecture.query.count()

        stats = {
            'total_users': total_users,
            'total_reservations': total_reservations,
            'total_lectures': total_lectures
        }

        return success_response({'stats': stats}, "ダッシュボード統計情報を取得しました。")
    except Exception as e:
        logger.error(f"Error in get_dashboard_stats: {e}", exc_info=True)
        return error_response("エラーが発生しました。", 500)

@api_dashboard.route('/recent_activities', methods=['GET'])
@jwt_required()
def get_recent_activities():
    """
    最近のユーザーアクティビティを取得します。
    例:
    - 最近の予約
    - 最近の講義
    """
    try:
        user_id = get_jwt_identity()
        current_user = User.query.get(user_id)

        if not current_user:
            return error_response("ユーザーが見つかりません。", 404)

        recent_reservations = Reservation.query.order_by(Reservation.date.desc()).limit(5).all()
        recent_lectures = Lecture.query.order_by(Lecture.created_at.desc()).limit(5).all()

        reservations_data = [res.to_dict() for res in recent_reservations]
        lectures_data = [lec.to_dict() for lec in recent_lectures]

        activities = {
            'recent_reservations': reservations_data,
            'recent_lectures': lectures_data
        }

        return success_response({'activities': activities}, "最近のアクティビティを取得しました。")
    except Exception as e:
        logger.error(f"Error in get_recent_activities: {e}", exc_info=True)
        return error_response("エラーが発生しました。", 500)

@api_dashboard.route('/user_profile', methods=['GET'])
@jwt_required()
def get_user_profile():
    """
    ユーザーのプロフィール情報を取得します。
    """
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)

        if not user:
            return error_response("ユーザーが見つかりません。", 404)

        profile_data = user.to_dict()

        return success_response({'profile': profile_data}, "ユーザープロフィールを取得しました。")
    except Exception as e:
        logger.error(f"Error in get_user_profile: {e}", exc_info=True)
        return error_response("エラーが発生しました。", 500)

@api_dashboard.route('/update_profile', methods=['PUT'])
@jwt_required()
def update_profile():
    """
    ユーザーのプロフィール情報を更新します。
    必要なデータをJSONで送信してください。
    """
    try:
        data = request.get_json()
        if not data:
            return error_response("無効なデータです。", 400)

        user_id = get_jwt_identity()
        user = User.query.get(user_id)

        if not user:
            return error_response("ユーザーが見つかりません。", 404)

        # 更新可能なフィールドのみを更新
        updatable_fields = ['company_name', 'prefecture', 'city', 'address', 'company_phone', 
                            'industry', 'job_title', 'without_approval', 'contact_name', 
                            'contact_phone', 'line_id', 'lecture_flug', 'business_structure']

        for field in updatable_fields:
            if field in data:
                setattr(user, field, data[field])

        db.session.commit()

        return success_response({'profile': user.to_dict()}, "プロフィールが更新されました。")
    except Exception as e:
        logger.error(f"Error in update_profile: {e}", exc_info=True)
        return error_response("エラーが発生しました。", 500)
