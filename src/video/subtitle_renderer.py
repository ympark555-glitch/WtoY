"""
video/subtitle_renderer.py — 자막 렌더링
moviepy ImageClip을 사용해 장면별 텍스트 오버레이를 생성한다.
자막 폰트, 크기, 위치, 색상은 config에서 읽는다.
폰트 파일이 없으면 PIL 기본 폰트로 자동 대체한다.
"""

import logging
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont
import numpy as np

import config

logger = logging.getLogger(__name__)

# 자막 위치 → 수직 여백 비율 (영상 높이 기준)
_POSITION_MAP = {
    "top":    0.05,
    "center": 0.45,
    "bottom": 0.82,
}


def _load_font(lang: str, size: int) -> ImageFont.FreeTypeFont:
    """언어에 맞는 TTF 폰트를 로드한다. 실패 시 PIL 기본 폰트 사용."""
    path = config.FONT_KO_PATH if lang == "ko" else config.FONT_EN_PATH
    try:
        return ImageFont.truetype(str(path), size)
    except (IOError, OSError):
        logger.warning("폰트 로드 실패 (%s) — PIL 기본 폰트 사용", path)
        try:
            # PIL 내장 폰트 (크기 조절 불가, 최후 수단)
            return ImageFont.load_default()
        except Exception:
            return ImageFont.load_default()


def render_subtitle_frame(
    text: str,
    width: int,
    height: int,
    lang: str = "ko",
    font_size: Optional[int] = None,
    position: Optional[str] = None,
    color: Optional[str] = None,
    stroke_color: Optional[str] = None,
    stroke_width: Optional[int] = None,
) -> np.ndarray:
    """
    투명 배경의 자막 RGBA 프레임을 numpy 배열로 반환한다.
    moviepy의 ImageClip에 직접 전달 가능.

    Parameters
    ----------
    text         : 표시할 자막 문자열
    width, height: 영상 프레임 크기
    lang         : "ko" | "en"
    나머지 파라미터는 None이면 config 기본값 사용
    """
    fs = font_size   or config.SUBTITLE_FONT_SIZE
    pos = position   or config.SUBTITLE_POSITION
    fg  = color      or config.SUBTITLE_COLOR
    sc  = stroke_color or config.SUBTITLE_STROKE_COLOR
    sw  = stroke_width if stroke_width is not None else config.SUBTITLE_STROKE_WIDTH

    font = _load_font(lang, fs)

    # 투명 레이어 생성
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 텍스트 박스 측정
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    x = (width - text_w) / 2
    y_ratio = _POSITION_MAP.get(pos, 0.82)
    y = height * y_ratio - text_h / 2

    # 스트로크(외곽선) 먼저 렌더링
    if sw > 0:
        for dx in range(-sw, sw + 1):
            for dy in range(-sw, sw + 1):
                if dx == 0 and dy == 0:
                    continue
                draw.text((x + dx, y + dy), text, font=font, fill=sc)

    # 본문 텍스트
    draw.text((x, y), text, font=font, fill=fg)

    return np.array(img)


def render_subtitle_clip(
    text: str,
    duration: float,
    width: int,
    height: int,
    lang: str = "ko",
    **kwargs,
):
    """
    자막 ImageClip을 생성해 반환한다.
    moviepy.ImageClip을 래핑하며, compose_landscape / compose_shorts에서 사용된다.

    Returns
    -------
    moviepy.ImageClip  (RGBA, duration=duration)
    """
    from moviepy.editor import ImageClip

    frame = render_subtitle_frame(
        text=text,
        width=width,
        height=height,
        lang=lang,
        **kwargs,
    )
    clip = ImageClip(frame, ismask=False).set_duration(duration)
    return clip


def build_subtitle_clips(
    scenes: list[dict],
    width: int,
    height: int,
    lang: str = "ko",
) -> list:
    """
    시나리오 scene 목록 → 자막 ImageClip 목록 (타이밍 포함).
    각 clip의 start는 누적 duration_sec으로 설정된다.

    Returns
    -------
    list of moviepy.ImageClip  (start 설정 완료)
    """
    if not config.SUBTITLE_ENABLED:
        return []

    clips = []
    t = 0.0
    for scene in scenes:
        text = scene.get("text_overlay") or scene.get("narration", "")
        dur = float(scene.get("duration_sec", 3.0))
        if text.strip():
            clip = render_subtitle_clip(
                text=text,
                duration=dur,
                width=width,
                height=height,
                lang=lang,
            )
            clip = clip.set_start(t)
            clips.append(clip)
        t += dur

    logger.debug("자막 클립 생성: %d개", len(clips))
    return clips
