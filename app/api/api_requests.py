# app/api/api_requests.py

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import User, Request, Material, WantedMaterial
from app import db
from marshmallow import ValidationError
from datetime import datetime
import logging
import pytz

api_requests = Blueprint('api_requests', __name__)
logger = logging.getLogger(__name__)
JST = pytz.timezone('Asia/Tokyo')

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

@api_requests.route('/create_request_material', methods=['POST'])
@jwt_required()
def create_request_material():
    try:
        data = request.get_json()
        material_id = data.get('material_id')

        if not material_id:
            return error_response("material_id が必要です。", 400)

        material = Material.query.get(material_id)
        if not material:
            return error_response("指定された材料が存在しません。", 404)

        user_id = get_jwt_identity()
        current_user = User.query.get(user_id)

        if material.user_id == current_user.id:
            return error_response("自分の材料にリクエストを送ることはできません。", 403)

        # 既存のリクエストがないか確認（重複防止）
        existing_request = Request.query.filter_by(
            material_id=material_id,
            requester_user_id=current_user.id,
            status='Pending'
        ).first()
        if existing_request:
            return error_response("既にこの材料に対するリクエストが存在します。", 400)

        new_request = Request(
            material_id=material_id,
            requester_user_id=current_user.id,
            requested_user_id=material.user_id,
            status='Pending',
            requested_at=datetime.now(JST)
        )
        db.session.add(new_request)
        db.session.commit()

        # without_approval チェック
        requested_user = User.query.get(material.user_id)
        if requested_user.without_approval:
            # 自動承認
            new_request.status = 'Accepted'
            new_request.matched = True
            new_request.matched_at = datetime.now(JST)

            # 材料のマッチング更新
            material.matched = True
            material.matched_at = datetime.now(JST)

            # 他の保留中リクエストを拒否
            new_request.reject_other_requests()

            db.session.commit()

            # メール通知の送信（メール送信はAPI外で処理）
            # 例: send_accept_request_email(requester=current_user, material=material, accepted_user=requested_user)

            return success_response(
                {'request': new_request.to_dict()},
                "リクエストが自動的に承認され、マッチングが完了しました。"
            )
        else:
            # メール通知の送信（メール送信はAPI外で処理）
            # 例: send_request_email(current_user.email), send_new_request_received_email(requested_user.email)

            return success_response(
                {'request': new_request.to_dict()},
                "リクエストが送信されました。"
            )
    except Exception as e:
        current_app.logger.error(f"Error in create_request_material: {e}", exc_info=True)
        return error_response("エラーが発生しました。", 500)

@api_requests.route('/create_request_wanted_material', methods=['POST'])
@jwt_required()
def create_request_wanted_material():
    try:
        data = request.get_json()
        wanted_material_id = data.get('wanted_material_id')

        if not wanted_material_id:
            return error_response("wanted_material_id が必要です。", 400)

        wanted_material = WantedMaterial.query.get(wanted_material_id)
        if not wanted_material:
            return error_response("指定された希望材料が存在しません。", 404)

        user_id = get_jwt_identity()
        current_user = User.query.get(user_id)

        if wanted_material.user_id == current_user.id:
            return error_response("自分の希望材料にリクエストを送ることはできません。", 403)

        # 既存のリクエストがないか確認（重複防止）
        existing_request = Request.query.filter_by(
            wanted_material_id=wanted_material_id,
            requester_user_id=current_user.id,
            status='Pending'
        ).first()
        if existing_request:
            return error_response("既にこの希望材料に対するリクエストが存在します。", 400)

        new_request = Request(
            wanted_material_id=wanted_material_id,
            requester_user_id=current_user.id,
            requested_user_id=wanted_material.user_id,
            status='Pending',
            requested_at=datetime.now(JST)
        )
        db.session.add(new_request)
        db.session.commit()

        # without_approval チェック
        requested_user = User.query.get(wanted_material.user_id)
        if requested_user.without_approval:
            # 自動承認
            new_request.status = 'Accepted'
            new_request.matched = True
            new_request.matched_at = datetime.now(JST)

            # 希望材料のマッチング更新
            wanted_material.matched = True
            wanted_material.matched_at = datetime.now(JST)

            # 他の保留中リクエストを拒否
            new_request.reject_other_requests()

            db.session.commit()

            # メール通知の送信（メール送信はAPI外で処理）
            # 例: send_accept_request_wanted_email(requester=current_user, wanted_material=wanted_material, accepted_user=requested_user)

            return success_response(
                {'request': new_request.to_dict()},
                "リクエストが自動的に承認され、マッチングが完了しました。"
            )
        else:
            # メール通知の送信（メール送信はAPI外で処理）
            # 例: send_request_email(current_user.email), send_new_request_received_email(requested_user.email)

            return success_response(
                {'request': new_request.to_dict()},
                "リクエストが送信されました。"
            )
    except Exception as e:
        current_app.logger.error(f"Error in create_request_wanted_material: {e}", exc_info=True)
        return error_response("エラーが発生しました。", 500)

