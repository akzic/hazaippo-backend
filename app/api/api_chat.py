# app/api/api_chat.py

from flask import Blueprint, request, jsonify, url_for, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, create_access_token
from app.models import User, Conversation, Message, Material, WantedMaterial, Request
from app import db
from werkzeug.utils import secure_filename
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from urllib.parse import quote_plus
from datetime import datetime, timedelta
import pytz
import os
from uuid import uuid4

# ✅ S3 を使う（materials と統一）
from app.utils.s3_uploader import upload_file_to_s3, build_s3_url, convert_heic_to_jpeg

# FCM
from firebase_admin import messaging, exceptions as fb_exc

api_chat_bp = Blueprint("api_chat", __name__, url_prefix="/api/chat")
JST = pytz.timezone("Asia/Tokyo")

# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
def allowed_file(filename: str) -> bool:
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "heic", "heif"}
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def get_current_user():
    """JWT からユーザーIDを取得し、DB からユーザー情報をロードする"""
    user_id = get_jwt_identity()
    return User.query.get(user_id)

def _safe_dt_iso(dt):
    if not dt:
        return None
    try:
        return dt.isoformat()
    except Exception:
        return None

def _attachment_to_image_url(attachment_value: str | None):
    """
    Message.attachment が
    - https://... の場合はそのまま
    - S3 key の場合は build_s3_url で返す
    - /static/... のようなパスが入ってる場合はそのまま
    """
    if not attachment_value:
        return None
    v = str(attachment_value).strip()
    if not v:
        return None

    if v.startswith("http://") or v.startswith("https://"):
        return v

    # 旧方式：static パスが入る場合
    if v.startswith("/static/"):
        return v

    # S3 key
    return build_s3_url(v)

def message_to_chat_json(m: Message, current_user_id: int):
    """
    Flutter の ChatMessage.fromJson が読める形に揃える
    - created_at / sent_at
    - image_url
    - is_mine
    """
    ts = getattr(m, "timestamp", None) or getattr(m, "created_at", None)
    return {
        "id": m.id,
        "conversation_id": m.conversation_id,
        "sender_id": m.sender_id,
        "content": (m.content or "").strip(),
        "image_url": _attachment_to_image_url(getattr(m, "attachment", None)),
        "created_at": _safe_dt_iso(ts) or datetime.now(JST).isoformat(),
        "is_mine": bool(m.sender_id == current_user_id),
    }

# ─────────────────────────────────────────────
# ✅ NEW (Flutter互換) : messages list
# ─────────────────────────────────────────────
@api_chat_bp.route("/conversations/<int:conversation_id>/messages", methods=["GET"])
@jwt_required()
def get_messages_v2(conversation_id):
    """
    ✅ Flutter RequestListChatScreen が叩く
    GET /api/chat/conversations/<id>/messages
    """
    current_user_obj = get_current_user()
    conv = Conversation.query.get_or_404(conversation_id)

    if current_user_obj.id not in (conv.user1_id, conv.user2_id):
        return jsonify({"status": "error", "message": "Unauthorized."}), 403

    try:
        msgs = (
            Message.query
            .filter_by(conversation_id=conversation_id)
            .order_by(Message.timestamp.asc())
            .all()
        )

        messages_json = [message_to_chat_json(m, current_user_obj.id) for m in msgs]

        # Flutter は List or {messages:[...]} を許容してるが
        # Map で返しておく（拡張しやすい）
        return jsonify({
            "status": "success",
            "messages": messages_json
        }), 200

    except Exception as e:
        current_app.logger.error(f"[chat] get_messages_v2 error: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Failed to load messages."}), 500

# ─────────────────────────────────────────────
# ✅ NEW (Flutter互換) : send text message
# ─────────────────────────────────────────────
@api_chat_bp.route("/conversations/<int:conversation_id>/messages", methods=["POST"])
@jwt_required()
def post_message_v2(conversation_id):
    """
    ✅ Flutter RequestListChatScreen が叩く
    POST /api/chat/conversations/<id>/messages
    body: { "content": "..." }
    """
    current_user_obj = get_current_user()
    conv = Conversation.query.get_or_404(conversation_id)

    if current_user_obj.id not in (conv.user1_id, conv.user2_id):
        return jsonify({"status": "error", "message": "Unauthorized."}), 403

    data = request.get_json(silent=True) or {}
    content = (data.get("content") or data.get("message") or "").strip()

    if not content:
        return jsonify({"status": "error", "message": "content is required"}), 400

    try:
        new_msg = Message(
            conversation_id=conv.id,
            sender_id=current_user_obj.id,
            content=content,
            attachment=None
        )
        db.session.add(new_msg)

        # last_message 更新
        conv.last_message = content
        db.session.commit()

        # ✅ push（失敗してもOK）
        try:
            send_chat_push(
                sender_id=current_user_obj.id,
                sender_name=current_user_obj.contact_name,
                conversation_id=conv.id,
                message_text=content,
            )
        except Exception as push_e:
            current_app.logger.warning(f"[chat] push failed: {push_e}")

        return jsonify({
            "status": "success",
            "message": message_to_chat_json(new_msg, current_user_obj.id),
        }), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"[chat] post_message_v2 error: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Failed to send message."}), 500

