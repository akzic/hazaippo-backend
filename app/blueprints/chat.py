# app/blueprints/chat.py

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from app.models import User, Conversation, Message, Material, WantedMaterial, Request
from app import db
from werkzeug.utils import secure_filename
import os
from datetime import datetime
import pytz
from firebase_admin import messaging

chat_bp = Blueprint('chat', __name__)

# 許可されたファイル拡張子（画像のみ）：'heic' を追加
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'heic'}

JST = pytz.timezone('Asia/Tokyo')

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@chat_bp.route('/conversations')
@login_required
def conversations():
    """
    現在のユーザーが参加している会話のうち、非表示になっていないものを取得し、
    そのままHTMLテンプレートへ渡す。
    また、マッチングしているユーザー情報を取得し user_with_last_matching としてテンプレに渡す。
    """
    # 現在のユーザーが参加している会話のうち、非表示になっていないもののみ取得
    conversations = Conversation.query.filter(
        ((Conversation.user1_id == current_user.id) | (Conversation.user2_id == current_user.id)) &
        (Conversation.is_hidden == False)
    ).order_by(Conversation.created_at.desc()).all()

    # matched=True の Material と WantedMaterial のIDをサブクエリで取得
    matched_materials_ids = db.session.query(Material.id).filter(Material.matched == True).subquery()
    matched_wanted_materials_ids = db.session.query(WantedMaterial.id).filter(WantedMaterial.matched == True).subquery()

    # Requestテーブルから関連するリクエストを取得
    matched_requests = Request.query.filter(
        (Request.material_id.in_(matched_materials_ids)) |
        (Request.wanted_material_id.in_(matched_wanted_materials_ids))
    ).all()

    # 現在のユーザー以外のユーザーIDを収集
    user_ids = set()
    for req in matched_requests:
        if req.requester_user_id != current_user.id:
            user_ids.add(req.requester_user_id)
        if req.requested_user_id != current_user.id:
            user_ids.add(req.requested_user_id)

    # ユーザーリストを取得
    users = User.query.filter(User.id.in_(user_ids)).all()

    # 各ユーザーの最新のマッチング日時を取得
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

    return render_template(
        'chat/conversations.html',
        conversations=conversations,
        users=user_with_last_matching
    )


@chat_bp.route('/conversation/<int:conversation_id>', methods=['GET', 'POST'])
@login_required
def conversation_view(conversation_id):
    """
    指定した会話IDの詳細ページ。
    GET: 会話内容を表示
    POST: 新しいメッセージを送信し、conversation.last_message を更新
    """
    conversation = Conversation.query.get_or_404(conversation_id)
    # 現在のユーザーが会話の参加者であるか確認
    if current_user.id not in [conversation.user1_id, conversation.user2_id]:
        flash('この会話にアクセスする権限がありません。', 'danger')
        return redirect(url_for('chat.conversations'))

    if request.method == 'POST':
        # テキストメッセージまたは画像送信（attachment）を処理
        message_content = request.form.get('message', '').strip()
        attachment = request.form.get('attachment', '').strip()

        # message_content か attachment のどちらかがあればメッセージ追加
        if message_content or attachment:
            new_message = Message(
                conversation_id=conversation.id,
                sender_id=current_user.id,
                content=message_content,
                attachment=attachment if attachment else None
            )
            db.session.add(new_message)

            # ★ conversation.last_message を更新
            if message_content:
                conversation.last_message = message_content
            else:
                conversation.last_message = '[attachment]'
            db.session.commit()

        return redirect(url_for('chat.conversation_view', conversation_id=conversation.id))

    # GETメソッド: メッセージ一覧を取得して表示
    messages = conversation.messages.order_by(Message.timestamp.asc()).all()
    # 自分以外のユーザーを会話相手として取得
    other_user = conversation.user2 if conversation.user1_id == current_user.id else conversation.user1
    return render_template(
        'chat/conversation.html',
        conversation=conversation,
        messages=messages,
        other_user=other_user
    )


