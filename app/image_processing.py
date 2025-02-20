# app/image_processing.py

import os
import cv2  # OpenCVをインポート
import numpy as np
import logging
import requests
import base64
from app.celery_app import celery  # Celeryインスタンスをインポート

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

def preprocess_image(image_path: str) -> bool:
    """
    画像前処理を行う関数。
    ノイズ除去、背景除去、コントラスト調整を実施。
    """
    try:
        # 画像を読み込む
        image = cv2.imread(image_path, cv2.IMREAD_COLOR)
        if image is None:
            logger.error("画像の読み込みに失敗しました。無効な画像形式です。")
            return False

        # (1) ノイズ除去処理
        # Gaussian Blur
        image = cv2.GaussianBlur(image, (5, 5), 0)
        # Median Blur
        image = cv2.medianBlur(image, 5)

        # (2) 背景除去処理
        # グレースケール変換
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        # Otsuのしきい値処理
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        # 輪郭検出
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        # 最大の輪郭を取得
        if contours:
            largest_contour = max(contours, key=cv2.contourArea)
            # マスクの作成
            mask = np.zeros_like(gray)
            cv2.drawContours(mask, [largest_contour], -1, 255, thickness=cv2.FILLED)
            # マスクを適用して背景を除去
            image = cv2.bitwise_and(image, image, mask=mask)
        else:
            logger.warning("輪郭が検出されませんでした。背景除去をスキップします。")

        # (3) コントラスト調整
        # カラー画像の各チャンネルにCLAHEを適用
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        clahe_b = clahe.apply(image[:, :, 0])
        clahe_g = clahe.apply(image[:, :, 1])
        clahe_r = clahe.apply(image[:, :, 2])
        # チャンネルを統合
        image = cv2.merge((clahe_b, clahe_g, clahe_r))

        # 前処理後の画像を保存（カラー画像）
        cv2.imwrite(image_path, image)
        logger.info(f"画像の前処理が完了しました: {image_path}")
        return True

    except Exception as e:
        logger.error(f"画像前処理中にエラーが発生しました: {e}")
        return False

def determine_material_type(extracted_labels: list) -> str:
    """
    抽出されたラベルから material_type を判別する関数。
    必要に応じてキーワードを追加・修正してください。
    """
    labels = [label.lower() for label in extracted_labels]
    logger.debug(f"material_type 判別用ラベル: {labels}")

    # ラベルに基づいて材質タイプを判定
    if any(label in labels for label in ['wood', 'lumber', 'timber', 'log']):
        return '木材'
    elif any(label in labels for label in ['light steel', 'steel', 'metal']):
        return '軽量鉄骨'
    elif any(label in labels for label in ['board', 'plasterboard', 'drywall']):
        return 'ボード材'
    elif any(label in labels for label in ['panel', 'sheet', 'slab']):
        return 'パネル材'
    else:
        return 'その他'

def determine_subtype(extracted_labels: list, category: str) -> str:
    """
    抽出されたラベルからサブタイプを判別する関数。
    category: 'wood', 'board', 'panel'
    """
    labels = [label.lower() for label in extracted_labels]
    logger.debug(f"determine_subtype: category={category}, labels={labels}")

    if category == 'wood':
        if 'solid wood' in labels:
            return '無垢材'
        elif 'laminated wood' in labels or 'glulam' in labels:
            return '集成材（積層材）'
        elif 'hardwood' in labels:
            return '広葉樹'
        elif 'softwood' in labels:
            return '針葉樹'
        else:
            return 'その他'

    elif category == 'board':
        if 'plasterboard' in labels:
            return 'プラスターボード'
        elif 'reinforced board' in labels:
            return '強化ボード'
        elif 'fire resistant board' in labels:
            return '耐火ボード'
        elif 'water resistant board' in labels:
            return '耐水(防水)ボード'
        else:
            return 'その他'

    elif category == 'panel':
        if 'kitchen panel' in labels:
            return 'キッチンパネル'
        elif 'decorative panel' in labels:
            return '化粧板'
        else:
            return 'その他'

    else:
        return ''

def extract_quantity(extracted_objects: list) -> int:
    """
    オブジェクトのリストから数量を抽出する関数。
    同一種類のオブジェクトが複数検出された場合、その数をカウントします。
    """
    try:
        # オブジェクト名ごとに数量をカウント
        object_counts = {}
        for obj in extracted_objects:
            obj_lower = obj.lower()
            if obj_lower in object_counts:
                object_counts[obj_lower] += 1
            else:
                object_counts[obj_lower] = 1

        # 全オブジェクトの合計数量を算出
        quantity = sum(object_counts.values())

    except Exception as e:
        logger.error(f"数量の抽出中にエラーが発生しました: {e}")
        quantity = 0

    logger.debug(f"抽出された数量: quantity={quantity}")
    return quantity

