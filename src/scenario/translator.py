"""
scenario/translator.py — 한/영 분기 + 번역

한국어 시나리오의 narration·text_overlay·title을 영어로 번역한다.
image_prompt는 이미 영어이므로 번역하지 않는다.
20장면씩 청크로 분할해 GPT-4o를 호출한다.
"""

import json
import logging
from typing import Optional

import config
from core.cost_tracker import CostTracker

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 20   # 한 번에 번역할 최대 장면 수

_SCENE_TRANSLATE_SYSTEM = """\
You are a professional Korean-to-English translator for YouTube video scripts.
Translate the "narration" and "text_overlay" fields from Korean to natural, engaging English.

Rules:
- narration: max 15 words, punchy and fast-paced
- text_overlay: max 5 words, ultra-compressed keyword
- scene_id: keep exactly as-is (integer)
- image_prompt: DO NOT translate, keep exactly as-is
- Return ONLY valid JSON: {"translations": [{"scene_id": N, "narration": "...", "text_overlay": "..."}, ...]}
"""

_TITLE_TRANSLATE_SYSTEM = """\
Translate this Korean YouTube title to English.
Make it catchy, click-worthy, and under 70 characters.
Include numbers if present. Create urgency or curiosity.
Return ONLY the English title string. No quotes. No JSON.
"""


def translate_scenario(
    scenes: list,
    title: str,
    cost_tracker: Optional[CostTracker] = None,
) -> tuple:
    """
    한국어 시나리오를 영어로 번역한다.

    Args:
        scenes: 한국어 scene 목록
        title: 한국어 유튜브 제목
        cost_tracker: 비용 추적기

    Returns:
        (영어 scene 목록, 영어 제목) tuple
    """
    scenes_en = _translate_scenes(scenes, cost_tracker)
    title_en = _translate_title(title, cost_tracker)
    return scenes_en, title_en


# ─────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────

def _translate_scenes(scenes: list, cost_tracker: Optional[CostTracker]) -> list:
    """
    장면 목록을 _CHUNK_SIZE씩 나눠 번역한 뒤 합친다.
    번역 실패 청크는 원본(한국어)을 그대로 사용한다.
    """
    if not scenes:
        return []

    all_translated: list = []
    for i in range(0, len(scenes), _CHUNK_SIZE):
        chunk = scenes[i : i + _CHUNK_SIZE]
        translated_chunk = _translate_chunk(chunk, cost_tracker)
        all_translated.extend(translated_chunk)

    logger.info("번역 완료: %d장면", len(all_translated))
    return all_translated


def _translate_chunk(scenes: list, cost_tracker: Optional[CostTracker]) -> list:
    """청크 단위로 GPT-4o를 호출해 번역하고 원본 scene에 병합한다."""
    # 번역 대상 필드만 전송 (image_prompt 제외)
    payload = [
        {
            "scene_id": s["scene_id"],
            "narration": s.get("narration", ""),
            "text_overlay": s.get("text_overlay", ""),
        }
        for s in scenes
    ]

    translated_list = _call_gpt_translate(
        system=_SCENE_TRANSLATE_SYSTEM,
        user=json.dumps(payload, ensure_ascii=False),
        cost_tracker=cost_tracker,
    )

    if translated_list is None:
        logger.warning("번역 실패 — 원본(한국어) 반환")
        return [dict(s) for s in scenes]

    # scene_id → 번역 결과 매핑
    # GPT가 scene_id를 정수로 반환하지 않을 수 있으므로 str→int 변환 처리
    trans_map: dict[int, dict] = {}
    for t in translated_list:
        if not isinstance(t, dict):
            continue
        try:
            sid = int(t.get("scene_id", -1))
        except (TypeError, ValueError):
            continue
        trans_map[sid] = t

    # 원본 scene에 번역 결과 병합 (image_prompt, stage, duration_sec 등은 원본 유지)
    result: list = []
    for s in scenes:
        new_s = dict(s)
        sid = s["scene_id"]
        if sid in trans_map:
            new_s["narration"] = trans_map[sid].get("narration") or s.get("narration", "")
            new_s["text_overlay"] = trans_map[sid].get("text_overlay") or s.get("text_overlay", "")
        result.append(new_s)

    return result


def _call_gpt_translate(
    system: str,
    user: str,
    cost_tracker: Optional[CostTracker],
) -> Optional[list]:
    """
    GPT-4o 번역 API를 호출하고 번역 결과 list를 반환한다.
    실패 시 None 반환.
    """
    try:
        from openai import OpenAI
        client = OpenAI(api_key=config.OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=4000,
        )
    except Exception as e:
        logger.error("GPT 번역 API 호출 실패: %s", e)
        return None

    if cost_tracker and response.usage:
        cost_tracker.add_gpt4o(
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
        )

    raw = response.choices[0].message.content or ""
    return _parse_translation(raw)


def _parse_translation(raw: str) -> Optional[list]:
    """
    GPT 번역 응답에서 list를 추출한다.
    GPT는 {"translations": [...]} 형태로 반환하도록 프롬프트했지만
    {"scenes": [...]} 또는 [...] 형태로 올 수도 있어 유연하게 처리한다.
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("번역 JSON 파싱 오류: %s", e)
        return None

    # 직접 list 반환 (response_format json_object 규칙상 드물지만 방어)
    if isinstance(data, list):
        return data

    # dict인 경우 알려진 키에서 list 추출
    if isinstance(data, dict):
        for key in ("translations", "scenes", "data", "results"):
            val = data.get(key)
            if isinstance(val, list):
                return val

    logger.warning("번역 결과에서 list를 찾을 수 없음: keys=%s", list(data.keys()) if isinstance(data, dict) else type(data))
    return None


def _translate_title(title: str, cost_tracker: Optional[CostTracker]) -> str:
    """유튜브 제목을 영어로 번역한다. 실패 시 원본 반환."""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=config.OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": _TITLE_TRANSLATE_SYSTEM},
                {"role": "user", "content": title},
            ],
            temperature=0.5,
            max_tokens=100,
        )
    except Exception as e:
        logger.error("제목 번역 API 호출 실패: %s", e)
        return title

    if cost_tracker and response.usage:
        cost_tracker.add_gpt4o(
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
        )

    # GPT가 제목을 따옴표로 감싸 반환하는 경우 제거
    en_title = (response.choices[0].message.content or "").strip().strip("\"'")
    logger.info("제목 번역: '%s' → '%s'", title, en_title)
    return en_title if en_title else title
