"""
image/cache_matcher.py — 유사 이미지 검색 및 재사용 판단

SQLite image_cache.db에 생성된 이미지 이력을 저장하고,
새 image_prompt와 기존 이력을 비교해 유사도 임계값 이상인 이미지를 반환한다.

유사도 계산: Jaccard similarity (단어 집합 교집합 / 합집합)
- 외부 라이브러리 없이 동작
- 2글자 이하 단어, 콤마/마침표 등은 토큰화 시 제거
"""

import logging
import sqlite3
from pathlib import Path
from typing import Optional

import config

logger = logging.getLogger(__name__)

_DB_PATH = config.IMAGE_CACHE_DB_PATH
_STOP_CHARS = str.maketrans("", "", ".,;:()[]\"'")


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    """테이블 및 인덱스를 초기화한다. 모듈 최초 로드 시 1회 실행."""
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS image_cache (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                prompt      TEXT    NOT NULL,
                image_path  TEXT    NOT NULL,
                created_at  TEXT    DEFAULT (datetime('now'))
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_created ON image_cache(created_at)"
        )


# 모듈 로드 시 DB 초기화
_init_db()


# ─────────────────────────────────────────────
# 공개 API
# ─────────────────────────────────────────────

def save(prompt: str, image_path: str | Path) -> None:
    """생성된 이미지 정보를 캐시 DB에 저장한다."""
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO image_cache (prompt, image_path) VALUES (?, ?)",
            (prompt.strip(), str(image_path)),
        )
    logger.debug("이미지 캐시 저장: %s", image_path)


def find_similar(
    prompt: str,
    threshold: Optional[float] = None,
    limit: int = 5,
) -> list[dict]:
    """
    저장된 이미지 중 Jaccard 유사도가 threshold 이상인 항목을 반환한다.

    Args:
        prompt:    비교할 새 이미지 프롬프트
        threshold: 유사도 기준 (None이면 config.IMAGE_SIMILARITY_THRESHOLD 사용)
        limit:     반환할 최대 항목 수

    Returns:
        유사한 항목 list — 각 항목은 {"similarity", "image_path", "prompt"}
        similarity 내림차순 정렬
    """
    threshold = threshold if threshold is not None else config.IMAGE_SIMILARITY_THRESHOLD
    prompt_words = _tokenize(prompt)

    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT prompt, image_path FROM image_cache ORDER BY created_at DESC"
        ).fetchall()

    if not rows:
        return []

    results: list[dict] = []
    for row in rows:
        cached_path = row["image_path"]
        if not Path(cached_path).exists():
            continue

        similarity = _jaccard(prompt_words, _tokenize(row["prompt"]))
        if similarity >= threshold:
            results.append({
                "similarity": similarity,
                "image_path": cached_path,
                "prompt": row["prompt"],
            })

    results.sort(key=lambda x: x["similarity"], reverse=True)
    results = results[:limit]

    if results:
        logger.info(
            "유사 이미지 %d개 발견 (최고 유사도=%.1f%%)",
            len(results), results[0]["similarity"] * 100,
        )
    return results


def clear_missing() -> int:
    """존재하지 않는 파일의 캐시 항목을 정리한다. 정리된 건수를 반환."""
    with _get_conn() as conn:
        rows = conn.execute("SELECT id, image_path FROM image_cache").fetchall()

    missing_ids = [row["id"] for row in rows if not Path(row["image_path"]).exists()]
    if not missing_ids:
        return 0

    with _get_conn() as conn:
        conn.execute(
            f"DELETE FROM image_cache WHERE id IN ({','.join('?' * len(missing_ids))})",
            missing_ids,
        )
    logger.info("캐시 정리: %d개 항목 삭제", len(missing_ids))
    return len(missing_ids)


# ─────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────

def _tokenize(text: str) -> frozenset[str]:
    """텍스트를 소문자 단어 집합으로 변환한다. 2글자 이하 단어는 제거."""
    cleaned = text.translate(_STOP_CHARS)
    return frozenset(w.lower() for w in cleaned.split() if len(w) > 2)


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    """두 단어 집합의 Jaccard 유사도를 계산한다."""
    if not a or not b:
        return 0.0
    union = len(a | b)
    return len(a & b) / union if union > 0 else 0.0
