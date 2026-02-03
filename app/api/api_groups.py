from datetime import datetime, timedelta
import pytz
import re
import secrets

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload

from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from app import db
from app.models import User, UserGroup, GroupMembership, GroupRole, Material

# ✅ 追加：Request（Flask の request と衝突するので alias）
from app.models import Request as MaterialRequest

# S3（資材と同じ運用に揃える：DBにはキー、レスポンスではURLも返す）
try:
    from app.utils.s3_uploader import upload_file_to_s3, build_s3_url
except Exception:  # noqa
    upload_file_to_s3 = None
    build_s3_url = None

JST = pytz.timezone("Asia/Tokyo")
api_groups_bp = Blueprint("api_groups", __name__, url_prefix="/api/groups")

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "heic", "heif"}


# ────────────── ユーティリティ ──────────────
def get_current_user():
    user_id = get_jwt_identity()
    if not user_id:
        return None
    return User.query.get(int(user_id))


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _pick(data: dict, *keys, default=None):
    for k in keys:
        if k in data and data.get(k) is not None:
            return data.get(k)
    return default


def _norm_str(v):
    if v is None:
        return None
    return str(v).strip()


def _empty_to_none(v):
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _to_int(v, default=None):
    if v is None:
        return default
    if isinstance(v, int):
        return v
    try:
        return int(str(v).strip())
    except Exception:
        return default


def _to_color_int(v, default=None):
    """
    Flutter Color.value 想定：
    - int
    - "4292076357" みたいな数字文字列
    - "0xFFD66A35" みたいな16進文字列
    - "#D66A35" の場合は 0xFF を補完して ARGB にする
    """
    if v is None:
        return default
    if isinstance(v, int):
        return v

    s = str(v).strip()
    if not s:
        return default

    if re.match(r"^0x[0-9a-fA-F]+$", s):
        try:
            return int(s, 16)
        except Exception:
            return default

    if re.match(r"^#[0-9a-fA-F]{6}$", s):
        try:
            return int("0xFF" + s[1:], 16)
        except Exception:
            return default

    try:
        return int(s)
    except Exception:
        return default


def _to_image_url(key_or_url: str | None):
    """
    DBに S3キー（例: groups/xxx.jpg）が入っていれば build_s3_url でURL化。
    既にURLが入っている既存データもそのまま返す（互換維持）。
    """
    if not key_or_url:
        return None
    s = str(key_or_url).strip()
    if not s:
        return None
    if s.startswith(("http://", "https://")):
        return s
    return build_s3_url(s) if build_s3_url else s


# 既存コード互換：ユーザー画像などで呼ばれているので残す
def _maybe_image_url(value: str | None):
    return _to_image_url(value)


def _visible_group_name(group: UserGroup) -> str:
    gn = getattr(group, "group_name", None)
    if gn and str(gn).strip():
        return str(gn).strip()
    return str(group.name).strip()


def _get_membership(group_id: int, user_id: int):
    return GroupMembership.query.filter_by(group_id=group_id, user_id=user_id).first()


def _role_to_str(role) -> str | None:
    if role is None:
        return None
    return role.value if hasattr(role, "value") else str(role)


def _is_admin(group: UserGroup, user: User) -> bool:
    if not user or not group:
        return False
    if user.id == group.owner_user_id:
        return True
    mem = _get_membership(group.id, user.id)
    if not mem:
        return False
    return _role_to_str(mem.role) == GroupRole.ADMIN.value


def _member_count_map(group_ids: list[int]) -> dict[int, int]:
    if not group_ids:
        return {}
    rows = (
        db.session.query(
            GroupMembership.group_id,
            func.count(GroupMembership.user_id).label("cnt"),
        )
        .filter(GroupMembership.group_id.in_(group_ids))
        .group_by(GroupMembership.group_id)
        .all()
    )
    return {int(gid): int(cnt) for gid, cnt in rows}


