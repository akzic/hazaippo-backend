# app/blueprints/terminal_management.py

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, abort
from flask_login import login_required, current_user
from app import db, csrf  # csrf を app からインポート
from app.models import Terminal, Room, Reservation, Lecture, Material, User, WorkingHours
from app.forms import TimeSlotForm, WorkingHoursForm
import logging
from datetime import datetime, timedelta, time
import pytz

from app.blueprints.email_notifications import (
    send_reservation_confirmation_email,
    send_lecture_confirmation_email,
    send_request_email,
    send_new_request_received_email,
    send_accept_request_email,
    send_accept_request_to_sender_email,
    send_reject_request_email,
    send_reject_request_to_sender_email,
    send_cancel_reservation_email
)

terminal_management_bp = Blueprint('terminal_management', __name__, url_prefix='/terminal_management')

JST = pytz.timezone('Asia/Tokyo')


# ターミナル予約管理
@terminal_management_bp.route('/reservation/management', methods=['GET'])
@login_required
def terminal_reservation_management():
    if not current_user.affiliated_terminal_id:
        flash('あなたには紐づいたターミナルがありません。', 'warning')
        return redirect(url_for('terminal.search_terminal'))

    terminal = Terminal.query.get(current_user.affiliated_terminal_id)
    if not terminal:
        flash('紐づいたターミナルが見つかりません。', 'warning')
        return redirect(url_for('terminal.search_terminal'))

    rooms = Room.query.filter_by(terminal_id=terminal.id).all()
    today = datetime.now(JST).date()

    # Generate min and max dates for the date input
    min_date = today.strftime('%Y-%m-%d')
    max_date = (today + timedelta(days=30)).strftime('%Y-%m-%d')

    # Generate date options for the next 30 days (if needed elsewhere)
    date_options = [(today + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(0, 31)]

    # Initialize schedule with empty slots from 9:00 to 22:00
    schedule = []
    for hour in range(9, 22):
        time_slot = f"{hour:02d}:00 ~ {hour + 1:02d}:00"
        schedule.append({
            'time': time_slot,
            'user_name': None,
            'lecturer_name': None,
            'reservation_id': None
        })

    return render_template('terminal_reservation_management.html', rooms=rooms, schedule=schedule, today=today, min_date=min_date, max_date=max_date, date_options=date_options)


# APIエンドポイント: スケジュール取得
@terminal_management_bp.route('/get_schedule', methods=['GET'])
@login_required
def get_schedule():
    room_id = request.args.get('room_id')
    date_str = request.args.get('date')

    if not room_id or not date_str:
        return jsonify({'status': 'error', 'message': '部屋と日付を指定してください。'}), 400

    try:
        date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'status': 'error', 'message': '日付の形式が正しくありません。'}), 400

    room = Room.query.get(room_id)
    if not room or room.terminal_id != current_user.affiliated_terminal_id:
        return jsonify({'status': 'error', 'message': '部屋が見つからないか、アクセス権がありません。'}), 404

    # Get reservations for the selected room and date between 9:00 and 22:00
    reservations = Reservation.query.filter(
        Reservation.room_id == room_id,
        Reservation.date == date,
        Reservation.canceled == False,
        Reservation.start_time >= time(9, 0),
        Reservation.start_time < time(23, 0)
    ).all()

    # Initialize schedule with empty slots from 9:00 to 22:00
    schedule = []
    for hour in range(9, 23):
        time_slot = f"{hour:02d}:00 ~ {hour + 1:02d}:00"
        schedule.append({
            'time': time_slot,
            'user_name': None,
            'lecturer_name': None,
            'reservation_id': None
        })

    for reservation in reservations:
        start_hour = reservation.start_time.hour
        if 9 <= start_hour < 22:
            index = start_hour - 9
            schedule[index]['user_name'] = reservation.user.contact_name
            schedule[index]['lecturer_name'] = reservation.lecturer.contact_name if reservation.lecturer else 'レクチャー担当なし'
            schedule[index]['reservation_id'] = reservation.id

    return jsonify({'status': 'success', 'schedule': schedule})


