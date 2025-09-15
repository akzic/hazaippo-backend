# app/api/api_terminal_management.py

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models import Terminal, Room, Reservation, Material, User
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, timedelta, time
import pytz
import logging

api_terminal_management_bp = Blueprint('api_terminal_management', __name__, url_prefix='/api/terminal_management')
JST = pytz.timezone('Asia/Tokyo')
logger = logging.getLogger(__name__)


def get_current_user():
    """
    JWT からユーザーIDを取得し、DB からユーザーをロードするヘルパー関数
    """
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    return user


# １．ターミナル予約管理（画面表示相当の情報を JSON で返す）
@api_terminal_management_bp.route('/reservation/management', methods=['GET'])
@jwt_required()
def reservation_management():
    current_user = get_current_user()
    if not current_user:
        return jsonify({'success': False, 'error': 'ユーザーが見つかりません。'}), 404

    if not current_user.affiliated_terminal_id:
        return jsonify({'success': False, 'error': 'あなたには紐づいたターミナルがありません。'}), 400

    terminal = Terminal.query.get(current_user.affiliated_terminal_id)
    if not terminal:
        return jsonify({'success': False, 'error': '紐づいたターミナルが見つかりません。'}), 404

    # 指定ターミナルの部屋を取得
    rooms = Room.query.filter_by(terminal_id=terminal.id).all()
    rooms_data = [{
        'id': room.id,
        'name': room.name  # ※ 必要に応じて他の情報も追加
    } for room in rooms]

    today = datetime.now(JST).date()
    min_date = today.strftime('%Y-%m-%d')
    max_date = (today + timedelta(days=30)).strftime('%Y-%m-%d')
    date_options = [(today + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(31)]

    # 空のスケジュール（9:00～22:00、各1時間枠）
    schedule = []
    for hour in range(9, 22):
        time_slot = f"{hour:02d}:00 ~ {hour+1:02d}:00"
        schedule.append({
            'time': time_slot,
            'user_name': None,
            'lecturer_name': None,
            'reservation_id': None
        })

    return jsonify({
        'success': True,
        'data': {
            'rooms': rooms_data,
            'schedule': schedule,
            'today': today.strftime('%Y-%m-%d'),
            'min_date': min_date,
            'max_date': max_date,
            'date_options': date_options
        }
    }), 200


# ２．APIエンドポイント: スケジュール取得（部屋・日付指定）
@api_terminal_management_bp.route('/get_schedule', methods=['GET'])
@jwt_required()
def get_schedule():
    current_user = get_current_user()
    if not current_user:
        return jsonify({'status': 'error', 'message': 'ユーザーが見つかりません。'}), 404

    room_id = request.args.get('room_id')
    date_str = request.args.get('date')

    if not room_id or not date_str:
        return jsonify({'status': 'error', 'message': '部屋と日付を指定してください。'}), 400

    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'status': 'error', 'message': '日付の形式が正しくありません。'}), 400

    room = Room.query.get(room_id)
    if not room or room.terminal_id != current_user.affiliated_terminal_id:
        return jsonify({'status': 'error', 'message': '部屋が見つからないか、アクセス権がありません。'}), 404

    # 9:00～22:00の予約を取得
    reservations = Reservation.query.filter(
        Reservation.room_id == room_id,
        Reservation.date == target_date,
        Reservation.canceled == False,
        Reservation.start_time >= time(9, 0),
        Reservation.start_time < time(23, 0)
    ).all()

    # スケジュールの初期化（9:00～22:00の1時間枠）
    schedule = []
    for hour in range(9, 23):
        time_slot = f"{hour:02d}:00 ~ {hour+1:02d}:00"
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
            schedule[index]['lecturer_name'] = (reservation.lecturer.contact_name 
                                                  if reservation.lecturer else 'レクチャー担当なし')
            schedule[index]['reservation_id'] = reservation.id

    return jsonify({'status': 'success', 'schedule': schedule}), 200


