"""
core/cost_tracker.py — 실시간 비용 계산
각 API 호출 후 비용을 누적하며, GUI의 cost_display에 콜백으로 전달한다.
"""

import logging
from typing import Callable, Optional

import config

logger = logging.getLogger(__name__)

# 비용 변경 알림 콜백 타입
CostCallback = Callable[[float], None]


class CostTracker:
    def __init__(self, on_update: Optional[CostCallback] = None) -> None:
        self._on_update = on_update
        self._costs: dict[str, float] = {
            "gpt4o": 0.0,
            "dalle3": 0.0,
            "tts": 0.0,
            "pixabay": 0.0,
        }

    # ─────────────────────────────────────────────
    # 비용 추가 메서드
    # ─────────────────────────────────────────────
    def add_gpt4o(self, input_tokens: int, output_tokens: int) -> float:
        cost = (
            input_tokens  / 1000 * config.COST_GPT4O_INPUT_PER_1K
            + output_tokens / 1000 * config.COST_GPT4O_OUTPUT_PER_1K
        )
        self._costs["gpt4o"] += cost
        self._notify()
        logger.debug("GPT-4o 비용 +$%.4f (in=%d, out=%d)", cost, input_tokens, output_tokens)
        return cost

    def add_dalle3(self, count: int = 1) -> float:
        unit = (
            config.COST_DALLE3_HD_PER_IMAGE
            if config.IMAGE_QUALITY == "hd"
            else config.COST_DALLE3_STD_PER_IMAGE
        )
        cost = unit * count
        self._costs["dalle3"] += cost
        self._notify()
        logger.debug("DALL-E 3 비용 +$%.4f (%d장)", cost, count)
        return cost

    def add_tts(self, char_count: int) -> float:
        cost = char_count / 1000 * config.COST_TTS_PER_1K_CHARS
        self._costs["tts"] += cost
        self._notify()
        logger.debug("TTS 비용 +$%.4f (%d자)", cost, char_count)
        return cost

    # ─────────────────────────────────────────────
    # 조회
    # ─────────────────────────────────────────────
    def total_usd(self) -> float:
        return sum(self._costs.values())

    def total_krw(self, rate: float = 1380.0) -> int:
        return int(self.total_usd() * rate)

    def breakdown(self) -> dict[str, float]:
        return dict(self._costs)

    def summary_str(self) -> str:
        t = self.total_usd()
        krw = self.total_krw()
        return (
            f"총 비용: ${t:.4f} (약 {krw:,}원)\n"
            f"  GPT-4o   : ${self._costs['gpt4o']:.4f}\n"
            f"  DALL-E 3 : ${self._costs['dalle3']:.4f}\n"
            f"  TTS      : ${self._costs['tts']:.4f}"
        )

    # ─────────────────────────────────────────────
    # 콜백
    # ─────────────────────────────────────────────
    def set_callback(self, callback: CostCallback) -> None:
        self._on_update = callback

    def _notify(self) -> None:
        if self._on_update:
            self._on_update(self.total_usd())
