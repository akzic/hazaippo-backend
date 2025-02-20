# app/blueprints/terminal.py

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from app import db
from app.models import Terminal, Room, Reservation, Lecture, Material, User, WorkingHours
from app.forms import TimeSlotForm, WorkingHoursForm
import logging
from datetime import datetime, timedelta
import pytz
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

terminal_bp = Blueprint('terminal', __name__, url_prefix='/terminal')

JST = pytz.timezone('Asia/Tokyo')


# ターミナル検索画面
@terminal_bp.route('/search', methods=['GET', 'POST'])
@login_required
def search_terminal():
    terminals = Terminal.query.all()
    lecturers = User.query.filter_by(lecture_flug=True).all()

    if request.method == 'POST':
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
                return jsonify({'status': 'success', 'message': 'ターミナルをお気に入りに追加しました。'})
            return jsonify({'status': 'error', 'message': 'ターミナルは既にお気に入りに追加されています。'}), 400

        if action == 'unfavorite':
            favorite_terminal = current_user.favorite_terminals.filter_by(id=terminal.id).first()
            if favorite_terminal:
                current_user.favorite_terminals.remove(favorite_terminal)
                db.session.commit()
                return jsonify({'status': 'success', 'message': 'ターミナルをお気に入りから削除しました。'})
            return jsonify({'status': 'error', 'message': 'ターミナルは既にお気に入り解除されています。'}), 400

        return jsonify({'status': 'error', 'message': '無効なアクションです。'}), 400

    return render_template('search_terminal.html', terminals=terminals, lecturers=lecturers)


# ターミナル検索機能を追加
@terminal_bp.route('/search_terminals', methods=['GET'])
@login_required
def search_terminals():
    search_query = request.args.get('query', '').strip().lower()

    # デフォルトですべてのターミナルを取得
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

    # フィルタリングされた結果をJSON形式で返す
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

    return jsonify(result)


# ターミナル詳細
@terminal_bp.route('/details/<int:terminal_id>', methods=['GET'])
@login_required
def terminal_details(terminal_id):
    terminal = Terminal.query.get_or_404(terminal_id)
    is_favorite = current_user.favorite_terminals.filter_by(id=terminal.id).first() is not None
    return render_template('terminal_details.html', terminal=terminal, is_favorite=is_favorite)


# 利用者のスケジュール管理画面
@terminal_bp.route('/schedule/<int:terminal_id>', methods=['GET', 'POST'])
@login_required
def user_schedule(terminal_id):
    rooms = Room.query.filter_by(terminal_id=terminal_id).all()
    selected_room = rooms[0] if rooms else None
    now = datetime.now(JST)
    today = now.date()
    if now.hour >= 22:
        selected_date = today + timedelta(days=1)
    else:
        selected_date = today

    if not selected_room:
        flash('指定されたターミナルに部屋がありません。', 'warning')
        return redirect(url_for('terminal.search_terminal'))

    if request.method == 'POST':
        selected_date = request.form.get('date')
        selected_time = request.form.get('time_slot')
        selected_room = Room.query.get(request.form.get('room_id'))

        # 時間範囲を分割して start_time と end_time を設定
        try:
            start_time_str, end_time_str = selected_time.split(' ~ ')
            start_time = datetime.strptime(start_time_str.strip(), '%H:%M').time()
            end_time = datetime.strptime(end_time_str.strip(), '%H:%M').time()
        except ValueError:
            flash('時間形式が無効です。', 'danger')
            return redirect(url_for('terminal.user_schedule', terminal_id=terminal_id))

        if not selected_room:
            flash('指定された部屋が見つかりませんでした。', 'danger')
            return redirect(url_for('terminal.user_schedule', terminal_id=terminal_id))

        # 予約処理
        reservation = Reservation(
            user_id=current_user.id,
            room_id=selected_room.id,
            terminal_id=terminal_id,
            date=selected_date,
            start_time=start_time,
            end_time=end_time
        )
        db.session.add(reservation)
        db.session.commit()
        flash(f'{selected_date} {selected_time}の予約が完了しました。', 'success')

    return render_template('user_schedule.html', rooms=rooms, selected_room=selected_room, today=today,
                           selected_date=selected_date)


