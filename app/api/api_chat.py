# app/api/api_chat.py

from flask import Blueprint, request, jsonify, current_app, url_for
from flask_login import login_required, current_user
from app.models import User, Conversation, Message, Material, WantedMaterial, Request
from app import db, socketio
from werkzeug.utils import secure_filename
import os
from datetime import datetime
import pytz
from app.blueprints.email_notifications import send_new_message_email  # メール通知関数をインポート

api_chat_bp = Blueprint('api_chat', __name__, url_prefix='/api/chat')

# 許可されたファイル拡張子のセット（画像のみ）
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'HEIC'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@api_chat_bp.route('/conversations', methods=['GET'])
@login_required
def get_conversations():
    """
    現在のユーザーが参加している全ての会話を取得します。
    """
    conversations = Conversation.query.filter(
        (Conversation.user1_id == current_user.id) | 
        (Conversation.user2_id == current_user.id)
    ).order_by(Conversation.created_at.desc()).all()

    # materialsとwanted_materialsでmatched=Trueのものを取得
    matched_materials_ids = db.session.query(Material.id).filter(Material.matched == True).subquery()
    matched_wanted_materials_ids = db.session.query(WantedMaterial.id).filter(WantedMaterial.matched == True).subquery()

    # requestsテーブルから関連するリクエストを取得
    matched_requests = Request.query.filter(
        (Request.material_id.in_(matched_materials_ids)) |
        (Request.wanted_material_id.in_(matched_wanted_materials_ids))
    ).all()

    # 現在のユーザーではないユーザーIDを取得
    user_ids = set()
    for req in matched_requests:
        if req.requester_user_id != current_user.id:
            user_ids.add(req.requester_user_id)
        if req.requested_user_id != current_user.id:
            user_ids.add(req.requested_user_id)

    # ユーザーリストを取得
    users = User.query.filter(User.id.in_(user_ids)).all()
    users_data = [{'id': user.id, 'email': user.email, 'company_name': user.company_name} for user in users]

    conversations_data = []
    for convo in conversations:
        other_user_id = convo.user2_id if convo.user1_id == current_user.id else convo.user1_id
        conversations_data.append({
            'id': convo.id,
            'other_user_id': other_user_id,
            'other_user_email': User.query.get(other_user_id).email,
            'created_at': convo.created_at.strftime('%Y-%m-%d %H:%M:%S')
        })

    return jsonify({
        'success': True,
        'data': {
            'conversations': conversations_data,
            'users': users_data
        }
    }), 200

@api_chat_bp.route('/conversations/<int:conversation_id>', methods=['GET'])
@login_required
def get_conversation(conversation_id):
    """
    指定された会話の詳細とメッセージを取得します。
    """
    conversation = Conversation.query.get_or_404(conversation_id)

    # 現在のユーザーが会話の一員であるか確認
    if current_user.id not in [conversation.user1_id, conversation.user2_id]:
        return jsonify({'success': False, 'message': 'この会話にアクセスする権限がありません。'}), 403

    # メッセージを取得
    messages = conversation.messages.order_by(Message.timestamp.asc()).all()
    messages_data = []
    for msg in messages:
        messages_data.append({
            'id': msg.id,
            'sender_id': msg.sender_id,
            'sender_email': User.query.get(msg.sender_id).email,
            'content': msg.content,
            'attachment': msg.attachment,
            'timestamp': msg.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'edited': msg.edited,
            'edited_at': msg.edited_at.strftime('%Y-%m-%d %H:%M:%S') if msg.edited_at else None
        })

    return jsonify({
        'success': True,
        'data': {
            'conversation': {
                'id': conversation.id,
                'user1_id': conversation.user1_id,
                'user2_id': conversation.user2_id,
                'created_at': conversation.created_at.strftime('%Y-%m-%d %H:%M:%S')
            },
            'messages': messages_data
        }
    }), 200

@api_chat_bp.route('/conversations/start/<int:user_id>', methods=['POST'])
@login_required
def start_conversation(user_id):
    """
    指定されたユーザーとの新しい会話を開始します。既存の会話があればそれを返します。
    """
    other_user = User.query.get_or_404(user_id)

    if other_user.id == current_user.id:
        return jsonify({'success': False, 'message': '自分自身との会話は開始できません。'}), 400

    # 既存の会話がないか確認
    conversation = Conversation.query.filter(
        ((Conversation.user1_id == current_user.id) & (Conversation.user2_id == other_user.id)) |
        ((Conversation.user1_id == other_user.id) & (Conversation.user2_id == current_user.id))
    ).first()

    if not conversation:
        # 新しい会話を作成
        conversation = Conversation(user1_id=current_user.id, user2_id=other_user.id)
        db.session.add(conversation)
        db.session.commit()

    return jsonify({
        'success': True,
        'message': '会話を開始しました。',
        'data': {
            'conversation': {
                'id': conversation.id,
                'user1_id': conversation.user1_id,
                'user2_id': conversation.user2_id,
                'created_at': conversation.created_at.strftime('%Y-%m-%d %H:%M:%S')
            }
        }
    }), 200

