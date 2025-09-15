# app/api/api_terminal.py

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models import Terminal, Room, Reservation, Lecture, Material, User, WorkingHours
from datetime import datetime, timedelta
import pytz
import logging
from sqlalchemy import or_, and_

from app.blueprints.email_notifications import (
    send_reservation_confirmation_email,
    send_lecture_confirmation_email,
    send_request_email,
    send_new_request_received_email,
    send_accept_request_email,
    send_accept_request_to_sender_email,
    send_reject_request_email,
    send_reject_request_to_sender_email,
    send_cancel_reservation_email,
    send_lecture_approval_email,
    send_lecturer_confirmation_email
)

api_terminal_bp = Blueprint('api_terminal', __name__, url_prefix='/api/terminal')
JST = pytz.timezone('Asia/Tokyo')
logger = logging.getLogger(__name__)


def get_current_user():
    """JWT からユーザーIDを取得し、DB からユーザー情報をロード"""
    user_id = get_jwt_identity()
    return User.query.get(user_id)


# ─── ターミナル検索 ─────────────────────────────
@api_terminal_bp.route('/search', methods=['GET', 'POST'])
@jwt_required()
def search_terminal():
    """
    GET: 全ターミナルと講師情報を JSON で返す
    POST: JSON の action と terminal_id に応じてお気に入りの追加／解除を処理
    """
    current_user = get_current_user()
    if not current_user:
        return jsonify({'status': 'error', 'message': 'ユーザーが見つかりません。'}), 404

    if request.method == 'GET':
        terminals = Terminal.query.all()
        lecturers = User.query.filter_by(lecture_flug=True).all()
        terminals_data = [{
            'id': term.id,
            'name': term.name,
            'prefecture': term.prefecture,
            'city': term.city
        } for term in terminals]
        lecturers_data = [{
            'id': lec.id,
            'contact_name': lec.contact_name,
            'company_name': lec.company_name
        } for lec in lecturers]
        return jsonify({'status': 'success', 'terminals': terminals_data, 'lecturers': lecturers_data}), 200

    # POST: お気に入りの追加／解除処理
    data = request.get_json()
    action = data.get('action')
    terminal_id = data.get('terminal_id')
    if not terminal_id:
        return jsonify({'status': 'error', 'message': 'ターミナルを選択してください。'}), 400

    terminal = Terminal.query.get(terminal_id)
    if not terminal:
        return jsonify({'status': 'error', 'message': 'ターミナルが見つかりません。'}), 404

    if action == 'favorite':
        if not current_user.favorite_terminals.filter_by(id=terminal.id).first():
            current_user.favorite_terminals.append(terminal)
            db.session.commit()
            return jsonify({'status': 'success', 'message': 'ターミナルをお気に入りに追加しました。'}), 200
        return jsonify({'status': 'error', 'message': 'ターミナルは既にお気に入りに追加されています。'}), 400

    elif action == 'unfavorite':
        favorite_terminal = current_user.favorite_terminals.filter_by(id=terminal.id).first()
        if favorite_terminal:
            current_user.favorite_terminals.remove(favorite_terminal)
            db.session.commit()
            return jsonify({'status': 'success', 'message': 'ターミナルをお気に入りから削除しました。'}), 200
        return jsonify({'status': 'error', 'message': 'ターミナルは既にお気に入り解除されています。'}), 400

    return jsonify({'status': 'error', 'message': '無効なアクションです。'}), 400


@api_terminal_bp.route('/search_terminals', methods=['GET'])
@jwt_required()
def search_terminals():
    """
    クエリパラメータ 'query' でターミナル名／県／市を検索し、
    一致したターミナル一覧を JSON で返す
    """
    current_user = get_current_user()
    search_query = request.args.get('query', '').strip().lower()
    if search_query:
        terminals = Terminal.query.filter(
            or_(
                Terminal.name.ilike(f'%{search_query}%'),
                Terminal.prefecture.ilike(f'%{search_query}%'),
                Terminal.city.ilike(f'%{search_query}%')
            )
        ).all()
    else:
        terminals = Terminal.query.all()

    result = []
    for terminal in terminals:
        is_favorite = current_user.favorite_terminals.filter_by(id=terminal.id).first() is not None
        result.append({
            'id': terminal.id,
            'name': terminal.name,
            'prefecture': terminal.prefecture,
            'city': terminal.city,
            'is_favorite': is_favorite
        })
    return jsonify({'status': 'success', 'terminals': result}), 200


