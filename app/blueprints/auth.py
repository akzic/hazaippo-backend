# app/blueprints/auth.py

from flask import Blueprint, render_template, url_for, flash, redirect, request, g, current_app
from app import db, bcrypt
from app.forms import RegistrationForm, LoginForm, ResetPasswordForm, RequestResetForm
from app.models import User
from flask_login import login_user, current_user, logout_user, login_required
import os
from app.blueprints.utils import log_user_activity, send_reset_email, send_welcome_email
from twilio.rest import Client
from datetime import datetime
import pytz

auth = Blueprint('auth', __name__)
JST = pytz.timezone('Asia/Tokyo')

@auth.route("/")
def home():
    return redirect(url_for('auth.login'))

@auth.before_app_request
def before_request():
    allowed_endpoints = [
        'auth.login', 
        'auth.register', 
        'auth.reset_request', 
        'auth.reset_token', 
        'static',
        'dashboard.dashboard_home',
        'terminal.search_terminal',
        'terminal_management.terminal_reservation_management',
        'terminal_management.terminal_material_management',
        'terminal_management.update_material',
        'terminal.reserve_terminal',
    ]
    
    current_app.logger.debug(f"User authenticated: {current_user.is_authenticated}")
    current_app.logger.debug(f"Request endpoint: {request.endpoint}")
    
    if not current_user.is_authenticated and request.endpoint not in allowed_endpoints:
        current_app.logger.debug("ログインしていないため、loginページにリダイレクトされました。")
        return redirect(url_for('auth.login'))
    
    if current_user.is_authenticated:
        g.company_name = current_user.company_name
        g.contact_name = current_user.contact_name

        # last_seen を更新
        current_user.last_seen = datetime.now(JST)
        db.session.commit()

@auth.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.dashboard_home'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and bcrypt.check_password_hash(user.password, form.password.data):
            login_user(user, remember=form.remember.data)
            next_page = request.args.get('next')
            log_user_activity(user.id, 'ログイン', 'ユーザーがログインしました。', request.remote_addr, request.user_agent.string, 'N/A')
            return redirect(next_page) if next_page else redirect(url_for('dashboard.dashboard_home'))
        else:
            flash('ログインに失敗しました。メールアドレスかパスワードが違います。', 'danger')
    return render_template('login.html', form=form)

