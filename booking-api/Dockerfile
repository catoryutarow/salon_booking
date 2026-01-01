# Cloud Run 用 Dockerfile
FROM python:3.11-slim

# 作業ディレクトリ
WORKDIR /app

# 依存関係コピー & インストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコードコピー
COPY server.py .
COPY calendar_service.py .
COPY rate_limiter.py .
COPY config.yaml .

# ポート公開
EXPOSE 8080

# 本番環境では gunicorn で起動
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 server:app