def _group_to_dict(
    group: UserGroup,
    user: User = None,
    role: str | None = None,
    member_count: int | None = None,
    owner: User | None = None,
) -> dict:
    visible_name = _visible_group_name(group)

    # DB保存値（S3キー想定）
    group_image_key = getattr(group, "group_image", None)
    cover_image_key = getattr(group, "cover_image", None)

    # 返却用URL（表示用）
    group_image_url = _to_image_url(group_image_key)
    cover_image_url = _to_image_url(cover_image_key)

    color_val = getattr(group, "group_color", None)
    try:
        color_val = int(color_val) if color_val is not None else None
    except Exception:
        color_val = None

    data = {
        "id": group.id,
        "name": group.name,
        "group_name": getattr(group, "group_name", None) or None,
        "description": group.description,
        "owner_user_id": group.owner_user_id,
        "created_at": group.created_at.isoformat() if group.created_at else None,
        "deleted_at": group.deleted_at.isoformat() if group.deleted_at else None,

        # 画像：DB保存値（キー）と、表示用URLを両方返す
        "group_image": group_image_key,
        "group_image_url": group_image_url,
        "cover_image": cover_image_key,
        "cover_image_url": cover_image_url,

        "group_color": color_val,

        # 集計
        "member_count": member_count,

        # 表示用
        "display_name": visible_name,
    }

    if owner:
        data["owner_company_name"] = owner.company_name
        data["owner_contact_name"] = owner.contact_name

    if user:
        data["is_owner"] = (group.owner_user_id == user.id)

        # ✅ ここが重要：role は membership から取る
        # ただし「オーナーなのに membership が無い」古いデータでも admin 扱いにする
        if role is None:
            mem = _get_membership(group.id, user.id)
            role = _role_to_str(mem.role) if mem else None
            if role is None and group.owner_user_id == user.id:
                role = GroupRole.ADMIN.value

        data["role"] = role

    # camelCase も併記（Flutter側互換）
    data["groupName"] = data["group_name"] or data["name"]

    # 互換維持：groupImage は「表示用URL」
    data["groupImageKey"] = data["group_image"]
    data["coverImageKey"] = data["cover_image"]
    data["groupImageUrl"] = data["group_image_url"]
    data["coverImageUrl"] = data["cover_image_url"]
    data["groupImage"] = data["group_image_url"]
    data["coverImage"] = data["cover_image_url"]

    data["groupColor"] = data["group_color"]
    data["memberCount"] = data["member_count"]

    return data


def _serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])


def _make_invite_token(group_id: int, inviter_user_id: int, role: str, expires_at: datetime) -> str:
    payload = {
        "gid": group_id,
        "iid": inviter_user_id,
        "role": role,
        "exp": expires_at.isoformat(),
        "nonce": secrets.token_hex(8),
    }
    return _serializer().dumps(payload, salt="group-invite")


def _load_invite_token(token: str, max_age_days: int = 365):
    try:
        data = _serializer().loads(token, salt="group-invite", max_age=max_age_days * 86400)
    except SignatureExpired:
        return None, "招待リンクの有効期限が切れています"
    except BadSignature:
        return None, "招待リンクが無効です"

    exp_raw = data.get("exp")
    if not exp_raw:
        return None, "招待リンクが無効です"
    exp = datetime.fromisoformat(exp_raw)
    if exp.tzinfo is None:
        exp = JST.localize(exp)
    now = datetime.now(JST)
    if now > exp:
        return None, "招待リンクの有効期限が切れています"

    return data, None


def _get_request_data():
    if request.is_json:
        return request.get_json(silent=True) or {}
    return request.form.to_dict() or {}


def _upload_group_images_if_any():
    if request.is_json:
        return None, None

    if not request.files:
        return None, None

    if upload_file_to_s3 is None:
        if (request.files.get("group_image") or request.files.get("groupImage") or
                request.files.get("cover_image") or request.files.get("coverImage")):
            raise RuntimeError("upload_file_to_s3 is not available")
        return None, None

    group_image_key = None
    cover_image_key = None

    f1 = request.files.get("group_image") or request.files.get("groupImage")
    if f1 and getattr(f1, "filename", ""):
        if not allowed_file(f1.filename):
            raise ValueError("group_image invalid format")
        group_image_key = upload_file_to_s3(f1, folder="groups")

    f2 = request.files.get("cover_image") or request.files.get("coverImage")
    if f2 and getattr(f2, "filename", ""):
        if not allowed_file(f2.filename):
            raise ValueError("cover_image invalid format")
        cover_image_key = upload_file_to_s3(f2, folder="groups")

    return group_image_key, cover_image_key


# ────────────── グループ一覧（所属しているアクティブグループ） ──────────────
@api_groups_bp.route("/", methods=["GET"])
@jwt_required()
def list_groups():
    user = get_current_user()
    if not user:
        return jsonify({"message": "認証に失敗しました"}), 401

    # ✅ member/admin どちらも取得
    # ✅ 古いデータで「owner なのに membership が無い」場合も拾うため outerjoin + OR
    rows = (
        db.session.query(UserGroup, GroupMembership.role)
        .outerjoin(
            GroupMembership,
            (GroupMembership.group_id == UserGroup.id) & (GroupMembership.user_id == user.id),
        )
        .filter(
            UserGroup.deleted_at.is_(None),
            or_(
                GroupMembership.user_id == user.id,
                UserGroup.owner_user_id == user.id,
            ),
        )
        .order_by(UserGroup.created_at.desc())
        .all()
    )

    groups = [g for g, _r in rows]
    cnt_map = _member_count_map([g.id for g in groups])

    payload = []
    for g, r in rows:
        payload.append(
            _group_to_dict(
                g,
                user=user,
                role=_role_to_str(r),
                member_count=cnt_map.get(g.id, 0),
            )
        )
    return jsonify(payload), 200