@chat_bp.route('/start/<int:user_id>', methods=['GET', 'POST'])
@login_required
def start_conversation(user_id):
    """
    指定したユーザーとの会話を開始する。
    既存の会話がなければ新規作成し、会話IDを返す。
    """
    other_user = User.query.get_or_404(user_id)
    if other_user.id == current_user.id:
        flash('自分自身との会話は開始できません。', 'warning')
        return redirect(url_for('chat.conversations'))

    # 既存の会話があるか確認（非表示でないもの）
    conversation = Conversation.query.filter(
        ((Conversation.user1_id == current_user.id) & (Conversation.user2_id == other_user.id)) |
        ((Conversation.user1_id == other_user.id) & (Conversation.user2_id == current_user.id))
    ).filter(Conversation.is_hidden == False).first()

    if not conversation:
        conversation = Conversation(user1_id=current_user.id, user2_id=other_user.id)
        db.session.add(conversation)
        db.session.commit()

    return redirect(url_for('chat.conversation_view', conversation_id=conversation.id))


@chat_bp.route('/upload', methods=['POST'])
@login_required
def upload_file():
    """
    チャット用のファイルアップロード（HTMLフォームからのPOST）。
    JSONでファイルURLを返す。
    """
    if 'file' not in request.files:
        return jsonify({'error': 'ファイルがリクエストに含まれていません。'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'ファイルが選択されていません。'}), 400
    if not allowed_file(file.filename):
        allowed_ext = ', '.join(ALLOWED_EXTENSIONS)
        return jsonify({'error': f'許可されていないファイル形式です。アップロードできる形式: {allowed_ext}'}), 400

    # ファイルサイズチェック：5MBまで
    file.seek(0, os.SEEK_END)
    file_length = file.tell()
    file.seek(0)
    max_size = 5 * 1024 * 1024  # 5MB
    if file_length > max_size:
        return jsonify({'error': 'アップロードできるファイルサイズは5MBまでです。'}), 400

    upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'chat_attachments')
    try:
        os.makedirs(upload_folder, exist_ok=True)
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        filename = f"{current_user.id}_{timestamp}_{filename}"
        file_path = os.path.join(upload_folder, filename)
        file.save(file_path)
    except Exception as e:
        current_app.logger.error(f"ファイル保存中にエラーが発生しました: {e}", exc_info=True)
        return jsonify({'error': 'ファイルのアップロード中にエラーが発生しました。'}), 500

    file_url = url_for('static', filename=f'uploads/chat_attachments/{filename}')
    return jsonify({'file_url': file_url}), 200


# 会話の非表示（ソフトデリート）
@chat_bp.route('/hide/<int:conversation_id>', methods=['POST'])
@login_required
def hide_conversation(conversation_id):
    """
    指定した会話を非表示状態にする。
    """
    conversation = Conversation.query.get_or_404(conversation_id)
    if current_user.id not in [conversation.user1_id, conversation.user2_id]:
        flash('この会話にアクセスする権限がありません。', 'danger')
        return redirect(url_for('chat.conversations'))
    
    conversation.is_hidden = True
    db.session.commit()
    flash('会話を非表示にしました。', 'success')
    return redirect(url_for('chat.conversations'))

def send_chat_push(user_id, conversation_id, message_text):
    """
    新しいチャットメッセージ送信時に相手へプッシュ通知を送る。
    :param user_id: 送信者 ID
    :param conversation_id: 会話 ID
    :param message_text: メッセージ本文
    """
    # 1. 受信者を特定
    convo = Conversation.query.get(conversation_id)
    if not convo:
        return
    target_user_id = (convo.user2_id if convo.user1_id == user_id
                      else convo.user1_id)

    # 2. FCM トークン取得（device_tokens は配列）
    target_user = User.query.get(target_user_id)
    tokens = (
        target_user.device_tokens
        if target_user and target_user.device_tokens
        else []
    )
    if not tokens:
        return

    # 3. 通知タイトル・本文を生成
    # ──────────────────────────────
    # ① 送信者名の決定ロジックを修正
    #    contact_name › company_name › email（@前）› “誰か” の順で採用
    # ──────────────────────────────
    sender = User.query.get(user_id)
    sender_display = (
        sender.contact_name
        or sender.company_name
        or (sender.email.split("@")[0] if sender and sender.email else "誰か")
    ) if sender else "誰か"

    title = f"{sender_display} から新しいメッセージ"
    body = message_text or "新しいメッセージがあります"

    # 4. すべての端末にループ送信
    for tkn in tokens:
        message = messaging.Message(
            token=tkn,
            notification=messaging.Notification(title=title, body=body),
            data={
                "conversation_id": str(conversation_id),
                "route": "/chat"
            }
        )
        try:
            response = messaging.send(message)
            print(f"FCM 送信成功: {response}")
        except Exception as e:
            print(f"FCM 送信エラー: {e}")
