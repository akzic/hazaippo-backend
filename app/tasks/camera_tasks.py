# app/tasks/camera_tasks.py

from app.celery_app import celery
from app.image_processing import process_image_ai
import logging
import requests
import os

# ロガーの設定
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

@celery.task(bind=True)
def process_image_task(self, image_path: str, latitude: str = None, longitude: str = None):
    """
    非同期で画像処理を行うタスク。
    前処理ありと前処理なしの両方の結果を取得。
    """
    try:
        logger.info(f"非同期タスク開始: image_path={image_path}, latitude={latitude}, longitude={longitude}")

        # 前処理ありでの画像処理
        logger.info("前処理ありで画像を処理します。")
        result_preprocessed = process_image_ai(image_path, preprocess=True)

        # 前処理なしでの画像処理
        logger.info("前処理なしで画像を処理します。")
        result_non_preprocessed = process_image_ai(image_path, preprocess=False)

        # 位置情報を含める（両方の結果に適用）
        location = ""
        if latitude and longitude:
            # 逆ジオコーディングを行う（Google Maps Geocoding APIを使用）
            google_api_key = celery.conf.get('GOOGLE_API_KEY')
            if google_api_key:
                geocoding_url = (
                    f"https://maps.googleapis.com/maps/api/geocode/json?"
                    f"latlng={latitude},{longitude}&language=ja&key={google_api_key}"
                )
                try:
                    response = requests.get(geocoding_url, timeout=10)
                    geocoding_data = response.json()
                    if geocoding_data['status'] == 'OK' and len(geocoding_data['results']) > 0:
                        location = geocoding_data['results'][0]['formatted_address']
                        logger.info(f"非同期タスクで位置情報を取得しました: {location}")
                    else:
                        logger.warning(f"非同期タスクで逆ジオコーディングに失敗しました: {geocoding_data['status']}")
                except Exception as e:
                    logger.error(f"非同期タスクで逆ジオコーディング中にエラーが発生しました: {e}")
            else:
                logger.warning("GOOGLE_API_KEY が設定されていません。位置情報の取得をスキップします。")
        else:
            logger.info("緯度経度が提供されていないため、位置情報の取得をスキップします。")

        # 両方の結果に位置情報を追加
        if result_preprocessed.get('status') == 'success':
            result_preprocessed['location'] = location
        if result_non_preprocessed.get('status') == 'success':
            result_non_preprocessed['location'] = location

        # 結果をまとめる
        combined_result = {
            'preprocessed': result_preprocessed,
            'non_preprocessed': result_non_preprocessed
        }

        logger.info(f"非同期タスク完了: {combined_result}")

        return combined_result  # 結果を返す

    except Exception as e:
        logger.error(f"非同期タスク中にエラーが発生しました: {e}")
        self.update_state(state='FAILURE', meta={'message': str(e)})
        return {'status': 'error', 'message': str(e)}
    finally:
        # 一時ファイルの削除
        try:
            if os.path.exists(image_path):
                os.remove(image_path)
                logger.info(f"一時ファイルを削除しました: {image_path}")
        except Exception as e:
            logger.error(f"一時ファイルの削除中にエラーが発生しました: {e}")