# APIエンドポイント: 予約削除
@csrf.exempt  # Exempt CSRF for API endpoint
@terminal_management_bp.route('/delete_reservation/<int:reservation_id>', methods=['DELETE'])
@login_required
def delete_reservation(reservation_id):
    reservation = Reservation.query.get(reservation_id)
    if not reservation:
        return jsonify({'status': 'error', 'message': '指定された予約が見つかりません。'}), 404

    if reservation.terminal_id != current_user.affiliated_terminal_id:
        return jsonify({'status': 'error', 'message': 'この予約を削除する権限がありません。'}), 403

    try:
        reservation.canceled = True
        db.session.commit()
        flash('予約が削除されました。', 'success')
        return jsonify({'status': 'success', 'message': '予約が削除されました。'})
    except Exception as e:
        db.session.rollback()
        logging.error(f"予約削除中にエラーが発生しました: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': '予約の削除中にエラーが発生しました。'}), 500


# ターミナル端材管理
@terminal_management_bp.route('/material/management', methods=['GET', 'POST'])
@login_required
def terminal_material_management():
    if current_user.affiliated_terminal_id is None:
        flash('あなたには紐づいたターミナルがありません。', 'warning')
        return redirect(url_for('terminal.search_terminal'))

    terminal = Terminal.query.get(current_user.affiliated_terminal_id)
    if not terminal:
        flash('紐づいたターミナルが見つかりません。', 'warning')
        return redirect(url_for('terminal.search_terminal'))

    # Get all users affiliated with this terminal
    affiliated_users = User.query.filter_by(affiliated_terminal_id=terminal.id).all()
    affiliated_user_ids = [user.id for user in affiliated_users]

    # Get materials registered by these users
    materials = Material.query.filter(Material.user_id.in_(affiliated_user_ids)).all()

    if request.method == 'POST':
        action = request.form.get('action')
        material_id = request.form.get('material_id')

        material = Material.query.get(material_id)
        if not material:
            flash('指定された端材が見つかりません。', 'danger')
            return redirect(url_for('terminal_management.terminal_material_management'))

        if not (material.user_id == current_user.id or current_user.is_terminal_admin):
            flash('この端材を編集または削除する権限がありません。', 'danger')
            return redirect(url_for('terminal_management.terminal_material_management'))

        if action == 'delete':
            try:
                db.session.delete(material)
                db.session.commit()
                flash('端材が削除されました。', 'success')
            except Exception as e:
                db.session.rollback()
                logging.error(f"端材削除中にエラーが発生しました: {e}", exc_info=True)
                flash('端材の削除中にエラーが発生しました。', 'danger')

        elif action == 'edit':
            # 編集処理を実装
            type = request.form.get('type')
            quantity = request.form.get('quantity')
            size_1 = request.form.get('size_1')
            size_2 = request.form.get('size_2')
            size_3 = request.form.get('size_3')
            location = request.form.get('location')  # Optional
            note = request.form.get('note')          # Optional

            try:
                material.type = type
                material.quantity = quantity
                material.size_1 = size_1
                material.size_2 = size_2
                material.size_3 = size_3
                material.location = location if location else material.location  # Update only if provided
                material.note = note if note else material.note          # Update only if provided
                db.session.commit()
                flash('端材が更新されました。', 'success')
            except ValueError:
                db.session.rollback()
                flash('数量は数値でなければなりません。', 'danger')
            except Exception as e:
                db.session.rollback()
                logging.error(f"端材更新中にエラーが発生しました: {e}", exc_info=True)
                flash('端材の更新中にエラーが発生しました。', 'danger')

        return redirect(url_for('terminal_management.terminal_material_management'))

    return render_template('terminal_material_management.html', materials=materials, terminal_name=terminal.name, is_admin=current_user.is_terminal_admin)


# 新しいAPIエンドポイント: 材料更新
@terminal_management_bp.route('/material/update/<int:material_id>', methods=['POST'])
@login_required
def update_material(material_id):
    material = Material.query.get(material_id)
    if not material:
        return jsonify({'status': 'error', 'message': '指定された端材が見つかりません。'}), 404

    if not (material.user_id == current_user.id or current_user.is_terminal_admin):
        return jsonify({'status': 'error', 'message': 'この端材を編集する権限がありません。'}), 403

    # CSRF トークンの検証は Flask-WTF によって自動的に行われます

    action = request.form.get('action')
    if action != 'edit':
        return jsonify({'status': 'error', 'message': '無効なアクションです。'}), 400

    type = request.form.get('type')
    quantity = request.form.get('quantity')
    size_1 = request.form.get('size_1')
    size_2 = request.form.get('size_2')
    size_3 = request.form.get('size_3')
    location = request.form.get('location')  # Optional
    note = request.form.get('note')          # Optional

    # ログにフォームデータを出力（デバッグ用）
    logging.debug(f"Received form data for update_material: type={type}, quantity={quantity}, size_1={size_1}, size_2={size_2}, size_3={size_3}, location={location}, note={note}")

    # 必須フィールドのみチェック
    if not all([type, quantity, size_1, size_2, size_3]):
        missing_fields = []
        if not type:
            missing_fields.append('type')
        if not quantity:
            missing_fields.append('quantity')
        if not size_1:
            missing_fields.append('size_1')
        if not size_2:
            missing_fields.append('size_2')
        if not size_3:
            missing_fields.append('size_3')
        return jsonify({'status': 'error', 'message': f'すべての必須フィールドを入力してください。欠落フィールド: {", ".join(missing_fields)}'}), 400

    try:
        material.type = type
        material.quantity = int(quantity)
        material.size_1 = size_1
        material.size_2 = size_2
        material.size_3 = size_3
        # 更新時に location と note はオプション。入力があれば更新し、なければ既存の値を保持
        if location:
            material.location = location
        if note:
            material.note = note
        db.session.commit()
        return jsonify({'status': 'success', 'message': '端材が更新されました。'})
    except ValueError:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': '数量は数値でなければなりません。'}), 400
    except Exception as e:
        db.session.rollback()
        logging.error(f"端材更新中にエラーが発生しました: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': '端材の更新中にエラーが発生しました。'}), 500
