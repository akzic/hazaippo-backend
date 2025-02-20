# app/api/api_terminal.py

from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from app import db
from app.models import Terminal, Room, Reservation, Lecture, Material, User, WorkingHours
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import or_, and_
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

api_terminal_bp = Blueprint('api_terminal', __name__, url_prefix='/api/terminal')

JST = pytz.timezone('Asia/Tokyo')

# ロガーの設定
logger = logging.getLogger(__name__)


# ターミナル検索とお気に入り管理
@api_terminal_bp.route('/search', methods=['GET'])
@login_required
def search_terminal():
    """
    ターミナルの検索およびお気に入り管理を行います。
    GET: ターミナル一覧と講師一覧を取得
    POST: ターミナルのお気に入り追加・解除
    """
    if request.method == 'GET':
        try:
            terminals = Terminal.query.all()
            lecturers = User.query.filter_by(lecture_flug=True).all()

            terminals_data = [
                {
                    'id': terminal.id,
                    'name': terminal.name,
                    'prefecture': terminal.prefecture,
                    'city': terminal.city
                } for terminal in terminals
            ]

            lecturers_data = [
                {
                    'id': lecturer.id,
                    'contact_name': lecturer.contact_name
                } for lecturer in lecturers
            ]

            return jsonify({
                'status': 'success',
                'terminals': terminals_data,
                'lecturers': lecturers_data
            }), 200

        except SQLAlchemyError as e:
            logger.error(f"Database error during terminal search GET: {e}")
            return jsonify({'status': 'error', 'message': 'データベースエラーが発生しました。'}), 500

        except Exception as e:
            logger.error(f"Unexpected error during terminal search GET: {e}")
            return jsonify({'status': 'error', 'message': '予期せぬエラーが発生しました。'}), 500

    elif request.method == 'POST':
        """
        ターミナルのお気に入り追加・解除を行います。
        JSON形式で以下のデータを受け取ります。
        - action: "favorite" または "unfavorite"
        - terminal_id: ターミナルのID
        """
        try:
            if not request.is_json:
                return jsonify({'status': 'error', 'message': 'JSON形式のデータを送信してください。'}), 400

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

            else:
                return jsonify({'status': 'error', 'message': '無効なアクションです。'}), 400

        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"Database error during terminal favorite action POST: {e}")
            return jsonify({'status': 'error', 'message': 'データベースエラーが発生しました。'}), 500

        except Exception as e:
            db.session.rollback()
            logger.error(f"Unexpected error during terminal favorite action POST: {e}")
            return jsonify({'status': 'error', 'message': '予期せぬエラーが発生しました。'}), 500


# ターミナル検索機能
@api_terminal_bp.route('/search_terminals', methods=['GET'])
@login_required
def search_terminals():
    """
    ターミナルの検索を行います。
    クエリパラメータ:
    - query: 検索キーワード（任意）
    """
    search_query = request.args.get('query', '').strip().lower()

    try:
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

    except SQLAlchemyError as e:
        logger.error(f"Database error during terminals search: {e}")
        return jsonify({'status': 'error', 'message': 'データベースエラーが発生しました。'}), 500

    except Exception as e:
        logger.error(f"Unexpected error during terminals search: {e}")
        return jsonify({'status': 'error', 'message': '予期せぬエラーが発生しました。'}), 500


# ターミナル詳細取得
@api_terminal_bp.route('/details/<int:terminal_id>', methods=['GET'])
@login_required
def terminal_details(terminal_id):
    """
    指定されたターミナルの詳細情報を取得します。
    """
    try:
        terminal = Terminal.query.get_or_404(terminal_id)
        is_favorite = current_user.favorite_terminals.filter_by(id=terminal.id).first() is not None

        terminal_data = {
            'id': terminal.id,
            'name': terminal.name,
            'prefecture': terminal.prefecture,
            'city': terminal.city,
            'is_favorite': is_favorite,
            # 必要に応じて他のフィールドを追加
        }

        return jsonify({'status': 'success', 'terminal': terminal_data}), 200

    except SQLAlchemyError as e:
        logger.error(f"Database error during terminal details GET: {e}")
        return jsonify({'status': 'error', 'message': 'データベースエラーが発生しました。'}), 500

    except Exception as e:
        logger.error(f"Unexpected error during terminal details GET: {e}")
        return jsonify({'status': 'error', 'message': '予期せぬエラーが発生しました。'}), 500