@api_terminal_bp.route('/details/<int:terminal_id>', methods=['GET'])
@jwt_required()
def terminal_details(terminal_id):
    """
    指定されたターミナルの詳細情報と、ユーザーのお気に入り登録状況を JSON で返す
    """
    current_user = get_current_user()
    terminal = Terminal.query.get_or_404(terminal_id)
    is_favorite = current_user.favorite_terminals.filter_by(id=terminal.id).first() is not None
    terminal_data = {
        'id': terminal.id,
        'name': terminal.name,
        'prefecture': terminal.prefecture,
        'city': terminal.city,
        # 必要に応じて他のフィールドを追加
        'is_favorite': is_favorite
    }
    return jsonify({'status': 'success', 'terminal': terminal_data}), 200


# ─── 利用者のスケジュール管理 ─────────────────────────────
@api_terminal_bp.route('/schedule/<int:terminal_id>', methods=['GET', 'POST'])
@jwt_required()
def user_schedule(terminal_id):
    """
    GET: 指定ターミナルの部屋一覧と、現在日時に基づくデフォルトの日付情報および空スケジュールを返す
    POST: JSON の予約情報を元に予約を作成し、（必要なら）レクチャー依頼も処理する
    """
    current_user = get_current_user()
    rooms = Room.query.filter_by(terminal_id=terminal_id).all()
    if not rooms:
        return jsonify({'status': 'error', 'message': '指定されたターミナルに部屋がありません。'}), 400

    now = datetime.now(JST)
    today = now.date()
    # 22時以降なら翌日をデフォルト
    selected_date = today + timedelta(days=1) if now.hour >= 22 else today

    if request.method == 'GET':
        rooms_data = [{'id': room.id, 'name': room.name} for room in rooms]
        # 空のスケジュール（9:00～22:00）
        schedule = []
        for hour in range(9, 22):
            time_slot = f"{hour:02d}:00 ~ {hour+1:02d}:00"
            schedule.append({
                'time': time_slot,
                'user_name': None,
                'reservation_id': None
            })
        return jsonify({
            'status': 'success',
            'data': {
                'rooms': rooms_data,
                'selected_date': selected_date.strftime('%Y-%m-%d'),
                'schedule': schedule
            }
        }), 200

    # POST: 予約処理
    data = request.get_json()
    selected_date_str = data.get('date')
    selected_time = data.get('time_slot')
    room_id = data.get('room_id')
    request_lecture = data.get('request_lecture', False)
    lecturer_id = data.get('lecturer_id')

    if not (selected_date_str and selected_time and room_id):
        return jsonify({'status': 'error', 'message': '予約情報が不完全です。'}), 400

    try:
        selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        start_time_str, end_time_str = selected_time.split(' ~ ')
        start_time = datetime.strptime(start_time_str.strip(), '%H:%M').time()
        end_time = datetime.strptime(end_time_str.strip(), '%H:%M').time()
    except ValueError:
        return jsonify({'status': 'error', 'message': '日付や時間形式が無効です。'}), 400

    room = Room.query.get(room_id)
    if not room:
        return jsonify({'status': 'error', 'message': '指定された部屋が見つかりません。'}), 404

    # 予約作成
    reservation = Reservation(
        user_id=current_user.id,
        room_id=room.id,
        terminal_id=terminal_id,
        date=selected_date,
        start_time=start_time,
        end_time=end_time
    )
    db.session.add(reservation)
    db.session.commit()

    # レクチャー依頼がある場合
    if request_lecture and lecturer_id:
        lecture = Lecture(
            reservation_id=reservation.id,
            lecturer_id=lecturer_id,
            status='Confirmed',
            created_at=datetime.now(JST)
        )
        db.session.add(lecture)
        reservation.lecturer_id = lecturer_id
        reservation.accepted_flag = True
        db.session.commit()

        lecturer = User.query.get(lecturer_id)
        if lecturer:
            send_lecture_confirmation_email(lecturer.email, selected_date, selected_time)
        send_reservation_confirmation_email(current_user.email, selected_date, selected_time)

    return jsonify({'status': 'success', 'message': '予約が完了しました。'}), 200


