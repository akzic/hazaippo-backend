# app/blueprints/email_notifications.py

from flask import Blueprint, render_template, current_app
from flask_mail import Message
import os
from app import mail

email_notifications = Blueprint('email_notifications', __name__)

def send_email_safe(msg):
    try:
        mail.send(msg)
        return True
    except Exception as e:
        # エラーログを記録するか、必要に応じて処理を追加
        current_app.logger.error(f"Error sending email: {e}")
        return False

def send_welcome_email(user_email):
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

def send_material_registration_email(user_email, material):
    msg = Message(
        '余った資材の登録が完了しました - はざいっぽ',
        sender=os.environ.get('EMAIL_USER'),
        recipients=[user_email]
    )
    msg.body = f'''\
余った資材の登録をいただき、誠にありがとうございました。
以下の情報にて登録が完了いたしましたことをご報告申し上げます。

【登録情報】

材料名：{material.type}
サイズ：{material.size_1}×{material.size_2}×{material.size_3}
場所：{material.location}
数量：{material.quantity}個
コメント：{material.note}

ご登録いただいた資材は、すぐに表示され、必要としている方々にマッチングされます。

何かご不明点やご質問がございましたら、どうぞお気軽にお問い合わせください。

今後とも「THE-IRIYO」をどうぞよろしくお願い申し上げます。

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

def send_wanted_material_registration_email(user_email, wanted_material):
    msg = Message(
        '欲しい資材の登録が完了しました - はざいっぽ',
        sender=os.environ.get('EMAIL_USER'),
        recipients=[user_email]
    )
    msg.body = f'''\
欲しい資材の登録をいただき、誠にありがとうございました。
以下の情報にて登録が完了しましたことをご報告申し上げます。

【登録情報】

材料名：{wanted_material.type}
サイズ：{wanted_material.size_1}×{wanted_material.size_2}×{wanted_material.size_3}
場所：{wanted_material.location}
数量：{wanted_material.quantity}個
コメント：{wanted_material.note}

ご登録いただいた資材は、すぐに表示され、必要としている方々にマッチングされます。

何かご不明点やご質問がございましたら、どうぞお気軽にお問い合わせください。

今後とも「THE-IRIYO」をどうぞよろしくお願い申し上げます。

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

def send_request_email(user_email):
    msg = Message(
        'リクエストの送信が完了しました - はざいっぽ',
        sender=os.environ.get('EMAIL_USER'),
        recipients=[user_email]
    )
    msg.body = '''\
資材のリクエストを送信しました。

資材のリクエストが承諾されるまでお待ちください。

もしこのリクエストに覚えがない場合は、このメールを無視してください。あなたのアカウントのセキュリティを確保するため、疑わしいアクティビティがあった場合はすぐに私たちにご連絡ください。

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

def send_new_request_received_email(user_email):
    msg = Message(
        '新たなリクエストが届きました - はざいっぽ',
        sender=os.environ.get('EMAIL_USER'),
        recipients=[user_email]
    )
    msg.body = '''\
資材のリクエストが届きました。

「はざいっぽ」ログイン後のダッシュボード画面にて、内容を確認の上、リクエストを受けてください。

もしこのリクエストに覚えがない場合は、このメールを無視してください。あなたのアカウントのセキュリティを確保するため、疑わしいアクティビティがあった場合はすぐにご連絡ください。

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

def send_accept_request_email(requester, material, accepted_user):
    msg = Message(
        'リクエストが承認されました - はざいっぽ',
        sender=os.environ.get('EMAIL_USER'),
        recipients=[requester.email]
    )
    msg.body = f'''\
リクエストが承認されました。

下記情報にて連絡を取り合い、受け渡しを完了させてください。

法人名（屋号）: {accepted_user.company_name}
法人住所: {accepted_user.prefecture} {accepted_user.city} {accepted_user.address}
業種: {accepted_user.industry}
職種: {accepted_user.job_title}
担当者氏名: {accepted_user.contact_name}
担当者メールアドレス: {accepted_user.email}
担当者電話番号: {accepted_user.contact_phone}
材料名: {material.type}
サイズ: {material.size_1}×{material.size_2}×{material.size_3}
場所: {material.location}
数量: {material.quantity}個
コメント: {material.note}

■受け渡しの完了後、「はざいっぽ」ログイン後のダッシュボード画面にて、対象の取引の完了ボタンを押してください。

もしこのリクエストに覚えがない場合は、このメールを直ちに削除してください。あなたのアカウントのセキュリティを確保するため、疑わしいアクティビティがあった場合はすぐにご連絡ください。

よろしくお願いいたします。

はざいっぽ チーム
'''
    return send_email_safe(msg)