# ユーザーのスケジュール管理
@api_terminal_bp.route('/schedule/<int:terminal_id>', methods=['GET', 'POST'])
@login_required
def user_schedule(terminal_id):
    """
    ユーザーのスケジュール管理を行います。
    GET: スケジュール情報を取得
    POST: 新しい予約を作成
    """
    if request.method == 'GET':
        try:
            rooms = Room.query.filter_by(terminal_id=terminal_id).all()
            if not rooms:
                return jsonify({'status': 'error', 'message': '指定されたターミナルに部屋がありません。'}), 404

            selected_room = rooms[0]
            now = datetime.now(JST)
            today = now.date()
            selected_date = today + timedelta(days=1) if now.hour >= 22 else today

            reservations = Reservation.query.filter_by(
                user_id=current_user.id,
                terminal_id=terminal_id,
                date=selected_date,
                canceled=False
            ).all()

            reservations_data = [
                {
                    'id': res.id,
                    'room_id': res.room_id,
                    'date': res.date.strftime('%Y-%m-%d'),
                    'start_time': res.start_time.strftime('%H:%M'),
                    'end_time': res.end_time.strftime('%H:%M')
                } for res in reservations
            ]

            return jsonify({
                'status': 'success',
                'terminal_id': terminal_id,
                'selected_date': selected_date.strftime('%Y-%m-%d'),
                'reservations': reservations_data
            }), 200

        except SQLAlchemyError as e:
            logger.error(f"Database error during user schedule GET: {e}")
            return jsonify({'status': 'error', 'message': 'データベースエラーが発生しました。'}), 500

        except Exception as e:
            logger.error(f"Unexpected error during user schedule GET: {e}")
            return jsonify({'status': 'error', 'message': '予期せぬエラーが発生しました。'}), 500

    elif request.method == 'POST':
        """
        新しい予約を作成します。
        JSON形式で以下のデータを受け取ります。
        - room_id: 部屋のID
        - date: 予約日（YYYY-MM-DD）
        - time_slot: 時間帯（"HH:MM ~ HH:MM"）
        """
        try:
            if not request.is_json:
                return jsonify({'status': 'error', 'message': 'JSON形式のデータを送信してください。'}), 400

            data = request.get_json()
            room_id = data.get('room_id')
            date_str = data.get('date')
            time_slot = data.get('time_slot')
            request_lecture = data.get('request_lecture', False)
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

            if room.terminal_id != terminal_id:
                return jsonify({'status': 'error', 'message': '部屋が指定されたターミナルに属していません。'}), 400

            # 重複予約のチェック
            existing_reservation = Reservation.query.filter_by(
                room_id=room_id,
                date=date,
                start_time=start_time,
                canceled=False
            ).first()
            if existing_reservation:
                return jsonify({'status': 'error', 'message': '指定された時間帯は既に予約されています。'}), 400

            # 予約情報の作成
            reservation = Reservation(
                user_id=current_user.id,
                room_id=room_id,
                terminal_id=terminal_id,
                date=date,
                start_time=start_time,
                end_time=end_time,
                request_flag=request_lecture
            )
            db.session.add(reservation)
            db.session.commit()

            # レクチャー依頼がある場合
            if request_lecture and lecturer_id:
                lecturer = User.query.get(lecturer_id)
                if not lecturer or not lecturer.lecture_flug:
                    return jsonify({'status': 'error', 'message': '指定されたレクチャー担当者が見つかりません。'}), 404

                lecture = Lecture(
                    reservation_id=reservation.id,
                    lecturer_id=lecturer_id,
                    status='Pending',
                    created_at=datetime.now(JST)
                )
                db.session.add(lecture)
                db.session.commit()

                # メール通知の送信
                send_lecture_confirmation_email(lecturer.email, date_str, time_slot)
                send_reservation_confirmation_email(current_user.email, date_str, time_slot)

            else:
                send_reservation_confirmation_email(current_user.email, date_str, time_slot)

            return jsonify({'status': 'success', 'message': '予約が完了しました。'}), 201

        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"Database error during reservation POST: {e}")
            return jsonify({'status': 'error', 'message': 'データベースエラーが発生しました。'}), 500

        except Exception as e:
            db.session.rollback()
            logger.error(f"Unexpected error during reservation POST: {e}")
            return jsonify({'status': 'error', 'message': '予期せぬエラーが発生しました。'}), 500


