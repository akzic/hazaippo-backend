# app/api/api_camera_ai.py

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required
from app.tasks.camera_tasks import process_image_task
import logging
from werkzeug.utils import secure_filename
import os
from uuid import uuid4

from app import csrf  # CSRFProtectオブジェクトをインポート

camera_ai_bp = Blueprint('api_camera_ai', __name__, url_prefix='/api/camera_ai')
csrf.exempt(camera_ai_bp)  # CSRFチェックを除外

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# 許可されたファイル拡張子の設定
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'heic'}

def allowed_file(filename):
    """許可された拡張子のファイルかどうかを判定する関数"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@camera_ai_bp.route('/process_image', methods=['POST'])
@jwt_required()
def process_image():
    """
    multipart/form-data でアップロードされたファイルを受け取り、
    Docker コンテナ間で共有される /app/shared_uploads に保存し、
    Celery タスクを起動する API エンドポイント。
    """
    try:
        image_file = request.files.get('image')
        if not image_file:
            return jsonify({'status': 'error', 'message': '画像ファイルがありません。'}), 400

        if not allowed_file(image_file.filename):
            return jsonify({
                'status': 'error', 
                'message': 'ファイル形式は png, jpg, jpeg, gif, heic のみです。'
            }), 400

        # ユニークなファイル名を生成
        original_filename = secure_filename(image_file.filename)
        unique_id = uuid4().hex
        name, ext = os.path.splitext(original_filename)
        unique_filename = f"{name}_{unique_id}{ext}"

        # Dockerで共有するアップロードディレクトリ（例: /app/shared_uploads）
        upload_dir = '/app/shared_uploads'
        if not os.path.exists(upload_dir):
            os.makedirs(upload_dir, exist_ok=True)

        saved_path = os.path.join(upload_dir, unique_filename)
        image_file.save(saved_path)
        logger.info(f"画像を保存しました: {saved_path}")

        # 緯度経度の取得（任意）
        latitude = request.form.get('latitude')
        longitude = request.form.get('longitude')

        # Celeryタスクの起動
        task = process_image_task.delay(saved_path, latitude, longitude)
        return jsonify({'status': 'success', 'task_id': task.id}), 202

    except Exception as e:
        logger.error(f"画像処理中にエラーが発生しました: {e}")
        return jsonify({'status': 'error', 'message': '画像処理中にエラーが発生しました。'}), 500

@camera_ai_bp.route('/task_status/<task_id>', methods=['GET'])
@jwt_required()
def task_status(task_id):
    """
    指定されたタスクID の状態を取得するエンドポイント。
    タスクが成功なら結果を返し、失敗ならエラー、実行中なら pending を返します。
    """
    try:
        task = process_image_task.AsyncResult(task_id)
        if task.state == 'SUCCESS':
            result = task.get()
            if result is not None:
                response = {'status': 'success'}
                response.update(result)
                return jsonify(response), 200
            else:
                logger.error("タスクの結果が None でした。")
                return jsonify({'status': 'error', 'message': 'タスクの結果が取得できませんでした。'}), 500
        elif task.state == 'FAILURE':
            logger.error(f"タスクが失敗しました: {task.info.get('message', '')}")
            return jsonify({'status': 'error', 'message': 'タスクが失敗しました。'}), 500
        else:
            return jsonify({'status': 'pending'}), 202
    except Exception as e:
        logger.error(f"タスクステータスの取得中にエラーが発生しました: {e}")
        return jsonify({'status': 'error', 'message': 'タスクステータスの取得中にエラーが発生しました。'}), 500