def send_accept_request_to_sender_email(requester, material, accepted_user):
    msg = Message(
        'リクエストを送信した予約が承認されました - はざいっぽ',
        sender=os.environ.get('EMAIL_USER'),
        recipients=[accepted_user.email]
    )
    msg.body = f'''\
リクエストを送信した予約が承認されました。

下記情報にて連絡を取り合い、取引を完了させてください。

法人名（屋号）: {requester.company_name}
法人住所: {requester.prefecture} {requester.city} {requester.address}
業種: {requester.industry}
職種: {requester.job_title}
担当者氏名: {requester.contact_name}
担当者メールアドレス: {requester.email}
担当者電話番号: {requester.contact_phone}
材料名: {material.type}
サイズ: {material.size_1}×{material.size_2}×{material.size_3}
場所: {material.location}
数量: {material.quantity}個
コメント: {material.note}

もしこのリクエストに覚えがない場合は、このメールを直ちに削除してください。アカウントのセキュリティを確保するため、疑わしいアクティビティがあった場合はすぐにご連絡ください。

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

def send_accept_request_wanted_email(requester, wanted_material, accepted_user):
    msg = Message(
        '欲しい資材がマッチしました - はざいっぽ',
        sender=os.environ.get('EMAIL_USER'),
        recipients=[requester.email]
    )
    msg.body = f'''\
欲しい資材がマッチしました。

下記情報にて連絡を取り合い、受け渡しを完了させてください。

法人名（屋号）: {accepted_user.company_name}
法人住所: {accepted_user.prefecture} {accepted_user.city} {accepted_user.address}
業種: {accepted_user.industry}
職種: {accepted_user.job_title}
担当者氏名: {accepted_user.contact_name}
担当者メールアドレス: {accepted_user.email}
担当者電話番号: {accepted_user.contact_phone}
材料名: {wanted_material.type}
サイズ: {wanted_material.size_1}×{wanted_material.size_2}×{wanted_material.size_3}
場所: {wanted_material.location}
数量: {wanted_material.quantity}個
コメント: {wanted_material.note}

■受け渡しの完了後、「はざいっぽ」ログイン後のダッシュボード画面にて、対象の取引の完了ボタンを押してください。

もしこのリクエストに覚えがない場合は、このメールを直ちに削除してください。あなたのアカウントのセキュリティを確保するため、疑わしいアクティビティがあった場合はすぐにご連絡ください。

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

def send_accept_request_wanted_to_sender_email(requester, wanted_material, accepted_user):
    msg = Message(
        'リクエストを送信した資材がマッチしました - はざいっぽ',
        sender=os.environ.get('EMAIL_USER'),
        recipients=[accepted_user.email]
    )
    msg.body = f'''\
リクエストを送信した資材がマッチしました。

下記情報にて連絡を取り合い、取引を完了させてください。

法人名（屋号）: {requester.company_name}
法人住所: {requester.prefecture} {requester.city} {requester.address}
業種: {requester.industry}
職種: {requester.job_title}
担当者氏名: {requester.contact_name}
担当者メールアドレス: {requester.email}
担当者電話番号: {requester.contact_phone}
材料名: {wanted_material.type}
サイズ: {wanted_material.size_1}×{wanted_material.size_2}×{wanted_material.size_3}
場所: {wanted_material.location}
数量: {wanted_material.quantity}個
コメント: {wanted_material.note}

もしこのリクエストに覚えがない場合は、このメールを直ちに削除してください。あなたのアカウントのセキュリティを確保するため、疑わしいアクティビティがあった場合はすぐにご連絡ください。

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

def send_reservation_confirmation_email(user_email, date, time_slot):
    msg = Message(
        '予約確認 - はざいっぽ',
        sender=os.environ.get('EMAIL_USER'),
        recipients=[user_email]
    )
    msg.body = f'''\
