"""
image/style_anchor.py — 이미지 스타일 앵커 적용

모든 image_prompt 끝에 스타일 앵커를 추가한다.
이중 방어:
  1차: scenario 생성 시 GPT 시스템 프롬프트에 스타일 규칙 포함 (gpt_generator.py)
  2차: 이 모듈에서 코드 레벨로 스타일 앵커를 강제 추가
config.IMAGE_STYLE 값이 기본값이면 prompts/image_style_anchor.txt를 읽는다.
"""

import logging
from pathlib import Path
from typing import Optional

import config

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_ANCHOR_FILE = _PROMPTS_DIR / "image_style_anchor.txt"

_cached_anchor: Optional[str] = None


def get_style_anchor() -> str:
    """현재 설정된 스타일 앵커 문자열을 반환한다."""
    global _cached_anchor

    # 사용자가 설정 탭에서 스타일을 직접 변경한 경우 우선 적용
    if config.IMAGE_STYLE and config.IMAGE_STYLE != config.IMAGE_STYLE_DEFAULT:
        return config.IMAGE_STYLE

    # 파일 캐싱: 첫 호출 시에만 파일을 읽는다
    if _cached_anchor is None:
        if _ANCHOR_FILE.exists():
            _cached_anchor = _ANCHOR_FILE.read_text(encoding="utf-8").strip()
            logger.debug("스타일 앵커 파일 로드: %d자", len(_cached_anchor))
        else:
            _cached_anchor = config.IMAGE_STYLE_DEFAULT
            logger.warning("image_style_anchor.txt 없음 — config 기본값 사용")

    return _cached_anchor


def apply(prompt: str, style: Optional[str] = None) -> str:
    """
    image_prompt에 스타일 앵커를 추가한다.
    앵커의 첫 번째 키워드가 이미 prompt에 포함되어 있으면 중복 추가하지 않는다.

    Args:
        prompt: 원본 이미지 프롬프트 (영어)
        style:  커스텀 스타일 문자열. None이면 get_style_anchor() 사용.

    Returns:
        스타일 앵커가 적용된 프롬프트 문자열
    """
    anchor = style if style is not None else get_style_anchor()
    prompt = prompt.strip()

    if not prompt:
        logger.warning("빈 image_prompt — 스타일 앵커만 반환")
        return anchor

    # 앵커 첫 키워드 중복 방지 (대소문자 무시)
    first_keyword = anchor.split(",")[0].strip().lower()
    if first_keyword in prompt.lower():
        logger.debug("스타일 앵커 이미 포함됨 — 추가 스킵")
        return prompt

    separator = ", " if not prompt.endswith(",") else " "
    return prompt + separator + anchor


def invalidate_cache() -> None:
    """스타일 앵커 캐시를 초기화한다. 설정 탭에서 스타일 변경 후 호출."""
    global _cached_anchor
    _cached_anchor = None
    logger.debug("스타일 앵커 캐시 초기화")
