# ─────────────────────────────────────────────
# Dockerfile  ― 3.11 + google-generativeai 0.5.x 専用
# ─────────────────────────────────────────────
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    LANG=C.UTF-8 \
    PIP_DEFAULT_TIMEOUT=600

WORKDIR /app

# ▽ OS 依存ライブラリ
COPY config/ ./config/
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc libpq-dev libgl1 libglx-mesa0 libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

# ▽ pip base
RUN pip install --upgrade pip setuptools wheel

# ▽ Python deps
COPY requirements.txt .

# ❶ 互換性のない旧 SDK を削除
RUN pip uninstall -y google-genai google-ai-generativelanguage || true

# ❷ 依存をインストール
RUN pip install --no-cache-dir -r requirements.txt

# アプリ本体
COPY . .

COPY app/static/.well-known /app/app/static/.well-known

EXPOSE 80
CMD ["python", "run.py"]
