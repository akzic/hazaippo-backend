# app/celery_app.py
from __future__ import annotations

import logging
import os
from celery import Celery

# ───────── ロギング ─────────
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# ───────── Celery インスタンス ─────────
CELERY_BROKER_URL     = os.getenv("CELERY_BROKER_URL",     "redis://redis:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", CELERY_BROKER_URL)

celery = Celery(
    "app",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
)

# “tasks.” 配下を自動検出（include を増やし忘れても OK）
celery.autodiscover_tasks(["app.tasks"])

logger.info("Celery が初期化されました（ブローカー: %s）", CELERY_BROKER_URL)


# ───────── Flask アプリから呼び出す関数 ─────────
def init_celery(flask_app):
    """
    Flask → create_app() 完了後に呼び出して Flask コンテキストを噛ませる。
    例:
        app = create_app()
        init_celery(app)
    """
    celery.conf.update(flask_app.config)

    class ContextTask(celery.Task):
        abstract = True  # ★ これで継承専用になる
        def __call__(self, *args, **kwargs):
            with flask_app.app_context():
                return super().__call__(*args, **kwargs)

    celery.Task = ContextTask
