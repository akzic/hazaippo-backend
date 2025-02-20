# app/blueprints/site.py

from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user
from app import db
from app.models import Site, User
from sqlalchemy.exc import SQLAlchemyError

site_bp = Blueprint('site', __name__, url_prefix='/site')

@site_bp.route('/register', methods=['GET', 'POST'])
@login_required
def register():
    if request.method == 'GET':
        # 同じ法人に属するユーザーを取得（登録ユーザーの会社名と一致）
        company_name = current_user.company_name
        # 現ユーザーを除外
        participants = User.query.filter(User.company_name == company_name, User.id != current_user.id).all()
        return render_template('register_site.html', users=participants, user_prefecture=current_user.prefecture)

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

            # 住所の重複チェック（同じ法人内での都道府県、市、住所の組み合わせ）
            existing_site = Site.query.join(User).filter(
                Site.site_prefecture == site_prefecture,
                Site.site_city == site_city,
                Site.site_address == site_address,
                User.company_name == current_user.company_name
            ).first()
            if existing_site:
                return jsonify({'success': False, 'error': 'この住所は既に登録されています。'}), 400

            # 参加者の検証（任意）
            if participant_ids:
                participants = User.query.filter(User.id.in_(participant_ids)).all()

                if len(participants) != len(participant_ids):
                    return jsonify({'success': False, 'error': '選択された参加者に無効なユーザーが含まれています。'}), 400
            else:
                participant_ids = []

            # 新しいSiteオブジェクトの作成
            new_site = Site(
                registered_user_id=current_user.id,
                site_prefecture=site_prefecture,
                site_city=site_city,
                site_address=site_address,
                location=f"{site_prefecture}{site_city}{site_address}",
                registered_company=current_user.company_name,  # registered_companyを設定
                participants=participant_ids,  # 参加者IDリストを格納（空でも可）
                # site_created_at はデフォルトで設定されます
            )

            # データベースに追加
            db.session.add(new_site)
            db.session.commit()

            return jsonify({'success': True}), 200

        except SQLAlchemyError as e:
            db.session.rollback()
            # ログにエラーを記録
            current_app.logger.error(f"Database error: {e}")
            return jsonify({'success': False, 'error': 'データベースエラーが発生しました。'}), 500

        except Exception as e:
            # その他のエラー処理
            current_app.logger.error(f"Unexpected error: {e}")
            return jsonify({'success': False, 'error': '予期せぬエラーが発生しました。'}), 500
        
@site_bp.route('/check_address', methods=['POST'])
@login_required
def check_address():
    try:
        data = request.get_json()
        site_prefecture = data.get('site_prefecture', '').strip()
        site_city = data.get('site_city', '').strip()
        site_address = data.get('site_address', '').strip()

        if not site_prefecture or not site_city or not site_address:
            return jsonify({'success': False, 'error': '現場県、市、住所をすべて入力してください。'}), 400

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
        return jsonify({'success': False, 'error': 'データベースエラーが発生しました。'}), 500

    except Exception as e:
        current_app.logger.error(f"Unexpected error during address check: {e}")
        return jsonify({'success': False, 'error': '予期せぬエラーが発生しました。'}), 500

@site_bp.route('/get_user_sites', methods=['GET'])
@login_required
def get_user_sites():
    try:
        # participantsはARRAY型なので、containsにリストを渡す必要があります
        sites = Site.query.filter(
            (Site.registered_user_id == current_user.id) | (Site.participants.contains([current_user.id]))
        ).all()
        site_addresses = [site.location for site in sites]
        current_app.logger.debug(f"Fetched sites for user {current_user.id}: {site_addresses}")
        return jsonify({'sites': site_addresses}), 200
    except SQLAlchemyError as e:
        current_app.logger.error(f"Database error fetching user sites: {e}")
        return jsonify({'success': False, 'error': 'データベースエラーが発生しました。'}), 500
    except Exception as e:
        current_app.logger.error(f"Unexpected error fetching user sites: {e}")
        return jsonify({'success': False, 'error': '予期せぬエラーが発生しました。'}), 500