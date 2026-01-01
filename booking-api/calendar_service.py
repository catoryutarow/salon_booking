"""
Google Calendar API サービスクラス
空き枠取得・予約作成を担当
"""

import os
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
import logging

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)


class CalendarService:
    """Google Calendar API操作クラス"""

    def __init__(self, credentials: Credentials):
        """
        初期化

        Args:
            credentials: Google OAuth 2.0 credentials
        """
        self.credentials = credentials
        self.service = build("calendar", "v3", credentials=credentials)

    def get_busy_slots(
        self,
        calendar_id: str,
        date: datetime,
        start_time: str,
        end_time: str,
        timezone: str = "Asia/Tokyo"
    ) -> List[Tuple[datetime, datetime]]:
        """
        指定日のbusy枠を取得

        Args:
            calendar_id: カレンダーID
            date: 対象日
            start_time: 開始時刻 (HH:MM)
            end_time: 終了時刻 (HH:MM)
            timezone: タイムゾーン

        Returns:
            busy枠のリスト [(開始時刻, 終了時刻), ...]
        """
        try:
            # 時刻範囲を作成（タイムゾーン付き）
            from datetime import timezone as tz_module
            import pytz

            tz = pytz.timezone(timezone)
            time_min = tz.localize(datetime.combine(
                date.date(),
                datetime.strptime(start_time, "%H:%M").time()
            ))
            time_max = tz.localize(datetime.combine(
                date.date(),
                datetime.strptime(end_time, "%H:%M").time()
            ))

            # freebusy.query 実行
            body = {
                "timeMin": time_min.isoformat(),
                "timeMax": time_max.isoformat(),
                "timeZone": timezone,
                "items": [{"id": calendar_id}]
            }

            result = self.service.freebusy().query(body=body).execute()
            calendar_busy = result["calendars"].get(calendar_id, {})
            busy_periods = calendar_busy.get("busy", [])

            # datetimeオブジェクトに変換
            busy_slots = []
            for period in busy_periods:
                start = datetime.fromisoformat(period["start"].replace("Z", "+00:00"))
                end = datetime.fromisoformat(period["end"].replace("Z", "+00:00"))
                busy_slots.append((start, end))

            logger.info(f"Retrieved {len(busy_slots)} busy slots for calendar {calendar_id[:8]}...")
            return busy_slots

        except HttpError as error:
            logger.error(f"Calendar API error: {error}")
            raise
        except Exception as error:
            logger.error(f"Unexpected error in get_busy_slots: {error}")
            raise

    def generate_available_slots(
        self,
        busy_slots: List[Tuple[datetime, datetime]],
        date: datetime,
        start_time: str,
        end_time: str,
        slot_duration: int,
        recovery_times: List[str],
        timezone: str = "Asia/Tokyo"
    ) -> List[datetime]:
        """
        空き枠リストを生成

        Args:
            busy_slots: busy枠リスト
            date: 対象日
            start_time: 営業開始時刻 (HH:MM)
            end_time: 営業終了時刻 (HH:MM)
            slot_duration: 1枠の長さ（分）
            recovery_times: 回復枠の時刻リスト ["12:00", "14:00"]
            timezone: タイムゾーン

        Returns:
            空き枠の開始時刻リスト
        """
        # 全枠を生成
        time_min = datetime.combine(
            date.date(),
            datetime.strptime(start_time, "%H:%M").time()
        )
        time_max = datetime.combine(
            date.date(),
            datetime.strptime(end_time, "%H:%M").time()
        )

        all_slots = []
        current = time_min
        while current < time_max:
            all_slots.append(current)
            current += timedelta(minutes=slot_duration)

        # 回復枠を除外
        recovery_slots = []
        for recovery_time in recovery_times:
            recovery_dt = datetime.combine(
                date.date(),
                datetime.strptime(recovery_time, "%H:%M").time()
            )
            recovery_slots.append(recovery_dt)

        # busy枠と回復枠を除外
        available_slots = []
        for slot in all_slots:
            slot_end = slot + timedelta(minutes=slot_duration)

            # 回復枠チェック
            if slot in recovery_slots:
                continue

            # busy枠チェック
            is_available = True
            for busy_start, busy_end in busy_slots:
                # 重複判定
                if self._slots_overlap(
                    (slot, slot_end),
                    (busy_start, busy_end)
                ):
                    is_available = False
                    break

            if is_available:
                available_slots.append(slot)

        logger.info(f"Generated {len(available_slots)} available slots from {len(all_slots)} total slots")
        return available_slots

    def _slots_overlap(
        self,
        slot1: Tuple[datetime, datetime],
        slot2: Tuple[datetime, datetime]
    ) -> bool:
        """
        2つの時間枠が重複しているか判定

        Args:
            slot1: (開始, 終了)
            slot2: (開始, 終了)

        Returns:
            重複している場合 True
        """
        start1, end1 = slot1
        start2, end2 = slot2
        return start1 < end2 and start2 < end1

    def create_booking(
        self,
        calendar_id: str,
        start_time: datetime,
        duration: int,
        customer_name: str,
        customer_phone: str,
        staff_name: str,
        service_name: str,
        location: str,
        customer_email: Optional[str] = None,
        note: Optional[str] = None,
        timezone: str = "Asia/Tokyo"
    ) -> Dict:
        """
        予約を確定（イベント作成）

        Args:
            calendar_id: カレンダーID
            start_time: 開始時刻
            duration: 施術時間（分）
            customer_name: 予約者名
            customer_phone: 電話番号
            staff_name: 施術者名
            service_name: サービス名
            location: 会場住所
            customer_email: メールアドレス（任意）
            note: 備考（任意）
            timezone: タイムゾーン

        Returns:
            作成されたイベント情報

        Raises:
            HttpError: Calendar API エラー
        """
        end_time = start_time + timedelta(minutes=duration)

        # イベント説明文作成
        description_lines = [
            f"予約者: {customer_name}",
            f"電話: {customer_phone}",
        ]
        if customer_email:
            description_lines.append(f"メール: {customer_email}")
        if note:
            description_lines.append(f"備考: {note}")

        description_lines.extend([
            "",
            "【注意事項】",
            "・延長や追加メニューは当日の空き状況次第でご案内します",
            "・遅刻した場合、施術時間が短くなる可能性があります",
            "・キャンセルはお早めにご連絡ください",
        ])

        description = "\n".join(description_lines)

        # イベント作成
        event = {
            "summary": f"【予約】{staff_name} / {service_name} / {customer_name}様",
            "location": location,
            "description": description,
            "start": {
                "dateTime": start_time.isoformat(),
                "timeZone": timezone,
            },
            "end": {
                "dateTime": end_time.isoformat(),
                "timeZone": timezone,
            },
            "visibility": "private",  # 非公開
            "reminders": {
                "useDefault": False,
            },
        }

        try:
            created_event = self.service.events().insert(
                calendarId=calendar_id,
                body=event
            ).execute()

            logger.info(
                f"Booking created - Staff: {staff_name}, "
                f"Time: {start_time.isoformat()}, "
                f"Customer: {customer_name[:2]}** (masked)"
            )

            return created_event

        except HttpError as error:
            logger.error(f"Failed to create booking: {error}")
            raise

    def is_slot_available(
        self,
        calendar_id: str,
        start_time: datetime,
        duration: int,
        recovery_times: List[str],
        timezone: str = "Asia/Tokyo"
    ) -> bool:
        """
        指定枠が予約可能かチェック（二重予約防止用）

        Args:
            calendar_id: カレンダーID
            start_time: 開始時刻
            duration: 施術時間（分）
            recovery_times: 回復枠時刻リスト
            timezone: タイムゾーン

        Returns:
            予約可能な場合 True
        """
        # 回復枠チェック
        start_time_str = start_time.strftime("%H:%M")
        if start_time_str in recovery_times:
            logger.warning(f"Slot {start_time_str} is a recovery slot")
            return False

        # busy枠チェック
        date = start_time
        busy_slots = self.get_busy_slots(
            calendar_id=calendar_id,
            date=date,
            start_time=start_time.strftime("%H:%M"),
            end_time=(start_time + timedelta(hours=1)).strftime("%H:%M"),
            timezone=timezone
        )

        end_time = start_time + timedelta(minutes=duration)
        requested_slot = (start_time, end_time)

        for busy_start, busy_end in busy_slots:
            if self._slots_overlap(requested_slot, (busy_start, busy_end)):
                logger.warning(
                    f"Slot {start_time.isoformat()} overlaps with busy period "
                    f"{busy_start.isoformat()} - {busy_end.isoformat()}"
                )
                return False

        return True
