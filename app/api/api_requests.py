# app/api/api_requests.py

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, create_access_token, verify_jwt_in_request
from app import db
from app.models import Material, WantedMaterial, Request, User, Conversation
from datetime import datetime
import pytz
import logging
from sqlalchemy import or_, exists, func
from sqlalchemy.orm import aliased, joinedload
from app.blueprints.utils import log_user_activity
from app.blueprints.email_notifications import (
    send_request_email,
    send_new_request_received_email,
    send_accept_request_email,
    send_accept_request_to_sender_email,
    send_accept_request_wanted_email,
    send_accept_request_wanted_to_sender_email,
    send_reject_request_material_email,
    send_reject_notification_material_email,
    send_reject_request_wanted_email,
    send_reject_notification_wanted_email
)
from app.utils.push import send_request_push, send_accept_push, send_precomplete_push, send_complete_push

api_requests_bp = Blueprint('api_requests', __name__, url_prefix='/api/requests')
JST = pytz.timezone('Asia/Tokyo')
logger = logging.getLogger(__name__)

# image が「S3キー」だった時に URL 化できるならする（無くても落とさない）
try:
    from app.utils.s3_uploader import build_s3_url  # type: ignore
except Exception:
    build_s3_url = None

def get_current_user():
    """JWTからユーザーIDを取得し、DBからユーザー情報をロードする"""
    user_id = get_jwt_identity()
    return User.query.get(user_id)

