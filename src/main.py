"""
main.py — 파이프라인 실행 진입점
CLI 모드: python main.py --url <URL> [--focus <focus>] [--step <N>]
GUI 모드: python main.py  (인자 없이 실행 시 GUI 실행)
"""

import sys
import argparse
import logging
from pathlib import Path

# 패키지 루트를 sys.path에 추가 (PyInstaller 빌드 호환)
sys.path.insert(0, str(Path(__file__).parent))

from core.pipeline import Pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")


def run_cli(url: str, focus: str = "", resume_step: int = 0) -> None:
    """CLI 모드로 파이프라인을 실행한다."""
    pipeline = Pipeline(url=url, focus=focus)
    pipeline.run(from_step=resume_step)


def run_gui() -> None:
    """GUI 모드를 실행한다."""
    try:
        from gui.app import App
        app = App()
        app.run()
    except ImportError as e:
        logger.error("GUI 모듈을 불러올 수 없습니다: %s", e)
        logger.info("CLI 모드 사용: python main.py --url <URL>")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Webpage to YouTube 자동화 파이프라인",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--url", type=str, help="변환할 웹페이지 URL")
    parser.add_argument(
        "--focus",
        type=str,
        default="",
        help="포커스 입력 (선택사항) — 이 부분을 중심으로 시나리오 생성",
    )
    parser.add_argument(
        "--step",
        type=int,
        default=0,
        metavar="N",
        help="재시작할 스텝 번호 (0=체크포인트 자동 감지, 기본값: 0)",
    )
    args = parser.parse_args()

    if args.url:
        run_cli(url=args.url, focus=args.focus, resume_step=args.step)
    else:
        run_gui()


if __name__ == "__main__":
    main()