@api_requests.route('/accept_request/<int:request_id>', methods=['POST'])
@jwt_required()
def accept_request(request_id):
    try:
        user_id = get_jwt_identity()
        current_user = User.query.get(user_id)

        request_obj = Request.query.get_or_404(request_id)

        # 承認者がリクエストを送られたユーザーであることを確認
        if request_obj.requested_user_id != current_user.id:
            return error_response("リクエストを承認する権限がありません。", 403)

        if request_obj.status != 'Pending':
            return error_response("承認できるのは保留中のリクエストのみです。", 400)

        # 承認処理
        request_obj.accept()
        request_obj.reject_other_requests()

        # メール通知の送信（メール送信はAPI外で処理）
        # 例: send_accept_request_email(requester=request_obj.requester_user, material=request_obj.material, accepted_user=current_user)
        # 例: send_accept_request_to_sender_email(requester=request_obj.requester_user, material=request_obj.material, accepted_user=current_user)

        return success_response({'request': request_obj.to_dict()}, "リクエストを承認しました。")
    except Exception as e:
        current_app.logger.error(f"Error in accept_request: {e}", exc_info=True)
        return error_response("エラーが発生しました。", 500)

@api_requests.route('/complete_match_material', methods=['POST'])
@jwt_required()
def complete_match_material():
    try:
        data = request.get_json()
        material_id = data.get('material_id')

        if not material_id:
            return error_response("material_id が必要です。", 400)

        material = Material.query.get(material_id)
        if not material:
            return error_response("指定された材料が存在しません。", 404)

        user_id = get_jwt_identity()
        current_user = User.query.get(user_id)

        # 完了者が材料の所有者であることを確認
        if material.user_id != current_user.id:
            return error_response("完了する権限がありません。", 403)

        # 完了処理
        material.completed = True
        material.completed_at = datetime.now(JST)
        db.session.commit()

        return success_response({'material': material.to_dict()}, "対象の端材が完了しました。")
    except Exception as e:
        current_app.logger.error(f"Error in complete_match_material: {e}", exc_info=True)
        return error_response("エラーが発生しました。", 500)

@api_requests.route('/complete_match_wanted', methods=['POST'])
@jwt_required()
def complete_match_wanted():
    try:
        data = request.get_json()
        wanted_material_id = data.get('wanted_material_id')

        if not wanted_material_id:
            return error_response("wanted_material_id が必要です。", 400)

        wanted_material = WantedMaterial.query.get(wanted_material_id)
        if not wanted_material:
            return error_response("指定された希望材料が存在しません。", 404)

        user_id = get_jwt_identity()
        current_user = User.query.get(user_id)

        # 完了者が希望材料の所有者であることを確認
        if wanted_material.user_id != current_user.id:
            return error_response("完了する権限がありません。", 403)

        # 完了処理
        wanted_material.completed = True
        wanted_material.completed_at = datetime.now(JST)
        db.session.commit()

        return success_response({'wanted_material': wanted_material.to_dict()}, "対象の希望材料が完了しました。")
    except Exception as e:
        current_app.logger.error(f"Error in complete_match_wanted: {e}", exc_info=True)
        return error_response("エラーが発生しました。", 500)

@api_requests.route('/cancel_request', methods=['POST'])
@jwt_required()
def cancel_request():
    try:
        data = request.get_json()
        request_id = data.get('request_id')

        if not request_id:
            return error_response("request_id が必要です。", 400)

        req = Request.query.get(request_id)
        if not req:
            return error_response("指定されたリクエストが存在しません。", 404)

        user_id = get_jwt_identity()
        current_user = User.query.get(user_id)

        if req.requester_user_id != current_user.id:
            return error_response("リクエストを取り消す権限がありません。", 403)

        if req.status != 'Pending':
            return error_response("キャンセルできるのは保留中のリクエストのみです。", 400)

        req.status = 'Rejected'
        db.session.commit()

        return success_response({'request': req.to_dict()}, "リクエストを取り消しました。")
    except Exception as e:
        current_app.logger.error(f"Error in cancel_request: {e}", exc_info=True)
        return error_response("エラーが発生しました。", 500)
