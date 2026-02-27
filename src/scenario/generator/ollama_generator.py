"""
scenario/generator/ollama_generator.py — Ollama 로컬 LLM 시나리오 생성

Ollama /api/chat HTTP 엔드포인트를 직접 호출한다 (ollama Python 패키지 미의존).
로컬 엔진이므로 비용 추적 없이 그대로 통과한다.
"""

import json
import logging
from pathlib import Path
from typing import Optional

import requests

import config
from core.cost_tracker import CostTracker

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
_PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"

_VALID_STAGES = frozenset({"hook", "problem", "core", "twist", "cta"})
# Ollama 응답이 너무 길면 파싱 부하가 크므로 상한 설정
_MAX_RESPONSE_CHARS = 120_000


def generate_scenario(
    page_text: str,
    focus: str = "",
    cost_tracker: Optional[CostTracker] = None,
) -> dict:
    """
    Ollama 로컬 LLM으로 5분 시나리오를 생성한다.

    Args:
        page_text: 웹페이지 본문 텍스트
        focus: 포커스 키워드 (선택)
        cost_tracker: 로컬 엔진이므로 비용 기록 없이 통과

    Returns:
        {"scenes": [...], "title_ko": "..."}
    """
    system_prompt = _load_system_prompt()
    user_prompt = _build_user_prompt(page_text, focus)
    last_result: Optional[dict] = None

    for attempt in range(1, MAX_RETRIES + 1):
        logger.info(
            "Ollama 시나리오 생성 시도 %d/%d (모델: %s)",
            attempt, MAX_RETRIES, config.OLLAMA_MODEL,
        )

        try:
            raw = _call_ollama(system_prompt, user_prompt)
        except requests.exceptions.ConnectionError:
            logger.error(
                "Ollama 연결 실패 — %s 가 실행 중인지 확인하세요.", config.OLLAMA_HOST
            )
            break
        except Exception as e:
            logger.error("Ollama API 호출 실패 (시도 %d): %s", attempt, e)
            continue

        result = _parse_response(raw)
        if result is None:
            logger.warning("JSON 파싱 실패 (시도 %d)", attempt)
            continue

        last_result = result
        issues = _check_scene_issues(result.get("scenes", []))
        if not issues:
            logger.info("시나리오 생성 성공: %d장면", len(result["scenes"]))
            return result

        logger.warning("검증 실패 (시도 %d): %s", attempt, " / ".join(issues))
        user_prompt = _build_user_prompt(page_text, focus, issues)

    # 최대 재시도 초과 또는 연결 실패
    if last_result:
        logger.warning(
            "최대 재시도 초과 — 마지막 결과 반환 (%d장면)",
            len(last_result.get("scenes", [])),
        )
        return last_result

    logger.error("시나리오 생성 완전 실패 — 빈 결과 반환")
    return {"scenes": [], "title_ko": "untitled"}


# ─────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────

def _call_ollama(system_prompt: str, user_prompt: str) -> str:
    """
    Ollama /api/chat 엔드포인트를 호출하고 content 문자열을 반환한다.
    stream=False로 단일 JSON 응답을 받는다.
    format="json"은 모델이 지원하는 경우 구조화된 출력을 강제한다.
    """
    url = f"{config.OLLAMA_HOST.rstrip('/')}/api/chat"
    payload = {
        "model": config.OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.8,
            "num_predict": 8000,
        },
    }

    resp = requests.post(url, json=payload, timeout=300)
    resp.raise_for_status()

    data = resp.json()
    content: str = data.get("message", {}).get("content", "")
    return content[:_MAX_RESPONSE_CHARS]


def _load_system_prompt() -> str:
    """scenario_system.txt를 읽는다. 없으면 gpt_generator의 인라인 프롬프트 공유."""
    path = _PROMPTS_DIR / "scenario_system.txt"
    if path.exists():
        return path.read_text(encoding="utf-8")
    logger.warning("scenario_system.txt 없음 — gpt_generator 인라인 프롬프트 사용")
    from scenario.generator.gpt_generator import _INLINE_SYSTEM_PROMPT
    return _INLINE_SYSTEM_PROMPT


def _build_user_prompt(page_text: str, focus: str, issues: Optional[list] = None) -> str:
    parts: list[str] = []
    if focus:
        parts.append(f"[포커스 주제]: {focus}")
    parts.append(f"[기사/페이지 내용]:\n{page_text}")
    if issues:
        parts.append(f"[이전 생성 문제점 — 반드시 수정]: {' | '.join(issues)}")
    return "\n\n".join(parts)


def _parse_response(raw: str) -> Optional[dict]:
    """
    JSON 파싱 후 scene 필드를 정규화한다.
    Ollama는 응답 앞뒤에 마크다운 코드블록(```json ... ```)을 붙이는 경우가 있어 제거한다.
    """
    cleaned = _strip_markdown_codeblock(raw.strip())

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.error("JSON 디코드 오류: %s | raw preview: %s...", e, cleaned[:200])
        return None

    if not isinstance(data.get("scenes"), list):
        logger.warning("scenes 키 누락 또는 타입 불일치")
        return None
    if not isinstance(data.get("title_ko"), str):
        data["title_ko"] = "untitled"

    normalized = []
    for i, s in enumerate(data["scenes"]):
        if not isinstance(s, dict):
            continue
        s.setdefault("scene_id", i + 1)
        s.setdefault("stage", "core")
        s.setdefault("narration", "")
        s.setdefault("duration_sec", 3)
        s.setdefault("image_prompt", "")
        s.setdefault("text_overlay", "")

        try:
            s["duration_sec"] = float(s["duration_sec"])
        except (TypeError, ValueError):
            s["duration_sec"] = 3.0

        if s["stage"] not in _VALID_STAGES:
            logger.debug("scene[%d] 비정상 stage '%s' → 'core' 대체", i, s["stage"])
            s["stage"] = "core"

        normalized.append(s)

    data["scenes"] = normalized
    return data


def _strip_markdown_codeblock(text: str) -> str:
    """
    ```json ... ``` 또는 ``` ... ``` 블록 내부를 추출한다.
    코드블록이 없으면 원본 반환.
    """
    if not text.startswith("```"):
        return text

    lines = text.splitlines()
    inner: list[str] = []
    in_block = False
    for line in lines:
        if not in_block and line.startswith("```"):
            in_block = True
            continue
        if in_block and line.startswith("```"):
            break
        if in_block:
            inner.append(line)

    return "\n".join(inner) if inner else text


def _check_scene_issues(scenes: list) -> list[str]:
    """재생성이 필요한 문제점 목록을 반환한다."""
    issues: list[str] = []
    if len(scenes) < config.MIN_SCENES:
        issues.append(f"장면 수 부족 ({len(scenes)}개, 최소 {config.MIN_SCENES}개 필요)")
    if scenes:
        avg_dur = sum(s.get("duration_sec", 3) for s in scenes) / len(scenes)
        if avg_dur > 5.0:
            issues.append(f"장면 평균 길이 과다 ({avg_dur:.1f}초, 최대 5초)")
    return issues
