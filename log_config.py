import logging
from logging.handlers import RotatingFileHandler
import os

# ログファイルのディレクトリ
log_directory = "logs"
if not os.path.exists(log_directory):
    os.makedirs(log_directory)

# ログファイルのパス
log_file = os.path.join(log_directory, "app.log")

# ロガーの設定
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ハンドラーの設定
handler = RotatingFileHandler(log_file, maxBytes=10240, backupCount=3)
handler.setLevel(logging.INFO)

# フォーマッターの設定
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)

# ハンドラーをロガーに追加
logger.addHandler(handler)