# 予約確認
@terminal_bp.route('/reservation/confirm', methods=['GET'])
@login_required
def reservation_confirm():
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

    # フラグで予約があるかどうかをチェック
    has_reservations = len(reservations) > 0

    # もしリクエストがある場合
    pending_request = None
    if has_reservations:
        pending_request = Reservation.query.filter(
            Reservation.user_id == current_user.id,
            Reservation.request_flag == True,
            Reservation.canceled == False,
            Reservation.accepted_flag == False
        ).first()

    return render_template('reservation_confirm.html', reservations=reservations, has_reservations=has_reservations, pending_request=pending_request)


# terminal.py の lecturer_schedule_management 関数

@terminal_bp.route('/lecturer/schedule', methods=['GET', 'POST'])
@login_required
def lecturer_schedule_management():
    if not current_user.lecture_flug:
        flash('レクチャー担当者のみがアクセスできます。', 'danger')
        return redirect(url_for('dashboard.dashboard_home'))

    now_jst = datetime.now(JST)
    today = now_jst.date()
    current_time = now_jst.time()

    form = WorkingHoursForm()
    selected_date = None
    schedule_days = []
    schedule_hours = []
    form_data = {}
    incoming_requests = []

    if request.method == 'POST':
        # AJAXリクエストであるかを確認
        if request.is_json:
            data = request.get_json()
            selected_date_str = data.get('selected_date')
            time_slots = data.get('time_slot', [])

            if not selected_date_str:
                return jsonify({'status': 'error', 'message': '日付が指定されていません。'}), 400

            try:
                selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
            except ValueError:
                return jsonify({'status': 'error', 'message': '無効な日付形式です。'}), 400

            # 選択された日付が今日から7日以内かチェック
            if not (today <= selected_date <= today + timedelta(days=6)):
                return jsonify({'status': 'error', 'message': '選択された日付は範囲外です。'}), 400

            try:
                # 既存データの削除
                existing_hours = WorkingHours.query.filter_by(user_id=current_user.id, date=selected_date).all()
                for hour in existing_hours:
                    db.session.delete(hour)
                db.session.commit()

                # 新しいデータの保存
                for slot in time_slots:
                    try:
                        start_time_str, end_time_str = slot.split(" ~ ")
                        start_time = datetime.strptime(start_time_str.strip(), '%H:%M').time()
                        end_time = datetime.strptime(end_time_str.strip(), '%H:%M').time()
                        new_working_hour = WorkingHours(
                            user_id=current_user.id,
                            date=selected_date,
                            start_time=start_time,
                            end_time=end_time,
                            is_active=True,
                            time_slots=slot,
                            created_at=datetime.now(JST)
                        )
                        db.session.add(new_working_hour)
                    except ValueError:
                        return jsonify({'status': 'error', 'message': f'無効な時間スロット形式: {slot}'}), 400
                db.session.commit()

                return jsonify({'status': 'success', 'message': f"{selected_date}の稼働日程が確定しました。"})
            except Exception as e:
                db.session.rollback()
                logging.error(f"{selected_date} のデータ処理中にエラーが発生しました: {str(e)}", exc_info=True)
                return jsonify({'status': 'error', 'message': '予定の処理中にエラーが発生しました。'}), 500

    else:
        # GETリクエストの場合、クエリパラメータからselected_dateを取得
        selected_date_str = request.args.get('selected_date')
        if selected_date_str:
            try:
                selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
            except ValueError:
                flash('無効な日付が選択されました。今日の日付を使用します。', 'warning')
                selected_date = today

    # selected_dateがまだ設定されていない場合、22時以降のロジックを適用
    if not selected_date:
        if now_jst.hour >= 22:
            selected_date = today + timedelta(days=1)
        else:
            selected_date = today

    # 一週間分の日付を生成（今日から6日後まで）
    schedule_days = [today + timedelta(days=i) for i in range(7)]

    if request.method == 'GET':
        # 期限が過ぎたリクエストを処理
        expired_requests = Reservation.query.filter(
            Reservation.requested_user_id == current_user.id,
            Reservation.request_flag == True,
            Reservation.canceled == False,
            or_(
                Reservation.date < today,
                and_(Reservation.date == today, Reservation.start_time < current_time)
            )
        ).all()

        for req in expired_requests:
            try:
                # 送信者と受信者のメールアドレスを取得
                requester = User.query.get(req.user_id)
                receiver = current_user

                if requester:
                    # リクエスト送信者に通知メールを送信
                    send_reject_request_email(requester.email, req, receiver)

                    # レクチャー担当者（現在のユーザー）に通知メールを送信
                    send_reject_request_to_sender_email(requester.email, req, receiver)

                    # リクエストのフィールドをリセット
                    req.lecturer_id = None
                    req.requested_user_id = None
                    req.requested_time = None
                    req.request_flag = False
                    db.session.commit()

                logging.info(f"Expired request {req.id} has been processed and notifications sent.")
            except Exception as e:
                db.session.rollback()
                logging.error(f"Error processing expired request {req.id}: {e}", exc_info=True)

    # フォームデータの取得
    working_hours = WorkingHours.query.filter_by(user_id=current_user.id, date=selected_date).all()

    # 9時から23時までの時間スロットを作成
    schedule_hours = [{'time': f'{h:02d}:00 ~ {h + 1:02d}:00'} for h in range(9, 23)]
    logging.debug(f"作成されたスケジュール時間: {schedule_hours}")

    # 過去の稼働データをチェック済みのスロットに反映
    form_data = {}
    for wh in working_hours:
        time_slot = f"{wh.start_time.strftime('%H:%M')} ~ {wh.end_time.strftime('%H:%M')}"
        form_data[f"time_slot_{time_slot}"] = 'true' if wh.is_active else 'false'

    # 受けたレクチャーリクエストを取得（accepted_flagがtrueのものは除外）
    incoming_requests = Reservation.query.filter_by(
        requested_user_id=current_user.id,
        request_flag=True,
        canceled=False,
        accepted_flag=False  # accepted_flagがfalseのもののみ
    ).all()

    return render_template(
        'lecturer_schedule_management.html',
        schedule_days=schedule_days,
        schedule_hours=schedule_hours,
        selected_date=selected_date,
        form=form,
        form_data=form_data,
        incoming_requests=incoming_requests,
        current_date=today,
        current_time=current_time,
        datetime=datetime  # 追加
    )

