# app/blueprints/camera_ai.py

from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required
from app.tasks.camera_tasks import process_image_task
import logging
from werkzeug.utils import secure_filename
import os
import tempfile
from uuid import uuid4

camera_ai_bp = Blueprint('camera_ai', __name__)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# 許可されたファイル拡張子の設定
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'HEIC'}

def allowed_file(filename):
    """許可された拡張子のファイルかどうかを判定する関数"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@camera_ai_bp.route('/process_image', methods=['POST'])
@login_required
def process_image():
    try:
        # 画像ファイルを取得
        image_file = request.files.get('image')
        if not image_file:
            return jsonify({'status': 'error', 'message': '画像ファイルがありません。'}), 400

        if not allowed_file(image_file.filename):
            return jsonify({'status': 'error', 'message': 'ファイル形式はpng, jpg, jpeg, gif, HEICのみにして下さい。'}), 400

        # ユニークなファイル名を生成
        original_filename = secure_filename(image_file.filename)
        unique_id = uuid4().hex
        name, ext = os.path.splitext(original_filename)
        unique_filename = f"{name}_{unique_id}{ext}"

        # 一時ディレクトリに保存
        temp_dir = tempfile.mkdtemp()
        image_path = os.path.join(temp_dir, unique_filename)
        image_file.save(image_path)
        logger.info(f"画像を一時保存しました: {image_path}")

        # 緯度経度を取得
        latitude = request.form.get('latitude')
        longitude = request.form.get('longitude')

        # タスクを起動
        task = process_image_task.delay(image_path, latitude, longitude)
        return jsonify({'status': 'success', 'task_id': task.id}), 202
    except Exception as e:
        logger.error(f"画像処理中にエラーが発生しました: {e}")
        return jsonify({'status': 'error', 'message': '画像処理中にエラーが発生しました。'}), 500

@camera_ai_bp.route('/task_status/<task_id>', methods=['GET'])
@login_required
def task_status(task_id):
    try:
        task = process_image_task.AsyncResult(task_id)
        if task.state == 'SUCCESS':
            result = task.get()
            if result is not None:
                # トップレベルに 'status': 'success' を追加
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
            # タスクが実行中または保留中
            return jsonify({'status': 'pending'}), 202
    except Exception as e:
        logger.error(f"タスクステータスの取得中にエラーが発生しました: {e}")
        return jsonify({'status': 'error', 'message': 'タスクステータスの取得中にエラーが発生しました。'}), 500
