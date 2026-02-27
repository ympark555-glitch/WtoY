"""
thumbnail/prompt_generator.py — 썸네일 프롬프트 생성

시나리오 데이터를 GPT-4o(또는 Ollama)에 전달해
썸네일 이미지 프롬프트와 한/영 오버레이 텍스트를 생성한다.

Returns:
    {
        "image_prompt":    str  — DALL-E 3에 넘길 영어 이미지 프롬프트
        "overlay_text_ko": str  — 한국어 오버레이 텍스트 (최대 10자)
        "overlay_text_en": str  — 영어 오버레이 텍스트 (최대 4단어)
    }
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional

import config
from core.cost_tracker import CostTracker

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_DELAY_SEC = 5
_PROMPT_FILE = config.PROMPTS_DIR / "thumbnail_system.txt"

# GPT 응답 오버레이 텍스트 길이 제한
_KO_MAX_CHARS = 12   # 여유 있게 12자 (MD 규격 10자보다 약간 여유)
_EN_MAX_WORDS = 5    # 여유 있게 5단어

# 폴백 프롬프트 (thumbnail_system.txt 로드 실패 시)
_FALLBACK_SYSTEM = (
    "You are a YouTube thumbnail expert. "
    "Reply ONLY with a JSON object containing exactly these keys: "
    "image_prompt, overlay_text_ko, overlay_text_en. "
    "No extra text outside the JSON."
)


def generate_thumbnail_prompt(
    title_ko: str,
    title_en: str,
    scenes: list[dict],
    cost_tracker: Optional[CostTracker] = None,
) -> dict:
    """
    GPT-4o(또는 Ollama)로 썸네일 이미지 프롬프트 + 오버레이 텍스트를 생성한다.

    Args:
        title_ko:     한국어 유튜브 제목
        title_en:     영어 유튜브 제목
        scenes:       시나리오 장면 리스트 (narration, stage, image_prompt 포함)
        cost_tracker: 비용 추적기

    Returns:
        {"image_prompt": str, "overlay_text_ko": str, "overlay_text_en": str}
        실패 시 타이틀 기반 폴백 dict 반환
    """
    system_prompt = _load_system_prompt()
    user_msg = _build_user_message(title_ko, title_en, scenes)

    if config.SCENARIO_ENGINE == "gpt4o":
        return _call_gpt4o(system_prompt, user_msg, cost_tracker)
    else:
        return _call_ollama(system_prompt, user_msg)


# ─────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────

def _load_system_prompt() -> str:
    """thumbnail_system.txt를 읽는다. 없으면 인라인 폴백 사용."""
    if _PROMPT_FILE.exists():
        return _PROMPT_FILE.read_text(encoding="utf-8")
    logger.warning("thumbnail_system.txt 없음 — 인라인 폴백 사용")
    return _FALLBACK_SYSTEM


def _build_user_message(title_ko: str, title_en: str, scenes: list[dict]) -> str:
    """GPT-4o에 전달할 영상 정보 요약 메시지를 구성한다."""
    hook_scenes = [s for s in scenes if s.get("stage") == "hook"][:3]
    hook_narrations = " / ".join(
        s.get("narration", "") for s in hook_scenes if s.get("narration")
    )
    first_image_hint = hook_scenes[0].get("image_prompt", "") if hook_scenes else ""

    cta_scenes = [s for s in scenes if s.get("stage") == "cta"][:2]
    cta_narrations = " / ".join(
        s.get("narration", "") for s in cta_scenes if s.get("narration")
    )

    return (
        f"[영상 제목 (한국어)]: {title_ko}\n"
        f"[영상 제목 (영어)]: {title_en}\n"
        f"[훅 내레이션]: {hook_narrations or '없음'}\n"
        f"[CTA 내레이션]: {cta_narrations or '없음'}\n"
        f"[훅 이미지 힌트]: {first_image_hint or '없음'}\n\n"
        "위 정보를 바탕으로 최고 CTR을 이끌어낼 썸네일을 설계하세요."
    )


def _call_gpt4o(
    system_prompt: str,
    user_msg: str,
    cost_tracker: Optional[CostTracker],
) -> dict:
    from openai import OpenAI

    client = OpenAI(api_key=config.OPENAI_API_KEY)

    for attempt in range(1, _MAX_RETRIES + 1):
        logger.debug("GPT-4o 썸네일 프롬프트 생성 시도 %d/%d", attempt, _MAX_RETRIES)
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.8,
                max_tokens=512,
            )
        except Exception as e:
            logger.error("GPT-4o 썸네일 API 오류 (시도 %d): %s", attempt, e)
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_DELAY_SEC * attempt)
                continue
            return _fallback_result(user_msg)

        raw = response.choices[0].message.content or ""

        if cost_tracker and response.usage:
            cost_tracker.add_gpt4o(
                response.usage.prompt_tokens,
                response.usage.completion_tokens,
            )

        result = _parse_response(raw)
        if result:
            logger.info("썸네일 프롬프트 생성 완료")
            return result

        logger.warning("GPT-4o 응답 파싱 실패 (시도 %d) — 재시도", attempt)

    return _fallback_result(user_msg)


def _call_ollama(system_prompt: str, user_msg: str) -> dict:
    """Ollama 로컬 엔진으로 썸네일 프롬프트를 생성한다."""
    try:
        import requests

        url = f"{config.OLLAMA_HOST.rstrip('/')}/api/chat"
        payload = {
            "model": config.OLLAMA_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.8, "num_predict": 512},
        }
        resp = requests.post(url, json=payload, timeout=120)
        resp.raise_for_status()
        raw: str = resp.json().get("message", {}).get("content", "")

        result = _parse_response(raw)
        if result:
            return result

    except requests.exceptions.ConnectionError:
        logger.error("Ollama 연결 실패 — %s 가 실행 중인지 확인하세요.", config.OLLAMA_HOST)
    except Exception as e:
        logger.error("Ollama 썸네일 프롬프트 오류: %s", e)

    return _fallback_result("")


def _parse_response(raw: str) -> Optional[dict]:
    """
    GPT/Ollama 응답에서 JSON을 파싱해 필수 키를 검증한다.
    Ollama 마크다운 코드블록 제거 후 파싱.
    """
    cleaned = _strip_markdown_codeblock(raw.strip())
    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning("썸네일 프롬프트 JSON 파싱 오류: %s | 미리보기: %s...", e, cleaned[:100])
        return None

    required = {"image_prompt", "overlay_text_ko", "overlay_text_en"}
    if not required.issubset(data.keys()):
        missing = required - data.keys()
        logger.warning("썸네일 프롬프트 응답 키 누락: %s", missing)
        return None

    return {
        "image_prompt": str(data["image_prompt"]).strip(),
        "overlay_text_ko": str(data["overlay_text_ko"]).strip()[:_KO_MAX_CHARS],
        "overlay_text_en": " ".join(
            str(data["overlay_text_en"]).split()[:_EN_MAX_WORDS]
        ),
    }


def _strip_markdown_codeblock(text: str) -> str:
    """```json ... ``` 또는 ``` ... ``` 블록 내부를 추출한다."""
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


def _fallback_result(context: str) -> dict:
    """API 실패 시 최소한의 폴백 결과를 반환한다."""
    logger.warning("썸네일 프롬프트 폴백 사용")
    return {
        "image_prompt": (
            "dramatic close-up illustration, bold subject positioned left third, "
            "high contrast background with single accent color, "
            "shock and curiosity emotion, clean modern editorial style, "
            "white space on right side for text, no text in image"
        ),
        "overlay_text_ko": "충격 공개",
        "overlay_text_en": "Shocking Truth",
    }
