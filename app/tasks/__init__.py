# app/tasks/__init__.py

import logging

# タスクモジュールのインポート
from .camera_tasks import *

# ロギングの設定
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

logger.info("tasks パッケージがインポートされ、camera_tasks モジュールが読み込まれました。")
