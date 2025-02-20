from functools import wraps
from flask import request, jsonify
from app.models import APIKey, User

def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get('X-API-KEY')
        if not key:
            return jsonify({'message': 'API key is missing'}), 401
        api_key = APIKey.query.filter_by(key=key, revoked=False).first()
        if not api_key:
            return jsonify({'message': 'Invalid or revoked API key'}), 401
        return f(*args, **kwargs)
    return decorated

def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get('X-API-KEY')
        if not key:
            return jsonify({'message': 'API key is missing'}), 401
        api_key = APIKey.query.filter_by(key=key, revoked=False).first()
        if not api_key:
            return jsonify({'message': 'Invalid or revoked API key'}), 401
        owner_user = User.query.filter_by(username=api_key.owner).first()
        if not owner_user or not owner_user.is_admin:
            return jsonify({'message': 'Admin privileges required'}), 403
        return f(*args, **kwargs)
    return decorated
