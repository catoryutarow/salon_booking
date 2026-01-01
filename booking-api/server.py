"""
予約システム Flask API サーバー
"""

import os
import sys
import yaml
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import pytz

from flask import Flask, request, jsonify
from flask_cors import CORS
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google.cloud import secretmanager
from googleapiclient.errors import HttpError

from calendar_service import CalendarService
from rate_limiter import RateLimiter

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Flask app
app = Flask(__name__)

# 設定読み込み
with open("config.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

# CORS設定
allowed_origins = config["cors"]["allowed_origins"]
CORS(app, resources={r"/api/*": {"origins": allowed_origins}})

# レート制限
rate_limit_config = config["rate_limit"]
rate_limiter = RateLimiter(
    max_per_minute=rate_limit_config["max_requests_per_minute"],
    max_per_hour=rate_limit_config["max_requests_per_hour"]
) if rate_limit_config["enabled"] else None

# グローバル変数
calendar_service: Optional[CalendarService] = None


def get_client_ip() -> str:
    """クライアントIPアドレスを取得"""
    if request.headers.get("X-Forwarded-For"):
        return request.headers["X-Forwarded-For"].split(",")[0].strip()
    return request.remote_addr or "unknown"


def check_rate_limit() -> Optional[Dict]:
    """レート制限チェック"""
    if not rate_limiter:
        return None

    ip_address = get_client_ip()
    allowed, message = rate_limiter.is_allowed(ip_address)

    if not allowed:
        logger.warning(f"Rate limit exceeded for IP: {ip_address}")
        return {"error": message}, 429

    return None


def mask_sensitive_data(data: str, mask_type: str) -> str:
    """個人情報をマスク"""
    if mask_type == "phone":
        # 090-1234-5678 → 090-****-5678
        if len(data) > 4:
            return data[:3] + "****" + data[-4:]
        return "****"
    elif mask_type == "email":
        # test@example.com → t***@example.com
        if "@" in data:
            local, domain = data.split("@", 1)
            return local[0] + "***@" + domain
        return "***"
    return data


def get_credentials() -> Credentials:
    """
    Google OAuth 2.0 認証情報を取得

    開発環境: token.json から読み込み
    本番環境: Secret Manager から refresh_token 取得
    """
    is_development = config.get("development", {}).get("use_local_credentials", False)

    if is_development:
        # ローカル開発環境
        logger.info("Using local credentials (development mode)")
        token_file = config["development"]["token_file"]

        if not os.path.exists(token_file):
            logger.error(f"Token file not found: {token_file}")
            logger.error("Run setup_oauth.py first to generate token.json")
            raise FileNotFoundError(f"Token file not found: {token_file}")

        creds = Credentials.from_authorized_user_file(
            token_file,
            scopes=config["google_calendar"]["scopes"]
        )

        # トークン更新
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())

        return creds

    else:
        # 本番環境（Secret Manager）
        logger.info("Using Secret Manager credentials (production mode)")
        project_id = os.environ.get("GCP_PROJECT_ID")

        if not project_id:
            raise ValueError("GCP_PROJECT_ID environment variable not set")

        client = secretmanager.SecretManagerServiceClient()

        # refresh_token 取得
        refresh_token_name = config["secrets"]["refresh_token_name"]
        refresh_token_path = f"projects/{project_id}/secrets/{refresh_token_name}/versions/latest"
        refresh_token_response = client.access_secret_version(name=refresh_token_path)
        refresh_token = refresh_token_response.payload.data.decode("UTF-8")

        # client_secret 取得
        client_secret_name = config["secrets"]["client_secret_name"]
        client_secret_path = f"projects/{project_id}/secrets/{client_secret_name}/versions/latest"
        client_secret_response = client.access_secret_version(name=client_secret_path)
        client_secret_data = client_secret_response.payload.data.decode("UTF-8")

        # client_secret は JSON 形式
        import json
        client_config = json.loads(client_secret_data)

        # Credentials 作成
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri=client_config["installed"]["token_uri"],
            client_id=client_config["installed"]["client_id"],
            client_secret=client_config["installed"]["client_secret"],
            scopes=config["google_calendar"]["scopes"]
        )

        # トークン更新
        creds.refresh(Request())

        return creds


