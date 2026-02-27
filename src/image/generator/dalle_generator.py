"""
image/generator/dalle_generator.py — DALL-E 3 이미지 생성

scene의 image_prompt를 받아 OpenAI DALL-E 3 API로 이미지를 생성하고
output_dir/scenes/scene_{id:04d}.png 로 저장한다.

응답 형식: b64_json (URL 만료 문제 없음, 요청 1회로 완결)
크기: 1024x1024 (비용 단가와 일치 — 영상 합성 시 리사이즈)
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


def generate_image(
    prompt: str,
    scene_id: int,
    output_dir: Path,
    cost_tracker: Optional[CostTracker] = None,
) -> Optional[Path]:
    """
    DALL-E 3로 이미지를 생성하고 PNG 파일로 저장한다.

    Args:
        prompt:       스타일 앵커가 적용된 이미지 프롬프트 (영어)
        scene_id:     저장 파일명에 사용할 장면 번호
        output_dir:   프로젝트 output 디렉토리 (output_dir/scenes/ 하위에 저장)
        cost_tracker: 비용 추적기

    Returns:
        저장된 이미지 Path, 실패 시 None
    """
    from openai import OpenAI

    client = OpenAI(api_key=config.OPENAI_API_KEY)

    scenes_dir = output_dir / "scenes"
    scenes_dir.mkdir(parents=True, exist_ok=True)
    save_path = scenes_dir / f"scene_{scene_id:04d}.png"

    # 이미 생성된 파일이 있으면 재사용 (체크포인트 재시작 시)
    if save_path.exists():
        logger.debug("scene %d 이미지 파일 이미 존재 — 건너뜀", scene_id)
        return save_path

    for attempt in range(1, _MAX_RETRIES + 1):
        logger.debug("DALL-E 3 시도 %d/%d — scene %d", attempt, _MAX_RETRIES, scene_id)
        try:
            response = client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                n=1,
                size="1024x1024",
                quality=config.IMAGE_QUALITY,
                response_format="b64_json",
            )
        except Exception as e:
            logger.error("DALL-E 3 API 오류 (scene %d, 시도 %d): %s", scene_id, attempt, e)
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
            logger.error("이미지 저장 실패 (scene %d): %s", scene_id, e)
            return None

        if cost_tracker:
            cost_tracker.add_dalle3(count=1)

        logger.info("DALL-E 3 완료: scene %d → %s", scene_id, save_path.name)
        return save_path

    return None
