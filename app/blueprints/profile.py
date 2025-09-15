# app/blueprints/profile.py

from flask import Blueprint, render_template, url_for, flash, redirect, request
from app import db
from app.forms import EditProfileForm
from app.models import User
from flask_login import login_required, current_user, login_user
from app.blueprints.utils import log_user_activity
from app.forms import DeleteAccountForm

profile = Blueprint('profile', __name__)

@profile.route("/profile/<int:user_id>")
@login_required
def user_profile(user_id):
    user = User.query.get_or_404(user_id)
    log_user_activity(
        current_user.id,
        'ユーザープロフィール表示',
        f'ユーザーがユーザーID: {user_id} のプロフィールを表示しました。',
        request.remote_addr,
        request.user_agent.string,
        'N/A'
    )
    return render_template('user_profile.html', user=user)

@profile.route("/profile", methods=['GET'])
@login_required
def view_profile():
    delete_form = DeleteAccountForm()  # フォームをインスタンス化
    return render_template('profile.html', form=delete_form)

@profile.route("/edit_profile", methods=['GET', 'POST'])
@login_required
def edit_profile():
    form = EditProfileForm()
    if form.validate_on_submit():
        # フィールドの更新
        current_user.company_name = form.company_name.data
        current_user.prefecture = form.prefecture.data
        current_user.city = form.city.data
        current_user.address = form.address.data
        current_user.without_approval = form.without_approval.data  # 修正
        current_user.contact_name = form.contact_name.data
        current_user.contact_phone = form.contact_phone.data
        current_user.line_id = form.line_id.data if form.line_id.data else None

        # 個人以外の場合のみ追加フィールドを更新
        if current_user.business_structure != 2:
            current_user.company_phone = form.company_phone.data
            current_user.industry = form.industry.data
            current_user.job_title = form.job_title.data

        db.session.commit()

        # current_user をセッションから再読み込み
        db.session.refresh(current_user)
        login_user(current_user, force=True)

        flash('プロフィールが更新されました！', 'success')
        # log_user_activity(
        #     current_user.id,
        #     'プロフィール編集',
        #     'ユーザーがプロフィールを編集しました。',
        #     request.remote_addr,
        #     request.user_agent.string,
        #     'N/A'
        # )
        return redirect(url_for('profile.view_profile'))
    elif request.method == 'GET':
        # フォームに現在のユーザーデータを設定
        form.company_name.data = current_user.company_name
        form.prefecture.data = current_user.prefecture
        form.city.data = current_user.city
        form.address.data = current_user.address
        form.without_approval.data = current_user.without_approval  # 修正
        form.contact_name.data = current_user.contact_name
        form.contact_phone.data = current_user.contact_phone
        form.line_id.data = current_user.line_id

        # 個人以外の場合のみ追加フィールドを設定
        if current_user.business_structure != 2:
            form.company_phone.data = current_user.company_phone
            form.industry.data = current_user.industry
            form.job_title.data = current_user.job_title

    return render_template('edit_profile.html', form=form)
