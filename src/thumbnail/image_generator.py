"""
thumbnail/image_generator.py — DALL-E 3 썸네일 이미지 생성

썸네일 전용 DALL-E 3 호출:
  - 가로 영상용: 1792x1024 (YouTube 1280x720 비율에 가장 가까운 DALL-E 지원 사이즈)
  - 쇼츠용:      1024x1792 (YouTube Shorts 1080x1920 비율)

생성된 원본은 PNG로 저장되며, text_overlay.generate_all_thumbnails()에서
YouTube 표준 사이즈로 리사이즈 + 텍스트 합성된다.

저장 경로:
  output_dir/thumbnails/thumb_landscape_base.png
  output_dir/thumbnails/thumb_shorts_base.png
"""

import base64
import logging
import time
from pathlib import Path
from typing import Optional

import config
from core.cost_tracker import CostTracker

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_DELAY_SEC = 5

# DALL-E 3 지원 사이즈
_LANDSCAPE_SIZE = "1792x1024"
_SHORTS_SIZE = "1024x1792"

# 썸네일에 공통 적용할 스타일 보조 프롬프트
# "no text in image"를 반복 명시해 DALL-E가 텍스트를 그리지 않도록 강제
_STYLE_SUFFIX = (
    ", YouTube thumbnail style, dramatic lighting, "
    "bold composition, high visual impact, "
    "no text, no letters, no words in the image, "
    "professional illustration or editorial photography quality"
)


def generate_thumbnail_image(
    prompt: str,
    output_dir: Path,
    variant: str,
    cost_tracker: Optional[CostTracker] = None,
) -> Optional[Path]:
    """
    DALL-E 3로 썸네일 베이스 이미지를 생성하고 PNG로 저장한다.

    Args:
        prompt:       prompt_generator에서 생성된 image_prompt
        output_dir:   프로젝트 output 디렉토리 (output_dir/thumbnails/ 하위 저장)
        variant:      "landscape" (16:9) 또는 "shorts" (9:16)
        cost_tracker: 비용 추적기

    Returns:
        저장된 이미지 Path, 실패 시 None
    """
    if variant not in ("landscape", "shorts"):
        raise ValueError(f"variant는 'landscape' 또는 'shorts'여야 합니다: {variant!r}")

    from openai import OpenAI

    client = OpenAI(api_key=config.OPENAI_API_KEY)
    size = _LANDSCAPE_SIZE if variant == "landscape" else _SHORTS_SIZE

    thumbnails_dir = output_dir / "thumbnails"
    thumbnails_dir.mkdir(parents=True, exist_ok=True)
    save_path = thumbnails_dir / f"thumb_{variant}_base.png"

    # 이미 생성된 베이스 이미지가 있으면 재사용 (체크포인트 재시작 시)
    if save_path.exists():
        logger.debug("썸네일 베이스 이미지 이미 존재 (%s) — 건너뜀", variant)
        return save_path

    full_prompt = prompt.rstrip() + _STYLE_SUFFIX

    for attempt in range(1, _MAX_RETRIES + 1):
        logger.debug("DALL-E 3 썸네일 시도 %d/%d — %s", attempt, _MAX_RETRIES, variant)
        try:
            response = client.images.generate(
                model="dall-e-3",
                prompt=full_prompt,
                n=1,
                size=size,
                quality=config.IMAGE_QUALITY,
                response_format="b64_json",
            )
        except Exception as e:
            logger.error("DALL-E 3 썸네일 API 오류 (%s, 시도 %d): %s", variant, attempt, e)
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_DELAY_SEC * attempt)
                continue
            return None

        try:
            b64_data = response.data[0].b64_json
            if not b64_data:
                raise ValueError("b64_json 응답이 비어 있음")
            img_bytes = base64.b64decode(b64_data)
            save_path.write_bytes(img_bytes)
        except Exception as e:
            logger.error("썸네일 이미지 저장 실패 (%s): %s", variant, e)
            return None

        if cost_tracker:
            cost_tracker.add_dalle3(count=1)

        logger.info("DALL-E 3 썸네일 완료: %s → %s", variant, save_path.name)
        return save_path

    return None


def generate_both_base_images(
    prompt: str,
    output_dir: Path,
    cost_tracker: Optional[CostTracker] = None,
) -> dict[str, Optional[Path]]:
    """
    landscape + shorts 베이스 이미지를 연속으로 생성한다.

    Returns:
        {"landscape": Path | None, "shorts": Path | None}
    """
    results: dict[str, Optional[Path]] = {}
    for variant in ("landscape", "shorts"):
        results[variant] = generate_thumbnail_image(
            prompt=prompt,
            output_dir=output_dir,
            variant=variant,
            cost_tracker=cost_tracker,
        )
    return results