def init_calendar_service():
    """CalendarService 初期化"""
    global calendar_service
    try:
        creds = get_credentials()
        calendar_service = CalendarService(creds)
        logger.info("CalendarService initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize CalendarService: {e}")
        raise


def get_staff_by_id(staff_id: str) -> Optional[Dict]:
    """スタッフIDから施術者情報を取得"""
    for staff in config["staff"]:
        if staff["id"] == staff_id:
            return staff
    return None


@app.route("/health", methods=["GET"])
def health_check():
    """ヘルスチェック"""
    return jsonify({"status": "ok", "service": "booking-api"}), 200


@app.route("/api/availability", methods=["GET"])
def get_availability():
    """
    空き枠取得API

    Query Parameters:
        staff: スタッフID（必須）
        date: 日付 YYYY-MM-DD（任意、デフォルトはイベント日）

    Returns:
        {
            "staff": {...},
            "date": "2026-02-20",
            "available_slots": ["10:30", "10:45", ...],
            "timezone": "Asia/Tokyo"
        }
    """
    # レート制限チェック
    rate_limit_error = check_rate_limit()
    if rate_limit_error:
        return rate_limit_error

    try:
        # パラメータ取得
        staff_id = request.args.get("staff")
        date_str = request.args.get("date", config["event"]["date"])

        if not staff_id:
            return jsonify({"error": "staff parameter is required"}), 400

        # スタッフ情報取得
        staff = get_staff_by_id(staff_id)
        if not staff:
            return jsonify({"error": f"Staff not found: {staff_id}"}), 404

        # 日付パース
        try:
            date = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

        # イベント日チェック
        event_date_str = config["event"]["date"]
        if date_str != event_date_str:
            return jsonify({"error": f"Bookings only available for {event_date_str}"}), 400

        # busy枠取得
        calendar_id = staff["calendar_id"]
        start_time = config["event"]["start_time"]
        end_time = config["event"]["end_time"]
        timezone = config["event"]["timezone"]

        busy_slots = calendar_service.get_busy_slots(
            calendar_id=calendar_id,
            date=date,
            start_time=start_time,
            end_time=end_time,
            timezone=timezone
        )

        # 回復枠時刻リスト
        recovery_times = [slot["time"] for slot in config["recovery_slots"]]

        # 空き枠生成
        available_slots_dt = calendar_service.generate_available_slots(
            busy_slots=busy_slots,
            date=date,
            start_time=start_time,
            end_time=end_time,
            slot_duration=config["booking"]["slot_duration"],
            recovery_times=recovery_times,
            timezone=timezone
        )

        # 時刻文字列に変換
        available_slots = [dt.strftime("%H:%M") for dt in available_slots_dt]

        logger.info(
            f"Availability requested - Staff: {staff['name']}, "
            f"Date: {date_str}, Available: {len(available_slots)} slots"
        )

        return jsonify({
            "staff": {
                "id": staff["id"],
                "name": staff["name"],
                "service": staff["service"],
                "menus": staff["menus"]
            },
            "date": date_str,
            "available_slots": available_slots,
            "timezone": timezone
        }), 200

    except HttpError as e:
        logger.error(f"Google Calendar API error: {e}")
        return jsonify({"error": "Calendar service error"}), 503
    except Exception as e:
        logger.error(f"Unexpected error in get_availability: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/book", methods=["POST"])
