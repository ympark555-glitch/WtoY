"""
scenario/generator/gpt_generator.py — GPT-4o 시나리오 생성

page_text를 입력받아 Scene JSON 배열과 YouTube 제목을 생성한다.
검증 실패(장면 수 부족 / 평균 duration 과다) 시 최대 MAX_RETRIES회 재생성한다.
"""

import json
import logging
from pathlib import Path
from typing import Optional

import config
from core.cost_tracker import CostTracker

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
_PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"

_VALID_STAGES = frozenset({"hook", "problem", "core", "twist", "cta"})


def generate_scenario(
    page_text: str,
    focus: str = "",
    cost_tracker: Optional[CostTracker] = None,
) -> dict:
    """
    GPT-4o로 5분 시나리오를 생성한다.

    Args:
        page_text: 웹페이지 본문 텍스트
        focus: 포커스 키워드 (선택)
        cost_tracker: 비용 추적기

    Returns:
        {"scenes": [...], "title_ko": "..."}
    """
    from openai import OpenAI

    client = OpenAI(api_key=config.OPENAI_API_KEY)
    system_prompt = _load_system_prompt()
    user_prompt = _build_user_prompt(page_text, focus)
    last_result: Optional[dict] = None

    for attempt in range(1, MAX_RETRIES + 1):
        logger.info("GPT-4o 시나리오 생성 시도 %d/%d", attempt, MAX_RETRIES)

        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.8,
                max_tokens=12000,
            )
        except Exception as e:
            logger.error("OpenAI API 호출 실패 (시도 %d): %s", attempt, e)
            continue

        if cost_tracker and response.usage:
            cost_tracker.add_gpt4o(
                input_tokens=response.usage.prompt_tokens,
                output_tokens=response.usage.completion_tokens,
            )

        raw = response.choices[0].message.content or ""
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

    # 최대 재시도 초과
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

def _load_system_prompt() -> str:
    path = _PROMPTS_DIR / "scenario_system.txt"
    if path.exists():
        return path.read_text(encoding="utf-8")
    logger.warning("scenario_system.txt 없음 — 인라인 기본 프롬프트 사용")
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
    """JSON 파싱 후 scene 필드를 정규화한다."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("JSON 디코드 오류: %s", e)
        return None

    if not isinstance(data.get("scenes"), list):
        logger.warning("scenes 키 누락 또는 타입 불일치")
        return None
    if not isinstance(data.get("title_ko"), str):
        logger.warning("title_ko 키 누락 또는 타입 불일치")
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

        # duration_sec float 보장
        try:
            s["duration_sec"] = float(s["duration_sec"])
        except (TypeError, ValueError):
            s["duration_sec"] = 3.0

        # 유효하지 않은 stage → core 대체
        if s["stage"] not in _VALID_STAGES:
            logger.debug("scene[%d] 비정상 stage '%s' → 'core' 대체", i, s["stage"])
            s["stage"] = "core"

        normalized.append(s)

    data["scenes"] = normalized
    return data


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


# ─────────────────────────────────────────────
# 인라인 폴백 프롬프트 (scenario_system.txt 없을 때)
# ─────────────────────────────────────────────
_INLINE_SYSTEM_PROMPT = """\
You are a YouTube short-form content writer. Create a highly engaging 5-minute video scenario.

Return ONLY valid JSON (no markdown, no explanation):
{
  "title_ko": "클릭유발형 유튜브 제목 30자이내",
  "scenes": [
    {
      "scene_id": 1,
      "stage": "hook",
      "narration": "한국어 내레이션 최대 15단어",
      "duration_sec": 3,
      "image_prompt": "English DALL-E 3 prompt, vivid and specific",
      "text_overlay": "핵심자막10자"
    }
  ]
}

Rules:
1. stage: hook | problem | core | twist | cta
2. Structure: hook(5~10) → problem(10~15) → core(40~60) → twist(10~15) → cta(5~10)
3. narration: Korean ONLY, max 15 words, punchy
4. duration_sec: 2~4 per scene
5. Total scenes: 80~100 (NEVER below 60)
6. Total duration sum: ~300 seconds
7. image_prompt: English ONLY, no real person names, style anchor at end:
   ", clean cartoon illustration, white background, flat design, high contrast"
8. text_overlay: Korean, max 10 characters
9. title_ko: under 30 chars, urgency/curiosity, include numbers if possible
"""
