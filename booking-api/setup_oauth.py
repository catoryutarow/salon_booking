#!/usr/bin/env python3
"""
OAuth 2.0 初回認証スクリプト
refresh_token を取得して token.json に保存
"""

import os
import sys
import yaml
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# 設定読み込み
with open("config.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

SCOPES = config["google_calendar"]["scopes"]
CREDENTIALS_FILE = config["development"]["credentials_file"]
TOKEN_FILE = config["development"]["token_file"]


def main():
    """OAuth認証実行"""
    print("🔐 Google Calendar API OAuth 2.0 認証")
    print("=" * 50)
    print()

    # credentials.json 確認
    if not os.path.exists(CREDENTIALS_FILE):
        print(f"❌ {CREDENTIALS_FILE} が見つかりません")
        print()
        print("以下の手順で credentials.json を取得してください：")
        print("1. https://console.cloud.google.com/apis/credentials にアクセス")
        print("2. 「認証情報を作成」→「OAuthクライアントID」")
        print("3. アプリケーションの種類: デスクトップアプリ")
        print("4. JSONをダウンロードして credentials.json にリネーム")
        print("5. このディレクトリに配置")
        sys.exit(1)

    creds = None

    # 既存トークン確認
    if os.path.exists(TOKEN_FILE):
        print(f"✅ 既存の {TOKEN_FILE} が見つかりました")
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    # トークンが無効な場合は再認証
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("🔄 トークンを更新中...")
            creds.refresh(Request())
        else:
            print("🌐 ブラウザで認証画面を開きます...")
            print("   Googleアカウントでログインして「許可」をクリックしてください")
            print()
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_FILE, SCOPES
            )
            creds = flow.run_local_server(port=0)

        # トークン保存
        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

        print()
        print(f"✅ {TOKEN_FILE} に認証情報を保存しました")

    print()
    print("=" * 50)
    print("✅ OAuth認証完了")
    print()
    print("📋 次のステップ:")
    print("1. refresh_token をSecret Managerに保存（本番環境）")
    print("   または、")
    print("2. ローカルテスト: python server.py")
    print()

    # refresh_token を表示（Secret Manager登録用）
    if creds.refresh_token:
        print("🔑 Refresh Token（Secret Manager登録用）:")
        print("-" * 50)
        print(creds.refresh_token)
        print("-" * 50)
        print()
        print("⚠️  この値は秘密情報です。誰にも共有しないでください")
        print()

        # refresh_token をファイルに保存
        refresh_token_file = "refresh_token.txt"
        with open(refresh_token_file, "w") as f:
            f.write(creds.refresh_token)
        print(f"✅ refresh_token を {refresh_token_file} に保存しました")
        print()


if __name__ == "__main__":
    main()
