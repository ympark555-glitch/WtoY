"""
scraper/fetcher.py — URL 요청 + HTML 수집
requests로 URL을 가져오고 raw HTML 문자열을 반환한다.
JavaScript 렌더링이 필요한 페이지는 정적 HTML만 수집하며
JS 의존 콘텐츠는 parser 단계에서 부분적으로 보완된다.
"""

import logging

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

_TIMEOUT_SEC: int = 20
_MAX_RETRIES: int = 3
_RETRY_BACKOFF: float = 1.0   # 재시도 간격 (초), exponential: 1, 2, 4...


def fetch_page(url: str, timeout: int = _TIMEOUT_SEC) -> str:
    """
    URL에서 HTML을 수집하고 문자열로 반환한다.

    Args:
        url: 수집할 웹페이지 URL
        timeout: 요청 타임아웃 (초)

    Returns:
        HTML 문자열

    Raises:
        FetchError: 수집 실패 시 (타임아웃 / 연결 오류 / HTTP 오류)
    """
    if not url or not url.startswith(("http://", "https://")):
        raise FetchError(f"유효하지 않은 URL: {url!r}")

    session = _build_session()
    logger.info("페이지 수집 시작: %s", url)

    try:
        response = session.get(
            url,
            headers=_DEFAULT_HEADERS,
            timeout=timeout,
            allow_redirects=True,
        )
        response.raise_for_status()

        # 인코딩 자동 감지 (chardet / charset-normalizer)
        # apparent_encoding이 None 이면 utf-8 폴백
        encoding = response.apparent_encoding or "utf-8"
        response.encoding = encoding
        html = response.text

        logger.info(
            "수집 완료: %s (%d bytes, 인코딩: %s, 상태: %d)",
            url, len(response.content), encoding, response.status_code,
        )
        return html

    except requests.exceptions.Timeout:
        raise FetchError(f"타임아웃: {url} (제한: {timeout}초)")
    except requests.exceptions.TooManyRedirects:
        raise FetchError(f"리다이렉트 초과: {url}")
    except requests.exceptions.ConnectionError as e:
        raise FetchError(f"연결 오류: {url} — {e}")
    except requests.exceptions.HTTPError as e:
        code = e.response.status_code if e.response is not None else "?"
        raise FetchError(f"HTTP {code} 오류: {url}")
    except requests.exceptions.RequestException as e:
        raise FetchError(f"요청 실패: {url} — {e}")


def _build_session() -> requests.Session:
    """재시도 로직이 내장된 HTTP 세션을 생성한다."""
    session = requests.Session()
    retry = Retry(
        total=_MAX_RETRIES,
        backoff_factor=_RETRY_BACKOFF,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,   # raise_for_status는 fetch_page에서 직접 처리
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


class FetchError(Exception):
    """페이지 수집 실패 시 발생."""
