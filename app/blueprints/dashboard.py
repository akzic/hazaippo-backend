# app/blueprints/dashboard.py

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from app import db
from app.models import Material, Request, WantedMaterial, User
from app.blueprints.utils import log_user_activity
from sqlalchemy.orm import joinedload
from sqlalchemy import or_, and_
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

        # ──────────────────────────────────────────
        # 1. 資材 (Material) 側
        # ──────────────────────────────────────────
        raw_materials = (
            Material.query.options(
                joinedload(Material.requests).joinedload(Request.requester_user)
            )
            .filter(
                Material.matched.is_(True),
                Material.completed.is_(False),
                or_(
                    # オーナー本人・同一所在地
                    Material.user_id.in_(same_location_user_ids),
                    # 自分がリクエスト送信者
                    Material.requests.any(
                        and_(
                            Request.requester_user_id == current_user.id,
                            Request.status.in_(["Accepted", "Pending"])
                        )
                    )
                )
            )
            .distinct(Material.id)   # DB レベルで重複除外
            .all()
        )

        matched_materials = list({m.id: m for m in raw_materials}.values())

        # ──────────────────────────────────────────
        # 2. 欲しい資材 (WantedMaterial) 側
        # ──────────────────────────────────────────
        raw_wanted = (
            WantedMaterial.query.options(
                joinedload(WantedMaterial.requests).joinedload(Request.requester_user)
            )
            .filter(
                WantedMaterial.matched.is_(True),
                WantedMaterial.completed.is_(False),
                or_(
                    # オーナー本人・同一所在地
                    WantedMaterial.user_id.in_(same_location_user_ids),
                    # 自分がリクエスト送信者
                    WantedMaterial.requests.any(
                        and_(
                            Request.requester_user_id == current_user.id,
                            Request.status.in_(["Accepted", "Pending"])
                        )
                    )
                )
            )
            .distinct(WantedMaterial.id)
            .all()
        )

        matched_wanted_materials = list({w.id: w for w in raw_wanted}.values())

        # 完了した提供資材
        completed_materials = Material.query.filter(
            Material.completed == True,
            Material.user_id.in_(same_location_user_ids)
        ).all()
        completed_materials_count = len(completed_materials)

        # 完了した欲しい資材
        completed_wanted_materials = WantedMaterial.query.filter(
            WantedMaterial.completed == True,
            WantedMaterial.user_id.in_(same_location_user_ids)
        ).all()
        completed_wanted_materials_count = len(completed_wanted_materials)

        # 届いたリクエスト（提供資材）
        received_requests_materials = Request.query.options(
            joinedload(Request.material).joinedload(Material.owner),
            joinedload(Request.requester_user)
        ).filter(
            Request.requested_user_id.in_(same_location_user_ids),
            Request.status == "Pending",
            Request.material_id.isnot(None)
        ).all()

        # 届いたリクエスト（欲しい資材）
        received_requests_wanted_materials = Request.query.options(
            joinedload(Request.wanted_material).joinedload(WantedMaterial.owner),
            joinedload(Request.requester_user)
        ).filter(
            Request.requested_user_id.in_(same_location_user_ids),
            Request.status == "Pending",
            Request.wanted_material_id.isnot(None)
        ).all()

        # 送信したリクエスト（提供資材）
        sent_requests_materials = Request.query.options(
            joinedload(Request.material).joinedload(Material.owner)
        ).filter(
            Request.requester_user_id == current_user.id, 
            Request.material_id.isnot(None), 
            Request.status == "Pending"
        ).all()

        # 送信したリクエスト（欲しい資材）
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
