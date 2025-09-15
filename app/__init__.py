# app/__init__.py

from flask import Flask, jsonify, redirect, url_for, request
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, current_user
from flask_mail import Mail
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect, CSRFError
from config import Config
from flask_cors import CORS
import os
import logging
from logging.handlers import RotatingFileHandler
from pytz import timezone
from datetime import datetime
from flask_socketio import SocketIO
from flask_restful import Api
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_jwt_extended import JWTManager
from firebase_admin import credentials, initialize_app

# Flask拡張の初期化
db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'info'
mail = Mail()
migrate = Migrate()
csrf = CSRFProtect()
socketio = SocketIO()
limiter = Limiter(key_func=get_remote_address)
jwt = JWTManager()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # ─────────────────────────────────────────────
    #  DB 接続時にセッション TZ を強制的に Asia/Tokyo へ
    # ─────────────────────────────────────────────
    # SQLALCHEMY_ENGINE_OPTIONS が既に dict ならマージ、
    # 無ければ新しく作ってから connect_args を追加
    engine_opts = app.config.setdefault('SQLALCHEMY_ENGINE_OPTIONS', {})
    connect_args = engine_opts.setdefault('connect_args', {})
    # 既存オプションを壊さないよう update
    connect_args.update({'options': '-c timezone=Asia/Tokyo'})

    # Flask拡張の初期化
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    CORS(app, resources={r"/api/*": {"origins": "*"}})  # CORS設定をAPIエンドポイントに限定
    socketio.init_app(app, cors_allowed_origins="*", async_mode='threading')
    limiter.init_app(app)
    jwt.init_app(app)
    cred_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
    if cred_path:                          # .env が読み込まれていればパスが入る
        cred = credentials.Certificate(cred_path)
        try:
            initialize_app(cred)           # すでに初期化済みでも ValueError
        except ValueError:
            pass

    # アップロードサイズの制限（5MB）
    app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB

    # ログの設定
    logging.basicConfig(level=logging.DEBUG)

    # アプリケーションのロガー設定
    if not app.debug:
        if not os.path.exists('logs'):
            os.mkdir('logs')
        file_handler = RotatingFileHandler('logs/app.log', maxBytes=10240, backupCount=10)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.DEBUG)
        app.logger.addHandler(file_handler)
        # propagate を無効化してルートロガーへの伝播を防ぐ
        app.logger.propagate = False

    app.logger.setLevel(logging.DEBUG)
    app.logger.info('THE IRIYO startup')

    # ユーザーアクティビティ用のロガー設定
    user_activity_logger = logging.getLogger('user_activity')
    user_activity_logger.setLevel(logging.INFO)

    # ユーザーアクティビティログ用のファイルハンドラーを追加
    if not os.path.exists('logs'):
        os.mkdir('logs')
    user_activity_file_handler = RotatingFileHandler('logs/user_activity.log', maxBytes=10240, backupCount=10)
    user_activity_file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s'
    ))
    user_activity_file_handler.setLevel(logging.INFO)
    user_activity_logger.addHandler(user_activity_file_handler)
    # コンソールハンドラーの追加（オプション）
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s: %(message)s'))
    console_handler.setLevel(logging.INFO)
    user_activity_logger.addHandler(console_handler)
    # propagate を無効化
    user_activity_logger.propagate = False

    # unauthorized_handler の定義（各リクエストでAjaxリクエストの場合は JSON レスポンス、それ以外はログイン画面へリダイレクト）
    @login_manager.unauthorized_handler
    def unauthorized_callback():
        # APIエンドポイントの場合、またはAjaxリクエストとして認識できた場合はJSONで返す
        if '/api' in request.path.lower() or request.headers.get('X-Requested-With', '').lower() == 'xmlhttprequest':

            return jsonify({'msg': 'Unauthorized'}), 401
        else:
            return redirect(url_for('auth.login'))

    # Celeryの初期化をBlueprintの登録前に行う
    from app.celery_app import init_celery
    init_celery(app)

    # ブループリントのインポートと登録
    from app.blueprints.auth import auth as auth_bp
    from app.blueprints.profile import profile as profile_bp
    from app.blueprints.materials import materials_bp
    from app.blueprints.dashboard import dashboard as dashboard_bp
    from app.blueprints.search import search_bp
    from app.blueprints.requests import requests_bp
    from app.blueprints.email_notifications import email_notifications as email_notifications_bp
    from app.blueprints.terminal import terminal_bp
    from app.blueprints.terminal_management import terminal_management_bp
    from app.blueprints.chat import chat_bp
    from app.blueprints.site import site_bp
    from app.blueprints.camera_ai import camera_ai_bp
    from app.blueprints.assetlinks import assetlinks_bp
    from app.blueprints.groups import groups_bp

    # APIブループリントのインポート
    from app.api.api_auth import api_auth as api_auth_bp
    from app.api.api_dashboard import api_dashboard as api_dashboard_bp
    from app.api.api_requests import api_requests_bp
    from app.api.api_materials import api_materials_bp
    from app.api.api_chat import api_chat_bp
    from app.api.api_profile import api_profile_bp
    from app.api.api_search import api_search_bp
    from app.api.api_site import api_site_bp
    from app.api.api_terminal_management import api_terminal_management_bp
    from app.api.api_terminal import api_terminal_bp
    from app.api.api_utils import api_utils_bp
    from app.api.api_notifications import api_notifications_bp
    from app.api.api_groups import api_groups_bp

    # APIブループリントをCSRF保護から除外
    csrf.exempt(api_auth_bp)
    csrf.exempt(api_dashboard_bp)
    csrf.exempt(api_requests_bp)
    csrf.exempt(api_materials_bp)
    csrf.exempt(api_chat_bp)
    csrf.exempt(api_profile_bp)
    csrf.exempt(api_search_bp)
    csrf.exempt(api_site_bp)
    csrf.exempt(api_terminal_management_bp)
    csrf.exempt(api_terminal_bp)
    csrf.exempt(api_utils_bp)
    csrf.exempt(camera_ai_bp)
    csrf.exempt(api_notifications_bp)
    csrf.exempt(assetlinks_bp)
    csrf.exempt(api_groups_bp)

    # Blueprintの登録にurl_prefixを追加
    app.register_blueprint(auth_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(materials_bp, url_prefix='/materials')
    app.register_blueprint(dashboard_bp, url_prefix='/dashboard')
    app.register_blueprint(search_bp, url_prefix='/search')
    app.register_blueprint(requests_bp)
    app.register_blueprint(email_notifications_bp)
    app.register_blueprint(terminal_bp, url_prefix='/terminal')
    app.register_blueprint(terminal_management_bp, url_prefix='/terminal_management')
    app.register_blueprint(chat_bp, url_prefix='/chat')
    app.register_blueprint(site_bp, url_prefix='/site')
    app.register_blueprint(camera_ai_bp, url_prefix='/camera_ai')
    app.register_blueprint(api_notifications_bp, url_prefix='/api/notifications')
    app.register_blueprint(assetlinks_bp)
    app.register_blueprint(groups_bp, url_prefix='/groups')

    # APIブループリントの登録
    app.register_blueprint(api_auth_bp, url_prefix='/api/auth')
    app.register_blueprint(api_dashboard_bp, url_prefix='/api/dashboard')
    app.register_blueprint(api_requests_bp, url_prefix='/api/requests')
    app.register_blueprint(api_materials_bp, url_prefix='/api/materials')
    app.register_blueprint(api_chat_bp, url_prefix='/api/chat')
    app.register_blueprint(api_profile_bp, url_prefix='/api/profile')
    app.register_blueprint(api_search_bp, url_prefix='/api/search')
    app.register_blueprint(api_site_bp, url_prefix='/api/site')
    app.register_blueprint(api_terminal_management_bp, url_prefix='/api/terminal_management')
    app.register_blueprint(api_terminal_bp, url_prefix='/api/terminal')
    app.register_blueprint(api_utils_bp, url_prefix='/api/utils')
    app.register_blueprint(api_groups_bp)

    # タイムゾーンの設定
    app.config['TIMEZONE'] = timezone('Asia/Tokyo')

    @app.template_filter('format_datetime_jst')
    def format_datetime_jst(value):
        if value is None:
            return ""
        jst = app.config['TIMEZONE']
        if value.tzinfo is None:
            value = value.replace(tzinfo=jst)
        jst_value = value.astimezone(jst)
        return jst_value.strftime('%Y-%m-%d %H:%M:%S')

    # コンテキストプロセッサの追加
    @app.context_processor
    def inject_user_flags():
        has_affiliated_terminal = False
        is_lecturer = False
        if current_user.is_authenticated:
            has_affiliated_terminal = current_user.affiliated_terminal_id is not None
            is_lecturer = current_user.lecture_flug
        return dict(has_affiliated_terminal=has_affiliated_terminal, is_lecturer=is_lecturer)

    # CSRFエラーハンドラーの追加
    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        return jsonify({'error': e.description}), e.code

    # 413エラーハンドラーの追加
    @app.errorhandler(413)
    def request_entity_too_large(error):
        return jsonify({'error': 'アップロードするファイルは5MB以下にしてください。'}), 413

    # グローバルなエラーハンドラーの追加
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({'message': 'Not Found'}), 404

    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({'message': 'Internal Server Error'}), 500

    @app.route("/health")
    def health():
        # 何もせず 200 を返すだけ
        return "OK", 200

    return app
