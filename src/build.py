"""
build.py — 빌드 자동화 스크립트

사용법:
    python build.py              기본 빌드 (현재 OS)
    python build.py --clean      빌드 전 build/dist 정리
    python build.py --onefile    단일 exe 모드 (onefile)
    python build.py --debug      콘솔 출력 포함 디버그 빌드

빌드 결과:
    dist/webpage-to-youtube/         (기본: onedir 모드)
    dist/webpage-to-youtube.exe      (--onefile 모드)
"""

import argparse
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("build")

# 프로젝트 경로
SRC_DIR = Path(__file__).parent
SPEC_FILE = SRC_DIR / "webpage-to-youtube.spec"
BUILD_DIR = SRC_DIR / "build"
DIST_DIR = SRC_DIR / "dist"


def check_prerequisites() -> bool:
    """빌드 전 필수 조건을 확인한다."""
    ok = True

    # PyInstaller 설치 확인
    try:
        import PyInstaller
        logger.info("PyInstaller %s 감지", PyInstaller.__version__)
    except ImportError:
        logger.error("PyInstaller가 설치되지 않았습니다: pip install pyinstaller")
        ok = False

    # PyQt6 설치 확인
    try:
        from PyQt6.QtCore import PYQT_VERSION_STR
        logger.info("PyQt6 %s 감지", PYQT_VERSION_STR)
    except ImportError:
        logger.error("PyQt6가 설치되지 않았습니다: pip install PyQt6")
        ok = False

    # ffmpeg 확인
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            first_line = result.stdout.split("\n")[0]
            logger.info("ffmpeg 감지: %s", first_line.strip())
        else:
            logger.warning("ffmpeg 실행 실패 — 영상 합성 기능이 동작하지 않을 수 있음")
    except FileNotFoundError:
        logger.warning("ffmpeg를 찾을 수 없음 — PATH에 ffmpeg를 추가하세요")

    # spec 파일 확인
    if not SPEC_FILE.exists():
        logger.error("spec 파일 없음: %s", SPEC_FILE)
        ok = False

    return ok


def clean_build() -> None:
    """build/ 및 dist/ 디렉토리를 삭제한다."""
    for d in (BUILD_DIR, DIST_DIR):
        if d.exists():
            logger.info("삭제: %s", d)
            shutil.rmtree(d)
    # __pycache__ 정리
    for cache in SRC_DIR.rglob("__pycache__"):
        shutil.rmtree(cache)
        logger.info("삭제: %s", cache)


def build_with_spec(debug: bool = False) -> bool:
    """spec 파일을 사용해 빌드한다."""
    cmd = [
        sys.executable, "-m", "PyInstaller",
        str(SPEC_FILE),
        "--distpath", str(DIST_DIR),
        "--workpath", str(BUILD_DIR),
        "--noconfirm",
    ]

    if debug:
        cmd.append("--log-level=DEBUG")

    logger.info("빌드 명령: %s", " ".join(cmd))
    result = subprocess.run(cmd, cwd=str(SRC_DIR))
    return result.returncode == 0


