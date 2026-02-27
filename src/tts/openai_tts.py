"""
tts/openai_tts.py — OpenAI TTS 음성 생성

각 씬의 narration을 OpenAI TTS API(tts-1)로 변환해 MP3로 저장한다.
이미 생성된 파일은 재사용해 API 비용을 절약한다.
"""

import logging
from pathlib import Path
from typing import Optional

import config
from core.cost_tracker import CostTracker

logger = logging.getLogger(__name__)


def synthesize(
    scenes: list[dict],
    lang: str,
    output_dir: Path,
    cost_tracker: Optional[CostTracker] = None,
) -> list[Path]:
    """
    OpenAI TTS API로 씬별 narration을 MP3로 저장한다.

    Args:
        scenes:      scene dict 목록 (narration, scene_id 포함)
        lang:        "ko" 또는 "en"
        output_dir:  MP3 저장 디렉터리
        cost_tracker: 비용 추적기

    Returns:
        씬 순서에 맞는 Path 목록 (빈 narration → 빈 파일)
    """
    from openai import OpenAI

    client = OpenAI(api_key=config.OPENAI_API_KEY)
    voice = config.TTS_KO_VOICE if lang == "ko" else config.TTS_EN_VOICE
    paths: list[Path] = []

    for i, scene in enumerate(scenes):
        scene_id = scene.get("scene_id", i + 1)
        narration = scene.get("narration", "").strip()
        out_path = output_dir / f"scene_{scene_id:03d}.mp3"

        # narration 없음 → 빈 파일
        if not narration:
            logger.warning("scene[%d] narration 없음 — 빈 파일 생성", scene_id)
            out_path.write_bytes(b"")
            paths.append(out_path)
            continue

        # 이미 생성된 파일 재사용 (체크포인트 재시작 대응)
        if out_path.exists() and out_path.stat().st_size > 0:
            logger.debug("scene[%d] 캐시 사용: %s", scene_id, out_path.name)
            paths.append(out_path)
            continue

        try:
            response = client.audio.speech.create(
                model="tts-1",
                voice=voice,
                input=narration,
                speed=config.TTS_SPEED,
                response_format="mp3",
            )
            response.stream_to_file(out_path)
            logger.debug("scene[%d] TTS 완료: %s", scene_id, out_path.name)

            if cost_tracker:
                cost_tracker.add_tts(len(narration))

        except Exception as e:
            logger.error("scene[%d] TTS 실패: %s", scene_id, e)
            out_path.write_bytes(b"")

        paths.append(out_path)

    logger.info("OpenAI TTS 완료: %d개 파일 (%s)", len(paths), lang)
    return paths