下記の日程でターミナルの予約が確定しました。

【予約情報】
日付：{date}
時間：{time_slot}

予約内容を確認の上、スケジュールに合わせてご準備ください。

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

def send_lecture_confirmation_email(lecturer_email, date, time_slot):
    msg = Message(
        'レクチャー予約確認 - はざいっぽ',
        sender=os.environ.get('EMAIL_USER'),
        recipients=[lecturer_email]
    )
    msg.body = f'''\
下記の日程でレクチャーの予約が確定しました。

【レクチャー情報】
日付：{date}
時間：{time_slot}

準備が整いましたら、ご連絡いただけますようお願い申し上げます。

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

def send_lecture_approval_email(requester_email, reservation, lecturer):
    try:
        msg = Message(
            'レクチャーリクエストが承認されました - はざいっぽ',
            sender=os.environ.get('EMAIL_USER'),
            recipients=[requester_email]
        )
        msg.body = f'''\
    あなたのレクチャーリクエストが承認されました。
    
    【レクチャー情報】
    日付：{reservation.date}
    時間：{reservation.start_time.strftime('%H:%M')} ~ {reservation.end_time.strftime('%H:%M')}
    レクチャー担当者：{lecturer.contact_name} ({lecturer.email})
    
    レクチャーの詳細については、担当者と直接連絡を取り合ってください。
    
    何かご不明点がございましたら、サポートまでお問い合わせください。
    
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
        send_email_safe(msg)
        return True
    except Exception as e:
        current_app.logger.error(f"レクチャー承認メール送信エラー: {e}")
        return False

def send_lecturer_confirmation_email(lecturer_email, reservation, requester):
    try:
        msg = Message(
            'レクチャーが確定しました - はざいっぽ',
            sender=os.environ.get('EMAIL_USER'),
            recipients=[lecturer_email]
        )
        msg.body = f'''\
    レクチャーが確定しました。
    
    【レクチャー情報】
    日付：{reservation.date}
    時間：{reservation.start_time.strftime('%H:%M')} ~ {reservation.end_time.strftime('%H:%M')}
    予約者：{requester.contact_name} ({requester.email})
    
    レクチャーの詳細については、予約者と直接連絡を取り合ってください。
    
    何かご不明点がございましたら、サポートまでお問い合わせください。
    
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
        send_email_safe(msg)
        return True
    except Exception as e:
        current_app.logger.error(f"レクチャー担当者確認メール送信エラー: {e}")
        return False

def send_cancel_reservation_email(user_email, reservation):
    msg = Message(
        '予約がキャンセルされました - はざいっぽ',
        sender=os.environ.get('EMAIL_USER'),
        recipients=[user_email]
    )
    msg.body = f'''\
あなたの以下の予約がキャンセルされました。

【予約情報】
日付：{reservation.date}
時間：{reservation.start_time.strftime('%H:%M')} ~ {reservation.end_time.strftime('%H:%M')}

予約のキャンセルを希望された場合は、再度予約を行ってください。

何かご不明点やご質問がございましたら、サポートまでお問い合わせください。

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

def send_reject_request_email(user_email, reservation, rejected_user):
    msg = Message(
        'リクエストが拒否されました - はざいっぽ',
        sender=os.environ.get('EMAIL_USER'),
        recipients=[user_email]
    )
    msg.body = f'''\
リクエストが拒否されました。

以下の予約に関するリクエストが拒否されました。

【予約情報】
日付：{reservation.date}
時間：{reservation.start_time.strftime('%H:%M')} ~ {reservation.end_time.strftime('%H:%M')}

リクエストを拒否しました。

何かご不明点やご質問がございましたら、サポートまでお問い合わせください。

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

def send_reject_request_to_sender_email(requester_email, reservation, rejected_user):
    msg = Message(
        'リクエストを拒否されました - はざいっぽ',
        sender=os.environ.get('EMAIL_USER'),
        recipients=[rejected_user.email]
    )
    msg.body = f'''\
あなたが送信したリクエストが拒否されました。

以下の予約に関するリクエストが拒否されました。

