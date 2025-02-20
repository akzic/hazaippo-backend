# app/blueprints/requests.py

from flask import Blueprint, render_template, flash, redirect, request, url_for, current_app
from app import db
from app.models import Material, WantedMaterial, Request, User
from app.forms import (
    RequestMaterialForm, 
    RequestWantedMaterialForm,
    CompleteMatchForm,
    AcceptRequestMaterialForm,
    AcceptRequestWantedForm,
    CancelRequestForm  # 追加
)
from datetime import datetime
from flask_login import login_required, current_user
from app.blueprints.utils import log_user_activity
from app.blueprints.email_notifications import (
    send_request_email,
    send_new_request_received_email,
    send_accept_request_email,
    send_accept_request_to_sender_email,
    send_accept_request_wanted_email,
    send_accept_request_wanted_to_sender_email
)
import logging
import pytz

requests_bp = Blueprint('requests_bp', __name__)
JST = pytz.timezone('Asia/Tokyo')

# ロギングの設定
logging.basicConfig(level=logging.DEBUG)

@requests_bp.route("/request_material/<int:material_id>", methods=['GET', 'POST'])
@login_required
def request_material(material_id):
    logging.debug(f"request_material: 材料ID {material_id} のリクエスト処理を開始")
    material = Material.query.get_or_404(material_id)
    form = RequestMaterialForm()
    
    # 自分の材料にはリクエストできないようにチェック
    if material.user_id == current_user.id:
        flash('自分の材料にリクエストを送ることはできません。', 'danger')
        return redirect(url_for('materials.material_list'))
    
    if form.validate_on_submit():
        logging.debug("フォームのバリデーションに成功")
        new_request = Request(
            material_id=material_id,
            requester_user_id=current_user.id,
            requested_user_id=material.user_id,
            status='Pending',  # デフォルトは 'Pending'
            requested_at=datetime.now(JST)
        )
        db.session.add(new_request)
        db.session.commit()
        flash('端材のリクエストが送信されました！', 'success')
        log_user_activity(
            current_user.id, 
            '材料リクエスト送信',
            f'ユーザーが材料ID: {material_id} のリクエストを送信しました。',
            request.remote_addr, 
            request.user_agent.string, 
            'N/A'
        )
        
        # 対象ユーザーの without_approval をチェック
        requested_user = User.query.get(material.user_id)
        if requested_user.without_approval:
            logging.debug("without_approval が True のため、リクエストを自動承認します。")
            try:
                # リクエストを承認状態に更新
                new_request.status = 'Accepted'
                new_request.matched = True
                new_request.matched_at = datetime.now(JST)
                
                # 対象の材料をマッチング済みに設定
                material.matched = True
                material.matched_at = datetime.now(JST)
                
                # 他の保留中リクエストを拒否
                new_request.reject_other_requests()
                
                db.session.commit()
                
                # メール通知の送信
                if not send_accept_request_email(requester=current_user, material=material, accepted_user=requested_user):
                    raise Exception("承認通知メールの送信に失敗しました。")
                if not send_accept_request_to_sender_email(requester=current_user, material=material, accepted_user=requested_user):
                    raise Exception("リクエスト受け取り側への承認通知メールの送信に失敗しました。")
                
                flash('リクエストが自動的に承認され、マッチングが完了しました。', 'success')
            except Exception as e:
                logging.error(f"自動承認時のエラー: {e}")
                # ロールバック
                db.session.delete(new_request)
                db.session.commit()
                flash('リクエストの送信に失敗しました。もう一度やり直してください。', 'danger')
                return redirect(url_for('requests_bp.request_material', material_id=material_id))
        else:
            try:
                if not send_request_email(current_user.email):
                    raise Exception("リクエストメール送信失敗")
                if not send_new_request_received_email(requested_user.email):
                    raise Exception("新規リクエスト受信メール送信失敗")
            except Exception as e:
                logging.error(f"メール送信エラー: {e}")
                db.session.delete(new_request)
                db.session.commit()
                flash('リクエストの送信に失敗しました。もう一度やり直してください。', 'danger')
                return redirect(url_for('requests_bp.request_material', material_id=material_id))
        return redirect(url_for('dashboard.dashboard_home'))
    elif request.method == 'POST':
        logging.debug(f"フォームのバリデーションに失敗: {form.errors}")
        flash('フォームの入力にエラーがあります。', 'danger')
    return render_template('request_material.html', material=material, form=form)