# ────────────── グループ詳細取得 ──────────────
@api_groups_bp.route("/<int:group_id>", methods=["GET"])
@jwt_required()
def get_group_detail(group_id: int):
    user = get_current_user()
    if not user:
        return jsonify({"message": "認証に失敗しました"}), 401

    group = UserGroup.query.get_or_404(group_id)
    if group.deleted_at:
        return jsonify({"message": "グループは存在しません"}), 404

    mem = _get_membership(group.id, user.id)
    if not mem and group.owner_user_id != user.id:
        return jsonify({"message": "参加していません"}), 403

    owner = User.query.get(group.owner_user_id)
    cnt_map = _member_count_map([group.id])
    role = _role_to_str(mem.role) if mem else (GroupRole.ADMIN.value if group.owner_user_id == user.id else None)

    return jsonify(
        _group_to_dict(
            group,
            user=user,
            role=role,
            member_count=cnt_map.get(group.id, 0),
            owner=owner,
        )
    ), 200


# ────────────── グループ作成（登録） ──────────────
@api_groups_bp.route("/", methods=["POST"])
@jwt_required()
def create_group():
    user = get_current_user()
    if not user:
        return jsonify({"message": "認証に失敗しました"}), 401

    data = _get_request_data()

    name = _norm_str(_pick(data, "name", "group_name", "groupName")) or ""
    description = _norm_str(_pick(data, "description")) or ""

    group_name = _empty_to_none(_pick(data, "group_name", "groupName"))

    group_image_str = _pick(data, "group_image", "groupImage")
    group_image_str = _empty_to_none(group_image_str)

    cover_image_str = _pick(data, "cover_image", "coverImage")
    cover_image_str = _empty_to_none(cover_image_str)

    group_color = _to_color_int(_pick(data, "group_color", "groupColor"))

    if not name.strip():
        return jsonify({"message": "グループ名は必須です"}), 400

    visible_name = (group_name or name).strip()

    dup = (
        UserGroup.query
        .filter(
            UserGroup.deleted_at.is_(None),
            func.lower(func.coalesce(getattr(UserGroup, "group_name", UserGroup.name), UserGroup.name)) == visible_name.lower(),
        )
        .first()
    )
    if dup:
        return jsonify({"message": "同じグループ名が既に存在します"}), 409

    try:
        group_image_key, cover_image_key = _upload_group_images_if_any()
    except ValueError as ve:
        msg = str(ve)
        if "group_image" in msg:
            return jsonify({"message": "group_image のファイル形式が無効です"}), 400
        if "cover_image" in msg:
            return jsonify({"message": "cover_image のファイル形式が無効です"}), 400
        return jsonify({"message": "画像ファイルが無効です"}), 400
    except RuntimeError:
        return jsonify({"message": "画像アップロードの設定が未完了です（S3）"}), 500
    except Exception as e:
        current_app.logger.error(f"[create_group] image upload error: {e}", exc_info=True)
        return jsonify({"message": "画像処理中にエラーが発生しました"}), 500

    group = UserGroup(
        name=name.strip(),
        description=description.strip() if description else None,
        owner_user_id=user.id,
    )

    if hasattr(group, "group_name"):
        group.group_name = group_name

    if hasattr(group, "group_image"):
        group.group_image = group_image_key or group_image_str
    if hasattr(group, "cover_image"):
        group.cover_image = cover_image_key or cover_image_str

    if hasattr(group, "group_color"):
        group.group_color = group_color

    db.session.add(group)
    db.session.flush()

    db.session.add(
        GroupMembership(
            group_id=group.id,
            user_id=user.id,
            role=GroupRole.ADMIN,
        )
    )
    db.session.commit()

    cnt_map = _member_count_map([group.id])
    return jsonify(
        _group_to_dict(
            group,
            user=user,
            role=GroupRole.ADMIN.value,
            member_count=cnt_map.get(group.id, 1),
            owner=user,
        )
    ), 201


