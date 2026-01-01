# 予約システム アーキテクチャ設計

## 📐 システム全体構成

```
┌─────────────────────────────────────────────────────────────┐
│                        ユーザー                               │
│                      (ブラウザ)                               │
└───────────────────┬─────────────────────────────────────────┘
                    │
                    │ HTTPS
                    ▼
┌─────────────────────────────────────────────────────────────┐
│                   Vercel (静的ホスティング)                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  index.html (予約LP + 予約UI)                         │   │
│  │  - 施術者選択                                          │   │
│  │  - 空き枠表示                                          │   │
│  │  - 予約フォーム                                        │   │
│  │  - JavaScript (Fetch API)                            │   │
│  └──────────────────────────────────────────────────────┘   │
└───────────────────┬─────────────────────────────────────────┘
                    │
                    │ HTTPS (CORS制限あり)
                    ▼
┌─────────────────────────────────────────────────────────────┐
│              Google Cloud Run (バックエンドAPI)               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Flask API Server (Python)                           │   │
│  │                                                       │   │
│  │  GET /api/availability                               │   │
│  │    → freebusy.query で空き枠取得                      │   │
│  │    → 回復枠を除外してJSON返却                         │   │
│  │                                                       │   │
│  │  POST /api/book                                      │   │
│  │    → 二重予約チェック (freebusy再確認)               │   │
│  │    → events.insert で予約確定                        │   │
│  │    → 成功/失敗をJSON返却                             │   │
│  │                                                       │   │
│  │  GET /health                                         │   │
│  │    → ヘルスチェック                                   │   │
│  └──────────────────────────────────────────────────────┘   │
│                           │                                  │
│  ┌────────────────────────┴──────────────────────────────┐   │
│  │  OAuth 2.0 Credentials                               │   │
│  │  - Refresh Token (Secret Managerから取得)            │   │
│  │  - Access Token (自動更新)                           │   │
│  └──────────────────────────────────────────────────────┘   │
└───────────────────┬─────────────────────────────────────────┘
                    │
                    │ Google Calendar API v3
                    ▼
┌─────────────────────────────────────────────────────────────┐
│              Google Calendar (予約先カレンダー)               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  平尾和子 (ドライヘッド) - Calendar ID: 8d9b024c...   │   │
│  │  星野美香 (ネイル)       - Calendar ID: 2192c0ed...   │   │
│  │  松岡佐智代 (手相)       - Calendar ID: 39bf6d15...   │   │
│  │  三浦智子 (エステ)       - Calendar ID: 7a5f8829...   │   │
│  │  平尾夏純 (耳つぼ)       - Calendar ID: 1d5175aa...   │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                    ▲
                    │
                    │ Secret Manager API
                    │
┌───────────────────┴─────────────────────────────────────────┐
│           Google Cloud Secret Manager                       │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  calendar-oauth-refresh-token                        │   │
│  │  calendar-oauth-client-secret                        │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 🏗️ Cloud Run vs Cloud Functions 比較

| 項目 | Cloud Run | Cloud Functions |
|------|-----------|-----------------|
| **コンテナ自由度** | 高い（任意のDockerfile） | 低い（ランタイム固定） |
| **起動時間** | やや遅い（コールドスタート） | やや遅い（同等） |
| **コスト** | リクエスト単位課金 | リクエスト単位課金 |
| **スケーラビリティ** | 自動・無制限 | 自動・無制限 |
| **状態管理** | ステートレス必須 | ステートレス必須 |
| **HTTPサーバー** | 任意（Flask/FastAPI等） | 関数ベース |
| **WebSocket対応** | 可能 | 不可 |
| **VPC接続** | 可能 | 可能 |

### ✅ 採用：Cloud Run

**理由:**
1. **Flaskでフルコントロール可能** - ミドルウェア、エラーハンドリング、ロギングを柔軟に実装
2. **複数エンドポイントを1サービスで管理** - `/api/availability`、`/api/book` を1つのアプリで提供
3. **将来の拡張性** - WebSocket（リアルタイム空き枠更新）やAdmin APIも追加可能
4. **デバッグが容易** - ローカルでDockerコンテナとして動作確認できる
5. **コスト効率** - 低トラフィックなら無料枠で十分（月100万リクエストまで無料）

---

## 🔒 セキュリティ設計

### 認証フロー

```
┌──────────────────────────────────────────────────────────┐
│  初回セットアップ（管理者がローカルで1回だけ実行）         │
└──────────────────────────────────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────────────────┐
│  1. OAuth 2.0 認証フロー（ブラウザで許可）                │
│     → credentials.json + 手動認可                         │
│     → refresh_token 取得                                 │
└──────────────────────────────────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────────────────┐
│  2. Secret Manager に保存                                │
│     gcloud secrets create calendar-oauth-refresh-token   │
│     --data-file=refresh_token.txt                        │
└──────────────────────────────────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────────────────┐
│  3. Cloud Run デプロイ時に環境変数で Secret 参照          │
│     環境変数: REFRESH_TOKEN_SECRET=projects/.../secrets/..│
└──────────────────────────────────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────────────────┐
│  4. 実行時に Secret Manager から refresh_token 取得       │
│     → access_token 自動生成（1時間有効）                 │
│     → Calendar API 呼び出し                              │
└──────────────────────────────────────────────────────────┘
```

### CORS設定

```python
# 許可するオリジン
ALLOWED_ORIGINS = [
    "https://salon-booking-vert.vercel.app",
    "http://localhost:8000",  # ローカルテスト用
]
```

### レート制限

```python
# IPアドレスごとに 1分間に10リクエストまで
# 簡易実装: インメモリカウンター（本番はRedis推奨）
```

---

## 🔄 二重予約防止ロジック

```python
def book_appointment(staff_id, start_time, duration, customer_info):
    """
    予約確定（二重予約防止付き）
    """
    # 1. 再度 freebusy.query で最新の空き状況を取得
    busy_slots = get_busy_slots(staff_id, start_time.date())

    # 2. 予約しようとしている時間帯が空いているか確認
    requested_slot = (start_time, start_time + duration)
    for busy_start, busy_end in busy_slots:
        if slots_overlap(requested_slot, (busy_start, busy_end)):
            raise ConflictError("この枠は既に予約されています")

    # 3. 空いていた場合のみ events.insert 実行
    event = {
        "summary": f"【予約】{staff_name} / {customer_info['name']}",
        "start": {"dateTime": start_time.isoformat(), "timeZone": "Asia/Tokyo"},
        "end": {"dateTime": (start_time + duration).isoformat(), "timeZone": "Asia/Tokyo"},
        "description": format_description(customer_info),
        "visibility": "private",
    }

    result = calendar_service.events().insert(
        calendarId=calendar_id,
        body=event
    ).execute()

    return result
