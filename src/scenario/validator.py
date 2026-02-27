"""
scenario/validator.py — 시나리오 자동 검증 및 보정

generate_scenario() 결과를 받아 아래 규칙을 적용한다.
  - scene_id 1부터 순서 재부여
  - 총 duration이 TARGET_DURATION_SEC ±10초를 벗어나면 비율 보정
  - stage 순서가 hook→problem→core→twist→cta를 벗어나면 경고 로그
"""

import logging
from typing import Optional

import config
from core.cost_tracker import CostTracker

logger = logging.getLogger(__name__)

_DURATION_TOLERANCE = 10   # 허용 오차 (초)
_SCENE_MIN_SEC = 2.0       # 장면 최소 시간
_SCENE_MAX_SEC = 6.0       # 장면 최대 시간 (보정 후 클램핑)
_STAGE_ORDER = ["hook", "problem", "core", "twist", "cta"]


def validate_and_fix(
    result: dict,
    cost_tracker: Optional[CostTracker] = None,
) -> dict:
    """
    시나리오를 검증하고 자동 보정한다.

    Args:
        result: {"scenes": [...], "title_ko": "..."}
        cost_tracker: 현재 미사용 (인터페이스 일관성 유지)

    Returns:
        보정된 result dict
    """
    scenes = result.get("scenes", [])
    if not scenes:
        logger.warning("validator: scenes가 비어 있음 — 보정 없이 반환")
        return result

    scenes = _fix_scene_ids(scenes)
    scenes = _fix_duration(scenes)
    _warn_stage_order(scenes)

    result["scenes"] = scenes

    total = sum(s["duration_sec"] for s in scenes)
    logger.info("validator 완료: %d장면, 총 %.1f초", len(scenes), total)
    return result


# ─────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────

def _fix_scene_ids(scenes: list) -> list:
    """scene_id를 1부터 순서대로 재부여한다."""
    for i, s in enumerate(scenes):
        s["scene_id"] = i + 1
    return scenes


def _fix_duration(scenes: list) -> list:
    """
    총 duration이 TARGET_DURATION_SEC ±TOLERANCE를 벗어나면
    비율 조정으로 보정한다.
    개별 scene은 [SCENE_MIN_SEC, SCENE_MAX_SEC] 범위로 클램핑한다.
    """
    target = float(config.TARGET_DURATION_SEC)
    lower = target - _DURATION_TOLERANCE
    upper = target + _DURATION_TOLERANCE

    total = sum(s.get("duration_sec", 3.0) for s in scenes)

    if lower <= total <= upper:
        logger.debug("총 duration %.1f초 — 목표 범위(%.0f~%.0f초) 내", total, lower, upper)
        return scenes

    ratio = target / total if total > 0 else 1.0
    logger.info(
        "총 duration 보정: %.1f초 → %.1f초 (ratio=%.4f)",
        total, target, ratio,
    )

    for s in scenes:
        raw = s.get("duration_sec", 3.0) * ratio
        s["duration_sec"] = round(max(_SCENE_MIN_SEC, min(_SCENE_MAX_SEC, raw)), 1)

    new_total = sum(s["duration_sec"] for s in scenes)
    logger.info("보정 후 총 duration: %.1f초", new_total)
    return scenes


def _warn_stage_order(scenes: list) -> None:
    """
    stage 순서가 hook→problem→core→twist→cta를 역행하면 경고한다.
    자동 수정은 하지 않는다 (내레이션 의미가 바뀔 수 있음).
    """
    last_idx = -1
    for s in scenes:
        stage = s.get("stage", "")
        if stage not in _STAGE_ORDER:
            continue
        idx = _STAGE_ORDER.index(stage)
        if idx < last_idx:
            logger.warning(
                "stage 순서 이상: scene_id=%d에서 '%s'(%d)가 '%s'(%d) 이전 단계로 역행",
                s.get("scene_id", "?"),
                stage, idx,
                _STAGE_ORDER[last_idx], last_idx,
            )
            return  # 첫 번째 이상만 경고
        last_idx = idx
