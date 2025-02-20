# app/api/api_search.py

from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from app.models import Material, WantedMaterial, User
from app.blueprints.utils import log_user_activity
from datetime import datetime, timedelta
import pytz
import logging

api_search_bp = Blueprint('api_search', __name__, url_prefix='/api/search')
JST = pytz.timezone('Asia/Tokyo')

logger = logging.getLogger(__name__)

def validate_material_search_data(data):
    """
    材料検索の入力データをバリデーションします。
    """
    required_fields = ['material_type']
    for field in required_fields:
        if field not in data:
            raise ValueError(f"{field} が必要です。")
    
    # サイズはオプショナルだが、数値である必要がある
    for size_field in ['size_1', 'size_2', 'size_3']:
        if size_field in data and not isinstance(data[size_field], (int, float)):
            raise ValueError(f"{size_field} は数値でなければなりません。")
    
    # locationはオプショナルだが、文字列である必要がある
    if 'location' in data and not isinstance(data['location'], str):
        raise ValueError("location は文字列でなければなりません。")
    
    # cityはオプショナルだが、文字列である必要がある
    if 'city' in data and not isinstance(data['city'], str):
        raise ValueError("city は文字列でなければなりません。")

def validate_wanted_material_search_data(data):
    """
    希望材料検索の入力データをバリデーションします。
    """
    required_fields = ['material_type']
    for field in required_fields:
        if field not in data:
            raise ValueError(f"{field} が必要です。")
    
    # サイズはオプショナルだが、数値である必要がある
    for size_field in ['size_1', 'size_2', 'size_3']:
        if size_field in data and not isinstance(data[size_field], (int, float)):
            raise ValueError(f"{size_field} は数値でなければなりません。")
    
    # locationはオプショナルだが、文字列である必要がある
    if 'location' in data and not isinstance(data['location'], str):
        raise ValueError("location は文字列でなければなりません。")

@api_search_bp.route('/materials', methods=['POST'])
@login_required
def search_materials_api():
    """
    材料を検索するAPIエンドポイント。
    JSON形式で検索条件を受け取り、検索結果を返します。
    """
    if not request.is_json:
        return jsonify({'success': False, 'message': 'JSON形式のデータを送信してください。'}), 400
    
    data = request.get_json()
    
    try:
        validate_material_search_data(data)
    except ValueError as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    
    material_type = data.get('material_type')
    size_1 = data.get('size_1', 0.0)
    size_2 = data.get('size_2', 0.0)
    size_3 = data.get('size_3', 0.0)
    location = data.get('location', '').strip()
    city = data.get('city', '').strip()
    
    # 現在の日付を取得して1日引く
    current_date = (datetime.now(JST) - timedelta(days=1)).date()
    
    try:
        # ベースクエリを作成
        query = Material.query.join(User, Material.user_id == User.id).filter(
            Material.type == material_type,
            Material.matched == False,
            Material.deadline >= current_date  # 締め切り日が現在の日付以上
        )
        
        # サイズフィルタリング
        if any([size_1, size_2, size_3]):
            query = query.filter(
                (Material.size_1 >= size_1) |
                (Material.size_2 >= size_2) |
                (Material.size_3 >= size_3)
            )
        
        # `business_structure` が `0` の場合、同じ `company_name` のユーザーの端材を除外
        if current_user.business_structure == 0:
            query = query.filter(User.company_name != current_user.company_name)
        
        # 市区町村のフィルタリング
        if city:
            query = query.filter(Material.location.ilike(f"%{city}%"))
        
        # 県名でのフィルタリング
        if location:
            query = query.filter(User.prefecture == location)
        
        # クエリを実行して結果を取得
        results = query.all()
        
        logger.debug(f"材料検索結果数: {len(results)}")
        
        # 結果をシリアライズ
        materials_data = []
        for material in results:
            materials_data.append({
                'id': material.id,
                'type': material.type,
                'size_1': material.size_1,
                'size_2': material.size_2,
                'size_3': material.size_3,
                'location': material.location,
                'deadline': material.deadline.strftime('%Y-%m-%d'),
                'user': {
                    'id': material.user.id,
                    'email': material.user.email,
                    'company_name': material.user.company_name,
                    'prefecture': material.user.prefecture,
                    'city': material.user.city,
                    'address': material.user.address,
                    'business_structure': material.user.business_structure
                }
            })
        
        # アクティビティログの記録
        log_user_activity(
            current_user.id,
            '材料検索',
            'ユーザーが材料を検索しました。',
            request.remote_addr,
            request.user_agent.string,
            'N/A'
        )
        
        return jsonify({
            'success': True,
            'data': {
                'materials': materials_data
            }
        }), 200
    except Exception as e:
        current_app.logger.error(f"材料検索中にエラーが発生しました: {e}")
        return jsonify({'success': False, 'message': '材料検索中にエラーが発生しました。'}), 500