# 動画閲覧
@terminal_bp.route('/video_viewing', methods=['GET'])
@login_required
def video_viewing():
    # terminal_id に関わらず全ユーザーが動画閲覧できる
    return render_template('video_viewing.html')


# 予約確認およびレクチャー依頼のメール送信
@terminal_bp.route('/reservation', methods=['POST'])
@login_required
def reserve_terminal():
    data = request.get_json()

    room_id = data.get('room_id')
    date_str = data.get('date')
    time_slot = data.get('time_slot')
    request_lecture = data.get('request_lecture')
    lecturer_id = data.get('lecturer_id')

    if not room_id or not date_str or not time_slot:
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
        return jsonify({'status': 'error', 'message': '部屋が見つかりません。'}), 400

    terminal_id = room.terminal_id

    # 予約情報の作成
    reservation = Reservation(
        user_id=current_user.id,
        room_id=room_id,
        terminal_id=terminal_id,
        date=date,
        start_time=start_time,
        end_time=end_time
    )
    db.session.add(reservation)
    db.session.commit()
    flash(f'{date} {time_slot}の予約が完了しました。', 'success')

    # レクチャー依頼がある場合、レクチャーデータを挿入し、accepted_flagをTrueに設定
    if request_lecture and lecturer_id:
        lecture = Lecture(
            reservation_id=reservation.id,
            lecturer_id=lecturer_id,
            status='Confirmed',
            created_at=datetime.now(JST)
        )
        db.session.add(lecture)
        # Reservationにレクチャー担当者を設定し、accepted_flagをTrueにする
        reservation.lecturer_id = lecturer_id
        reservation.accepted_flag = True
        db.session.commit()

        # レクチャー担当者に確認メールを送信
        lecturer = User.query.get(lecturer_id)
        if lecturer:
            send_lecture_confirmation_email(lecturer.email, date, time_slot)

        # 利用者に予約確認メールを送信
        send_reservation_confirmation_email(current_user.email, date, time_slot)

    return jsonify({'status': 'success', 'message': '予約が完了しました。'})


