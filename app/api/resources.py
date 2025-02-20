from flask_restful import Resource
from flask import request, jsonify
from app.models import User, APIKey
from app import db
from app.api.schemas import UserSchema, APIKeySchema
from app.api.decorators import require_api_key, require_admin
from app import limiter

user_schema = UserSchema()
users_schema = UserSchema(many=True)
api_key_schema = APIKeySchema()
api_keys_schema = APIKeySchema(many=True)

class UserListResource(Resource):
    decorators = [limiter.limit("10 per minute"), require_api_key]

    def get(self):
        users = User.query.all()
        return users_schema.dump(users), 200

    def post(self):
        json_data = request.get_json()
        if not json_data:
            return {'message': 'No input data provided'}, 400
        errors = user_schema.validate(json_data)
        if errors:
            return errors, 422
        new_user = User(
            username=json_data['username'],
            is_admin=json_data.get('is_admin', False)
        )
        db.session.add(new_user)
        db.session.commit()
        return user_schema.dump(new_user), 201

class GenerateAPIKeyResource(Resource):
    decorators = [limiter.limit("5 per minute"), require_api_key, require_admin]

    def post(self):
        json_data = request.get_json()
        owner = json_data.get('owner')
        if not owner:
            return {'message': 'Owner is required'}, 400
        new_key = APIKey(owner=owner)
        db.session.add(new_key)
        db.session.commit()
        return {'api_key': new_key.key}, 201
