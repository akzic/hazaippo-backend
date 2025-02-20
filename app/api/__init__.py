from flask import Blueprint
from flask_restful import Api
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from app import limiter  # `app/__init__.py` で定義する `limiter` をインポート
from app.api.resources import UserListResource, GenerateAPIKeyResource

api_bp = Blueprint('api', __name__)
api = Api(api_bp)

# APIエンドポイントの登録
api.add_resource(UserListResource, '/users')
api.add_resource(GenerateAPIKeyResource, '/generate-key')
