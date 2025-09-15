# app/blueprints/utils.py

from app import db, mail
from app.models import Log
import os
from flask import flash, request, current_app, url_for
from flask_mail import Message
import logging

def log_user_activity(user_id, action, details, ip_address, device_info, location='N/A'):
    """
    ユーザーアクティビティをデータベースおよびログファイルに記録する関数。

    Parameters:
        user_id (int): ユーザーのID。
        action (str): アクション名（例：'ログイン'）。
        details (str): アクションの詳細説明。
        ip_address (str): ユーザーのIPアドレス。
        device_info (str): ユーザーのデバイス情報。
        location (str): ユーザーの位置情報（デフォルトは'N/A'）。
    """
    # データベースに保存
    log_entry = Log(
        user_id=user_id,
        action=action,
        details=details,
        ip_address=ip_address,
        device_info=device_info,
        location=location
    )
    db.session.add(log_entry)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"データベースへのログ保存に失敗しました: {e}")
        flash('ユーザーアクティビティの記録中にエラーが発生しました。', 'danger')

    # ファイルにログを保存
    user_activity_logger = logging.getLogger('user_activity')
    log_message = (
        f"UserID: {user_id}, "
        f"Action: {action}, "
        f"Details: {details}, "
        f"IP: {ip_address}, "
        f"Device: {device_info}, "
        f"Location: {location}"
    )
    user_activity_logger.info(log_message)

def send_email_safe(msg):
    """
    メールを安全に送信する関数。送信に失敗した場合はロールバックし、エラーメッセージを表示する。

    Parameters:
        msg (Message): Flask-MailのMessageオブジェクト。

    Returns:
        bool: 送信が成功した場合はTrue、失敗した場合はFalse。
    """
    try:
        mail.send(msg)
    except Exception as e:
        current_app.logger.error(f"メール送信エラー: {e}")
        db.session.rollback()
        flash('メールの送信に失敗しました。後でもう一度試してください。', 'danger')
        return False
    return True

def send_reset_email(user, for_mobile: bool = False):
    """
    パスワードリセットメールを送信する共通ユーティリティ
    ------------------------------------------------------------------
    今は HTTPS 未整備のため **必ず Web 版 URL** を送る。
    Deep Link はコメントアウトしておき、将来 for_mobile=True で復活可能。
    """
    token = user.get_reset_token()

    # ────────────────────────────────────────────────────────────────
    # 1) リセット URL 生成
    # ────────────────────────────────────────────────────────────────
    # if for_mobile:
    #     # ===== DeepLink（カスタムスキーム）が必要になったらコメント解除 =====
    #     reset_url = f"hazaippo://reset_password?token={token}"
    # else:
    #     reset_url = url_for('auth.reset_token', token=token, _external=True, _scheme="https")
    # ----------------------------------------------------------------
    # いまは常に Web 版 (HTTP) を使用
    reset_url = url_for('auth.reset_token', token=token,
                        _external=True, _scheme="http")   # ← 証明書取得後 https へ

    # ────────────────────────────────────────────────────────────────
    # 2) メール本文
    # ────────────────────────────────────────────────────────────────
    body = f'''{user.contact_name} さん

アカウントのパスワードリセットのリクエストを受け取りました。

以下のリンクをクリックして、新しいパスワードを設定してください。

{reset_url}

このリンクは30分間有効です。期限が過ぎると、このリンクは使用できなくなりますので、その場合は再度パスワードリセットのリクエストを行ってください。

もしこのリクエストに覚えがない場合は、このメールを無視してください。
疑わしいアクティビティがあった場合はすぐにご連絡ください。

---------------------------------
ZAI株式会社  システムチーム
メール: support@zai-ltd.com
電話: 052-990-3452
住所: 〒466-0064 愛知県名古屋市昭和区鶴舞１丁目２−３２ STATION Ai 4階
---------------------------------
'''

    # ────────────────────────────────────────────────────────────────
    # 3) 送信
    # ────────────────────────────────────────────────────────────────
    msg = Message(
        subject='パスワードリセットのご案内 - はざいっぽ',
        sender=os.environ.get('EMAIL_USER'),
        recipients=[user.email],
        body=body,
    )

    try:
        return send_email_safe(msg)
    except Exception as e:
        current_app.logger.error("Password-reset mail send failed: %s", e, exc_info=True)
        return False

def send_welcome_email(user_email):
    """
    新規ユーザー登録時に送信するウェルカムメールを送信する関数。

    Parameters:
        user_email (str): 送信先のユーザーのメールアドレス。

    Returns:
        bool: 送信が成功した場合はTrue、失敗した場合はFalse。
    """
    msg = Message(
        'ユーザーが登録されました。- はざいっぽ',
        sender=os.environ.get('EMAIL_USER'),
        recipients=[user_email]
    )
    msg.body = '''\

この度ははざいっぽにご登録いただき、誠にありがとうございます。
アカウントが正常に作成されました。


今後も末永くご愛顧賜りますようお願い申し上げます。

何かご不明点やご質問がございましたら、お気軽にお問い合わせください。

よろしくお願いいたします。

はざいっぽ チーム

---------------------------------

ZAI株式会社
システムチーム
メール: support@zai-ltd.com
電話: 052-990-3452
住所: 〒466-0064 愛知県名古屋市昭和区鶴舞１丁目２−３２ STATION Ai 4階

---------------------------------
'''
    return send_email_safe(msg)