# 予約確認
@api_terminal_bp.route('/reservation_confirm', methods=['GET'])
@login_required
def reservation_confirm():
    """
    ユーザーの現在有効な予約を取得します。
    """
    try:
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

        reservations_data = [
            {
                'id': res.id,
                'room_id': res.room_id,
                'terminal_id': res.terminal_id,
                'date': res.date.strftime('%Y-%m-%d'),
                'start_time': res.start_time.strftime('%H:%M'),
                'end_time': res.end_time.strftime('%H:%M'),
                'lecture_requested': res.request_flag,
                'lecture_accepted': res.accepted_flag
            } for res in reservations
        ]

        return jsonify({
            'status': 'success',
            'has_reservations': len(reservations_data) > 0,
            'reservations': reservations_data
        }), 200

    except SQLAlchemyError as e:
        logger.error(f"Database error during reservation confirm GET: {e}")
        return jsonify({'status': 'error', 'message': 'データベースエラーが発生しました。'}), 500

    except Exception as e:
        logger.error(f"Unexpected error during reservation confirm GET: {e}")
        return jsonify({'status': 'error', 'message': '予期せぬエラーが発生しました。'}), 500


# レクチャーリクエストの送信
@api_terminal_bp.route('/lecture_request', methods=['POST'])
@login_required
def lecture_request():
    """
    レクチャーリクエストを送信します。
    JSON形式で以下のデータを受け取ります。
    - lecturer_id: レクチャー担当者のID
    - reservation_id: 予約のID
    """
    try:
        if not request.is_json:
            return jsonify({'status': 'error', 'message': 'JSON形式のデータを送信してください。'}), 400

        data = request.get_json()
        lecturer_id = data.get('lecturer_id')
        reservation_id = data.get('reservation_id')

        if not lecturer_id or not reservation_id:
            return jsonify({'status': 'error', 'message': '必要な情報が不足しています。'}), 400

        reservation = Reservation.query.get(reservation_id)
        if not reservation or reservation.canceled:
            return jsonify({'status': 'error', 'message': '指定された予約が見つかりません。'}), 404

        if reservation.request_flag:
            return jsonify({'status': 'error', 'message': '既にレクチャーリクエストが送信されています。'}), 400

        lecturer = User.query.get(lecturer_id)
        if not lecturer or not lecturer.lecture_flug:
            return jsonify({'status': 'error', 'message': '指定されたレクチャー担当者が見つかりません。'}), 404

        # リクエスト情報を更新
        reservation.requested_user_id = current_user.id
        reservation.requested_time = reservation.start_time  # または必要な時間を設定
        reservation.request_flag = True
        db.session.commit()

        # メール通知の送信
        send_new_request_received_email(lecturer.email)
        send_request_email(current_user.email)

        return jsonify({'status': 'success', 'message': 'レクチャーリクエストが送信されました。'}), 200

    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"Database error during lecture request POST: {e}")
        return jsonify({'status': 'error', 'message': 'データベースエラーが発生しました。'}), 500

    except Exception as e:
        db.session.rollback()
        logger.error(f"Unexpected error during lecture request POST: {e}")
        return jsonify({'status': 'error', 'message': '予期せぬエラーが発生しました。'}), 500


# レクチャーリクエストの承諾・拒否
@api_terminal_bp.route('/process_lecture_request', methods=['POST'])
@login_required
def process_lecture_request():
    """
    レクチャーリクエストの承諾・拒否を行います。
    JSON形式で以下のデータを受け取ります。
    - request_id: リクエストのID（予約ID）
    - action: "accept" または "reject"
    """
    try:
        if not current_user.lecture_flug:
            return jsonify({'status': 'error', 'message': 'レクチャー担当のみがこの操作を行えます。'}), 403

        if not request.is_json:
            return jsonify({'status': 'error', 'message': 'JSON形式のデータを送信してください。'}), 400

        data = request.get_json()
        request_id = data.get('request_id')
        action = data.get('action')

        if not request_id or action not in ['accept', 'reject']:
            return jsonify({'status': 'error', 'message': '無効なリクエストです。'}), 400

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

            # リクエスト送信者に承諾メールを送信
            send_accept_request_email(requester.email, reservation, current_user)
            send_accept_request_to_sender_email(requester.email, reservation, current_user.email)

            return jsonify({'status': 'success', 'message': 'リクエストを承諾しました。'}), 200

        elif action == 'reject':
            reservation.lecturer_id = None
            reservation.requested_user_id = None
            reservation.requested_time = None
            reservation.request_flag = False
            db.session.commit()

            send_reject_request_email(requester.email, reservation, current_user)
            send_reject_request_to_sender_email(requester.email, reservation, current_user.email)

            return jsonify({'status': 'success', 'message': 'リクエストを拒否しました。'}), 200

        return jsonify({'status': 'error', 'message': '無効なアクションです。'}), 400

    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"Database error during processing lecture request POST: {e}")
        return jsonify({'status': 'error', 'message': 'データベースエラーが発生しました。'}), 500

    except Exception as e:
        db.session.rollback()
        logger.error(f"Unexpected error during processing lecture request POST: {e}")
        return jsonify({'status': 'error', 'message': '予期せぬエラーが発生しました。'}), 500


