#!/bin/bash
# Cloud Run デプロイスクリプト

set -e

# 色付きログ
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}  予約API - Cloud Run デプロイ${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo

# プロジェクトID確認
PROJECT_ID=$(gcloud config get-value project)
if [ -z "$PROJECT_ID" ]; then
  echo -e "${RED}❌ GCPプロジェクトが設定されていません${NC}"
  echo "gcloud config set project YOUR_PROJECT_ID を実行してください"
  exit 1
fi

echo -e "${GREEN}✅ プロジェクト: $PROJECT_ID${NC}"
echo

# リージョン設定
REGION="asia-northeast1"
SERVICE_NAME="booking-api"

# Secret Manager にトークンがあるか確認
echo -e "${BLUE}🔐 Secret Manager 確認...${NC}"
if ! gcloud secrets describe calendar-oauth-refresh-token --project=$PROJECT_ID &>/dev/null; then
  echo -e "${YELLOW}⚠️  Secret が見つかりません${NC}"
  echo "以下のコマンドで refresh_token を登録してください:"
  echo ""
  echo "  gcloud secrets create calendar-oauth-refresh-token \\"
  echo "    --data-file=refresh_token.txt \\"
  echo "    --replication-policy=automatic"
  echo ""
  echo "  gcloud secrets create calendar-oauth-client-secret \\"
  echo "    --data-file=credentials.json \\"
  echo "    --replication-policy=automatic"
  echo ""
  read -p "Secretを登録しましたか？ (y/N): " -n 1 -r
  echo
  if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "デプロイを中断しました"
    exit 1
  fi
fi

echo -e "${GREEN}✅ Secret が存在します${NC}"
echo

# API有効化
echo -e "${BLUE}📦 必要なAPIを有効化...${NC}"
gcloud services enable run.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  --project=$PROJECT_ID

echo -e "${GREEN}✅ API有効化完了${NC}"
echo

# Cloud Run デプロイ
echo -e "${BLUE}🚀 Cloud Run にデプロイ...${NC}"

gcloud run deploy $SERVICE_NAME \
  --source . \
  --region=$REGION \
  --platform=managed \
  --allow-unauthenticated \
  --set-env-vars="GCP_PROJECT_ID=$PROJECT_ID" \
  --update-secrets="REFRESH_TOKEN=calendar-oauth-refresh-token:latest,CLIENT_SECRET=calendar-oauth-client-secret:latest" \
  --memory=512Mi \
  --cpu=1 \
  --timeout=60s \
  --max-instances=10 \
  --min-instances=0 \
  --project=$PROJECT_ID

echo
echo -e "${GREEN}✅ デプロイ完了${NC}"
echo

# サービスURL取得
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME \
  --region=$REGION \
  --format='value(status.url)' \
  --project=$PROJECT_ID)

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}📋 デプロイ情報${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo
echo "サービスURL: $SERVICE_URL"
echo
echo "エンドポイント:"
echo "  - GET  $SERVICE_URL/health"
echo "  - GET  $SERVICE_URL/api/availability?staff=hirao_kazuko&date=2026-02-20"
echo "  - POST $SERVICE_URL/api/book"
echo
echo "次のステップ:"
echo "1. ヘルスチェック: curl $SERVICE_URL/health"
echo "2. index.html の API_BASE_URL を更新"
echo "3. git commit & push（Vercel自動デプロイ）"
echo
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
