"""
bgm/audio_mixer.py — TTS + BGM 볼륨 덕킹 처리

대화 6(영상 합성)에서 landscape_composer / shorts_composer가 호출한다.
두 가지 주요 기능:
  1. loop_to_duration  — BGM을 목표 길이에 맞게 루프/트림 후 페이드아웃 처리
  2. mix_bgm_with_tts  — 전체 TTS 오디오에 BGM을 덕킹 볼륨으로 믹싱
"""

import logging
import math
from pathlib import Path
from typing import Optional

import config

logger = logging.getLogger(__name__)

# BGM 페이드아웃 길이 (초)
_FADE_OUT_SEC = 3.0


def loop_to_duration(
    bgm_path: Path,
    duration_sec: float,
    output_path: Path,
) -> Path:
    """
    BGM 파일을 목표 길이(duration_sec)에 맞게 루프하거나 트림해 저장한다.
    마지막 _FADE_OUT_SEC 초를 페이드아웃 처리한다.

    Args:
        bgm_path:     원본 BGM 파일 Path
        duration_sec: 목표 오디오 길이 (초)
        output_path:  출력 파일 Path

    Returns:
        저장된 오디오 파일 Path
    """
    from pydub import AudioSegment

    bgm = AudioSegment.from_file(str(bgm_path))
    target_ms = int(duration_sec * 1000)

    looped = _loop_audio(bgm, target_ms)

    # 페이드아웃
    fade_ms = min(int(_FADE_OUT_SEC * 1000), len(looped))
    looped = looped.fade_out(fade_ms)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    looped.export(str(output_path), format="mp3", bitrate="192k")
    logger.debug("BGM 루프 완료: %.1f초 → %s", duration_sec, output_path.name)
    return output_path


def mix_bgm_with_tts(
    tts_path: Path,
    bgm_path: Path,
    output_path: Path,
    bgm_ratio: Optional[float] = None,
) -> Path:
    """
    TTS 오디오에 BGM을 덕킹 볼륨으로 오버레이해 저장한다.

    BGM은 TTS 길이에 맞게 루프/트림된 후 config.BGM_VOLUME_RATIO 비율로
    볼륨을 낮춰 믹싱한다.

    Args:
        tts_path:   전체 TTS 오디오 파일 Path (씬 연결 후)
        bgm_path:   BGM 파일 Path
        output_path: 믹싱된 출력 파일 Path
        bgm_ratio:  BGM 볼륨 비율 (None → config.BGM_VOLUME_RATIO 사용)

    Returns:
        저장된 믹싱 오디오 파일 Path
    """
    from pydub import AudioSegment

    tts = AudioSegment.from_file(str(tts_path))
    bgm = AudioSegment.from_file(str(bgm_path))

    tts_duration_ms = len(tts)
    bgm_looped = _loop_audio(bgm, tts_duration_ms)

    # 볼륨 조정: ratio → dB 변환 (dB = 20 * log10(ratio))
    ratio = bgm_ratio if bgm_ratio is not None else config.BGM_VOLUME_RATIO
    ratio = max(ratio, 1e-6)   # log(0) 방지
    db_change = 20 * math.log10(ratio)
    bgm_ducked = bgm_looped + db_change

    # 페이드아웃
    fade_ms = min(int(_FADE_OUT_SEC * 1000), len(bgm_ducked))
    bgm_ducked = bgm_ducked.fade_out(fade_ms)

    # 믹싱 (TTS가 기준, BGM을 위에 오버레이)
    mixed = tts.overlay(bgm_ducked)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    mixed.export(str(output_path), format="mp3", bitrate="192k")
    logger.info(
        "오디오 믹싱 완료: TTS %.1fs + BGM(%.0f%%) → %s",
        tts_duration_ms / 1000, ratio * 100, output_path.name,
    )
    return output_path


def concatenate_tts(audio_paths: list[Path], output_path: Path) -> Path:
    """
    씬별 TTS 오디오 파일들을 순서대로 이어붙여 단일 파일로 저장한다.
    영상 합성 시 BGM 믹싱 전에 호출한다.

    Args:
        audio_paths: 씬 순서대로 정렬된 TTS 파일 Path 목록
        output_path: 출력 파일 Path

    Returns:
        저장된 연결 오디오 파일 Path
    """
    from pydub import AudioSegment

    combined = AudioSegment.empty()
    for path in audio_paths:
        if path.exists() and path.stat().st_size > 0:
            try:
                seg = AudioSegment.from_file(str(path))
                combined += seg
            except Exception as e:
                logger.warning("오디오 로드 실패 (%s): %s — 씬 건너뜀", path.name, e)
        else:
            # 빈 파일은 2초 무음으로 대체
            combined += AudioSegment.silent(duration=2000)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    combined.export(str(output_path), format="mp3", bitrate="192k")
    logger.debug("TTS 연결 완료: %d개 파일, 총 %.1fs", len(audio_paths), len(combined) / 1000)
    return output_path


# ─────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────

def _loop_audio(audio, target_ms: int):
    """AudioSegment를 target_ms 길이에 맞게 루프하거나 트림한다."""
    from pydub import AudioSegment

    if len(audio) == 0:
        return AudioSegment.silent(duration=target_ms)

    # 충분한 길이까지 루프
    looped = audio
    while len(looped) < target_ms:
        looped = looped + audio

    # 목표 길이로 트림
    return looped[:target_ms]
