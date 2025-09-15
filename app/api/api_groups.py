from datetime import datetime
import pytz
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func

from app import db
from app.models import User, UserGroup, GroupMembership, GroupRole

JST = pytz.timezone("Asia/Tokyo")

api_groups_bp = Blueprint("api_groups", __name__, url_prefix="/api/groups")

# ────────────── ユーザ取得ユーティリティ ──────────────
def get_current_user():
    user_id = get_jwt_identity()
    return User.query.get(user_id)

def _is_admin(group: UserGroup, user: User) -> bool:
    return (
        user.id == group.owner_user_id or
        any(m.user_id == user.id and m.role == GroupRole.ADMIN for m in group.members)
    )

def _group_to_dict(group: UserGroup, user: User = None) -> dict:
    # user: 現在のユーザー。roleやオーナーかどうかを判別するため
    # NoneでもOK
    data = {
        "id": group.id,
        "name": group.name,
        "description": group.description,
        "owner_user_id": group.owner_user_id,
        "created_at": group.created_at.isoformat(),
        "deleted_at": group.deleted_at.isoformat() if group.deleted_at else None,
    }
    if user:
        membership = GroupMembership.query.filter_by(group_id=group.id, user_id=user.id).first()
        data["role"] = membership.role.value if membership else None
        data["is_owner"] = (group.owner_user_id == user.id)
    return data

# ────────────── グループ一覧 ──────────────
@api_groups_bp.route("/", methods=["GET"])
@jwt_required()
def list_groups():
    user = get_current_user()
    groups = (
        UserGroup.query
        .join(GroupMembership, GroupMembership.group_id == UserGroup.id)
        .filter(
            UserGroup.deleted_at.is_(None),
            GroupMembership.user_id == user.id,
        )
        .all()
    )
    return jsonify([_group_to_dict(g, user) for g in groups]), 200

# ────────────── グループ作成 ──────────────
@api_groups_bp.route("/", methods=["POST"])
@jwt_required()
def create_group():
    user = get_current_user()
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    description = (data.get("description") or "").strip()

    if not name:
        return jsonify({"message": "グループ名は必須です"}), 400

    dup = (
        UserGroup.query
        .filter(func.lower(UserGroup.name) == name.lower(),
                UserGroup.deleted_at.is_(None))
        .first()
    )
    if dup:
        return jsonify({"message": "同じグループ名が既に存在します"}), 409

    group = UserGroup(name=name,
                      description=description,
                      owner_user_id=user.id)
    db.session.add(group)
    db.session.flush()

    db.session.add(GroupMembership(group_id=group.id,
                                   user_id=user.id,
                                   role=GroupRole.ADMIN))
    db.session.commit()

    return jsonify(_group_to_dict(group, user)), 201

# ────────────── グループ更新 ──────────────
@api_groups_bp.route("/<int:group_id>", methods=["PUT"])
@jwt_required()
def update_group(group_id):
    user = get_current_user()
    group = UserGroup.query.get_or_404(group_id)
    if not _is_admin(group, user):
        return jsonify({"message": "権限がありません"}), 403

    data = request.get_json(silent=True) or {}
    new_name = (data.get("name") or group.name).strip()
    new_desc = (data.get("description") or group.description).strip()

    dup = (
        UserGroup.query
        .filter(func.lower(UserGroup.name) == new_name.lower(),
                UserGroup.id != group.id,
                UserGroup.deleted_at.is_(None))
        .first()
    )
    if dup:
        return jsonify({"message": "同じグループ名が既に存在します"}), 409

    group.name = new_name
    group.description = new_desc
    db.session.commit()
    return jsonify(_group_to_dict(group, user)), 200

# ────────────── グループ削除 ──────────────
@api_groups_bp.route("/<int:group_id>", methods=["DELETE"])
@jwt_required()
def delete_group(group_id):
    user = get_current_user()
    group = UserGroup.query.get_or_404(group_id)
    if not _is_admin(group, user):
        return jsonify({"message": "権限がありません"}), 403

    group.deleted_at = datetime.now(JST)
    db.session.commit()
    return jsonify({"message": "deleted"}), 200

# ────────────── グループ検索 ──────────────
@api_groups_bp.route("/search", methods=["POST"])
@jwt_required()
def search_groups():
    user = get_current_user()
    data = request.get_json(silent=True) or {}
    company_q = (data.get("company_name") or "").strip()
    group_q   = (data.get("group_name") or "").strip()

    if not (company_q and group_q):
        return jsonify({"message": "company_name と group_name が必要です"}), 400

    results = (
        db.session.query(UserGroup, User)
        .join(User, User.id == UserGroup.owner_user_id)
        .filter(UserGroup.deleted_at.is_(None))
        .filter(func.lower(User.company_name) == company_q.lower(),
                func.lower(UserGroup.name)   == group_q.lower())
        .all()
    )

    joined_ids = {
        m.group_id for m in GroupMembership.query
                                 .filter_by(user_id=user.id)
                                 .all()
    }

    payload = []
    for g, owner in results:
        payload.append({
            **_group_to_dict(g, user),
            "owner_company_name": owner.company_name,
            "joined": g.id in joined_ids
        })

    return jsonify({"results": payload}), 200

# ────────────── 所属グループ一覧 ──────────────
@api_groups_bp.route("/joined", methods=["GET"])
@jwt_required()
def joined_groups():
    user = get_current_user()
    memberships = (
        GroupMembership.query
        .join(UserGroup, UserGroup.id == GroupMembership.group_id)
        .filter(GroupMembership.user_id == user.id,
                UserGroup.deleted_at.is_(None))
        .all()
    )
    payload = []
    for mem in memberships:
        group = mem.group
        payload.append({
            **_group_to_dict(group, user),
            "role": mem.role.value,
            "is_owner": group.owner_user_id == user.id,
        })
    return jsonify({"my_groups": payload}), 200

# ────────────── グループ参加 ──────────────
@api_groups_bp.route("/<int:group_id>/join", methods=["POST"])
@jwt_required()
def join_group(group_id):
    user = get_current_user()
    group = UserGroup.query.get_or_404(group_id)
    if group.deleted_at:
        return jsonify({"message": "グループは存在しません"}), 404

    dup = GroupMembership.query.filter_by(
        group_id=group.id, user_id=user.id
    ).first()
    if dup:
        return jsonify({"message": "既に参加しています"}), 409

    db.session.add(GroupMembership(group_id=group.id,
                                   user_id=user.id,
                                   role=GroupRole.MEMBER))
    db.session.commit()
    return jsonify({"message": "joined"}), 201

# ────────────── グループ退会 ──────────────
@api_groups_bp.route("/<int:group_id>/leave", methods=["POST"])
@jwt_required()
def leave_group(group_id):
    user = get_current_user()
    mem = GroupMembership.query.filter_by(
        group_id=group_id, user_id=user.id
    ).first()
    if not mem:
        return jsonify({"message": "参加していません"}), 404

    if mem.group.owner_user_id == user.id:
        return jsonify({"message": "オーナーは退会できません"}), 403

    db.session.delete(mem)
    db.session.commit()
    return jsonify({"message": "left"}), 200
