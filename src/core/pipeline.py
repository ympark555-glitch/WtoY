"""
core/pipeline.py — 전체 스텝 순서 관리
STEP 1~11 을 순서대로 실행하며 각 스텝 완료 시 체크포인트를 저장한다.
컨펌이 필요한 STEP 2, 11은 confirm_callback으로 GUI/CLI와 통신한다.
"""

import logging
from typing import Callable, Optional

from core.checkpoint import Checkpoint
from core.cost_tracker import CostTracker

logger = logging.getLogger(__name__)

# 컨펌 콜백 타입: (message: str, data: dict) -> bool
ConfirmCallback = Callable[[str, dict], bool]

# 진행 콜백 타입: (step: int, total: int, desc: str, pct: float) -> None
ProgressCallback = Callable[[int, int, str, float], None]


class Pipeline:
    TOTAL_STEPS = 11

    def __init__(
        self,
        url: str,
        focus: str = "",
        confirm_callback: Optional[ConfirmCallback] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> None:
        self.url = url
        self.focus = focus
        self.confirm_callback = confirm_callback or self._cli_confirm
        self.progress_callback = progress_callback or self._cli_progress

        self.checkpoint = Checkpoint(url=url)
        self.cost_tracker = CostTracker()

        # 파이프라인 공유 상태 (각 스텝이 여기에 결과를 기록)
        self.state: dict = self.checkpoint.load() or {
            "url": url,
            "focus": focus,
            "page_text": None,
            "page_lang": None,
            "scenario_ko": None,       # [{scene_id, stage, narration, duration_sec, image_prompt, text_overlay}]
            "scenario_en": None,
            "shorts_scenario_ko": None,
            "shorts_scenario_en": None,
            "youtube_title_ko": None,
            "youtube_title_en": None,
            "image_paths": [],         # scenes/ 아래 저장된 이미지 경로 목록
            "audio_ko_paths": [],
            "audio_en_paths": [],
            "bgm_path": None,
            "video_landscape_ko": None,
            "video_landscape_en": None,
            "video_shorts_ko": None,
            "video_shorts_en": None,
            "thumbnail_paths": {},
            "output_dir": None,
        }

    # ─────────────────────────────────────────────
    # 실행 진입점
    # ─────────────────────────────────────────────
    def run(self, from_step: int = 0) -> None:
        # BUG-01 FIX: from_step=0 이면 체크포인트에서 자동 결정
        if from_step == 0:
            from_step = self.checkpoint.last_completed_step() + 1
        logger.info("파이프라인 시작: %s (STEP %d부터)", self.url, from_step)

        steps = [
            (1,  "웹페이지 수집",           self._step1_scrape),
            (2,  "시나리오 생성",           self._step2_scenario),
            (3,  "쇼츠 시나리오 재구성",    self._step3_shorts_scenario),
            (4,  "한/영 버전 분기",          self._step4_translate),
            (5,  "이미지 생성",             self._step5_images),
            (6,  "TTS 음성 생성",            self._step6_tts),
            (7,  "BGM 선택",                self._step7_bgm),
            (8,  "영상 합성",               self._step8_compose),
            (9,  "썸네일 생성",             self._step9_thumbnails),
            (10, "결과물 저장",             self._step10_save),
            (11, "유튜브 업로드",           self._step11_upload),
        ]

        for step_num, step_name, step_fn in steps:
            if step_num < from_step:
                continue

            self._notify_progress(step_num, step_name, 0.0)
            logger.info("▶ STEP %d: %s", step_num, step_name)

            try:
                step_fn()
            except PipelineAborted:
                logger.info("파이프라인이 사용자에 의해 중단됐습니다.")
                return
            except Exception as e:
                logger.error("STEP %d 실패: %s", step_num, e, exc_info=True)
                self.checkpoint.save(self.state, last_completed_step=step_num - 1)
                raise

            self.checkpoint.save(self.state, last_completed_step=step_num)
            self._notify_progress(step_num, step_name, 1.0)
            logger.info("✔ STEP %d 완료", step_num)

        logger.info("파이프라인 완료! 총 비용: $%.4f", self.cost_tracker.total_usd())

    # ─────────────────────────────────────────────
    # STEP 구현 (각 대화에서 채워질 스텁)
    # ─────────────────────────────────────────────
    def _step1_scrape(self) -> None:
        from scraper.fetcher import fetch_page
        from scraper.parser import extract_text
        from scraper.language_detector import detect_language

        html = fetch_page(self.url)
        text = extract_text(html, focus=self.focus)
        lang = detect_language(text)

        self.state["page_text"] = text
        self.state["page_lang"] = lang
        logger.info("언어 감지: %s / 텍스트 길이: %d자", lang, len(text))

    def _step2_scenario(self) -> None:
        import config
        if config.SCENARIO_ENGINE == "gpt4o":
            from scenario.generator.gpt_generator import generate_scenario
        else:
            from scenario.generator.ollama_generator import generate_scenario

        from scenario.validator import validate_and_fix

        result = generate_scenario(
            page_text=self.state["page_text"],
            focus=self.state["focus"],
            cost_tracker=self.cost_tracker,
        )
        result = validate_and_fix(result, cost_tracker=self.cost_tracker)

        # 🔴 컨펌 대기
        confirmed = self.confirm_callback(
            "시나리오 생성 완료 — 확인 후 진행하세요.",
            {"scenario": result["scenes"], "title_ko": result["title_ko"]},
        )
        if not confirmed:
            raise PipelineAborted("시나리오 컨펌 거부")

        self.state["scenario_ko"] = result["scenes"]
        self.state["youtube_title_ko"] = result["title_ko"]

    def _step3_shorts_scenario(self) -> None:
        from scenario.shorts_builder import build_shorts_scenario

        self.state["shorts_scenario_ko"] = build_shorts_scenario(
            self.state["scenario_ko"]
        )

    def _step4_translate(self) -> None:
        from scenario.translator import translate_scenario

        self.state["scenario_en"], self.state["youtube_title_en"] = translate_scenario(
            scenes=self.state["scenario_ko"],
            title=self.state["youtube_title_ko"],
            cost_tracker=self.cost_tracker,
        )
        self.state["shorts_scenario_en"] = translate_scenario(
            scenes=self.state["shorts_scenario_ko"],
            title=self.state["youtube_title_ko"],
            cost_tracker=self.cost_tracker,
        )[0]

    def _step5_images(self) -> None:
        from image.batch_processor import generate_all

        scenes = self.state["scenario_ko"]   # image_prompt는 한/영 공통
        output_dir = self._ensure_output_dir() / "scenes"
        output_dir.mkdir(exist_ok=True)

        result = generate_all(
            scenes=scenes,
            output_dir=output_dir,
            cost_tracker=self.cost_tracker,
        )
        # generate_all returns {scene_id: Path} — scene_id 순으로 경로 리스트 변환
        self.state["image_paths"] = [str(result[sid]) for sid in sorted(result)]

    def _step6_tts(self) -> None:
        import config
        if config.TTS_ENGINE == "openai":
            from tts.openai_tts import synthesize
        else:
            from tts.edge_tts import synthesize

        from tts.duration_corrector import correct_durations

        audio_dir = self._ensure_output_dir() / "audio"
        ko_dir = audio_dir / "ko"
        en_dir = audio_dir / "en"
        ko_dir.mkdir(parents=True, exist_ok=True)
        en_dir.mkdir(parents=True, exist_ok=True)

        ko_paths = synthesize(
            scenes=self.state["scenario_ko"],
            lang="ko",
            output_dir=ko_dir,
            cost_tracker=self.cost_tracker,
        )
        en_paths = synthesize(
            scenes=self.state["scenario_en"],
            lang="en",
            output_dir=en_dir,
            cost_tracker=self.cost_tracker,
        )

        self.state["scenario_ko"] = correct_durations(self.state["scenario_ko"], ko_paths)
        self.state["scenario_en"] = correct_durations(self.state["scenario_en"], en_paths)
        self.state["audio_ko_paths"] = [str(p) for p in ko_paths]
        self.state["audio_en_paths"] = [str(p) for p in en_paths]

    def _step7_bgm(self) -> None:
        from bgm.stage_selector import select_bgm
        from bgm.pixabay_fetcher import fetch_bgm

        stage_counts = {}
        for scene in self.state["scenario_ko"]:
            stage_counts[scene["stage"]] = stage_counts.get(scene["stage"], 0) + 1

        # BUG-02 FIX: stage_counts가 비어 있으면 기본값 사용
        dominant_stage = max(stage_counts, key=stage_counts.get) if stage_counts else "core"
        bgm_url = select_bgm(dominant_stage)
        bgm_path = fetch_bgm(bgm_url, cache_dir=self._ensure_output_dir() / "bgm")
        self.state["bgm_path"] = str(bgm_path)

    def _step8_compose(self) -> None:
        from video.landscape_composer import compose_landscape
        from video.shorts_composer import compose_shorts

        video_dir = self._ensure_output_dir() / "videos"
        video_dir.mkdir(exist_ok=True)

        self.state["video_landscape_ko"] = str(compose_landscape(
            scenes=self.state["scenario_ko"],
            image_paths=self.state["image_paths"],
            audio_paths=self.state["audio_ko_paths"],
            bgm_path=self.state["bgm_path"],
            output_path=video_dir / "landscape_ko.mp4",
            lang="ko",
        ))
        self.state["video_landscape_en"] = str(compose_landscape(
            scenes=self.state["scenario_en"],
            image_paths=self.state["image_paths"],
            audio_paths=self.state["audio_en_paths"],
            bgm_path=self.state["bgm_path"],
            output_path=video_dir / "landscape_en.mp4",
            lang="en",
        ))
        self.state["video_shorts_ko"] = str(compose_shorts(
            scenes=self.state["shorts_scenario_ko"],
            image_paths=self.state["image_paths"],
            audio_paths=self.state["audio_ko_paths"],
            bgm_path=self.state["bgm_path"],
            output_path=video_dir / "shorts_ko.mp4",
            title=self.state["youtube_title_ko"],
            lang="ko",
        ))
        self.state["video_shorts_en"] = str(compose_shorts(
            scenes=self.state["shorts_scenario_en"],
            image_paths=self.state["image_paths"],
            audio_paths=self.state["audio_en_paths"],
            bgm_path=self.state["bgm_path"],
            output_path=video_dir / "shorts_en.mp4",
            title=self.state["youtube_title_en"],
            lang="en",
        ))

    def _step9_thumbnails(self) -> None:
        from thumbnail.prompt_generator import generate_thumbnail_prompt
        from thumbnail.image_generator import generate_both_base_images
        from thumbnail.text_overlay import generate_all_thumbnails

        thumb_dir = self._ensure_output_dir() / "thumbnails"
        thumb_dir.mkdir(exist_ok=True)

        prompt_result = generate_thumbnail_prompt(
            title_ko=self.state["youtube_title_ko"],
            title_en=self.state["youtube_title_en"],
            scenes=self.state["scenario_ko"],
            cost_tracker=self.cost_tracker,
        )
        prompt = prompt_result.get("prompt", "")

        base_images = generate_both_base_images(
            prompt=prompt,
            output_dir=thumb_dir,
            cost_tracker=self.cost_tracker,
        )

        paths = generate_all_thumbnails(
            base_landscape_path=base_images.get("landscape"),
            base_shorts_path=base_images.get("shorts"),
            overlay_text_ko=self.state["youtube_title_ko"],
            overlay_text_en=self.state["youtube_title_en"],
            output_dir=thumb_dir,
        )
        self.state["thumbnail_paths"] = {k: str(v) for k, v in paths.items() if v}

    def _step10_save(self) -> None:
        # 결과물은 이미 output_dir 아래에 저장돼 있으므로 경로 로깅만 수행
        logger.info("결과물 저장 경로: %s", self.state["output_dir"])

    def _step11_upload(self) -> None:
        from uploader.youtube_uploader import upload_video
        from uploader.metadata_builder import build_metadata

        # 🔴 최종 컨펌 대기
        confirmed = self.confirm_callback(
            "업로드 직전 최종 확인 — 4개 영상을 유튜브에 업로드합니다.",
            {
                "video_landscape_ko": self.state["video_landscape_ko"],
                "video_landscape_en": self.state["video_landscape_en"],
                "video_shorts_ko":    self.state["video_shorts_ko"],
                "video_shorts_en":    self.state["video_shorts_en"],
                "thumbnails":         self.state["thumbnail_paths"],
            },
        )
        if not confirmed:
            raise PipelineAborted("업로드 컨펌 거부")

        for lang, video_key, shorts_key in [
            ("ko", "video_landscape_ko", "video_shorts_ko"),
            ("en", "video_landscape_en", "video_shorts_en"),
        ]:
            meta_long  = build_metadata(self.state, lang=lang, is_shorts=False)
            meta_short = build_metadata(self.state, lang=lang, is_shorts=True)

            upload_video(
                video_path=self.state[video_key],
                thumbnail_path=self.state["thumbnail_paths"][f"landscape_{lang}"],
                metadata=meta_long,
                lang=lang,
            )
            upload_video(
                video_path=self.state[shorts_key],
                thumbnail_path=self.state["thumbnail_paths"][f"shorts_{lang}"],
                metadata=meta_short,
                lang=lang,
            )

    # ─────────────────────────────────────────────
    # 헬퍼
    # ─────────────────────────────────────────────
    def _ensure_output_dir(self):
        from pathlib import Path
        import config, re

        if self.state["output_dir"]:
            return Path(self.state["output_dir"])

        title = self.state.get("youtube_title_ko") or "untitled"
        safe = re.sub(r'[\\/:*?"<>|]', "_", title)[:80]
        output_dir = config.OUTPUT_DIR / safe
        output_dir.mkdir(parents=True, exist_ok=True)
        self.state["output_dir"] = str(output_dir)
        return output_dir

    def _notify_progress(self, step: int, desc: str, pct: float) -> None:
        if self.progress_callback:
            self.progress_callback(step, self.TOTAL_STEPS, desc, pct)

    @staticmethod
    def _cli_confirm(message: str, data: dict) -> bool:
        print(f"\n{'='*60}")
        print(f"🔴 컨펌 필요: {message}")
        if "scenario" in data:
            scenes = data["scenario"]
            print(f"   시나리오 장면 수: {len(scenes)}")
            for s in scenes[:3]:
                print(f"   [{s['stage']}] {s['narration']}")
            if len(scenes) > 3:
                print(f"   ... ({len(scenes) - 3}개 더)")
        print(f"{'='*60}")
        # BUG-03 FIX: 빈 입력은 거부로 처리 (실수 컨펌 방지)
        ans = input("계속 진행하시겠습니까? (y/n): ").strip().lower()
        return ans in ("y", "yes")

    @staticmethod
    def _cli_progress(step: int, total: int, desc: str, pct: float) -> None:
        bar_len = 30
        filled = int(bar_len * pct)
        bar = "█" * filled + "░" * (bar_len - filled)
        print(f"\r  STEP {step}/{total} [{bar}] {desc}", end="", flush=True)
        if pct >= 1.0:
            print()


class PipelineAborted(Exception):
    """사용자가 컨펌을 거부하거나 중단 요청 시 발생."""
