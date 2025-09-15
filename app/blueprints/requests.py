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
    CancelRequestForm
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
from sqlalchemy.orm import joinedload
import logging
import pytz
from app.utils.push import send_request_push, send_accept_push, send_precomplete_push, send_complete_push

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
        send_request_push(new_request)
        flash('資材のリクエストが送信されました！', 'success')
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
                send_request_push(new_request, auto_accepted=True)

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
        send_request_push(new_request)
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
                send_request_push(new_request, auto_accepted=True)

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
            send_accept_push(material_request)
            flash('リクエストを承認しました。対象の資材がマッチングしました。', 'success')
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
            send_accept_push(wanted_material_request)
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

@requests_bp.route("/pre_complete_material/<int:material_id>", methods=['POST'])
@login_required
def pre_complete_material(material_id):
    form = CompleteMatchForm()
    if not form.validate_on_submit():
        flash('フォームエラー', 'danger')
        return redirect(url_for('dashboard.dashboard_home'))

    material = Material.query.get_or_404(material_id)

    # オーナー or 同一所在地ユーザのみ
    if not _has_completion_right(material.user_id):
        flash('完了する権限がありません。', 'danger')
        return redirect(url_for('dashboard.dashboard_home'))

    # すでに一次完了していれば何もしない
    if material.pre_completed:
        flash('すでに一次完了済みです。', 'warning')
        return redirect(url_for('dashboard.dashboard_home'))

    material.pre_completed    = True
    material.pre_completed_at = datetime.now(JST)
    db.session.commit()
    send_precomplete_push(material_request)

    flash('一次完了しました。相手の完了をお待ちください。', 'success')
    _log('材料一次完了', f'MaterialID={material_id}')
    return redirect(url_for('dashboard.dashboard_home'))

@requests_bp.route("/finalize_material/<int:req_id>", methods=['POST'])
@login_required
def finalize_material(req_id):
    form = CompleteMatchForm()
    if not form.validate_on_submit():
        flash('フォームエラー', 'danger')
        return redirect(url_for('dashboard.dashboard_home'))

    req = Request.query.options(joinedload(Request.material)).get_or_404(req_id)

    # ❶ 受取側だけが呼べる  
    if req.requester_user_id != current_user.id:
        flash('完了する権限がありません。', 'danger')
        return redirect(url_for('dashboard.dashboard_home'))

    # ❷ オーナーが一次完了しているか？
    if not req.material.pre_completed:
        flash('まだ相手が一次完了していません。', 'warning')
        return redirect(url_for('dashboard.dashboard_home'))

    # ❸ 二段階完了
    req.material.completed    = True
    req.material.completed_at = datetime.now(JST)
    req.status                = 'Completed'
    req.completed_at          = req.material.completed_at
    db.session.commit()
    send_complete_push(req)

    flash('取引を完了しました。ありがとうございました！', 'success')
    _log('材料最終完了', f'RequestID={req.id}')
    return redirect(url_for('dashboard.dashboard_home'))

# ───────────────────────────────────────────────
# 1. 欲しい資材：一次完了（オーナー or 同一所在地ユーザ）
#    URL: /pre_complete_wanted/<wanted_material_id>
# ───────────────────────────────────────────────
@requests_bp.route("/pre_complete_wanted/<int:wanted_material_id>", methods=['POST'])
@login_required
def pre_complete_wanted(wanted_material_id):
    form = CompleteMatchForm()
    if not form.validate_on_submit():
        flash('フォームエラー', 'danger')
        return redirect(url_for('dashboard.dashboard_home'))

    wanted = WantedMaterial.query.get_or_404(wanted_material_id)

    # オーナー権限チェック
    if not _has_completion_right(wanted.user_id):
        flash('完了する権限がありません。', 'danger')
        return redirect(url_for('dashboard.dashboard_home'))

    # 重複防止
    if wanted.pre_completed:
        flash('すでに一次完了済みです。', 'warning')
        return redirect(url_for('dashboard.dashboard_home'))

    wanted.pre_completed    = True
    wanted.pre_completed_at = datetime.now(JST)
    db.session.commit()
    send_precomplete_push(wanted_request)

    flash('一次完了しました。相手の完了をお待ちください。', 'success')
    _log('希望材料一次完了', f'WantedMaterialID={wanted_material_id}')
    return redirect(url_for('dashboard.dashboard_home'))