def create_booking():
    """
    予約確定API

    Request Body:
        {
            "staff": "hirao_kazuko",
            "start": "2026-02-20T11:30:00",
            "menu": "ドライヘッドスパ",
            "name": "田中太郎",
            "phone": "090-1234-5678",
            "email": "test@example.com" (optional),
            "note": "備考" (optional)
        }

    Returns:
        {
            "success": true,
            "event_id": "...",
            "message": "予約が完了しました",
            "booking": {...}
        }
    """
    # レート制限チェック
    rate_limit_error = check_rate_limit()
    if rate_limit_error:
        return rate_limit_error

    try:
        data = request.get_json()

        # バリデーション
        required_fields = ["staff", "start", "menu", "name", "phone"]
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400

        staff_id = data["staff"]
        start_str = data["start"]
        menu_name = data["menu"]
        customer_name = data["name"]
        customer_phone = data["phone"]
        customer_email = data.get("email")
        note = data.get("note")

        # スタッフ情報取得
        staff = get_staff_by_id(staff_id)
        if not staff:
            return jsonify({"error": f"Staff not found: {staff_id}"}), 404

        # メニュー情報取得
        menu = None
        for m in staff["menus"]:
            if m["name"] == menu_name:
                menu = m
                break

        if not menu:
            return jsonify({"error": f"Menu not found: {menu_name}"}), 404

        # 開始時刻パース（タイムゾーン付き）
        timezone = config["event"]["timezone"]
        try:
            # naive datetime をパース
            start_time_naive = datetime.fromisoformat(start_str)
            # タイムゾーンを付与
            tz = pytz.timezone(timezone)
            start_time = tz.localize(start_time_naive)
        except ValueError:
            return jsonify({"error": "Invalid start time format"}), 400

        # イベント日チェック
        event_date_str = config["event"]["date"]
        if start_time.strftime("%Y-%m-%d") != event_date_str:
            return jsonify({"error": f"Bookings only available for {event_date_str}"}), 400

        # 回復枠時刻リスト
        recovery_times = [slot["time"] for slot in config["recovery_slots"]]

        # 二重予約チェック
        calendar_id = staff["calendar_id"]
        duration = menu["duration"]

        is_available = calendar_service.is_slot_available(
            calendar_id=calendar_id,
            start_time=start_time,
            duration=duration,
            recovery_times=recovery_times,
            timezone=timezone
        )

        if not is_available:
            logger.warning(
                f"Booking failed - Slot already taken - "
                f"Staff: {staff['name']}, Time: {start_str}"
            )
            return jsonify({
                "error": "この時間枠は既に予約されています。別の時間をお選びください。"
            }), 409  # Conflict

        # 予約確定
        event = calendar_service.create_booking(
            calendar_id=calendar_id,
            start_time=start_time,
            duration=duration,
            customer_name=customer_name,
            customer_phone=customer_phone,
            staff_name=staff["name"],
            service_name=menu_name,
            location=config["event"]["location"],
            customer_email=customer_email,
            note=note,
            timezone=timezone
        )

        # マスク処理してログ
        masked_phone = mask_sensitive_data(customer_phone, "phone")
        masked_email = mask_sensitive_data(customer_email, "email") if customer_email else None

        logger.info(
            f"Booking confirmed - Staff: {staff['name']}, "
            f"Time: {start_str}, Menu: {menu_name}, "
            f"Customer: {customer_name[:2]}**, Phone: {masked_phone}"
        )

        return jsonify({
            "success": True,
            "event_id": event["id"],
            "message": "予約が完了しました",
            "booking": {
                "staff": staff["name"],
                "service": staff["service"],
                "menu": menu_name,
                "date": start_time.strftime("%Y年%m月%d日"),
                "time": start_time.strftime("%H:%M"),
                "duration": duration,
                "location": config["event"]["location"],
                "customer_name": customer_name
            }
        }), 200

    except HttpError as e:
        logger.error(f"Google Calendar API error: {e}")
        return jsonify({"error": "予約処理中にエラーが発生しました"}), 503
    except Exception as e:
        logger.error(f"Unexpected error in create_booking: {e}")
        return jsonify({"error": "予約処理中にエラーが発生しました"}), 500


@app.errorhandler(404)
def not_found(error):
    """404エラーハンドラ"""
    return jsonify({"error": "Endpoint not found"}), 404


@app.errorhandler(500)
def internal_error(error):
    """500エラーハンドラ"""
    logger.error(f"Internal server error: {error}")
    return jsonify({"error": "Internal server error"}), 500


if __name__ == "__main__":
    # CalendarService 初期化
    init_calendar_service()

    # サーバー起動
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
