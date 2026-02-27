"""
config.py — 전역 설정 + 기본값
설정 탭에서 변경된 값은 이 파일을 통해 런타임에 반영된다.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# ─────────────────────────────────────────────
# 경로 (PyInstaller frozen 모드 대응)
# ─────────────────────────────────────────────
if getattr(sys, 'frozen', False):
    # PyInstaller로 빌드된 실행 파일
    _BUNDLE_DIR = Path(sys._MEIPASS)
    BASE_DIR = Path(sys.executable).parent
else:
    _BUNDLE_DIR = Path(__file__).parent
    BASE_DIR = Path(__file__).parent

OUTPUT_DIR = BASE_DIR / "output"
ASSETS_DIR = _BUNDLE_DIR / "assets"
DATABASE_DIR = BASE_DIR / "database"
PROMPTS_DIR = _BUNDLE_DIR / "prompts"

OUTPUT_DIR.mkdir(exist_ok=True)
DATABASE_DIR.mkdir(exist_ok=True)

# ─────────────────────────────────────────────
# API 키 (환경변수 우선, 설정 탭에서 덮어쓰기 가능)
# ─────────────────────────────────────────────
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
PIXABAY_API_KEY: str = os.getenv("PIXABAY_API_KEY", "")
GOOGLE_CLIENT_SECRET_PATH: str = os.getenv("GOOGLE_CLIENT_SECRET_PATH", "")

# ─────────────────────────────────────────────
# 엔진 선택 ("gpt4o" | "ollama") / ("dalle3" | "sd") / ("openai" | "edge")
# ─────────────────────────────────────────────
SCENARIO_ENGINE: str = "gpt4o"
IMAGE_ENGINE: str = "dalle3"
TTS_ENGINE: str = "openai"

# Ollama 설정 (로컬 엔진 선택 시)
OLLAMA_HOST: str = "http://localhost:11434"
OLLAMA_MODEL: str = "llama3.1"

# Stable Diffusion 설정 (로컬 엔진 선택 시)
SD_API_URL: str = "http://localhost:7860"

# ─────────────────────────────────────────────
# 유튜브 채널
# ─────────────────────────────────────────────
YOUTUBE_KO_CHANNEL_ID: str = os.getenv("YOUTUBE_KO_CHANNEL_ID", "")
YOUTUBE_EN_CHANNEL_ID: str = os.getenv("YOUTUBE_EN_CHANNEL_ID", "")
YOUTUBE_PRIVACY: str = "public"          # "public" | "unlisted" | "private"
YOUTUBE_CATEGORY_ID: str = "22"          # 22 = People & Blogs
YOUTUBE_SCHEDULE_ENABLED: bool = False

# ─────────────────────────────────────────────
# 영상 품질
# ─────────────────────────────────────────────
VIDEO_RESOLUTION: str = "1080p"          # "1080p" | "720p" | "480p"
VIDEO_BITRATE: str = "4000k"
VIDEO_FPS: int = 24

RESOLUTION_MAP = {
    "1080p": (1920, 1080),
    "720p":  (1280,  720),
    "480p":  (854,   480),
}

def get_landscape_resolution() -> tuple[int, int]:
    return RESOLUTION_MAP.get(VIDEO_RESOLUTION, (1920, 1080))

def get_shorts_resolution() -> tuple[int, int]:
    w, h = get_landscape_resolution()
    return (h, w)   # 9:16

# ─────────────────────────────────────────────
# 시나리오 & 템포
# ─────────────────────────────────────────────
TARGET_DURATION_SEC: int = 300          # 5분
SHORTS_DURATION_SEC: int = 60           # 1분
SCENE_TARGET_SEC: float = 3.0           # 장면당 목표 시간 (초)
MIN_SCENES: int = 60
TARGET_SCENES: int = 80
NARRATIVE_TONE: str = "informative"     # "informative" | "dramatic" | "casual"
HOOK_INTENSITY: str = "high"            # "low" | "medium" | "high"

# ─────────────────────────────────────────────
# 이미지 스타일 (자연어, 사용자 수정 가능)
# ─────────────────────────────────────────────
IMAGE_STYLE_DEFAULT = (
    "clean cartoon illustration style, "
    "minimal and modern design, "
    "black and white line art with selective color accent, "
    "only the most important element highlighted in a single bold accent color, "
    "flat design, simple shapes, sophisticated and elegant, "
    "white background, high contrast, editorial style, "
    "not childish, sleek and refined visual tone"
)
IMAGE_STYLE: str = IMAGE_STYLE_DEFAULT
IMAGE_QUALITY: str = "hd"              # "hd" | "standard"
IMAGE_BATCH_SIZE: int = 10             # 병렬 배치 처리 단위

# ─────────────────────────────────────────────
# TTS 음성
# ─────────────────────────────────────────────
TTS_SPEED: float = 1.0
TTS_KO_VOICE: str = "nova"             # OpenAI: alloy|echo|fable|onyx|nova|shimmer
TTS_EN_VOICE: str = "echo"
EDGE_TTS_KO_VOICE: str = "ko-KR-SunHiNeural"
EDGE_TTS_EN_VOICE: str = "en-US-AriaNeural"

# ─────────────────────────────────────────────
# BGM
# ─────────────────────────────────────────────
BGM_VOLUME_RATIO: float = 0.15         # TTS 대비 BGM 볼륨 (0.10 ~ 0.40)
BGM_CACHE_DIR = ASSETS_DIR / "bgm"
BGM_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# stage → Pixabay 검색 키워드 매핑
BGM_STAGE_MAP = {
    "hook":    "dramatic intense",
    "problem": "dramatic intense",
    "core":    "energetic upbeat",
    "twist":   "dramatic intense",
    "cta":     "motivational",
}

# ─────────────────────────────────────────────
# 자막
# ─────────────────────────────────────────────
SUBTITLE_ENABLED: bool = True
SUBTITLE_FONT_SIZE: int = 36
SUBTITLE_POSITION: str = "bottom"      # "top" | "center" | "bottom"
SUBTITLE_COLOR: str = "white"
SUBTITLE_STROKE_COLOR: str = "black"
SUBTITLE_STROKE_WIDTH: int = 2

FONT_KO_PATH = ASSETS_DIR / "fonts" / "korean_bold.ttf"
FONT_EN_PATH = ASSETS_DIR / "fonts" / "english_bold.ttf"

# ─────────────────────────────────────────────
# 유사 이미지 재사용
# ─────────────────────────────────────────────
IMAGE_SIMILARITY_THRESHOLD: float = 0.80   # 80% 이상이면 재사용 팝업

# ─────────────────────────────────────────────
# 비용 단가 (USD)
# ─────────────────────────────────────────────
COST_GPT4O_INPUT_PER_1K: float = 0.005
COST_GPT4O_OUTPUT_PER_1K: float = 0.015
COST_DALLE3_HD_PER_IMAGE: float = 0.080
COST_DALLE3_STD_PER_IMAGE: float = 0.040
COST_TTS_PER_1K_CHARS: float = 0.015

# ─────────────────────────────────────────────
# 데이터베이스
# ─────────────────────────────────────────────
HISTORY_DB_PATH = DATABASE_DIR / "history.db"
IMAGE_CACHE_DB_PATH = DATABASE_DIR / "image_cache.db"

# ─────────────────────────────────────────────
# 런타임 설정 업데이트 (GUI 설정 탭에서 호출)
# ─────────────────────────────────────────────
def apply_settings(settings: dict) -> None:
    """GUI 설정 탭에서 전달받은 dict를 전역 변수에 반영한다."""
    g = globals()
    for key, value in settings.items():
        if key in g:
            g[key] = value