@requests_bp.route("/request_wanted_material/<int:wanted_material_id>", methods=['GET', 'POST'])
@login_required
def request_wanted_material(wanted_material_id):
    logging.debug(f"request_wanted_material: 希望材料ID {wanted_material_id} のリクエスト処理を開始")
    wanted_material = WantedMaterial.query.get_or_404(wanted_material_id)
    form = RequestWantedMaterialForm()
    
    # 自分の希望材料にはリクエストできないようにチェック
    if wanted_material.user_id == current_user.id:
        flash('自分の希望材料にリクエストを送ることはできません。', 'danger')
        return redirect(url_for('materials.material_wanted_list'))
    
    if form.validate_on_submit():
        logging.debug("フォームのバリデーションに成功")
        new_request = Request(
            wanted_material_id=wanted_material_id,
            requester_user_id=current_user.id,
            requested_user_id=wanted_material.user_id,
            status='Pending',  # デフォルトは 'Pending'
            requested_at=datetime.now(JST)
        )
        db.session.add(new_request)
        db.session.commit()
        flash('希望材料のリクエストが送信されました！', 'success')
        log_user_activity(
            current_user.id, 
            '希望材料リクエスト送信',
            f'ユーザーが希望材料ID: {wanted_material_id} のリクエストを送信しました。',
            request.remote_addr, 
            request.user_agent.string, 
            'N/A'
        )
        
        # 対象ユーザーの without_approval をチェック
        requested_user = User.query.get(wanted_material.user_id)
        if requested_user.without_approval:
            logging.debug("without_approval が True のため、リクエストを自動承認します。")
            try:
                # リクエストを承認状態に更新
                new_request.status = 'Accepted'
                new_request.matched = True
                new_request.matched_at = datetime.now(JST)
                
                # 対象の希望材料をマッチング済みに設定
                wanted_material.matched = True
                wanted_material.matched_at = datetime.now(JST)
                
                # 他の保留中リクエストを拒否
                new_request.reject_other_requests()
                
                db.session.commit()
                
                # メール通知の送信
                if not send_accept_request_wanted_email(requester=current_user, wanted_material=wanted_material, accepted_user=requested_user):
                    raise Exception("希望材料承認通知メールの送信に失敗しました。")
                if not send_accept_request_wanted_to_sender_email(requester=current_user, wanted_material=wanted_material, accepted_user=requested_user):
                    raise Exception("希望材料リクエスト受け取り側への承認通知メールの送信に失敗しました。")
                
                flash('リクエストが自動的に承認され、マッチングが完了しました。', 'success')
            except Exception as e:
                logging.error(f"自動承認時のエラー: {e}")
                # ロールバック
                db.session.delete(new_request)
                db.session.commit()
                flash('リクエストの送信に失敗しました。もう一度やり直してください。', 'danger')
                return redirect(url_for('requests_bp.request_wanted_material', wanted_material_id=wanted_material_id))
        else:
            try:
                if not send_request_email(current_user.email):
                    raise Exception("リクエストメール送信失敗")
                if not send_new_request_received_email(requested_user.email):
                    raise Exception("新規リクエスト受信メール送信失敗")
            except Exception as e:
                logging.error(f"メール送信エラー: {e}")
                db.session.delete(new_request)
                db.session.commit()
                flash('リクエストの送信に失敗しました。もう一度やり直してください。', 'danger')
                return redirect(url_for('requests_bp.request_wanted_material', wanted_material_id=wanted_material_id))
        return redirect(url_for('dashboard.dashboard_home'))
    elif request.method == 'POST':
        logging.debug(f"フォームのバリデーションに失敗: {form.errors}")
        flash('フォームの入力にエラーがあります。', 'danger')
    return render_template('request_wanted_material.html', wanted_material=wanted_material, form=form)

