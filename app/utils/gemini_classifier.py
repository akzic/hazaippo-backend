# app/utils/gemini_classifier.py
# ----------------------------------------------------------
#  Gemini Flash 画像分類ユーティリティ   (google-generativeai 0.5.x)
# ----------------------------------------------------------
from __future__ import annotations
import os, re, json, logging
from typing import List, Dict

import google.generativeai as genai

logger = logging.getLogger(__name__)

# ── 認証 ──────────────────────────────────────────────
_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=_API_KEY)

# ── 使用モデルを決定（2.5-flash が無ければ 2.0-flash）────────────
def _best_flash() -> str:
    try:
        models = [m.name for m in genai.list_models() if m.name.endswith("-flash")]
        if not models:
            return "models/gemini-2.5-flash"
        def ver(m): return float(re.search(r'(\d+(?:\.\d+)?)', m).group(1))
        return max(models, key=ver)
    except Exception as e:
        logger.warning(f"モデル一覧取得失敗: {e}")
        return "models/gemini-2.5-flash"

_MODEL_ID = _best_flash()
logger.info(f"★ 使用モデル: {_MODEL_ID}")

# ── ラベル定義 ───────────────────────────────────────
_CATEGORIES = ["木材", "軽量鉄骨", "ボード材", "パネル材", "その他"]
_SUBTYPES: Dict[str, List[str]] = {
    "木材":   ["無垢材", "集成材（積層材）", "広葉樹", "針葉樹", "その他"],
    "ボード材": ["プラスターボード", "強化ボード", "耐火ボード", "耐水(防水)ボード", "その他"],
    "パネル材": ["キッチンパネル", "化粧板", "その他"],
}

_PROMPT = f"""
あなたは建築材料鑑定AIです。以下の形式で **JSON のみ** 日本語で返答してください。

{{
 "material_type": <カテゴリ>,
 "subtype": <サブタイプまたは空文字>,
 "size_1": <長さmmまたは空文字>,
 "size_2": <幅mmまたは空文字>,
 "size_3": <厚さmmまたは空文字>,
 "quantity": <整数または空文字>
}}

カテゴリ候補: {", ".join(_CATEGORIES)}
サブタイプ候補:
- 木材: {", ".join(_SUBTYPES["木材"])}
- ボード材: {", ".join(_SUBTYPES["ボード材"])}
- パネル材: {", ".join(_SUBTYPES["パネル材"])}
軽量鉄骨・その他の場合は "subtype" を空文字にしてください。
サイズ・数量が推定不能なら空文字。
""".strip()

# ── 画像分類関数 ────────────────────────────────────
def classify_image(image_path: str) -> dict:
    """
    画像を Gemini Flash に送り、結果 dict を返す。
    * 0.5.x で response_format が無い場合はテキストを自力で JSON パース
    """
    try:
        with open(image_path, "rb") as f:
            img_bytes = f.read()

        image_blob = {"mime_type": "image/jpeg", "data": img_bytes}

        model = genai.GenerativeModel(_MODEL_ID)

        # --- JSON ダイレクト返却を試みる ------------------------
        try:
            resp = model.generate_content(
                [image_blob, _PROMPT],
                response_format="json_object",
            )
            payload = resp  # 0.6.x 互換: 既に dict
        except TypeError:
            # 旧 SDK: response_format 未対応 → 普通のテキストで返る
            resp = model.generate_content([image_blob, _PROMPT])
            txt = resp.text if hasattr(resp, "text") else str(resp)
            txt = re.sub(r"```json|```", "", txt, flags=re.I).strip()
            m = re.search(r"\{.*\}", txt, re.S)
            payload = json.loads(m.group(0) if m else txt)

        payload["status"] = "success"
        return payload

    except Exception as e:
        logger.error(f"Gemini 分類エラー: {e}")
        return {
            "status": "error",
            "message": str(e),
            "material_type": "その他",
            "subtype": "",
            "size_1": "", "size_2": "", "size_3": "",
            "quantity": ""
        }