@api_terminal_bp.route('/reservation/confirm', methods=['GET'])
@jwt_required()
def reservation_confirm():
    """
    ユーザーの今後の予約情報と、（存在する場合）ペンディングのレクチャーリクエストを返す
    """
    current_user = get_current_user()
    now_jst = datetime.now(JST)
    current_date = now_jst.date()
    current_time = now_jst.time()

    reservations = Reservation.query.filter(
        Reservation.user_id == current_user.id,
        Reservation.canceled == False,
        or_(
            Reservation.date > current_date,
            and_(Reservation.date == current_date, Reservation.end_time >= current_time)
        )
    ).all()

    reservations_data = [{
        'id': res.id,
        'date': res.date.strftime('%Y-%m-%d'),
        'time_slot': f"{res.start_time.strftime('%H:%M')} ~ {res.end_time.strftime('%H:%M')}"
    } for res in reservations]

    pending_request = None
    if reservations:
        req = Reservation.query.filter(
            Reservation.user_id == current_user.id,
            Reservation.request_flag == True,
            Reservation.canceled == False,
            Reservation.accepted_flag == False
        ).first()
        if req:
            pending_request = {
                'id': req.id,
                'date': req.date.strftime('%Y-%m-%d'),
                'time_slot': f"{req.start_time.strftime('%H:%M')} ~ {req.end_time.strftime('%H:%M')}"
            }

    return jsonify({
        'status': 'success',
        'reservations': reservations_data,
        'pending_request': pending_request
    }), 200