【予約情報】
日付：{reservation.date}
時間：{reservation.start_time.strftime('%H:%M')} ~ {reservation.end_time.strftime('%H:%M')}

リクエストが拒否されました。

もしこのリクエストに覚えがない場合は、このメールを無視してください。アカウントのセキュリティを確保するため、疑わしいアクティビティがあった場合はすぐにご連絡ください。

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

def send_new_message_email(to_email, company_name):
    try:
        msg = Message(
            '新しいメッセージがあります',
            sender=os.environ.get('EMAIL_USER'),
            recipients=[to_email]
        )
        msg.body = f"{company_name} から新しいメッセージが届いています。"
        # HTML部分を削除 since the template does not exist
        mail.send(msg)
        return True
    except Exception as e:
        current_app.logger.error(f"メール送信エラー: {e}")
        return False

# --- 資材リクエスト「拒否」通知 -------------------------------

def send_reject_request_material_email(requester, material, rejector):
    """
    提供資材リクエストを『された側（＝リクエスト送信者）』へ送るメール
    """
    msg = Message(
        'リクエストが拒否されました - はざいっぽ',
        sender=os.environ.get('EMAIL_USER'),
        recipients=[requester.email]
    )
    msg.body = f'''\
残念ながら、以下の提供資材リクエストは拒否されました。

【資材情報】
材料名：{material.type}
サイズ：{material.size_1}×{material.size_2}×{material.size_3}
数量：{material.quantity}個
場所：{material.location}

【拒否した事業者】
法人名（屋号）：{rejector.company_name}
住所：{rejector.prefecture} {rejector.city} {rejector.address}
担当者：{rejector.contact_name}（{rejector.email} / {rejector.contact_phone}）

またのご利用をお待ちしております。

はざいっぽ チーム
'''
    return send_email_safe(msg)


def send_reject_notification_material_email(rejector, material):
    """
    提供資材リクエストを『した側（＝受信者 = 拒否したユーザ）』へ送る確認メール
    """
    msg = Message(
        'リクエストを拒否しました - はざいっぽ',
        sender=os.environ.get('EMAIL_USER'),
        recipients=[rejector.email]
    )
    msg.body = f'''\
以下の提供資材リクエストを拒否しました。

材料名：{material.type}
サイズ：{material.size_1}×{material.size_2}×{material.size_3}
数量：{material.quantity}個
場所：{material.location}

拒否が完了しましたのでご確認ください。

はざいっぽ チーム
'''
    return send_email_safe(msg)


def send_reject_request_wanted_email(requester, wanted_material, rejector):
    """
    希望資材リクエストを『された側（＝リクエスト送信者）』へ送るメール
    """
    msg = Message(
        'リクエストが拒否されました - はざいっぽ',
        sender=os.environ.get('EMAIL_USER'),
        recipients=[requester.email]
    )
    msg.body = f'''\
残念ながら、以下の希望資材リクエストは拒否されました。

【希望資材情報】
材料名：{wanted_material.type}
サイズ：{wanted_material.size_1}×{wanted_material.size_2}×{wanted_material.size_3}
数量：{wanted_material.quantity}個
場所：{wanted_material.location}

【拒否した事業者】
法人名（屋号）：{rejector.company_name}
住所：{rejector.prefecture} {rejector.city} {rejector.address}
担当者：{rejector.contact_name}（{rejector.email} / {rejector.contact_phone}）

またのご利用をお待ちしております。

はざいっぽ チーム
'''
    return send_email_safe(msg)


def send_reject_notification_wanted_email(rejector, wanted_material):
    """
    希望資材リクエストを『した側（＝受信者 = 拒否したユーザ）』へ送る確認メール
    """
    msg = Message(
        'リクエストを拒否しました - はざいっぽ',
        sender=os.environ.get('EMAIL_USER'),
        recipients=[rejector.email]
    )
    msg.body = f'''\
以下の希望資材リクエストを拒否しました。

材料名：{wanted_material.type}
サイズ：{wanted_material.size_1}×{wanted_material.size_2}×{wanted_material.size_3}
数量：{wanted_material.quantity}個
場所：{wanted_material.location}

拒否が完了しましたのでご確認ください。

はざいっぽ チーム
'''
    return send_email_safe(msg)