# ─────────────────────────────────────────────
# ✅ NEW (Flutter互換) : send image message
# ─────────────────────────────────────────────
@api_chat_bp.route("/conversations/<int:conversation_id>/messages/image", methods=["POST"])
@jwt_required()
def post_image_message_v2(conversation_id):
    """
    ✅ Flutter RequestListChatScreen が叩く
    POST /api/chat/conversations/<id>/messages/image
    multipart: image
    """
    current_user_obj = get_current_user()
    conv = Conversation.query.get_or_404(conversation_id)

    if current_user_obj.id not in (conv.user1_id, conv.user2_id):
        return jsonify({"status": "error", "message": "Unauthorized."}), 403

    if "image" not in request.files:
        return jsonify({"status": "error", "message": "image is required"}), 400

    file = request.files["image"]
    if not file or file.filename == "":
        return jsonify({"status": "error", "message": "image is required"}), 400

    if not allowed_file(file.filename):
        return jsonify({"status": "error", "message": "invalid image extension"}), 400

    try:
        # ✅ HEIC/HEIF の場合は JPEG に変換してからアップ（表示できない事故を防ぐ）
        filename = secure_filename(file.filename)
        ext = os.path.splitext(filename)[1].lower()

        upload_target = file
        if ext in (".heic", ".heif"):
            jpeg_io, _ = convert_heic_to_jpeg(file)
            jpeg_io.seek(0)

            # werkzeug の FileStorage を作り直して S3 uploader に渡す
            from werkzeug.datastructures import FileStorage
            upload_target = FileStorage(
                stream=jpeg_io,
                filename=f"{uuid4().hex}.jpg",
                content_type="image/jpeg",
            )

        # ✅ S3へ保存（chat_attachments フォルダに入れる）
        image_key = upload_file_to_s3(upload_target, folder="chat_attachments")

        new_msg = Message(
            conversation_id=conv.id,
            sender_id=current_user_obj.id,
            content="",
            attachment=image_key,
        )
        db.session.add(new_msg)

        # last_message 更新
        conv.last_message = "[image]"
        db.session.commit()

        # ✅ push（失敗してもOK）
        try:
            send_chat_push(
                sender_id=current_user_obj.id,
                sender_name=current_user_obj.contact_name,
                conversation_id=conv.id,
                message_text="[image]",
            )
        except Exception as push_e:
            current_app.logger.warning(f"[chat] push failed: {push_e}")

        return jsonify({
            "status": "success",
            "message": message_to_chat_json(new_msg, current_user_obj.id),
        }), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"[chat] post_image_message_v2 error: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Failed to send image."}), 500

