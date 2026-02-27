"""
analytics/youtube_analytics.py — 유튜브 성과 트래킹

YouTube Analytics API (v2) 및 YouTube Data API (v3)를 사용해
업로드된 영상의 조회수, CTR, 구독 증가 등 성과 지표를 조회한다.

통계 탭에서 영상별·채널별 성과 현황을 표시할 때 사용된다.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# Analytics API 스코프 (OAuth에 추가 필요)
ANALYTICS_SCOPES = [
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/youtube.readonly",
]


def _get_youtube_service(lang: str = "ko"):
    """기존 OAuth 토큰으로 YouTube Data API v3 서비스를 가져온다."""
    from uploader.oauth_handler import get_authenticated_service
    return get_authenticated_service(lang)


def _get_analytics_service(lang: str = "ko"):
    """
    YouTube Analytics API v2 서비스 객체를 반환한다.

    주의: Analytics API는 youtube.readonly + yt-analytics.readonly 스코프가
    필요하므로, oauth_handler의 SCOPES에 추가되어야 한다.
    현재는 Data API로 가능한 범위까지만 조회하고,
    Analytics 전용 지표(CTR 등)는 Analytics API가 설정된 경우에만 동작한다.
    """
    try:
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
        import pickle
        import config

        token_path = config.DATABASE_DIR / f"token_{lang}.pickle"
        if not token_path.exists():
            return None

        with open(token_path, "rb") as f:
            creds = pickle.load(f)

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())

        return build("youtubeAnalytics", "v2", credentials=creds)
    except Exception as e:
        logger.debug("Analytics API 서비스 생성 실패: %s", e)
        return None


# ─────────────────────────────────────────────
# Data API 기반 성과 조회
# ─────────────────────────────────────────────

def get_video_stats(video_id: str, lang: str = "ko") -> Optional[dict]:
    """
    특정 영상의 기본 통계를 조회한다 (Data API v3).

    반환:
        {
            "video_id": str,
            "title": str,
            "view_count": int,
            "like_count": int,
            "comment_count": int,
            "published_at": str,
        }
    """
    try:
        youtube = _get_youtube_service(lang)
        response = youtube.videos().list(
            part="snippet,statistics",
            id=video_id,
        ).execute()

        items = response.get("items", [])
        if not items:
            logger.warning("영상을 찾을 수 없음: %s", video_id)
            return None

        item = items[0]
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})

        return {
            "video_id": video_id,
            "title": snippet.get("title", ""),
            "view_count": int(stats.get("viewCount", 0)),
            "like_count": int(stats.get("likeCount", 0)),
            "comment_count": int(stats.get("commentCount", 0)),
            "published_at": snippet.get("publishedAt", ""),
        }
    except Exception as e:
        logger.error("영상 통계 조회 실패 (%s): %s", video_id, e)
        return None


def get_multi_video_stats(video_ids: list[str], lang: str = "ko") -> list[dict]:
    """
    여러 영상의 통계를 한 번에 조회한다 (최대 50개씩 배치).

    반환: get_video_stats와 동일한 dict의 리스트
    """
    results: list[dict] = []

    try:
        youtube = _get_youtube_service(lang)
    except Exception as e:
        logger.error("YouTube 서비스 초기화 실패: %s", e)
        return results

    # Data API는 id 파라미터에 최대 50개까지 허용
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        try:
            response = youtube.videos().list(
                part="snippet,statistics",
                id=",".join(batch),
            ).execute()

            for item in response.get("items", []):
                snippet = item.get("snippet", {})
                stats = item.get("statistics", {})
                results.append({
                    "video_id": item["id"],
                    "title": snippet.get("title", ""),
                    "view_count": int(stats.get("viewCount", 0)),
                    "like_count": int(stats.get("likeCount", 0)),
                    "comment_count": int(stats.get("commentCount", 0)),
                    "published_at": snippet.get("publishedAt", ""),
                })
        except Exception as e:
            logger.error("배치 통계 조회 실패: %s", e)

    return results


def get_channel_stats(lang: str = "ko") -> Optional[dict]:
    """
    채널의 전체 통계를 조회한다 (Data API v3).

    반환:
        {
            "channel_id": str,
            "title": str,
            "subscriber_count": int,
            "total_view_count": int,
            "video_count": int,
        }
    """
    try:
        youtube = _get_youtube_service(lang)
        response = youtube.channels().list(
            part="snippet,statistics",
            mine=True,
        ).execute()

        items = response.get("items", [])
        if not items:
            logger.warning("채널 정보를 찾을 수 없음 (lang=%s)", lang)
            return None

        item = items[0]
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})

        return {
            "channel_id": item["id"],
            "title": snippet.get("title", ""),
            "subscriber_count": int(stats.get("subscriberCount", 0)),
            "total_view_count": int(stats.get("viewCount", 0)),
            "video_count": int(stats.get("videoCount", 0)),
        }
    except Exception as e:
        logger.error("채널 통계 조회 실패 (lang=%s): %s", lang, e)
        return None


# ─────────────────────────────────────────────
# Analytics API 기반 심화 지표
# ─────────────────────────────────────────────

def get_video_analytics(
    video_id: str,
    lang: str = "ko",
    days: int = 28,
) -> Optional[dict]:
    """
    YouTube Analytics API로 영상의 심화 지표를 조회한다.

    반환:
        {
            "video_id": str,
            "views": int,
            "estimated_minutes_watched": float,
            "average_view_duration": float,
            "impressions": int,
            "impressions_ctr": float,  (%)
            "subscribers_gained": int,
            "subscribers_lost": int,
        }
    또는 Analytics API 미설정 시 None
    """
    analytics = _get_analytics_service(lang)
    if not analytics:
        logger.debug("Analytics API 미사용 — 심화 지표 건너뜀")
        return None

    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    try:
        response = analytics.reports().query(
            ids="channel==MINE",
            startDate=start_date,
            endDate=end_date,
            metrics=(
                "views,estimatedMinutesWatched,averageViewDuration,"
                "impressions,impressionClickThroughRate,"
                "subscribersGained,subscribersLost"
            ),
            filters=f"video=={video_id}",
        ).execute()

        rows = response.get("rows", [])
        if not rows:
            return None

        row = rows[0]
        return {
            "video_id": video_id,
            "views": int(row[0]),
            "estimated_minutes_watched": float(row[1]),
            "average_view_duration": float(row[2]),
            "impressions": int(row[3]),
            "impressions_ctr": round(float(row[4]) * 100, 2),
            "subscribers_gained": int(row[5]),
            "subscribers_lost": int(row[6]),
        }
    except Exception as e:
        logger.error("Analytics 조회 실패 (%s): %s", video_id, e)
        return None


# ─────────────────────────────────────────────
# 히스토리 연동 편의 함수
# ─────────────────────────────────────────────

def fetch_stats_for_history(record: dict) -> list[dict]:
    """
    history_manager의 record dict에서 video_ids를 추출하고
    각 영상의 통계를 조회한다.

    record["video_ids"]: {"landscape_ko": "xxx", "landscape_en": "yyy", ...}
    반환: get_video_stats 결과 리스트
    """
    video_ids_map = record.get("video_ids") or {}
    if not video_ids_map:
        return []

    results: list[dict] = []
    for key, vid in video_ids_map.items():
        if not vid:
            continue
        lang = "en" if key.endswith("_en") else "ko"
        stats = get_video_stats(vid, lang=lang)
        if stats:
            stats["type"] = key  # "landscape_ko", "shorts_en" 등
            results.append(stats)

    return results
