"""
image/generator/sd_generator.py — Stable Diffusion WebUI API 이미지 생성

Automatic1111 WebUI의 /sdapi/v1/txt2img 엔드포인트를 사용해
로컬에서 이미지를 생성한다. config.SD_API_URL에 서버 주소를 설정한다.

기본 포트: http://localhost:7860
WebUI 실행 옵션: --api 플래그 필요 (python launch.py --api)
"""

import base64
import logging
import time
from pathlib import Path
from typing import Optional

import config

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_DELAY_SEC = 5

# SD WebUI 기본 생성 파라미터
# 영상 장면 이미지는 16:9(1024×576) 권장 — 합성 시 crop/resize 처리
_SD_PAYLOAD_DEFAULTS: dict = {
    "steps": 25,
    "cfg_scale": 7.5,
    "width": 1024,
    "height": 576,
    "sampler_name": "DPM++ 2M Karras",
    "negative_prompt": (
        "ugly, blurry, low quality, watermark, text, signature, "
        "nsfw, violence, gore, real person, photograph, photorealistic"
    ),
    "restore_faces": False,
    "tiling": False,
}


def generate_image(
    prompt: str,
    scene_id: int,
    output_dir: Path,
) -> Optional[Path]:
    """
    Stable Diffusion WebUI API로 이미지를 생성하고 PNG로 저장한다.

    Args:
        prompt:     스타일 앵커가 적용된 이미지 프롬프트 (영어)
        scene_id:   저장 파일명에 사용할 장면 번호
        output_dir: 프로젝트 output 디렉토리 (output_dir/scenes/ 하위에 저장)

    Returns:
        저장된 이미지 Path, 실패 시 None
    """
    import requests

    scenes_dir = output_dir / "scenes"
    scenes_dir.mkdir(parents=True, exist_ok=True)
    save_path = scenes_dir / f"scene_{scene_id:04d}.png"

    if save_path.exists():
        logger.debug("scene %d 이미지 파일 이미 존재 — 건너뜀", scene_id)
        return save_path

    url = f"{config.SD_API_URL.rstrip('/')}/sdapi/v1/txt2img"
    payload = {**_SD_PAYLOAD_DEFAULTS, "prompt": prompt}

    for attempt in range(1, _MAX_RETRIES + 1):
        logger.debug("SD 시도 %d/%d — scene %d", attempt, _MAX_RETRIES, scene_id)
        try:
            resp = requests.post(url, json=payload, timeout=120)
            resp.raise_for_status()
        except Exception as e:
            logger.error("SD API 오류 (scene %d, 시도 %d): %s", scene_id, attempt, e)
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_DELAY_SEC * attempt)
                continue
            return None

        try:
            data = resp.json()
            img_b64 = data["images"][0]
            save_path.write_bytes(base64.b64decode(img_b64))
        except Exception as e:
            logger.error("SD 이미지 저장 실패 (scene %d): %s", scene_id, e)
            return None

        logger.info("SD 완료: scene %d → %s", scene_id, save_path.name)
        return save_path

    return None


def check_server() -> bool:
    """SD WebUI 서버가 응답 가능한지 확인한다. 파이프라인 시작 전 호출."""
    import requests
    try:
        resp = requests.get(
            f"{config.SD_API_URL.rstrip('/')}/sdapi/v1/options",
            timeout=5,
        )
        return resp.status_code == 200
    except Exception:
        return False
