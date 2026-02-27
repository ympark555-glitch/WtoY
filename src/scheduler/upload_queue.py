"""
scheduler/upload_queue.py — 업로드 큐 관리

SQLite 기반으로 업로드 대기 항목을 관리한다.
영상 제작 완료 후 즉시 업로드하지 않고 큐에 추가하면,
cron_runner가 예약된 시간에 업로드를 실행한다.
"""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

import config

logger = logging.getLogger(__name__)

_DB_PATH = config.HISTORY_DB_PATH  # history.db를 공유 (테이블 분리)


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    """upload_queue 테이블을 초기화한다."""
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS upload_queue (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                video_path      TEXT    NOT NULL,
                thumbnail_path  TEXT    NOT NULL,
                metadata_json   TEXT    NOT NULL,
                lang            TEXT    NOT NULL DEFAULT 'ko',
                status          TEXT    NOT NULL DEFAULT 'pending',
                scheduled_at    TEXT,
                created_at      TEXT    DEFAULT (datetime('now')),
                uploaded_at     TEXT,
                video_id        TEXT,
                error_message   TEXT
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_queue_status ON upload_queue(status)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_queue_scheduled ON upload_queue(scheduled_at)"
        )


_init_db()


# ─────────────────────────────────────────────
# 큐 항목 추가
# ─────────────────────────────────────────────

def enqueue(
    video_path: str,
    thumbnail_path: str,
    metadata: dict,
    lang: str = "ko",
    scheduled_at: Optional[str] = None,
) -> int:
    """
    업로드 큐에 항목을 추가한다.

    video_path:     업로드할 .mp4 파일 경로
    thumbnail_path: 썸네일 .jpg 파일 경로
    metadata:       metadata_builder.build_metadata() 반환값
    lang:           "ko" | "en"
    scheduled_at:   예약 시간 (ISO 형식, None이면 즉시 업로드 대상)
    반환: 생성된 큐 항목 id
    """
    metadata_json = json.dumps(metadata, ensure_ascii=False)
    with _get_conn() as conn:
        cursor = conn.execute(
            """INSERT INTO upload_queue
               (video_path, thumbnail_path, metadata_json, lang, scheduled_at)
               VALUES (?, ?, ?, ?, ?)""",
            (video_path, thumbnail_path, metadata_json, lang, scheduled_at),
        )
        queue_id = cursor.lastrowid
    logger.info("큐 추가 [id=%d] %s (%s)", queue_id, Path(video_path).name, lang)
    return queue_id


def enqueue_batch(items: list[dict]) -> list[int]:
    """
    여러 항목을 한 번에 큐에 추가한다.

    items: [{"video_path", "thumbnail_path", "metadata", "lang", "scheduled_at"(선택)}]
    반환: 생성된 큐 항목 id 목록
    """
    ids: list[int] = []
    for item in items:
        qid = enqueue(
            video_path=item["video_path"],
            thumbnail_path=item["thumbnail_path"],
            metadata=item["metadata"],
            lang=item.get("lang", "ko"),
            scheduled_at=item.get("scheduled_at"),
        )
        ids.append(qid)
    return ids


# ─────────────────────────────────────────────
# 큐 조회
# ─────────────────────────────────────────────

def get_pending(limit: int = 50) -> list[dict]:
    """
    업로드 대기 중인 항목을 반환한다.
    scheduled_at이 현재 시간 이전이거나 NULL인 항목만 대상.
    """
    now = datetime.now().isoformat()
    with _get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM upload_queue
               WHERE status = 'pending'
                 AND (scheduled_at IS NULL OR scheduled_at <= ?)
               ORDER BY scheduled_at ASC, created_at ASC
               LIMIT ?""",
            (now, limit),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_all(status: Optional[str] = None) -> list[dict]:
    """전체 큐 항목을 조회한다. status로 필터링 가능."""
    with _get_conn() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM upload_queue WHERE status = ? ORDER BY created_at DESC",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM upload_queue ORDER BY created_at DESC"
            ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_by_id(queue_id: int) -> Optional[dict]:
    """특정 큐 항목을 조회한다."""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM upload_queue WHERE id = ?", (queue_id,)
        ).fetchone()
    return _row_to_dict(row) if row else None


# ─────────────────────────────────────────────
# 상태 변경
# ─────────────────────────────────────────────

def mark_uploading(queue_id: int) -> None:
    """업로드 시작 상태로 변경한다."""
    with _get_conn() as conn:
        conn.execute(
            "UPDATE upload_queue SET status = 'uploading' WHERE id = ?",
            (queue_id,),
        )


def mark_done(queue_id: int, video_id: str) -> None:
    """업로드 완료 상태로 변경한다."""
    with _get_conn() as conn:
        conn.execute(
            """UPDATE upload_queue
               SET status = 'done', video_id = ?, uploaded_at = datetime('now')
               WHERE id = ?""",
            (video_id, queue_id),
        )
    logger.info("큐 완료 [id=%d] video_id=%s", queue_id, video_id)


def mark_failed(queue_id: int, error: str) -> None:
    """업로드 실패 상태로 변경한다."""
    with _get_conn() as conn:
        conn.execute(
            "UPDATE upload_queue SET status = 'failed', error_message = ? WHERE id = ?",
            (error, queue_id),
        )
    logger.warning("큐 실패 [id=%d] %s", queue_id, error)


def retry(queue_id: int) -> None:
    """실패한 항목을 다시 pending 상태로 되돌린다."""
    with _get_conn() as conn:
        conn.execute(
            "UPDATE upload_queue SET status = 'pending', error_message = NULL WHERE id = ?",
            (queue_id,),
        )
    logger.info("큐 재시도 [id=%d]", queue_id)


def cancel(queue_id: int) -> None:
    """대기 중인 항목을 취소한다."""
    with _get_conn() as conn:
        conn.execute(
            "UPDATE upload_queue SET status = 'cancelled' WHERE id = ?",
            (queue_id,),
        )
    logger.info("큐 취소 [id=%d]", queue_id)


def remove(queue_id: int) -> None:
    """큐 항목을 삭제한다."""
    with _get_conn() as conn:
        conn.execute("DELETE FROM upload_queue WHERE id = ?", (queue_id,))
    logger.info("큐 삭제 [id=%d]", queue_id)


# ─────────────────────────────────────────────
# 예약 시간 변경
# ─────────────────────────────────────────────

def reschedule(queue_id: int, scheduled_at: str) -> None:
    """큐 항목의 예약 시간을 변경한다. ISO 형식 문자열."""
    with _get_conn() as conn:
        conn.execute(
            "UPDATE upload_queue SET scheduled_at = ? WHERE id = ?",
            (scheduled_at, queue_id),
        )
    logger.info("큐 예약 변경 [id=%d] → %s", queue_id, scheduled_at)


# ─────────────────────────────────────────────
# 통계
# ─────────────────────────────────────────────

def count_by_status() -> dict[str, int]:
    """상태별 큐 항목 수를 반환한다."""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM upload_queue GROUP BY status"
        ).fetchall()
    return {row["status"]: row["cnt"] for row in rows}


# ─────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────

def _row_to_dict(row: sqlite3.Row) -> dict:
    """sqlite3.Row를 dict로 변환하고 metadata_json을 파싱한다."""
    d = dict(row)
    if d.get("metadata_json"):
        try:
            d["metadata"] = json.loads(d["metadata_json"])
        except json.JSONDecodeError:
            d["metadata"] = {}
    return d