```

**重要:**
- `freebusy.query` と `events.insert` の間にタイムラグがあるため、完全な排他制御ではない
- Google Calendar API側でも重複イベント作成は可能（物理的な排他ロックなし）
- しかし実用上、数秒のタイムラグで同じ枠を2人が予約する確率は極めて低い
- より厳密には「予約番号 + 事後確認メール」で運用でカバー

---

## 📊 データフロー

### 空き枠取得フロー

```
ユーザー
  │
  │ 1. 施術者選択「平尾和子」をクリック
  ▼
index.html
  │
  │ 2. GET /api/availability?staff=平尾和子&date=2026-02-20
  ▼
Cloud Run API
  │
  │ 3. freebusy.query(calendar_id, 2026-02-20 10:30-16:30)
  ▼
Google Calendar API
  │
  │ 4. busy: [{start: 11:00, end: 11:30}, {start: 12:00, end: 12:15}, ...]
  ▼
Cloud Run API
  │
  │ 5. 全枠（10:30-16:30、15分刻み）から busy を除外
  │    → available: [10:30, 10:45, 11:30, 11:45, ...]
  │ 6. 回復枠（12:00, 14:00）も除外
  ▼
index.html
  │
  │ 7. 空き枠を○×で表示
  ▼
ユーザー
```

### 予約確定フロー

```
ユーザー
  │
  │ 1. 空き枠「11:30」選択 + フォーム入力
  │    氏名：田中太郎、電話：090-xxxx-xxxx
  │ 2. 「予約する」ボタンクリック
  ▼
