# app/blueprints/assetlinks.py
import os
from flask import Blueprint, current_app, send_from_directory, abort

assetlinks_bp = Blueprint("assetlinks", __name__)

@assetlinks_bp.route("/.well-known/assetlinks.json")
def assetlinks():
    """Android App Links 用の宣言 JSON を返すだけ"""
    root = os.path.join(current_app.root_path, "static", ".well-known")
    json_path = os.path.join(root, "assetlinks.json")
    if not os.path.exists(json_path):
        abort(404)
    return send_from_directory(root, "assetlinks.json", mimetype="application/json")
