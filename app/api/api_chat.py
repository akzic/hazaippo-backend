# app/api/api_chat.py

from flask import Blueprint, request, jsonify, url_for, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, create_access_token
from app.models import User, Conversation, Message, Material, WantedMaterial, Request
from app import db
from werkzeug.utils import secure_filename
import os
from datetime import datetime
import pytz
from app.blueprints.chat import send_chat_push
from sqlalchemy import func
from urllib.parse import quote_plus
from firebase_admin import messaging, exceptions as fb_exc
from datetime import timedelta

api_chat_bp = Blueprint('api_chat', __name__, url_prefix='/api/chat')
JST = pytz.timezone('Asia/Tokyo')

def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'heic'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_current_user():
    """JWT からユーザーIDを取得し、DB からユーザー情報をロードする"""
    user_id = get_jwt_identity()
    return User.query.get(user_id)

@api_chat_bp.route('/conversations', methods=['GET'])
@jwt_required()
def get_conversations():
    """
    現在のユーザーが参加している非表示でない会話を返す。
    それに加えて、matching済みのユーザー + 最終マッチ日時リストも返す。
    """
    current_user_obj = get_current_user()
    # ── 最新メッセージ時刻を求めるサブクエリ ──
    latest_msg_subq = (
        db.session.query(
            Message.conversation_id,
            func.max(Message.timestamp).label('latest_at')
        )
        .group_by(Message.conversation_id)
        .subquery()
    )

    # ── 会話を最新メッセージ順に取得 ──
    conversations = (
        db.session.query(
            Conversation,
            func.coalesce(latest_msg_subq.c.latest_at, Conversation.created_at).label('latest_at')
        )
        .outerjoin(latest_msg_subq, Conversation.id == latest_msg_subq.c.conversation_id)
        .filter(
            ((Conversation.user1_id == current_user_obj.id) | (Conversation.user2_id == current_user_obj.id)) &
            (Conversation.is_hidden == False)
        )
        .order_by(func.coalesce(latest_msg_subq.c.latest_at,Conversation.created_at).desc())
        .all()
    )

    conversations_data = []
    for conv, latest_at in conversations:
        # Conversationに .to_dict() があるなら活用してもOKだが、ここでは手動で組み立て
        conversations_data.append({
            'id': conv.id,
            'user1_id': conv.user1_id,
            'user2_id': conv.user2_id,
            'created_at': conv.created_at.isoformat(),
            'is_hidden': conv.is_hidden,
            'last_message': conv.last_message or '',
            'last_message_at': latest_at.isoformat()
        })

    # 以下は元コード: リクエストテーブルからマッチ済み材料のユーザー情報を取得
    matched_materials_ids = db.session.query(Material.id).filter(Material.matched == True).subquery()
    matched_wanted_materials_ids = db.session.query(WantedMaterial.id).filter(WantedMaterial.matched == True).subquery()

    matched_requests = Request.query.filter(
        (
            (Request.requester_user_id == current_user_obj.id) |
            (Request.requested_user_id == current_user_obj.id)
        ) & (
            (Request.material_id.in_(matched_materials_ids)) |
            (Request.wanted_material_id.in_(matched_wanted_materials_ids))
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
        latest_request = Request.query.filter(
            ((Request.requester_user_id == user.id) | (Request.requested_user_id == user.id)) &
            ((Request.material_id.in_(matched_materials_ids)) | (Request.wanted_material_id.in_(matched_wanted_materials_ids)))
        ).order_by(Request.requested_at.desc()).first()
        last_matching_date = latest_request.requested_at if latest_request else None
        user_with_last_matching.append({
            'user': {
                'id': user.id,
                'email': user.email,
                'company_name': user.company_name,
                'contact_name': user.contact_name,
            },
            'last_matching_date': last_matching_date.isoformat() if last_matching_date else None
        })

    return jsonify({
        'status': 'success',
        'conversations': conversations_data,
        'users': user_with_last_matching
    }), 200

@api_chat_bp.route('/conversation/<int:conversation_id>', methods=['GET'])
@jwt_required()
def get_conversation(conversation_id):
    """
    指定会話IDのメッセージ一覧 + 相手情報を返す。
    relationship の lazy が何であっても動くようにメッセージは
    Message テーブルから直接取得する。
    """
    current_user = get_current_user()
    conv = Conversation.query.get_or_404(conversation_id)

    if current_user.id not in (conv.user1_id, conv.user2_id):
        return jsonify({'status': 'error', 'message': 'Unauthorized access.'}), 403

    # ✅ 直接クエリで取得し昇順ソート
    messages = (Message.query
                .filter_by(conversation_id=conv.id)
                .order_by(Message.timestamp.asc())
                .all())
    messages_data = [m.to_dict() for m in messages]

    other_user = conv.user2 if conv.user1_id == current_user.id else conv.user1
    other_user_data = {
        'id'           : other_user.id,
        'email'        : other_user.email,
        'contact_name' : other_user.contact_name
    }

    return jsonify({
        'status': 'success',
        'conversation': {
            'id'          : conv.id,
            'last_message': conv.last_message or '',
            'messages'    : messages_data,
            'other_user'  : other_user_data
        }
    }), 200

@api_chat_bp.route('/conversation/<int:conversation_id>', methods=['POST'])
@jwt_required()
def post_message(conversation_id):
    """
    指定した会話に対して新しいメッセージを送信し、送信相手へ FCM プッシュ通知を送る。
    """
    current_user_obj = get_current_user()
    conversation = Conversation.query.get_or_404(conversation_id)

    if current_user_obj.id not in [conversation.user1_id, conversation.user2_id]:
        return jsonify({'status': 'error', 'message': 'Unauthorized.'}), 403

    data = request.get_json() or {}
    message_content = (data.get('message') or '').strip()
    attachment = (data.get('attachment') or '').strip()

    if not (message_content or attachment):
        return jsonify({'status': 'error', 'message': 'No message content provided.'}), 400

    new_message = Message(
        conversation_id=conversation.id,
        sender_id=current_user_obj.id,
        content=message_content,
        attachment=attachment if attachment else None
    )
    db.session.add(new_message)

    # last_message を更新
    conversation.last_message = message_content if message_content else '[attachment]'
    db.session.commit()  # ここで確定してから通知

    # ───── FCM プッシュ通知 ─────
    try:
        send_chat_push(
            sender_id=current_user_obj.id,
            sender_name=current_user_obj.contact_name,  # ← 修正: name → contact_name
            conversation_id=conversation.id,
            message_text=message_content or '[attachment]'
        )
    except Exception as e:
        current_app.logger.warning(f'Push notification failed: {e}')

    # ────────────────────────────────
    # ✅ 成功レスポンスを返す
    # ────────────────────────────────
    return jsonify({
        'status'     : 'success',
        'message_id' : new_message.id,
        'timestamp'  : new_message.timestamp.isoformat()
    }), 200

def send_chat_push(
    sender_id: int,
    sender_name: str,
    conversation_id: int,
    message_text: str,
) -> None:
    """
    受信者（＝送信者以外）にチャット通知を送信する。
    * users.device_tokens (ARRAY) を直接参照。
    * data.route に `/chat?conversation_id=xx&user_name=yy` を入れる。
    """

    # ── 会話を取得して受信者を判定 ─────────────────────────
    convo: Conversation | None = Conversation.query.get(conversation_id)
    if convo is None:
        current_app.logger.warning(f"[send_chat_push] conversation {conversation_id} not found")
        return

    receiver_id: int | None = (
        convo.user2_id if sender_id == convo.user1_id else convo.user1_id
    )
    if receiver_id is None:
        current_app.logger.warning("[send_chat_push] receiver could not be determined")
        return

    # ── 受信者のデバイストークン (ARRAY) を取得 ─────────────
    receiver: User | None = User.query.get(receiver_id)
    if receiver is None:
        current_app.logger.warning(f"[send_chat_push] user {receiver_id} not found")
        return

    # ── 有効トークンを抽出（重複排除） ──────────────
    tokens = list({t for t in (receiver.device_tokens or []) if t})
    if not tokens:
        current_app.logger.info(f"[send_chat_push] skipped: no token for user {receiver_id}")
        return

    # ── チャット用 JWT を Conversation 経由で生成 ──────────────
    #    生成と同時に conversations.chat_token に保存
    chat_token = convo.gen_chat_token(receiver_id)
    db.session.commit()   # トークン更新を確定

    # ── route 生成（ユーザー名＋chat_token を URL エンコード）────────
    safe_name  = quote_plus(sender_name or "", safe="")
    safe_token = quote_plus(chat_token,        safe="")
    route = (
        f"/chat?"
        f"conversation_id={conversation_id}"
        f"&user_name={safe_name}"
        f"&chat_token={safe_token}"
    )

    # ── ここから 1 token ずつ送る (404 /batch を回避) ──
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
            # 無効トークンなら DB から除去
            if e.code in ("registration-token-not-registered", "invalid-argument"):
                receiver.device_tokens.remove(tk)
    db.session.commit()
    current_app.logger.info(f"[send_chat_push] success={success}, failure={fail}")

@api_chat_bp.route('/start/<int:user_id>', methods=['POST'])
@jwt_required()
def start_conversation(user_id):
    """
    指定したユーザーとの会話を開始する。既存の会話がなければ新規作成し、会話IDを返す。
    """
    current_user_obj = get_current_user()
    if user_id == current_user_obj.id:
        return jsonify({'status': 'error', 'message': 'Cannot start a conversation with yourself.'}), 400

    other_user = User.query.get_or_404(user_id)
    conversation = Conversation.query.filter(
        ((Conversation.user1_id == current_user_obj.id) & (Conversation.user2_id == other_user.id)) |
        ((Conversation.user1_id == other_user.id) & (Conversation.user2_id == current_user_obj.id))
    ).filter(Conversation.is_hidden == False).first()

    if not conversation:
        conversation = Conversation(user1_id=current_user_obj.id, user2_id=other_user.id)
        db.session.add(conversation)
        db.session.commit()

    return jsonify({'status': 'success', 'conversation_id': conversation.id}), 200

@api_chat_bp.route('/upload', methods=['POST'])
@jwt_required()
def upload_file():
    """
    チャット用添付ファイルのアップロード処理。許可された画像ファイルのみ受け付ける。
    """
    current_user_obj = get_current_user()
    if 'file' not in request.files:
        return jsonify({'error': 'No file part in the request.'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected.'}), 400
    if not allowed_file(file.filename):
        allowed_ext = ', '.join(allowed_file.__globals__['ALLOWED_EXTENSIONS'])
        return jsonify({'error': f'Invalid file extension. Allowed: {allowed_ext}'}), 400

    file.seek(0, os.SEEK_END)
    file_length = file.tell()
    file.seek(0)
    max_size = 5 * 1024 * 1024  # 5MB
    if file_length > max_size:
        return jsonify({'error': 'File size exceeds 5MB.'}), 400

    upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'chat_attachments')
    try:
        os.makedirs(upload_folder, exist_ok=True)
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        filename = f"{current_user_obj.id}_{timestamp}_{filename}"
        file_path = os.path.join(upload_folder, filename)
        file.save(file_path)
    except Exception as e:
        current_app.logger.error(f"Error saving file: {e}", exc_info=True)
        return jsonify({'error': 'Error uploading file.'}), 500

    file_url = url_for('static', filename=f'uploads/chat_attachments/{filename}')
    return jsonify({'file_url': file_url}), 200

@api_chat_bp.route('/hide/<int:conversation_id>', methods=['POST'])
@jwt_required()
def hide_conversation(conversation_id):
    """
    指定した会話を非表示（ソフトデリート）にする
    """
    current_user_obj = get_current_user()
    conversation = Conversation.query.get_or_404(conversation_id)
    if current_user_obj.id not in [conversation.user1_id, conversation.user2_id]:
        return jsonify({'status': 'error', 'message': 'Unauthorized.'}), 403

    conversation.is_hidden = True
    db.session.commit()
    return jsonify({'status': 'success', 'message': 'Conversation hidden successfully.'}), 200

@api_chat_bp.route('/conversation_from_request/<int:request_id>', methods=['POST'])
@jwt_required()
def conversation_from_request(request_id):
    """
    1. 指定リクエストが自分に関わるものか確認
    2. 相手ユーザーを特定
    3. 既存の Conversation を探し、無ければ新規作成
    4. 会話ID・チャット用トークン・相手名を返却
    """
    current_user = get_current_user()

    # --- 1) リクエスト取得 & 権限チェック -------------------
    req_obj = Request.query.get_or_404(request_id)
    if current_user.id not in (req_obj.requester_user_id, req_obj.requested_user_id):
        return jsonify({'status': 'error', 'message': 'Unauthorized.'}), 403

    # --- 2) 相手ユーザー決定 -------------------------------
    other_user_id = (
        req_obj.requester_user_id
        if current_user.id == req_obj.requested_user_id
        else req_obj.requested_user_id
    )
    other_user = User.query.get_or_404(other_user_id)

    # --- 3) 会話取得 or 生成 ------------------------------
    conversation = Conversation.query.filter(
        ((Conversation.user1_id == current_user.id) & (Conversation.user2_id == other_user_id)) |
        ((Conversation.user1_id == other_user_id) & (Conversation.user2_id == current_user.id))
    ).filter_by(is_hidden=False).first()

    if conversation is None:
        conversation = Conversation(user1_id=current_user.id, user2_id=other_user_id)
        db.session.add(conversation)
        db.session.commit()

    # --- 4) チャット用トークン生成 --------------------------
    chat_token = create_access_token(identity=current_user.id)

    return jsonify({
        'status'         : 'success',
        'conversation_id': conversation.id,
        'chat_token'     : chat_token,
        'user_name'      : other_user.contact_name or other_user.company_name or other_user.email
    }), 200
