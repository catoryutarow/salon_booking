# 予約システムAPI - セットアップガイド

**よりみちSALON 美と癒しのマルシェ** オンライン予約システム

---

## 📋 目次

1. [システム概要](#システム概要)
2. [前提条件](#前提条件)
3. [ローカル開発環境セットアップ](#ローカル開発環境セットアップ)
4. [Google Cloud セットアップ](#google-cloud-セットアップ)
5. [Cloud Run デプロイ](#cloud-run-デプロイ)
6. [フロントエンド設定](#フロントエンド設定)
7. [動作確認](#動作確認)
8. [トラブルシューティング](#トラブルシューティング)

---

## システム概要

### アーキテクチャ

```
ユーザー（ブラウザ）
    ↓
Vercel（index.html）
    ↓ API呼び出し
Cloud Run（Flask API）
    ↓ Calendar API
Google Calendar（施術者別カレンダー）
```

### 主な機能

- **空き枠取得API** (`GET /api/availability`) - freebusy.query で空き状況を返す
- **予約確定API** (`POST /api/book`) - 二重予約チェック後にevents.insertで予約
- **CORS制限** - Vercelドメインのみ許可
- **レート制限** - IP単位で 10req/分、60req/時
- **個人情報保護** - ログにマスク処理

---

## 前提条件

### 必要なもの

- Python 3.11以上
- Google Cloud プロジェクト
- gcloud CLI
- Googleアカウント（Calendar API用）

### 既に完了している前提

- 施術者別カレンダーの作成（`calendar-setup/`で実施済み）
- カレンダーIDの取得

---

## ローカル開発環境セットアップ

### 1. 仮想環境作成

```bash
cd booking-api

# 仮想環境作成
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 依存関係インストール
pip install -r requirements.txt
```

### 2. OAuth 2.0 認証情報取得

#### GCP Console で設定

1. **OAuth同意画面**
   - https://console.cloud.google.com/apis/credentials/consent
   - ユーザータイプ: **外部**
   - アプリ名: よりみちSALON予約システム
   - スコープ: `https://www.googleapis.com/auth/calendar`
   - テストユーザー: 自分のGoogleアカウントを追加

2. **認証情報作成**
   - https://console.cloud.google.com/apis/credentials
   - 「認証情報を作成」→ **OAuthクライアントID**
   - アプリケーションの種類: **デスクトップアプリ**
   - JSONダウンロード → `credentials.json` にリネーム
   - `booking-api/` ディレクトリに配置

#### 初回認証実行

```bash
python setup_oauth.py
```

**手順:**
1. ブラウザが開く
2. Googleアカウントでログイン
3. 「許可」をクリック
4. `token.json` と `refresh_token.txt` が生成される

**出力例:**
```
✅ token.json に認証情報を保存しました

🔑 Refresh Token（Secret Manager登録用）:
--------------------------------------------------
1//0gXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
--------------------------------------------------

✅ refresh_token を refresh_token.txt に保存しました
```

### 3. ローカルサーバー起動

```bash
python server.py
```

**起動ログ:**
```
INFO:__main__:CalendarService initialized successfully
INFO:werkzeug: * Running on http://0.0.0.0:8080
```

### 4. 動作確認（ローカル）

```bash
# ヘルスチェック
curl http://localhost:8080/health

# 空き枠取得
curl "http://localhost:8080/api/availability?staff=hirao_kazuko&date=2026-02-20"

# 予約（POST）
curl -X POST http://localhost:8080/api/book \
  -H "Content-Type: application/json" \
  -d '{
    "staff": "hirao_kazuko",
    "start": "2026-02-20T11:30:00",
    "menu": "ドライヘッドスパ",
    "name": "テスト太郎",
    "phone": "090-1234-5678"
  }'
```

---

## Google Cloud セットアップ

### 1. プロジェクト作成（既存ならスキップ）

```bash
export PROJECT_ID="salon-booking-system"
gcloud projects create $PROJECT_ID --name="Salon Booking System"
gcloud config set project $PROJECT_ID

# 課金アカウント紐付け
gcloud billing accounts list
gcloud billing projects link $PROJECT_ID --billing-account=XXXXXX-XXXXXX-XXXXXX
```

### 2. 必要なAPIを有効化

```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  calendar-json.googleapis.com
```

### 3. Secret Manager に認証情報を保存

```bash
# refresh_token 保存
gcloud secrets create calendar-oauth-refresh-token \
  --data-file=refresh_token.txt \
  --replication-policy=automatic

# credentials.json（client_secret）保存
gcloud secrets create calendar-oauth-client-secret \
  --data-file=credentials.json \
  --replication-policy=automatic

# 確認
gcloud secrets list
```

### 4. サービスアカウントに権限付与

```bash
# Cloud Run のデフォルトサービスアカウント
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")
SERVICE_ACCOUNT="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

# Secret Manager アクセス権限
gcloud secrets add-iam-policy-binding calendar-oauth-refresh-token \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding calendar-oauth-client-secret \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role="roles/secretmanager.secretAccessor"
```

---

## Cloud Run デプロイ

### デプロイスクリプト実行

```bash
./deploy.sh
```

**処理内容:**
1. Secret Manager の確認
2. 必要なAPI有効化
3. Cloud Run にソースコードからデプロイ
4. サービスURL取得

**デプロイ完了時の出力:**
```
✅ デプロイ完了

サービスURL: https://booking-api-XXXXXXXXX-an.a.run.app

エンドポイント:
  - GET  https://booking-api-XXXXXXXXX-an.a.run.app/health
  - GET  https://booking-api-XXXXXXXXX-an.a.run.app/api/availability?staff=hirao_kazuko&date=2026-02-20
  - POST https://booking-api-XXXXXXXXX-an.a.run.app/api/book
```

### 手動デプロイ（デプロイスクリプトを使わない場合）

```bash
gcloud run deploy booking-api \
  --source . \
  --region=asia-northeast1 \
  --platform=managed \
  --allow-unauthenticated \
  --set-env-vars="GCP_PROJECT_ID=$PROJECT_ID" \
  --memory=512Mi \
  --cpu=1 \
  --timeout=60s \
  --max-instances=10
```

---

## フロントエンド設定

### 1. API URL をフロントエンドに設定

`index_with_booking.html` の API_BASE_URL を更新:

```javascript
// デプロイ前（ローカル開発）
const API_BASE_URL = 'http://localhost:8080';

// デプロイ後（本番環境）
const API_BASE_URL = 'https://booking-api-XXXXXXXXX-an.a.run.app';
```

### 2. index.html を差し替え

```bash
cd /Users/ryutaro/salon_booking

# バックアップ
mv index.html index_old.html

# 新しいファイルをindex.htmlにリネーム
cp index_with_booking.html index.html

# API URLを実際のCloud Run URLに置換
# （手動で編集するか、sedコマンド使用）
```

### 3. Vercel に再デプロイ

```bash
git add index.html
git commit -m "Add booking system with API integration"
git push
```

Vercelが自動でデプロイします。

---

## 動作確認

### 1. ヘルスチェック

```bash
curl https://booking-api-XXXXXXXXX-an.a.run.app/health
```

**期待レスポンス:**
```json
{"status":"ok","service":"booking-api"}
```

### 2. 空き枠取得テスト

```bash
curl "https://booking-api-XXXXXXXXX-an.a.run.app/api/availability?staff=hirao_kazuko&date=2026-02-20"
```

**期待レスポンス:**
```json
{
  "staff": {
    "id": "hirao_kazuko",
    "name": "平尾和子",
    "service": "ドライヘッド",
    "menus": [...]
  },
  "date": "2026-02-20",
  "available_slots": ["10:30", "10:45", "11:00", ...],
  "timezone": "Asia/Tokyo"
}
```

### 3. 予約テスト

```bash
curl -X POST https://booking-api-XXXXXXXXX-an.a.run.app/api/book \
  -H "Content-Type: application/json" \
  -d '{
    "staff": "hirao_kazuko",
    "start": "2026-02-20T15:00:00",
    "menu": "ドライヘッドスパ",
    "name": "テスト花子",
    "phone": "080-9999-8888",
    "email": "test@example.com",
    "note": "初めてです"
  }'
```

**成功レスポンス:**
```json
{
  "success": true,
  "event_id": "XXXXXXXXX",
  "message": "予約が完了しました",
  "booking": {
    "staff": "平尾和子",
    "service": "ドライヘッド",
    "menu": "ドライヘッドスパ",
    "date": "2026年02月20日",
    "time": "15:00",
    "duration": 10,
    "location": "北本市栄市民活動交流センター（埼玉県北本市栄1-1）",
    "customer_name": "テスト花子"
  }
}
```

### 4. Googleカレンダーで確認

https://calendar.google.com

予約が「平尾和子」のカレンダーに表示されているはずです。

### 5. フロントエンドで確認

https://salon-booking-vert.vercel.app/

1. 施術者カードの「予約する」ボタンをクリック
2. 空き枠が表示される
3. 時間を選択してフォーム入力
4. 予約確定

---

## トラブルシューティング

### Q. `token.json` が見つからない

```
FileNotFoundError: Token file not found: token.json
```

**対処法:**
```bash
python setup_oauth.py
```

### Q. Secret Manager へのアクセスエラー

```
PermissionDenied: The caller does not have permission
```

**対処法:**
```bash
# サービスアカウントに権限付与
gcloud secrets add-iam-policy-binding calendar-oauth-refresh-token \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role="roles/secretmanager.secretAccessor"
```

### Q. CORS エラー

```
Access to fetch at 'https://...' from origin 'https://salon-booking-vert.vercel.app' has been blocked by CORS policy
```

**対処法:**
`config.yaml` の `cors.allowed_origins` にVercelドメインを追加して再デプロイ

### Q. 二重予約が発生した

**原因:** 同時に2人が同じ枠を予約した（非常に稀）

**対処法:**
- Googleカレンダーで重複を確認
- 片方の予約をキャンセルして連絡
- 将来的にはRedisで分散ロック実装を検討

### Q. レート制限エラー

```
{"error":"Rate limit exceeded: 10 requests per minute"}
```

**対処法:**
- 正常な動作（DoS攻撃防止）
- `config.yaml` で制限値を調整可能

---

## 運用Tips

### ログ確認

```bash
# Cloud Run ログ確認
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=booking-api" \
  --limit 50 \
  --format json

# エラーログのみ
gcloud logging read "resource.type=cloud_run_revision AND severity>=ERROR" \
  --limit 20
```

### Secret更新

```bash
# refresh_token 更新
gcloud secrets versions add calendar-oauth-refresh-token \
  --data-file=refresh_token.txt
```

### デプロイ履歴確認

```bash
gcloud run revisions list --service=booking-api --region=asia-northeast1
```

### ロールバック

```bash
# 前のリビジョンに戻す
gcloud run services update-traffic booking-api \
  --to-revisions=REVISION_NAME=100 \
  --region=asia-northeast1
```

---

## セキュリティチェックリスト

- [ ] credentials.json をGitにコミットしていないか
- [ ] token.json をGitにコミットしていないか
- [ ] refresh_token.txt をGitにコミットしていないか
- [ ] Secret Manager に認証情報を保存したか
- [ ] CORS設定で許可ドメインを制限したか
- [ ] レート制限が有効になっているか
- [ ] ログに個人情報がマスクされているか

---

## 次のステップ

- [ ] 予約確認メール送信機能（SendGrid連携）
- [ ] 管理画面（予約一覧・キャンセル）
- [ ] リアルタイム空き枠更新（WebSocket）
- [ ] 予約リマインダー（前日通知）

---

## サポート

質問・不具合報告:
- GitHub Issues: https://github.com/catoryutarow/salon_booking/issues
- または README.md の連絡先へ

---

**予約システムの構築、お疲れ様でした！** 🎉
