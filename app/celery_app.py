# app/celery_app.py

from celery import Celery
import logging
import os
from flask import Flask
from config import Config
from app import create_app  # Flaskアプリケーションのファクトリ関数をインポート

# ロギングの設定
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# 環境変数またはデフォルト値から設定を取得
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')

# Celeryインスタンスの作成と設定
celery = Celery(
    'app',
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=['app.tasks.camera_tasks']  # タスクモジュールを明示的に指定
)

logger.info("Celeryが初期化され、タスクが登録されました。")

def init_celery(app):
    """
    FlaskアプリケーションとCeleryを連携させる関数。
    """
    celery.conf.update(app.config)

    # タスク実行時にFlaskのアプリケーションコンテキストを利用
    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask

# Flaskアプリケーションを初期化し、Celeryを設定
app = create_app(Config)
init_celery(app)
