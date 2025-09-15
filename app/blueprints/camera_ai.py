# app/blueprints/camera_ai.py
# ----------------------------------------------------------
# 画像アップロード → Celery タスク起動
#  - スマホ写真(～30MB) まで許容
#  - ファイル名が空でも自動で拡張子付与
#  - webp & heic 対応
#  - 413 (RequestEntityTooLarge) を JSON で返却
# ----------------------------------------------------------

import os
import logging
from uuid import uuid4

from flask import (
    Blueprint, request, jsonify, current_app, send_from_directory
)
from flask_login import login_required
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge, BadRequest

from app.tasks.camera_tasks import process_image_task
from app import csrf

# ───────────────────────── 設定 ───────────────────────── #
MAX_UPLOAD_MB      = 32                     # ★ スマホ写真十分カバー
MAX_CONTENT_LENGTH = MAX_UPLOAD_MB * 1024 * 1024

camera_ai_bp = Blueprint("camera_ai", __name__)
csrf.exempt(camera_ai_bp)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# アプリ起動時に MAX_CONTENT_LENGTH を注入
@camera_ai_bp.record_once
def set_max_content_length(state):
    app = state.app
    app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
    logger.info(f"MAX_CONTENT_LENGTH set to {MAX_UPLOAD_MB} MB")

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "heic", "webp"}

def allowed_file(filename: str) -> bool:
    return "." in filename and (
        filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )

# ───────────────────────── アップロード ───────────────────────── #
@camera_ai_bp.route("/process_image", methods=["POST"])
@login_required
def process_image():
    """
    画像を /app/shared_uploads に保存し Celery に回す
    """
    try:
        # -------- サイズチェック (Flaskが自動413返す前にメッセージを整形) --------
        if request.content_length is not None and request.content_length > MAX_CONTENT_LENGTH:
            return jsonify({
                "status": "error",
                "message": f"ファイルサイズが大きすぎます。{MAX_UPLOAD_MB}MB 以内にしてください。"
            }), 413

        image_file = request.files.get("image")
        if not image_file:
            return jsonify({"status": "error", "message": "画像ファイルがありません。"}), 400

        # 空 filename → 拡張子推定 (デフォルト .jpg)
        if image_file.filename == "":
            image_file.filename = "upload.jpg"

        if not allowed_file(image_file.filename):
            return jsonify({
                "status": "error",
                "message": "許可されていない形式です (png, jpg, jpeg, gif, heic, webp)。"
            }), 400

        # -------- ユニーク名生成 --------
        original = secure_filename(image_file.filename)
        name, ext = os.path.splitext(original)
        unique_filename = f"{name}_{uuid4().hex}{ext}"

        # -------- 保存 --------
        upload_dir = "/app/shared_uploads"
        os.makedirs(upload_dir, exist_ok=True)

        saved_path = os.path.join(upload_dir, unique_filename)
        image_file.save(saved_path)
        logger.info(f"画像保存: {saved_path}")

        # -------- 緯度経度 --------
        lat  = request.form.get("latitude")
        lon  = request.form.get("longitude")

        # -------- Celery 起動 --------
        task = process_image_task.delay(saved_path, lat, lon)
        return jsonify({"status": "success", "task_id": task.id}), 202

    except RequestEntityTooLarge:
        logger.warning("アップロードサイズが上限を超過")
        return jsonify({
            "status": "error",
            "message": f"ファイルサイズが大きすぎます。{MAX_UPLOAD_MB}MB 以内にしてください。"
        }), 413

    except Exception as e:
        logger.error(f"画像処理中エラー: {e}")
        return jsonify({"status": "error", "message": "画像処理中にエラーが発生しました。"}), 500

# ───────────────────────── タスク状態 ───────────────────────── #
@camera_ai_bp.route("/task_status/<task_id>", methods=["GET"])
@login_required
def task_status(task_id):
    try:
        task = process_image_task.AsyncResult(task_id)

        if task.state == "SUCCESS":
            result = task.get() or {}
            return jsonify({"status": "success", **result}), 200

        if task.state == "FAILURE":
            return jsonify({
                "status": "error",
                "message": task.info.get("message", "タスクが失敗しました。")
            }), 500

        return jsonify({"status": "pending"}), 202

    except Exception as e:
        logger.error(f"タスクステータス取得エラー: {e}")
        return jsonify({"status": "error", "message": "タスクステータス取得でエラー"}), 500

@camera_ai_bp.errorhandler(RequestEntityTooLarge)
def handle_413(e):
    return jsonify({
        "status": "error",
        "message": f"ファイルが大きすぎます。{MAX_UPLOAD_MB} MB 以内にしてください。"
    }), 413

@camera_ai_bp.errorhandler(BadRequest)
def handle_400(e):
    # ここで multipart/form-data 不備 or 異常サイズ などを一本化
    return jsonify({
        "status": "error",
        "message": "リクエスト形式が不正です。画像を再選択してお試しください。"
    }), 400
