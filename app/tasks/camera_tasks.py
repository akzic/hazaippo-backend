# app/tasks/camera_tasks.py
"""
画像 AI 推論 Celery タスク
1) 前処理なし  → 推論
2) 前処理あり  → 推論
3) 位置情報を（あれば）逆ジオコーディングして付与
"""

from __future__ import annotations

import logging
import os
import shutil
from uuid import uuid4

import requests

from app.celery_app import celery
from app.image_processing import preprocess_image, classify_image  # あなたの実装
# from app.utils.s3_uploader import upload_file_to_s3  # S3 へ保存したい場合は有効に

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


@celery.task(bind=True, name="camera.process_image_ai")  # ★ 公開名を固定
def process_image_ai(
    self,
    image_path: str,
    latitude: str | None = None,
    longitude: str | None = None,
) -> dict:
    """
    Parameters
    ----------
    image_path : str
        ローカル一時ファイルのパス
    latitude / longitude : str | None
        緯度経度文字列（'' 空文字なら無視）

    Returns
    -------
    dict
        {
          "non_preprocessed": {"status": "success", ...},
          "preprocessed":    {"status": "success", ...}
        }
    """
    tmp_dir = os.path.join("/tmp", "gemini_task", uuid4().hex)
    os.makedirs(tmp_dir, exist_ok=True)

    try:
        logger.info("[TASK] start: %s", image_path)

        # ---- 元画像をコピーして保存（安全のため読み込み専用） ----
        orig_path = os.path.join(tmp_dir, "orig.jpg")
        shutil.copy(image_path, orig_path)

        # ---- 前処理なし推論 ----
        result_np = classify_image(orig_path)

        # ---- 前処理あり推論 ----
        work_path = os.path.join(tmp_dir, "work.jpg")
        shutil.copy(orig_path, work_path)
        preprocess_image(work_path)
        result_p = classify_image(work_path)

        # ---- 逆ジオコーディング ----
        location = ""
        if latitude and longitude and latitude.strip() and longitude.strip():
            gkey = os.getenv("GOOGLE_API_KEY") or celery.conf.get("GOOGLE_API_KEY")
            if gkey:
                url = (
                    "https://maps.googleapis.com/maps/api/geocode/json"
                    f"?latlng={latitude},{longitude}&language=ja&key={gkey}"
                )
                try:
                    data = requests.get(url, timeout=10).json()
                    if data.get("status") == "OK" and data["results"]:
                        location = data["results"][0]["formatted_address"]
                except Exception as e:
                    logger.warning("[TASK] geocoding error: %s", e)

        for r in (result_np, result_p):
            if r.get("status") == "success":
                r["location"] = location

        return {"non_preprocessed": result_np, "preprocessed": result_p}

    except Exception as e:
        logger.exception("[TASK] ERROR")
        self.update_state(state="FAILURE", meta={"message": str(e)})
        return {"status": "error", "message": str(e)}

    finally:
        # ---- 後始末 ----
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            if os.path.exists(image_path):
                os.remove(image_path)
        except Exception as e:
            logger.warning("[TASK] cleanup error: %s", e)


# ---- 旧 import 対応用エイリアス ----------------------------
process_image_task = process_image_ai
__all__ = ["process_image_ai", "process_image_task"]