def _normalize_image_url(raw):
    """
    User.image が URL の場合はそのまま返す。
    URL でなければ build_s3_url があれば使う。
    どちらも無理なら文字列として返す（nullも許容）
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if s.startswith("http://") or s.startswith("https://"):
        return s
    if build_s3_url:
        try:
            return build_s3_url(s)
        except Exception:
            return s
    return s

def user_to_dict(u: User):
    """Flutter の RequestUser に合わせた dict（image を追加）"""
    if u is None:
        return None
    # 画像カラム名が揺れても落ちないように（image / image_url 想定）
    raw_image = getattr(u, "image", None)
    if raw_image is None:
        raw_image = getattr(u, "image_url", None)
    return {
        'id': u.id,
        'email': u.email,
        'company_name': u.company_name,
        'prefecture': u.prefecture,
        'city': u.city,
        'address': u.address,
        'business_structure': u.business_structure,
        'industry': u.industry,
        'job_title': u.job_title,
        'image': _normalize_image_url(raw_image),  # ★追加
    }

# ヘルパー関数：WantedMaterial オブジェクトを辞書形式に変換
def wanted_material_to_dict(wm):
    return {
        'id': wm.id,
        'type': wm.type,  # SQLAlchemyモデル側で資材の種類を保持しているキー。Flutter側では materialType として扱います。
        'wood_type': wm.wood_type,
        'board_material_type': wm.board_material_type,
        'panel_type': wm.panel_type,
        'size_1': wm.size_1,
        'size_2': wm.size_2,
        'size_3': wm.size_3,
        'quantity': wm.quantity,
        'deadline': wm.deadline.isoformat() if wm.deadline else None,
        'created_at': wm.created_at.isoformat() if wm.created_at else None,
        'exclude_weekends': wm.exclude_weekends,
        'note': wm.note,
        'location': wm.location,
        'completed': wm.completed,
        'deleted': wm.deleted,
        # WantedMaterial には user 属性はなく、代わりに owner 属性が存在する前提で変換
        'user': {
            'id': wm.owner.id if wm.owner else None,
            'email': wm.owner.email if wm.owner else None,
            'company_name': wm.owner.company_name if wm.owner else None,
            'prefecture': wm.owner.prefecture if wm.owner else None,
            'city': wm.owner.city if wm.owner else None,
            'address': wm.owner.address if wm.owner else None,
            'business_structure': wm.owner.business_structure if wm.owner else None,
            'industry': wm.owner.industry if wm.owner else None,
            'job_title': wm.owner.job_title if wm.owner else None,
        } if wm.owner else None,
    }

# 現在のユーザー視点の資材リクエスト状況をまとめて返すヘルパー
def _get_material_request_stats(material, requester_user_id=None):
    """
    material: Material オブジェクト
    requester_user_id: ログインユーザーID（None の場合は has_requested は常に False）
    戻り値:
      {
        'material_id': ...,
        'total_requests': int,
        'pending_requests': int,
        'has_requested': bool,
        'request_id': int or None,
        'has_rejected': bool,
        'rejected_request_id': int or None,
        'rejected_at': str or None,
      }
    """
    # 全ステータスのリクエスト数
    total_requests = db.session.query(func.count(Request.id)).filter(
        Request.material_id == material.id
    ).scalar()

    # Pending のリクエスト数
    pending_requests = db.session.query(func.count(Request.id)).filter(
        Request.material_id == material.id,
        Request.status == "Pending"
    ).scalar()

    has_requested = False
    current_request_id = None
    has_rejected = False
    rejected_request_id = None
    rejected_at = None

    if requester_user_id is not None:
        my_req = Request.query.filter_by(
            material_id=material.id,
            requester_user_id=requester_user_id,
            status="Pending"
        ).first()
        if my_req:
            has_requested = True
            current_request_id = my_req.id

        # ★ 自分の Rejected（直近）も拾う（cancel_request 由来で rejected_at が null の場合もあるので id も併用）
        my_rejected = (Request.query
                       .filter_by(material_id=material.id,
                                  requester_user_id=requester_user_id,
                                  status="Rejected")
                       .order_by(Request.rejected_at.desc(), Request.id.desc())
                       .first())
        if my_rejected:
            has_rejected = True
            rejected_request_id = my_rejected.id
            ra = getattr(my_rejected, "rejected_at", None)
            rejected_at = ra.isoformat() if ra else None

    return {
         'material_id': material.id,
         'total_requests': total_requests,
         'pending_requests': pending_requests,
         'has_requested': has_requested,
         'request_id': current_request_id,
         'has_rejected': has_rejected,
         'rejected_request_id': rejected_request_id,
         'rejected_at': rejected_at,
    }

# ─── 資材リクエスト（材料） ─────────────────────────────
@api_requests_bp.route("/request_material/<int:material_id>", methods=['POST'])
@jwt_required()
def request_material(material_id):
    current_user = get_current_user()
    material = Material.query.get_or_404(material_id)

    if material.user_id == current_user.id:
        return jsonify({'status': 'error', 'message': '自分の材料にリクエストを送ることはできません。'}), 400

    # すでに同じ資材に Pending のリクエストを出している場合は二重送信させない
    existing_req = Request.query.filter_by(
        material_id=material_id,
        requester_user_id=current_user.id,
        status='Pending'
    ).first()
    if existing_req:
        stats = _get_material_request_stats(material, requester_user_id=current_user.id)
        return jsonify({
            'status': 'error',
            'message': 'この資材にはすでにリクエストを送信済みです。',
            'request_id': existing_req.id,
            **stats,
        }), 400

    new_request = Request(
        material_id=material_id,
        requester_user_id=current_user.id,
        requested_user_id=material.user_id,
        status='Pending',
        requested_at=datetime.now(JST)
    )
    db.session.add(new_request)
    db.session.commit()
    send_request_push(new_request)

    log_user_activity(
        current_user.id,
        '材料リクエスト送信',
        f'ユーザーが材料ID: {material_id} のリクエストを送信しました。',
        request.remote_addr,
        request.user_agent.string,
        'N/A'
    )

    requested_user = User.query.get(material.user_id)
    if requested_user.without_approval:
        try:
            # 既に別のリクエストが承諾/完了されている場合は「自動承諾」しない（Pending のまま保留）
            existing_match = Request.query.filter(
                Request.material_id == material_id,
                Request.status.in_(["Accepted", "Completed"])
            ).first()
            if existing_match:
                stats = _get_material_request_stats(material, requester_user_id=current_user.id)
                return jsonify({
                    'status': 'success',
                    'message': '資材のリクエストが送信されました。（現在別のリクエストを承諾中のため保留中です）',
                    'request_id': new_request.id,
                    **stats,
                }), 200
            new_request.status = 'Accepted'
            new_request.matched = True
            new_request.matched_at = datetime.now(JST)
            material.matched = True
            material.matched_at = datetime.now(JST)
            db.session.commit()
            send_request_push(new_request, auto_accepted=True)

            if not send_accept_request_email(requester=current_user, material=material, accepted_user=requested_user):
                raise Exception("承認通知メールの送信に失敗しました。")
            if not send_accept_request_to_sender_email(requester=current_user, material=material, accepted_user=requested_user):
                raise Exception("リクエスト受け取り側への承認通知メールの送信に失敗しました。")

            # 自動承認後の最新ステータスを返す
            stats = _get_material_request_stats(material, requester_user_id=current_user.id)
            return jsonify({
                'status': 'success',
                'message': 'リクエストが自動承認され、マッチングが完了しました。',
                'request_id': new_request.id,
                **stats,
            }), 200

        except Exception as e:
            logger.error(f"自動承認時のエラー: {e}")
            db.session.delete(new_request)
            db.session.commit()
            return jsonify({'status': 'error', 'message': 'リクエストの送信に失敗しました。もう一度お試しください。'}), 500
    else:
        try:
            if not send_request_email(current_user.email):
                raise Exception("リクエストメール送信失敗")
            if not send_new_request_received_email(requested_user.email):
                raise Exception("新規リクエスト受信メール送信失敗")
        except Exception as e:
            logger.error(f"メール送信エラー: {e}")
            db.session.delete(new_request)
            db.session.commit()
            return jsonify({'status': 'error', 'message': 'リクエストの送信に失敗しました。もう一度お試しください。'}), 500

    # 通常パターンの成功レスポンス（件数＋has_requested 付き）
    stats = _get_material_request_stats(material, requester_user_id=current_user.id)
    return jsonify({
        'status': 'success',
        'message': '資材のリクエストが送信されました。',
        'request_id': new_request.id,
        **stats,
    }), 200


# ─── 資材リクエスト（希望材料） ─────────────────────────────
@api_requests_bp.route("/request_wanted_material/<int:wanted_material_id>", methods=['POST'])
@jwt_required()
def request_wanted_material(wanted_material_id):
    current_user = get_current_user()
    wanted_material = WantedMaterial.query.get_or_404(wanted_material_id)

    if wanted_material.user_id == current_user.id:
        return jsonify({'status': 'error', 'message': '自分の希望材料にリクエストを送ることはできません。'}), 400

    new_request = Request(
        wanted_material_id=wanted_material_id,
        requester_user_id=current_user.id,
        requested_user_id=wanted_material.user_id,
        status='Pending',
        requested_at=datetime.now(JST)
    )
    db.session.add(new_request)
    db.session.commit()
    send_request_push(new_request)

    log_user_activity(
        current_user.id, 
        '希望材料リクエスト送信',
        f'ユーザーが希望材料ID: {wanted_material_id} のリクエストを送信しました。',
        request.remote_addr, 
        request.user_agent.string, 
        'N/A'
    )

    requested_user = User.query.get(wanted_material.user_id)
    if requested_user.without_approval:
        try:
            new_request.status = 'Accepted'
            new_request.matched = True
            new_request.matched_at = datetime.now(JST)
            wanted_material.matched = True
            wanted_material.matched_at = datetime.now(JST)
            new_request.reject_other_requests()
            db.session.commit()
            send_request_push(new_request, auto_accepted=True)

            if not send_accept_request_wanted_email(requester=current_user, wanted_material=wanted_material, accepted_user=requested_user):
                raise Exception("希望材料承認通知メールの送信に失敗しました。")
            if not send_accept_request_wanted_to_sender_email(requester=current_user, wanted_material=wanted_material, accepted_user=requested_user):
                raise Exception("希望材料リクエスト受け取り側への承認通知メールの送信に失敗しました。")
            return jsonify({'status': 'success', 'message': 'リクエストが自動承認され、マッチングが完了しました。'}), 200

        except Exception as e:
            logger.error(f"自動承認時のエラー: {e}")
            db.session.delete(new_request)
            db.session.commit()
            return jsonify({'status': 'error', 'message': 'リクエストの送信に失敗しました。もう一度お試しください。'}), 500
    else:
        try:
            if not send_request_email(current_user.email):
                raise Exception("リクエストメール送信失敗")
            if not send_new_request_received_email(requested_user.email):
                raise Exception("新規リクエスト受信メール送信失敗")
        except Exception as e:
            logger.error(f"メール送信エラー: {e}")
            db.session.delete(new_request)
            db.session.commit()
            return jsonify({'status': 'error', 'message': 'リクエストの送信に失敗しました。もう一度お試しください。'}), 500

    return jsonify({'status': 'success', 'message': '希望材料のリクエストが送信されました。'}), 200


# ─── 資材リクエスト承認（材料） ─────────────────────────────
@api_requests_bp.route("/accept_request_material/<int:request_id>", methods=['POST'])
@jwt_required()
def accept_request_material(request_id):
    current_user = get_current_user()
    material_request = Request.query.get_or_404(request_id)

    # 同一拠点ユーザー許可
    same_location_users = User.query.filter(
        User.company_name == current_user.company_name,
        User.prefecture   == current_user.prefecture,
        User.city         == current_user.city,
        User.address      == current_user.address
    ).all()
    same_location_user_ids = [u.id for u in same_location_users]

    if (material_request.requested_user_id != current_user.id and
        material_request.requested_user_id not in same_location_user_ids):
        return jsonify({'status': 'error', 'message': 'リクエストを承認する権限がありません。'}), 403

    if material_request.status != 'Pending':
        return jsonify({'status': 'error', 'message': '承認できるのは保留中のリクエストのみです。'}), 400

    # 既に同一資材で承諾/完了があるなら二重承諾させない
    if material_request.material_id is not None:
        existing_match = Request.query.filter(
            Request.material_id == material_request.material_id,
            Request.status.in_(["Accepted", "Completed"]),
            Request.id != material_request.id
        ).first()
        if existing_match:
            return jsonify({
                'status': 'error',
                'message': '既に別のリクエストを承諾中です。キャンセル後に受け入れてください。'
            }), 400

    try:
        # 1) リクエスト承認処理
        material_request.accept()
        db.session.commit()
        send_accept_push(material_request)

        log_user_activity(
            current_user.id,
            '材料リクエスト承認',
            f'ユーザーがリクエストID: {request_id} の材料リクエストを承認しました。',
            request.remote_addr,
            request.user_agent.string,
            'N/A'
        )

        # 2) メール送信（失敗時は例外でロールバック）
        if (not send_accept_request_email(requester=material_request.requester_user,
                                          material=material_request.material,
                                          accepted_user=current_user)
            or
            not send_accept_request_to_sender_email(requester=material_request.requester_user,
                                                    material=material_request.material,
                                                    accepted_user=current_user)):
            raise Exception("承認通知メール送信失敗")

        # === 3) 会話ID & チャットトークンを返す ================== #
        ### 追加: 会話が無ければ生成し、JWT を発行して返却 ############
        requester = material_request.requester_user
        conversation = Conversation.query.filter(
            ((Conversation.user1_id == current_user.id) & (Conversation.user2_id == requester.id)) |
            ((Conversation.user1_id == requester.id)     & (Conversation.user2_id == current_user.id))
        ).filter_by(is_hidden=False).first()

        if conversation is None:
            conversation = Conversation(user1_id=current_user.id, user2_id=requester.id)
            db.session.add(conversation)
            db.session.commit()

        chat_token = create_access_token(identity=current_user.id)
        #############################################################

        return jsonify({
            'status'         : 'success',
            'message'        : 'リクエストを承認しました。',
            'conversation_id': conversation.id,        # 追加
            'chat_token'     : chat_token,             # 追加
            'user_name'      : requester.contact_name or
                               requester.company_name  or
                               requester.email         # 追加
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"材料リクエスト処理中のエラー: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': 'リクエストの承認に失敗しました。'}), 500



# ─── 資材リクエスト承認（希望材料） ─────────────────────────────
@api_requests_bp.route("/accept_request_wanted/<int:request_id>", methods=['POST'])
@jwt_required()
def accept_request_wanted(request_id):
    current_user = get_current_user()
    wanted_request = Request.query.get_or_404(request_id)

    same_location_users = User.query.filter(
        User.company_name == current_user.company_name,
        User.prefecture   == current_user.prefecture,
        User.city         == current_user.city,
        User.address      == current_user.address
    ).all()
    same_location_user_ids = [u.id for u in same_location_users]

    if (wanted_request.requested_user_id != current_user.id and
        wanted_request.requested_user_id not in same_location_user_ids):
        return jsonify({'status': 'error', 'message': 'リクエストを承認する権限がありません。'}), 403

    if wanted_request.status != 'Pending':
        return jsonify({'status': 'error', 'message': '承認できるのは保留中のリクエストのみです。'}), 400

    try:
        wanted_request.accept()
        wanted_request.reject_other_requests()
        db.session.commit()
        send_accept_push(wanted_request)

        log_user_activity(
            current_user.id,
            '希望材料リクエスト承認',
            f'ユーザーがリクエストID: {request_id} の希望材料リクエストを承認しました。',
            request.remote_addr,
            request.user_agent.string,
            'N/A'
        )

        if (not send_accept_request_wanted_email(requester=wanted_request.requester_user,
                                                 wanted_material=wanted_request.wanted_material,
                                                 accepted_user=current_user)
            or
            not send_accept_request_wanted_to_sender_email(requester=wanted_request.requester_user,
                                                           wanted_material=wanted_request.wanted_material,
                                                           accepted_user=current_user)):
            raise Exception("承認通知メール送信失敗")

        # === 会話ID & トークン生成 ===
        ### 追加ロジックは材料側と同じ ###############################
        requester = wanted_request.requester_user
        conversation = Conversation.query.filter(
            ((Conversation.user1_id == current_user.id) & (Conversation.user2_id == requester.id)) |
            ((Conversation.user1_id == requester.id)     & (Conversation.user2_id == current_user.id))
        ).filter_by(is_hidden=False).first()

        if conversation is None:
            conversation = Conversation(user1_id=current_user.id, user2_id=requester.id)
            db.session.add(conversation)
            db.session.commit()

        chat_token = create_access_token(identity=current_user.id)
        ###############################################################

        return jsonify({
            'status'         : 'success',
            'message'        : 'リクエストを承認しました。',
            'conversation_id': conversation.id,        # 追加
            'chat_token'     : chat_token,             # 追加
            'user_name'      : requester.contact_name or
                               requester.company_name  or
                               requester.email         # 追加
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"希望材料リクエスト処理中のエラー: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': 'リクエストの承認に失敗しました。'}), 500

from sqlalchemy.orm import joinedload
from datetime import datetime
# ─── 取引【最終】完了（材料）──────────────────────────────────
@api_requests_bp.route("/complete_match_material/<int:material_id>", methods=['POST'])
@jwt_required()
def complete_match_material(material_id):
    current_user = get_current_user()
    material = Material.query.get_or_404(material_id)

    # ★ 承諾済みリクエストを取得
    accepted_req = (Request.query
                    .options(joinedload(Request.requester_user))
                    .filter_by(material_id=material.id, status='Accepted')
                    .first())

    # ★ 最終完了できるのはリクエスト送信者のみ
    if not accepted_req or accepted_req.requester_user_id != current_user.id:
        return jsonify({'status': 'error', 'message': '完了する権限がありません。'}), 403

    # すでに完了済みなら 200 を返して何もしない
    if material.completed:
        return jsonify({'status': 'success', 'message': '既に完了しています。'}), 200

    # ★ 完了フラグの更新
    material.completed = True
    material.completed_at = datetime.now(JST)
    accepted_req.completed_at = material.completed_at
    accepted_req.status = 'Completed'

    db.session.commit()
    send_complete_push(accepted_req)
    return jsonify({'status': 'success', 'message': '材料の取引が最終完了しました。'}), 200

# ─── 取引【最終】完了（希望材料）────────────────────────────
@api_requests_bp.route("/complete_match_wanted/<int:wanted_material_id>", methods=['POST'])
@jwt_required()
def complete_match_wanted(wanted_material_id):
    current_user = get_current_user()
    wanted_material = WantedMaterial.query.get_or_404(wanted_material_id)

    # ★ 承諾済みリクエスト取得
    accepted_req = (Request.query
                    .options(joinedload(Request.requester_user))
                    .filter_by(wanted_material_id=wanted_material.id, status='Accepted')
                    .first())

    # ★ リクエスト送信者だけが最終完了できる
    if not accepted_req or accepted_req.requester_user_id != current_user.id:
        return jsonify({'status': 'error', 'message': '完了する権限がありません。'}), 403

    if wanted_material.completed:
        return jsonify({'status': 'success', 'message': '既に完了しています。'}), 200

    wanted_material.completed = True
    wanted_material.completed_at = datetime.now(JST)
    accepted_req.completed_at = wanted_material.completed_at
    accepted_req.status = 'Completed'

    db.session.commit()
    send_complete_push(accepted_req)
    return jsonify({'status': 'success', 'message': '希望材料の取引が最終完了しました。'}), 200

# ─── 取引【一次】完了（材料）──────────────────────────────
@api_requests_bp.route("/pre_complete_material/<int:material_id>", methods=['POST'])
@jwt_required()
def pre_complete_material(material_id: int):
    current_user = get_current_user()
    material = Material.query.get_or_404(material_id)

    # 承諾済みリクエストを取得
    accepted_req = (Request.query
                    .options(joinedload(Request.requester_user))
                    .filter_by(material_id=material.id, status='Accepted')
                    .first())

    # 一次完了できるのは「承諾側 (= requested_user)」のみ
    if not accepted_req or accepted_req.requested_user_id != current_user.id:
        return jsonify({'status': 'error', 'message': '一次完了する権限がありません。'}), 403

    # 既に立っていれば何もしない
    if material.pre_completed:
        return jsonify({'status': 'success', 'message': '既に一次完了されています。'}), 200

    material.pre_completed = True
    material.pre_completed_at = datetime.now(JST)
    db.session.commit()
    send_precomplete_push(accepted_req)

    return jsonify({'status': 'success', 'message': '材料の取引が一次完了しました。'}), 200

# ─── 取引【一次】完了（希望材料）─────────────────────────
@api_requests_bp.route("/pre_complete_wanted/<int:request_id>", methods=["POST"])
@jwt_required()
def pre_complete_wanted(request_id: int):
    accepted_req = Request.query.get_or_404(request_id)
    current_user = get_current_user()
    wanted = accepted_req.wanted_material

    if not accepted_req or accepted_req.requested_user_id != current_user.id:
        return jsonify({'status': 'error', 'message': '一次完了する権限がありません。'}), 403

    if wanted.pre_completed:
        return jsonify({'status': 'success', 'message': '既に一次完了されています。'}), 200

    wanted.pre_completed = True
    wanted.pre_completed_at = datetime.now(JST)
    db.session.commit()
    send_precomplete_push(accepted_req)

    return jsonify({'status': 'success', 'message': '希望材料の取引が一次完了しました。'}), 200

# ─── リクエストキャンセル ─────────────────────────────
@api_requests_bp.route("/cancel_request/<int:request_id>", methods=['POST'])
@jwt_required()
def cancel_request(request_id):
    current_user = get_current_user()
    req_obj = Request.query.get_or_404(request_id)

    logger.debug(
        f"Cancel request endpoint: Request ID {request_id}, current_user.id: {current_user.id}, "
        f"req_obj.requester_user_id: {req_obj.requester_user_id}, req_obj.status: {req_obj.status}"
    )

    if req_obj.requester_user_id != current_user.id:
        logger.debug("キャンセル権限がありません。")
        return jsonify({'status': 'error', 'message': 'リクエストを取り消す権限がありません。'}), 403
    if req_obj.status != 'Pending':
        logger.debug(f"キャンセル不可: 現在のリクエスト状態は {req_obj.status} です。")
        return jsonify({'status': 'error', 'message': 'キャンセルできるのは保留中のリクエストのみです。'}), 400

    related_material = req_obj.material  # Material に紐づくリクエストならここに入る

    req_obj.status = 'Rejected'
    # ★ cancel でも rejected_at を埋める（存在しないモデルなら落とさない）
    if hasattr(req_obj, "rejected_at"):
        req_obj.rejected_at = datetime.now(JST)
    db.session.commit()
    log_user_activity(
        current_user.id,
        'リクエスト取り消し',
        f'ユーザーがリクエストID: {request_id} を取り消しました。',
        request.remote_addr,
        request.user_agent.string,
        'N/A'
    )

    response = {
        'status': 'success',
        'message': 'リクエストを取り消しました。',
    }

    # Material に紐づくリクエストだった場合は、統計情報も返す
    if related_material is not None:
        stats = _get_material_request_stats(related_material, requester_user_id=current_user.id)
        response.update(stats)

    return jsonify(response), 200

@api_requests_bp.route("/sent_requests_give", methods=['GET'])
@jwt_required()
def get_sent_requests_give():
    """
    現在のユーザーが送信した「提供材料リクエスト」を取得するエンドポイント。
    Request テーブルから、requester_user_id == current_user.id かつ
    material_id が NOT NULL のレコードを取得します。

    追加で以下も返す（フロントが状態判定しやすいように）:
      - give_material.pre_completed / give_material.completed
      - top-level material_pre_completed / material_completed
      - （任意）top-level material_is_matched / material_matched_* など
    """
    current_user = get_current_user()

    sent_requests = (
        Request.query
        .options(
            joinedload(Request.material).joinedload(Material.owner),
        )
        .filter(
            Request.requester_user_id == current_user.id,
            Request.material_id.isnot(None)
        )
        .order_by(Request.requested_at.desc())
        .all()
    )

    # --- material_id ごとに「現在のマッチ（Accepted/Completed）」を集計（任意だけど便利） ---
    material_ids = sorted({r.material_id for r in sent_requests if r.material_id is not None})

    matched_map = {}  # material_id -> {'request_id': int, 'status': str}
    if material_ids:
        rows = (
            db.session.query(
                Request.material_id,
                Request.id,
                Request.status,
            )
            .filter(
                Request.material_id.in_(material_ids),
                Request.status.in_(["Accepted", "Completed"])
            )
            .all()
        )

        # Completed を優先（あれば Completed を採用、なければ Accepted）
        for material_id, req_id, status in rows:
            if material_id is None or req_id is None:
                continue

            existing = matched_map.get(material_id)
            if existing is None:
                matched_map[material_id] = {"request_id": req_id, "status": str(status)}
                continue

            # 優先順位: Completed > Accepted
            if existing["status"] != "Completed" and str(status) == "Completed":
                matched_map[material_id] = {"request_id": req_id, "status": "Completed"}
            elif existing["status"] == str(status) and req_id > existing["request_id"]:
                matched_map[material_id] = {"request_id": req_id, "status": str(status)}

    result = []
    for req in sent_requests:
        req_dict = req.to_dict()

        # ★ Rejected もフロントが確実に拾えるように明示
        req_dict.update({
            "is_rejected": (req.status == "Rejected"),
            "rejected_at": (req.rejected_at.isoformat() if getattr(req, "rejected_at", None) else None),
        })

        mat = req.material
        if mat:
            # Material 側の一次完了／完了フラグ
            material_pre_completed = bool(getattr(mat, "pre_completed", False))
            material_completed = bool(getattr(mat, "completed", False))

            # “現在のマッチ”情報（Accepted/Completed が存在するか）
            matched_info = matched_map.get(mat.id)
            material_is_matched = matched_info is not None
            material_matched_request_id = matched_info["request_id"] if matched_info else None
            material_matched_status = matched_info["status"] if matched_info else None

            # Material dict
            mat_dict = mat.to_dict()

            # owner(User) も入れる（画像URL正規化つき）
            mat_dict['user'] = user_to_dict(mat.owner) if mat.owner else None

            # give_material 内に状態を同梱（フロントが取りやすい）
            mat_dict.update({
                "is_matched": material_is_matched,
                "matched_request_id": material_matched_request_id,
                "matched_status": material_matched_status,
                "pre_completed": material_pre_completed,
                "completed": material_completed,
            })

            req_dict['give_material'] = mat_dict

            # ★トップレベルにも同じ情報を付与（フロント判定が一気にラク）
            req_dict.update({
                "material_is_matched": material_is_matched,
                "material_matched_request_id": material_matched_request_id,
                "material_matched_status": material_matched_status,
                "material_pre_completed": material_pre_completed,
                "material_completed": material_completed,
            })

        result.append(req_dict)

    return jsonify(result), 200

# ─── 送信した希望材料リクエスト取得エンドポイント ─────────────────────────────
@api_requests_bp.route("/sent_requests_wanted", methods=['GET'])
@jwt_required()
def get_sent_requests_wanted():
    """
    現在のユーザーが送信した希望材料リクエストを取得するエンドポイント。
    リクエストテーブルから、requester_user_id が現在のユーザーで、wanted_material_id が存在するリクエストを返します。
    """
    current_user = get_current_user()
    sent_requests = Request.query.filter(
        Request.requester_user_id == current_user.id,
        Request.wanted_material_id.isnot(None),
        Request.status == "Pending"
    ).all()

    result = []
    for req in sent_requests:
        req_dict = req.to_dict()
        if req.wanted_material:
            req_dict['wanted_material'] = wanted_material_to_dict(req.wanted_material)
        result.append(req_dict)
    return jsonify(result), 200

@api_requests_bp.route("/received_requests_give", methods=['GET'])
@jwt_required()
def get_received_requests_give():
    """
    現在のユーザーが受信した「提供材料のリクエスト」を取得するエンドポイント。
    リクエストテーブルから、requested_user_id == current_user.id かつ
    material_id が NOT NULL のレコードを返します。

    追加で以下も返す（親画面で状態判定できるように）:
      - material_is_matched: 資材がマッチ済みか（Accepted/Completed が存在）
      - material_matched_request_id / material_matched_status: 資材の“現在のマッチ”のリクエストIDと状態
      - is_this_request_matched: この req が“現在のマッチ”本人か
      - material_pre_completed / material_completed: 資材の一次完了／完全完了フラグ
    """
    current_user = get_current_user()

    received_requests = (
        Request.query
        .options(
            joinedload(Request.material).joinedload(Material.owner),
            joinedload(Request.requester_user),
        )
        .filter(
            Request.requested_user_id == current_user.id,
            Request.material_id.isnot(None)
        )
        .all()
    )

    # --- 資材IDごとに「現在のマッチ（Accepted/Completed）」を集計 ---
    material_ids = sorted({r.material_id for r in received_requests if r.material_id is not None})

    matched_map = {}  # material_id -> {'request_id': int, 'status': str}
    if material_ids:
        rows = (
            db.session.query(
                Request.material_id,
                Request.id,
                Request.status,
            )
            .filter(
                Request.material_id.in_(material_ids),
                Request.status.in_(["Accepted", "Completed"])
            )
            .all()
        )

        # Completed を優先（あれば Completed を採用、なければ Accepted）
        for material_id, req_id, status in rows:
            if material_id is None or req_id is None:
                continue

            existing = matched_map.get(material_id)
            if existing is None:
                matched_map[material_id] = {"request_id": req_id, "status": str(status)}
                continue

            # 優先順位: Completed > Accepted
            if existing["status"] != "Completed" and str(status) == "Completed":
                matched_map[material_id] = {"request_id": req_id, "status": "Completed"}
            elif existing["status"] == str(status) and req_id > existing["request_id"]:
                # 同じステータスなら最新っぽい方（idが大きい方）を採用
                matched_map[material_id] = {"request_id": req_id, "status": str(status)}

    result = []
    for req in received_requests:
        req_dict = req.to_dict()

        # ★ Rejected もフロントが確実に拾えるように明示
        req_dict.update({
            "is_rejected": (req.status == "Rejected"),
            "rejected_at": (req.rejected_at.isoformat() if getattr(req, "rejected_at", None) else None),
        })

        # 資材の状態フラグ（pre/complete は Material 側）
        mat = req.material
        material_id = req.material_id
        matched_info = matched_map.get(material_id) if material_id is not None else None

        material_is_matched = matched_info is not None
        material_matched_request_id = matched_info["request_id"] if matched_info else None
        material_matched_status = matched_info["status"] if matched_info else None
        is_this_request_matched = (
            True if (matched_info and req.id == matched_info["request_id"]) else False
        )

        material_pre_completed = bool(getattr(mat, "pre_completed", False)) if mat else False
        material_completed = bool(getattr(mat, "completed", False)) if mat else False

        # Material 情報を辞書化（必要ならここにフラグも同梱）
        if mat:
            mat_dict = material_to_dict(mat)
            mat_dict.update({
                "is_matched": material_is_matched,
                "matched_request_id": material_matched_request_id,
                "matched_status": material_matched_status,
                "pre_completed": material_pre_completed,
                "completed": material_completed,
            })
            req_dict["give_material"] = mat_dict

        # リクエスト送信者
        if req.requester_user:
            req_dict["requester_user"] = {
                "id": req.requester_user.id,
                "email": req.requester_user.email,
                "company_name": req.requester_user.company_name,
                "prefecture": req.requester_user.prefecture,
                "city": req.requester_user.city,
                "address": req.requester_user.address,
                "business_structure": req.requester_user.business_structure,
                "industry": req.requester_user.industry,
                "job_title": req.requester_user.job_title,
                "image": _normalize_image_url(
                    getattr(req.requester_user, "image", None)
                    or getattr(req.requester_user, "image_url", None)
                ),
            }

        # ★このAPIだけで判定できるように “トップレベル” にも同じ情報を付与
        req_dict.update({
            "material_is_matched": material_is_matched,
            "material_matched_request_id": material_matched_request_id,
            "material_matched_status": material_matched_status,
            "is_this_request_matched": is_this_request_matched,
            "material_pre_completed": material_pre_completed,
            "material_completed": material_completed,
        })

        result.append(req_dict)

    return jsonify(result), 200

def material_to_dict(mat):
    """
    Material（あげる資材）を辞書化する補助関数
    """
    mat_dict = mat.to_dict()
    # owner ユーザー情報を付加する例（GiveMaterialの user フィールド相当）
    if mat.owner:
        mat_dict['user'] = user_to_dict(mat.owner)
    return mat_dict

@api_requests_bp.route("/received_requests_wanted", methods=['GET'])
@jwt_required()
def get_received_requests_wanted():
    """
    現在のユーザーが受信した希望材料リクエストを取得するエンドポイント。
    リクエストテーブルから、requested_user_id が現在のユーザーで、wanted_material_id が存在するリクエストを返します。
    """
    current_user = get_current_user()
    received_requests = Request.query.filter(
        Request.requested_user_id == current_user.id,
        Request.wanted_material_id.isnot(None)
    ).all()

    result = []
    for req in received_requests:
        req_dict = req.to_dict()
        if req.wanted_material:
            req_dict['wanted_material'] = wanted_material_to_dict(req.wanted_material)
        # リクエスト送信者情報も追加（to_dict() メソッドが定義されていない場合は個別にパースしてください）
        if req.requester_user:
            # ここでは仮に requester_user の情報も辞書化するものとする
            req_dict['requester_user'] = {
                'id': req.requester_user.id,
                'email': req.requester_user.email,
                'company_name': req.requester_user.company_name,
                'prefecture': req.requester_user.prefecture,
                'city': req.requester_user.city,
                'address': req.requester_user.address,
                'business_structure': req.requester_user.business_structure,
                'industry': req.requester_user.industry,
                'job_title': req.requester_user.job_title,
            }
        result.append(req_dict)
    return jsonify(result), 200



# ================================================================
# 未完了マッチ（Material）   /api/requests/incomplete_matches_material
# ================================================================
@api_requests_bp.route("/incomplete_matches_material", methods=['GET'])
@jwt_required()
def get_incomplete_matches_material():
    cu = get_current_user()

    # ① 当事者だけを含む Accepted Request を素材ごとに一意にする
    accq = (db.session.query(Request)
            .filter(Request.status == 'Accepted',
                    or_(Request.requester_user_id == cu.id,
                        Request.requested_user_id == cu.id)))

    # 📢 デバッグ：どんな Request が取れているか全部出力
    logger.debug('▼▼ Accepted Request (Material) for user %s ▼▼', cu.id)
    for r in accq.all():
        logger.debug(
            '  ReqID=%s  mat=%s  requester=%s  requested=%s',
            r.id, r.material_id, r.requester_user_id, r.requested_user_id
        )
    logger.debug('▲▲ END Accepted Request (Material) ▲▲')

    acc = accq.with_entities(Request.material_id).distinct().subquery()

    mats = (Material.query
            .join(acc, acc.c.material_id == Material.id)
            .filter(Material.deleted == False,
                    Material.completed == False)
            .all())

    def to_dict(mat: Material):
        # 1) 役割判定
        roles = Request.get_roles_for_material(mat, cu.id)

        # 2) この Material に紐づく Accepted Request を 1 件取得
        acc_req = (Request.query
                   .options(joinedload(Request.requester_user),
                            joinedload(Request.requested_user))
                   .filter_by(material_id=mat.id, status='Accepted')
                   .first())

        chat = {}
        if acc_req:
            partner = (acc_req.requested_user if roles['is_sender']
                       else acc_req.requester_user)
            if partner:
                cid, tok, pn = get_or_create_conversation_and_token(cu, partner)
                chat = {'conversation_id': cid, 'chat_token': tok, 'partner_name': pn}

        # 📢 デバッグ：roles の判定結果
        logger.debug(
            'MAT %s  sender=%s receiver=%s pre=%s fin=%s',
            mat.id, roles['is_sender'], roles['is_receiver'],
            mat.pre_completed, mat.completed
        )

        return {
            'id'            : mat.id,
            'type'          : mat.type,
            'wood_type'     : mat.wood_type,
            'board_material_type': mat.board_material_type,
            'panel_type'    : mat.panel_type,
            'size_1'        : mat.size_1,
            'size_2'        : mat.size_2,
            'size_3'        : mat.size_3,
            'quantity'      : mat.quantity,
            'deadline'      : mat.deadline.isoformat() if mat.deadline else None,
            'matched_at'    : mat.matched_at.isoformat() if mat.matched_at else None,
            'm_prefecture'  : mat.m_prefecture or (mat.owner.prefecture if mat.owner else ''),
            'm_city'        : mat.m_city       or (mat.owner.city       if mat.owner else ''),
            'm_address'     : mat.m_address    or (mat.owner.address    if mat.owner else ''),
            'exclude_weekends': mat.exclude_weekends,
            'note'          : mat.note or '',
            'pre_completed' : mat.pre_completed,
            'completed'     : mat.completed,
            'acc_request_id': acc_req.id if acc_req else None,
            **roles,
            **chat,
        }

    return jsonify([to_dict(m) for m in mats]), 200

# ──────────────────────────────────────────────
# 会話を取得し、無ければ作成してトークンを返すユーティリティ
# ──────────────────────────────────────────────
def get_or_create_conversation_and_token(user_a: User, user_b: User):
    """
    user_a = 現在のユーザ（トークンを発行する当事者）
    user_b = 相手ユーザ
    戻り値  (conversation_id, chat_token, partner_name)
    """
    convo = (Conversation.query.filter(
                ((Conversation.user1_id == user_a.id) & (Conversation.user2_id == user_b.id)) |
                ((Conversation.user1_id == user_b.id) & (Conversation.user2_id == user_a.id))
            )
            .filter_by(is_hidden=False)
            .first())

    if convo is None:
        convo = Conversation(user1_id=user_a.id, user2_id=user_b.id)
        db.session.add(convo)
        db.session.commit()

    token = create_access_token(identity=user_a.id)
    partner_name = (user_b.contact_name or user_b.company_name or user_b.email)
    return convo.id, token, partner_name

# ================================================================
# 未完了マッチ（WantedMaterial） /api/requests/incomplete_matches_wanted
# ================================================================
@api_requests_bp.route("/incomplete_matches_wanted", methods=['GET'])
@jwt_required()
def get_incomplete_matches_wanted():
    cu = get_current_user()

    accq = (db.session.query(Request)
            .filter(Request.status == 'Accepted',
                    or_(Request.requester_user_id == cu.id,
                        Request.requested_user_id == cu.id)))

    # 📢 デバッグ：Wanted 用 Accepted Request 一覧
    logger.debug('▼▼ Accepted Request (Wanted) for user %s ▼▼', cu.id)
    for r in accq.all():
        logger.debug(
            '  ReqID=%s  wanted=%s  requester=%s  requested=%s',
            r.id, r.wanted_material_id, r.requester_user_id, r.requested_user_id
        )
    logger.debug('▲▲ END Accepted Request (Wanted) ▲▲')

    acc = accq.with_entities(Request.wanted_material_id).distinct().subquery()

    wanted = (WantedMaterial.query
              .join(acc, acc.c.wanted_material_id == WantedMaterial.id)
              .filter(WantedMaterial.deleted == False,
                      WantedMaterial.completed == False)
              .all())

    def to_dict(wm: WantedMaterial):
        roles = Request.get_roles_for_wanted(wm, cu.id)

        acc_req = (Request.query
                   .options(joinedload(Request.requester_user),
                            joinedload(Request.requested_user))
                   .filter_by(wanted_material_id=wm.id, status='Accepted')
                   .first())

        chat = {}
        if acc_req:
            partner = (acc_req.requested_user if roles['is_sender']
                       else acc_req.requester_user)
            if partner:
                cid, tok, pn = get_or_create_conversation_and_token(cu, partner)
                chat = {'conversation_id': cid, 'chat_token': tok, 'partner_name': pn}
        # 📢 デバッグ：roles の判定結果
        logger.debug(
            'WANTED %s  sender=%s receiver=%s pre=%s fin=%s',
            wm.id, roles['is_sender'], roles['is_receiver'],
            wm.pre_completed, wm.completed
        )

        return {
            'id'            : wm.id,
            'type'          : wm.type,
            'wood_type'     : wm.wood_type,
            'board_material_type': wm.board_material_type,
            'panel_type'    : wm.panel_type,
            'size_1'        : wm.size_1,
            'size_2'        : wm.size_2,
            'size_3'        : wm.size_3,
            'quantity'      : wm.quantity,
            'deadline'      : wm.deadline.isoformat() if wm.deadline else None,
            'matched_at'    : wm.matched_at.isoformat() if wm.matched_at else None,
            'wm_prefecture' : wm.wm_prefecture or (wm.owner.prefecture if wm.owner else ''),
            'wm_city'       : wm.wm_city       or (wm.owner.city       if wm.owner else ''),
            'wm_address'    : wm.wm_address    or (wm.owner.address    if wm.owner else ''),
            'exclude_weekends': wm.exclude_weekends,
            'note'          : wm.note,
            'pre_completed' : wm.pre_completed,
            'completed'     : wm.completed,
            'acc_request_id': acc_req.id if acc_req else None,
            **roles,
            **chat,
        }

    return jsonify([to_dict(w) for w in wanted]), 200

# ───────────────────────────────────────────────
# 資材リクエスト拒否（材料 / Give）
#   URL: /api/requests/reject_request_material/<request_id>
# ───────────────────────────────────────────────
@api_requests_bp.route("/reject_request_material/<int:request_id>", methods=['POST'])
@jwt_required()
def reject_request_material(request_id):
    """提供資材リクエストを受信側が拒否する"""
    current_user = get_current_user()
    mat_req = Request.query.get_or_404(request_id)

    # ---------- 権限チェック ----------
    same_loc_ids = [
        u.id for u in User.query.filter(
            User.company_name == current_user.company_name,
            User.prefecture   == current_user.prefecture,
            User.city         == current_user.city,
            User.address      == current_user.address
        ).all()
    ]
    if mat_req.requested_user_id not in ([current_user.id] + same_loc_ids):
        return jsonify({'status': 'error', 'message': 'リクエストを拒否する権限がありません。'}), 403
    # Pending: 通常の拒否
    # Accepted: “マッチ後キャンセル”（一次完了前のみ）
    if mat_req.status not in ('Pending', 'Accepted'):
        return jsonify({'status': 'error', 'message': '拒否（キャンセル）できるのは保留中または承諾済みのリクエストのみです。'}), 400
    if mat_req.status == 'Accepted':
        mat = mat_req.material
        if mat is None:
            return jsonify({'status': 'error', 'message': '資材情報が見つかりません。'}), 400
        # 一次完了/最終完了後はキャンセル不可（仕様）
        if bool(getattr(mat, "pre_completed", False)) or bool(getattr(mat, "completed", False)):
            return jsonify({'status': 'error', 'message': '一次完了後はリクエストをキャンセルできません。'}), 400
        # 二重マッチが存在する場合の安全策（基本は accept 側で防ぐ）
        other_match = Request.query.filter(
            Request.material_id == mat_req.material_id,
            Request.status.in_(["Accepted", "Completed"]),
            Request.id != mat_req.id
        ).first()
        if other_match:
            return jsonify({'status': 'error', 'message': '他の承諾済みリクエストが存在するためキャンセルできません。'}), 400
    # -----------------------------------

    try:
        # ステータス更新
        mat_req.status      = 'Rejected'
        mat_req.rejected_at = datetime.now(JST)
        # “マッチ後キャンセル” の場合は、資材側の matched を戻す
        if mat_req.status == 'Rejected' and getattr(mat_req, "matched", None) is not None:
            # Request 側フラグがあるなら戻す（無ければ無視される）
            try:
                mat_req.matched = False
                mat_req.matched_at = None
            except Exception:
                pass
        mat = mat_req.material
        if mat is not None:
            try:
                mat.matched = False
                mat.matched_at = None
            except Exception:
                pass
        db.session.commit()

        # --- メール通知（送信者・拒否者） ---
        send_reject_request_material_email(    # 送信者へ「拒否された」通知
            requester = mat_req.requester_user,
            material  = mat_req.material,
            rejector  = current_user
        )
        send_reject_notification_material_email(  # 拒否者へ確認
            rejector = current_user,
            material = mat_req.material
        )

        # 操作ログ
        log_user_activity(
            current_user.id, '材料リクエスト拒否',
            f'ユーザーがリクエストID: {request_id} を拒否しました。',
            request.remote_addr, request.user_agent.string, 'N/A'
        )

        return jsonify({'status': 'success', 'message': 'リクエストを拒否しました。'}), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"材料リクエスト拒否エラー: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': 'リクエストの拒否に失敗しました。'}), 500



# ───────────────────────────────────────────────
# 資材リクエスト拒否（希望材料 / Wanted）
#   URL: /api/requests/reject_request_wanted/<request_id>
# ───────────────────────────────────────────────
@api_requests_bp.route("/reject_request_wanted/<int:request_id>", methods=['POST'])
@jwt_required()
def reject_request_wanted(request_id):
    """希望資材リクエストを受信側が拒否する"""
    current_user = get_current_user()
    wanted_req = Request.query.get_or_404(request_id)

    # ---------- 権限チェック ----------
    same_loc_ids = [
        u.id for u in User.query.filter(
            User.company_name == current_user.company_name,
            User.prefecture   == current_user.prefecture,
            User.city         == current_user.city,
            User.address      == current_user.address
        ).all()
    ]
    if wanted_req.requested_user_id not in ([current_user.id] + same_loc_ids):
        return jsonify({'status': 'error', 'message': 'リクエストを拒否する権限がありません。'}), 403
    if wanted_req.status != 'Pending':
        return jsonify({'status': 'error', 'message': '拒否できるのは保留中のリクエストのみです。'}), 400
    # -----------------------------------

    try:
        # ステータス更新
        wanted_req.status      = 'Rejected'
        wanted_req.rejected_at = datetime.now(JST)
        db.session.commit()

        # --- メール通知（送信者・拒否者） ---
        send_reject_request_wanted_email(    # 送信者へ「拒否された」通知
            requester       = wanted_req.requester_user,
            wanted_material = wanted_req.wanted_material,
            rejector        = current_user
        )
        send_reject_notification_wanted_email(  # 拒否者へ確認
            rejector        = current_user,
            wanted_material = wanted_req.wanted_material
        )

        # 操作ログ
        log_user_activity(
            current_user.id, '希望材料リクエスト拒否',
            f'ユーザーがリクエストID: {request_id} を拒否しました。',
            request.remote_addr, request.user_agent.string, 'N/A'
        )

        return jsonify({'status': 'success', 'message': 'リクエストを拒否しました。'}), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"希望材料リクエスト拒否エラー: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': 'リクエストの拒否に失敗しました。'}), 500

# ─── 資材ごとのリクエスト数取得 ─────────────────────────────
@api_requests_bp.route("/material_request_count/<int:material_id>", methods=['GET'])
@jwt_required(optional=True)
def get_material_request_count(material_id):
    """
    指定した Material のリクエスト状況を返すエンドポイント。
    ログイン済みなら「自分が Pending リクエストを出しているか」も含めて返す。
    """
    material = Material.query.get_or_404(material_id)
    user_id = get_jwt_identity()

    # ログインしていなくても _get_material_request_stats は動く（has_requested=False のまま）
    stats = _get_material_request_stats(material, requester_user_id=user_id)
    return jsonify(stats), 200
