from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models import Request, User, Material, WantedMaterial
import pytz
import logging
import re

try:
    from firebase_admin import messaging
except ModuleNotFoundError:
    messaging = None

api_notifications_bp = Blueprint("api_notifications", __name__)
JST = pytz.timezone("Asia/Tokyo")
logger = logging.getLogger(__name__)


def get_current_user():
    user_id = get_jwt_identity()
    return User.query.get(user_id)


# ------------------------------------------------------------------
# 1) Wanted 向け通知
# ------------------------------------------------------------------
@api_notifications_bp.route("/matching_wanted", methods=["GET"])
@jwt_required()
def get_matching_notifications_wanted():
    """
    欲しい資材(WantedMaterial) に関するマッチング通知を返す
    """
    cu = get_current_user()
    notifs: list[dict] = []

    # ① 送信側
    for r in Request.query.filter(
        Request.requester_user_id == cu.id,
        Request.wanted_material_id.isnot(None),
    ):
        if r.requested_at:
            notifs.append(
                {
                    "message": "資材が欲しい人にリクエストを送信しました（Wanted）",
                    "timestamp": r.requested_at.isoformat(),
                }
            )
        if r.accepted_at:
            notifs.append(
                {
                    "message": "送信したリクエストが承認されました（Wanted）\nチャットで受け渡しをしてください",
                    "timestamp": r.accepted_at.isoformat(),
                }
            )
        if r.rejected_at:
            notifs.append(
                {
                    "message": "送信したリクエストを取り消しました（Wanted）",
                    "timestamp": r.rejected_at.isoformat(),
                }
            )

    # ② 受信側
    for r in Request.query.filter(
        Request.requested_user_id == cu.id,
        Request.wanted_material_id.isnot(None),
    ):
        if r.requested_at:
            notifs.append(
                {
                    "message": "欲しい資材に新しいリクエストが届きました（Wanted）",
                    "timestamp": r.requested_at.isoformat(),
                }
            )
        if (
            r.accepted_at
            and r.wanted_material
            and r.wanted_material.user_id == cu.id
        ):
            notifs.append(
                {
                    "message": "登録した欲しい資材がマッチングしました（Wanted）\nチャットで受け渡し後、完了ボタンを押してください",
                    "timestamp": r.accepted_at.isoformat(),
                }
            )

    # ③ 完了イベント
    for r in Request.query.filter(
        Request.completed_at.isnot(None),
        Request.wanted_material_id.isnot(None),
        (Request.requester_user_id == cu.id)
        | (Request.requested_user_id == cu.id),
    ):
        notifs.append(
            {
                "message": "受け渡しが完了しました（Wanted）",
                "timestamp": r.completed_at.isoformat(),
            }
        )

    notifs.sort(key=lambda x: x["timestamp"], reverse=True)
    return jsonify(notifs), 200