def build_onefile(debug: bool = False) -> bool:
    """단일 실행 파일 모드로 빌드한다."""
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", "webpage-to-youtube",
        "--distpath", str(DIST_DIR),
        "--workpath", str(BUILD_DIR),
        "--noconfirm",
    ]

    if not debug:
        cmd.append("--windowed")

    # 데이터 파일
    cmd.extend(["--add-data", f"{SRC_DIR / 'prompts' / '*.txt'}{os.pathsep}prompts"])
    cmd.extend(["--add-data", f"{SRC_DIR / 'assets' / 'fonts'}{os.pathsep}assets/fonts"])
    cmd.extend(["--add-data", f"{SRC_DIR / 'assets' / 'bgm'}{os.pathsep}assets/bgm"])

    # 숨겨진 임포트 (주요 동적 import만)
    for mod in [
        "scenario.generator.gpt_generator",
        "scenario.generator.ollama_generator",
        "image.generator.dalle_generator",
        "image.generator.sd_generator",
        "tts.openai_tts",
        "tts.edge_tts",
        "langdetect",
        "bs4",
        "lxml",
        "PIL",
        "pydub",
        "dotenv",
        "edge_tts",
        "moviepy",
        "moviepy.editor",
        "gui.app",
    ]:
        cmd.extend(["--hidden-import", mod])

    # 제외 모듈
    for mod in ["tkinter", "matplotlib", "pandas", "scipy"]:
        cmd.extend(["--exclude-module", mod])

    cmd.append(str(SRC_DIR / "main.py"))

    logger.info("빌드 명령: %s", " ".join(cmd))
    result = subprocess.run(cmd, cwd=str(SRC_DIR))
    return result.returncode == 0


def verify_build() -> bool:
    """빌드 결과물을 검증한다."""
    # onedir 결과 확인
    onedir = DIST_DIR / "webpage-to-youtube"
    if onedir.exists():
        if sys.platform == "win32":
            exe = onedir / "webpage-to-youtube.exe"
        else:
            exe = onedir / "webpage-to-youtube"

        if exe.exists():
            size_mb = exe.stat().st_size / (1024 * 1024)
            logger.info("빌드 성공: %s (%.1f MB)", exe, size_mb)

            # 번들 데이터 확인
            prompts_dir = onedir / "_internal" / "prompts"
            if not prompts_dir.exists():
                prompts_dir = onedir / "prompts"
            if prompts_dir.exists():
                txt_count = len(list(prompts_dir.glob("*.txt")))
                logger.info("프롬프트 파일: %d개", txt_count)
            else:
                logger.warning("프롬프트 디렉토리 미발견 — 번들 데이터 누락 가능")

            return True

    # onefile 결과 확인
    if sys.platform == "win32":
        onefile = DIST_DIR / "webpage-to-youtube.exe"
    else:
        onefile = DIST_DIR / "webpage-to-youtube"

    if onefile.exists():
        size_mb = onefile.stat().st_size / (1024 * 1024)
        logger.info("빌드 성공 (onefile): %s (%.1f MB)", onefile, size_mb)
        return True

    logger.error("빌드 결과물을 찾을 수 없습니다")
    return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Webpage to YouTube 빌드 스크립트",
    )
    parser.add_argument(
        "--clean", action="store_true",
        help="빌드 전 build/dist 디렉토리 정리",
    )
    parser.add_argument(
        "--onefile", action="store_true",
        help="단일 실행 파일 모드 (기본: onedir)",
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="콘솔 출력 포함 디버그 빌드",
    )
    parser.add_argument(
        "--skip-check", action="store_true",
        help="사전 조건 검사 건너뛰기",
    )
    args = parser.parse_args()

    logger.info("=" * 50)
    logger.info("Webpage to YouTube 빌드 시작")
    logger.info("플랫폼: %s", sys.platform)
    logger.info("Python: %s", sys.version.split()[0])
    logger.info("=" * 50)

    # 사전 조건 확인
    if not args.skip_check:
        if not check_prerequisites():
            logger.error("사전 조건 미충족 — 빌드 중단")
            sys.exit(1)

    # 정리
    if args.clean:
        clean_build()

    # 빌드 실행
    if args.onefile:
        success = build_onefile(debug=args.debug)
    else:
        success = build_with_spec(debug=args.debug)

    if not success:
        logger.error("빌드 실패")
        sys.exit(1)

    # 결과 검증
    if verify_build():
        logger.info("=" * 50)
        logger.info("빌드 완료!")
        logger.info("출력 경로: %s", DIST_DIR)
        logger.info("=" * 50)
    else:
        logger.error("빌드 검증 실패")
        sys.exit(1)


if __name__ == "__main__":
    main()
