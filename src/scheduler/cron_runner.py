"""
scheduler/cron_runner.py — 예약 업로드 실행

백그라운드 스레드에서 upload_queue를 주기적으로 폴링하며,
예약 시간이 도래한 대기 항목을 순차 업로드한다.

반복 스케줄 설정: "없음" | "매일" | "월수금" | 직접설정(cron 문자열)
"""

import json
import logging
import threading
from datetime import datetime, timedelta
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# 스케줄 체크 간격 (초)
_POLL_INTERVAL = 60

# 반복 스케줄 프리셋에서 허용하는 요일 (ISO weekday: 1=월 ... 7=일)
_REPEAT_PRESETS = {
    "none":     [],
    "daily":    [1, 2, 3, 4, 5, 6, 7],
    "weekdays": [1, 2, 3, 4, 5],
    "mwf":      [1, 3, 5],
}

# 진행/완료 콜백 타입
UploadResultCallback = Callable[[int, bool, str], None]  # (queue_id, success, message)


class CronRunner:
    """
    백그라운드에서 업로드 큐를 폴링하고 예약 업로드를 실행한다.

    사용법:
        runner = CronRunner()
        runner.start()
        ...
        runner.stop()
    """

    def __init__(
        self,
        poll_interval: int = _POLL_INTERVAL,
        on_upload_result: Optional[UploadResultCallback] = None,
    ) -> None:
        self._poll_interval = poll_interval
        self._on_upload_result = on_upload_result
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # 반복 스케줄 설정
        self._repeat_mode: str = "none"     # "none" | "daily" | "mwf" | "weekdays" | "custom"
        self._repeat_days: list[int] = []   # ISO weekday 목록 (custom일 때 사용)
        self._upload_time: str = "09:00"    # HH:MM 형식

    # ─────────────────────────────────────────────
    # 스레드 제어
    # ─────────────────────────────────────────────

    def start(self) -> None:
        """백그라운드 폴링 스레드를 시작한다."""
        if self._thread and self._thread.is_alive():
            logger.warning("CronRunner가 이미 실행 중입니다")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("CronRunner 시작 (간격=%d초)", self._poll_interval)

    def stop(self) -> None:
        """백그라운드 폴링 스레드를 중지한다."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
        logger.info("CronRunner 중지")

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ─────────────────────────────────────────────
    # 스케줄 설정
    # ─────────────────────────────────────────────

    def set_repeat(self, mode: str, upload_time: str = "09:00", custom_days: Optional[list[int]] = None) -> None:
        """
        반복 업로드 스케줄을 설정한다.

        mode:         "none" | "daily" | "mwf" | "weekdays" | "custom"
        upload_time:  업로드 시간 (HH:MM)
        custom_days:  mode="custom"일 때 요일 목록 (ISO weekday: 1=월 ... 7=일)
        """
        self._repeat_mode = mode
        self._upload_time = upload_time

        if mode == "custom" and custom_days:
            self._repeat_days = sorted(set(custom_days))
        elif mode in _REPEAT_PRESETS:
            self._repeat_days = _REPEAT_PRESETS[mode]
        else:
            self._repeat_days = []

        logger.info(
            "반복 스케줄 설정: mode=%s, time=%s, days=%s",
            mode, upload_time, self._repeat_days,
        )

    def get_schedule_info(self) -> dict:
        """현재 스케줄 설정 정보를 반환한다."""
        return {
            "repeat_mode": self._repeat_mode,
            "upload_time": self._upload_time,
            "repeat_days": self._repeat_days,
            "is_running": self.is_running(),
        }

    def next_upload_time(self) -> Optional[str]:
        """다음 업로드 예정 시간을 ISO 형식으로 반환한다. 없으면 None."""
        if self._repeat_mode == "none" or not self._repeat_days:
            return None

        now = datetime.now()
        hour, minute = map(int, self._upload_time.split(":"))

        for day_offset in range(8):  # 최대 7일 앞까지 탐색
            target = now + timedelta(days=day_offset)
            target = target.replace(hour=hour, minute=minute, second=0, microsecond=0)

            if target <= now:
                continue

            if target.isoweekday() in self._repeat_days:
                return target.isoformat()

        return None

    # ─────────────────────────────────────────────
    # 폴링 루프
    # ─────────────────────────────────────────────

    def _run_loop(self) -> None:
        """메인 폴링 루프. stop_event가 설정될 때까지 반복한다."""
        while not self._stop_event.is_set():
            try:
                self._process_pending()
            except Exception as e:
                logger.error("CronRunner 폴링 오류: %s", e, exc_info=True)

            self._stop_event.wait(timeout=self._poll_interval)

    def _process_pending(self) -> None:
        """대기 중인 큐 항목을 확인하고 업로드를 실행한다."""
        from scheduler.upload_queue import get_pending, mark_uploading, mark_done, mark_failed

        pending = get_pending()
        if not pending:
            return

        logger.info("대기 항목 %d개 발견 — 업로드 시작", len(pending))

        for item in pending:
            if self._stop_event.is_set():
                break

            queue_id = item["id"]
            try:
                mark_uploading(queue_id)
                video_id = self._do_upload(item)
                mark_done(queue_id, video_id)
                self._notify_result(queue_id, True, f"업로드 완료 (video_id={video_id})")

            except Exception as e:
                error_msg = str(e)
                mark_failed(queue_id, error_msg)
                self._notify_result(queue_id, False, error_msg)
                logger.error("큐 [id=%d] 업로드 실패: %s", queue_id, e)

    def _do_upload(self, item: dict) -> str:
        """실제 업로드를 수행하고 video_id를 반환한다."""
        from uploader.youtube_uploader import upload_video

        metadata = item.get("metadata") or {}
        if not metadata and item.get("metadata_json"):
            metadata = json.loads(item["metadata_json"])

        video_id = upload_video(
            video_path=item["video_path"],
            thumbnail_path=item["thumbnail_path"],
            metadata=metadata,
            lang=item["lang"],
        )
        return video_id

    def _notify_result(self, queue_id: int, success: bool, message: str) -> None:
        """업로드 결과 콜백을 호출한다."""
        if self._on_upload_result:
            try:
                self._on_upload_result(queue_id, success, message)
            except Exception as e:
                logger.warning("결과 콜백 오류: %s", e)