@requests_bp.route("/accept_request_material/<int:request_id>", methods=['POST'])
@login_required
def accept_request_material(request_id):
    logging.debug(f"accept_request_material: リクエストID {request_id} の承認処理を開始")
    form = AcceptRequestMaterialForm()
    if form.validate_on_submit():
        material_request = Request.query.get_or_404(request_id)
        # 承認者がリクエストを送られたユーザーまたは同一の属性を持つユーザーであることを確認
        same_location_users = User.query.filter(
            User.company_name == current_user.company_name,
            User.prefecture == current_user.prefecture,
            User.city == current_user.city,
            User.address == current_user.address
        ).all()
        same_location_user_ids = [user.id for user in same_location_users]

        if (material_request.requested_user_id != current_user.id and 
            material_request.requested_user_id not in same_location_user_ids):
            flash('リクエストを承認する権限がありません。', 'danger')
            return redirect(url_for('dashboard.dashboard_home'))
        if material_request.status != 'Pending':
            flash('承認できるのは保留中のリクエストのみです。', 'warning')
            return redirect(url_for('dashboard.dashboard_home'))
        
        try:
            material_request.accept()
            material_request.reject_other_requests()
            flash('リクエストを承認しました。対象の端材がマッチングしました。', 'success')
            log_user_activity(
                current_user.id, 
                '材料リクエスト承認',
                f'ユーザーがリクエストID: {request_id} の材料リクエストを承認しました。',
                request.remote_addr, 
                request.user_agent.string, 
                'N/A'
            )
            # メール通知の送信
            if not send_accept_request_email(requester=material_request.requester_user, material=material_request.material, accepted_user=current_user):
                raise Exception("承認メール送信失敗")
            if not send_accept_request_to_sender_email(requester=material_request.requester_user, material=material_request.material, accepted_user=current_user):
                raise Exception("送信者への承認通知メール送信失敗")
        except Exception as e:
            logging.error(f"メール送信エラー: {e}")
            material_request.status = 'Pending'  # 状態を元に戻す
            db.session.commit()
            flash('リクエストの承認に失敗しました。もう一度やり直してください。', 'danger')
            return redirect(url_for('dashboard.dashboard_home'))
        return redirect(url_for('dashboard.dashboard_home'))
    else:
        logging.debug(f"フォームのバリデーションに失敗: {form.errors}")
        flash('フォームの入力にエラーがあります。', 'danger')
        return redirect(url_for('dashboard.dashboard_home'))

@requests_bp.route("/accept_request_wanted/<int:request_id>", methods=['POST'])
@login_required
def accept_request_wanted(request_id):
    logging.debug(f"accept_request_wanted: リクエストID {request_id} の承認処理を開始")
    form = AcceptRequestWantedForm()
    if form.validate_on_submit():
        wanted_material_request = Request.query.get_or_404(request_id)
        # 承認者がリクエストを送られたユーザーまたは同一の属性を持つユーザーであることを確認
        same_location_users = User.query.filter(
            User.company_name == current_user.company_name,
            User.prefecture == current_user.prefecture,
            User.city == current_user.city,
            User.address == current_user.address
        ).all()
        same_location_user_ids = [user.id for user in same_location_users]

        if (wanted_material_request.requested_user_id != current_user.id and 
            wanted_material_request.requested_user_id not in same_location_user_ids):
            flash('リクエストを承認する権限がありません。', 'danger')
            return redirect(url_for('dashboard.dashboard_home'))
        if wanted_material_request.status != 'Pending':
            flash('承認できるのは保留中のリクエストのみです。', 'warning')
            return redirect(url_for('dashboard.dashboard_home'))
        
        try:
            wanted_material_request.accept()
            wanted_material_request.reject_other_requests()
            flash('リクエストを承認しました。対象の希望材料がマッチングしました。', 'success')
            log_user_activity(
                current_user.id, 
                '希望材料リクエスト承認',
                f'ユーザーがリクエストID: {request_id} の希望材料リクエストを承認しました。',
                request.remote_addr, 
                request.user_agent.string, 
                'N/A'
            )
            # メール通知の送信
            if not send_accept_request_wanted_email(requester=wanted_material_request.requester_user, wanted_material=wanted_material_request.wanted_material, accepted_user=current_user):
                raise Exception("希望材料承認メール送信失敗")
            if not send_accept_request_wanted_to_sender_email(requester=wanted_material_request.requester_user, wanted_material=wanted_material_request.wanted_material, accepted_user=current_user):
                raise Exception("送信者への希望材料承認通知メール送信失敗")
        except Exception as e:
            logging.error(f"メール送信エラー: {e}")
            wanted_material_request.status = 'Pending'  # 状態を元に戻す
            db.session.commit()
            flash('リクエストの承認に失敗しました。もう一度やり直してください。', 'danger')
            return redirect(url_for('dashboard.dashboard_home'))
        return redirect(url_for('dashboard.dashboard_home'))
    else:
        logging.debug(f"フォームのバリデーションに失敗: {form.errors}")
        flash('フォームの入力にエラーがあります。', 'danger')
        return redirect(url_for('dashboard.dashboard_home'))