# ────────────── グループ編集（更新） ──────────────
@api_groups_bp.route("/<int:group_id>", methods=["PUT"])
@jwt_required()
def update_group(group_id: int):
    user = get_current_user()
    if not user:
        return jsonify({"message": "認証に失敗しました"}), 401

    group = UserGroup.query.get_or_404(group_id)
    if group.deleted_at:
        return jsonify({"message": "グループは存在しません"}), 404

    if not _is_admin(group, user):
        return jsonify({"message": "権限がありません"}), 403

    data = _get_request_data()

    new_name = _norm_str(_pick(data, "name")) or group.name
    new_desc = _pick(data, "description")
    new_desc = _norm_str(new_desc) if new_desc is not None else group.description

    new_group_name = _pick(data, "group_name", "groupName")
    new_group_name = _empty_to_none(new_group_name) if new_group_name is not None else getattr(group, "group_name", None)

    new_group_image = _pick(data, "group_image", "groupImage")
    new_group_image = _empty_to_none(new_group_image) if new_group_image is not None else getattr(group, "group_image", None)

    new_cover_image = _pick(data, "cover_image", "coverImage")
    new_cover_image = _empty_to_none(new_cover_image) if new_cover_image is not None else getattr(group, "cover_image", None)

    new_group_color = _pick(data, "group_color", "groupColor")
    new_group_color = _to_color_int(new_group_color) if new_group_color is not None else getattr(group, "group_color", None)

    visible_name = (new_group_name or new_name).strip()

    dup = (
        UserGroup.query
        .filter(
            UserGroup.id != group.id,
            UserGroup.deleted_at.is_(None),
            func.lower(func.coalesce(getattr(UserGroup, "group_name", UserGroup.name), UserGroup.name)) == visible_name.lower(),
        )
        .first()
    )
    if dup:
        return jsonify({"message": "同じグループ名が既に存在します"}), 409

    try:
        uploaded_group_key, uploaded_cover_key = _upload_group_images_if_any()
    except ValueError as ve:
        msg = str(ve)
        if "group_image" in msg:
            return jsonify({"message": "group_image のファイル形式が無効です"}), 400
        if "cover_image" in msg:
            return jsonify({"message": "cover_image のファイル形式が無効です"}), 400
        return jsonify({"message": "画像ファイルが無効です"}), 400
    except RuntimeError:
        return jsonify({"message": "画像アップロードの設定が未完了です（S3）"}), 500
    except Exception as e:
        current_app.logger.error(f"[update_group] image upload error: {e}", exc_info=True)
        return jsonify({"message": "画像処理中にエラーが発生しました"}), 500

    group.name = new_name.strip()
    group.description = new_desc.strip() if isinstance(new_desc, str) and new_desc.strip() else (new_desc if new_desc else None)

    if hasattr(group, "group_name"):
        group.group_name = new_group_name

    if hasattr(group, "group_image"):
        group.group_image = uploaded_group_key or new_group_image
    if hasattr(group, "cover_image"):
        group.cover_image = uploaded_cover_key or new_cover_image

    if hasattr(group, "group_color"):
        group.group_color = new_group_color

    db.session.commit()

    mem = _get_membership(group.id, user.id)
    role = _role_to_str(mem.role) if mem else None
    owner = User.query.get(group.owner_user_id)
    cnt_map = _member_count_map([group.id])

    return jsonify(_group_to_dict(group, user=user, role=role, member_count=cnt_map.get(group.id, 0), owner=owner)), 200


# ────────────── グループ削除（論理削除） ──────────────
@api_groups_bp.route("/<int:group_id>", methods=["DELETE"])
@jwt_required()
def delete_group(group_id: int):
    user = get_current_user()
    if not user:
        return jsonify({"message": "認証に失敗しました"}), 401

    group = UserGroup.query.get_or_404(group_id)
    if group.deleted_at:
        return jsonify({"message": "グループは存在しません"}), 404

    if not _is_admin(group, user):
        return jsonify({"message": "権限がありません"}), 403

    group.deleted_at = datetime.now(JST)
    db.session.commit()
    return jsonify({"message": "deleted"}), 200


# ────────────── 所属グループ一覧（joined） ──────────────
@api_groups_bp.route("/joined", methods=["GET"])
@jwt_required()
def joined_groups():
    user = get_current_user()
    if not user:
        return jsonify({"message": "認証に失敗しました"}), 401

    # ✅ member/admin どちらも取得
    # ✅ owner なのに membership が無い古いデータでも拾う
    rows = (
        db.session.query(UserGroup, GroupMembership.role)
        .outerjoin(
            GroupMembership,
            (GroupMembership.group_id == UserGroup.id) & (GroupMembership.user_id == user.id),
        )
        .filter(
            UserGroup.deleted_at.is_(None),
            or_(
                GroupMembership.user_id == user.id,
                UserGroup.owner_user_id == user.id,
            ),
        )
        .order_by(UserGroup.created_at.desc())
        .all()
    )

    groups = [g for g, _r in rows]
    cnt_map = _member_count_map([g.id for g in groups])

    payload = []
    for g, r in rows:
        payload.append(_group_to_dict(g, user=user, role=_role_to_str(r), member_count=cnt_map.get(g.id, 0)))

    return jsonify({"my_groups": payload}), 200


# ────────────── グループ参加（統合版 / 互換レスポンス） ──────────────
@api_groups_bp.route("/<int:group_id>/join", methods=["POST"])
@jwt_required()
def join_group(group_id: int):
    user = get_current_user()
    if not user:
        return jsonify({"message": "認証に失敗しました"}), 401

    group = UserGroup.query.get_or_404(group_id)
    if group.deleted_at:
        return jsonify({"message": "グループは存在しません"}), 404

    existing = _get_membership(group.id, user.id)
    if existing:
        role = _role_to_str(existing.role) or GroupRole.MEMBER.value
        return jsonify({
            "message": "既に参加しています",
            "joined": True,
            "group_id": group.id,
            "role": role,
        }), 200

    db.session.add(GroupMembership(group_id=group.id, user_id=user.id, role=GroupRole.MEMBER))
    db.session.commit()

    return jsonify({
        "message": "joined",
        "joined": True,
        "group_id": group.id,
        "role": GroupRole.MEMBER.value,
    }), 201