def process_image_ai(image_path: str, preprocess: bool = True) -> dict:
    """
    画像をAIで処理し、抽出されたラベルと材質タイプ、およびその他のフィールドを返す関数。
    Google Cloud Vision APIの利用。
    preprocess: 前処理を行うかどうか
    """
    try:
        if preprocess:
            # 画像前処理の実行
            preprocessed = preprocess_image(image_path)
            if not preprocessed:
                logger.error("画像前処理に失敗しました。")
                return {
                    'status': 'error',
                    'message': '画像前処理に失敗しました。',
                    'extracted_text': '',
                    'material_type': 'その他',
                    'wood_type': '',
                    'board_material_type': '',
                    'panel_type': '',
                    'material_size_1': '',
                    'material_size_2': '',
                    'material_size_3': '',
                    'quantity': 0,
                    'location': ''
                }
        else:
            logger.info("前処理なしで画像を処理します。")

        # APIキーの取得
        api_key = celery.conf.get('GOOGLE_API_KEY')  # celeryの設定から取得
        if not api_key:
            logger.error("GOOGLE_API_KEY が設定されていません。")
            return {
                'status': 'error',
                'message': 'サーバー設定エラー',
                'extracted_text': '',
                'material_type': 'その他',
                'wood_type': '',
                'board_material_type': '',
                'panel_type': '',
                'material_size_1': '',
                'material_size_2': '',
                'material_size_3': '',
                'quantity': 0,
                'location': ''
            }

        # Vision APIのエンドポイントURL
        vision_api_url = f"https://vision.googleapis.com/v1/images:annotate?key={api_key}"

        # 画像をBase64エンコード
        with open(image_path, 'rb') as img_file:
            content = img_file.read()
        encoded_image = base64.b64encode(content).decode('utf-8')

        # ペイロードの構築
        payload = {
            "requests": [
                {
                    "image": {
                        "content": encoded_image
                    },
                    "features": [
                        {
                            "type": "LABEL_DETECTION",
                            "maxResults": 15  # maxResultsを増やす
                        },
                        {
                            "type": "OBJECT_LOCALIZATION",
                            "maxResults": 10
                        }
                    ]
                }
            ]
        }

        headers = {
            "Content-Type": "application/json"
        }

        # Vision APIにリクエストを送信
        response = requests.post(vision_api_url, json=payload, headers=headers, timeout=10)

        if response.status_code != 200:
            logger.error(f"Vision APIのレスポンスエラー: {response.text}")
            return {
                'status': 'error',
                'message': 'Vision APIの呼び出しに失敗しました。',
                'extracted_text': '',
                'material_type': 'その他',
                'wood_type': '',
                'board_material_type': '',
                'panel_type': '',
                'material_size_1': '',
                'material_size_2': '',
                'material_size_3': '',
                'quantity': 0,
                'location': ''
            }

        result = response.json()

        # レスポンスからデータを抽出
        labels = result['responses'][0].get('labelAnnotations', [])
        objects = result['responses'][0].get('localizedObjectAnnotations', [])
        extracted_labels = [label['description'] for label in labels]
        extracted_objects = [obj['name'] for obj in objects]

        logger.info(f"Vision APIから抽出したラベル: {extracted_labels}")
        logger.info(f"Vision APIから抽出したオブジェクト: {extracted_objects}")

        # ラベルの詳細ログ出力
        for label in labels:
            logger.debug(f"Label: {label['description']}, Score: {label['score']}")

        # 抽出されたラベルに基づいて材質タイプを判定
        material_type = determine_material_type(extracted_labels)

        # サブタイプの判定
        wood_type = board_material_type = panel_type = ''
        if material_type == '木材':
            wood_type = determine_subtype(extracted_labels, 'wood')
        elif material_type == 'ボード材':
            board_material_type = determine_subtype(extracted_labels, 'board')
        elif material_type == 'パネル材':
            panel_type = determine_subtype(extracted_labels, 'panel')

        # 数量の抽出
        quantity = extract_quantity(extracted_objects)

        # サイズの抽出は困難なため、ユーザーに手動入力を推奨
        material_size_1 = ''
        material_size_2 = ''
        material_size_3 = ''

        return {
            'status': 'success',
            'extracted_text': '',  # テキストは使用しない
            'material_type': material_type,
            'wood_type': wood_type,
            'board_material_type': board_material_type,
            'panel_type': panel_type,
            'material_size_1': material_size_1,
            'material_size_2': material_size_2,
            'material_size_3': material_size_3,
            'quantity': quantity,
            'location': ''  # 位置情報はタスク側で追加
        }

    except Exception as e:
        logger.error(f"画像認識中にエラーが発生しました: {e}")
        return {
            'status': 'error',
            'message': str(e),
            'extracted_text': '',
            'material_type': 'その他',
            'wood_type': '',
            'board_material_type': '',
            'panel_type': '',
            'material_size_1': '',
            'material_size_2': '',
            'material_size_3': '',
            'quantity': 0,
            'location': ''
        }
