"""
scraper/language_detector.py — 한/영 언어 감지
1차: 한국어 문자 비율 휴리스틱 (빠르고 안정적)
2차: langdetect 라이브러리 (다국어 대응)
감지 실패 시 "en" 반환.
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# 한국어 유니코드 범위 (한글 음절, 자모, 호환 자모)
_KO_PATTERN = re.compile(
    r"[\uac00-\ud7a3"   # 한글 음절 (가~힣)
    r"\u1100-\u11ff"    # 한글 자모
    r"\u3131-\u318e]"   # 한글 호환 자모
)

# 한국어 문자 비율이 이 값 이상이면 langdetect 없이 바로 "ko" 반환
_KO_FAST_THRESHOLD = 0.30

# langdetect 신뢰도가 이 값 미만이면 휴리스틱으로 재판단
_MIN_CONFIDENCE = 0.80

# langdetect 샘플 길이 (속도 최적화, 앞부분이 언어 판단에 충분)
_SAMPLE_LENGTH = 3_000


def detect_language(text: str) -> str:
    """
    텍스트 언어를 감지하고 ISO 639-1 코드를 반환한다.

    Args:
        text: 언어를 감지할 텍스트

    Returns:
        언어 코드 (예: "ko", "en", "ja", ...)
        텍스트가 너무 짧거나 감지 실패 시 "en" 반환
    """
    if not text or len(text.strip()) < 10:
        logger.warning("텍스트 부족 (%d자) — 기본값 'en' 사용", len(text) if text else 0)
        return "en"

    # 1차: 한국어 문자 비율 휴리스틱
    ko_ratio = _korean_char_ratio(text)
    if ko_ratio >= _KO_FAST_THRESHOLD:
        logger.info("한국어 문자 비율 %.1f%% — 'ko' 확정", ko_ratio * 100)
        return "ko"

    # 2차: langdetect
    lang = _detect_with_langdetect(text, ko_ratio)
    logger.info("최종 감지 언어: '%s' (한국어 비율: %.1f%%)", lang, ko_ratio * 100)
    return lang


# ─────────────────────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────────────────────

def _korean_char_ratio(text: str) -> float:
    """공백 제외 전체 문자 대비 한국어 문자 비율을 반환한다."""
    no_space = re.sub(r"\s", "", text)
    if not no_space:
        return 0.0
    ko_count = len(_KO_PATTERN.findall(no_space))
    return ko_count / len(no_space)


def _detect_with_langdetect(text: str, ko_ratio: float) -> str:
    """
    langdetect로 언어를 감지한다.
    langdetect 미설치 또는 감지 실패 시 휴리스틱 결과를 사용한다.
    """
    try:
        from langdetect import detect_langs
        from langdetect import DetectorFactory
        DetectorFactory.seed = 0   # BUG-06 FIX: 동일 텍스트에 항상 동일 결과 보장
    except ImportError:
        logger.warning("langdetect 미설치 — 한국어 비율(%.1f%%)로 판단", ko_ratio * 100)
        return "ko" if ko_ratio >= 0.10 else "en"

    sample = text[:_SAMPLE_LENGTH] if len(text) > _SAMPLE_LENGTH else text

    try:
        langs = detect_langs(sample)
    except Exception as e:
        logger.warning("langdetect 감지 오류: %s — 한국어 비율로 폴백", e)
        return "ko" if ko_ratio >= 0.10 else "en"

    if not langs:
        logger.warning("langdetect 결과 없음 — 기본값 'en'")
        return "en"

    best = langs[0]
    logger.debug(
        "langdetect 결과: %s (신뢰도: %.2f) [전체: %s]",
        best.lang, best.prob,
        ", ".join(f"{l.lang}:{l.prob:.2f}" for l in langs),
    )

    if best.prob >= _MIN_CONFIDENCE:
        return best.lang

    # 신뢰도 낮음 → 한국어 비율로 재판단
    logger.warning(
        "낮은 신뢰도 (%.2f < %.2f), 한국어 비율(%.1f%%)로 재판단",
        best.prob, _MIN_CONFIDENCE, ko_ratio * 100,
    )
    if ko_ratio >= 0.10:
        return "ko"
    return best.lang