# ─── 講師スケジュール管理（レクチャー担当者専用） ─────────────────────────────
@api_terminal_bp.route('/lecturer/schedule', methods=['GET', 'POST'])
@jwt_required()
def lecturer_schedule_management():
    current_user = get_current_user()
    if not current_user.lecture_flug:
        return jsonify({'status': 'error', 'message': 'レクチャー担当者のみがアクセスできます。'}), 403

    now_jst = datetime.now(JST)
    today = now_jst.date()
    current_time = now_jst.time()
    selected_date = None

    if request.method == 'POST':
        data = request.get_json()
        selected_date_str = data.get('selected_date')
        time_slots = data.get('time_slot', [])
        if not selected_date_str:
            return jsonify({'status': 'error', 'message': '日付が指定されていません。'}), 400
        try:
            selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'status': 'error', 'message': '無効な日付形式です。'}), 400

        if not (today <= selected_date <= today + timedelta(days=6)):
            return jsonify({'status': 'error', 'message': '選択された日付は範囲外です。'}), 400

        try:
            existing_hours = WorkingHours.query.filter_by(user_id=current_user.id, date=selected_date).all()
            for wh in existing_hours:
                db.session.delete(wh)
            db.session.commit()

            for slot in time_slots:
                try:
                    start_time_str, end_time_str = slot.split(" ~ ")
                    start_time = datetime.strptime(start_time_str.strip(), '%H:%M').time()
                    end_time = datetime.strptime(end_time_str.strip(), '%H:%M').time()
                    new_wh = WorkingHours(
                        user_id=current_user.id,
                        date=selected_date,
                        start_time=start_time,
                        end_time=end_time,
                        is_active=True,
                        time_slots=slot,
                        created_at=datetime.now(JST)
                    )
                    db.session.add(new_wh)
                except ValueError:
                    return jsonify({'status': 'error', 'message': f'無効な時間スロット形式: {slot}'}), 400
            db.session.commit()
            return jsonify({'status': 'success', 'message': f"{selected_date}の稼働日程が確定しました。"}), 200
        except Exception as e:
            db.session.rollback()
            logger.error(f"{selected_date} のデータ処理中にエラーが発生しました: {e}", exc_info=True)
            return jsonify({'status': 'error', 'message': '予定の処理中にエラーが発生しました。'}), 500

    # GET: パラメータまたはデフォルトの日付設定
    selected_date_str = request.args.get('selected_date')
    try:
        selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date() if selected_date_str else (
            today + timedelta(days=1) if now_jst.hour >= 22 else today)
    except ValueError:
        selected_date = today

    schedule_days = [(today + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7)]
    all_time_slots = [f"{h:02d}:00 ~ {h+1:02d}:00" for h in range(9, 23)]

    working_hours = WorkingHours.query.filter_by(user_id=current_user.id, date=selected_date).all()
    checked_slots = [f"{wh.start_time.strftime('%H:%M')} ~ {wh.end_time.strftime('%H:%M')}" for wh in working_hours]

    updated_schedule = []
    for slot in all_time_slots:
        slot_start = datetime.strptime(slot.split(' ~ ')[0], '%H:%M').time()
        is_past = (selected_date == today and slot_start <= current_time)
        updated_schedule.append({
            'time': slot,
            'checked': slot in checked_slots,
            'is_past': is_past
        })

    # 講師へのレクチャーリクエスト（受信済み）の取得
    incoming_requests = Reservation.query.filter_by(
        requested_user_id=current_user.id,
        request_flag=True,
        canceled=False,
        accepted_flag=False
    ).all()
    incoming_data = [{
        'id': req.id,
        'date': req.date.strftime('%Y-%m-%d'),
        'time_slot': f"{req.start_time.strftime('%H:%M')} ~ {req.end_time.strftime('%H:%M')}"
    } for req in incoming_requests]

    return jsonify({
        'status': 'success',
        'data': {
            'schedule_days': schedule_days,
            'schedule_hours': updated_schedule,
            'selected_date': selected_date.strftime('%Y-%m-%d'),
            'incoming_requests': incoming_data,
            'current_date': today.strftime('%Y-%m-%d'),
            'current_time': current_time.strftime('%H:%M')
        }
    }), 200


# ─── 動画閲覧 ─────────────────────────────
@api_terminal_bp.route('/video_viewing', methods=['GET'])
@jwt_required()
def video_viewing():
    """
    動画閲覧可能な状態を示す（必要に応じて動画URLなどを付与可能）
    """
    return jsonify({'status': 'success', 'message': '動画閲覧可能です。'}), 200


# ─── 予約作成およびレクチャー依頼 ─────────────────────────────
@api_terminal_bp.route('/reservation', methods=['POST'])
@jwt_required()
def reserve_terminal():
    current_user = get_current_user()
    data = request.get_json()
    room_id = data.get('room_id')
    date_str = data.get('date')
    time_slot = data.get('time_slot')
    request_lecture = data.get('request_lecture', False)
    lecturer_id = data.get('lecturer_id')

    if not (room_id and date_str and time_slot):
        return jsonify({'status': 'error', 'message': '予約情報が不完全です。'}), 400

    try:
        date = datetime.strptime(date_str, '%Y-%m-%d').date()
        start_time_str, end_time_str = time_slot.split(' ~ ')
        start_time = datetime.strptime(start_time_str.strip(), '%H:%M').time()
        end_time = datetime.strptime(end_time_str.strip(), '%H:%M').time()
    except ValueError:
        return jsonify({'status': 'error', 'message': '日付や時間形式が無効です。'}), 400

    room = Room.query.get(room_id)
    if not room:
        return jsonify({'status': 'error', 'message': '部屋が見つかりません。'}), 404

    reservation = Reservation(
        user_id=current_user.id,
        room_id=room.id,
        terminal_id=room.terminal_id,
        date=date,
        start_time=start_time,
        end_time=end_time
    )
    db.session.add(reservation)
    db.session.commit()

    if request_lecture and lecturer_id:
        lecture = Lecture(
            reservation_id=reservation.id,
            lecturer_id=lecturer_id,
            status='Confirmed',
            created_at=datetime.now(JST)
        )
        db.session.add(lecture)
        reservation.lecturer_id = lecturer_id
        reservation.accepted_flag = True
        db.session.commit()
        lecturer = User.query.get(lecturer_id)
        if lecturer:
            send_lecture_confirmation_email(lecturer.email, date, time_slot)
        send_reservation_confirmation_email(current_user.email, date, time_slot)

    return jsonify({'status': 'success', 'message': '予約が完了しました。'}), 200