# 予約のキャンセル
@api_terminal_bp.route('/cancel_reservation', methods=['POST'])
@login_required
def cancel_reservation():
    """
    ユーザーが予約をキャンセルします。
    JSON形式で以下のデータを受け取ります。
    - reservation_id: キャンセルする予約のID
    """
    try:
        if not request.is_json:
            return jsonify({'status': 'error', 'message': 'JSON形式のデータを送信してください。'}), 400

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
            logger.error(f"Error during reservation cancellation POST: {e}", exc_info=True)
            return jsonify({'status': 'error', 'message': '予約のキャンセル中にエラーが発生しました。'}), 500

    except Exception as e:
        logger.error(f"Unexpected error during reservation cancellation POST: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': '予期せぬエラーが発生しました。'}), 500


# 複数予約のキャンセル
@api_terminal_bp.route('/cancel_multiple_reservations', methods=['POST'])
@login_required
def cancel_multiple_reservations():
    """
    ユーザーが複数の予約をキャンセルします。
    JSON形式で以下のデータを受け取ります。
    - reservation_ids: キャンセルする予約のIDリスト
    """
    try:
        if not request.is_json:
            return jsonify({'status': 'error', 'message': 'JSON形式のデータを送信してください。'}), 400

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
            return jsonify({'status': 'success', 'message': '選択された予約がキャンセルされました。'}), 200

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error during multiple reservations cancellation POST: {e}", exc_info=True)
            return jsonify({'status': 'error', 'message': '予約のキャンセル中にエラーが発生しました。'}), 500

    except Exception as e:
        logger.error(f"Unexpected error during multiple reservations cancellation POST: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': '予期せぬエラーが発生しました。'}), 500


# レクチャー担当者のお気に入り管理
@api_terminal_bp.route('/favorite_lecturer', methods=['POST'])
@login_required
def favorite_lecturer():
    """
    レクチャー担当者をお気に入りに追加します。
    JSON形式で以下のデータを受け取ります。
    - lecturer_id: レクチャー担当者のID
    """
    try:
        if not request.is_json:
            return jsonify({'status': 'error', 'message': 'JSON形式のデータを送信してください。'}), 400

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
            logger.error(f"Error during favorite lecturer POST: {e}", exc_info=True)
            return jsonify({'status': 'error', 'message': 'レクチャー担当者のお気に入り追加中にエラーが発生しました。'}), 500

    except Exception as e:
        logger.error(f"Unexpected error during favorite lecturer POST: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': '予期せぬエラーが発生しました。'}), 500


@api_terminal_bp.route('/unfavorite_lecturer', methods=['POST'])
@login_required
def unfavorite_lecturer():
    """
    レクチャー担当者のお気に入りを解除します。
    JSON形式で以下のデータを受け取ります。
    - lecturer_id: レクチャー担当者のID
    """
    try:
        if not request.is_json:
            return jsonify({'status': 'error', 'message': 'JSON形式のデータを送信してください。'}), 400

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
            return jsonify({'status': 'success', 'message': 'レクチャー担当者のお気に入りを解除しました。'}), 200

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error during unfavorite lecturer POST: {e}", exc_info=True)
            return jsonify({'status': 'error', 'message': 'レクチャー担当者のお気に入り解除中にエラーが発生しました。'}), 500

    except Exception as e:
        logger.error(f"Unexpected error during unfavorite lecturer POST: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': '予期せぬエラーが発生しました。'}), 500


# レクチャー担当者の検索
@api_terminal_bp.route('/search_lecturers', methods=['GET'])
@login_required
def search_lecturers():
    """
    レクチャー担当者を検索します。
    クエリパラメータ:
    - query: 検索キーワード（任意）
    """
    search_query = request.args.get('query', '').lower()

    try:
        if search_query:
            lecturers = User.query.filter(
                User.lecture_flug == True,
                or_(
                    User.contact_name.ilike(f'%{search_query}%'),
                    User.company_name.ilike(f'%{search_query}%')
                )
            ).all()
        else:
            lecturers = User.query.filter_by(lecture_flug=True).all()

        result = []
        for lecturer in lecturers:
            is_favorite = current_user.favorite_lecturers.filter_by(id=lecturer.id).first() is not None
            result.append({
                'id': lecturer.id,
                'contact_name': lecturer.contact_name,
                'is_favorite': is_favorite
            })

        return jsonify({'status': 'success', 'lecturers': result}), 200

    except SQLAlchemyError as e:
        logger.error(f"Database error during lecturers search: {e}")
        return jsonify({'status': 'error', 'message': 'データベースエラーが発生しました。'}), 500

    except Exception as e:
        logger.error(f"Unexpected error during lecturers search: {e}")
        return jsonify({'status': 'error', 'message': '予期せぬエラーが発生しました。'}), 500


# 利用可能なレクチャー担当者の取得
@api_terminal_bp.route('/available_lecturers', methods=['GET'])
@login_required
def available_lecturers():
    """
    指定された日付と時間に利用可能なレクチャー担当者を取得します。
    クエリパラメータ:
    - date: 日付（YYYY-MM-DD）
    - time: 時間（HH:MM）
    """
    date_str = request.args.get('date')
    time_str = request.args.get('time')

    if not date_str or not time_str:
        return jsonify({'status': 'error', 'message': 'date と time を指定してください。'}), 400

    try:
        date = datetime.strptime(date_str, '%Y-%m-%d').date()
        time_obj = datetime.strptime(time_str, '%H:%M').time()
    except ValueError:
        return jsonify({'status': 'error', 'message': '日付や時間の形式が無効です。'}), 400

    try:
        # レクチャー担当者のみを対象とする
        lecturers = User.query.filter_by(lecture_flug=True).all()

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

        return jsonify({'status': 'success', 'available_lecturers': available_lecturers}), 200

    except SQLAlchemyError as e:
        logger.error(f"Database error during available lecturers GET: {e}")
        return jsonify({'status': 'error', 'message': 'データベースエラーが発生しました。'}), 500

    except Exception as e:
        logger.error(f"Unexpected error during available lecturers GET: {e}")
        return jsonify({'status': 'error', 'message': '予期せぬエラーが発生しました。'}), 500


# お気に入りターミナルの追加
@api_terminal_bp.route('/favorite_terminal', methods=['POST'])
@login_required
def favorite_terminal():
    """
    ターミナルをお気に入りに追加します。
    JSON形式で以下のデータを受け取ります。
    - terminal_id: ターミナルのID
    """
    try:
        if not request.is_json:
            return jsonify({'status': 'error', 'message': 'JSON形式のデータを送信してください。'}), 400

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
            logger.error(f"Error during favorite terminal POST: {e}", exc_info=True)
            return jsonify({'status': 'error', 'message': 'ターミナルのお気に入り追加中にエラーが発生しました。'}), 500

    except Exception as e:
        logger.error(f"Unexpected error during favorite terminal POST: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': '予期せぬエラーが発生しました。'}), 500


# お気に入りターミナルの解除
@api_terminal_bp.route('/unfavorite_terminal', methods=['POST'])
@login_required
def unfavorite_terminal():
    """
    ターミナルのお気に入りを解除します。
    JSON形式で以下のデータを受け取ります。
    - terminal_id: ターミナルのID
    """
    try:
        if not request.is_json:
            return jsonify({'status': 'error', 'message': 'JSON形式のデータを送信してください。'}), 400

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
            return jsonify({'status': 'success', 'message': 'ターミナルのお気に入りを解除しました。'}), 200

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error during unfavorite terminal POST: {e}", exc_info=True)
            return jsonify({'status': 'error', 'message': 'ターミナルのお気に入り解除中にエラーが発生しました。'}), 500

    except Exception as e:
        logger.error(f"Unexpected error during unfavorite terminal POST: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': '予期せぬエラーが発生しました。'}), 500
