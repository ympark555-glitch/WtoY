"""
bgm/pixabay_fetcher.py — Pixabay BGM 검색 + 다운로드

Pixabay Music API로 키워드 검색 후 오디오 파일을 캐시 디렉터리에 다운로드한다.
동일 URL은 해시 기반 캐시 파일명으로 재다운로드를 방지한다.
"""

import hashlib
import logging
from pathlib import Path

import requests

import config

logger = logging.getLogger(__name__)

_PIXABAY_MUSIC_API = "https://pixabay.com/api/music/"
_REQUEST_TIMEOUT = 20


def search_tracks(keyword: str, per_page: int = 10) -> list[dict]:
    """
    Pixabay Music API로 키워드 검색, hits 목록을 반환한다.

    Args:
        keyword:  검색 키워드 (예: "dramatic intense")
        per_page: 반환 트랙 수 (최대 20)

    Returns:
        Pixabay API hits 목록. 실패 시 빈 리스트.
    """
    if not config.PIXABAY_API_KEY:
        logger.warning("PIXABAY_API_KEY 미설정 — BGM 검색 불가")
        return []

    params = {
        "key": config.PIXABAY_API_KEY,
        "q": keyword,
        "per_page": min(per_page, 20),
    }

    try:
        resp = requests.get(
            _PIXABAY_MUSIC_API,
            params=params,
            timeout=_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        hits = data.get("hits", [])
        logger.debug("Pixabay 검색 '%s': %d개 트랙", keyword, len(hits))
        return hits
    except Exception as e:
        logger.error("Pixabay API 검색 실패 (%s): %s", keyword, e)
        return []


def extract_audio_url(track: dict) -> str:
    """
    Pixabay track dict에서 오디오 다운로드 URL을 추출한다.

    Pixabay Music API 응답에서 오디오 URL 필드명이 변경될 수 있으므로
    여러 후보 키를 순서대로 시도한다.
    """
    candidates = [
        "audio",            # 오디오 객체 내 URL
        "preview_url",
        "download_url",
        "url",
    ]
    for key in candidates:
        val = track.get(key)
        if isinstance(val, dict):
            # 중첩 dict인 경우 내부에서 URL 재탐색
            for sub_key in ("url", "download_url", "preview_url"):
                inner = val.get(sub_key, "")
                if isinstance(inner, str) and inner.startswith("http"):
                    return inner
        elif isinstance(val, str) and val.startswith("http"):
            return val
    return ""


def fetch_bgm(url: str, cache_dir: Path) -> Path:
    """
    오디오 URL에서 MP3를 다운로드해 cache_dir에 저장한다.
    동일 URL은 캐시 파일을 재사용한다.
    다운로드 실패 시 무음 BGM 파일을 생성해 반환한다.

    Args:
        url:       Pixabay 오디오 다운로드 URL
        cache_dir: 캐시 디렉터리 Path

    Returns:
        다운로드된 오디오 파일 Path
    """
    cache_dir.mkdir(parents=True, exist_ok=True)

    if not url:
        logger.warning("BGM URL 없음 — 무음 파일 생성")
        return _create_silent_bgm(cache_dir)

    # URL MD5 해시로 캐시 파일명 결정
    url_hash = hashlib.md5(url.encode()).hexdigest()[:16]
    cache_path = cache_dir / f"bgm_{url_hash}.mp3"

    if cache_path.exists() and cache_path.stat().st_size > 0:
        logger.debug("BGM 캐시 사용: %s", cache_path.name)
        return cache_path

    logger.info("BGM 다운로드 중: %s", url)
    try:
        resp = requests.get(url, timeout=60, stream=True)
        resp.raise_for_status()

        with open(cache_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        logger.info("BGM 다운로드 완료: %s (%.1f KB)", cache_path.name, cache_path.stat().st_size / 1024)
        return cache_path

    except Exception as e:
        logger.error("BGM 다운로드 실패: %s", e)
        return _create_silent_bgm(cache_dir)


# ─────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────

def _create_silent_bgm(cache_dir: Path) -> Path:
    """
    5분 30초 무음 MP3를 생성해 반환한다.
    Pixabay API 실패 시 파이프라인이 중단되지 않도록 하는 안전망.
    pydub 미설치 시 빈 바이트로 대체.
    """
    silent_path = cache_dir / "silent_bgm.mp3"
    if silent_path.exists() and silent_path.stat().st_size > 0:
        return silent_path

    try:
        from pydub import AudioSegment
        duration_ms = 330 * 1000  # 5분 30초
        silent = AudioSegment.silent(duration=duration_ms)
        silent.export(str(silent_path), format="mp3", bitrate="64k")
        logger.info("무음 BGM 생성 완료: %s", silent_path.name)
    except Exception as e:
        logger.warning("pydub 미설치로 무음 BGM 생성 실패: %s — 빈 파일로 대체", e)
        silent_path.write_bytes(b"")

    return silent_path
