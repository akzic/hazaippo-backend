# app/api/api_site.py

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models import Site, User
from sqlalchemy.exc import SQLAlchemyError

api_site_bp = Blueprint('api_site', __name__, url_prefix='/api/site')

@api_site_bp.route('/register', methods=['GET', 'POST'])
@jwt_required()
def register_site():
    """
    GET: 同じ法人に属するユーザー一覧と現在のユーザーの都道府県情報を返す。
    POST: JSON 形式のデータを受け取り、新規の現場を登録する。
    """
    user_id = get_jwt_identity()
    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({'success': False, 'error': 'ユーザーが見つかりません。'}), 404

    if request.method == 'GET':
        # 同じ法人に属する参加者を、現在のユーザーを除いて取得
        company_name = current_user.company_name
        participants = User.query.filter(
            User.company_name == company_name,
            User.id != current_user.id
        ).all()
        # シリアライズ（必要な情報だけ）
        participants_list = [{
            'id': user.id,
            'email': user.email,
            'prefecture': user.prefecture,
            'city': user.city,
            'company_name': user.company_name
        } for user in participants]
        return jsonify({
            'success': True,
            'data': {
                'participants': participants_list,
                'user_prefecture': current_user.prefecture
            }
        }), 200

    elif request.method == 'POST':
        try:
            data = request.get_json()
            site_prefecture = data.get('site_prefecture', '').strip()
            site_city = data.get('site_city', '').strip()
            site_address = data.get('site_address', '').strip()
            participant_ids = data.get('participants', [])

            # バリデーション
            if not site_prefecture:
                return jsonify({'success': False, 'error': '現場県を選択してください。'}), 400
            if not site_city:
                return jsonify({'success': False, 'error': '市を入力してください。'}), 400
            if not site_address:
                return jsonify({'success': False, 'error': 'それ以降の住所を入力してください。'}), 400

            # 住所の重複チェック（同じ法人内での組み合わせ）
            existing_site = Site.query.join(User).filter(
                Site.site_prefecture == site_prefecture,
                Site.site_city == site_city,
                Site.site_address == site_address,
                User.company_name == current_user.company_name
            ).first()
            if existing_site:
                return jsonify({'success': False, 'error': 'この住所は既に登録されています。'}), 400

            # 参加者の検証（存在するユーザーかどうかをチェック）
            if participant_ids:
                participants = User.query.filter(User.id.in_(participant_ids)).all()
                if len(participants) != len(participant_ids):
                    return jsonify({'success': False, 'error': '選択された参加者に無効なユーザーが含まれています。'}), 400
            else:
                participant_ids = []

            # 新しい Site オブジェクトの作成
            new_site = Site(
                registered_user_id=current_user.id,
                site_prefecture=site_prefecture,
                site_city=site_city,
                site_address=site_address,
                location=f"{site_prefecture}{site_city}{site_address}",
                registered_company=current_user.company_name,
                participants=participant_ids
            )

            db.session.add(new_site)
            db.session.commit()

            return jsonify({'success': True}), 200

        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Database error: {e}")
            return jsonify({'success': False, 'error': 'データベースエラーが発生しました。'}), 500

        except Exception as e:
            current_app.logger.error(f"Unexpected error: {e}")
            return jsonify({'success': False, 'error': '予期せぬエラーが発生しました。'}), 500


@api_site_bp.route('/check_address', methods=['POST'])
@jwt_required()
def check_address():
    """
    POST: JSON形式で送信された現場の住所（県、市、以降の住所）に対して、同一法人内での重複があるかチェックする。
    """
    try:
        user_id = get_jwt_identity()
        current_user = User.query.get(user_id)
        if not current_user:
            return jsonify({'success': False, 'error': 'ユーザーが見つかりません。'}), 404

        data = request.get_json()
        site_prefecture = data.get('site_prefecture', '').strip()
        site_city = data.get('site_city', '').strip()
        site_address = data.get('site_address', '').strip()

        if not site_prefecture or not site_city or not site_address:
            return jsonify({'success': False, 'error': '現場県、市、住所をすべて入力してください。'}), 400

        existing_site = Site.query.join(User).filter(
            Site.site_prefecture == site_prefecture,
            Site.site_city == site_city,
            Site.site_address == site_address,
            User.company_name == current_user.company_name
        ).first()

        if existing_site:
            return jsonify({'exists': True}), 200
        else:
            return jsonify({'exists': False}), 200

    except SQLAlchemyError as e:
        current_app.logger.error(f"Database error during address check: {e}")
        return jsonify({'success': False, 'error': 'データベースエラーが発生しました。'}), 500

    except Exception as e:
        current_app.logger.error(f"Unexpected error during address check: {e}")
        return jsonify({'success': False, 'error': '予期せぬエラーが発生しました。'}), 500


@api_site_bp.route('/get_user_sites', methods=['GET'])
@jwt_required()
def get_user_sites():
    """
    GET: 現在のユーザーが登録した、または参加者に含まれる現場の住所一覧を返す。
    """
    try:
        user_id = get_jwt_identity()
        current_user = User.query.get(user_id)
        if not current_user:
            return jsonify({'success': False, 'error': 'ユーザーが見つかりません。'}), 404

        sites = Site.query.filter(
            (Site.registered_user_id == current_user.id) |
            (Site.participants.contains([current_user.id]))
        ).all()
        site_addresses = [site.location for site in sites]
        current_app.logger.debug(f"Fetched sites for user {current_user.id}: {site_addresses}")
        return jsonify({'success': True, 'sites': site_addresses}), 200

    except SQLAlchemyError as e:
        current_app.logger.error(f"Database error fetching user sites: {e}")
        return jsonify({'success': False, 'error': 'データベースエラーが発生しました。'}), 500

    except Exception as e:
        current_app.logger.error(f"Unexpected error fetching user sites: {e}")
        return jsonify({'success': False, 'error': '予期せぬエラーが発生しました。'}), 500
