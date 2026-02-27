"""
tts/edge_tts.py — Edge TTS 음성 생성 (무료 로컬 대안)

Microsoft Edge TTS를 사용해 narration을 MP3로 저장한다.
API 키 불필요, 비용 0원.
"""

import asyncio
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
    Edge TTS로 씬별 narration을 MP3로 저장한다.
    openai_tts.synthesize와 동일한 인터페이스.

    Args:
        scenes:      scene dict 목록 (narration, scene_id 포함)
        lang:        "ko" 또는 "en"
        output_dir:  MP3 저장 디렉터리
        cost_tracker: 비용 추적기 (Edge TTS는 무료이므로 비용 미기록)

    Returns:
        씬 순서에 맞는 Path 목록
    """
    voice = config.EDGE_TTS_KO_VOICE if lang == "ko" else config.EDGE_TTS_EN_VOICE
    paths: list[Path] = []

    for i, scene in enumerate(scenes):
        scene_id = scene.get("scene_id", i + 1)
        narration = scene.get("narration", "").strip()
        out_path = output_dir / f"scene_{scene_id:03d}.mp3"

        if not narration:
            logger.warning("scene[%d] narration 없음 — 빈 파일 생성", scene_id)
            out_path.write_bytes(b"")
            paths.append(out_path)
            continue

        if out_path.exists() and out_path.stat().st_size > 0:
            logger.debug("scene[%d] 캐시 사용: %s", scene_id, out_path.name)
            paths.append(out_path)
            continue

        try:
            _run_async(_generate_speech(narration, voice, out_path))
            logger.debug("scene[%d] Edge TTS 완료: %s", scene_id, out_path.name)
        except Exception as e:
            logger.error("scene[%d] Edge TTS 실패: %s", scene_id, e)
            out_path.write_bytes(b"")

        paths.append(out_path)

    logger.info("Edge TTS 완료: %d개 파일 (%s)", len(paths), lang)
    return paths


# ─────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────

def _run_async(coro) -> None:
    """
    이미 실행 중인 이벤트 루프(GUI 환경) 여부와 무관하게 코루틴을 실행한다.
    PyQt6는 자체 이벤트 루프를 가지므로 asyncio.run() 직접 호출 시
    'RuntimeError: This event loop is already running' 발생.
    → 실행 중인 루프가 있으면 별도 스레드에서 새 이벤트 루프로 실행한다.
    """
    import concurrent.futures

    try:
        running_loop = asyncio.get_running_loop()
    except RuntimeError:
        running_loop = None

    if running_loop and running_loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, coro)
            future.result()
    else:
        asyncio.run(coro)


async def _generate_speech(text: str, voice: str, out_path: Path) -> None:
    """edge_tts.Communicate로 음성을 생성하고 파일로 저장한다."""
    import edge_tts

    rate = _speed_to_rate_str(config.TTS_SPEED)
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate)
    await communicate.save(str(out_path))


def _speed_to_rate_str(speed: float) -> str:
    """
    config.TTS_SPEED (0.5~2.0) → Edge TTS rate 문자열 변환.
    예: 1.0 → "+0%", 1.2 → "+20%", 0.8 → "-20%"
    """
    pct = int((speed - 1.0) * 100)
    return f"{pct:+d}%"