@terminal_bp.route('/get_schedule_hours', methods=['POST'])
@login_required
def get_schedule_hours():
    data = request.get_json()
    selected_date_str = data.get('selected_date')

    if not selected_date_str:
        return jsonify({'status': 'error', 'message': '日付が指定されていません。'}), 400

    try:
        selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'status': 'error', 'message': '無効な日付形式です。'}), 400

    # 現在の日付と時間
    now_jst = datetime.now(JST)
    current_date = now_jst.date()
    current_time = now_jst.time()

    # レクチャー担当者のWorkingHoursを取得
    working_hours = WorkingHours.query.filter_by(user_id=current_user.id, date=selected_date, is_active=True).all()

    # スケジュール時間の生成
    schedule_hours = []
    for wh in working_hours:
        slot_time = f"{wh.start_time.strftime('%H:%M')} ~ {wh.end_time.strftime('%H:%M')}"
        schedule_hours.append({
            'time': slot_time,
            'checked': True  # この例では、既存の稼働時間はチェックされた状態とします
        })

    # 一般的な時間スロットを生成（必要に応じて調整）
    # 例として、午前9時から午後11時までの時間帯を生成
    all_time_slots = [f"{hour:02d}:00 ~ {hour + 1:02d}:00" for hour in range(9, 23)]

    # チェックされているスロットを基にデータを整形
    updated_schedule = []
    for slot in all_time_slots:
        is_checked = slot in [sh['time'] for sh in schedule_hours]
        # 選択された日付が今日で、現在の時間より過去の場合は無効化
        slot_start_time = datetime.strptime(slot.split(' ~ ')[0], '%H:%M').time()
        if selected_date == current_date and slot_start_time <= current_time:
            is_past = True
        else:
            is_past = False

        updated_schedule.append({
            'time': slot,
            'checked': is_checked,
            'is_past': is_past
        })

    return jsonify({
        'status': 'success',
        'schedule_hours': updated_schedule,
        'current_date': selected_date_str
    })

# 利用時間選択のスケジュールを取得するAPIエンドポイント
@terminal_bp.route('/get_schedule', methods=['GET'])
@login_required
def get_schedule():
    room_id = request.args.get('room_id')
    date_str = request.args.get('date')

    logging.debug(f"get_schedule called with room_id={room_id}, date_str={date_str}")

    try:
        date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        logging.error("Invalid date format")
        return jsonify({'status': 'error', 'message': '日付の形式が無効です。'}), 400

    # 予約済みの時間帯を取得
    reservations = Reservation.query.filter_by(room_id=room_id, date=date, canceled=False).all()
    logging.debug(f"Found {len(reservations)} reservations")

    # 予約データをJSON形式で返す
    schedule_data = [
        {
            'time_slot': f"{res.start_time.strftime('%H:%M')} ~ {res.end_time.strftime('%H:%M')}",
            'reserved': True,  # 予約済み
            'lecturer': res.lecturer.contact_name if res.lecturer else None  # レクチャー担当者の名前
        }
        for res in reservations
    ]

    logging.debug(f"schedule_data: {schedule_data}")

    return jsonify({'status': 'success', 'schedule': schedule_data})


# レクチャー担当者を検索して取得するエンドポイント（従来の検索用）
@terminal_bp.route('/search_lecturers', methods=['GET'])
@login_required
def search_lecturers():
    # 検索クエリを取得
    search_query = request.args.get('query', '').lower()

    # 講師フラグがTrueで、現在のユーザーではないユーザーを取得
    query = User.query.filter(User.lecture_flug == True, User.id != current_user.id)

    if search_query:
        query = query.filter(
            or_(
                User.contact_name.ilike(f'%{search_query}%'),
                User.company_name.ilike(f'%{search_query}%')
            )
        )

    lecturers = query.all()

    # 検索結果を構築
    result = []
    for lecturer in lecturers:
        is_favorite = current_user.favorite_lecturers.filter_by(id=lecturer.id).first() is not None
        result.append({
            'id': lecturer.id,
            'contact_name': lecturer.contact_name,
            'is_favorite': is_favorite
        })

    return jsonify(result)