# ─── 利用時間選択スケジュール ─────────────────────────────
@api_terminal_bp.route('/get_schedule_hours', methods=['POST'])
@jwt_required()
def get_schedule_hours():
    data = request.get_json()
    selected_date_str = data.get('selected_date')
    if not selected_date_str:
        return jsonify({'status': 'error', 'message': '日付が指定されていません。'}), 400

    try:
        selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'status': 'error', 'message': '無効な日付形式です。'}), 400

    now_jst = datetime.now(JST)
    current_date = now_jst.date()
    current_time = now_jst.time()

    working_hours = WorkingHours.query.filter_by(user_id=get_current_user().id, date=selected_date, is_active=True).all()
    checked_slots = [f"{wh.start_time.strftime('%H:%M')} ~ {wh.end_time.strftime('%H:%M')}" for wh in working_hours]

    all_time_slots = [f"{h:02d}:00 ~ {h+1:02d}:00" for h in range(9, 23)]
    updated_schedule = []
    for slot in all_time_slots:
        slot_start = datetime.strptime(slot.split(' ~ ')[0], '%H:%M').time()
        is_past = (selected_date == current_date and slot_start <= current_time)
        updated_schedule.append({
            'time': slot,
            'checked': slot in checked_slots,
            'is_past': is_past
        })
    return jsonify({'status': 'success', 'schedule_hours': updated_schedule, 'current_date': selected_date_str}), 200


# ─── 予約済みスケジュール取得（部屋指定） ─────────────────────────────
@api_terminal_bp.route('/get_schedule', methods=['GET'])
@jwt_required()
def get_schedule():
    room_id = request.args.get('room_id')
    date_str = request.args.get('date')
    if not (room_id and date_str):
        return jsonify({'status': 'error', 'message': '部屋と日付を指定してください。'}), 400

    try:
        date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'status': 'error', 'message': '日付の形式が無効です。'}), 400

    reservations = Reservation.query.filter_by(room_id=room_id, date=date, canceled=False).all()
    schedule_data = [{
        'time_slot': f"{res.start_time.strftime('%H:%M')} ~ {res.end_time.strftime('%H:%M')}",
        'reserved': True,
        'lecturer': res.lecturer.contact_name if res.lecturer else None
    } for res in reservations]
    return jsonify({'status': 'success', 'schedule': schedule_data}), 200


# ─── 講師検索 ─────────────────────────────
@api_terminal_bp.route('/search_lecturers', methods=['GET'])
@jwt_required()
def search_lecturers():
    current_user = get_current_user()
    search_query = request.args.get('query', '').lower()
    query = User.query.filter(User.lecture_flug == True, User.id != current_user.id)
    if search_query:
        query = query.filter(
            or_(
                User.contact_name.ilike(f'%{search_query}%'),
                User.company_name.ilike(f'%{search_query}%')
            )
        )
    lecturers = query.all()
    result = []
    for lecturer in lecturers:
        is_favorite = current_user.favorite_lecturers.filter_by(id=lecturer.id).first() is not None
        result.append({
            'id': lecturer.id,
            'contact_name': lecturer.contact_name,
            'is_favorite': is_favorite
        })
    return jsonify({'status': 'success', 'lecturers': result}), 200