# ------------------------------------------------------------------
# 2) Give 向け通知
# ------------------------------------------------------------------
@api_notifications_bp.route("/matching_give", methods=["GET"])
@jwt_required()
def get_matching_notifications_give():
    """
    あげる資材(Material) に関するマッチング通知を返す
    """
    cu = get_current_user()
    notifs: list[dict] = []

    # ① 送信側
    for r in Request.query.filter(
        Request.requester_user_id == cu.id, Request.material_id.isnot(None)
    ):
        if r.requested_at:
            notifs.append(
                {
                    "message": "資材をあげる相手にリクエストを送信しました（Give）",
                    "timestamp": r.requested_at.isoformat(),
                }
            )
        if r.accepted_at:
            notifs.append(
                {
                    "message": "送信したリクエストが承認されました（Give）\nチャットで受け渡しをしてください",
                    "timestamp": r.accepted_at.isoformat(),
                }
            )
        if r.rejected_at:
            notifs.append(
                {
                    "message": "送信したリクエストを取り消しました（Give）",
                    "timestamp": r.rejected_at.isoformat(),
                }
            )

    # ② 受信側
    for r in Request.query.filter(
        Request.requested_user_id == cu.id, Request.material_id.isnot(None)
    ):
        if r.requested_at:
            notifs.append(
                {
                    "message": "あげる資材に新しいリクエストが届きました（Give）",
                    "timestamp": r.requested_at.isoformat(),
                }
            )
        if r.accepted_at and r.material and r.material.user_id == cu.id:
            notifs.append(
                {
                    "message": "登録したあげる資材がマッチングしました（Give）\nチャットで受け渡し後、完了ボタンを押してください",
                    "timestamp": r.accepted_at.isoformat(),
                }
            )

    # ③ 完了イベント
    for r in Request.query.filter(
        Request.completed_at.isnot(None),
        Request.material_id.isnot(None),
        (Request.requester_user_id == cu.id) | (Request.requested_user_id == cu.id),
    ):
        notifs.append(
            {
                "message": "受け渡しが完了しました（Give）",
                "timestamp": r.completed_at.isoformat(),
            }
        )

    notifs.sort(key=lambda x: x["timestamp"], reverse=True)
    return jsonify(notifs), 200


# ------------------------------------------------------------------
# 3) 取引ステータス更新 → 相手に Push
# ------------------------------------------------------------------
@api_notifications_bp.route("/match_status_changed", methods=["POST"])
@jwt_required()
def notify_match_status_changed():
    """
    Body: { "path": "/pre_complete_material/123" }
    """
    if messaging is None:
        logger.warning("firebase_admin 未初期化。通知をスキップ")
        return jsonify({"message": "push skipped"}), 200

    body_json = request.get_json(silent=True) or {}
    path = body_json.get("path")
    if not path:
        return jsonify({"message": "path required"}), 400

    # ------------------------------------------------------------------
    #   ① pre/complete                        （既存）
    #   ② accept_request_<kind>/<id>          （承諾）
    #   ③ reject_request_<kind>/<id>          （拒否）
    #   ④ cancel_request/<id>                 （依頼者がキャンセル）
    # ------------------------------------------------------------------
    m = re.match(
        r"^/(?:(pre_complete|complete_match|accept_request|reject_request)_(material|wanted)|cancel_request)/(\d+)$",
        path,
    )
    if not m:
        return jsonify({"message": "invalid path"}), 400

    action, kind, mid_str = m.groups()

    # まず current_user を取得しておく（ここより前で使わない！）
    cu = get_current_user()
    if not cu:
        return jsonify({"message": "unauthorized"}), 401

    # ──────────────────────────────
    #   すべての値が確定してからデバッグ出力
    # ──────────────────────────────
    logger.info(
        "match_status_changed: path=%s user=%s action=%s kind=%s mid=%s",
        path, cu.id, action, kind, mid_str
    )

    req = Request.query.get(int(mid_str))

    if not req:                           # 主キーで取れなかったら…
        if kind == "material":
            req = (Request.query
                   .filter(Request.material_id == int(mid_str),
                           Request.status.in_(["Accepted", "Completed"]))
                   .first())
        elif kind == "wanted":
            req = (Request.query
                   .filter(Request.wanted_material_id == int(mid_str),
                           Request.status.in_(["Accepted", "Completed"]))
                   .first())
    if not req:
        return jsonify({"message": "match not found"}), 404

    if cu.id == req.requester_user_id:
        counterpart_id = req.requested_user_id
    elif cu.id == req.requested_user_id:
        counterpart_id = req.requester_user_id
    else:
        return jsonify({"message": "no permission"}), 403

    user = User.query.get(counterpart_id)
    tokens = user.device_tokens if user and user.device_tokens else []
    if not tokens:
        logger.info("User %s にトークン無し、スキップ", counterpart_id)
        return jsonify({"message": "no token"}), 200

    # -----------------------------
    #   通知メッセージ
    # -----------------------------
    title = "取引状況が更新されました"
    if action == "pre_complete":
        body = "相手が一次完了ボタンを押しました。確認してください。"
    elif action == "complete_match":
        body = "取引が最終完了しました。お疲れさまでした。"
    elif action == "accept_request":
        body = "あなたのリクエストが承認されました。チャットで調整しましょう！"
    elif action in ("reject_request",) or path.startswith("/cancel_request"):
        body = "リクエストが拒否されました。"
    else:
        body = "取引ステータスが更新されました。"
    payload = {
        "matchId": str(mid_str),
        # kind が None（cancel_request）の場合は前回互換のため false 扱い
        "isGive": str((kind or "material") == "material").lower(),
    }

    ok = 0
    for tkn in tokens:
        try:
            messaging.send(
                messaging.Message(
                    token=tkn,
                    notification=messaging.Notification(title=title, body=body),
                    data=payload,
                )
            )
            ok += 1
        except Exception as ex:
            logger.error("FCM send error (%s…): %s", tkn[:10], ex)

    return jsonify({"message": f"notification sent: {ok}/{len(tokens)}"}), 200

