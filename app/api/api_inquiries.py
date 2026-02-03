# app/api/api_inquiries.py

import re
from flask import Blueprint, request, jsonify
from app import db
from app.models import Inquiry

# __init__.py で
# app.register_blueprint(api_inquiries_bp, url_prefix='/api/inquiries')
# として使う前提
api_inquiries_bp = Blueprint("api_inquiries", __name__)


def _looks_like_email(s: str) -> bool:
    s = (s or "").strip()
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", s))


def _extract_user_id_from_jwt() -> int | None:
    """
    JWT が付いていれば user_id を取りたい場合の optional 実装。
    既存プロジェクトの JWT identity 形式が「int」でも「dict」でも壊れないようにする。
    """
    try:
        from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
    except Exception:
        return None

    try:
        # JWT が無くても OK（任意）
        verify_jwt_in_request(optional=True)
        identity = get_jwt_identity()
        if identity is None:
            return None

        # identity が int / str
        if isinstance(identity, int):
            return identity
        if isinstance(identity, str):
            return int(identity) if identity.isdigit() else None

        # identity が dict っぽいケース（例: {"id": 123}）
        if isinstance(identity, dict):
            v = identity.get("id") or identity.get("user_id")
            if isinstance(v, int):
                return v
            if isinstance(v, str):
                return int(v) if v.isdigit() else None

        return None
    except Exception:
        # JWT 周りで何かあっても問い合わせ自体は受け付けたい
        return None


@api_inquiries_bp.route("", methods=["POST"], strict_slashes=False)
def create_inquiry():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"message": "JSON の形式が不正です"}), 400

    name = str(data.get("name", "")).strip()
    email = str(data.get("email", "")).strip()
    phone = str(data.get("phone", "")).strip()
    message = str(data.get("message", "")).strip()
    source = str(data.get("source", "")).strip() or None

    if not name:
        return jsonify({"message": "名前を入力してください"}), 400
    if not email or not _looks_like_email(email):
        return jsonify({"message": "有効なメールアドレスを入力してください"}), 400
    if not phone:
        return jsonify({"message": "電話番号を入力してください"}), 400
    if not message:
        return jsonify({"message": "メッセージを入力してください"}), 400

    user_id = _extract_user_id_from_jwt()

    inquiry = Inquiry(
        user_id=user_id,
        name=name,
        email=email,
        phone=phone,
        message=message,
        source=source,
    )
    db.session.add(inquiry)
    db.session.commit()

    return jsonify(
        {
            "message": "ok",
            "inquiry_id": inquiry.id,
        }
    ), 201
