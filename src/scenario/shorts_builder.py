"""
scenario/shorts_builder.py — 쇼츠 시나리오 재구성

5분 시나리오에서 핵심 장면만 추려 60초 이내 쇼츠 시나리오를 만든다.
쇼츠는 5분 영상 유입을 유도하는 예고편/훅 역할이다.
순수 알고리즘으로 처리 (GPT 추가 호출 없음).
"""

import logging
from typing import Optional

import config

logger = logging.getLogger(__name__)

# stage별 쇼츠에 포함할 최대 장면 수
# 빠른 템포를 위해 stage당 4~6장면 이하로 제한
_SHORTS_STAGE_BUDGET: dict[str, int] = {
    "hook":    5,   # 강한 훅 전부
    "problem": 3,   # 문제 제기 핵심만
    "core":    6,   # 가장 임팩트 있는 핵심 장면
    "twist":   3,   # 반전 하이라이트
    "cta":     2,   # 풀영상 유도
}

_STAGE_ORDER = ["hook", "problem", "core", "twist", "cta"]


def build_shorts_scenario(scenes: list) -> list:
    """
    5분 시나리오에서 쇼츠 시나리오를 재구성한다.

    전략:
    1. stage별로 대표 장면 선발 (짧고 임팩트 있는 장면 우선)
    2. 총 duration이 SHORTS_DURATION_SEC 이하가 되도록 제한
    3. scene_id를 1부터 재부여

    Args:
        scenes: 5분 시나리오 장면 목록

    Returns:
        쇼츠 시나리오 장면 목록 (새 scene_id, 원본 dict 불변)
    """
    if not scenes:
        logger.warning("shorts_builder: 입력 scenes가 비어 있음")
        return []

    selected = _select_scenes(scenes)
    selected = _cap_to_duration(selected, config.SHORTS_DURATION_SEC)
    selected = _reassign_ids(selected)

    total_dur = sum(s["duration_sec"] for s in selected)
    logger.info("쇼츠 시나리오: %d장면, 총 %.1f초", len(selected), total_dur)
    return selected


# ─────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────

def _select_scenes(scenes: list) -> list:
    """
    stage별 할당량에 따라 장면을 선발한다.
    같은 stage 내에서는 duration이 짧은 장면을 우선 선발 (빠른 템포).
    stage 등장 순서(원본 기준)를 유지하며 stage_order 순으로 정렬해 재조합한다.
    """
    # stage별 그룹화 (원본 순서 유지)
    by_stage: dict[str, list] = {}
    for s in scenes:
        stage = s.get("stage", "core")
        by_stage.setdefault(stage, []).append(s)

    # stage 내부: duration 짧은 것 우선 (빠른 템포 극대화)
    for stage in by_stage:
        by_stage[stage].sort(key=lambda s: s.get("duration_sec", 3.0))

    selected: list = []
    for stage in _STAGE_ORDER:
        budget = _SHORTS_STAGE_BUDGET.get(stage, 2)
        candidates = by_stage.get(stage, [])
        chosen = candidates[:budget]
        selected.extend(chosen)

    logger.debug(
        "stage별 선발: %s",
        {st: len([s for s in selected if s.get("stage") == st]) for st in _STAGE_ORDER},
    )
    return selected


def _cap_to_duration(scenes: list, max_sec: float) -> list:
    """총 duration이 max_sec를 초과하면 초과 직전까지만 포함한다."""
    result: list = []
    total = 0.0
    for s in scenes:
        dur = s.get("duration_sec", 3.0)
        if total + dur > max_sec:
            break
        result.append(s)
        total += dur
    return result


def _reassign_ids(scenes: list) -> list:
    """scene_id를 1부터 재부여한다. 원본 dict를 수정하지 않고 복사본을 반환한다."""
    result: list = []
    for i, s in enumerate(scenes):
        new_scene = dict(s)
        new_scene["scene_id"] = i + 1
        result.append(new_scene)
    return result
