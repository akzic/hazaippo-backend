# celery_worker.py

import logging
from app.celery_app import celery, init_celery
from app import create_app

# ロガーの設定
logging.basicConfig(
    level=logging.DEBUG,  # ログレベルをDEBUGに設定
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Flaskアプリケーションの作成とCeleryの初期化
app = create_app()
init_celery(app)

logger.info("Celeryワーカーが初期化されました。")

if __name__ == '__main__':
    logger.info("Celeryワーカーを起動します。")
    celery.start()