@api_terminal_bp.route('/available_lecturers', methods=['GET'])
@jwt_required()
def available_lecturers():
    date_str = request.args.get('date')
    time_str = request.args.get('time')
    if not (date_str and time_str):
        return jsonify({'status': 'error', 'message': '日付と時間を指定してください。'}), 400

    try:
        date = datetime.strptime(date_str, '%Y-%m-%d').date()
        time_obj = datetime.strptime(time_str, '%H:%M').time()
    except ValueError:
        return jsonify({'status': 'error', 'message': '日付または時間の形式が無効です。'}), 400

    current_user = get_current_user()
    lecturers = User.query.filter(User.lecture_flug == True, User.id != current_user.id).all()
    available = []
    for lecturer in lecturers:
        for wh in lecturer.working_hours:
            if wh.date == date and wh.is_active:
                if wh.start_time <= time_obj < wh.end_time:
                    is_favorite = current_user.favorite_lecturers.filter_by(id=lecturer.id).first() is not None
                    available.append({
                        'id': lecturer.id,
                        'contact_name': lecturer.contact_name,
                        'is_favorite': is_favorite
                    })
                    break
    return jsonify({'status': 'success', 'available_lecturers': available}), 200


@api_terminal_bp.route('/user_reservations', methods=['GET'])
@jwt_required()
def user_reservations():
    current_user = get_current_user()
    now_jst = datetime.now(JST)
    current_date = now_jst.date()
    current_time = now_jst.time()

    reservations = Reservation.query.filter_by(user_id=current_user.id, canceled=False).all()
    filtered = [res for res in reservations if res.date > current_date or (res.date == current_date and res.start_time > current_time)]
    reservation_list = sorted([{
        'id': res.id,
        'date': res.date.strftime('%Y-%m-%d'),
        'time_slot': f"{res.start_time.strftime('%H:%M')} ~ {res.end_time.strftime('%H:%M')}"
    } for res in filtered], key=lambda x: (x['date'], x['time_slot']))
    return jsonify({'status': 'success', 'reservations': reservation_list}), 200


# ─── レクチャーリクエスト関連 ─────────────────────────────
@api_terminal_bp.route('/lecture_request', methods=['POST'])
@jwt_required()
def lecture_request():
    current_user = get_current_user()
    data = request.get_json()
    lecturer_id = data.get('lecturer_id')
    reservation_id = data.get('reservation_id')
    if not (lecturer_id and reservation_id):
        return jsonify({'status': 'error', 'message': '必要な情報が不足しています。'}), 400

    reservation = Reservation.query.get(reservation_id)
    if not reservation or reservation.canceled:
        return jsonify({'status': 'error', 'message': '指定された予約が見つかりません。'}), 404

    if reservation.request_flag:
        return jsonify({'status': 'error', 'message': '既にレクチャーリクエストが送信されています。'}), 400

    lecturer = User.query.get(lecturer_id)
    if not lecturer or not lecturer.lecture_flug:
        return jsonify({'status': 'error', 'message': '指定されたレクチャー担当者が見つかりません。'}), 404

    reservation.requested_user_id = lecturer_id
    reservation.requested_time = reservation.start_time
    reservation.request_flag = True
    db.session.commit()

    try:
        date = reservation.date
        time_slot = f"{reservation.start_time.strftime('%H:%M')} ~ {reservation.end_time.strftime('%H:%M')}"
        send_lecture_confirmation_email(lecturer.email, date, time_slot)
        send_reservation_confirmation_email(current_user.email, date, time_slot)
    except Exception as e:
        logger.error(f"Email sending failed: {e}")
        return jsonify({'status': 'error', 'message': 'メール送信中にエラーが発生しました。'}), 500

    return jsonify({'status': 'success', 'message': 'レクチャーリクエストが送信されました。'}), 200