# ───────────────────────────────────────────────
# 2. 欲しい資材：最終完了（リクエスト送信者）
#    URL: /finalize_wanted/<req_id>
# ───────────────────────────────────────────────
@requests_bp.route("/finalize_wanted/<int:req_id>", methods=['POST'])
@login_required
def finalize_wanted(req_id):
    form = CompleteMatchForm()
    if not form.validate_on_submit():
        flash('フォームエラー', 'danger')
        return redirect(url_for('dashboard.dashboard_home'))

    # リクエストを取得（WantedMaterial と requester_user を事前ロード）
    req = Request.query.options(
        joinedload(Request.wanted_material)
    ).get_or_404(req_id)

    # ❶ リクエスト送信者のみ実行可能
    if req.requester_user_id != current_user.id:
        flash('完了する権限がありません。', 'danger')
        return redirect(url_for('dashboard.dashboard_home'))

    # ❷ 相手の一次完了確認
    if not req.wanted_material.pre_completed:
        flash('まだ相手が一次完了していません。', 'warning')
        return redirect(url_for('dashboard.dashboard_home'))

    # ❸ 二段階目の完了処理
    now = datetime.now(JST)
    req.wanted_material.completed    = True
    req.wanted_material.completed_at = now
    req.status                       = 'Completed'
    req.completed_at                 = now
    db.session.commit()
    send_complete_push(req)

    flash('取引を完了しました。ありがとうございました！', 'success')
    _log('希望材料最終完了', f'RequestID={req.id}')
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

def _has_completion_right(owner_id: int) -> bool:
    """オーナー本人または同一所在地ユーザかどうか判定"""
    if owner_id == current_user.id:
        return True
    same_location_users = User.query.filter(
        User.company_name == current_user.company_name,
        User.prefecture   == current_user.prefecture,
        User.city         == current_user.city,
        User.address      == current_user.address
    ).all()
    return owner_id in [u.id for u in same_location_users]


def _log(action: str, details: str):
    """操作ログを簡単に残すヘルパー"""
    log_user_activity(
        current_user.id,
        action,
        details,
        request.remote_addr,
        request.user_agent.string,
        'N/A'
    )

# ───────────────────────────────────────────────
#   受信した「提供材料リクエスト」を拒否
#   URL: /reject_request_material/<request_id>
# ───────────────────────────────────────────────
@requests_bp.route("/reject_request_material/<int:request_id>", methods=['POST'])
@login_required
def reject_request_material(request_id):
    form = RejectRequestMaterialForm()
    if not form.validate_on_submit():
        flash('フォームエラー', 'danger')
        return redirect(url_for('dashboard.dashboard_home'))

    req = Request.query.get_or_404(request_id)

    # ▼ 権限チェック：受信側（requested_user）か同一所在地ユーザのみ
    same_loc = User.query.filter(
        User.company_name == current_user.company_name,
        User.prefecture   == current_user.prefecture,
        User.city         == current_user.city,
        User.address      == current_user.address
    ).with_entities(User.id).all()
    same_loc_ids = [u.id for u in same_loc]

    if req.requested_user_id not in ([current_user.id] + same_loc_ids):
        flash('拒否する権限がありません。', 'danger')
        return redirect(url_for('dashboard.dashboard_home'))

    if req.status != 'Pending':
        flash('拒否できるのは保留中のリクエストのみです。', 'warning')
        return redirect(url_for('dashboard.dashboard_home'))

    try:
        req.status      = 'Rejected'
        req.rejected_at = datetime.now(JST)
        db.session.commit()
        flash('リクエストを拒否しました。', 'success')
        log_user_activity(
            current_user.id, '材料リクエスト拒否',
            f'ユーザーがリクエストID: {request_id} を拒否しました。',
            request.remote_addr, request.user_agent.string, 'N/A'
        )
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"材料リクエスト拒否エラー: {e}", exc_info=True)
        flash('リクエストの拒否に失敗しました。', 'danger')

    return redirect(url_for('dashboard.dashboard_home'))


# ───────────────────────────────────────────────
#   受信した「希望材料リクエスト」を拒否
#   URL: /reject_request_wanted/<request_id>
# ───────────────────────────────────────────────
@requests_bp.route("/reject_request_wanted/<int:request_id>", methods=['POST'])
@login_required
def reject_request_wanted(request_id):
    form = RejectRequestWantedForm()
    if not form.validate_on_submit():
        flash('フォームエラー', 'danger')
        return redirect(url_for('dashboard.dashboard_home'))

    req = Request.query.get_or_404(request_id)

    # ▼ 権限チェック（材料側と同じロジック）
    same_loc = User.query.filter(
        User.company_name == current_user.company_name,
        User.prefecture   == current_user.prefecture,
        User.city         == current_user.city,
        User.address      == current_user.address
    ).with_entities(User.id).all()
    same_loc_ids = [u.id for u in same_loc]

    if req.requested_user_id not in ([current_user.id] + same_loc_ids):
        flash('拒否する権限がありません。', 'danger')
        return redirect(url_for('dashboard.dashboard_home'))

    if req.status != 'Pending':
        flash('拒否できるのは保留中のリクエストのみです。', 'warning')
        return redirect(url_for('dashboard.dashboard_home'))

    try:
        req.status      = 'Rejected'
        req.rejected_at = datetime.now(JST)
        db.session.commit()
        flash('リクエストを拒否しました。', 'success')
        log_user_activity(
            current_user.id, '希望材料リクエスト拒否',
            f'ユーザーがリクエストID: {request_id} を拒否しました。',
            request.remote_addr, request.user_agent.string, 'N/A'
        )
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"希望材料リクエスト拒否エラー: {e}", exc_info=True)
        flash('リクエストの拒否に失敗しました。', 'danger')

    return redirect(url_for('dashboard.dashboard_home'))
