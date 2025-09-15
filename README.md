# はざいっぽ

## プロジェクト概要

建築・リフォームで発生する資材の廃棄コスト削減と、資材不足の業者へのマッチングを通じて、建築業界全体の資源利用効率を向上させるWEBアプリケーションです。

## セットアップ

1. リポジトリをクローン
    ```bash
    git clone https://github.com/yourusername/the-iriyo.git
    cd the-iriyo
    ```

2. 仮想環境を作成してアクティベート
    ```bash
    python3 -m venv venv
    source venv/bin/activate  # Windowsの場合: venv\Scripts\activate
    ```

3. 必要なパッケージをインストール
    ```bash
    pip install -r requirements.txt
    ```

4. データベースを設定
    ```python
    from app import db, create_app

    app = create_app()
    with app.app_context():
        db.create_all()
    ```

5. アプリケーションを起動
    ```bash
    flask run
    ```

## デプロイ

Herokuにデプロイするには、以下のコマンドを実行してください。

1. Heroku CLIにログイン
    ```bash
    heroku login
    ```

2. Herokuアプリを作成
    ```bash
    heroku create the-iriyo
    ```

3. Herokuにデプロイ
    ```bash
    git push heroku main
    ```

4. 環境変数を設定
    ```bash
    heroku config:set SECRET_KEY=your_secret_key
    heroku config:set EMAIL_USER=your_email@example.com
    heroku config:set EMAIL_PASS=your_email_password
    heroku config:set MAPS_API_KEY=your_maps_api_key
    heroku config:set LINE_API_KEY=your_line_api_key
    ```

## 使用技術

- フロントエンド: Flask (Python)
- バックエンド: Flask (Python)
- データベース: PostgreSQL
- インフラ: Heroku
- バージョン管理: Git (GitHub)
- CI/CD: GitHub Actions

## 開発者

荒木 海至
