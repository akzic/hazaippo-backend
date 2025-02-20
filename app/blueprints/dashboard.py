# app/blueprints/dashboard.py

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from app import db
from app.models import Material, Request, WantedMaterial, User
from app.blueprints.utils import log_user_activity
from sqlalchemy.orm import joinedload
from app.forms import (
    CompleteMatchForm, 
    AcceptRequestMaterialForm, 
    AcceptRequestWantedForm,
    CancelRequestForm
)

dashboard = Blueprint('dashboard', __name__, url_prefix='/dashboard')

@dashboard.route("/", methods=['GET'])
@login_required
def dashboard_home():
    try:
        # 現在のユーザーと同じ会社名、都道府県、市、住所を持つユーザーを取得
        same_location_users = User.query.filter(
            User.company_name == current_user.company_name,
            User.prefecture == current_user.prefecture,
            User.city == current_user.city,
            User.address == current_user.address
        ).all()
        same_location_user_ids = [user.id for user in same_location_users]

        # 提供端材のマッチ履歴を事前ロード
        matched_materials = Material.query.options(
            joinedload(Material.requests).joinedload(Request.requester_user)
        ).filter(
            Material.matched == True,
            Material.completed == False,
            Material.user_id.in_(same_location_user_ids)
        ).all()

        # 欲しい端材のマッチ履歴を事前ロード
        matched_wanted_materials = WantedMaterial.query.options(
            joinedload(WantedMaterial.requests).joinedload(Request.requester_user)
        ).filter(
            WantedMaterial.matched == True,
            WantedMaterial.completed == False,
            WantedMaterial.user_id.in_(same_location_user_ids)
        ).all()

        # 完了した提供端材
        completed_materials = Material.query.filter(
            Material.completed == True,
            Material.user_id.in_(same_location_user_ids)
        ).all()
        completed_materials_count = len(completed_materials)

        # 完了した欲しい端材
        completed_wanted_materials = WantedMaterial.query.filter(
            WantedMaterial.completed == True,
            WantedMaterial.user_id.in_(same_location_user_ids)
        ).all()
        completed_wanted_materials_count = len(completed_wanted_materials)

        # 届いたリクエスト（提供端材）
        received_requests_materials = Request.query.options(
            joinedload(Request.material).joinedload(Material.owner),
            joinedload(Request.requester_user)
        ).filter(
            Request.requested_user_id.in_(same_location_user_ids),
            Request.status == "Pending",
            Request.material_id.isnot(None)
        ).all()

        # 届いたリクエスト（欲しい端材）
        received_requests_wanted_materials = Request.query.options(
            joinedload(Request.wanted_material).joinedload(WantedMaterial.owner),
            joinedload(Request.requester_user)
        ).filter(
            Request.requested_user_id.in_(same_location_user_ids),
            Request.status == "Pending",
            Request.wanted_material_id.isnot(None)
        ).all()

        # 送信したリクエスト（提供端材）
        sent_requests_materials = Request.query.options(
            joinedload(Request.material).joinedload(Material.owner)
        ).filter(
            Request.requester_user_id == current_user.id, 
            Request.material_id.isnot(None), 
            Request.status == "Pending"
        ).all()

        # 送信したリクエスト（欲しい端材）
        sent_requests_wanted = Request.query.options(
            joinedload(Request.wanted_material).joinedload(WantedMaterial.owner)
        ).filter(
            Request.requester_user_id == current_user.id, 
            Request.wanted_material_id.isnot(None), 
            Request.status == "Pending"
        ).all()

        # ユーザーのアクティビティをログに記録
        log_user_activity(
            current_user.id, 
            'ダッシュボード表示', 
            'ユーザーがダッシュボードを表示しました。', 
            request.remote_addr, 
            request.user_agent.string, 
            'N/A'
        )

        # フォームのインスタンス化
        complete_match_form = CompleteMatchForm()
        accept_request_material_form = AcceptRequestMaterialForm()
        accept_request_wanted_form = AcceptRequestWantedForm()
        cancel_request_form = CancelRequestForm()

        return render_template(
            'dashboard.html', 
            matched_materials=matched_materials, 
            matched_wanted_materials=matched_wanted_materials,
            completed_materials=completed_materials, 
            completed_materials_count=completed_materials_count,
            completed_wanted_materials=completed_wanted_materials,
            completed_wanted_materials_count=completed_wanted_materials_count,
            received_requests_materials=received_requests_materials, 
            received_requests_wanted_materials=received_requests_wanted_materials, 
            sent_requests_materials=sent_requests_materials, 
            sent_requests_wanted=sent_requests_wanted,
            complete_match_form=complete_match_form,
            cancel_request_form=cancel_request_form,
            accept_request_material_form=accept_request_material_form,
            accept_request_wanted_form=accept_request_wanted_form,
            same_location_users=same_location_users,
            same_location_user_ids=same_location_user_ids
        )
    except Exception as e:
        # エラーログを記録
        current_app.logger.error(f"Error in dashboard_home: {e}", exc_info=True)
        # ユーザーにエラーメッセージを表示
        flash(f"エラーが発生しました: {str(e)}", "danger")
        return render_template('error.html'), 500