# 利用可能なレクチャー担当者を取得するエンドポイント
@terminal_bp.route('/available_lecturers', methods=['GET'])
@login_required
def available_lecturers():
    date_str = request.args.get('date')
    time_str = request.args.get('time')

    if not date_str or not time_str:
        return jsonify([]), 400

    try:
        date = datetime.strptime(date_str, '%Y-%m-%d').date()
        time_obj = datetime.strptime(time_str, '%H:%M').time()
    except ValueError:
        return jsonify([]), 400

    # レクチャー担当者のみを対象とし、現在のユーザーを除外する
    lecturers = User.query.filter(
        User.lecture_flug == True,
        User.id != current_user.id
    ).all()

    available_lecturers = []
    for lecturer in lecturers:
        # 各レクチャー担当者のWorkingHoursをチェック
        for wh in lecturer.working_hours:
            if wh.date == date and wh.is_active:
                # 予約時間がWorkingHoursの範囲内にあるかチェック
                if wh.start_time <= time_obj < wh.end_time:
                    is_favorite = current_user.favorite_lecturers.filter_by(id=lecturer.id).first() is not None
                    available_lecturers.append({
                        'id': lecturer.id,
                        'contact_name': lecturer.contact_name,
                        'is_favorite': is_favorite
                    })
                    break  # 一致するWorkingHoursが見つかったら次のレクチャー担当者へ
    return jsonify(available_lecturers)



# ユーザーの予約日程を取得するエンドポイント
@terminal_bp.route('/user_reservations', methods=['GET'])
@login_required
def user_reservations():
    now_jst = datetime.now(JST)
    current_date = now_jst.date()
    current_time = now_jst.time()

    reservations = Reservation.query.filter_by(user_id=current_user.id, canceled=False).all()
    filtered_reservations = [
        res for res in reservations
        if res.date > current_date or (res.date == current_date and res.start_time > current_time)
    ]

    reservation_list = sorted([
        {
            'id': res.id,
            'date': res.date.strftime('%Y-%m-%d'),
            'time_slot': f"{res.start_time.strftime('%H:%M')} ~ {res.end_time.strftime('%H:%M')}"
        }
        for res in filtered_reservations
    ], key=lambda x: (x['date'], x['time_slot']))
    return jsonify({'status': 'success', 'reservations': reservation_list})

@terminal_bp.route('/lecture_request', methods=['POST'])
@login_required
def lecture_request():
    data = request.get_json()
    logging.debug(f"Received lecture_request data: {data}")

    lecturer_id = data.get('lecturer_id')
    reservation_id = data.get('reservation_id')

    if not lecturer_id or not reservation_id:
        logging.warning("lecture_request: Missing lecturer_id or reservation_id")
        return jsonify({'status': 'error', 'message': '必要な情報が不足しています。'}), 400

    reservation = Reservation.query.get(reservation_id)
    if not reservation or reservation.canceled:
        logging.warning(f"lecture_request: Invalid reservation_id={reservation_id}")
        return jsonify({'status': 'error', 'message': '指定された予約が見つかりません。'}), 404

    if reservation.request_flag:
        logging.info(f"lecture_request: Reservation {reservation_id} already has a request")
        return jsonify({'status': 'error', 'message': '既にレクチャーリクエストが送信されています。'}), 400

    lecturer = User.query.get(lecturer_id)
    if not lecturer or not lecturer.lecture_flug:
        logging.warning(f"lecture_request: Invalid lecturer_id={lecturer_id}")
        return jsonify({'status': 'error', 'message': '指定されたレクチャー担当者が見つかりません。'}), 404

    # リクエスト情報を更新
    reservation.requested_user_id = lecturer_id
    reservation.requested_time = reservation.start_time  # または必要な時間を設定
    reservation.request_flag = True
    db.session.commit()
    logging.info(f"lecture_request: Updated Reservation {reservation_id} with requested_user_id={lecturer_id}")

    # メール通知の送信
    if lecturer:
        date = reservation.date
        time_slot = f"{reservation.start_time.strftime('%H:%M')} ~ {reservation.end_time.strftime('%H:%M')}"
        try:
            send_lecture_confirmation_email(lecturer.email, date, time_slot)
            send_reservation_confirmation_email(current_user.email, date, time_slot)
            logging.info(f"lecture_request: Sent confirmation emails for Reservation {reservation_id}")
        except Exception as e:
            logging.error(f"lecture_request: Email sending failed: {e}")
            return jsonify({'status': 'error', 'message': 'メール送信中にエラーが発生しました。'}), 500

    return jsonify({'status': 'success', 'message': 'レクチャーリクエストが送信されました。'})