# ─────────────────────────────────────────────
# 旧API（残す：既存画面が壊れないように互換維持）
# ─────────────────────────────────────────────
@api_chat_bp.route("/conversations", methods=["GET"])
@jwt_required()
def get_conversations():
    """
    現在のユーザーが参加している非表示でない会話を返す。
    + matching済みのユーザー + 最終マッチ日時リスト
    """
    current_user_obj = get_current_user()

    latest_msg_subq = (
        db.session.query(
            Message.conversation_id,
            func.max(Message.timestamp).label("latest_at"),
        )
        .group_by(Message.conversation_id)
        .subquery()
    )

    conversations = (
        db.session.query(
            Conversation,
            func.coalesce(latest_msg_subq.c.latest_at, Conversation.created_at).label("latest_at"),
        )
        .outerjoin(latest_msg_subq, Conversation.id == latest_msg_subq.c.conversation_id)
        .filter(
            ((Conversation.user1_id == current_user_obj.id) | (Conversation.user2_id == current_user_obj.id))
            & (Conversation.is_hidden == False)
        )
        .order_by(func.coalesce(latest_msg_subq.c.latest_at, Conversation.created_at).desc())
        .all()
    )

    conversations_data = []
    for conv, latest_at in conversations:
        conversations_data.append(
            {
                "id": conv.id,
                "user1_id": conv.user1_id,
                "user2_id": conv.user2_id,
                "created_at": conv.created_at.isoformat(),
                "is_hidden": conv.is_hidden,
                "last_message": conv.last_message or "",
                "last_message_at": latest_at.isoformat() if latest_at else None,
            }
        )

    matched_materials_ids = db.session.query(Material.id).filter(Material.matched == True).subquery()
    matched_wanted_materials_ids = db.session.query(WantedMaterial.id).filter(WantedMaterial.matched == True).subquery()

    matched_requests = Request.query.filter(
        (
            (Request.requester_user_id == current_user_obj.id)
            | (Request.requested_user_id == current_user_obj.id)
        )
        & (
            (Request.material_id.in_(matched_materials_ids))
            | (Request.wanted_material_id.in_(matched_wanted_materials_ids))
        )
    ).all()

    user_ids = set()
    for req in matched_requests:
        if req.requester_user_id != current_user_obj.id:
            user_ids.add(req.requester_user_id)
        if req.requested_user_id != current_user_obj.id:
            user_ids.add(req.requested_user_id)

    users = User.query.filter(User.id.in_(user_ids)).all()

    user_with_last_matching = []
    for user in users:
        latest_request = (
            Request.query.filter(
                ((Request.requester_user_id == user.id) | (Request.requested_user_id == user.id))
                & (
                    (Request.material_id.in_(matched_materials_ids))
                    | (Request.wanted_material_id.in_(matched_wanted_materials_ids))
                )
            )
            .order_by(Request.requested_at.desc())
            .first()
        )
        last_matching_date = latest_request.requested_at if latest_request else None

        user_with_last_matching.append(
            {
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "company_name": user.company_name,
                    "contact_name": user.contact_name,
                },
                "last_matching_date": last_matching_date.isoformat() if last_matching_date else None,
            }
        )

    return jsonify(
        {"status": "success", "conversations": conversations_data, "users": user_with_last_matching}
    ), 200

@api_chat_bp.route("/conversation/<int:conversation_id>", methods=["GET"])
@jwt_required()
def get_conversation(conversation_id):
    current_user_obj = get_current_user()
    conv = Conversation.query.get_or_404(conversation_id)

    if current_user_obj.id not in (conv.user1_id, conv.user2_id):
        return jsonify({"status": "error", "message": "Unauthorized access."}), 403

    messages = (
        Message.query.filter_by(conversation_id=conv.id)
        .order_by(Message.timestamp.asc())
        .all()
    )
    messages_data = [m.to_dict() for m in messages]

    other_user = conv.user2 if conv.user1_id == current_user_obj.id else conv.user1
    other_user_data = {
        "id": other_user.id,
        "email": other_user.email,
        "contact_name": other_user.contact_name,
    }

    return jsonify(
        {
            "status": "success",
            "conversation": {
                "id": conv.id,
                "last_message": conv.last_message or "",
                "messages": messages_data,
                "other_user": other_user_data,
            },
        }
    ), 200

@api_chat_bp.route("/conversation/<int:conversation_id>", methods=["POST"])
@jwt_required()
def post_message(conversation_id):
    """
    旧: body {message, attachment}
    """
    current_user_obj = get_current_user()
    conversation = Conversation.query.get_or_404(conversation_id)

    if current_user_obj.id not in [conversation.user1_id, conversation.user2_id]:
        return jsonify({"status": "error", "message": "Unauthorized."}), 403

    data = request.get_json(silent=True) or {}
    message_content = (data.get("message") or "").strip()
    attachment = (data.get("attachment") or "").strip()

    if not (message_content or attachment):
        return jsonify({"status": "error", "message": "No message content provided."}), 400

    new_message = Message(
        conversation_id=conversation.id,
        sender_id=current_user_obj.id,
        content=message_content,
        attachment=attachment if attachment else None,
    )
    db.session.add(new_message)

    conversation.last_message = message_content if message_content else "[attachment]"
    db.session.commit()

    try:
        send_chat_push(
            sender_id=current_user_obj.id,
            sender_name=current_user_obj.contact_name,
            conversation_id=conversation.id,
            message_text=message_content or "[attachment]",
        )
    except Exception as e:
        current_app.logger.warning(f"Push notification failed: {e}")

    return jsonify(
        {
            "status": "success",
            "message_id": new_message.id,
            "timestamp": new_message.timestamp.isoformat(),
        }
    ), 200

