"""
history/image_db.py — 이미지 캐시 DB 관리

image/cache_matcher.py가 유사도 검색/저장을 담당하고,
이 모듈은 DB의 상위 관리 기능을 제공한다:
  - 통계 조회 (총 캐시 수, 디스크 용량)
  - 전체 목록 조회/검색
  - 대량 정리/삭제
  - 제작 이력(history_id)과의 연결
"""

import logging
import sqlite3
from pathlib import Path
from typing import Optional

import config

logger = logging.getLogger(__name__)

_DB_PATH = config.IMAGE_CACHE_DB_PATH


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_columns() -> None:
    """
    image_cache 테이블에 관리용 컬럼이 없으면 추가한다.
    cache_matcher.py가 생성한 기본 스키마에 history_id, style 컬럼을 추가.
    """
    with _get_conn() as conn:
        # 기존 컬럼 확인
        cursor = conn.execute("PRAGMA table_info(image_cache)")
        columns = {row["name"] for row in cursor.fetchall()}

        if "history_id" not in columns:
            conn.execute("ALTER TABLE image_cache ADD COLUMN history_id INTEGER")
        if "style" not in columns:
            conn.execute("ALTER TABLE image_cache ADD COLUMN style TEXT DEFAULT ''")


# cache_matcher.py가 _init_db()로 테이블을 먼저 생성하므로
# import 시점에 컬럼 확장만 수행
try:
    _ensure_columns()
except Exception:
    pass  # 테이블이 아직 없을 수 있음 — cache_matcher 첫 사용 시 생성됨


# ─────────────────────────────────────────────
# 조회
# ─────────────────────────────────────────────

def get_all(limit: int = 200, offset: int = 0) -> list[dict]:
    """전체 캐시 이미지를 최신순으로 조회한다."""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM image_cache ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    return [dict(r) for r in rows]


def get_by_history(history_id: int) -> list[dict]:
    """특정 제작 이력에 연결된 캐시 이미지를 조회한다."""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM image_cache WHERE history_id = ? ORDER BY id ASC",
            (history_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def search_prompt(keyword: str, limit: int = 50) -> list[dict]:
    """프롬프트에 키워드가 포함된 캐시를 검색한다."""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM image_cache WHERE prompt LIKE ? ORDER BY created_at DESC LIMIT ?",
            (f"%{keyword}%", limit),
        ).fetchall()
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────
# 저장 (history_id 포함)
# ─────────────────────────────────────────────

def save_with_history(
    prompt: str,
    image_path: str,
    history_id: Optional[int] = None,
    style: str = "",
) -> int:
    """
    이미지를 캐시에 저장하면서 history_id로 제작 이력과 연결한다.

    반환: 생성된 캐시 레코드 id
    """
    with _get_conn() as conn:
        cursor = conn.execute(
            """INSERT INTO image_cache (prompt, image_path, history_id, style)
               VALUES (?, ?, ?, ?)""",
            (prompt.strip(), str(image_path), history_id, style),
        )
        cache_id = cursor.lastrowid
    logger.debug("이미지 캐시 저장 [id=%d, history=%s]: %s", cache_id, history_id, image_path)
    return cache_id


def link_to_history(cache_ids: list[int], history_id: int) -> None:
    """기존 캐시 항목들을 특정 제작 이력에 연결한다."""
    if not cache_ids:
        return
    placeholders = ",".join("?" * len(cache_ids))
    with _get_conn() as conn:
        conn.execute(
            f"UPDATE image_cache SET history_id = ? WHERE id IN ({placeholders})",
            [history_id] + cache_ids,
        )
    logger.debug("캐시 %d개 → history_id=%d 연결", len(cache_ids), history_id)


# ─────────────────────────────────────────────
# 통계
# ─────────────────────────────────────────────

def total_count() -> int:
    """전체 캐시 이미지 수."""
    with _get_conn() as conn:
        row = conn.execute("SELECT COUNT(*) as cnt FROM image_cache").fetchone()
    return row["cnt"]


def total_disk_usage_mb() -> float:
    """
    캐시 이미지 파일의 총 디스크 사용량 (MB).
    존재하지 않는 파일은 제외한다.
    """
    with _get_conn() as conn:
        rows = conn.execute("SELECT image_path FROM image_cache").fetchall()

    total_bytes = 0
    for row in rows:
        p = Path(row["image_path"])
        if p.exists():
            total_bytes += p.stat().st_size

    return total_bytes / (1024 * 1024)


def reuse_stats() -> dict:
    """
    이미지 재사용 통계를 반환한다.

    반환:
        {
            "total_cached": int,
            "total_disk_mb": float,
            "unique_prompts": int,
            "reusable": int  (2회 이상 유사 프롬프트가 있는 이미지 수),
        }
    """
    with _get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) as cnt FROM image_cache").fetchone()["cnt"]
        unique = conn.execute("SELECT COUNT(DISTINCT prompt) as cnt FROM image_cache").fetchone()["cnt"]

    return {
        "total_cached": total,
        "total_disk_mb": total_disk_usage_mb(),
        "unique_prompts": unique,
        "reusable": max(0, total - unique),
    }


# ─────────────────────────────────────────────
# 정리
# ─────────────────────────────────────────────

def clear_missing() -> int:
    """
    파일이 존재하지 않는 캐시 항목을 삭제한다.
    image/cache_matcher.py의 clear_missing()과 동일 로직이지만
    관리 UI에서 호출할 수 있도록 이쪽에도 제공한다.

    반환: 삭제된 항목 수
    """
    with _get_conn() as conn:
        rows = conn.execute("SELECT id, image_path FROM image_cache").fetchall()

    missing_ids = [row["id"] for row in rows if not Path(row["image_path"]).exists()]
    if not missing_ids:
        return 0

    placeholders = ",".join("?" * len(missing_ids))
    with _get_conn() as conn:
        conn.execute(
            f"DELETE FROM image_cache WHERE id IN ({placeholders})",
            missing_ids,
        )
    logger.info("캐시 정리: %d개 항목 삭제 (파일 누락)", len(missing_ids))
    return len(missing_ids)


def clear_all() -> int:
    """전체 캐시 DB를 초기화한다. 이미지 파일은 삭제하지 않는다."""
    with _get_conn() as conn:
        cursor = conn.execute("DELETE FROM image_cache")
        count = cursor.rowcount
    logger.info("캐시 전체 초기화: %d개 항목 삭제", count)
    return count


def delete_by_history(history_id: int) -> int:
    """특정 제작 이력에 연결된 캐시를 삭제한다. 파일은 삭제하지 않는다."""
    with _get_conn() as conn:
        cursor = conn.execute(
            "DELETE FROM image_cache WHERE history_id = ?", (history_id,)
        )
        count = cursor.rowcount
    logger.info("캐시 삭제 (history_id=%d): %d개 항목", history_id, count)
    return count