@api_chat_bp.route('/upload', methods=['POST'])
@login_required
def upload_file():
    """
    ファイルをアップロードします。許可されたファイル形式のみ受け付けます。
    """
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'ファイルがリクエストに含まれていません。'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'ファイルが選択されていません。'}), 400
    if not allowed_file(file.filename):
        allowed_ext = ', '.join(ALLOWED_EXTENSIONS)
        return jsonify({'success': False, 'error': f'許可されていないファイル形式です。アップロードできる形式: {allowed_ext}'}), 400
    # ファイルサイズのバリデーションはFlaskのMAX_CONTENT_LENGTHで処理される
    if file:
        # アップロードフォルダのパスを動的に取得
        upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'chat_attachments')
        os.makedirs(upload_folder, exist_ok=True)

        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        filename = f"{current_user.id}_{timestamp}_{filename}"
        file_path = os.path.join(upload_folder, filename)
        try:
            file.save(file_path)
        except Exception as e:
            current_app.logger.error(f"ファイル保存中にエラーが発生しました: {e}")
            return jsonify({'success': False, 'error': 'ファイルのアップロード中にエラーが発生しました。'}), 500
        file_url = url_for('static', filename=f'uploads/chat_attachments/{filename}', _external=True)
        return jsonify({'success': True, 'file_url': file_url}), 200
    else:
        return jsonify({'success': False, 'error': 'ファイルのアップロードに失敗しました。'}), 400

# SocketIOイベントは通常APIではなくリアルタイム通信として扱います。
# そのため、`api_chat.py`ではなく元の`chat.py`に保持することをお勧めします。

# もしAPI経由でメッセージを送信・編集したい場合は、以下のようなエンドポイントを追加できます。

@api_chat_bp.route('/messages/send', methods=['POST'])
@login_required
def send_message_api():
    """
    API経由でメッセージを送信します。
    """
    data = request.get_json()
    conversation_id = data.get('conversation_id')
    content = data.get('content', '')
    attachment = data.get('attachment', None)

    if not conversation_id:
        return jsonify({'success': False, 'message': 'conversation_id が必要です。'}), 400

    conversation = Conversation.query.get(conversation_id)
    if not conversation:
        return jsonify({'success': False, 'message': '会話が見つかりません。'}), 404

    # 現在のユーザーが会話の一員であるか確認
    if current_user.id not in [conversation.user1_id, conversation.user2_id]:
        return jsonify({'success': False, 'message': 'この会話にメッセージを送信する権限がありません。'}), 403

    # 新しいメッセージを作成
    message = Message(
        conversation_id=conversation_id,
        sender_id=current_user.id,
        content=content,
        attachment=attachment,
        timestamp=datetime.now(pytz.timezone('Asia/Tokyo'))
    )
    db.session.add(message)
    db.session.commit()

    # クライアントに送信するメッセージデータ
    message_data = {
        'id': message.id,
        'sender_id': message.sender_id,
        'sender_email': current_user.email,
        'content': message.content,
        'attachment': message.attachment,
        'timestamp': message.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
        'edited': message.edited,
        'edited_at': message.edited_at.strftime('%Y-%m-%d %H:%M:%S') if message.edited_at else None
    }

    # 相手ユーザーにメール通知を送信
    other_user_id = conversation.user2_id if current_user.id == conversation.user1_id else conversation.user1_id
    other_user = User.query.get(other_user_id)
    if other_user and other_user.email:
        success = send_new_message_email(other_user.email, current_user.company_name)
        if not success:
            current_app.logger.error(f"{other_user.email} への新しいメッセージのメール送信に失敗しました。")

    # リアルタイム通知を受信者に送信
    if other_user:
        socketio.emit('new_message_notification', {
            'conversation_id': conversation_id,
            'sender_id': current_user.id,
            'sender_email': current_user.email,
            'message_id': message.id
        }, room=f'user_{other_user_id}')

    return jsonify({
        'success': True,
        'message': 'メッセージが送信されました。',
        'data': {
            'message': message_data
        }
    }), 200

@api_chat_bp.route('/messages/edit', methods=['PUT'])
@login_required
def edit_message_api():
    """
    API経由でメッセージを編集します。
    """
    data = request.get_json()
    message_id = data.get('message_id')
    new_content = data.get('new_content', '')

    if not message_id:
        return jsonify({'success': False, 'message': 'message_id が必要です。'}), 400

    message = Message.query.get(message_id)
    if not message:
        return jsonify({'success': False, 'message': 'メッセージが見つかりません。'}), 404

    # メッセージの送信者が現在のユーザーであるか確認
    if message.sender_id != current_user.id:
        return jsonify({'success': False, 'message': 'このメッセージを編集する権限がありません。'}), 403

    message.content = new_content
    message.edited = True
    message.edited_at = datetime.now(pytz.timezone('Asia/Tokyo'))
    db.session.commit()

    # 更新されたメッセージデータ
    updated_message = {
        'id': message.id,
        'content': message.content,
        'edited': message.edited,
        'edited_at': message.edited_at.strftime('%Y-%m-%d %H:%M:%S') if message.edited_at else None
    }

    # メッセージが属する会話
    conversation = Conversation.query.get(message.conversation_id)
    room = f'conversation_{conversation.id}'
    socketio.emit('update_message', updated_message, room=room)

    return jsonify({
        'success': True,
        'message': 'メッセージが編集されました。',
        'data': {
            'message': updated_message
        }
    }), 200
