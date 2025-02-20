# app/api/api_materials.py

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import User, Material, WantedMaterial, Site
from app import db
from app.api.schemas import (
    CreateMaterialSchema,
    EditMaterialSchema,
    CreateWantedMaterialSchema,
    EditWantedMaterialSchema
)
from marshmallow import ValidationError
from werkzeug.utils import secure_filename
import os
import logging
from datetime import datetime
import pytz

api_materials = Blueprint('api_materials', __name__)
logger = logging.getLogger(__name__)
JST = pytz.timezone('Asia/Tokyo')

def success_response(data, message="", status=200):
    return jsonify({
        'success': True,
        'message': message,
        'data': data
    }), status

def error_response(message, status=400):
    return jsonify({
        'success': False,
        'message': message
    }), status

@api_materials.route('/register_material', methods=['POST'])
@jwt_required()
def register_material():
    try:
        data = request.form.to_dict()
        schema = CreateMaterialSchema()
        validated_data = schema.load(data)
        
        # 画像の保存処理
        image_file = None
        if 'image' in request.files and request.files['image']:
            image = request.files['image']
            if image.filename != '':
                image_filename = secure_filename(image.filename)
                image_path = os.path.join(current_app.root_path, 'static/uploads', image_filename)
                image.save(image_path)
                image_file = image_filename
                logger.debug(f"Image saved at {image_path}")
        
        user_id = get_jwt_identity()
        current_user = User.query.get(user_id)
        if not current_user:
            return error_response("ユーザーが見つかりません。", 404)
        
        # 受け渡し場所の設定
        business_structure = current_user.business_structure
        if business_structure == 0:
            location = validated_data.get('location', '').strip()
        else:
            location = validated_data.get('location', '').strip()
        
        # company_name のバリデーション（法人の場合）
        if business_structure == 0:
            if not current_user.company_name.strip():
                return error_response("会社名が必要です。", 400)
        
        # Materialオブジェクトの作成
        new_material = Material(
            user_id=current_user.id,
            type=validated_data['type'],
            size_1=validated_data['size_1'],
            size_2=validated_data['size_2'],
            size_3=validated_data['size_3'],
            location=location,
            quantity=validated_data['quantity'],
            deadline=validated_data['deadline'],
            exclude_weekends=validated_data['exclude_weekends'],
            image=image_file,
            note=validated_data.get('note'),
            wood_type=validated_data.get('wood_type') if validated_data['type'] == "木材" else None,
            board_material_type=validated_data.get('board_material_type') if validated_data['type'] == "ボード材" else None,
            panel_type=validated_data.get('panel_type') if validated_data['type'] == "パネル材" else None
        )
        logger.debug(f"New Material object created: {new_material}")
        
        # 受け渡し場所がSiteテーブルに存在する場合は site_id を設定
        if location:
            if business_structure == 0:
                site = Site.query.filter(Site.location.ilike(location)).first()
            else:
                site = Site.query.filter(
                    Site.location.ilike(location),
                    Site.registered_company.ilike(current_user.company_name)
                ).first()
            
            if site:
                new_material.site_id = site.id
                logger.debug(f"Site found: {site}")
            else:
                new_material.site_id = None
                logger.warning(f"Site not found for location '{location}'. site_id set to None.")
        
        db.session.add(new_material)
        db.session.commit()
        logger.debug(f"Material saved with ID {new_material.id}")
        
        # メール送信処理はここでは省略（非同期タスクとして実装することを推奨）
        
        return success_response({'material': new_material.to_dict()}, "端材が正常に登録されました。")
    
    except ValidationError as ve:
        logger.error(f"Validation error: {ve.messages}")
        return error_response(ve.messages, 400)
    except Exception as e:
        logger.exception(f"Error in register_material: {e}")
        return error_response("端材の登録中にエラーが発生しました。", 500)

