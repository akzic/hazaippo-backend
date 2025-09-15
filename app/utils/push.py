"""
Firebase Cloud Messaging で送る Push 通知ユーティリティ

 1. リクエスト受信         … send_request_push
 2. 自動承認               … send_request_push(auto_accepted=True)
 3. 手動承認               … send_accept_push
 4. 一次完了               … send_precomplete_push
 5. 最終完了               … send_complete_push

環境変数 GOOGLE_APPLICATION_CREDENTIALS は
サービスアカウント JSON の絶対パスを指してください。
"""
from __future__ import annotations

import os
from typing import Sequence

from flask import current_app
from firebase_admin import credentials, initialize_app, messaging, _apps  # type: ignore
from app.models import User, Request

# ───────────────────── Firebase Admin 初期化 ─────────────────────
if not _apps:
    cred_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not cred_file or not os.path.exists(cred_file):
        raise RuntimeError("GOOGLE_APPLICATION_CREDENTIALS が未設定かパス不正")
    import json, pathlib
    project_id = os.getenv("FIREBASE_PROJECT_ID") \
        or json.loads(pathlib.Path(cred_path).read_text())["project_id"]
    initialize_app(credentials.Certificate(cred_path), {"projectId": project_id})

# ───────────────────── 内部共通ヘルパ ─────────────────────
def _send_multicast(
    tokens: Sequence[str],
    title: str,
    body: str,
    data: dict[str, str],
) -> None:
    """複数トークンへ一斉送信（失敗しても raise しない）"""
    if not tokens:
        return

    msg = messaging.MulticastMessage(
        tokens=list(tokens),
        notification=messaging.Notification(title=title, body=body),
        data=data,
    )
    try:
        res = messaging.send_multicast(msg)
        current_app.logger.info(
            f"FCM multicast sent: success={res.success_count}, fail={res.failure_count}"
        )
    except Exception as ex:  # pragma: no cover
        current_app.logger.exception(f"FCM send error: {ex}")


# ───────────────────── 1) 新規リクエスト / 自動承認 ─────────────────────
def send_request_push(request: Request, *, auto_accepted: bool = False) -> None:
    target = User.query.get(request.requested_user_id)
    if not target or not target.device_tokens:
        return

    sender = User.query.get(request.requester_user_id)
    sender_name = sender.contact_name if sender else "誰か"

    if auto_accepted:
        title = "リクエストが承認されました"
        body = f"{sender_name} さんとの取引が開始されました。"
        route = "/incomplete_match"
    else:
        title = "新しいリクエストが届きました"
        body = f"{sender_name} さんから資材リクエストがあります。"
        route = "/requests"

    data = {
        "route": route,
        "request_id": str(request.id),
        "kind": "wanted" if request.wanted_material_id else "material",
    }
    _send_multicast(target.device_tokens, title, body, data)


# ───────────────────── 2) 手動承認 ─────────────────────
def send_accept_push(request: Request) -> None:
    target = User.query.get(request.requester_user_id)
    if not target or not target.device_tokens:
        return

    accepter = User.query.get(request.requested_user_id)
    accepter_name = accepter.contact_name if accepter else "相手"

    title = "あなたのリクエストが承認されました"
    body = f"{accepter_name} さんがリクエストを承認しました。取引を開始してください。"
    data = {
        "route": "/incomplete_match",
        "request_id": str(request.id),
        "kind": "wanted" if request.wanted_material_id else "material",
    }
    _send_multicast(target.device_tokens, title, body, data)


# ───────────────────── 3) 一次完了 ─────────────────────
def send_precomplete_push(request: Request) -> None:
    target = User.query.get(request.requester_user_id)
    if not target or not target.device_tokens:
        return

    title = "取引が一次完了しました"
    body = "受け渡し後、完了ボタンを押してください。"
    data = {
        "route": "/matches",
        "request_id": str(request.id),
        "kind": "wanted" if request.wanted_material_id else "material",
    }
    _send_multicast(target.device_tokens, title, body, data)


# ───────────────────── 4) 最終完了 ─────────────────────
def send_complete_push(request: Request) -> None:
    target = User.query.get(request.requested_user_id)
    if not target or not target.device_tokens:
        return

    is_mat = bool(request.material_id)
    route = "/list/give" if is_mat else "/list/wanted"

    title = "取引が完了しました"
    body = "取引が最終完了しました。履歴は完了済みタブに移動しました。"
    data = {
        "route": route,
        "id": str(request.material_id or request.wanted_material_id),
    }
    _send_multicast(target.device_tokens, title, body, data)
