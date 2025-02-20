# Python3.11-slimをベースイメージとして使用
FROM python:3.11-slim

# 出力を即時に行うための環境変数
ENV PYTHONUNBUFFERED=1
ENV LANG=C.UTF-8

# 作業ディレクトリを設定
WORKDIR /app

# システムパッケージの更新と必要パッケージのインストール
RUN apt-get update && apt-get install -y gcc libpq-dev && rm -rf /var/lib/apt/lists/*

# 依存パッケージリストをコピー
COPY requirements.txt .

# pipのアップグレードと依存パッケージのインストール
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# プロジェクト内の全ファイルをコンテナにコピー
COPY . .

# アプリケーションがリッスンするポート（例：8000）を公開
EXPOSE 8000

# コンテナ起動時にrun.pyからFlaskアプリを起動
CMD ["python", "run.py"]
