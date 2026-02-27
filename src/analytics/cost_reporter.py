"""
analytics/cost_reporter.py — 비용 리포트

히스토리 DB에서 비용 데이터를 집계하여
월별 현황, 영상별 비용, 이미지 재사용 절감액 등을 리포트한다.
통계 탭에서 차트와 테이블로 표시할 데이터를 제공한다.
"""

import logging
from datetime import datetime
from typing import Optional

import config

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# 월별 비용 현황
# ─────────────────────────────────────────────

def monthly_summary(year: Optional[int] = None) -> list[dict]:
    """
    월별 비용 요약을 반환한다.

    year: 조회 연도 (None이면 현재 연도)
    반환:
        [
            {
                "year": 2024,
                "month": 1,
                "total_cost": 12.50,
                "video_count": 3,
                "avg_cost": 4.17,
                "image_count": 240,
                "reused_images": 15,
            },
            ...
        ]
    """
    from history.history_manager import get_by_month

    if year is None:
        year = datetime.now().year

    results: list[dict] = []
    for month in range(1, 13):
        records = get_by_month(year, month)
        if not records:
            continue

        total_cost = sum(r.get("cost_usd", 0.0) for r in records)
        image_count = sum(r.get("image_count", 0) for r in records)
        reused = sum(r.get("reused_images", 0) for r in records)

        results.append({
            "year": year,
            "month": month,
            "total_cost": round(total_cost, 4),
            "video_count": len(records),
            "avg_cost": round(total_cost / len(records), 4) if records else 0.0,
            "image_count": image_count,
            "reused_images": reused,
        })

    return results


# ─────────────────────────────────────────────
# 전체 누적 비용
# ─────────────────────────────────────────────

def total_summary() -> dict:
    """
    전체 기간 비용 요약을 반환한다.

    반환:
        {
            "total_cost_usd": float,
            "total_cost_krw": int,
            "total_videos": int,
            "avg_cost_per_video": float,
            "total_images": int,
            "reused_images": int,
            "estimated_savings_usd": float,
        }
    """
    from history.history_manager import total_count, total_cost, total_reused_images, get_all

    videos = total_count()
    cost = total_cost()
    reused = total_reused_images()

    # 모든 기록에서 이미지 총합 계산
    all_records = get_all(limit=10000)
    total_images = sum(r.get("image_count", 0) for r in all_records)

    # 절감액: 재사용 이미지 * DALL-E 3 단가
    unit_cost = (
        config.COST_DALLE3_HD_PER_IMAGE
        if config.IMAGE_QUALITY == "hd"
        else config.COST_DALLE3_STD_PER_IMAGE
    )
    savings = reused * unit_cost

    return {
        "total_cost_usd": round(cost, 4),
        "total_cost_krw": int(cost * 1380),
        "total_videos": videos,
        "avg_cost_per_video": round(cost / videos, 4) if videos else 0.0,
        "total_images": total_images,
        "reused_images": reused,
        "estimated_savings_usd": round(savings, 4),
    }


# ─────────────────────────────────────────────
# 영상별 비용 상세
# ─────────────────────────────────────────────

def per_video_costs(limit: int = 50) -> list[dict]:
    """
    영상별 비용 상세를 반환한다 (최신순).

    반환:
        [
            {
                "id": int,
                "title": str,
                "created_at": str,
                "cost_usd": float,
                "cost_krw": int,
                "breakdown": {"gpt4o": 0.10, "dalle3": 3.20, "tts": 0.05},
                "image_count": int,
                "reused_images": int,
            },
            ...
        ]
    """
    from history.history_manager import get_all

    records = get_all(limit=limit)
    results: list[dict] = []

    for r in records:
        cost = r.get("cost_usd", 0.0)
        results.append({
            "id": r["id"],
            "title": r.get("title_ko", "") or r.get("title_en", "Untitled"),
            "created_at": r.get("created_at", ""),
            "cost_usd": round(cost, 4),
            "cost_krw": int(cost * 1380),
            "breakdown": r.get("cost_breakdown") or {},
            "image_count": r.get("image_count", 0),
            "reused_images": r.get("reused_images", 0),
        })

    return results


# ─────────────────────────────────────────────
# 이미지 재사용 절감 분석
# ─────────────────────────────────────────────

def reuse_savings_report() -> dict:
    """
    이미지 재사용으로 절약한 비용을 분석한다.

    반환:
        {
            "total_generated": int,     총 생성 이미지 수
            "total_reused": int,        재사용 이미지 수
            "reuse_rate": float,        재사용률 (%)
            "cost_saved_usd": float,    절감 비용 (USD)
            "cost_saved_krw": int,      절감 비용 (KRW)
        }
    """
    from history.history_manager import get_all

    all_records = get_all(limit=10000)
    total_images = sum(r.get("image_count", 0) for r in all_records)
    total_reused = sum(r.get("reused_images", 0) for r in all_records)

    unit_cost = (
        config.COST_DALLE3_HD_PER_IMAGE
        if config.IMAGE_QUALITY == "hd"
        else config.COST_DALLE3_STD_PER_IMAGE
    )
    saved = total_reused * unit_cost
    total_generated = total_images  # image_count는 이미 재사용 포함 (전체 사용 이미지)

    return {
        "total_generated": total_generated,
        "total_reused": total_reused,
        "reuse_rate": round(total_reused / total_generated * 100, 1) if total_generated else 0.0,
        "cost_saved_usd": round(saved, 4),
        "cost_saved_krw": int(saved * 1380),
    }


# ─────────────────────────────────────────────
# 카테고리별 비용 분석
# ─────────────────────────────────────────────

def cost_by_category() -> dict[str, float]:
    """
    전체 비용을 카테고리별로 집계한다.

    반환: {"gpt4o": float, "dalle3": float, "tts": float, "pixabay": float}
    """
    from history.history_manager import get_all

    totals: dict[str, float] = {
        "gpt4o": 0.0,
        "dalle3": 0.0,
        "tts": 0.0,
        "pixabay": 0.0,
    }

    all_records = get_all(limit=10000)
    for r in all_records:
        breakdown = r.get("cost_breakdown") or {}
        for key in totals:
            totals[key] += breakdown.get(key, 0.0)

    return {k: round(v, 4) for k, v in totals.items()}


# ─────────────────────────────────────────────
# 포맷팅 유틸
# ─────────────────────────────────────────────

def format_summary_text() -> str:
    """
    전체 비용 요약을 읽기 쉬운 텍스트로 반환한다.
    CLI 또는 로깅에서 사용.
    """
    s = total_summary()
    by_cat = cost_by_category()
    savings = reuse_savings_report()

    lines = [
        f"총 비용: ${s['total_cost_usd']:.4f} (약 {s['total_cost_krw']:,}원)",
        f"총 영상: {s['total_videos']}편 / 평균 ${s['avg_cost_per_video']:.4f}/편",
        f"",
        f"카테고리별 비용:",
        f"  GPT-4o   : ${by_cat['gpt4o']:.4f}",
        f"  DALL-E 3 : ${by_cat['dalle3']:.4f}",
        f"  TTS      : ${by_cat['tts']:.4f}",
        f"",
        f"이미지 재사용 절감:",
        f"  재사용: {savings['total_reused']}장 ({savings['reuse_rate']:.1f}%)",
        f"  절감액: ${savings['cost_saved_usd']:.4f} (약 {savings['cost_saved_krw']:,}원)",
    ]
    return "\n".join(lines)
