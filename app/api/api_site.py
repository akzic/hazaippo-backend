# app/api/api_site.py

from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from app import db
from app.models import Site, User
from sqlalchemy.exc import SQLAlchemyError

api_site_bp = Blueprint('api_site', __name__, url_prefix='/api/site')

@api_site_bp.route('/register', methods=['GET', 'POST'])
@login_required
def register_site():
    if request.method == 'GET':
        """
        現場登録に必要なデータを取得します。
        - 同じ法人に属するユーザーのリスト（現在のユーザーを除く）
        - 現在のユーザーの都道府県
        """
        try:
            company_name = current_user.company_name
            participants = User.query.filter(
                User.company_name == company_name,
                User.id != current_user.id
            ).all()
            participants_data = [
                {
                    'id': user.id,
                    'email': user.email,
                    'name': f"{user.first_name} {user.last_name}"
                } for user in participants
            ]

            user_prefecture = current_user.prefecture

            return jsonify({
                'success': True,
                'data': {
                    'participants': participants_data,
                    'user_prefecture': user_prefecture
                }
            }), 200

        except SQLAlchemyError as e:
            current_app.logger.error(f"Database error during site registration GET: {e}")
            return jsonify({'success': False, 'message': 'データベースエラーが発生しました。'}), 500

        except Exception as e:
            current_app.logger.error(f"Unexpected error during site registration GET: {e}")
            return jsonify({'success': False, 'message': '予期せぬエラーが発生しました。'}), 500

    elif request.method == 'POST':
        """
        新しい現場を登録します。
        JSON形式で以下のデータを受け取ります。
        - site_prefecture: 現場の都道府県
        - site_city: 現場の市
        - site_address: 現場の住所
        - participants: 参加者のユーザーIDリスト（任意）
        """
        try:
            if not request.is_json:
                return jsonify({'success': False, 'message': 'JSON形式のデータを送信してください。'}), 400

            data = request.get_json()
            site_prefecture = data.get('site_prefecture', '').strip()
            site_city = data.get('site_city', '').strip()
            site_address = data.get('site_address', '').strip()
            participant_ids = data.get('participants', [])

            # バリデーション
            if not site_prefecture:
                return jsonify({'success': False, 'message': '現場県を選択してください。'}), 400
            if not site_city:
                return jsonify({'success': False, 'message': '市を入力してください。'}), 400
            if not site_address:
                return jsonify({'success': False, 'message': 'それ以降の住所を入力してください。'}), 400

            # 住所の重複チェック（同じ法人内での都道府県、市、住所の組み合わせ）
            existing_site = Site.query.join(User).filter(
                Site.site_prefecture == site_prefecture,
                Site.site_city == site_city,
                Site.site_address == site_address,
                User.company_name == current_user.company_name
            ).first()
            if existing_site:
                return jsonify({'success': False, 'message': 'この住所は既に登録されています。'}), 400

            # 参加者の検証（任意）
            if participant_ids:
                participants = User.query.filter(User.id.in_(participant_ids)).all()
                if len(participants) != len(participant_ids):
                    return jsonify({'success': False, 'message': '選択された参加者に無効なユーザーが含まれています。'}), 400
            else:
                participant_ids = []

            # 新しいSiteオブジェクトの作成
            new_site = Site(
                registered_user_id=current_user.id,
                site_prefecture=site_prefecture,
                site_city=site_city,
                site_address=site_address,
                location=f"{site_prefecture}{site_city}{site_address}",
                registered_company=current_user.company_name,
                participants=participant_ids  # participantsがリストであることを前提
                # site_created_at はデフォルトで設定されます
            )

            # データベースに追加
            db.session.add(new_site)
            db.session.commit()

            # アクティビティログの記録（必要に応じて実装）
            # log_user_activity(...)

            return jsonify({'success': True, 'message': '現場が正常に登録されました。'}), 201

        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Database error during site registration POST: {e}")
            return jsonify({'success': False, 'message': 'データベースエラーが発生しました。'}), 500

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Unexpected error during site registration POST: {e}")
            return jsonify({'success': False, 'message': '予期せぬエラーが発生しました。'}), 500

@api_site_bp.route('/check_address', methods=['POST'])
@login_required
def check_address():
    """
    指定された住所が既に登録されているかを確認します。
    JSON形式で以下のデータを受け取ります。
    - site_prefecture: 現場の都道府県
    - site_city: 現場の市
    - site_address: 現場の住所
    """
    try:
        if not request.is_json:
            return jsonify({'success': False, 'message': 'JSON形式のデータを送信してください。'}), 400

        data = request.get_json()
        site_prefecture = data.get('site_prefecture', '').strip()
        site_city = data.get('site_city', '').strip()
        site_address = data.get('site_address', '').strip()

        if not site_prefecture or not site_city or not site_address:
            return jsonify({'success': False, 'message': '現場県、市、住所をすべて入力してください。'}), 400

        # 住所の重複チェック（同じ法人内での都道府県、市、住所の組み合わせ）
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
        return jsonify({'success': False, 'message': 'データベースエラーが発生しました。'}), 500

    except Exception as e:
        current_app.logger.error(f"Unexpected error during address check: {e}")
        return jsonify({'success': False, 'message': '予期せぬエラーが発生しました。'}), 500

@api_site_bp.route('/user_sites', methods=['GET'])
@login_required
def get_user_sites():
    """
    現在のユーザーに関連する現場の一覧を取得します。
    """
    try:
        # 現在のユーザーが登録した現場、または参加者として登録されている現場を取得
        sites = Site.query.filter(
            (Site.registered_user_id == current_user.id) | (Site.participants.contains([current_user.id]))
        ).all()

        site_addresses = [
            {
                'id': site.id,
                'prefecture': site.site_prefecture,
                'city': site.site_city,
                'address': site.site_address,
                'location': site.location,
                'registered_company': site.registered_company,
                'registered_user_id': site.registered_user_id
            } for site in sites
        ]

        current_app.logger.debug(f"Fetched sites for user {current_user.id}: {site_addresses}")

        return jsonify({
            'success': True,
            'data': {
                'sites': site_addresses
            }
        }), 200

    except SQLAlchemyError as e:
        current_app.logger.error(f"Database error fetching user sites: {e}")
        return jsonify({'success': False, 'message': 'データベースエラーが発生しました。'}), 500

    except Exception as e:
        current_app.logger.error(f"Unexpected error fetching user sites: {e}")
        return jsonify({'success': False, 'message': '予期せぬエラーが発生しました。'}), 500
