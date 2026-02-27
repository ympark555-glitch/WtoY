"""
video/shorts_composer.py — 쇼츠 합성 (9:16 레터박스)
설계 사양: 상단 제목 + 이미지 원본 + 하단 여백

레이아웃 (9:16, 예: 1080×1920):
  ┌─────────────────────┐
  │   상단 제목 영역     │  ← 전체 높이의 약 12%
  ├─────────────────────┤
  │                     │
  │   이미지 (원본)      │  ← 1:1 또는 4:3 비율 유지, 중앙 정렬
  │                     │
  ├─────────────────────┤
  │   하단 여백         │  ← 나머지 공간 (자막 영역)
  └─────────────────────┘

BUG-04 해결: shorts 시나리오의 scene_id 기반으로 landscape audio_paths에서
  해당 scene 오디오만 필터링한다.
  scene_id는 1-based 정수이므로 audio_paths[scene_id - 1]로 매핑.
"""

import logging
from pathlib import Path
from typing import Union

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import config
from video.subtitle_renderer import build_subtitle_clips
from video.encoder import encode

logger = logging.getLogger(__name__)

# 레이아웃 비율
_TITLE_HEIGHT_RATIO = 0.12   # 상단 제목 영역 높이 / 전체 높이
_BOTTOM_PAD_RATIO   = 0.08   # 하단 여백 높이 / 전체 높이


