# config.py

import os
from dotenv import load_dotenv
import pytz
from datetime import timedelta

load_dotenv()  # .envファイルを読み込む

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your_default_secret_key'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'postgresql://iriyo:iriyo@localhost/iriyo'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # メール設定
    MAIL_SERVER = os.environ.get('MAIL_SERVER') or 'smtp.example.com'
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS') in ['true', 'True', '1']
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL') in ['true', 'True', '1']
    MAIL_USERNAME = os.environ.get('EMAIL_USER')
    MAIL_PASSWORD = os.environ.get('EMAIL_PASS')
    MAIL_DEFAULT_SENDER = os.environ.get('EMAIL_USER')
    
    # マップAPIキー
    MAPS_API_KEY = os.environ.get('MAPS_API_KEY')
    
    # タイムゾーン
    TIMEZONE = pytz.timezone('Asia/Tokyo')
    
    # ファイルアップロードフォルダー
    UPLOAD_FOLDER = 'app/static/uploads/chat_attachments'
    
    # JWT設定
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or 'your_jwt_secret_key'
    
    # Twilio設定
    TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
    TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
    TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER')
    
    # Google APIキー（Vision AI と Geocoding API 用）
    GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY')

    # Flask-Limiter の設定
    RATELIMIT_STORAGE_URL = os.environ.get('RATELIMIT_STORAGE_URL') or 'redis://localhost:6379/1'  # Redisを使用

    S3_BUCKET = os.getenv("S3_BUCKET", "hazaippo-assets-prod")
    AWS_REGION = os.getenv("AWS_REGION", "ap-northeast-1")
    # ↓ローカル開発だけキーを読む。EC2/IAM ロール上では不要
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