@requests_bp.route("/complete_match_material/<int:material_id>", methods=['POST'])
@login_required
def complete_match_material(material_id):
    logging.debug(f"complete_match_material: 材料ID {material_id} の取引完了処理を開始")
    form = CompleteMatchForm()
    if form.validate_on_submit():
        material = Material.query.get_or_404(material_id)
        # 完了者が材料の所有者または同一の属性を持つユーザーであることを確認
        same_location_users = User.query.filter(
            User.company_name == current_user.company_name,
            User.prefecture == current_user.prefecture,
            User.city == current_user.city,
            User.address == current_user.address
        ).all()
        same_location_user_ids = [user.id for user in same_location_users]

        if (material.user_id != current_user.id and 
            material.user_id not in same_location_user_ids):
            flash('完了する権限がありません。', 'danger')
            return redirect(url_for('dashboard.dashboard_home'))
        
        material.completed = True
        material.completed_at = datetime.now(JST)
        db.session.commit()
        flash('対象の端材が完了しました。', 'success')
        log_user_activity(
            current_user.id, 
            '材料取引完了',
            f'ユーザーが材料ID: {material_id} の取引を完了しました。',
            request.remote_addr, 
            request.user_agent.string, 
            'N/A'
        )
        return redirect(url_for('dashboard.dashboard_home'))
    else:
        logging.debug(f"フォームのバリデーションに失敗: {form.errors}")
        flash('フォームの入力にエラーがあります。', 'danger')
        return redirect(url_for('dashboard.dashboard_home'))

@requests_bp.route("/complete_match_wanted/<int:wanted_material_id>", methods=['POST'])
@login_required
def complete_match_wanted(wanted_material_id):
    logging.debug(f"complete_match_wanted: 希望材料ID {wanted_material_id} の取引完了処理を開始")
    form = CompleteMatchForm()
    if form.validate_on_submit():
        wanted_material = WantedMaterial.query.get_or_404(wanted_material_id)
        # 完了者が希望材料の所有者または同一の属性を持つユーザーであることを確認
        same_location_users = User.query.filter(
            User.company_name == current_user.company_name,
            User.prefecture == current_user.prefecture,
            User.city == current_user.city,
            User.address == current_user.address
        ).all()
        same_location_user_ids = [user.id for user in same_location_users]

        if (wanted_material.user_id != current_user.id and 
            wanted_material.user_id not in same_location_user_ids):
            flash('完了する権限がありません。', 'danger')
            return redirect(url_for('dashboard.dashboard_home'))
        
        wanted_material.completed = True
        wanted_material.completed_at = datetime.now(JST)
        db.session.commit()
        flash('対象の希望材料が完了しました。', 'success')
        log_user_activity(
            current_user.id, 
            '希望材料取引完了',
            f'ユーザーが希望材料ID: {wanted_material_id} の取引を完了しました。',
            request.remote_addr, 
            request.user_agent.string, 
            'N/A'
        )
        return redirect(url_for('dashboard.dashboard_home'))
    else:
        logging.debug(f"フォームのバリデーションに失敗: {form.errors}")
        flash('フォームの入力にエラーがあります。', 'danger')
        return redirect(url_for('dashboard.dashboard_home'))

@requests_bp.route("/cancel_request/<int:request_id>", methods=['POST'])
@login_required
def cancel_request(request_id):
    logging.debug(f"cancel_request: リクエストID {request_id} のキャンセル処理を開始")
    form = CancelRequestForm()
    if form.validate_on_submit():
        req = Request.query.get_or_404(request_id)
        if req.requester_user_id != current_user.id:
            flash('リクエストを取り消す権限がありません。', 'danger')
            return redirect(url_for('dashboard.dashboard_home'))
        if req.status != 'Pending':
            flash('キャンセルできるのは保留中のリクエストのみです。', 'warning')
            return redirect(url_for('dashboard.dashboard_home'))
        req.status = 'Rejected'
        db.session.commit()
        flash('リクエストを取り消しました。', 'success')
        log_user_activity(
            current_user.id, 
            'リクエスト取り消し',
            f'ユーザーがリクエストID: {request_id} を取り消しました。',
            request.remote_addr, 
            request.user_agent.string, 
            'N/A'
        )
        return redirect(url_for('dashboard.dashboard_home'))
    else:
        logging.debug(f"フォームのバリデーションに失敗: {form.errors}")
        flash('フォームの入力にエラーがあります。', 'danger')
        return redirect(url_for('dashboard.dashboard_home'))
