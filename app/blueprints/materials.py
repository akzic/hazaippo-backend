# app/blueprints/materials.py

from flask import Blueprint, render_template, url_for, flash, redirect, request, jsonify, current_app
from app import db
from app.forms import MaterialForm, WantedMaterialForm, DeleteHistoryForm, BulkMaterialForm
from app.models import Material, WantedMaterial, User, Site, Request
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from datetime import datetime
from app.blueprints.utils import log_user_activity
from app.blueprints.email_notifications import send_material_registration_email, send_wanted_material_registration_email
import pytz
import os
from wtforms.validators import ValidationError
import logging
import re  # 住所解析に必要
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import SQLAlchemyError
from uuid import uuid4

# 正しいインポートパスに修正
from app.image_processing import process_image_ai

# Blueprintの定義
materials_bp = Blueprint('materials', __name__)

# タイムゾーンの設定
JST = pytz.timezone('Asia/Tokyo')

# ロガーの設定
logger = logging.getLogger(__name__)

# アップロード可能なファイル拡張子の設定
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'HEIC'}

def allowed_file(filename):
    """許可された拡張子のファイルかどうかを判定する関数"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def parse_japanese_address(location):
    """日本の住所を郵便番号と国名を除去し、都道府県、市区町村、住所に分割する関数"""
    try:
        logger.debug(f"元のlocation: {location}")
        # 住所から国名を除去 (例: 日本、または日本,)
        location = re.sub(r'^日本[、,]\s*', '', location)
        logger.debug(f"国名除去後: {location}")
        
        # 住所から郵便番号を除去 (例: 〒123-4567)
        location = re.sub(r'〒\d{3}-\d{4}\s*', '', location)
        logger.debug(f"郵便番号除去後: {location}")

        # 都道府県のリスト
        prefectures = [
            '北海道', '青森県', '岩手県', '宮城県', '秋田県', '山形県', '福島県',
            '茨城県', '栃木県', '群馬県', '埼玉県', '千葉県', '東京都', '神奈川県',
            '新潟県', '富山県', '石川県', '福井県', '山梨県', '長野県', '岐阜県',
            '静岡県', '愛知県', '三重県', '滋賀県', '京都府', '大阪府', '兵庫県',
            '奈良県', '和歌山県', '鳥取県', '島根県', '岡山県', '広島県', '山口県',
            '徳島県', '香川県', '愛媛県', '高知県',
            '福岡県', '佐賀県', '長崎県', '熊本県', '大分県', '宮崎県', '鹿児島県',
            '沖縄県'
        ]

        # 都道府県を抽出
        prefecture = None
        for pref in prefectures:
            if location.startswith(pref):
                prefecture = pref
                break

        if not prefecture:
            logger.warning("都道府県が見つかりませんでした。")
            return None

        logger.debug(f"抽出された都道府県: {prefecture}")

        # 都道府県を除いた部分を解析
        remaining = location[len(prefecture):].strip()
        logger.debug(f"都道府県を除いた残り: {remaining}")

        # 市区町村を抽出（市、区、町、村で終わる）
        city_match = re.match(r'^([^市区町村]*[市区町村]+)', remaining)
        city = None
        address = None

        if city_match:
            city = city_match.group(1)
            address = remaining[len(city):].strip()
            logger.debug(f"抽出された市区町村: {city}")
            logger.debug(f"抽出された住所: {address}")
        else:
            # 市区町村が見つからない場合
            city = ''
            address = remaining
            logger.warning("市区町村が見つかりませんでした。")

        return {
            'prefecture': prefecture,
            'city': city,
            'address': address
        }
    except Exception as e:
        logger.error(f"住所のパース中にエラーが発生しました: {e}")
        return None

@materials_bp.route('/register_material', methods=['GET', 'POST'])
@login_required
def register_material():
    form = MaterialForm()
    if form.validate_on_submit():
        try:
            current_app.logger.debug("フォームの送信が検出されました。")

            # 画像の保存処理
            image_file = None
            if form.image.data:
                if allowed_file(form.image.data.filename):
                    # ユニークなファイル名を生成
                    original_filename = secure_filename(form.image.data.filename)
                    unique_id = uuid4().hex
                    name, ext = os.path.splitext(original_filename)
                    unique_filename = f"{name}_{unique_id}{ext}"
                    upload_path = os.path.join(current_app.root_path, 'static/uploads', unique_filename)

                    # ファイルを保存
                    form.image.data.save(upload_path)
                    image_file = unique_filename
                    current_app.logger.debug(f"画像が保存されました: {upload_path}")
                else:
                    flash('許可されていないファイル形式です。', 'error')
                    current_app.logger.debug(f"許可されていないファイル形式のファイルがアップロードされました: {form.image.data.filename}")
                    return render_template('register_material.html', form=form, business_structure=current_user.business_structure)

            # AIによる画像処理
            material_type_ai = "その他"
            ai_location = None  # AIからのlocationデータを保持
            if image_file:
                temp_path = os.path.join(current_app.root_path, 'static/uploads', image_file)
                ai_result = process_image_ai(temp_path)
                if ai_result['status'] == 'success':
                    material_type_ai = ai_result['material_type']
                    ai_location = ai_result.get('location')  # AIからのlocationデータが含まれている場合
                    current_app.logger.debug(f"AIによる材質判定結果: {material_type_ai}")
                    current_app.logger.debug(f"AIによる位置情報: {ai_location}")
                else:
                    flash('AIによる画像解析に失敗しました。', 'warning')
                    current_app.logger.warning(f"AI解析失敗: {ai_result['message']}")

            # business_structure を current_user から取得
            business_structure = current_user.business_structure
            current_app.logger.debug(f"User business_structure: {business_structure}")

            # 位置情報の設定
            if ai_location:
                # AIからのlocationを優先
                location = ai_location.strip()
                current_app.logger.debug(f"AIから提供された位置情報を使用します: '{location}'")
                # 位置情報を解析して都道府県、市区町村、住所に分割
                parsed_location = parse_japanese_address(location)
                if parsed_location:
                    m_prefecture = parsed_location['prefecture']
                    m_city = parsed_location['city']
                    m_address = parsed_location['address']
                    current_app.logger.debug(f"Parsed Location - Prefecture: {m_prefecture}, City: {m_city}, Address: {m_address}")
                else:
                    # 解析に失敗した場合は空にする
                    m_prefecture = ""
                    m_city = ""
                    m_address = ""
                    current_app.logger.warning("AIによる位置情報の解析に失敗しました。")
            else:
                # フォームからの入力を使用
                m_prefecture = form.m_prefecture.data.strip()
                m_city = form.m_city.data.strip()
                m_address = form.m_address.data.strip()
                location = f"{m_prefecture} {m_city} {m_address}"
                current_app.logger.debug(f"連結された位置情報: '{location}'")

            # company_name のバリデーション（business_structureが0または1の場合）
            if business_structure in [0, 1]:
                if not current_user.company_name.strip():
                    flash('会社名が必要です。', 'error')
                    current_app.logger.debug("business_structureが0または1なのに、company_nameが空です。")
                    raise ValidationError('会社名が必要です。')

            # Materialオブジェクトの作成
            new_material = Material(
                user_id=current_user.id,
                type=material_type_ai if image_file else form.material_type.data,  # AIによる判定を優先
                size_1=form.material_size_1.data or 0.0,  # デフォルト値を設定
                size_2=form.material_size_2.data or 0.0,  # デフォルト値を設定
                size_3=form.material_size_3.data or 0.0,  # デフォルト値を設定
                location=location,  # AIが提供する場合はそれを、そうでない場合はフォームからの連結値を設定
                m_prefecture=m_prefecture,  # ここでm_prefectureを設定
                m_city=m_city,              # ここでm_cityを設定
                m_address=m_address,        # ここでm_addressを設定
                quantity=form.quantity.data,
                deadline=form.deadline.data,
                exclude_weekends=form.exclude_weekends.data,
                image=image_file,
                note=form.note.data,
                # 新しいカラムの設定をオプションに対応
                wood_type=form.wood_type.data if (image_file and material_type_ai == "木材") else (form.wood_type.data if form.material_type.data == "木材" else None),
                board_material_type=form.board_material_type.data if (image_file and material_type_ai == "ボード材") else (form.board_material_type.data if form.material_type.data == "ボード材" else None),
                panel_type=form.panel_type.data if (image_file and material_type_ai == "パネル材") else (form.panel_type.data if form.material_type.data == "パネル材" else None)
            )
            current_app.logger.debug(f"New Material object created: {new_material}")

            # 受け渡し場所がSiteテーブルに存在する場合は site_id を設定
            if location:
                site = Site.query.filter(
                    Site.site_prefecture.ilike(m_prefecture),
                    Site.site_city.ilike(m_city),
                    Site.site_address.ilike(m_address)
                ).first()

                if site:
                    new_material.site_id = site.id
                    current_app.logger.debug(f"Site found for location '{location}'. Setting site_id to {site.id}")
                else:
                    new_material.site_id = None
                    #flash('指定された受け渡し場所がSiteテーブルに存在しません。site_idは設定されません。', 'warning')
                    current_app.logger.debug(f"Site not found for location '{location}'. site_id is set to None.")
            else:
                new_material.site_id = None
                current_app.logger.debug("location が空です。site_idは設定されません。")

            db.session.add(new_material)
            db.session.commit()
            current_app.logger.debug(f"Material saved to database with id {new_material.id} and site_id {new_material.site_id}")

            # メール送信処理の追加
            send_material_registration_email(current_user, new_material)
            current_app.logger.debug("メール送信処理が完了しました。")

            flash('端材が正常に登録されました。', 'success')
            return redirect(url_for('materials.register_material'))  # 修正ポイント

        except ValidationError as ve:
            # バリデーションエラーの場合はフォームに戻す
            flash(str(ve), 'error')
            current_app.logger.error(f"Validation error during material registration: {ve}")
            return render_template('register_material.html', form=form, business_structure=business_structure)

        except SQLAlchemyError as sae:
            db.session.rollback()
            current_app.logger.error(f"Database error during material registration: {sae}")
            flash('データベースエラーが発生しました。再度お試しください。', 'error')
            return redirect(url_for('materials.register_material'))

        except Exception as e:
            current_app.logger.error(f"Error during material registration: {e}")
            flash(f'端材の登録中にエラーが発生しました: {str(e)}', 'error')
            return redirect(url_for('materials.register_material'))
    else:
        # GETリクエスト時は単にフォームを表示
        return render_template('register_material.html', form=form, business_structure=current_user.business_structure)

@materials_bp.route('/get_cities/<prefecture>', methods=['GET'])
@login_required
def get_cities(prefecture):
    """
    選択された都道府県に基づいて、ユーザーが関連するSiteから市区町村を取得するAPIエンドポイント
    """
    try:
        # ユーザーが関連するSiteを取得
        user_sites = Site.query.filter(
            (Site.registered_user_id == current_user.id) | 
            Site.participants.any(current_user.id)  # 修正箇所
        ).filter(Site.site_prefecture.ilike(prefecture)).all()

        # 重複を避けるためにセットを使用
        cities = set()
        for site in user_sites:
            cities.add(site.site_city)

        cities = sorted(list(cities))

        logger.debug(f"Fetched cities for prefecture '{prefecture}': {cities}")  # デバッグ用

        return jsonify({'cities': cities}), 200
    except Exception as e:
        logger.error(f"市区町村の取得中にエラーが発生しました: {e}")
        return jsonify({'error': '市区町村の取得中にエラーが発生しました。'}), 500
    
@materials_bp.route('/get_addresses/<prefecture>/<city>', methods=['GET'])
@login_required
def get_addresses(prefecture, city):
    """
    選択された都道府県と市区町村に基づいて、ユーザーが関連するSiteから住所を取得するAPIエンドポイント
    """
    try:
        # ユーザーが関連するSiteを取得
        user_sites = Site.query.filter(
            (Site.registered_user_id == current_user.id) | 
            Site.participants.any(current_user.id)  # 修正箇所
        ).filter(Site.site_prefecture.ilike(prefecture), Site.site_city.ilike(city)).all()

        # 重複を避けるためにセットを使用
        addresses = set()
        for site in user_sites:
            addresses.add(site.site_address)

        addresses = sorted(list(addresses))

        logger.debug(f"Fetched addresses for prefecture '{prefecture}' and city '{city}': {addresses}")  # デバッグ用

        return jsonify({'addresses': addresses}), 200
    except Exception as e:
        logger.error(f"住所の取得中にエラーが発生しました: {e}")
        return jsonify({'error': '住所の取得中にエラーが発生しました。'}), 500


@materials_bp.route('/register_wanted', methods=['GET', 'POST'])
@login_required
def register_wanted():
    form = WantedMaterialForm()
    if form.validate_on_submit():
        try:
            logger.debug("フォームが送信されました。データを処理中...")

            # フォームデータの取得
            material_type = form.material_type.data
            size_1 = form.material_size_1.data or 0.0
            size_2 = form.material_size_2.data or 0.0
            size_3 = form.material_size_3.data or 0.0
            location = form.location.data.strip() if form.location.data else ""
            quantity = form.quantity.data
            deadline = form.deadline.data
            exclude_weekends = form.exclude_weekends.data
            note = form.note.data
            wood_type = form.wood_type.data if material_type == "木材" else None
            board_material_type = form.board_material_type.data if material_type == "ボード材" else None
            panel_type = form.panel_type.data if material_type == "パネル材" else None

            logger.debug(f"取得したフォームデータ: type={material_type}, size_1={size_1}, size_2={size_2}, size_3={size_3}, location='{location}', quantity={quantity}, deadline={deadline}, exclude_weekends={exclude_weekends}, note='{note}', wood_type={wood_type}, board_material_type={board_material_type}, panel_type={panel_type}")

            # WantedMaterialオブジェクトの作成
            wanted_material = WantedMaterial(
                user_id=current_user.id,
                type=material_type,
                size_1=size_1,
                size_2=size_2,
                size_3=size_3,
                location=location,
                quantity=quantity,
                deadline=deadline,
                exclude_weekends=exclude_weekends,
                note=note,
                wood_type=wood_type,
                board_material_type=board_material_type,
                panel_type=panel_type
            )
            logger.debug("WantedMaterialオブジェクトを作成しました。")

            # データベースへの追加
            db.session.add(wanted_material)
            db.session.commit()
            logger.debug(f"WantedMaterialをデータベースに保存しました。ID: {wanted_material.id}")

            # ログアクティビティの記録
            log_user_activity(
                current_user.id, 
                '希望材料登録', 
                'ユーザーが希望材料を登録しました。', 
                request.remote_addr, 
                request.user_agent.string, 
                'N/A'
            )

            # メール送信
            email_sent = send_wanted_material_registration_email(current_user.email, wanted_material)
            if not email_sent:
                logger.error("メール送信に失敗しました。WantedMaterialを削除します。")
                db.session.delete(wanted_material)
                db.session.commit()
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({
                        'status': 'error',
                        'message': '希望材料の登録に失敗しました。もう一度やり直してください。'
                    }), 500
                flash('希望材料の登録に失敗しました。もう一度やり直してください。', 'danger')
                return redirect(url_for('materials.register_wanted'))

            logger.debug("メール送信に成功しました。ダッシュボードにリダイレクトします。")

            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'status': 'success',
                    'message': '希望材料が登録されました！',
                    'redirect_url': url_for('dashboard.dashboard_home')
                }), 200

            flash('希望材料が登録されました！', 'success')
            return redirect(url_for('dashboard.dashboard_home'))

        except ValidationError as ve:
            # バリデーションエラーの場合はフォームに戻す
            flash(str(ve), 'danger')
            logger.error(f"Validation error during wanted material registration: {ve}")
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'status': 'error',
                    'message': str(ve)
                }), 400
            return render_template('register_wanted.html', form=form)

        except Exception as e:
            current_app.logger.exception(f"希望材料の登録中にエラーが発生しました: {e}")
            flash('希望材料の登録中にエラーが発生しました。もう一度お試しください。', 'danger')
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'status': 'error',
                    'message': '希望材料の登録中にエラーが発生しました。'
                }), 500

    else:
        if request.method == 'POST':
            flash('入力内容に誤りがあります。', 'danger')
            logger.debug(f"フォームのバリデーションに失敗しました: {form.errors}")
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'status': 'error',
                    'errors': form.errors
                }), 400
    # GETリクエスト時またはバリデーション失敗時にフォームを表示
    return render_template('register_wanted.html', form=form)

@materials_bp.route("/detail/<int:material_id>")
@login_required
def detail(material_id):
    material = Material.query.get_or_404(material_id)
    user = User.query.get_or_404(material.user_id)  # user_id を使用

    # ユーザーのマッチング回数を取得 (materialsテーブル)
    matched_materials_count = Material.query.filter_by(user_id=user.id, matched=True).count()

    # 合計マッチ数を計算
    total_matched_count = matched_materials_count

    log_user_activity(
        current_user.id, 
        '材料詳細表示', 
        f'ユーザーが材料ID: {material_id} の詳細を表示しました。', 
        request.remote_addr, 
        request.user_agent.string, 
        'N/A'
    )

    return render_template(
        'detail.html', 
        material=material, 
        user=user, 
        total_matched_count=total_matched_count
    )

@materials_bp.route("/detail_wanted/<int:wanted_material_id>")
@login_required
def detail_wanted(wanted_material_id):
    wanted_material = WantedMaterial.query.get_or_404(wanted_material_id)
    user = User.query.get_or_404(wanted_material.user_id)  # user_id を使用

    # ユーザーのマッチング回数を取得 (wanted_materialsテーブル)
    matched_wanted_materials_count = WantedMaterial.query.filter_by(user_id=user.id, matched=True).count()

    # 合計マッチ数を計算
    total_matched_count = matched_wanted_materials_count

    log_user_activity(
        current_user.id, 
        '希望材料詳細表示', 
        f'ユーザーが希望材料ID: {wanted_material_id} の詳細を表示しました。', 
        request.remote_addr, 
        request.user_agent.string, 
        'N/A'
    )

    return render_template(
        'detail_wanted.html', 
        wanted_material=wanted_material, 
        user=user, 
        total_matched_count=total_matched_count
    )

@materials_bp.route('/material_list', methods=['GET'])
@login_required
def material_list():
    delete_form = DeleteHistoryForm()
    try:
        business_structure = current_user.business_structure
        logger.debug(f"Current user business_structure: {business_structure}")

        if business_structure in [0, 1]:
            # 同じ company_name, prefecture, city, address を持つユーザーが登録した端材を取得
            unmatched_materials = Material.query.options(joinedload('owner')).join(User, Material.user_id == User.id).filter(
                Material.matched == False,
                Material.completed == False,
                Material.deleted == False,
                User.company_name == current_user.company_name,
                User.prefecture == current_user.prefecture,
                User.city == current_user.city,
                User.address == current_user.address
            ).all()

            matched_uncompleted_materials = Material.query.options(joinedload('owner')).join(Request, Material.id == Request.material_id).join(User, Material.user_id == User.id).filter(
                Material.matched == True,
                Material.completed == False,
                Material.deleted == False,
                User.company_name == current_user.company_name,
                User.prefecture == current_user.prefecture,
                User.city == current_user.city,
                User.address == current_user.address
            ).all()

            completed_materials = Material.query.options(joinedload('owner')).join(User, Material.user_id == User.id).filter(
                Material.completed == True,
                Material.deleted == False,
                User.company_name == current_user.company_name,
                User.prefecture == current_user.prefecture,
                User.city == current_user.city,
                User.address == current_user.address
            ).all()
        elif business_structure == 2:
            # business_structure が2の場合、現在のユーザーが登録した端材のみを表示
            unmatched_materials = Material.query.options(joinedload('owner')).filter_by(
                user_id=current_user.id,
                matched=False,
                completed=False,
                deleted=False
            ).all()

            matched_uncompleted_materials = Material.query.options(joinedload('owner')).join(Request, Material.id == Request.material_id).filter(
                Material.matched == True,
                Material.completed == False,
                Material.deleted == False,
                Material.user_id == current_user.id
            ).all()

            completed_materials = Material.query.options(joinedload('owner')).filter_by(
                user_id=current_user.id,
                completed=True,
                deleted=False
            ).all()
        else:
            # その他の business_structure の場合、端材を表示しない
            unmatched_materials = []
            matched_uncompleted_materials = []
            completed_materials = []

        logger.debug(f"unmatched_materials count: {len(unmatched_materials)}")
        logger.debug(f"matched_uncompleted_materials count: {len(matched_uncompleted_materials)}")
        logger.debug(f"completed_materials count: {len(completed_materials)}")

        return render_template('material_list.html',
                               unmatched_materials=unmatched_materials,
                               matched_uncompleted_materials=matched_uncompleted_materials,
                               completed_materials=completed_materials,
                               delete_form=delete_form)
    except Exception as e:
        # エラーをログに記録
        current_app.logger.error(f"Error fetching material list: {e}")
        return render_template('error.html', message='端材一覧の取得中にエラーが発生しました。'), 500

@materials_bp.route('/edit_material_ajax/<int:material_id>', methods=['POST'])
@login_required
def edit_material_ajax(material_id):
    try:
        material = Material.query.get_or_404(material_id)
    
        # 所有者の確認
        business_structure = current_user.business_structure
        if business_structure in [0, 1]:
            owner = material.owner
            if (current_user.company_name != owner.company_name or
                current_user.prefecture != owner.prefecture or
                current_user.city != owner.city or
                current_user.address != owner.address):
                return jsonify({'status': 'error', 'message': '権限がありません。'}), 403
        elif business_structure == 2:
            if current_user.id != material.user_id:
                return jsonify({'status': 'error', 'message': '権限がありません。'}), 403
        else:
            return jsonify({'status': 'error', 'message': '権限がありません。'}), 403
    
        data = request.get_json()
    
        # 必要なフィールドを取得
        type = data.get('type', '').strip()
        category = data.get('category', '').strip()
        quantity = data.get('quantity', 0)
        size_1 = data.get('size_1', 0.0)
        size_2 = data.get('size_2', 0.0)
        size_3 = data.get('size_3', 0.0)
        m_prefecture = data.get('m_prefecture', '').strip()
        m_city = data.get('m_city', '').strip()
        m_address = data.get('m_address', '').strip()
        deadline_str = data.get('deadline', '').strip()
        note = data.get('note', '').strip()
    
        # 締切日のバリデーション
        try:
            deadline = datetime.strptime(deadline_str, '%Y-%m-%dT%H:%M')
            deadline = JST.localize(deadline)
            if deadline < datetime.now(JST):
                return jsonify({'status': 'error', 'message': '締切日は現在日時より前に設定できません。'}), 400
        except ValueError:
            return jsonify({'status': 'error', 'message': '無効な締切日です。'}), 400
    
        # 材種の設定
        if type == "木材":
            wood_type = category
            board_material_type = ""
            panel_type = ""
        elif type == "ボード材":
            wood_type = ""
            board_material_type = category
            panel_type = ""
        elif type == "パネル材":
            wood_type = ""
            board_material_type = ""
            panel_type = category
        else:
            wood_type = ""
            board_material_type = ""
            panel_type = ""
    
        # 場所の設定
        if m_prefecture and m_city and m_address:
            location = f"{m_prefecture}{m_city}{m_address}"
        else:
            location = ""
    
        # サイズの設定
        try:
            size_1 = float(size_1)
            size_2 = float(size_2)
            size_3 = float(size_3)
        except ValueError:
            return jsonify({'status': 'error', 'message': 'サイズは数値で入力してください。'}), 400
    
        # サイズが全て0.0の場合
        if size_1 == 0.0 and size_2 == 0.0 and size_3 == 0.0:
            size_display = "指定なし"
        else:
            size_display = f"{size_1} × {size_2} × {size_3}"
    
        # 更新
        material.type = type
        material.wood_type = wood_type
        material.board_material_type = board_material_type
        material.panel_type = panel_type
        material.quantity = quantity
        material.size_1 = size_1
        material.size_2 = size_2
        material.size_3 = size_3
        material.m_prefecture = m_prefecture
        material.m_city = m_city
        material.m_address = m_address
        material.location = location
        material.deadline = deadline
        material.note = note
    
        db.session.commit()
        return jsonify({'status': 'success', 'message': '端材が更新されました。', 'material': material.to_dict()}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error editing material: {e}")
        return jsonify({'status': 'error', 'message': '端材の更新に失敗しました。'}), 500

@materials_bp.route('/delete_material_ajax/<int:material_id>', methods=['POST'])
@login_required
def delete_material_ajax(material_id):
    try:
        material = Material.query.get_or_404(material_id)
    
        # 所有者の確認
        business_structure = current_user.business_structure
        if business_structure in [0, 1]:
            owner = material.owner
            if (current_user.company_name != owner.company_name or
                current_user.prefecture != owner.prefecture or
                current_user.city != owner.city or
                current_user.address != owner.address):
                return jsonify({'status': 'error', 'message': '権限がありません。'}), 403
        elif business_structure == 2:
            if current_user.id != material.user_id:
                return jsonify({'status': 'error', 'message': '権限がありません。'}), 403
        else:
            return jsonify({'status': 'error', 'message': '権限がありません。'}), 403
    
        db.session.delete(material)
        db.session.commit()
        return jsonify({'status': 'success', 'message': '端材が削除されました。'}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting material: {e}")
        return jsonify({'status': 'error', 'message': '端材の削除に失敗しました。'}), 500

@materials_bp.route("/material_wanted_list", methods=['GET', 'POST'])
@login_required
def material_wanted_list():
    delete_form = DeleteHistoryForm()  # DeleteHistoryFormのインスタンスを作成

    try:
        # マッチしていない希望端材の取得
        unmatched_wanted_materials = WantedMaterial.query.filter(
            WantedMaterial.user_id == current_user.id,  # 現在のユーザーが所有者
            WantedMaterial.matched == False,
            WantedMaterial.deleted == False  # 削除済みでないもののみ
        ).all()

        # マッチしているが未完了の希望端材の取得
        matched_uncompleted_wanted_materials = db.session.query(WantedMaterial, Request).join(
            Request, Request.wanted_material_id == WantedMaterial.id
        ).filter(
            Request.requested_user_id == current_user.id,  # 現在のユーザーがリクエストを受け取った側
            WantedMaterial.matched == True,
            WantedMaterial.completed == False,
            WantedMaterial.deleted == False  # 削除済みでないもののみ
        ).all()

        # 完了済みの希望端材の取得
        completed_wanted_materials = WantedMaterial.query.filter(
            WantedMaterial.user_id == current_user.id,  # 現在のユーザーが所有者
            WantedMaterial.completed == True,
            WantedMaterial.deleted == False  # 削除済みでないもののみ
        ).all()

        # デバッグ用ログ
        current_app.logger.debug(f"unmatched_wanted_materials count: {len(unmatched_wanted_materials)}")
        current_app.logger.debug(f"matched_uncompleted_wanted_materials count: {len(matched_uncompleted_wanted_materials)}")
        current_app.logger.debug(f"completed_wanted_materials count: {len(completed_wanted_materials)}")

        log_user_activity(
            current_user.id, 
            '希望端材一覧表示', 
            'ユーザーが希望端材一覧を表示しました。', 
            request.remote_addr, 
            request.user_agent.string, 
            'N/A'
        )

        return render_template('material_wanted_list.html', 
                               unmatched_wanted_materials=unmatched_wanted_materials,
                               matched_uncompleted_wanted_materials=matched_uncompleted_wanted_materials,
                               completed_wanted_materials=completed_wanted_materials,
                               delete_form=delete_form)  # フォームをテンプレートに渡す
    except Exception as e:
        current_app.logger.error(f"Error fetching wanted material list: {e}")
        flash('希望端材一覧の取得中にエラーが発生しました。', 'danger')
        return redirect(url_for('dashboard.dashboard_home'))

@materials_bp.route("/edit_wanted_material_ajax/<int:wanted_material_id>", methods=['POST'])
@login_required
def edit_wanted_material_ajax(wanted_material_id):
    wanted_material = WantedMaterial.query.get_or_404(wanted_material_id)

    # 編集権限の確認
    if current_user.id != wanted_material.user_id:
        return jsonify({'status': 'error', 'message': '編集する権限がありません。'}), 403

    # JSONデータを取得
    data = request.get_json()

    if not data:
        return jsonify({'status': 'error', 'message': '無効なデータです。'}), 400

    try:
        # 必須フィールドのチェック（サイズフィールドを除外）
        required_fields = ['type', 'quantity', 'deadline']
        for field in required_fields:
            if field not in data or data[field] == '':
                return jsonify({'status': 'error', 'message': f'{field} は必須項目です。'}), 400

        # 「材種」が必要な場合のバリデーション
        material_type = data['type']
        category_input = data.get('category', '').strip()

        required_types = ["木材", "ボード材", "パネル材"]
        if material_type in required_types and not category_input:
            return jsonify({'status': 'error', 'message': '「材種」を選択してください。'}), 400

        # データの取得とバリデーション
        quantity = int(data['quantity'])
        size_1 = float(data['size_1']) if data.get('size_1') not in [None, ''] else 0.0
        size_2 = float(data['size_2']) if data.get('size_2') not in [None, ''] else 0.0
        size_3 = float(data['size_3']) if data.get('size_3') not in [None, ''] else 0.0
        deadline_str = data['deadline'].strip()
        note = data.get('note', '').strip()

        # 締切日のバリデーション
        try:
            deadline = datetime.strptime(deadline_str, '%Y-%m-%dT%H:%M')
            deadline = JST.localize(deadline)
            if deadline < datetime.now(JST):
                return jsonify({'status': 'error', 'message': '締切日は現在日時より前に設定できません。'}), 400
        except ValueError:
            return jsonify({'status': 'error', 'message': '無効な締切日です。'}), 400

        # 材種の設定
        if material_type == "木材":
            wood_type = category_input
            board_material_type = ""
            panel_type = ""
        elif material_type == "ボード材":
            wood_type = ""
            board_material_type = category_input
            panel_type = ""
        elif material_type == "パネル材":
            wood_type = ""
            board_material_type = ""
            panel_type = category_input
        else:
            # その他の場合は選択肢を無効にする
            wood_type = ""
            board_material_type = ""
            panel_type = ""

        # 更新
        wanted_material.type = material_type
        wanted_material.quantity = quantity
        wanted_material.size_1 = size_1
        wanted_material.size_2 = size_2
        wanted_material.size_3 = size_3
        wanted_material.deadline = deadline
        wanted_material.note = note
        wanted_material.wood_type = wood_type
        wanted_material.board_material_type = board_material_type
        wanted_material.panel_type = panel_type

        db.session.commit()

        # レスポンス用に締切日をISO 8601形式にフォーマット
        formatted_deadline = wanted_material.deadline.isoformat() if wanted_material.deadline else '未設定'

        return jsonify({
            'status': 'success',
            'message': '希望材料が更新されました。',
            'wanted_material': {
                'type': wanted_material.type,
                'quantity': wanted_material.quantity,
                'size_1': wanted_material.size_1,
                'size_2': wanted_material.size_2,
                'size_3': wanted_material.size_3,
                'deadline': formatted_deadline,
                'note': wanted_material.note or "",
                'wood_type': wanted_material.wood_type,
                'board_material_type': wanted_material.board_material_type,
                'panel_type': wanted_material.panel_type
            }
        }), 200

    except ValueError as ve:
        current_app.logger.error(f"Value error during wanted material update: {ve}")
        return jsonify({'status': 'error', 'message': '数値形式が正しくありません。'}), 400

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating wanted material: {e}")
        return jsonify({'status': 'error', 'message': '希望材料情報の更新中にエラーが発生しました。'}), 500
    
# AJAXで希望端材を削除するルート
@materials_bp.route("/delete_wanted_material_ajax/<int:wanted_material_id>", methods=['POST'])
@login_required
def delete_wanted_material_ajax(wanted_material_id):
    wanted_material = WantedMaterial.query.get_or_404(wanted_material_id)
    if current_user.id != wanted_material.user_id:
        return jsonify({'status': 'error', 'message': '削除する権限がありません。'}), 403
    try:
        db.session.delete(wanted_material)
        db.session.commit()
        return jsonify({'status': 'success', 'message': '希望端材が削除されました。'}), 200
    except Exception as e:
        logger.error(f"Error deleting wanted material: {e}")
        return jsonify({'status': 'error', 'message': '希望端材の削除に失敗しました。'}), 500

@materials_bp.route("/edit_material/<int:material_id>", methods=['GET', 'POST'])
@login_required
def edit_material(material_id):
    material = Material.query.get_or_404(material_id)
    business_structure = current_user.business_structure
    if business_structure == 2:
        if current_user.id != material.user_id:
            flash('編集する権限がありません。', 'danger')
            return redirect(url_for('materials.material_list'))
    else:
        owner = material.owner
        if (current_user.company_name != owner.company_name or
            current_user.prefecture != owner.prefecture or
            current_user.city != owner.city or
            current_user.address != owner.address):
            flash('編集する権限がありません。', 'danger')
            return redirect(url_for('materials.material_list'))

    form = MaterialForm()
    if form.validate_on_submit():
        try:
            # 受け渡し場所の設定
            if business_structure in [0, 1]:
                location = form.handover_location.data.strip() if form.handover_location.data else ''
                logger.debug(f"法人または特定のビジネス構造の場合のhandover_location: '{location}'")
            else:
                location = form.location.data.strip() if form.location.data else ''
                logger.debug(f"その他のビジネス構造の場合のlocation: '{location}'")

            material.type = form.material_type.data
            material.size_1 = form.material_size_1.data or 0.0  # デフォルト値を設定
            material.size_2 = form.material_size_2.data or 0.0  # デフォルト値を設定
            material.size_3 = form.material_size_3.data or 0.0  # デフォルト値を設定
            material.location = location  # 受け渡し場所を設定
            material.quantity = form.quantity.data
            # 締切日は修正不可
            material.exclude_weekends = form.exclude_weekends.data  # 新しいフィールドの更新
            material.note = form.note.data

            # 新しいカラムの更新をオプションに対応
            material.wood_type = form.wood_type.data if form.material_type.data == "木材" else None
            material.board_material_type = form.board_material_type.data if form.material_type.data == "ボード材" else None
            material.panel_type = form.panel_type.data if form.material_type.data == "パネル材" else None

            # 変更をコミット
            db.session.commit()
            flash('材料情報が更新されました！', 'success')
            log_user_activity(
                current_user.id, 
                '材料編集', 
                f'ユーザーが材料ID: {material_id} の情報を編集しました。', 
                request.remote_addr, 
                request.user_agent.string, 
                'N/A'
            )
            return redirect(url_for('materials.material_list'))
        except Exception as e:
            current_app.logger.error(f"Error updating material: {e}")
            flash('材料情報の更新中にエラーが発生しました。', 'danger')
    else:
        if request.method == 'POST':
            flash('入力内容に誤りがあります。', 'error')
            logger.debug(f"フォームのバリデーションに失敗しました: {form.errors}")
    # GETリクエスト時またはバリデーション失敗時にフォームを表示
    # フォームに既存のデータをセット
    form.material_type.data = material.type
    form.material_size_1.data = material.size_1
    form.material_size_2.data = material.size_2
    form.material_size_3.data = material.size_3
    form.location.data = material.location if business_structure not in [0,1] else ""
    form.handover_location.data = material.location if business_structure in [0,1] else ""
    form.quantity.data = material.quantity
    # 締切日は修正不可なので設定しない
    form.exclude_weekends.data = material.exclude_weekends  # 新しいフィールドの初期値設定
    form.note.data = material.note
    # 新しいカラムの初期値設定
    form.wood_type.data = material.wood_type
    form.board_material_type.data = material.board_material_type
    form.panel_type.data = material.panel_type

    return render_template('edit_material.html', form=form, material=material)

@materials_bp.route("/edit_wanted_material/<int:material_id>", methods=['GET', 'POST'])
@login_required
def edit_wanted_material(material_id):
    wanted_material = WantedMaterial.query.get_or_404(material_id)
    if current_user.id != wanted_material.user_id:
        flash('編集する権限がありません。', 'danger')
        return redirect(url_for('materials.material_wanted_list'))

    form = WantedMaterialForm()
    if form.validate_on_submit():
        try:
            wanted_material.type = form.material_type.data
            wanted_material.size_1 = form.material_size_1.data or 0.0  # デフォルト値を設定
            wanted_material.size_2 = form.material_size_2.data or 0.0  # デフォルト値を設定
            wanted_material.size_3 = form.material_size_3.data or 0.0  # デフォルト値を設定
            wanted_material.location = form.location.data if form.location.data else ""
            wanted_material.quantity = form.quantity.data
            # 締切日は修正不可
            wanted_material.exclude_weekends = form.exclude_weekends.data  # 新しいフィールドの更新
            wanted_material.note = form.note.data

            # 新しいカラムの更新
            wanted_material.wood_type = form.wood_type.data if form.material_type.data == "木材" else None
            wanted_material.board_material_type = form.board_material_type.data if form.material_type.data == "ボード材" else None
            wanted_material.panel_type = form.panel_type.data if form.material_type.data == "パネル材" else None

            # 変更をコミット
            db.session.commit()
            flash('希望材料情報が更新されました！', 'success')
            log_user_activity(
                current_user.id, 
                '希望材料編集', 
                f'ユーザーが希望材料ID: {material_id} の情報を編集しました。', 
                request.remote_addr, 
                request.user_agent.string, 
                'N/A'
            )
            return redirect(url_for('materials.material_wanted_list'))
        except Exception as e:
            current_app.logger.error(f"Error updating wanted material: {e}")
            flash('希望材料情報の更新中にエラーが発生しました。', 'danger')
    else:
        if request.method == 'POST':
            flash('入力内容に誤りがあります。', 'error')
            logger.debug(f"フォームのバリデーションに失敗しました: {form.errors}")
    # GETリクエスト時またはバリデーション失敗時にフォームを表示
    # フォームに既存のデータをセット
    form.material_type.data = wanted_material.type
    form.material_size_1.data = wanted_material.size_1
    form.material_size_2.data = wanted_material.size_2
    form.material_size_3.data = wanted_material.size_3
    form.location.data = wanted_material.location
    form.quantity.data = wanted_material.quantity
    # 締切日は修正不可なので設定しない
    form.exclude_weekends.data = wanted_material.exclude_weekends  # 新しいフィールドの初期値設定
    form.note.data = wanted_material.note
    # 新しいカラムの初期値設定
    form.wood_type.data = wanted_material.wood_type
    form.board_material_type.data = wanted_material.board_material_type
    form.panel_type.data = wanted_material.panel_type

    return render_template('edit_wanted_material.html', form=form, wanted_material=wanted_material)

@materials_bp.route("/delete_history_material/<int:material_id>", methods=['POST'])
@login_required
def delete_history_material(material_id):
    try:
        form = DeleteHistoryForm()
        if form.validate_on_submit():
            material = Material.query.get_or_404(material_id)
            # 権限の確認
            if current_user.id != material.user_id:
                return jsonify({'status': 'error', 'message': '履歴を削除する権限がありません。'}), 403
            # 履歴削除の処理
            material.deleted = True
            material.deleted_at = datetime.now(JST)
            db.session.commit()

            # アクティビティログの記録
            log_user_activity(
                current_user.id, 
                '履歴削除', 
                f'ユーザーが材料ID: {material_id} の履歴を削除しました。', 
                request.remote_addr, 
                request.user_agent.string, 
                'N/A'
            )

            return jsonify({'status': 'success', 'message': '履歴が削除されました。'}), 200
        else:
            return jsonify({'status': 'error', 'message': '無効なリクエストです。'}), 400
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting material history: {e}")
        return jsonify({'status': 'error', 'message': '履歴の削除に失敗しました。'}), 500

@materials_bp.route("/delete_history_wanted_material/<int:material_id>", methods=['POST'])
@login_required
def delete_history_wanted_material(material_id):
    form = DeleteHistoryForm()
    if form.validate_on_submit():
        wanted_material = WantedMaterial.query.get_or_404(material_id)
        if current_user.id != wanted_material.user_id:
            flash('履歴を削除する権限がありません。', 'danger')
            return redirect(url_for('materials.material_wanted_list'))
        try:
            wanted_material.deleted = True
            wanted_material.deleted_at = datetime.now(JST)
            db.session.commit()

            flash('履歴が削除されました。', 'success')
            log_user_activity(
                current_user.id, 
                '履歴削除', 
                f'ユーザーが希望材料ID: {material_id} の履歴を削除しました。', 
                request.remote_addr, 
                request.user_agent.string, 
                'N/A'
            )
        except Exception as e:
            current_app.logger.error(f"Error deleting wanted material history: {e}")
            flash('履歴の削除中にエラーが発生しました。', 'danger')
    else:
        flash('無効なリクエストです。', 'danger')
    return redirect(url_for('materials.material_wanted_list'))

def save_image(form_image):
    """画像を保存し、ファイル名を返す関数"""
    random_hex = os.urandom(8).hex()
    _, f_ext = os.path.splitext(form_image.filename)
    image_fn = random_hex + f_ext
    image_path = os.path.join(current_app.root_path, 'static/images/materials', image_fn)
    
    # 画像を保存
    form_image.save(image_path)
    
    return image_fn

# app/blueprints/materials.py

@materials_bp.route('/bulk_register_wanted', methods=['GET', 'POST'])
@login_required
def bulk_register_wanted():
    form = BulkMaterialForm()  # BulkMaterialFormはWantedMaterialFormを内包する形にするか、適宜定義してください
    if form.validate_on_submit():
        try:
            # 例: 各エントリーの処理
            for entry in form.materials.data:
                new_wanted = WantedMaterial(
                    user_id=current_user.id,
                    type=entry.get('material_type'),
                    size_1=entry.get('material_size_1') or 0.0,
                    size_2=entry.get('material_size_2') or 0.0,
                    size_3=entry.get('material_size_3') or 0.0,
                    # 住所は分割されているので個別に処理
                    location=f"{entry.get('m_prefecture','')} {entry.get('m_city','')} {entry.get('m_address','')}",
                    quantity=entry.get('quantity'),
                    deadline=entry.get('deadline'),
                    exclude_weekends=entry.get('exclude_weekends'),
                    note=entry.get('note'),
                    # サブタイプフィールドも必要に応じて設定
                    wood_type=entry.get('wood_type'),
                    board_material_type=entry.get('board_material_type'),
                    panel_type=entry.get('panel_type')
                )
                db.session.add(new_wanted)
            db.session.commit()
            flash('欲しい端材を一括で登録しました。', 'success')
            return redirect(url_for('materials.material_wanted_list'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Bulk wanted registration error: {e}")
            flash('一括登録中にエラーが発生しました。', 'danger')
    return render_template('bulk_register_material.html', form=form)
