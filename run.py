import os
from app import create_app, socketio  # socketio をインポート
from config import Config

app = create_app(Config)

if __name__ == "__main__":
    # デバッグモードとポートの設定を環境変数で制御
    debug_mode = os.environ.get('FLASK_DEBUG', 'True').lower() == 'true'
    port = int(os.environ.get('PORT', 80))
    
    # socketio.run() を使用してアプリケーションを起動
    socketio.run(app, debug=debug_mode, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)
