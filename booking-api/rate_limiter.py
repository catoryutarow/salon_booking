"""
シンプルなレート制限実装（インメモリ）
本番環境ではRedisを推奨
"""

import time
from collections import defaultdict
from threading import Lock
from typing import Dict, Tuple


class RateLimiter:
    """IPアドレスベースのレート制限"""

    def __init__(self, max_per_minute: int = 10, max_per_hour: int = 60):
        """
        初期化

        Args:
            max_per_minute: 1分あたりの最大リクエスト数
            max_per_hour: 1時間あたりの最大リクエスト数
        """
        self.max_per_minute = max_per_minute
        self.max_per_hour = max_per_hour

        # IPごとのリクエスト履歴 {ip: [(timestamp, count), ...]}
        self.minute_requests: Dict[str, list] = defaultdict(list)
        self.hour_requests: Dict[str, list] = defaultdict(list)

        self.lock = Lock()

    def is_allowed(self, ip_address: str) -> Tuple[bool, str]:
        """
        リクエストを許可するか判定

        Args:
            ip_address: クライアントIPアドレス

        Returns:
            (許可するか, エラーメッセージ)
        """
        with self.lock:
            current_time = time.time()

            # 古いエントリを削除
            self._cleanup_old_entries(ip_address, current_time)

            # 1分間のリクエスト数チェック
            minute_count = len(self.minute_requests[ip_address])
            if minute_count >= self.max_per_minute:
                return False, f"Rate limit exceeded: {self.max_per_minute} requests per minute"

            # 1時間のリクエスト数チェック
            hour_count = len(self.hour_requests[ip_address])
            if hour_count >= self.max_per_hour:
                return False, f"Rate limit exceeded: {self.max_per_hour} requests per hour"

            # リクエストを記録
            self.minute_requests[ip_address].append(current_time)
            self.hour_requests[ip_address].append(current_time)

            return True, ""

    def _cleanup_old_entries(self, ip_address: str, current_time: float):
        """
        古いリクエスト記録を削除

        Args:
            ip_address: IPアドレス
            current_time: 現在時刻（Unix timestamp）
        """
        # 1分以上前のエントリを削除
        minute_threshold = current_time - 60
        self.minute_requests[ip_address] = [
            t for t in self.minute_requests[ip_address]
            if t > minute_threshold
        ]

        # 1時間以上前のエントリを削除
        hour_threshold = current_time - 3600
        self.hour_requests[ip_address] = [
            t for t in self.hour_requests[ip_address]
            if t > hour_threshold
        ]

    def reset(self, ip_address: str):
        """
        特定IPのカウンターをリセット

        Args:
            ip_address: IPアドレス
        """
        with self.lock:
            self.minute_requests.pop(ip_address, None)
            self.hour_requests.pop(ip_address, None)

    def reset_all(self):
        """全IPのカウンターをリセット"""
        with self.lock:
            self.minute_requests.clear()
            self.hour_requests.clear()