@api_terminal_bp.route('/process_lecture_request', methods=['POST'])
@jwt_required()
def process_lecture_request():
    current_user = get_current_user()
    if not current_user.lecture_flug:
        return jsonify({'status': 'error', 'message': 'レクチャー担当のみがこの操作を行えます。'}), 403

    data = request.get_json()
    request_id = data.get('request_id')
    action = data.get('action')
    if not request_id or action not in ['accept', 'reject']:
        return jsonify({'status': 'error', 'message': '無効なリクエストです。'}), 400

    try:
        reservation = Reservation.query.get(request_id)
        if not reservation or not reservation.request_flag or reservation.canceled:
            return jsonify({'status': 'error', 'message': 'リクエストが見つかりません。'}), 404

        requester = User.query.get(reservation.user_id)
        if not requester:
            return jsonify({'status': 'error', 'message': 'リクエスト送信者が見つかりません。'}), 404

        if action == 'accept':
            reservation.accepted_flag = True
            reservation.accepted_time = datetime.now(JST)
            reservation.lecturer_id = current_user.id
            db.session.commit()
            send_lecture_approval_email(requester.email, reservation, current_user)
            send_lecturer_confirmation_email(current_user.email, reservation, requester)
            return jsonify({'status': 'success', 'message': 'リクエストを承諾しました。'}), 200

        elif action == 'reject':
            reservation.lecturer_id = None
            reservation.requested_user_id = None
            reservation.requested_time = None
            reservation.request_flag = False
            db.session.commit()
            send_reject_request_email(requester.email, reservation, current_user)
            send_reject_request_to_sender_email(requester.email, reservation, current_user)
            return jsonify({'status': 'success', 'message': 'リクエストを拒否しました。'}), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"レクチャーリクエスト処理中にエラーが発生しました: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': 'レクチャーリクエスト処理中にエラーが発生しました。'}), 500


@api_terminal_bp.route('/cancel_reservation', methods=['POST'])
@jwt_required()
def cancel_reservation():
    current_user = get_current_user()
    data = request.get_json()
    reservation_id = data.get('reservation_id')
    if not reservation_id:
        return jsonify({'status': 'error', 'message': '予約IDが指定されていません。'}), 400

    reservation = Reservation.query.get(reservation_id)
    if not reservation or reservation.user_id != current_user.id or reservation.canceled:
        return jsonify({'status': 'error', 'message': '指定された予約が見つかりません。'}), 404

    try:
        reservation.canceled = True
        db.session.commit()
        send_cancel_reservation_email(current_user.email, reservation)
        return jsonify({'status': 'success', 'message': '予約がキャンセルされました。'}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"予約キャンセル中にエラーが発生しました: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': '予約のキャンセル中にエラーが発生しました。'}), 500


@api_terminal_bp.route('/cancel_multiple_reservations', methods=['POST'])
@jwt_required()
def cancel_multiple_reservations():
    current_user = get_current_user()
    data = request.get_json()
    reservation_ids = data.get('reservation_ids', [])
    if not reservation_ids:
        return jsonify({'status': 'error', 'message': 'キャンセルする予約が選択されていません。'}), 400

    reservations = Reservation.query.filter(
        Reservation.id.in_(reservation_ids),
        Reservation.user_id == current_user.id,
        Reservation.canceled == False
    ).all()
    if not reservations:
        return jsonify({'status': 'error', 'message': 'キャンセル可能な予約が見つかりません。'}), 404

    try:
        for res in reservations:
            res.canceled = True
            send_cancel_reservation_email(current_user.email, res)
        db.session.commit()
        return jsonify({'status': 'success', 'message': '選択された予約がキャンセルされました。'}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"複数予約キャンセル中にエラーが発生しました: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': '予約のキャンセル中にエラーが発生しました。'}), 500


# ─── お気に入り関連 ─────────────────────────────
@api_terminal_bp.route('/favorite_lecturer', methods=['POST'])
@jwt_required()
def favorite_lecturer():
    current_user = get_current_user()
    data = request.get_json()
    lecturer_id = data.get('lecturer_id')
    if not lecturer_id:
        return jsonify({'status': 'error', 'message': 'レクチャー担当者が指定されていません。'}), 400

    lecturer = User.query.get(lecturer_id)
    if not lecturer or not lecturer.lecture_flug:
        return jsonify({'status': 'error', 'message': '指定されたレクチャー担当者が見つかりません。'}), 404

    if current_user.favorite_lecturers.filter_by(id=lecturer.id).first():
        return jsonify({'status': 'error', 'message': 'レクチャー担当者は既にお気に入りに追加されています。'}), 400

    try:
        current_user.favorite_lecturers.append(lecturer)
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'レクチャー担当者をお気に入りに追加しました。'}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"レクチャー担当者のお気に入り追加中にエラーが発生しました: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': 'レクチャー担当者のお気に入り追加中にエラーが発生しました。'}), 500


@api_terminal_bp.route('/unfavorite_lecturer', methods=['POST'])
@jwt_required()
def unfavorite_lecturer():
    current_user = get_current_user()
    data = request.get_json()
    lecturer_id = data.get('lecturer_id')
    if not lecturer_id:
        return jsonify({'status': 'error', 'message': 'レクチャー担当者が指定されていません。'}), 400

    lecturer = User.query.get(lecturer_id)
    if not lecturer or not lecturer.lecture_flug:
        return jsonify({'status': 'error', 'message': '指定されたレクチャー担当者が見つかりません。'}), 404

    favorite = current_user.favorite_lecturers.filter_by(id=lecturer.id).first()
    if not favorite:
        return jsonify({'status': 'error', 'message': 'レクチャー担当者は既にお気に入り解除されています。'}), 400

    try:
        current_user.favorite_lecturers.remove(favorite)
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'レクチャー担当者のお気に入りを解除しました。'}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"レクチャー担当者のお気に入り解除中にエラーが発生しました: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': 'レクチャー担当者のお気に入り解除中にエラーが発生しました。'}), 500


