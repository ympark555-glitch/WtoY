"""
core/checkpoint.py — 체크포인트 저장/복구
각 스텝 완료 시 state를 JSON으로 저장한다.
실패 시 마지막 완료된 스텝 이후부터 재시작할 수 있다.
"""

import json
import hashlib
import logging
from pathlib import Path
from typing import Optional

import config

logger = logging.getLogger(__name__)

CHECKPOINT_DIR = config.OUTPUT_DIR / ".checkpoints"
CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)


class Checkpoint:
    def __init__(self, url: str) -> None:
        url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
        self.path: Path = CHECKPOINT_DIR / f"{url_hash}.json"

    def save(self, state: dict, last_completed_step: int) -> None:
        data = {
            "last_completed_step": last_completed_step,
            "state": state,
        }
        try:
            self.path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.debug("체크포인트 저장: STEP %d → %s", last_completed_step, self.path)
        except Exception as e:
            logger.warning("체크포인트 저장 실패: %s", e)

    def load(self) -> Optional[dict]:
        if not self.path.exists():
            return None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            step = data.get("last_completed_step", 0)
            state = data.get("state", {})
            logger.info("체크포인트 복구: STEP %d까지 완료됨", step)
            return state
        except Exception as e:
            logger.warning("체크포인트 로드 실패 (무시): %s", e)
            return None

    def delete(self) -> None:
        if self.path.exists():
            self.path.unlink()
            logger.debug("체크포인트 삭제: %s", self.path)

    def last_completed_step(self) -> int:
        if not self.path.exists():
            return 0
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data.get("last_completed_step", 0)
        except Exception:
            return 0