# ────────────── グループ退会（従来） ──────────────
@api_groups_bp.route("/<int:group_id>/leave", methods=["POST"])
@jwt_required()
def leave_group(group_id: int):
    user = get_current_user()
    if not user:
        return jsonify({"message": "認証に失敗しました"}), 401

    group = UserGroup.query.get_or_404(group_id)
    if group.deleted_at:
        return jsonify({"message": "グループは存在しません"}), 404

    mem = _get_membership(group_id, user.id)
    if not mem:
        return jsonify({"message": "参加していません"}), 404

    if group.owner_user_id == user.id:
        return jsonify({"message": "オーナーは退会できません"}), 403

    db.session.delete(mem)
    db.session.commit()
    return jsonify({"message": "left"}), 200

# ──────────────────────────────────────────────
#  ここから「先行追加」：招待リンク / メンバー管理
# ──────────────────────────────────────────────

# ────────────── 招待リンク生成 ──────────────
@api_groups_bp.route("/<int:group_id>/invite-link", methods=["POST"])
@jwt_required()
def generate_invite_link(group_id: int):
    """
    管理者のみ。
    body:
      - role: "member" or "admin"（基本は member 推奨。admin は必要時だけ）
      - expires_in_days: 例 7（省略時 7日）
    return:
      - invite_token
      - expires_at
      - role
      - group_id
    """
    user = get_current_user()
    if not user:
        return jsonify({"message": "認証に失敗しました"}), 401

    group = UserGroup.query.get_or_404(group_id)
    if group.deleted_at:
        return jsonify({"message": "グループは存在しません"}), 404

    if not _is_admin(group, user):
        return jsonify({"message": "権限がありません"}), 403

    data = request.get_json(silent=True) or {}
    role = (_pick(data, "role") or GroupRole.MEMBER.value).strip().lower()

    # admin招待は事故りやすいので一応制限（必要ならここを外す）
    if role not in (GroupRole.MEMBER.value, GroupRole.ADMIN.value):
        return jsonify({"message": "role は member/admin のみ指定可能です"}), 400

    expires_in_days = _to_int(_pick(data, "expires_in_days", "expiresInDays"), default=7)
    if expires_in_days <= 0 or expires_in_days > 365:
        return jsonify({"message": "expires_in_days は 1〜365 を指定してください"}), 400

    expires_at = datetime.now(JST) + timedelta(days=expires_in_days)
    token = _make_invite_token(group.id, user.id, role, expires_at)

    return jsonify({
        "group_id": group.id,
        "role": role,
        "expires_at": expires_at.isoformat(),
        "invite_token": token,
        # フロント側で自由にURL化してOK（例：hazaippo://invite?token=...）
        "hint": "この invite_token をアプリ側でURL化して共有してください",
    }), 200


# ────────────── 招待リンク受け入れ（参加） ──────────────
@api_groups_bp.route("/invite/accept", methods=["POST"])
@jwt_required()
def accept_invite_link():
    """
    body:
      - invite_token
    """
    user = get_current_user()
    if not user:
        return jsonify({"message": "認証に失敗しました"}), 401

    data = request.get_json(silent=True) or {}
    token = (_pick(data, "invite_token", "inviteToken") or "").strip()
    if not token:
        return jsonify({"message": "invite_token が必要です"}), 400

    payload, err = _load_invite_token(token)
    if err:
        return jsonify({"message": err}), 400

    group_id = _to_int(payload.get("gid"))
    inviter_id = _to_int(payload.get("iid"))
    role = (payload.get("role") or GroupRole.MEMBER.value).strip().lower()

    if not group_id:
        return jsonify({"message": "招待リンクが無効です"}), 400

    group = UserGroup.query.get(group_id)
    if not group or group.deleted_at:
        return jsonify({"message": "グループは存在しません"}), 404

    # 既に参加済み
    dup = _get_membership(group.id, user.id)
    if dup:
        owner = User.query.get(group.owner_user_id)
        cnt_map = _member_count_map([group.id])
        return jsonify({
            "message": "既に参加しています",
            "group": _group_to_dict(group, user=user, role=_role_to_str(dup.role), member_count=cnt_map.get(group.id, 0), owner=owner)
        }), 200

    # 招待ロール（admin招待は発行側で制限してるが、ここでも念のため保護）
    if role not in (GroupRole.MEMBER.value, GroupRole.ADMIN.value):
        role = GroupRole.MEMBER.value

    db.session.add(GroupMembership(group_id=group.id, user_id=user.id, role=GroupRole(role)))
    db.session.commit()

    owner = User.query.get(group.owner_user_id)
    cnt_map = _member_count_map([group.id])

    return jsonify({
        "message": "joined",
        "invited_by_user_id": inviter_id,
        "group": _group_to_dict(group, user=user, role=role, member_count=cnt_map.get(group.id, 0), owner=owner)
    }), 201