def _render_title_bar(title: str, width: int, height: int, lang: str) -> np.ndarray:
    """상단 제목 바 이미지를 RGBA numpy 배열로 반환한다."""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 200))
    draw = ImageDraw.Draw(img)

    font_path = config.FONT_KO_PATH if lang == "ko" else config.FONT_EN_PATH
    font_size = max(28, int(height * 0.45))
    try:
        font = ImageFont.truetype(str(font_path), font_size)
    except (IOError, OSError):
        font = ImageFont.load_default()

    # 텍스트가 너무 길면 말줄임 처리
    max_chars = 25
    display_text = title if len(title) <= max_chars else title[:max_chars - 1] + "…"

    bbox = draw.textbbox((0, 0), display_text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = (width - tw) / 2
    y = (height - th) / 2

    # 스트로크
    sw = config.SUBTITLE_STROKE_WIDTH
    for dx in range(-sw, sw + 1):
        for dy in range(-sw, sw + 1):
            if dx == 0 and dy == 0:
                continue
            draw.text((x + dx, y + dy), display_text, font=font, fill="black")
    draw.text((x, y), display_text, font=font, fill="white")

    return np.array(img)


def _make_scene_frame(
    image_path: str,
    title: str,
    sw: int,
    sh: int,
    lang: str,
) -> np.ndarray:
    """
    한 장면의 쇼츠 프레임(sw×sh, RGB)을 생성한다.
    - 검은 배경
    - 상단: 반투명 제목 바
    - 중간: 원본 이미지 (비율 유지 letterbox)
    - 하단: 여백
    """
    canvas = Image.new("RGB", (sw, sh), (0, 0, 0))

    title_h = int(sh * _TITLE_HEIGHT_RATIO)
    bottom_h = int(sh * _BOTTOM_PAD_RATIO)
    image_area_h = sh - title_h - bottom_h

    # 이미지 로드 → 이미지 영역에 맞게 letterbox 리사이즈
    img = Image.open(str(image_path)).convert("RGB")
    img_w, img_h = img.size
    scale = min(sw / img_w, image_area_h / img_h)
    new_w = int(img_w * scale)
    new_h = int(img_h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)

    # 이미지를 이미지 영역 중앙에 붙이기
    x_offset = (sw - new_w) // 2
    y_offset = title_h + (image_area_h - new_h) // 2
    canvas.paste(img, (x_offset, y_offset))

    # 상단 제목 바 오버레이
    title_arr = _render_title_bar(title, sw, title_h, lang)
    title_img = Image.fromarray(title_arr, "RGBA")
    canvas.paste(title_img, (0, 0), title_img)  # alpha 마스크 사용

    return np.array(canvas)


def _filter_audio_by_scene_ids(
    all_audio_paths: list[str],
    scenes: list[dict],
) -> list[str]:
    """
    BUG-04 해결:
    shorts 시나리오의 scene_id를 기준으로 landscape 전체 오디오 목록에서
    해당 scene의 오디오 경로만 추출한다.
    scene_id는 1-based이므로 index = scene_id - 1.
    scene_id가 없거나 범위를 벗어나면 빈 문자열("")로 채운다.
    """
    filtered = []
    for scene in scenes:
        sid = scene.get("scene_id")
        if sid is None:
            filtered.append("")
            continue
        idx = int(sid) - 1
        if 0 <= idx < len(all_audio_paths):
            filtered.append(all_audio_paths[idx])
        else:
            logger.warning("scene_id %d에 해당하는 오디오 없음 (전체 %d개)", sid, len(all_audio_paths))
            filtered.append("")
    return filtered


def compose_shorts(
    scenes: list[dict],
    image_paths: list[str],
    audio_paths: list[str],
    bgm_path: str,
    output_path: Union[str, Path],
    title: str,
    lang: str = "ko",
) -> Path:
    """
    쇼츠(9:16) 영상을 합성해 output_path에 저장한다.

    Parameters
    ----------
    scenes      : shorts_scenario_ko 또는 shorts_scenario_en
    image_paths : STEP 5에서 생성된 전체 이미지 경로 목록 (landscape와 동일)
    audio_paths : STEP 6에서 생성된 landscape TTS 오디오 목록 (scene_id 기반 필터링)
    bgm_path    : STEP 7에서 선택된 BGM 파일 경로
    output_path : 저장할 MP4 경로
    title       : 상단 제목 바에 표시할 유튜브 제목
    lang        : "ko" | "en"

    Returns
    -------
    Path  — 저장된 파일 경로
    """
    from moviepy.editor import (
        ImageClip,
        concatenate_videoclips,
        CompositeVideoClip,
        AudioFileClip,
        CompositeAudioClip,
        concatenate_audioclips,
    )

    output_path = Path(output_path)
    sw, sh = config.get_shorts_resolution()

    logger.info("shorts 합성 시작: lang=%s, 장면=%d개 (%dx%d)", lang, len(scenes), sw, sh)

    # BUG-04: scene_id 기반 오디오 필터링
    filtered_audio = _filter_audio_by_scene_ids(audio_paths, scenes)

    # ── 1. 장면별 프레임 → ImageClip ──────────────────────
    image_clips = []
    for i, scene in enumerate(scenes):
        img_idx = scene.get("scene_id", i + 1) - 1
        img_idx = max(0, min(img_idx, len(image_paths) - 1))

        dur = float(scene.get("duration_sec", config.SCENE_TARGET_SEC))
        frame = _make_scene_frame(image_paths[img_idx], title, sw, sh, lang)
        clip = ImageClip(frame).set_duration(dur)
        image_clips.append(clip)

    video = concatenate_videoclips(image_clips, method="compose")

    # ── 2. 자막 오버레이 ──────────────────────────────────
    subtitle_clips = build_subtitle_clips(scenes, sw, sh, lang=lang)
    if subtitle_clips:
        video = CompositeVideoClip([video] + subtitle_clips)

    # ── 3. 오디오 합성 (scene_id 기반 필터링된 TTS + BGM) ──
    total_dur = video.duration
    tts_clips = []
    for ap in filtered_audio:
        if ap and Path(ap).exists():
            tts_clips.append(AudioFileClip(ap))
        else:
            # 오디오 없는 장면은 무음으로 채우지 않음 (gap 자연스럽게 처리)
            pass

    if tts_clips:
        tts_audio = concatenate_audioclips(tts_clips)
    else:
        tts_audio = None

    if bgm_path and Path(bgm_path).exists():
        bgm = AudioFileClip(str(bgm_path))
        if bgm.duration < total_dur:
            from moviepy.editor import concatenate_audioclips as _cat
            repeats = int(total_dur / bgm.duration) + 1
            bgm = _cat([bgm] * repeats)
        bgm = bgm.subclip(0, total_dur).volumex(config.BGM_VOLUME_RATIO)

        if tts_audio is not None:
            audio = CompositeAudioClip([tts_audio, bgm]).set_duration(total_dur)
        else:
            audio = bgm.set_duration(total_dur)
    else:
        audio = tts_audio

    if audio is not None:
        video = video.set_audio(audio)

    # ── 4. 인코딩 저장 ────────────────────────────────────
    result = encode(video, output_path, is_shorts=True)

    video.close()

    logger.info("shorts 합성 완료: %s", result.name)
    return result