@auth.route("/register", methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.dashboard_home'))
    form = RegistrationForm()
    if form.validate_on_submit():
        current_app.logger.debug("フォームが有効です。")
        # メールアドレスと電話番号の重複チェック
        existing_user_by_email = User.query.filter_by(email=form.contact_email.data).first()
        existing_user_by_contact_phone = User.query.filter_by(contact_phone=form.contact_phone.data).first()
        
        if existing_user_by_email:
            flash('このメールアドレスは既に使用されています。別のメールアドレスを使用してください。', 'danger')
            current_app.logger.debug("メールアドレスが既に存在します。")
            return render_template('register.html', form=form)
        
        if form.business_structure.data in ['0', '1']:
            if existing_user_by_contact_phone:
                flash('この電話番号は既に使用されています。別の電話番号を使用してください。', 'danger')
                current_app.logger.debug("電話番号が既に存在します。")
                return render_template('register.html', form=form)

        # business_structureの取得
        try:
            business_structure = form.business_structure.data  # '0': 法人, '1': 個人事業主, '2': 個人
            current_app.logger.debug(f"business_structure: {business_structure}")
        except ValueError:
            flash('有効な登録形態を選択してください。', 'danger')
            current_app.logger.debug("business_structure の値が無効です。")
            return render_template('register.html', form=form)

        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')

        # business_structure に基づいて company_name を設定
        if business_structure == '0':  # 法人
            company_name = form.company_name.data
            industry = form.industry.data
            job_title = form.job_title.data
            current_app.logger.debug(f"法人として登録: company_name={company_name}, industry={industry}, job_title={job_title}")
        elif business_structure == '1':  # 個人事業主
            company_name = form.company_name.data  # 屋号として同じフィールドを使用
            industry = form.industry.data
            job_title = form.job_title.data
            current_app.logger.debug(f"個人事業主として登録: company_name={company_name}, industry={industry}, job_title={job_title}")
        elif business_structure == '2':  # 個人
            company_name = form.company_name.data  # ニックネームとして同じフィールドを使用
            industry = '業種なし'
            job_title = '職種なし'
            current_app.logger.debug(f"個人として登録: company_name={company_name}, industry={industry}, job_title={job_title}")
        else:
            flash('有効な登録形態を選択してください。', 'danger')
            current_app.logger.debug("business_structure が無効です。")
            return render_template('register.html', form=form)

        # ユーザーの作成とデータベースへの追加
        if business_structure in ['0', '1']:
            user = User(
                email=form.contact_email.data, 
                password=hashed_password,
                company_name=company_name,
                prefecture=form.prefecture.data,
                city=form.city.data,
                address=form.address.data,
                company_phone=form.company_phone.data,  # 会社電話番号
                industry=industry,
                job_title=job_title,
                without_approval=form.without_approval.data,
                contact_name=form.contact_name.data,
                contact_phone=form.contact_phone.data,  # 担当者電話番号
                business_structure=business_structure
            )
        else:
            phone_number = form.individual_phone.data
            user = User(
                email=form.contact_email.data, 
                password=hashed_password,
                company_name=company_name,
                prefecture=form.prefecture.data,
                city=form.city.data,
                address=form.address.data,
                company_phone=phone_number,  # 個人の場合、company_phoneに電話番号を割り当て
                industry=industry,
                job_title=job_title,
                without_approval=form.without_approval.data,
                contact_name=form.contact_name.data,
                contact_phone=phone_number,  # 個人の場合、contact_phoneにも電話番号を割り当て
                business_structure=business_structure
            )

        db.session.add(user)
        try:
            db.session.commit()
            current_app.logger.debug("ユーザーがデータベースに保存されました。")
        except Exception as e:
            db.session.rollback()
            flash('ユーザー登録中にエラーが発生しました。もう一度やり直してください。', 'danger')
            current_app.logger.error(f'ユーザー登録エラー: {e}')
            return render_template('register.html', form=form)

        flash('ユーザー登録が完了しました！', 'success')
        log_user_activity(user.id, 'ユーザー登録', 'ユーザーが新規登録しました。', request.remote_addr, request.user_agent.string, 'N/A')
        
        if not send_welcome_email(user.email):
            db.session.delete(user)
            db.session.commit()
            flash('ユーザー登録に失敗しました。もう一度やり直してください。', 'danger')
            current_app.logger.debug("ウェルカムメールの送信に失敗しました。")
            return render_template('register.html', form=form)

        return redirect(url_for('auth.login'))
    else:
        # フォームが無効な場合の詳細なエラーをログに出力
        if request.method == 'POST':
            for fieldName, errorMessages in form.errors.items():
                for err in errorMessages:
                    current_app.logger.debug(f"Validation error in '{fieldName}': {err}")
            current_app.logger.debug("フォームが無効です。")
    return render_template('register.html', form=form)

@auth.route("/reset_password", methods=['GET', 'POST'])
def reset_request():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.dashboard_home'))

    form = RequestResetForm()
    
    if form.validate_on_submit():
        reset_option = request.form.get('reset_option')  # ラジオボタンの選択肢を取得
        if reset_option == 'email':
            user = User.query.filter_by(email=form.email.data).first()
            if user:
                if send_reset_email(user):
                    flash('パスワードリセットのためのメールを送信しました。', 'info')
                else:
                    flash('パスワードリセットのメール送信に失敗しました。', 'danger')
                log_user_activity(user.id, 'パスワードリセットリクエスト', 'パスワードリセットのリクエストを受け付けました。', request.remote_addr, request.user_agent.string, 'N/A')
                return redirect(url_for('auth.login'))
            else:
                flash('このメールアドレスに該当するアカウントはありません。', 'warning')
        elif reset_option == 'sms':
            user = User.query.filter_by(contact_phone=form.phone.data).first()
            if user:
                if send_reset_sms(user):
                    flash('パスワードリセットのためのSMSを送信しました。', 'info')
                else:
                    flash('パスワードリセットのSMS送信に失敗しました。', 'danger')
                log_user_activity(user.id, 'パスワードリセットリクエスト', 'パスワードリセットのリクエストを受け付けました。', request.remote_addr, request.user_agent.string, 'N/A')
                return redirect(url_for('auth.login'))
            else:
                flash('この電話番号に該当するアカウントはありません。', 'warning')
    
    return render_template('reset_password.html', form=form)

@auth.route("/reset_password/<token>", methods=['GET', 'POST'])
def reset_token(token):
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.dashboard_home'))

    user = User.verify_reset_token(token)
    if not user:
        flash('トークンが無効です。', 'warning')
        return redirect(url_for('auth.reset_request'))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user.password = hashed_password
        db.session.commit()
        flash('パスワードが更新されました！', 'success')
        log_user_activity(user.id, 'パスワードリセット', 'パスワードがリセットされました。', request.remote_addr, request.user_agent.string, 'N/A')
        return redirect(url_for('auth.login'))
    
    return render_template('reset_token.html', form=form, token=token)

@auth.route("/logout")
def logout():
    if current_user.is_authenticated:
        log_user_activity(current_user.id, 'ログアウト', 'ユーザーがログアウトしました。', request.remote_addr, request.user_agent.string, 'N/A')
    logout_user()
    return redirect(url_for('auth.login'))

def send_reset_sms(user):
    account_sid = os.getenv('TWILIO_ACCOUNT_SID')
    auth_token = os.getenv('TWILIO_AUTH_TOKEN')
    client = Client(account_sid, auth_token)

    token = user.get_reset_token()
    reset_url = url_for('auth.reset_token', token=token, _external=True)

    message_body = f"こんにちは、{user.contact_name}様。パスワードリセットのリクエストがありました。\n以下のリンクをクリックしてパスワードをリセットしてください: {reset_url}"

    try:
        message = client.messages.create(
            body=message_body,
            from_='+1234567890',  # Twilioの電話番号に置き換えてください
            to=user.contact_phone
        )
        return True
    except Exception as e:
        current_app.logger.error(f"SMS送信に失敗しました: {e}")
        return False