# ３．APIエンドポイント: 予約削除
@api_terminal_management_bp.route('/delete_reservation/<int:reservation_id>', methods=['DELETE'])
@jwt_required()
def delete_reservation(reservation_id):
    current_user = get_current_user()
    if not current_user:
        return jsonify({'status': 'error', 'message': 'ユーザーが見つかりません。'}), 404

    reservation = Reservation.query.get(reservation_id)
    if not reservation:
        return jsonify({'status': 'error', 'message': '指定された予約が見つかりません。'}), 404

    if reservation.terminal_id != current_user.affiliated_terminal_id:
        return jsonify({'status': 'error', 'message': 'この予約を削除する権限がありません。'}), 403

    try:
        reservation.canceled = True
        db.session.commit()
        return jsonify({'status': 'success', 'message': '予約が削除されました。'}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"予約削除中にエラーが発生しました: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': '予約の削除中にエラーが発生しました。'}), 500


# ４．ターミナル資材管理：登録済み材料一覧の取得
@api_terminal_management_bp.route('/material/management', methods=['GET'])
@jwt_required()
def terminal_material_management():
    current_user = get_current_user()
    if not current_user:
        return jsonify({'success': False, 'error': 'ユーザーが見つかりません。'}), 404

    if current_user.affiliated_terminal_id is None:
        return jsonify({'success': False, 'error': 'あなたには紐づいたターミナルがありません。'}), 400

    terminal = Terminal.query.get(current_user.affiliated_terminal_id)
    if not terminal:
        return jsonify({'success': False, 'error': '紐づいたターミナルが見つかりません。'}), 404

    # 同一ターミナルに紐づくユーザーの ID を取得
    affiliated_users = User.query.filter_by(affiliated_terminal_id=terminal.id).all()
    affiliated_user_ids = [user.id for user in affiliated_users]

    # 資材はこれらのユーザーが登録したもの
    materials = Material.query.filter(Material.user_id.in_(affiliated_user_ids)).all()
    materials_data = []
    for material in materials:
        materials_data.append({
            'id': material.id,
            'type': material.type,
            'quantity': material.quantity,
            'size_1': material.size_1,
            'size_2': material.size_2,
            'size_3': material.size_3,
            'location': material.location,
            'note': material.note,
            'user_id': material.user_id
        })

    return jsonify({
        'success': True,
        'data': {
            'materials': materials_data,
            'terminal_name': terminal.name,
            'is_admin': current_user.is_terminal_admin
        }
    }), 200


# ５．APIエンドポイント: 資材削除
@api_terminal_management_bp.route('/material/delete', methods=['POST'])
@jwt_required()
def delete_material():
    current_user = get_current_user()
    if not current_user:
        return jsonify({'status': 'error', 'message': 'ユーザーが見つかりません。'}), 404

    data = request.get_json()
    material_id = data.get('material_id')
    if not material_id:
        return jsonify({'status': 'error', 'message': 'material_id を指定してください。'}), 400

    material = Material.query.get(material_id)
    if not material:
        return jsonify({'status': 'error', 'message': '指定された資材が見つかりません。'}), 404

    # 資材の編集・削除は登録ユーザーまたはターミナル管理者のみ可能
    if not (material.user_id == current_user.id or current_user.is_terminal_admin):
        return jsonify({'status': 'error', 'message': 'この資材を削除する権限がありません。'}), 403

    try:
        db.session.delete(material)
        db.session.commit()
        return jsonify({'status': 'success', 'message': '資材が削除されました。'}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"資材削除中にエラーが発生しました: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': '資材の削除中にエラーが発生しました。'}), 500


# ６．APIエンドポイント: 資材更新
@api_terminal_management_bp.route('/material/update/<int:material_id>', methods=['POST'])
@jwt_required()
def update_material(material_id):
    current_user = get_current_user()
    if not current_user:
        return jsonify({'status': 'error', 'message': 'ユーザーが見つかりません。'}), 404

    material = Material.query.get(material_id)
    if not material:
        return jsonify({'status': 'error', 'message': '指定された資材が見つかりません。'}), 404

    if not (material.user_id == current_user.id or current_user.is_terminal_admin):
        return jsonify({'status': 'error', 'message': 'この資材を編集する権限がありません。'}), 403

    data = request.get_json()
    action = data.get('action')
    if action != 'edit':
        return jsonify({'status': 'error', 'message': '無効なアクションです。'}), 400

    # 必須フィールドのチェック
    required_fields = ['type', 'quantity', 'size_1', 'size_2', 'size_3']
    missing_fields = [field for field in required_fields if not data.get(field)]
    if missing_fields:
        return jsonify({'status': 'error', 
                        'message': f'すべての必須フィールドを入力してください。欠落フィールド: {", ".join(missing_fields)}'}), 400

    try:
        material.type = data.get('type')
        material.quantity = int(data.get('quantity'))
        material.size_1 = data.get('size_1')
        material.size_2 = data.get('size_2')
        material.size_3 = data.get('size_3')
        # location, note はオプション。入力があれば更新
        if data.get('location'):
            material.location = data.get('location')
        if data.get('note'):
            material.note = data.get('note')
        db.session.commit()
        return jsonify({'status': 'success', 'message': '資材が更新されました。'}), 200
    except ValueError:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': '数量は数値でなければなりません。'}), 400
    except Exception as e:
        db.session.rollback()
        logger.error(f"資材更新中にエラーが発生しました: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': '資材の更新中にエラーが発生しました。'}), 500