@api_materials.route('/register_wanted_material', methods=['POST'])
@jwt_required()
def register_wanted_material():
    try:
        data = request.get_json()
        schema = CreateWantedMaterialSchema()
        validated_data = schema.load(data)
        
        user_id = get_jwt_identity()
        current_user = User.query.get(user_id)
        if not current_user:
            return error_response("ユーザーが見つかりません。", 404)
        
        # WantedMaterialオブジェクトの作成
        new_wanted_material = WantedMaterial(
            user_id=current_user.id,
            type=validated_data['type'],
            size_1=validated_data['size_1'],
            size_2=validated_data['size_2'],
            size_3=validated_data['size_3'],
            location=validated_data.get('location', '').strip(),
            quantity=validated_data['quantity'],
            deadline=validated_data['deadline'],
            exclude_weekends=validated_data['exclude_weekends'],
            note=validated_data.get('note'),
            wood_type=validated_data.get('wood_type') if validated_data['type'] == "木材" else None,
            board_material_type=validated_data.get('board_material_type') if validated_data['type'] == "ボード材" else None,
            panel_type=validated_data.get('panel_type') if validated_data['type'] == "パネル材" else None
        )
        logger.debug(f"New WantedMaterial object created: {new_wanted_material}")
        
        db.session.add(new_wanted_material)
        db.session.commit()
        logger.debug(f"WantedMaterial saved with ID {new_wanted_material.id}")
        
        # メール送信処理はここでは省略（非同期タスクとして実装することを推奨）
        
        return success_response({'wanted_material': new_wanted_material.to_dict()}, "希望材料が登録されました。")
    
    except ValidationError as ve:
        logger.error(f"Validation error: {ve.messages}")
        return error_response(ve.messages, 400)
    except Exception as e:
        logger.exception(f"Error in register_wanted_material: {e}")
        return error_response("希望材料の登録中にエラーが発生しました。", 500)

@api_materials.route('/edit_material/<int:material_id>', methods=['PUT'])
@jwt_required()
def edit_material(material_id):
    try:
        material = Material.query.get_or_404(material_id)
        user_id = get_jwt_identity()
        current_user = User.query.get(user_id)
        
        if current_user.id != material.user_id:
            return error_response("編集する権限がありません。", 403)
        
        data = request.get_json()
        schema = EditMaterialSchema()
        validated_data = schema.load(data)
        
        # データの更新
        material.type = validated_data['type']
        material.size_1 = validated_data['size_1']
        material.size_2 = validated_data['size_2']
        material.size_3 = validated_data['size_3']
        material.quantity = validated_data['quantity']
        material.exclude_weekends = validated_data['exclude_weekends']
        material.note = validated_data.get('note')
        material.location = validated_data.get('location', '').strip()
        
        # 材種フィールドの更新
        if validated_data['type'] == "木材":
            material.wood_type = validated_data.get('wood_type') or None
            material.board_material_type = None
            material.panel_type = None
        elif validated_data['type'] == "ボード材":
            material.board_material_type = validated_data.get('board_material_type') or None
            material.wood_type = None
            material.panel_type = None
        elif validated_data['type'] == "パネル材":
            material.panel_type = validated_data.get('panel_type') or None
            material.wood_type = None
            material.board_material_type = None
        else:
            material.wood_type = None
            material.board_material_type = None
            material.panel_type = None
        
        # 受け渡し場所がSiteテーブルに存在する場合は site_id を設定
        location = material.location
        if location:
            if current_user.business_structure == 0:
                site = Site.query.filter(Site.location.ilike(location)).first()
            else:
                site = Site.query.filter(
                    Site.location.ilike(location),
                    Site.registered_company.ilike(current_user.company_name)
                ).first()
            
            if site:
                material.site_id = site.id
                logger.debug(f"Site found: {site}")
            else:
                material.site_id = None
                logger.warning(f"Site not found for location '{location}'. site_id set to None.")
        
        db.session.commit()
        logger.debug(f"Material ID {material.id} updated successfully.")
        
        return success_response({'material': material.to_dict()}, "材料情報が更新されました！")
    
    except ValidationError as ve:
        logger.error(f"Validation error: {ve.messages}")
        return error_response(ve.messages, 400)
    except Exception as e:
        logger.exception(f"Error in edit_material: {e}")
        return error_response("材料情報の更新中にエラーが発生しました。", 500)