@api_search_bp.route('/wanted_materials', methods=['POST'])
@login_required
def search_wanted_materials_api():
    """
    希望材料を検索するAPIエンドポイント。
    JSON形式で検索条件を受け取り、検索結果を返します。
    """
    if not request.is_json:
        return jsonify({'success': False, 'message': 'JSON形式のデータを送信してください。'}), 400
    
    data = request.get_json()
    
    try:
        validate_wanted_material_search_data(data)
    except ValueError as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    
    material_type = data.get('material_type')
    size_1 = data.get('size_1', 0.0)
    size_2 = data.get('size_2', 0.0)
    size_3 = data.get('size_3', 0.0)
    location = data.get('location', '').strip()
    
    # 現在の日付を取得して1日引く
    current_date = (datetime.now(JST) - timedelta(days=1)).date()
    
    try:
        # ベースクエリを作成
        query = WantedMaterial.query.join(User, WantedMaterial.user_id == User.id).filter(
            WantedMaterial.type == material_type,
            WantedMaterial.matched == False,
            WantedMaterial.deadline >= current_date  # 締め切り日が現在の日付以上
        )
        
        # サイズフィルタリング
        if any([size_1, size_2, size_3]):
            query = query.filter(
                (WantedMaterial.size_1 >= size_1) &
                (WantedMaterial.size_2 >= size_2) &
                (WantedMaterial.size_3 >= size_3)
            )
        
        # `business_structure` が `0` の場合、同じ `company_name` のユーザーの希望端材を除外
        if current_user.business_structure == 0:
            query = query.filter(User.company_name != current_user.company_name)
        
        # 県名でのフィルタリング
        if location:
            query = query.filter(User.prefecture == location)
        
        # クエリを実行して結果を取得
        results = query.all()
        
        logger.debug(f"希望材料検索結果数: {len(results)}")
        
        # 結果をシリアライズ
        wanted_materials_data = []
        for wanted in results:
            wanted_materials_data.append({
                'id': wanted.id,
                'type': wanted.type,
                'size_1': wanted.size_1,
                'size_2': wanted.size_2,
                'size_3': wanted.size_3,
                'deadline': wanted.deadline.strftime('%Y-%m-%d'),
                'user': {
                    'id': wanted.user.id,
                    'email': wanted.user.email,
                    'company_name': wanted.user.company_name,
                    'prefecture': wanted.user.prefecture,
                    'city': wanted.user.city,
                    'address': wanted.user.address,
                    'business_structure': wanted.user.business_structure
                }
            })
        
        # アクティビティログの記録
        log_user_activity(
            current_user.id,
            '希望材料検索',
            'ユーザーが希望材料を検索しました。',
            request.remote_addr,
            request.user_agent.string,
            'N/A'
        )
        
        return jsonify({
            'success': True,
            'data': {
                'wanted_materials': wanted_materials_data
            }
        }), 200
    except Exception as e:
        current_app.logger.error(f"希望材料検索中にエラーが発生しました: {e}")
        return jsonify({'success': False, 'message': '希望材料検索中にエラーが発生しました。'}), 500
