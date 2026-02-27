"""
history/history_manager.py — 히스토리 저장/조회

영상 제작 이력을 SQLite에 기록한다.
제목, URL, 날짜, 이미지 장수, 비용, 업로드 상태 등을 관리하며
히스토리 탭 및 통계 탭에서 활용된다.
"""

import json
import logging
import sqlite3
from typing import Optional

import config

logger = logging.getLogger(__name__)

_DB_PATH = config.HISTORY_DB_PATH


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    """history 테이블을 초기화한다."""
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                url             TEXT    NOT NULL,
                title_ko        TEXT,
                title_en        TEXT,
                page_lang       TEXT,
                scene_count     INTEGER DEFAULT 0,
                image_count     INTEGER DEFAULT 0,
                reused_images   INTEGER DEFAULT 0,
                cost_usd        REAL    DEFAULT 0.0,
                cost_breakdown  TEXT,
                output_dir      TEXT,
                upload_status   TEXT    DEFAULT 'not_uploaded',
                video_ids       TEXT,
                created_at      TEXT    DEFAULT (datetime('now')),
                updated_at      TEXT    DEFAULT (datetime('now'))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_history_created ON history(created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_history_title ON history(title_ko)")


_init_db()


# ─────────────────────────────────────────────
# 기록 추가
# ─────────────────────────────────────────────

def add_record(
    url: str,
    title_ko: str = "",
    title_en: str = "",
    page_lang: str = "",
    scene_count: int = 0,
    image_count: int = 0,
    reused_images: int = 0,
    cost_usd: float = 0.0,
    cost_breakdown: Optional[dict] = None,
    output_dir: str = "",
) -> int:
    """
    새 제작 이력을 추가한다. 반환: 생성된 record id.
    """
    breakdown_json = json.dumps(cost_breakdown or {}, ensure_ascii=False)
    with _get_conn() as conn:
        cursor = conn.execute(
            """INSERT INTO history
               (url, title_ko, title_en, page_lang, scene_count,
                image_count, reused_images, cost_usd, cost_breakdown, output_dir)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (url, title_ko, title_en, page_lang, scene_count,
             image_count, reused_images, cost_usd, breakdown_json, output_dir),
        )
        record_id = cursor.lastrowid
    logger.info("히스토리 추가 [id=%d] %s", record_id, title_ko)
    return record_id


def add_from_pipeline(state: dict, cost_tracker) -> int:
    """
    pipeline.state와 cost_tracker에서 직접 히스토리를 생성한다.
    파이프라인 완료 후 호출하기 편리한 래퍼.
    """
    scenario = state.get("scenario_ko") or []
    return add_record(
        url=state.get("url", ""),
        title_ko=state.get("youtube_title_ko", ""),
        title_en=state.get("youtube_title_en", ""),
        page_lang=state.get("page_lang", ""),
        scene_count=len(scenario),
        image_count=len(state.get("image_paths", [])),
        cost_usd=cost_tracker.total_usd(),
        cost_breakdown=cost_tracker.breakdown(),
        output_dir=state.get("output_dir", ""),
    )


# ─────────────────────────────────────────────
# 조회
# ─────────────────────────────────────────────

def get_all(limit: int = 100, offset: int = 0) -> list[dict]:
    """전체 이력을 최신순으로 조회한다."""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM history ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_by_id(record_id: int) -> Optional[dict]:
    """특정 이력을 조회한다."""
    with _get_conn() as conn:
        row = conn.execute("SELECT * FROM history WHERE id = ?", (record_id,)).fetchone()
    return _row_to_dict(row) if row else None


def search(keyword: str, limit: int = 50) -> list[dict]:
    """제목 또는 URL에 키워드가 포함된 이력을 검색한다."""
    pattern = f"%{keyword}%"
    with _get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM history
               WHERE title_ko LIKE ? OR title_en LIKE ? OR url LIKE ?
               ORDER BY created_at DESC LIMIT ?""",
            (pattern, pattern, pattern, limit),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_by_month(year: int, month: int) -> list[dict]:
    """특정 월의 이력을 조회한다."""
    month_str = f"{year:04d}-{month:02d}"
    with _get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM history
               WHERE created_at LIKE ?
               ORDER BY created_at DESC""",
            (f"{month_str}%",),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


# ─────────────────────────────────────────────
# 업데이트
# ─────────────────────────────────────────────

def update_upload_status(record_id: int, status: str, video_ids: Optional[dict] = None) -> None:
    """
    업로드 상태를 변경한다.
    status: "not_uploaded" | "partial" | "uploaded"
    video_ids: {"landscape_ko": "xxx", "landscape_en": "xxx", ...}
    """
    ids_json = json.dumps(video_ids or {}, ensure_ascii=False) if video_ids else None
    with _get_conn() as conn:
        if ids_json:
            conn.execute(
                """UPDATE history
                   SET upload_status = ?, video_ids = ?, updated_at = datetime('now')
                   WHERE id = ?""",
                (status, ids_json, record_id),
            )
        else:
            conn.execute(
                """UPDATE history
                   SET upload_status = ?, updated_at = datetime('now')
                   WHERE id = ?""",
                (status, record_id),
            )
    logger.info("히스토리 업로드 상태 변경 [id=%d] → %s", record_id, status)


def update_reused_images(record_id: int, count: int) -> None:
    """재사용 이미지 수를 업데이트한다."""
    with _get_conn() as conn:
        conn.execute(
            "UPDATE history SET reused_images = ?, updated_at = datetime('now') WHERE id = ?",
            (count, record_id),
        )


# ─────────────────────────────────────────────
# 삭제
# ─────────────────────────────────────────────

def delete_record(record_id: int) -> None:
    """이력을 삭제한다. output_dir의 파일은 삭제하지 않는다."""
    with _get_conn() as conn:
        conn.execute("DELETE FROM history WHERE id = ?", (record_id,))
    logger.info("히스토리 삭제 [id=%d]", record_id)


# ─────────────────────────────────────────────
# 통계
# ─────────────────────────────────────────────

def total_count() -> int:
    """전체 제작 이력 수."""
    with _get_conn() as conn:
        row = conn.execute("SELECT COUNT(*) as cnt FROM history").fetchone()
    return row["cnt"]


def total_cost() -> float:
    """전체 누적 비용 (USD)."""
    with _get_conn() as conn:
        row = conn.execute("SELECT COALESCE(SUM(cost_usd), 0.0) as total FROM history").fetchone()
    return row["total"]


def monthly_cost(year: int, month: int) -> float:
    """특정 월의 비용 합계 (USD)."""
    month_str = f"{year:04d}-{month:02d}"
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0.0) as total FROM history WHERE created_at LIKE ?",
            (f"{month_str}%",),
        ).fetchone()
    return row["total"]


def total_reused_images() -> int:
    """전체 재사용 이미지 수."""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(reused_images), 0) as total FROM history"
        ).fetchone()
    return row["total"]


# ─────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────

def _row_to_dict(row: sqlite3.Row) -> dict:
    """sqlite3.Row를 dict로 변환하고 JSON 필드를 파싱한다."""
    d = dict(row)
    for json_field in ("cost_breakdown", "video_ids"):
        if d.get(json_field):
            try:
                d[json_field] = json.loads(d[json_field])
            except json.JSONDecodeError:
                d[json_field] = {}
    return d
