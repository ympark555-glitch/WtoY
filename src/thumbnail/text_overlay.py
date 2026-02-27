"""
thumbnail/text_overlay.py — Pillow 텍스트 오버레이

썸네일 베이스 이미지를 YouTube 표준 사이즈로 리사이즈하고
한/영 오버레이 텍스트를 합성해 최종 JPG를 저장한다.

YouTube 표준 썸네일 사이즈:
  - 가로 영상:  1280 x  720  → thumb_landscape_ko.jpg / thumb_landscape_en.jpg
  - 쇼츠:      1080 x 1920  → thumb_shorts_ko.jpg    / thumb_shorts_en.jpg

텍스트 배치:
  - 가로 영상: 하단 80% 위치 (하단 여백 20%)
  - 쇼츠:      하단 88% 위치 (하단 여백 12%)

스타일: 흰색 텍스트 + 검정 스트로크 (stroke_width 4px, subtitle_renderer와 동일 방식)
"""

import logging
from pathlib import Path
from typing import Optional

import config

logger = logging.getLogger(__name__)

# YouTube 표준 썸네일 사이즈
_LANDSCAPE_SIZE = (1280, 720)
_SHORTS_SIZE = (1080, 1920)

# 텍스트 수직 위치 (이미지 높이 기준 비율)
_TEXT_Y_RATIO = {
    "landscape": 0.82,
    "shorts": 0.88,
}

# 폰트 크기 (이미지 너비 기준 비율)
_FONT_RATIO = {
    "landscape": 0.075,
    "shorts":    0.085,
}

# 텍스트 스트로크 픽셀 수
_STROKE_WIDTH = 4

# 색상
_COLOR_WHITE = (255, 255, 255)
_COLOR_BLACK = (0, 0, 0)


def apply_text_overlay(
    base_image_path: Path,
    overlay_text: str,
    output_path: Path,
    variant: str,
    lang: str = "ko",
) -> Optional[Path]:
    """
    베이스 이미지에 텍스트를 오버레이하고 최종 썸네일 JPG를 저장한다.

    Args:
        base_image_path: DALL-E 3로 생성된 베이스 PNG 경로
        overlay_text:    오버레이할 텍스트 (ko 또는 en)
        output_path:     저장할 JPG 경로
        variant:         "landscape" 또는 "shorts"
        lang:            "ko" 또는 "en" (폰트 선택)

    Returns:
        저장된 JPG Path, 실패 시 None
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        logger.error("Pillow가 설치되지 않았습니다: pip install Pillow")
        return None

    if variant not in ("landscape", "shorts"):
        logger.error("variant는 'landscape' 또는 'shorts'여야 합니다: %r", variant)
        return None

    if not base_image_path.exists():
        logger.error("베이스 이미지 없음: %s", base_image_path)
        return None

    target_size = _LANDSCAPE_SIZE if variant == "landscape" else _SHORTS_SIZE

    # 이미지 열기 + 리사이즈
    try:
        img = Image.open(base_image_path).convert("RGB")
        img = img.resize(target_size, Image.LANCZOS)
    except Exception as e:
        logger.error("이미지 열기/리사이즈 실패: %s", e)
        return None

    draw = ImageDraw.Draw(img)
    font = _load_font(lang, target_size, variant)

    # 텍스트 크기 측정
    try:
        bbox = draw.textbbox((0, 0), overlay_text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
    except Exception:
        text_w, text_h = target_size[0] // 2, 50

    # 텍스트 위치: 수평 중앙, 수직은 설정 비율
    x = (target_size[0] - text_w) // 2
    y = int(target_size[1] * _TEXT_Y_RATIO[variant]) - text_h // 2

    # 스트로크 먼저 렌더링 (subtitle_renderer와 동일 방식)
    for dx in range(-_STROKE_WIDTH, _STROKE_WIDTH + 1):
        for dy in range(-_STROKE_WIDTH, _STROKE_WIDTH + 1):
            if dx == 0 and dy == 0:
                continue
            draw.text((x + dx, y + dy), overlay_text, font=font, fill=_COLOR_BLACK)

    # 본문 텍스트
    draw.text((x, y), overlay_text, font=font, fill=_COLOR_WHITE)

    # 저장
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(output_path), "JPEG", quality=95)
        logger.info("썸네일 저장 완료: %s", output_path.name)
        return output_path
    except Exception as e:
        logger.error("썸네일 저장 실패 (%s): %s", output_path.name, e)
        return None


def generate_all_thumbnails(
    base_landscape_path: Optional[Path],
    base_shorts_path: Optional[Path],
    overlay_text_ko: str,
    overlay_text_en: str,
    output_dir: Path,
) -> dict[str, Optional[Path]]:
    """
    4종 썸네일을 한 번에 생성한다.

    Args:
        base_landscape_path: 가로 베이스 PNG 경로 (없으면 해당 2종 None)
        base_shorts_path:    쇼츠 베이스 PNG 경로 (없으면 해당 2종 None)
        overlay_text_ko:     한국어 오버레이 텍스트
        overlay_text_en:     영어 오버레이 텍스트
        output_dir:          프로젝트 output 디렉토리

    Returns:
        {
            "landscape_ko": Path | None,
            "landscape_en": Path | None,
            "shorts_ko":    Path | None,
            "shorts_en":    Path | None,
        }
    """
    thumbnails_dir = output_dir / "thumbnails"

    specs = [
        ("landscape_ko", base_landscape_path, overlay_text_ko, "landscape", "ko"),
        ("landscape_en", base_landscape_path, overlay_text_en, "landscape", "en"),
        ("shorts_ko",    base_shorts_path,    overlay_text_ko, "shorts",    "ko"),
        ("shorts_en",    base_shorts_path,    overlay_text_en, "shorts",    "en"),
    ]

    results: dict[str, Optional[Path]] = {}
    for key, base_path, text, variant, lang in specs:
        if base_path is None:
            logger.warning("베이스 이미지 없음 — %s 건너뜀", key)
            results[key] = None
            continue
        results[key] = apply_text_overlay(
            base_image_path=base_path,
            overlay_text=text,
            output_path=thumbnails_dir / f"thumb_{key}.jpg",
            variant=variant,
            lang=lang,
        )

    success = sum(1 for v in results.values() if v is not None)
    logger.info("썸네일 생성 완료: %d/4종", success)
    return results


# ─────────────────────────────────────────────
# 내부 유틸
# ─────────────────────────────────────────────

def _load_font(lang: str, target_size: tuple[int, int], variant: str):
    """언어와 영상 타입에 맞는 Pillow 폰트를 로드한다."""
    from PIL import ImageFont

    font_path = config.FONT_KO_PATH if lang == "ko" else config.FONT_EN_PATH
    font_size = int(target_size[0] * _FONT_RATIO[variant])

    if font_path.exists():
        try:
            return ImageFont.truetype(str(font_path), font_size)
        except Exception as e:
            logger.warning("폰트 로드 실패 (%s): %s — 기본 폰트 사용", font_path.name, e)

    # 폴백: PIL 내장 폰트 (한글 깨질 수 있음 — BUG-24 참고)
    try:
        return ImageFont.load_default(size=font_size)
    except TypeError:
        return ImageFont.load_default()
