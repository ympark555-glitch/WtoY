"""
uploader/oauth_handler.py — Google OAuth2 인증 처리

한국어 채널("ko")과 영어 채널("en")의 토큰을 분리 관리한다.
토큰 파일이 있으면 재사용하고, 만료 시 자동 갱신한다.
토큰이 없으면 브라우저를 열어 신규 인증한다.
"""

import logging
import pickle
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# YouTube 업로드 + 채널 관리에 필요한 최소 스코프
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]


def _get_token_path(lang: str) -> Path:
    """채널별 토큰 파일 경로를 반환한다."""
    import config
    return config.DATABASE_DIR / f"token_{lang}.pickle"


def get_authenticated_service(lang: str = "ko"):
    """
    Google OAuth2 인증 후 YouTube API 서비스 객체를 반환한다.

    lang: "ko" (한국어 채널) | "en" (영어 채널)
    반환: googleapiclient.discovery.Resource (youtube v3)

    최초 실행 시 브라우저 인증 창이 열린다.
    이후에는 저장된 토큰(token_{lang}.pickle)을 재사용한다.
    """
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as e:
        raise OAuthError(
            "Google 인증 라이브러리 미설치.\n"
            "pip install google-auth google-auth-oauthlib google-auth-httplib2 "
            "google-api-python-client"
        ) from e

    import config

    token_path = _get_token_path(lang)
    creds: Optional[Credentials] = None

    # 저장된 토큰 로드
    if token_path.exists():
        try:
            with open(token_path, "rb") as f:
                creds = pickle.load(f)
            logger.debug("[%s] 저장된 OAuth 토큰 로드", lang)
        except Exception as e:
            logger.warning("[%s] 토큰 파일 손상 — 재인증 필요: %s", lang, e)
            creds = None

    # 토큰 갱신 또는 신규 인증
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                logger.info("[%s] OAuth 토큰 갱신 완료", lang)
            except Exception as e:
                logger.warning("[%s] 토큰 갱신 실패 — 재인증 진행: %s", lang, e)
                creds = None

        if not creds:
            client_secret = config.GOOGLE_CLIENT_SECRET_PATH
            if not client_secret:
                raise OAuthError(
                    "GOOGLE_CLIENT_SECRET_PATH가 설정되지 않았습니다.\n"
                    "설정 탭에서 Google OAuth2 클라이언트 시크릿 파일 경로를 입력하세요."
                )
            if not Path(client_secret).exists():
                raise OAuthError(f"클라이언트 시크릿 파일을 찾을 수 없습니다: {client_secret}")

            flow = InstalledAppFlow.from_client_secrets_file(client_secret, SCOPES)
            # GUI 환경에서는 redirect_uri를 별도로 처리해야 할 수 있으나
            # 현재는 로컬 서버 방식으로 처리
            creds = flow.run_local_server(port=0)
            logger.info("[%s] OAuth 신규 인증 완료", lang)

        # 토큰 저장 (다음 실행에서 재사용)
        try:
            with open(token_path, "wb") as f:
                pickle.dump(creds, f)
            logger.debug("[%s] 토큰 저장 완료: %s", lang, token_path)
        except Exception as e:
            logger.warning("[%s] 토큰 저장 실패 (다음 실행 시 재인증 필요): %s", lang, e)

    return build("youtube", "v3", credentials=creds)


def revoke_token(lang: str = "ko") -> None:
    """저장된 OAuth 토큰을 삭제해 다음 실행 시 재인증을 강제한다."""
    token_path = _get_token_path(lang)
    if token_path.exists():
        token_path.unlink()
        logger.info("[%s] OAuth 토큰 삭제 완료", lang)
    else:
        logger.info("[%s] 삭제할 토큰 파일 없음", lang)


def is_authenticated(lang: str = "ko") -> bool:
    """저장된 유효 토큰이 있는지 확인한다 (API 호출 없음)."""
    token_path = _get_token_path(lang)
    if not token_path.exists():
        return False
    try:
        with open(token_path, "rb") as f:
            creds = pickle.load(f)
        return creds is not None and (creds.valid or bool(creds.refresh_token))
    except Exception:
        return False


class OAuthError(Exception):
    """OAuth 인증 실패 시 발생."""
