"""
tts/duration_corrector.py — 실제 음성 길이로 scene duration_sec 보정

TTS 생성 후 실제 MP3 길이를 측정해 scene의 duration_sec를 덮어쓴다.
이 값이 영상 합성(STEP 8)에서 이미지 표시 시간 및 자막 타이밍의 기준이 된다.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# 빈 파일(narration 없음)의 fallback duration
_EMPTY_FILE_FALLBACK_SEC = 2.0


def correct_durations(scenes: list[dict], audio_paths: list[Path]) -> list[dict]:
    """
    audio_paths의 실제 길이로 scenes의 duration_sec를 갱신한다.

    Args:
        scenes:      scene dict 목록
        audio_paths: synthesize()가 반환한 Path 목록 (scenes와 동일 순서)

    Returns:
        duration_sec가 갱신된 scenes 복사본
    """
    if len(scenes) != len(audio_paths):
        logger.warning(
            "scenes(%d)와 audio_paths(%d) 길이 불일치 — 짧은 쪽 기준으로 처리",
            len(scenes), len(audio_paths),
        )

    corrected = []
    for i, (scene, audio_path) in enumerate(zip(scenes, audio_paths)):
        duration = _get_duration(audio_path)

        if duration <= 0:
            duration = _EMPTY_FILE_FALLBACK_SEC
            logger.debug(
                "scene[%d] 오디오 길이 0 → fallback %.1f초",
                scene.get("scene_id", i + 1), duration,
            )

        updated = dict(scene)
        updated["duration_sec"] = round(duration, 3)
        corrected.append(updated)

    total = sum(s["duration_sec"] for s in corrected)
    logger.info("duration 보정 완료: %d개 씬, 총 %.1f초", len(corrected), total)
    return corrected


# ─────────────────────────────────────────────
# 오디오 길이 측정
# ─────────────────────────────────────────────

def _get_duration(path: Path) -> float:
    """
    MP3 파일의 재생 시간(초)을 반환한다.
    mutagen 우선 → pydub 대체 → 파일 크기 추정 순으로 시도한다.
    """
    if not path.exists() or path.stat().st_size == 0:
        return 0.0

    # 1차: mutagen (순수 파이썬, ffmpeg 불필요)
    try:
        from mutagen.mp3 import MP3
        audio = MP3(str(path))
        return float(audio.info.length)
    except Exception:
        pass

    # 2차: pydub (ffmpeg 필요, 프로젝트 이미 의존)
    try:
        from pydub import AudioSegment
        seg = AudioSegment.from_file(str(path))
        return len(seg) / 1000.0
    except Exception:
        pass

    # 3차: 파일 크기 기반 추정 (128kbps MP3 가정)
    size_bytes = path.stat().st_size
    estimated = size_bytes / (128 * 1000 / 8)
    logger.warning(
        "%s 길이 측정 실패 → 크기 기반 추정 %.1f초", path.name, estimated
    )
    return estimated
