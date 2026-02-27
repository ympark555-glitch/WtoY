"""
scraper/parser.py — 핵심 텍스트 추출
BeautifulSoup4 + lxml으로 HTML 본문에서 의미 있는 텍스트를 추출한다.
focus 키워드가 있으면 해당 단락을 앞으로 배치한다.
"""

import logging
import re
from typing import Optional

from bs4 import BeautifulSoup, NavigableString, Tag

logger = logging.getLogger(__name__)

# ── 제거할 노이즈 태그 ────────────────────────────────────────
_NOISE_TAGS = frozenset({
    "script", "style", "noscript", "iframe", "nav", "footer",
    "header", "aside", "form", "button", "input", "select",
    "textarea", "svg", "canvas", "meta", "link",
})

# ── 본문 후보 CSS 선택자 (우선순위 순) ────────────────────────
_CONTENT_SELECTORS = [
    "article",
    "main",
    "[role='main']",
    ".post-content",
    ".article-content",
    ".entry-content",
    ".post-body",
    ".article-body",
    ".content-body",
    ".content",
    "#content",
    "#main",
    "#article",
]

# ── 텍스트 수집 대상 태그 ─────────────────────────────────────
_TEXT_TAGS = (
    "h1", "h2", "h3", "h4", "h5", "h6",
    "p", "li", "blockquote", "td", "th",
    "dd", "dt", "pre", "figcaption",
)

# 최소 유효 길이 (이보다 짧은 조각은 노이즈로 간주)
_MIN_FRAGMENT_LEN = 15

# GPT 토큰 절약을 위한 최대 텍스트 길이
_MAX_TEXT_LENGTH = 8_000


def extract_text(html: str, focus: str = "") -> str:
    """
    HTML에서 핵심 본문 텍스트를 추출한다.

    Args:
        html: raw HTML 문자열
        focus: 주목할 키워드/주제 (있으면 해당 단락을 앞으로 배치)

    Returns:
        정제된 본문 텍스트. 최대 8,000자.
    """
    if not html or not html.strip():
        logger.warning("빈 HTML 입력")
        return ""

    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        # lxml 실패 시 html.parser 폴백
        soup = BeautifulSoup(html, "html.parser")

    # 노이즈 태그 제거 (in-place)
    for tag in soup.find_all(_NOISE_TAGS):
        tag.decompose()

    # 본문 영역 탐색
    content_node = _find_content_node(soup)

    # 텍스트 조각 수집
    if focus and focus.strip():
        text = _extract_with_focus(content_node, focus.strip())
    else:
        text = _collect_fragments(content_node)

    text = _clean_text(text)

    # 추출 결과가 너무 짧으면 전체 body에서 재시도
    if len(text) < 200 and content_node is not soup:
        logger.warning(
            "본문 추출 텍스트 부족 (%d자), 전체 body에서 재시도", len(text)
        )
        fallback_node = soup.body if soup.body else soup
        text = _clean_text(_collect_fragments(fallback_node))

    # 최대 길이 제한
    if len(text) > _MAX_TEXT_LENGTH:
        text = text[:_MAX_TEXT_LENGTH] + "\n[...이하 생략...]"
        logger.info("텍스트 길이 초과, %d자로 잘림", _MAX_TEXT_LENGTH)

    logger.info("텍스트 추출 완료: %d자", len(text))
    return text


# ─────────────────────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────────────────────

def _find_content_node(soup: BeautifulSoup) -> Tag:
    """
    본문 콘텐츠 노드를 우선순위 선택자로 탐색한다.
    유효한 노드를 찾지 못하면 body(없으면 soup 전체)를 반환한다.
    """
    for selector in _CONTENT_SELECTORS:
        try:
            node = soup.select_one(selector)
        except Exception:
            continue
        if node and len(node.get_text(strip=True)) > 200:
            logger.debug("본문 노드 선택: selector='%s'", selector)
            return node

    logger.debug("특정 본문 노드 없음 — body 전체 사용")
    return soup.body if soup.body else soup


def _collect_fragments(node: Tag) -> str:
    """
    노드 내 모든 텍스트 태그에서 조각을 수집해 하나의 문자열로 합친다.
    중복 제거: 부모-자식 관계에서 같은 텍스트가 두 번 나오는 걸 방지한다.
    """
    seen: set[str] = set()
    parts: list[str] = []

    for elem in node.find_all(_TEXT_TAGS):
        # 하위 블록 태그가 없는 리프 수준 텍스트만 직접 수집
        # (예: <p>안에 <h2>가 없으면 정상 수집)
        child_block = elem.find(_TEXT_TAGS)
        if child_block is not None:
            continue

        t = elem.get_text(separator=" ", strip=True)
        if len(t) < _MIN_FRAGMENT_LEN:
            continue
        # 중복 조각 제거
        key = t[:80]
        if key in seen:
            continue
        seen.add(key)
        parts.append(t)

    return "\n".join(parts)


def _extract_with_focus(node: Tag, focus: str) -> str:
    """
    focus 키워드 포함 단락을 앞으로 배치하고, 나머지를 뒤에 이어 붙인다.
    """
    keywords = [k.lower() for k in re.split(r"[\s,]+", focus.lower()) if k]

    seen: set[str] = set()
    prioritized: list[str] = []
    rest: list[str] = []

    for elem in node.find_all(_TEXT_TAGS):
        # 리프 수준만 수집 (중복 방지)
        if elem.find(_TEXT_TAGS) is not None:
            continue

        t = elem.get_text(separator=" ", strip=True)
        if len(t) < _MIN_FRAGMENT_LEN:
            continue

        key = t[:80]
        if key in seen:
            continue
        seen.add(key)

        if any(kw in t.lower() for kw in keywords):
            prioritized.append(t)
        else:
            rest.append(t)

    logger.debug(
        "focus '%s' 관련 단락: %d개 / 기타: %d개",
        focus, len(prioritized), len(rest),
    )
    return "\n".join(prioritized + rest)


def _clean_text(text: str) -> str:
    """
    텍스트 정제:
    - 탭 → 공백
    - 줄 내 연속 공백 → 단일 공백
    - 3줄 이상 연속 빈 줄 → 2줄
    - 각 줄 앞뒤 공백 제거
    """
    text = text.replace("\t", " ")
    text = re.sub(r" {2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    lines = [line.strip() for line in text.splitlines()]

    result: list[str] = []
    prev_empty = False
    for line in lines:
        if not line:
            if not prev_empty:
                result.append("")
            prev_empty = True
        else:
            result.append(line)
            prev_empty = False

    return "\n".join(result).strip()
