"""
video/encoder.py — ffmpeg 인코딩 설정
moviepy의 write_videofile에 전달할 ffmpeg 파라미터를 중앙 관리한다.
config.VIDEO_RESOLUTION / VIDEO_BITRATE / VIDEO_FPS 를 참조한다.
"""

import logging
from pathlib import Path
from typing import Any

import config

logger = logging.getLogger(__name__)

# ffmpeg libx264 프리셋 (속도 vs 압축률 트레이드오프)
# "medium" → 대부분 환경에서 적절한 균형
_FFMPEG_PRESET = "medium"

# CRF 값 (낮을수록 고품질, 파일 큰 편)
# 23 = libx264 기본값, 18 = 시각적 무손실에 가까움
_CRF = "23"


def get_write_params(is_shorts: bool = False) -> dict[str, Any]:
    """
    moviepy write_videofile()에 전달할 kwargs를 반환한다.

    Parameters
    ----------
    is_shorts : 쇼츠(9:16)이면 True, 일반 영상(16:9)이면 False

    Returns
    -------
    dict  — codec, audio_codec, fps, bitrate, ffmpeg_params 등 포함
    """
    w, h = (
        config.get_shorts_resolution()
        if is_shorts
        else config.get_landscape_resolution()
    )

    params = {
        "codec": "libx264",
        "audio_codec": "aac",
        "fps": config.VIDEO_FPS,
        "bitrate": config.VIDEO_BITRATE,
        "ffmpeg_params": [
            "-preset", _FFMPEG_PRESET,
            "-crf", _CRF,
            "-movflags", "+faststart",   # 웹 스트리밍 최적화 (메타데이터 앞 배치)
            "-pix_fmt", "yuv420p",       # 유튜브 호환성
        ],
        "logger": None,   # moviepy 내부 tqdm 출력 억제
    }

    logger.debug(
        "인코딩 파라미터: %dx%d %s fps=%d bitrate=%s",
        w, h,
        "shorts" if is_shorts else "landscape",
        config.VIDEO_FPS,
        config.VIDEO_BITRATE,
    )
    return params


def encode(
    clip,
    output_path: Path,
    is_shorts: bool = False,
    threads: int = 2,
) -> Path:
    """
    moviepy VideoClip을 ffmpeg로 인코딩해 파일로 저장한다.

    Parameters
    ----------
    clip        : moviepy CompositeVideoClip 등
    output_path : 저장할 파일 경로
    is_shorts   : 쇼츠 여부 (인코딩 파라미터 선택에만 사용)
    threads     : ffmpeg 스레드 수 (기본 2 — 다중 영상 병렬 처리 고려)

    Returns
    -------
    Path  — 저장된 파일 경로
    """
    params = get_write_params(is_shorts=is_shorts)
    params["threads"] = threads

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("인코딩 시작: %s", output_path.name)
    clip.write_videofile(str(output_path), **params)
    logger.info("인코딩 완료: %s (%.1f MB)", output_path.name, output_path.stat().st_size / 1e6)

    return output_path