# ────────────── メンバー一覧 ──────────────
@api_groups_bp.route("/<int:group_id>/members", methods=["GET"])
@jwt_required()
def list_members(group_id: int):
    user = get_current_user()
    if not user:
        return jsonify({"message": "認証に失敗しました"}), 401

    group = UserGroup.query.get_or_404(group_id)
    if group.deleted_at:
        return jsonify({"message": "グループは存在しません"}), 404

    # 非公開想定：参加者のみ見れる
    mem = _get_membership(group.id, user.id)
    if not mem and group.owner_user_id != user.id:
        return jsonify({"message": "参加していません"}), 403

    # joined_at が無いモデルでも落ちないように防御（存在すれば joined_at で、なければ user_id で）
    try:
        order_col = GroupMembership.joined_at.asc()
        rows = (
            db.session.query(GroupMembership, User)
            .join(User, User.id == GroupMembership.user_id)
            .filter(GroupMembership.group_id == group.id)
            .order_by(order_col)
            .all()
        )
    except Exception:
        rows = (
            db.session.query(GroupMembership, User)
            .join(User, User.id == GroupMembership.user_id)
            .filter(GroupMembership.group_id == group.id)
            .order_by(GroupMembership.user_id.asc())
            .all()
        )

    payload = []
    for m, u in rows:
        joined_at = getattr(m, "joined_at", None)
        payload.append({
            "user_id": u.id,
            "email": u.email,
            "company_name": u.company_name,
            "contact_name": u.contact_name,
            "image": _maybe_image_url(getattr(u, "image", None)),
            "role": _role_to_str(m.role),
            "joined_at": joined_at.isoformat() if joined_at else None,
            "is_owner": (u.id == group.owner_user_id),
        })

    return jsonify({
        "group_id": group.id,
        "members": payload,
        "is_admin": _is_admin(group, user),
    }), 200


# ────────────── メンバー招待（= 既存ユーザーを追加） ──────────────
@api_groups_bp.route("/<int:group_id>/members", methods=["POST"])
@jwt_required()
def invite_member(group_id: int):
    """
    管理者のみ。
    body:
      - user_id もしくは email
      - role: "member" or "admin"（省略時 member）
    ※「ユーザーが存在しない」場合は 404 を返す（将来は pending 招待テーブルにしてもOK）
    """
    user = get_current_user()
    if not user:
        return jsonify({"message": "認証に失敗しました"}), 401

    group = UserGroup.query.get_or_404(group_id)
    if group.deleted_at:
        return jsonify({"message": "グループは存在しません"}), 404

    if not _is_admin(group, user):
        return jsonify({"message": "権限がありません"}), 403

    data = request.get_json(silent=True) or {}
    role = (_pick(data, "role") or GroupRole.MEMBER.value).strip().lower()
    if role not in (GroupRole.MEMBER.value, GroupRole.ADMIN.value):
        return jsonify({"message": "role は member/admin のみ指定可能です"}), 400

    target_user = None
    uid = _pick(data, "user_id", "userId")
    email = _pick(data, "email")
    if uid is not None:
        target_user = User.query.get(int(uid))
    elif email:
        target_user = User.query.filter(func.lower(User.email) == str(email).strip().lower()).first()

    if not target_user:
        return jsonify({"message": "招待対象ユーザーが見つかりません"}), 404

    if target_user.id == group.owner_user_id:
        return jsonify({"message": "オーナーは既にグループに存在します"}), 409

    dup = _get_membership(group.id, target_user.id)
    if dup:
        return jsonify({"message": "既に参加しています"}), 409

    db.session.add(GroupMembership(group_id=group.id, user_id=target_user.id, role=GroupRole(role)))
    db.session.commit()

    return jsonify({
        "message": "invited",
        "group_id": group.id,
        "user_id": target_user.id,
        "role": role,
    }), 201


# ────────────── メンバー削除 ──────────────
@api_groups_bp.route("/<int:group_id>/members/<int:member_user_id>", methods=["DELETE"])
@jwt_required()
def remove_member(group_id: int, member_user_id: int):
    """
    管理者のみ。
    - オーナーは削除不可
    - 自分を消したい場合は leave を使う（事故防止）
    """
    user = get_current_user()
    if not user:
        return jsonify({"message": "認証に失敗しました"}), 401

    group = UserGroup.query.get_or_404(group_id)
    if group.deleted_at:
        return jsonify({"message": "グループは存在しません"}), 404

    if not _is_admin(group, user):
        return jsonify({"message": "権限がありません"}), 403

    if member_user_id == group.owner_user_id:
        return jsonify({"message": "オーナーは削除できません"}), 403

    if member_user_id == user.id:
        return jsonify({"message": "自分を削除する場合は leave を使用してください"}), 400

    mem = _get_membership(group.id, member_user_id)
    if not mem:
        return jsonify({"message": "対象ユーザーは参加していません"}), 404

    db.session.delete(mem)
    db.session.commit()
    return jsonify({"message": "removed"}), 200


