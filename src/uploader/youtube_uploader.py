"""
uploader/youtube_uploader.py — YouTube Data API v3 업로드

resumable upload로 대용량 영상 파일을 안정적으로 업로드한다.
업로드 완료 후 thumbnails.set으로 썸네일을 설정한다.
"""

import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB — resumable 청크 크기
_MAX_RETRIES = 5                # 서버 오류 시 최대 재시도 횟수
_RETRY_STATUSES = {500, 502, 503, 504}  # 재시도 대상 HTTP 상태 코드


def upload_video(
    video_path: str,
    thumbnail_path: str,
    metadata: dict,
    lang: str = "ko",
) -> str:
    """
    YouTube에 영상을 업로드하고 썸네일을 설정한다.

    video_path:     업로드할 .mp4 파일 경로
    thumbnail_path: 썸네일 .jpg 파일 경로
    metadata:       metadata_builder.build_metadata() 반환값
    lang:           "ko" | "en" (채널 OAuth 토큰 선택에 사용)
    반환: 업로드된 영상의 video_id (str)
    """
    try:
        from googleapiclient.http import MediaFileUpload
        from googleapiclient.errors import HttpError
    except ImportError as e:
        raise UploadError(
            "google-api-python-client 미설치.\n"
            "pip install google-api-python-client"
        ) from e

    from uploader.oauth_handler import get_authenticated_service

    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"영상 파일 없음: {video_path}")

    youtube = get_authenticated_service(lang)

    logger.info("[%s] 업로드 시작: %s (%.1f MB)", lang, video_path.name,
                video_path.stat().st_size / 1024 / 1024)

    video_id = _upload_file(youtube, video_path, metadata)
    logger.info("[%s] 업로드 완료 — video_id: %s", lang, video_id)

    thumb_path = Path(thumbnail_path) if thumbnail_path else None
    if thumb_path and thumb_path.exists():
        _set_thumbnail(youtube, video_id, thumb_path)
        logger.info("[%s] 썸네일 설정 완료", lang)
    else:
        logger.warning("[%s] 썸네일 파일 없음 — 건너뜀: %s", lang, thumbnail_path)

    return video_id


# ─────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────

def _upload_file(youtube, video_path: Path, metadata: dict) -> str:
    """
    resumable upload를 실행하고 video_id를 반환한다.
    서버 오류(5xx) 발생 시 지수적 대기 후 재시도한다.
    """
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError

    body = {
        "snippet": metadata["snippet"],
        "status":  metadata["status"],
    }
    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        chunksize=_CHUNK_SIZE,
        resumable=True,
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    retry = 0

    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                logger.info("  [업로드] %d%% (%s)", pct, video_path.name)

        except HttpError as e:
            if e.resp.status in _RETRY_STATUSES:
                retry += 1
                if retry > _MAX_RETRIES:
                    raise UploadError(
                        f"최대 재시도 초과 (HTTP {e.resp.status}): {video_path.name}"
                    ) from e
                wait = 2 ** retry  # 지수적 대기: 2, 4, 8, 16, 32초
                logger.warning(
                    "서버 오류 %d — %d초 후 재시도 (%d/%d)",
                    e.resp.status, wait, retry, _MAX_RETRIES,
                )
                time.sleep(wait)
            else:
                raise UploadError(
                    f"업로드 실패 (HTTP {e.resp.status}): {e.reason}"
                ) from e

        except Exception as e:
            retry += 1
            if retry > _MAX_RETRIES:
                raise UploadError(f"예상치 못한 업로드 오류: {e}") from e
            wait = 2 ** retry
            logger.warning("업로드 오류 — %d초 후 재시도: %s", wait, e)
            time.sleep(wait)

    video_id: str = response.get("id", "")
    if not video_id:
        raise UploadError("업로드 응답에 video_id 없음")
    return video_id


def _set_thumbnail(youtube, video_id: str, thumbnail_path: Path) -> None:
    """
    업로드된 영상에 썸네일을 설정한다.
    썸네일 실패는 영상 업로드 자체를 실패시키지 않는다.
    """
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError

    media = MediaFileUpload(str(thumbnail_path), mimetype="image/jpeg")
    try:
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=media,
        ).execute()
    except HttpError as e:
        logger.warning("썸네일 설정 실패 (video_id=%s, HTTP %d): %s",
                       video_id, e.resp.status, e.reason)
    except Exception as e:
        logger.warning("썸네일 설정 오류 (video_id=%s): %s", video_id, e)


class UploadError(Exception):
    """업로드 실패 시 발생."""
