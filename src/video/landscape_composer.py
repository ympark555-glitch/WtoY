"""
video/landscape_composer.py — 5분 영상 합성 (16:9)
이미지 + TTS 오디오 + BGM + 자막을 합성해 landscape MP4를 생성한다.

합성 순서:
  1. 장면별 이미지 → ImageClip (duration = scene.duration_sec)
  2. 장면별 TTS 오디오 → AudioFileClip
  3. 전체 TTS 오디오 연결 → CompositeAudioClip (concat)
  4. BGM AudioFileClip → TTS 대비 BGM_VOLUME_RATIO 볼륨으로 덕킹
  5. 이미지 CUT 전환 → concatenate_videoclips (method="compose")
  6. 자막 오버레이 → CompositeVideoClip
  7. encoder.encode() 호출
"""

import logging
from pathlib import Path
from typing import Union

import config
from video.subtitle_renderer import build_subtitle_clips
from video.encoder import encode

logger = logging.getLogger(__name__)


def _load_image_clip(image_path: Union[str, Path], duration: float, width: int, height: int):
    """이미지를 로드해 지정 해상도로 리사이즈한 ImageClip을 반환한다."""
    from moviepy.editor import ImageClip
    from PIL import Image
    import numpy as np

    img = Image.open(str(image_path)).convert("RGB")
    img = img.resize((width, height), Image.LANCZOS)
    arr = np.array(img)
    return ImageClip(arr).set_duration(duration)


def _build_audio(audio_paths: list[str], bgm_path: str, total_duration: float):
    """
    TTS 오디오 배열 + BGM을 합성해 CompositeAudioClip을 반환한다.
    BGM은 total_duration에 맞게 루프하거나 잘라서 덕킹 처리한다.
    """
    from moviepy.editor import AudioFileClip, CompositeAudioClip, concatenate_audioclips

    # TTS 클립 연결
    tts_clips = []
    for p in audio_paths:
        if Path(p).exists():
            tts_clips.append(AudioFileClip(str(p)))
        else:
            logger.warning("TTS 오디오 파일 없음: %s", p)

    if not tts_clips:
        return None

    tts_audio = concatenate_audioclips(tts_clips)

    if not bgm_path or not Path(bgm_path).exists():
        logger.warning("BGM 파일 없음 — TTS만 사용")
        return tts_audio

    # BGM 로드 → 전체 duration에 맞게 처리
    bgm = AudioFileClip(str(bgm_path))
    if bgm.duration < total_duration:
        # 루프: 필요한 반복 횟수만큼 연결
        from moviepy.editor import concatenate_audioclips as _cat
        repeats = int(total_duration / bgm.duration) + 1
        bgm = _cat([bgm] * repeats)
    bgm = bgm.subclip(0, total_duration)

    # 볼륨 덕킹
    bgm = bgm.volumex(config.BGM_VOLUME_RATIO)

    composite = CompositeAudioClip([tts_audio, bgm])
    composite = composite.set_duration(total_duration)
    return composite


def compose_landscape(
    scenes: list[dict],
    image_paths: list[str],
    audio_paths: list[str],
    bgm_path: str,
    output_path: Union[str, Path],
    lang: str = "ko",
) -> Path:
    """
    5분 landscape(16:9) 영상을 합성해 output_path에 저장한다.

    Parameters
    ----------
    scenes      : scenario_ko 또는 scenario_en (duration_sec 보정 완료)
    image_paths : STEP 5에서 생성된 이미지 경로 목록 (scenes와 동수)
    audio_paths : STEP 6에서 생성된 TTS 오디오 경로 목록 (scenes와 동수)
    bgm_path    : STEP 7에서 선택된 BGM 파일 경로
    output_path : 저장할 MP4 경로
    lang        : "ko" | "en" (자막 폰트 선택에 사용)

    Returns
    -------
    Path  — 저장된 파일 경로
    """
    from moviepy.editor import concatenate_videoclips, CompositeVideoClip

    output_path = Path(output_path)
    w, h = config.get_landscape_resolution()

    logger.info("landscape 합성 시작: lang=%s, 장면=%d개", lang, len(scenes))

    # ── 1. 장면별 이미지 클립 ──────────────────────────────
    n = min(len(scenes), len(image_paths))
    if n < len(scenes):
        logger.warning("이미지 수(%d) < 장면 수(%d) — 초과 장면은 마지막 이미지 재사용", len(image_paths), len(scenes))

    image_clips = []
    for i, scene in enumerate(scenes):
        img_idx = min(i, len(image_paths) - 1)
        dur = float(scene.get("duration_sec", config.SCENE_TARGET_SEC))
        clip = _load_image_clip(image_paths[img_idx], dur, w, h)
        image_clips.append(clip)

    video = concatenate_videoclips(image_clips, method="compose")

    # ── 2. 자막 오버레이 ──────────────────────────────────
    subtitle_clips = build_subtitle_clips(scenes, w, h, lang=lang)
    if subtitle_clips:
        video = CompositeVideoClip([video] + subtitle_clips)

    # ── 3. 오디오 합성 ────────────────────────────────────
    total_dur = video.duration
    audio = _build_audio(audio_paths, bgm_path, total_dur)
    if audio is not None:
        video = video.set_audio(audio)

    # ── 4. 인코딩 저장 ────────────────────────────────────
    result = encode(video, output_path, is_shorts=False)

    # 메모리 해제
    video.close()

    logger.info("landscape 합성 완료: %s", result.name)
    return result
