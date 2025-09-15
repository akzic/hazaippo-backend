"""ユーザーグループ用 Blueprint"""
from datetime import datetime
import pytz
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import func

from app import db
from app.models import User, UserGroup, GroupMembership, GroupRole

JST = pytz.timezone("Asia/Tokyo")

# Blueprint を登録
groups_bp = Blueprint("groups", __name__, url_prefix="/groups")

def _is_admin(group: UserGroup) -> bool:
    """オーナー or 管理者かどうか判定"""
    if current_user.id == group.owner_user_id:
        return True
    for m in group.members:
        if m.user_id == current_user.id and m.role == GroupRole.ADMIN:
            return True
    return False

@groups_bp.route("/", methods=["GET"])
@login_required
def index():
    """グループ一覧 + 追加フォーム"""
    groups = (UserGroup.query
              .filter(UserGroup.deleted_at.is_(None),
                      UserGroup.owner_user_id == current_user.id)
              .all())
    return render_template("groups.html", groups=groups)

@groups_bp.route("/create", methods=["POST"])
@login_required
def create():
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()

    # ---------- 同名チェック ----------
    dup = (UserGroup.query
           .filter(db.func.lower(UserGroup.name) == name.lower(),
                   UserGroup.deleted_at.is_(None))
           .first())
    if dup:
        flash("同じグループ名が既に存在します。別の名前を入力してください。", "danger")
        return redirect(url_for("groups.index"))

    if not name:
        flash("グループ名は必須です。", "danger")
        return redirect(url_for("groups.index"))

    group = UserGroup(name=name,
                      description=description,
                      owner_user_id=current_user.id)
    db.session.add(group)
    db.session.flush()  # group.id を得る

    # オーナーを ADMIN として登録
    mem = GroupMembership(group_id=group.id,
                           user_id=current_user.id,
                           role=GroupRole.ADMIN)
    db.session.add(mem)
    db.session.commit()

    flash("グループを作成しました。", "success")
    return redirect(url_for("groups.index"))

@groups_bp.route("/update/<int:group_id>", methods=["POST"])
@login_required
def update(group_id):
    group = UserGroup.query.get_or_404(group_id)
    if not _is_admin(group):
        flash("権限がありません。", "danger")
        return redirect(url_for("groups.index"))

    new_name = request.form.get("name", group.name).strip()
    new_desc = request.form.get("description", group.description).strip()

    # ---------- 同名チェック（自分以外で重複） ----------
    dup = (UserGroup.query
           .filter(db.func.lower(UserGroup.name) == new_name.lower(),
                   UserGroup.id != group.id,
                   UserGroup.deleted_at.is_(None))
           .first())
    if dup:
        flash("同じグループ名が既に存在します。別の名前を入力してください。", "danger")
        return redirect(url_for("groups.index"))

    group.name = new_name
    group.description = new_desc
    db.session.commit()

    flash("グループ情報を更新しました。", "success")
    return redirect(url_for("groups.index"))

@groups_bp.route("/delete/<int:group_id>", methods=["POST"])
@login_required
def delete(group_id):
    group = UserGroup.query.get_or_404(group_id)
    if not _is_admin(group):
        flash("権限がありません。", "danger")
        return redirect(url_for("groups.index"))

    group.deleted_at = datetime.now(JST)
    db.session.commit()

    flash("グループを削除しました。", "success")
    return redirect(url_for("groups.index"))

@groups_bp.route("/join", methods=["GET", "POST"])
@login_required
def join():
    company_q = request.form.get("company_query", "").strip()
    group_q   = request.form.get("group_query", "").strip()

    results = []
    if company_q and group_q:
        # 会社名・グループ名 とも完全一致
        results = (db.session.query(UserGroup, User)
                   .join(User, User.id == UserGroup.owner_user_id)
                   .filter(UserGroup.deleted_at.is_(None))
                   .filter(func.lower(User.company_name) == company_q.lower(),
                           func.lower(UserGroup.name)   == group_q.lower())
                   .all())
    elif request.method == "POST":
        flash("法人名とグループ名の両方を入力してください。", "warning")

    # ── 自分が参加済みのグループ ID セット ──
    joined_ids = {m.group_id for m in GroupMembership.query
                                        .filter_by(user_id=current_user.id)
                                        .all()}

    my_groups = (db.session.query(UserGroup, GroupMembership)
                 .join(GroupMembership,
                       GroupMembership.group_id == UserGroup.id)
                 .filter(GroupMembership.user_id == current_user.id,
                         UserGroup.deleted_at.is_(None))
                 .all())

    return render_template("join_group.html",
                           company_query=company_q,
                           group_query=group_q,
                           results=results,
                           joined_ids=joined_ids,
                           my_groups=my_groups)

@groups_bp.route("/join/<int:group_id>", methods=["POST"])
@login_required
def join_apply(group_id):
    group = UserGroup.query.get_or_404(group_id)
    if group.deleted_at:
        flash("このグループは存在しません。", "danger")
        return redirect(url_for("groups.join"))

    dup = GroupMembership.query.filter_by(group_id=group.id,
                                          user_id=current_user.id).first()
    if dup:
        flash("既に参加しています。", "warning")
        return redirect(url_for("groups.join"))

    db.session.add(GroupMembership(
        group_id=group.id,
        user_id=current_user.id,
        role=GroupRole.MEMBER
    ))
    db.session.commit()

    flash(f"「{group.name}」に参加しました。", "success")
    return redirect(url_for("groups.join"))

@groups_bp.route("/leave/<int:group_id>", methods=["POST"])
@login_required
def leave(group_id):
    """自分の membership 行を削除"""
    mem = GroupMembership.query.filter_by(
        group_id=group_id, user_id=current_user.id
    ).first_or_404()

    # オーナーは退会できない
    if mem.group.owner_user_id == current_user.id:
        flash("オーナーは退会できません。まずオーナー権限を移譲してください。", "danger")
        return redirect(url_for("groups.join"))

    db.session.delete(mem)
    db.session.commit()
    flash(f"「{mem.group.name}」を退会しました。", "success")
    return redirect(url_for("groups.join"))

