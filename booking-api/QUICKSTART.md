# クイックスタートガイド

**10分で動かす予約システム（ローカル開発）**

---

## 🚀 最速セットアップ

### 前提条件

- Python 3.11以上
- Googleアカウント
- 施術者別カレンダー作成済み（`calendar-setup/`で完了済み）

---

## ステップ1: OAuth認証（5分）

### 1-1. GCP Consoleでcredentials.json取得

👉 https://console.cloud.google.com/apis/credentials

1. 「認証情報を作成」→ **OAuthクライアントID**
2. アプリケーションの種類: **デスクトップアプリ**
3. JSONダウンロード → `booking-api/credentials.json` に配置

### 1-2. OAuth同意画面設定

👉 https://console.cloud.google.com/apis/credentials/consent

1. ユーザータイプ: **外部**
2. アプリ名: 任意
3. スコープ追加: `../auth/calendar`
4. テストユーザー: 自分のGoogleアカウント追加

### 1-3. 初回認証実行

```bash
cd booking-api

# 仮想環境
python3 -m venv venv
source venv/bin/activate

# パッケージインストール
pip install -r requirements.txt

# OAuth認証
python setup_oauth.py
```

ブラウザが開く → ログイン → 「許可」

✅ `token.json` が生成される

---

## ステップ2: ローカル実行（2分）

### 2-1. サーバー起動

```bash
python server.py
```

**起動確認:**
```
INFO:__main__:CalendarService initialized successfully
 * Running on http://0.0.0.0:8080
```

### 2-2. 動作確認

別のターミナルで:

```bash
# ヘルスチェック
curl http://localhost:8080/health

# 空き枠取得
curl "http://localhost:8080/api/availability?staff=hirao_kazuko&date=2026-02-20"
```

---

## ステップ3: フロントエンド確認（3分）

### 3-1. ブラウザでindex.htmlを開く

```bash
cd ..
open index_with_booking.html  # macOS
# または
# start index_with_booking.html  # Windows
# xdg-open index_with_booking.html  # Linux
```

### 3-2. 予約テスト

1. 施術者カードの「予約する」をクリック
2. 空き枠が表示される
3. 時間を選択
4. フォーム入力して「予約を確定する」

### 3-3. Googleカレンダーで確認

👉 https://calendar.google.com

予約が施術者カレンダーに表示される ✅

---

## 本番デプロイへ進む場合

👉 `README.md` の「Cloud Run デプロイ」セクションへ

---

## トラブルシューティング

**Q. ブラウザ認証画面が出ない**
→ `token.json` を削除して `python setup_oauth.py` 再実行

**Q. 空き枠が表示されない**
→ カレンダーIDが正しいか `config.yaml` を確認

**Q. CORSエラー**
→ ローカルテストなら `config.yaml` に `http://localhost:8000` を追加

---

以上で動作確認完了です！ 🎉
