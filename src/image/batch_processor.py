"""
image/batch_processor.py — 배치 병렬 이미지 생성

scenes 목록을 IMAGE_BATCH_SIZE(기본 10)개 단위 배치로 나눠 처리한다.
  - DALL-E 3: ThreadPoolExecutor로 배치 내 병렬 생성 (max_workers=5, Rate Limit 대응)
  - Stable Diffusion: 순차 생성 (로컬 GPU 단일 처리)

각 scene 생성 전 cache_matcher로 유사 이미지를 검색한다.
유사도 80% 이상 발견 시 reuse_callback을 호출해 제작자(또는 GUI)가 결정하도록 한다.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Optional

import config
from core.cost_tracker import CostTracker
from image import cache_matcher, style_anchor
from image.generator import dalle_generator, sd_generator

logger = logging.getLogger(__name__)

# (scene_id, prompt, existing_path) -> bool (True=재사용, False=새로 생성)
ReuseCallback = Callable[[int, str, str], bool]

# (completed: int, total: int) -> None
ProgressCallback = Callable[[int, int], None]

# DALL-E 3 Tier-1 Rate Limit: ~5 img/min. 워커 5개면 큐 쌓임 방지
_DALLE_MAX_WORKERS = 5


def generate_all(
    scenes: list,
    output_dir: Path,
    cost_tracker: Optional[CostTracker] = None,
    reuse_callback: Optional[ReuseCallback] = None,
    progress_callback: Optional[ProgressCallback] = None,
) -> dict[int, Path]:
    """
    모든 scene의 이미지를 생성하고 {scene_id: image_path} 딕셔너리를 반환한다.

    Args:
        scenes:            Scene JSON 리스트 (scene_id, image_prompt 필드 필수)
        output_dir:        프로젝트 output 디렉토리
        cost_tracker:      비용 추적기 (None이면 비용 기록 없음)
        reuse_callback:    유사 이미지 발견 시 호출. True 반환 시 재사용.
                           None이면 항상 새로 생성.
        progress_callback: (완료 수, 전체 수) 진행 알림 콜백

    Returns:
        {scene_id: image_path} — 실패한 scene_id는 포함되지 않음
    """
    result: dict[int, Path] = {}
    total = len(scenes)
    batch_size = config.IMAGE_BATCH_SIZE
    batches = [scenes[i:i + batch_size] for i in range(0, total, batch_size)]
    completed = 0

    logger.info(
        "이미지 생성 시작: 총 %d장, %d개 배치 (엔진=%s)",
        total, len(batches), config.IMAGE_ENGINE,
    )

    for batch_idx, batch in enumerate(batches):
        logger.info("배치 %d/%d 처리 중 (%d장)", batch_idx + 1, len(batches), len(batch))

        if config.IMAGE_ENGINE == "dalle3":
            batch_result = _process_parallel(batch, output_dir, cost_tracker, reuse_callback)
        else:
            batch_result = _process_sequential(batch, output_dir, reuse_callback)

        result.update(batch_result)
        completed += len(batch)

        if progress_callback:
            progress_callback(completed, total)

    success = len(result)
    logger.info("이미지 생성 완료: %d/%d장 성공", success, total)
    return result


# ─────────────────────────────────────────────
# 내부 처리
# ─────────────────────────────────────────────

def _generate_one(
    scene: dict,
    output_dir: Path,
    cost_tracker: Optional[CostTracker],
    reuse_callback: Optional[ReuseCallback],
) -> tuple[int, Optional[Path]]:
    """
    장면 하나의 이미지를 생성한다.
    1. 스타일 앵커 적용
    2. 캐시에서 유사 이미지 검색
    3. 유사 이미지 있으면 reuse_callback 호출
    4. 재사용 거부 or 캐시 없음 → 엔진으로 생성 후 캐시 저장
    """
    scene_id: int = scene["scene_id"]
    raw_prompt: str = scene.get("image_prompt", "")

    # 스타일 앵커 적용 (이중 방어 2차)
    prompt = style_anchor.apply(raw_prompt)

    # 캐시 검색
    similar = cache_matcher.find_similar(prompt)
    if similar and reuse_callback is not None:
        best = similar[0]
        logger.info(
            "유사 이미지 발견 scene %d: 유사도=%.1f%% → 재사용 여부 콜백",
            scene_id, best["similarity"] * 100,
        )
        if reuse_callback(scene_id, prompt, best["image_path"]):
            logger.info("scene %d — 캐시 이미지 재사용", scene_id)
            return scene_id, Path(best["image_path"])

    # 새 이미지 생성
    path = _call_engine(prompt, scene_id, output_dir, cost_tracker)
    if path:
        cache_matcher.save(prompt, path)

    return scene_id, path


def _call_engine(
    prompt: str,
    scene_id: int,
    output_dir: Path,
    cost_tracker: Optional[CostTracker],
) -> Optional[Path]:
    """선택된 엔진으로 이미지를 생성한다."""
    if config.IMAGE_ENGINE == "dalle3":
        return dalle_generator.generate_image(prompt, scene_id, output_dir, cost_tracker)
    else:
        return sd_generator.generate_image(prompt, scene_id, output_dir)


def _process_parallel(
    batch: list,
    output_dir: Path,
    cost_tracker: Optional[CostTracker],
    reuse_callback: Optional[ReuseCallback],
) -> dict[int, Path]:
    """ThreadPoolExecutor로 배치 내 병렬 처리 (DALL-E 3 전용)."""
    result: dict[int, Path] = {}
    workers = min(_DALLE_MAX_WORKERS, len(batch))

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_generate_one, scene, output_dir, cost_tracker, reuse_callback): scene["scene_id"]
            for scene in batch
        }
        for future in as_completed(futures):
            sid = futures[future]
            try:
                scene_id, path = future.result()
                if path:
                    result[scene_id] = path
                else:
                    logger.warning("scene %d 이미지 생성 실패", sid)
            except Exception as e:
                logger.error("scene %d 처리 중 예외: %s", sid, e)

    return result


def _process_sequential(
    batch: list,
    output_dir: Path,
    reuse_callback: Optional[ReuseCallback],
) -> dict[int, Path]:
    """순차 처리 (Stable Diffusion 전용 — 로컬 GPU는 병렬 무의미)."""
    result: dict[int, Path] = {}
    for scene in batch:
        scene_id, path = _generate_one(scene, output_dir, None, reuse_callback)
        if path:
            result[scene_id] = path
        else:
            logger.warning("scene %d 이미지 생성 실패", scene["scene_id"])
    return result
