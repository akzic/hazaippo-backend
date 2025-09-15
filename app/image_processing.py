# app/image_processing.py
import os, logging
import cv2, numpy as np

from app.utils.gemini_classifier import classify_image  # ★ 新 SDK 版

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# ───────────────────────── 前処理 ───────────────────────────
def preprocess_image(image_path: str) -> bool:
    """
    ノイズ除去＋背景除去＋コントラスト強調。
    Gemini 送信前に視認性を上げる。失敗しても致命的ではない。
    """
    try:
        img = cv2.imread(image_path, cv2.IMREAD_COLOR)
        if img is None:
            logger.error("画像読み込み失敗")
            return False

        img = cv2.GaussianBlur(img, (5, 5), 0)
        img = cv2.medianBlur(img, 5)

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        contours, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            mask = np.zeros_like(gray)
            cv2.drawContours(mask, [max(contours, key=cv2.contourArea)], -1, 255, cv2.FILLED)
            img = cv2.bitwise_and(img, img, mask=mask)

        clahe = cv2.createCLAHE(2.0, (8, 8))
        img = cv2.merge([clahe.apply(img[:, :, i]) for i in range(3)])
        cv2.imwrite(image_path, img)
        return True
    except Exception as e:
        logger.warning(f"前処理失敗: {e}")
        return False

# ───────────────────────── エントリ ─────────────────────────
def process_image_ai(image_path: str, preprocess: bool = True) -> dict:
    """
    画像を解析し、Gemini 2.5 Flash の JSON 結果を返す。
    """
    if preprocess:
        preprocess_image(image_path)
    return classify_image(image_path)