# リクエスト承諾・拒否を処理するエンドポイント
@terminal_bp.route('/process_lecture_request', methods=['POST'])
@login_required
def process_lecture_request():
    if not current_user.lecture_flug:
        logging.warning("Non-lecturer user attempted to process a lecture request.")
        return jsonify({'status': 'error', 'message': 'レクチャー担当のみがこの操作を行えます。'}), 403

    data = request.get_json()
    request_id = data.get('request_id')
    action = data.get('action')

    if not request_id or action not in ['accept', 'reject']:
        logging.warning(f"Invalid request data: request_id={request_id}, action={action}")
        return jsonify({'status': 'error', 'message': '無効なリクエストです。'}), 400

    logging.debug(f"Processing lecture request: ID={request_id}, Action={action}")

    try:
        reservation = Reservation.query.get(request_id)
        if not reservation or not reservation.request_flag or reservation.canceled:
            logging.warning(f"Reservation not found or invalid: ID={request_id}")
            return jsonify({'status': 'error', 'message': 'リクエストが見つかりません。'}), 404

        requester = User.query.get(reservation.user_id)
        if not requester:
            logging.warning(f"Requester not found for reservation ID={request_id}")
            return jsonify({'status': 'error', 'message': 'リクエスト送信者が見つかりません。'}), 404

        if action == 'accept':
            logging.debug(f"Accepting reservation ID={request_id}")
            reservation.accepted_flag = True
            reservation.accepted_time = datetime.now(JST)
            reservation.lecturer_id = current_user.id
            db.session.commit()
            logging.info(f"Reservation ID={request_id} accepted by user ID={current_user.id}")

            # メール送信
            send_lecture_approval_email(requester.email, reservation, current_user)
            send_lecturer_confirmation_email(current_user.email, reservation, requester)

            return jsonify({'status': 'success', 'message': 'リクエストを承諾しました。'})

        elif action == 'reject':
            logging.debug(f"Rejecting reservation ID={request_id}")
            reservation.lecturer_id = None
            reservation.requested_user_id = None
            reservation.requested_time = None
            reservation.request_flag = False
            db.session.commit()
            logging.info(f"Reservation ID={request_id} rejected by user ID={current_user.id}")

            # メール送信
            send_reject_request_email(requester.email, reservation, current_user)
            send_reject_request_to_sender_email(requester.email, reservation, current_user)

            return jsonify({'status': 'success', 'message': 'リクエストを拒否しました。'})

        else:
            logging.warning(f"Invalid action received: {action}")
            return jsonify({'status': 'error', 'message': '無効なアクションです。'}), 400

    except Exception as e:
        db.session.rollback()
        logging.error(f"レクチャーリクエスト処理中にエラーが発生しました: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': 'レクチャーリクエスト処理中にエラーが発生しました。'}), 500


# ユーザーが予約をキャンセルするエンドポイント
@terminal_bp.route('/cancel_reservation', methods=['POST'])
@login_required
def cancel_reservation():
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

        return jsonify({'status': 'success', 'message': '予約がキャンセルされました。'})
    except Exception as e:
        db.session.rollback()
        logging.error(f"予約キャンセル中にエラーが発生しました: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': '予約のキャンセル中にエラーが発生しました。'}), 500


# ユーザーが複数の予約をキャンセルするエンドポイント
@terminal_bp.route('/cancel_multiple_reservations', methods=['POST'])
@login_required
def cancel_multiple_reservations():
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
        for reservation in reservations:
            reservation.canceled = True
            send_cancel_reservation_email(current_user.email, reservation)
        db.session.commit()
        return jsonify({'status': 'success', 'message': '選択された予約がキャンセルされました。'})
    except Exception as e:
        db.session.rollback()
        logging.error(f"複数予約キャンセル中にエラーが発生しました: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': '予約のキャンセル中にエラーが発生しました。'}), 500


# レクチャー担当者をお気に入りに追加するエンドポイント
@terminal_bp.route('/favorite_lecturer', methods=['POST'])
@login_required
def favorite_lecturer():
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
        return jsonify({'status': 'success', 'message': 'レクチャー担当者をお気に入りに追加しました。'})
    except Exception as e:
        db.session.rollback()
        logging.error(f"レクチャー担当者のお気に入り追加中にエラーが発生しました: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': 'レクチャー担当者のお気に入り追加中にエラーが発生しました。'}), 500


# レクチャー担当者のお気に入りを解除するエンドポイント
@terminal_bp.route('/unfavorite_lecturer', methods=['POST'])
@login_required
def unfavorite_lecturer():
    data = request.get_json()
    lecturer_id = data.get('lecturer_id')

    if not lecturer_id:
        return jsonify({'status': 'error', 'message': 'レクチャー担当者が指定されていません。'}), 400

    lecturer = User.query.get(lecturer_id)
    if not lecturer or not lecturer.lecture_flug:
        return jsonify({'status': 'error', 'message': '指定されたレクチャー担当者が見つかりません。'}), 404

    favorite_lecturer = current_user.favorite_lecturers.filter_by(id=lecturer.id).first()
    if not favorite_lecturer:
        return jsonify({'status': 'error', 'message': 'レクチャー担当者は既にお気に入りから解除されています。'}), 400

    try:
        current_user.favorite_lecturers.remove(favorite_lecturer)
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'レクチャー担当者のお気に入りを解除しました。'})
    except Exception as e:
        db.session.rollback()
        logging.error(f"レクチャー担当者のお気に入り解除中にエラーが発生しました: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': 'レクチャー担当者のお気に入り解除中にエラーが発生しました。'}), 500


# ターミナルをお気に入りに追加するエンドポイント
@terminal_bp.route('/favorite_terminal', methods=['POST'])
@login_required
def favorite_terminal():
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
        return jsonify({'status': 'success', 'message': 'ターミナルをお気に入りに追加しました。'})
    except Exception as e:
        db.session.rollback()
        logging.error(f"ターミナルのお気に入り追加中にエラーが発生しました: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': 'ターミナルのお気に入り追加中にエラーが発生しました。'}), 500


# ターミナルのお気に入りを解除するエンドポイント
@terminal_bp.route('/unfavorite_terminal', methods=['POST'])
@login_required
def unfavorite_terminal():
    data = request.get_json()
    terminal_id = data.get('terminal_id')

    if not terminal_id:
        return jsonify({'status': 'error', 'message': 'ターミナルが指定されていません。'}), 400

    terminal = Terminal.query.get(terminal_id)
    if not terminal:
        return jsonify({'status': 'error', 'message': '指定されたターミナルが見つかりません。'}), 404

    favorite_terminal = current_user.favorite_terminals.filter_by(id=terminal.id).first()
    if not favorite_terminal:
        return jsonify({'status': 'error', 'message': 'ターミナルは既にお気に入りから解除されています。'}), 400

    try:
        current_user.favorite_terminals.remove(favorite_terminal)
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'ターミナルのお気に入りを解除しました。'})
    except Exception as e:
        db.session.rollback()
        logging.error(f"ターミナルのお気に入り解除中にエラーが発生しました: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': 'ターミナルのお気に入り解除中にエラーが発生しました。'}), 500