@api_materials.route('/edit_wanted_material/<int:wanted_material_id>', methods=['PUT'])
@jwt_required()
def edit_wanted_material(wanted_material_id):
    try:
        wanted_material = WantedMaterial.query.get_or_404(wanted_material_id)
        user_id = get_jwt_identity()
        current_user = User.query.get(user_id)
        
        if current_user.id != wanted_material.user_id:
            return error_response("編集する権限がありません。", 403)
        
        data = request.get_json()
        schema = EditWantedMaterialSchema()
        validated_data = schema.load(data)
        
        # データの更新
        wanted_material.type = validated_data['type']
        wanted_material.size_1 = validated_data['size_1']
        wanted_material.size_2 = validated_data['size_2']
        wanted_material.size_3 = validated_data['size_3']
        wanted_material.quantity = validated_data['quantity']
        wanted_material.exclude_weekends = validated_data['exclude_weekends']
        wanted_material.note = validated_data.get('note')
        wanted_material.location = validated_data.get('location', '').strip()
        
        # 材種フィールドの更新
        if validated_data['type'] == "木材":
            wanted_material.wood_type = validated_data.get('wood_type') or None
            wanted_material.board_material_type = None
            wanted_material.panel_type = None
        elif validated_data['type'] == "ボード材":
            wanted_material.board_material_type = validated_data.get('board_material_type') or None
            wanted_material.wood_type = None
            wanted_material.panel_type = None
        elif validated_data['type'] == "パネル材":
            wanted_material.panel_type = validated_data.get('panel_type') or None
            wanted_material.wood_type = None
            wanted_material.board_material_type = None
        else:
            wanted_material.wood_type = None
            wanted_material.board_material_type = None
            wanted_material.panel_type = None
        
        db.session.commit()
        logger.debug(f"WantedMaterial ID {wanted_material.id} updated successfully.")
        
        return success_response({'wanted_material': wanted_material.to_dict()}, "希望材料情報が更新されました！")
    
    except ValidationError as ve:
        logger.error(f"Validation error: {ve.messages}")
        return error_response(ve.messages, 400)
    except Exception as e:
        logger.exception(f"Error in edit_wanted_material: {e}")
        return error_response("希望材料情報の更新中にエラーが発生しました。", 500)

@api_materials.route('/delete_material/<int:material_id>', methods=['DELETE'])
@jwt_required()
def delete_material(material_id):
    try:
        material = Material.query.get_or_404(material_id)
        user_id = get_jwt_identity()
        current_user = User.query.get(user_id)
        
        if current_user.id != material.user_id:
            return error_response("削除する権限がありません。", 403)
        
        db.session.delete(material)
        db.session.commit()
        logger.debug(f"Material ID {material.id} deleted successfully.")
        
        return success_response({'message': '材料が削除されました。'}, "材料が削除されました。", 200)
    
    except Exception as e:
        logger.exception(f"Error in delete_material: {e}")
        return error_response("材料の削除中にエラーが発生しました。", 500)

@api_materials.route('/delete_wanted_material/<int:wanted_material_id>', methods=['DELETE'])
@jwt_required()
def delete_wanted_material(wanted_material_id):
    try:
        wanted_material = WantedMaterial.query.get_or_404(wanted_material_id)
        user_id = get_jwt_identity()
        current_user = User.query.get(user_id)
        
        if current_user.id != wanted_material.user_id:
            return error_response("削除する権限がありません。", 403)
        
        db.session.delete(wanted_material)
        db.session.commit()
        logger.debug(f"WantedMaterial ID {wanted_material.id} deleted successfully.")
        
        return success_response({'message': '希望材料が削除されました。'}, "希望材料が削除されました。", 200)
    
    except Exception as e:
        logger.exception(f"Error in delete_wanted_material: {e}")
        return error_response("希望材料の削除中にエラーが発生しました。", 500)

@api_materials.route('/material_detail/<int:material_id>', methods=['GET'])
@jwt_required()
def material_detail(material_id):
    try:
        material = Material.query.get_or_404(material_id)
        user_id = get_jwt_identity()
        current_user = User.query.get(user_id)
        
        if current_user.id != material.user_id and current_user.id not in [req.requested_user_id for req in material.requests]:
            return error_response("詳細を閲覧する権限がありません。", 403)
        
        return success_response({'material': material.to_dict()}, "材料詳細を取得しました。")
    
    except Exception as e:
        logger.exception(f"Error in material_detail: {e}")
        return error_response("材料詳細の取得中にエラーが発生しました。", 500)

@api_materials.route('/wanted_material_detail/<int:wanted_material_id>', methods=['GET'])
@jwt_required()
def wanted_material_detail(wanted_material_id):
    try:
        wanted_material = WantedMaterial.query.get_or_404(wanted_material_id)
        user_id = get_jwt_identity()
        current_user = User.query.get(user_id)
        
        if current_user.id != wanted_material.user_id and current_user.id not in [req.requested_user_id for req in wanted_material.requests]:
            return error_response("詳細を閲覧する権限がありません。", 403)
        
        return success_response({'wanted_material': wanted_material.to_dict()}, "希望材料詳細を取得しました。")
    
    except Exception as e:
        logger.exception(f"Error in wanted_material_detail: {e}")
        return error_response("希望材料詳細の取得中にエラーが発生しました。", 500)
