# app/api/api_terminal_management.py

from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from app import db
from app.models import Terminal, Room, Reservation, Lecture, Material, User, WorkingHours
from sqlalchemy.exc import SQLAlchemyError
import logging
from datetime import datetime, timedelta, time
import pytz

api_terminal_management_bp = Blueprint('api_terminal_management', __name__, url_prefix='/api/terminal_management')

JST = pytz.timezone('Asia/Tokyo')

# ロガーの設定
logger = logging.getLogger(__name__)

@api_terminal_management_bp.route('/reservations', methods=['GET'])
@login_required
def get_reservations():
    """
    ターミナルに関連する全ての予約を取得します。
    クエリパラメータで日付と部屋IDを指定可能。
    """
    room_id = request.args.get('room_id')
    date_str = request.args.get('date')

    if not room_id or not date_str:
        return jsonify({'status': 'error', 'message': 'room_id と date を指定してください。'}), 400

    try:
        date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'status': 'error', 'message': '日付の形式が正しくありません。'}), 400

    room = Room.query.get(room_id)
    if not room or room.terminal_id != current_user.affiliated_terminal_id:
        return jsonify({'status': 'error', 'message': '部屋が見つからないか、アクセス権がありません。'}), 404

    # 指定された部屋と日にちの予約を取得（9:00～22:00）
    reservations = Reservation.query.filter(
        Reservation.room_id == room_id,
        Reservation.date == date,
        Reservation.canceled == False,
        Reservation.start_time >= time(9, 0),
        Reservation.start_time < time(23, 0)
    ).all()

    # スケジュールを初期化
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

    return jsonify({'status': 'success', 'schedule': schedule}), 200


@api_terminal_management_bp.route('/reservations/<int:reservation_id>', methods=['DELETE'])
@login_required
def delete_reservation(reservation_id):
    """
    指定された予約を削除（キャンセル）します。
    """
    reservation = Reservation.query.get(reservation_id)
    if not reservation:
        return jsonify({'status': 'error', 'message': '指定された予約が見つかりません。'}), 404

    if reservation.terminal_id != current_user.affiliated_terminal_id:
        return jsonify({'status': 'error', 'message': 'この予約を削除する権限がありません。'}), 403

    try:
        reservation.canceled = True
        db.session.commit()

        # 予約削除時のメール通知（必要に応じて）
        # send_cancel_reservation_email(reservation)

        logger.info(f"予約ID {reservation_id} がユーザーID {current_user.id} によってキャンセルされました。")
        return jsonify({'status': 'success', 'message': '予約が削除されました。'}), 200

    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"予約削除中にデータベースエラーが発生しました: {e}")
        return jsonify({'status': 'error', 'message': '予約の削除中にデータベースエラーが発生しました。'}), 500

    except Exception as e:
        db.session.rollback()
        logger.error(f"予約削除中に予期せぬエラーが発生しました: {e}")
        return jsonify({'status': 'error', 'message': '予約の削除中に予期せぬエラーが発生しました。'}), 500