# ────────────────────────────────────────────────
#   /api/notifications/request_sent
#   リクエスト送信時のプッシュ通知
# ────────────────────────────────────────────────
@api_notifications_bp.route("/request_sent", methods=["POST"])
@jwt_required()
def notify_request_sent():
    """
    body 例:
      {
        "materialId": "123"       # ← Give(材料) へのリクエスト
        # もしくは
        "wantedId":  "456"       # ← Wanted へのリクエスト
      }
    """
    if messaging is None:
        logger.warning("firebase_admin 未初期化。通知をスキップ")
        return jsonify({"message": "push skipped"}), 200

    data = request.get_json(silent=True) or {}
    material_id = data.get("materialId")
    wanted_id   = data.get("wantedId")

    # どちらも無い／両方ある場合はエラー
    if bool(material_id) == bool(wanted_id):
        return jsonify({"message": "materialId か wantedId のいずれか一方を指定してください"}), 400

    # --------------------------------------------------------------------
    # 対象データの取得と権限チェック
    # --------------------------------------------------------------------
    if material_id:
        target = Material.query.get(material_id)
        if not target:
            return jsonify({"message": "material not found"}), 404
        receiver_id = target.user_id         # 資材登録者
        is_give     = True
    else:
        target = WantedMaterial.query.get(wanted_id)
        if not target:
            return jsonify({"message": "wanted material not found"}), 404
        receiver_id = target.user_id         # 希望登録者
        is_give     = False

    current_user = get_current_user()
    if current_user.id == receiver_id:
        # 自分自身には通知しない
        return jsonify({"message": "no need to notify self"}), 200

    # --------------------------------------------------------------------
    # プッシュ通知送信
    # --------------------------------------------------------------------
    receiver = User.query.get(receiver_id)
    tokens   = receiver.device_tokens if receiver and receiver.device_tokens else []

    if not tokens:
        logger.info("User %s にトークン無し、通知スキップ", receiver_id)
        return jsonify({"message": "no token"}), 200

    title = "新しいリクエストが届きました"
    body  = "あなたの資材にリクエストが届いています。内容を確認してください。"

    payload = {
        # フロントで画面遷移する際の判定用
        "materialId": str(material_id) if material_id else "",
        "wantedId"  : str(wanted_id)   if wanted_id  else "",
        "isGive"    : str(is_give).lower()           # "true" / "false"
    }

    sent = 0
    for tkn in tokens:
        try:
            messaging.send(
                messaging.Message(
                    token=tkn,
                    notification=messaging.Notification(title=title, body=body),
                    data=payload,
                )
            )
            sent += 1
        except Exception as ex:
            logger.error("FCM send error (%s…): %s", tkn[:10], ex)

    return jsonify({"message": f"notification sent: {sent}/{len(tokens)}"}), 200
