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

def send_reset_email(user):
    """
    パスワードリセット用のメールを送信する関数。

    Parameters:
        user (User): パスワードリセットを行うユーザーオブジェクト。

    Returns:
        bool: 送信が成功した場合はTrue、失敗した場合はFalse。
    """
    token = user.get_reset_token()
    reset_url = url_for('auth.reset_token', token=token, _external=True)
    msg = Message(
        'パスワードリセットのリクエスト - はざいっぽ',
        sender=os.environ.get('EMAIL_USER'),
        recipients=[user.email]
    )
    msg.body = f'''{user.contact_name} さん,

アカウントのパスワードリセットのリクエストを受け取りました。

以下のリンクをクリックして、新しいパスワードを設定してください。

{reset_url}

このリンクは30分間有効です。期限が過ぎると、このリンクは使用できなくなりますので、その場合は再度パスワードリセットのリクエストを行ってください。

もしこのリクエストに覚えがない場合は、このメールを無視してください。あなたのアカウントのセキュリティを確保するため、疑わしいアクティビティがあった場合はすぐに私たちにご連絡ください。

よろしくお願いいたします。

はざいっぽ チーム

---------------------------------

ZAI株式会社
システムチーム
メール: support@zai-ltd.com
電話: 052-990-3452
住所: 〒455-0068 愛知県名古屋市港区土古町1丁目51番10号

---------------------------------
'''
    return send_email_safe(msg)

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
住所: 〒455-0068 愛知県名古屋市港区土古町1丁目51番10号

---------------------------------
'''
    return send_email_safe(msg)
