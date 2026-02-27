"""
bgm/stage_selector.py — stage별 BGM 자동 선택

파이프라인 STEP 7에서 호출된다.
시나리오의 지배적 stage를 분석해 Pixabay에서 적절한 BGM을 선택하고
다운로드 URL을 반환한다.
"""

import logging
import random

import config

logger = logging.getLogger(__name__)


def select_bgm(stage: str) -> str:
    """
    stage에 맞는 BGM을 Pixabay에서 검색해 오디오 URL을 반환한다.

    BGM_STAGE_MAP 키워드로 검색 → hits에서 랜덤 선택 (다양성 확보).
    검색 실패 또는 결과 없을 시 빈 문자열 반환 (fetch_bgm이 무음으로 대체).

    Args:
        stage: "hook" | "problem" | "core" | "twist" | "cta"
               또는 지배적 stage 문자열

    Returns:
        Pixabay 오디오 다운로드 URL (실패 시 빈 문자열)
    """
    from bgm.pixabay_fetcher import search_tracks, extract_audio_url

    keyword = config.BGM_STAGE_MAP.get(stage, config.BGM_STAGE_MAP.get("core", "background music"))
    logger.info("BGM 검색 — stage: %s / 키워드: %s", stage, keyword)

    tracks = search_tracks(keyword)

    if not tracks:
        # 키워드 완화 재시도: 첫 번째 단어만 사용
        simple_keyword = keyword.split()[0] if keyword else "music"
        logger.info("검색 결과 없음 — 재시도: '%s'", simple_keyword)
        tracks = search_tracks(simple_keyword)

    if not tracks:
        logger.warning("BGM 검색 결과 없음 — 무음으로 대체됩니다")
        return ""

    # 상위 5개 중 랜덤 선택 (매번 같은 BGM 사용 방지)
    pool = tracks[:5]
    track = random.choice(pool)
    url = extract_audio_url(track)

    if not url:
        logger.warning("BGM URL 추출 실패 — track: %s", track)
        return ""

    track_id = track.get("id", "?")
    duration = track.get("duration", "?")
    logger.info("BGM 선택: id=%s, duration=%ss, url=%s...", track_id, duration, url[:60])
    return url