@api_terminal_management_bp.route('/materials', methods=['GET', 'POST'])
@login_required
def manage_materials():
    """
    ターミナルに関連する端材の管理を行います。
    GET: 端材の一覧を取得。
    POST: 新しい端材を追加または既存の端材を編集。
    """
    if current_user.affiliated_terminal_id is None:
        return jsonify({'status': 'error', 'message': 'あなたには紐づいたターミナルがありません。'}), 403

    terminal = Terminal.query.get(current_user.affiliated_terminal_id)
    if not terminal:
        return jsonify({'status': 'error', 'message': '紐づいたターミナルが見つかりません。'}), 404

    if request.method == 'GET':
        try:
            # ターミナルに所属するユーザーのIDを取得
            affiliated_users = User.query.filter_by(affiliated_terminal_id=terminal.id).all()
            affiliated_user_ids = [user.id for user in affiliated_users]

            # 端材を取得
            materials = Material.query.filter(Material.user_id.in_(affiliated_user_ids)).all()

            materials_data = [
                {
                    'id': material.id,
                    'type': material.type,
                    'quantity': material.quantity,
                    'size_1': material.size_1,
                    'size_2': material.size_2,
                    'size_3': material.size_3,
                    'location': material.location,
                    'note': material.note,
                    'user_id': material.user_id,
                    'user_email': material.user.email
                } for material in materials
            ]

            return jsonify({'status': 'success', 'materials': materials_data}), 200

        except SQLAlchemyError as e:
            logger.error(f"端材取得中にデータベースエラーが発生しました: {e}")
            return jsonify({'status': 'error', 'message': '端材取得中にデータベースエラーが発生しました。'}), 500

        except Exception as e:
            logger.error(f"端材取得中に予期せぬエラーが発生しました: {e}")
            return jsonify({'status': 'error', 'message': '端材取得中に予期せぬエラーが発生しました。'}), 500

    elif request.method == 'POST':
        """
        端材の追加または編集を行います。
        JSON形式で以下のデータを受け取ります。
        - action: 'add' または 'edit'
        - material_id: 編集する場合に必要
        - type, quantity, size_1, size_2, size_3: 端材の詳細
        - location, note: オプショナル
        """
        try:
            if not request.is_json:
                return jsonify({'status': 'error', 'message': 'JSON形式のデータを送信してください。'}), 400

            data = request.get_json()
            action = data.get('action')
            type_ = data.get('type')
            quantity = data.get('quantity')
            size_1 = data.get('size_1')
            size_2 = data.get('size_2')
            size_3 = data.get('size_3')
            location = data.get('location', '').strip()
            note = data.get('note', '').strip()

            if action not in ['add', 'edit']:
                return jsonify({'status': 'error', 'message': '有効なアクションを指定してください。'}), 400

            # バリデーション
            if not all([type_, quantity, size_1, size_2, size_3]):
                return jsonify({'status': 'error', 'message': 'type, quantity, size_1, size_2, size_3 は必須フィールドです。'}), 400

            if not isinstance(quantity, int) or quantity <= 0:
                return jsonify({'status': 'error', 'message': 'quantity は正の整数でなければなりません。'}), 400

            if not all(isinstance(s, (int, float)) for s in [size_1, size_2, size_3]):
                return jsonify({'status': 'error', 'message': 'size_1, size_2, size_3 は数値でなければなりません。'}), 400

            if action == 'add':
                # 新しい端材の作成
                new_material = Material(
                    user_id=current_user.id,
                    type=type_,
                    quantity=quantity,
                    size_1=size_1,
                    size_2=size_2,
                    size_3=size_3,
                    location=location if location else None,
                    note=note if note else None
                )
                db.session.add(new_material)
                db.session.commit()

                logger.info(f"ユーザーID {current_user.id} によって端材ID {new_material.id} が追加されました。")
                return jsonify({'status': 'success', 'message': '端材が正常に追加されました。'}), 201

            elif action == 'edit':
                material_id = data.get('material_id')
                if not material_id:
                    return jsonify({'status': 'error', 'message': 'material_id が必要です。'}), 400

                material = Material.query.get(material_id)
                if not material:
                    return jsonify({'status': 'error', 'message': '指定された端材が見つかりません。'}), 404

                if not (material.user_id == current_user.id or current_user.is_terminal_admin):
                    return jsonify({'status': 'error', 'message': 'この端材を編集する権限がありません。'}), 403

                # 更新
                material.type = type_
                material.quantity = quantity
                material.size_1 = size_1
                material.size_2 = size_2
                material.size_3 = size_3
                material.location = location if location else material.location
                material.note = note if note else material.note

                db.session.commit()

                logger.info(f"端材ID {material_id} がユーザーID {current_user.id} によって編集されました。")
                return jsonify({'status': 'success', 'message': '端材が正常に更新されました。'}), 200

        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"端材管理中にデータベースエラーが発生しました: {e}")
            return jsonify({'status': 'error', 'message': '端材管理中にデータベースエラーが発生しました。'}), 500

        except Exception as e:
            db.session.rollback()
            logger.error(f"端材管理中に予期せぬエラーが発生しました: {e}")
            return jsonify({'status': 'error', 'message': '端材管理中に予期せぬエラーが発生しました。'}), 500


@api_terminal_management_bp.route('/materials/<int:material_id>', methods=['DELETE'])
@login_required
def delete_material(material_id):
    """
    指定された端材を削除します。
    """
    material = Material.query.get(material_id)
    if not material:
        return jsonify({'status': 'error', 'message': '指定された端材が見つかりません。'}), 404

    if not (material.user_id == current_user.id or current_user.is_terminal_admin):
        return jsonify({'status': 'error', 'message': 'この端材を削除する権限がありません。'}), 403

    try:
        db.session.delete(material)
        db.session.commit()

        logger.info(f"端材ID {material_id} がユーザーID {current_user.id} によって削除されました。")
        return jsonify({'status': 'success', 'message': '端材が削除されました。'}), 200

    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"端材削除中にデータベースエラーが発生しました: {e}")
        return jsonify({'status': 'error', 'message': '端材削除中にデータベースエラーが発生しました。'}), 500

    except Exception as e:
        db.session.rollback()
        logger.error(f"端材削除中に予期せぬエラーが発生しました: {e}")
        return jsonify({'status': 'error', 'message': '端材削除中に予期せぬエラーが発生しました。'}), 500


@api_terminal_management_bp.route('/schedule', methods=['GET'])
@login_required
def get_schedule_api():
    """
    指定された部屋と日にちのスケジュールを取得します。
    クエリパラメータで room_id と date を指定。
    """
    room_id = request.args.get('room_id')
    date_str = request.args.get('date')

    if not room_id or not date_str:
        return jsonify({'status': 'error', 'message': 'room_id と date を指定してください。'}), 400

    try:
        date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'status': 'error', 'message': '日付の形式が正しくありません。'}), 400

    room = Room.query.get(room_id)
    if not room or room.terminal_id != current_user.affiliated_terminal_id:
        return jsonify({'status': 'error', 'message': '部屋が見つからないか、アクセス権がありません。'}), 404

    # 指定された部屋と日にちの予約を取得（9:00～22:00）
    reservations = Reservation.query.filter(
        Reservation.room_id == room_id,
        Reservation.date == date,
        Reservation.canceled == False,
        Reservation.start_time >= time(9, 0),
        Reservation.start_time < time(23, 0)
    ).all()

    # スケジュールを初期化
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

    return jsonify({'status': 'success', 'schedule': schedule}), 200