# ────────────── メンバーのロール変更（先行追加） ──────────────
@api_groups_bp.route("/<int:group_id>/members/<int:member_user_id>/role", methods=["PUT"])
@jwt_required()
def update_member_role(group_id: int, member_user_id: int):
    """
    管理者のみ。
    body:
      - role: "member" or "admin"
    """
    user = get_current_user()
    if not user:
        return jsonify({"message": "認証に失敗しました"}), 401

    group = UserGroup.query.get_or_404(group_id)
    if group.deleted_at:
        return jsonify({"message": "グループは存在しません"}), 404

    if not _is_admin(group, user):
        return jsonify({"message": "権限がありません"}), 403

    if member_user_id == group.owner_user_id:
        return jsonify({"message": "オーナーのロールは変更できません"}), 403

    data = request.get_json(silent=True) or {}
    role = (_pick(data, "role") or "").strip().lower()
    if role not in (GroupRole.MEMBER.value, GroupRole.ADMIN.value):
        return jsonify({"message": "role は member/admin のみ指定可能です"}), 400

    mem = _get_membership(group.id, member_user_id)
    if not mem:
        return jsonify({"message": "対象ユーザーは参加していません"}), 404

    mem.role = GroupRole(role)
    db.session.commit()
    return jsonify({"message": "updated", "role": role}), 200


def _material_to_dict_for_flutter(m: Material) -> dict:
    """
    Flutter(GiveMaterial) 側で拾いやすいように
    snake_case + camelCase を両方載せた安全レスポンスを返す
    """
    d = m.to_dict(include_user=True)

    # 画像URL（Material.image が S3キー前提）
    img = (d.get("image") or "").strip() if isinstance(d.get("image"), str) else ""
    if img:
        if img.startswith(("http://", "https://")):
            image_url = img
        else:
            image_url = build_s3_url(img) if build_s3_url else img
    else:
        image_url = None

    d["image_url"] = image_url
    d["imageUrl"] = image_url

    # size系（Flutter側で size1/size2/size3 を参照する想定）
    d["size1"] = d.get("size_1")
    d["size2"] = d.get("size_2")
    d["size3"] = d.get("size_3")

    # createdAt も併記
    d["createdAt"] = d.get("created_at")

    # 住所系も camelCase 併記（Flutter側が mPrefecture を見てもOKにする）
    d["mPrefecture"] = d.get("m_prefecture")
    d["mCity"] = d.get("m_city")
    d["mAddress"] = d.get("m_address")

    # user も camelCase を併記
    u = d.get("user")
    if isinstance(u, dict):
        u["companyName"] = u.get("company_name")
        u["contactName"] = u.get("contact_name")
        u["companyPhone"] = u.get("company_phone")
        u["jobTitle"] = u.get("job_title")
        u["businessStructure"] = u.get("business_structure")
        u["isAdmin"] = u.get("is_admin")
        u["isTerminalAdmin"] = u.get("is_terminal_admin")
        u["lineId"] = u.get("line_id")
        u["lectureFlug"] = u.get("lecture_flug")
        u["lastSeen"] = u.get("last_seen")

        # user.image は User.to_dict() で URL になってる前提
        u["imageUrl"] = u.get("image")
        u["imageKey"] = u.get("image_key")

    return d


# ✅ 追加：Request status 判定（RequestListScreenと同じ思想）
def _norm_status(s) -> str:
    if s is None:
        return ""
    return str(s).strip().lower()


def _is_accepted_status(s) -> bool:
    return _norm_status(s) == "accepted"


def _is_completed_status(s) -> bool:
    # RequestListScreen のコメントに pre_completed があったので吸収しておく
    v = _norm_status(s)
    return v in ("completed", "pre_completed")


def _safe_iso(dt):
    if not dt:
        return None
    try:
        return dt.isoformat()
    except Exception:
        return None


def _material_match_status_from_requests(request_dicts: list[dict]) -> tuple[str, str, bool, bool]:
    """
    return:
      - status_key: unmatched / matched / completed
      - status_label: 未マッチ / マッチ済 / 完了済
      - has_accepted
      - has_completed
    """
    has_accepted = False
    has_completed = False

    for r in request_dicts:
        st = r.get("status")
        if _is_completed_status(st):
            has_completed = True
        if _is_accepted_status(st):
            has_accepted = True

    if has_completed:
        return "completed", "完了済", has_accepted, True
    if has_accepted:
        return "matched", "マッチ済", True, False
    return "unmatched", "未マッチ", False, False