@api_terminal_bp.route('/favorite_terminal', methods=['POST'])
@jwt_required()
def favorite_terminal():
    current_user = get_current_user()
    data = request.get_json()
    terminal_id = data.get('terminal_id')
    if not terminal_id:
        return jsonify({'status': 'error', 'message': 'ターミナルが指定されていません。'}), 400

    terminal = Terminal.query.get(terminal_id)
    if not terminal:
        return jsonify({'status': 'error', 'message': '指定されたターミナルが見つかりません。'}), 404

    if current_user.favorite_terminals.filter_by(id=terminal.id).first():
        return jsonify({'status': 'error', 'message': 'ターミナルは既にお気に入りに追加されています。'}), 400

    try:
        current_user.favorite_terminals.append(terminal)
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'ターミナルをお気に入りに追加しました。'}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"ターミナルのお気に入り追加中にエラーが発生しました: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': 'ターミナルのお気に入り追加中にエラーが発生しました。'}), 500


@api_terminal_bp.route('/unfavorite_terminal', methods=['POST'])
@jwt_required()
def unfavorite_terminal():
    current_user = get_current_user()
    data = request.get_json()
    terminal_id = data.get('terminal_id')
    if not terminal_id:
        return jsonify({'status': 'error', 'message': 'ターミナルが指定されていません。'}), 400

    terminal = Terminal.query.get(terminal_id)
    if not terminal:
        return jsonify({'status': 'error', 'message': '指定されたターミナルが見つかりません。'}), 404

    favorite = current_user.favorite_terminals.filter_by(id=terminal.id).first()
    if not favorite:
        return jsonify({'status': 'error', 'message': 'ターミナルは既にお気に入り解除されています。'}), 400

    try:
        current_user.favorite_terminals.remove(favorite)
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'ターミナルのお気に入りを解除しました。'}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"ターミナルのお気に入り解除中にエラーが発生しました: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': 'ターミナルのお気に入り解除中にエラーが発生しました。'}), 500