index.html
  │
  │ 3. POST /api/book
  │    {staff: "平尾和子", start: "2026-02-20T11:30:00",
  │     name: "田中太郎", phone: "090-xxxx-xxxx", ...}
  ▼
Cloud Run API
  │
  │ 4. 二重予約チェック（freebusy 再取得）
  │ 5. 11:30 が空いているか確認
  ▼
Google Calendar API
  │
  │ 6. events.insert(calendar_id, event)
  ▼
Cloud Run API
  │
  │ 7. {success: true, eventId: "...", message: "予約完了"}
  ▼
index.html
  │
  │ 8. 予約確定画面を表示
  │    「2026/2/20 11:30 平尾和子（ドライヘッド）の予約が完了しました」
  ▼
ユーザー
```

---

## 🗂️ ファイル構成

```
salon_booking/
├── index.html                    # LP + 予約UI（既存を拡張）
├── .gitignore
└── booking-api/
    ├── ARCHITECTURE.md           # 本ファイル
    ├── README.md                 # セットアップ手順
    ├── QUICKSTART.md             # 最短手順
    ├── config.yaml               # 設定ファイル
    ├── requirements.txt          # Python依存
    ├── Dockerfile                # Cloud Run用
    ├── .dockerignore
    ├── deploy.sh                 # デプロイスクリプト
    ├── setup_oauth.py            # 初回OAuth認証＆token取得
    ├── server.py                 # Flask APIサーバー本体
    ├── calendar_service.py       # Google Calendar API ラッパー
    ├── rate_limiter.py           # レート制限（簡易）
    └── .gitignore
```

---

## 🚀 デプロイフロー

```
1. ローカル開発
   ├── OAuth認証取得（setup_oauth.py）
   ├── refresh_token.txt 生成
   └── ローカルテスト（Docker）

2. GCP準備
   ├── Secret Manager に refresh_token 保存
   ├── Cloud Run サービス作成
   └── IAM権限設定

3. デプロイ
   ├── docker build
   ├── docker push (Artifact Registry)
   └── gcloud run deploy

4. フロントエンド更新
   ├── index.html に API URL 設定
   ├── git commit & push
   └── Vercel 自動デプロイ
```

---

## 📈 監視・運用

### ログ出力

```python
# 成功ログ
INFO: Booking confirmed - Staff: 平尾和子, Time: 2026-02-20T11:30, Customer: 田中**(マスク)

# エラーログ
ERROR: Booking failed - Slot already taken - Staff: 平尾和子, Time: 2026-02-20T11:30
```

### メトリクス（Cloud Run標準）

- リクエスト数
- レイテンシ
- エラー率
- コンテナインスタンス数

### アラート設定（任意）

- エラー率 > 10% → メール通知
- レイテンシ > 5秒 → Slack通知

---

## 🔮 将来の拡張案

1. **リアルタイム空き枠更新** - WebSocket or Server-Sent Events
2. **予約確認メール送信** - SendGrid / Gmail API
3. **管理画面** - 予約一覧、キャンセル、統計
4. **決済連携** - Stripe / Square（事前決済）
5. **LINE連携** - LINE Messaging API で予約通知
6. **多言語対応** - i18n（英語・中国語）

---

以上がシステム全体のアーキテクチャ設計です。