@api_groups_bp.route("/<int:group_id>/materials", methods=["GET"])
@jwt_required()
def list_group_materials(group_id: int):
    """
    ✅ 修正版：
    グループ資材一覧を返す際に、各資材に紐づく Request の status を同梱する。
    → Flutter側で「未マッチ / マッチ済 / 完了済」フィルタ可能になる

    Optional Query:
      - limit: 1〜200（default 200）
      - status: unmatched|matched|completed（指定時はAPI側で絞り込み）
      - include_requests: 1/0（default 1）
    """
    user = get_current_user()
    if not user:
        return jsonify({"message": "認証に失敗しました"}), 401

    group = UserGroup.query.get_or_404(group_id)
    if group.deleted_at:
        return jsonify({"message": "グループは存在しません"}), 404

    # 非公開グループ想定：参加者のみ閲覧可
    mem = _get_membership(group.id, user.id)
    if not mem and group.owner_user_id != user.id:
        return jsonify({"message": "参加していません"}), 403

    # 任意：件数制限（安全用）
    limit = request.args.get("limit", type=int) or 200
    limit = max(1, min(limit, 200))

    # ✅ Optional：サーバー側フィルタ（使わなくてもOK）
    status_filter = (request.args.get("status") or "").strip().lower()
    include_requests = (request.args.get("include_requests") or "1").strip().lower() not in ("0", "false", "no")

    # ✅ ここが重要：group_id で絞り込む
    materials = (
        Material.query
        .options(joinedload(Material.owner))
        .filter(
            Material.group_id == group.id,
            Material.deleted.is_(False),     # deleted=True は除外
        )
        .order_by(Material.created_at.desc())
        .limit(limit)
        .all()
    )

    material_ids = [m.id for m in materials if getattr(m, "id", None) is not None]

    # ─────────────────────────────────────────
    # ✅ material_id -> requests の Map を作る（N+1回避）
    # ─────────────────────────────────────────
    req_map: dict[int, list[dict]] = {mid: [] for mid in material_ids}

    if include_requests and material_ids:
        # Request モデルの material_id で紐付ける想定
        req_rows = (
            MaterialRequest.query
            .filter(getattr(MaterialRequest, "material_id").in_(material_ids))
            .all()
        )

        for r in req_rows:
            mid = getattr(r, "material_id", None)
            if mid is None:
                continue

            # 最低限の情報だけ返す（フィルタリングに必要なもの）
            req_map.setdefault(mid, []).append({
                "id": getattr(r, "id", None),
                "material_id": mid,
                "status": getattr(r, "status", None),
                "requested_at": _safe_iso(getattr(r, "requested_at", None)),
                "requester_user_id": getattr(r, "requester_user_id", None),
                "requested_user_id": getattr(r, "requested_user_id", None),
            })

        # requested_at の降順で整列（UIの「最新が上」にしやすい）
        for mid in list(req_map.keys()):
            req_map[mid].sort(key=lambda x: x.get("requested_at") or "", reverse=True)

    # ─────────────────────────────────────────
    # ✅ 返却payload作成（materials + requests + status）
    # ─────────────────────────────────────────
    payload = []
    for m in materials:
        d = _material_to_dict_for_flutter(m)

        mid = getattr(m, "id", None)
        reqs = req_map.get(mid, []) if mid is not None else []

        status_key, status_label, has_accepted, has_completed = _material_match_status_from_requests(reqs)

        # ✅ ステータス情報を同梱（Flutter側でフィルタ可能）
        d["requests"] = reqs
        d["request_count"] = len(reqs)
        d["has_accepted"] = has_accepted
        d["has_completed"] = has_completed

        d["material_status"] = status_key
        d["material_status_label"] = status_label

        # camelCase も併記（Flutterで拾いやすい）
        d["requestCount"] = d["request_count"]
        d["hasAccepted"] = d["has_accepted"]
        d["hasCompleted"] = d["has_completed"]
        d["materialStatus"] = d["material_status"]
        d["materialStatusLabel"] = d["material_status_label"]

        payload.append(d)

    # ✅ Optional：サーバー側絞り込み
    if status_filter in ("unmatched", "matched", "completed"):
        payload = [p for p in payload if p.get("material_status") == status_filter]

    return jsonify(payload), 200

@api_groups_bp.route("/<int:group_id>/join", methods=["POST"])
@jwt_required()
def api_join_group(group_id: int):
    """
    ✅ グループ参加（member）
    - 既に参加済み: 200
    - 新規参加: 201
    """
    identity = get_jwt_identity()

    # identity が dict のケースにも耐性
    user_id = identity
    if isinstance(identity, dict):
        user_id = identity.get("user_id") or identity.get("id")

    try:
        user_id = int(user_id)
    except Exception:
        return jsonify({"msg": "認証情報が不正です。"}), 401

    group = UserGroup.query.filter_by(id=group_id).first()
    if not group or not group.is_active:
        return jsonify({"msg": "グループが存在しません。"}), 404

    existing = GroupMembership.query.filter_by(
        group_id=group_id,
        user_id=user_id
    ).first()
    if existing:
        return jsonify({
            "msg": "既にグループに参加しています。",
            "joined": True,
            "group_id": group_id,
            "role": existing.role,
        }), 200

    try:
        membership = GroupMembership(
            group_id=group_id,
            user_id=user_id,
            role=GroupRole.MEMBER.value,  # "member"
        )
        db.session.add(membership)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"msg": f"グループ参加に失敗しました: {e}"}), 500

    return jsonify({
        "msg": "グループに参加しました。",
        "joined": True,
        "group_id": group_id,
        "role": GroupRole.MEMBER.value,
    }), 201