def send_chat_push(sender_id, sender_name, conversation_id, message_text):
    """
    受信者（送信者以外）にチャット通知を送信する。
    users.device_tokens (ARRAY) を参照する前提。
    """
    convo = Conversation.query.get(conversation_id)
    if convo is None:
        current_app.logger.warning(f"[send_chat_push] conversation {conversation_id} not found")
        return

    receiver_id = convo.user2_id if sender_id == convo.user1_id else convo.user1_id
    if receiver_id is None:
        current_app.logger.warning("[send_chat_push] receiver could not be determined")
        return

    receiver = User.query.get(receiver_id)
    if receiver is None:
        current_app.logger.warning(f"[send_chat_push] user {receiver_id} not found")
        return

    tokens = list({t for t in (receiver.device_tokens or []) if t})
    if not tokens:
        current_app.logger.info(f"[send_chat_push] skipped: no token for user {receiver_id}")
        return

    # route（アプリ側の deep link 用）
    safe_name = quote_plus(sender_name or "", safe="")
    route = f"/chat?conversation_id={conversation_id}&user_name={safe_name}"

    payload_common = {
        "notification": messaging.Notification(
            title="新着メッセージ",
            body=f"{sender_name}: {message_text[:40]}",
        ),
        "data": {"route": route},
        "android": messaging.AndroidConfig(
            priority="high",
            notification=messaging.AndroidNotification(channel_id="default"),
        ),
        "apns": messaging.APNSConfig(
            payload=messaging.APNSPayload(
                aps=messaging.Aps(content_available=True, sound="default")
            ),
        ),
    }

    success, fail = 0, 0
    for tk in tokens:
        try:
            messaging.send(messaging.Message(token=tk, **payload_common))
            success += 1
        except fb_exc.FirebaseError as e:
            current_app.logger.warning(f"[send_chat_push] token_err={tk[:10]}… {e.code}")
            fail += 1
            if e.code in ("registration-token-not-registered", "invalid-argument"):
                try:
                    receiver.device_tokens.remove(tk)
                except Exception:
                    pass

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()

    current_app.logger.info(f"[send_chat_push] success={success}, failure={fail}")

@api_chat_bp.route("/start/<int:user_id>", methods=["POST"])
@jwt_required()
def start_conversation(user_id):
    current_user_obj = get_current_user()
    if user_id == current_user_obj.id:
        return jsonify({"status": "error", "message": "Cannot start a conversation with yourself."}), 400

    other_user = User.query.get_or_404(user_id)
    conversation = (
        Conversation.query.filter(
            ((Conversation.user1_id == current_user_obj.id) & (Conversation.user2_id == other_user.id))
            | ((Conversation.user1_id == other_user.id) & (Conversation.user2_id == current_user_obj.id))
        )
        .filter(Conversation.is_hidden == False)
        .first()
    )

    if not conversation:
        conversation = Conversation(user1_id=current_user_obj.id, user2_id=other_user.id)
        db.session.add(conversation)
        db.session.commit()

    return jsonify({"status": "success", "conversation_id": conversation.id}), 200

@api_chat_bp.route("/hide/<int:conversation_id>", methods=["POST"])
@jwt_required()
def hide_conversation(conversation_id):
    current_user_obj = get_current_user()
    conversation = Conversation.query.get_or_404(conversation_id)
    if current_user_obj.id not in [conversation.user1_id, conversation.user2_id]:
        return jsonify({"status": "error", "message": "Unauthorized."}), 403

    conversation.is_hidden = True
    db.session.commit()
    return jsonify({"status": "success", "message": "Conversation hidden successfully."}), 200

@api_chat_bp.route("/conversation_from_request/<int:request_id>", methods=["POST"])
@jwt_required()
def conversation_from_request(request_id):
    """
    既存仕様維持：
    - conversation_id
    - chat_token
    - user_name
    """
    current_user_obj = get_current_user()

    req_obj = Request.query.get_or_404(request_id)
    if current_user_obj.id not in (req_obj.requester_user_id, req_obj.requested_user_id):
        return jsonify({"status": "error", "message": "Unauthorized."}), 403

    other_user_id = (
        req_obj.requester_user_id
        if current_user_obj.id == req_obj.requested_user_id
        else req_obj.requested_user_id
    )
    other_user = User.query.get_or_404(other_user_id)

    conversation = (
        Conversation.query.filter(
            ((Conversation.user1_id == current_user_obj.id) & (Conversation.user2_id == other_user_id))
            | ((Conversation.user1_id == other_user_id) & (Conversation.user2_id == current_user_obj.id))
        )
        .filter_by(is_hidden=False)
        .first()
    )

    if conversation is None:
        conversation = Conversation(user1_id=current_user_obj.id, user2_id=other_user_id)
        db.session.add(conversation)
        db.session.commit()

    chat_token = create_access_token(identity=current_user_obj.id)

    return jsonify(
        {
            "status": "success",
            "conversation_id": conversation.id,
            "chat_token": chat_token,
            "user_name": other_user.contact_name or other_user.company_name or other_user.email,
        }
    ), 200
