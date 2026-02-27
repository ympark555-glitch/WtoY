"""
gui/tabs/result_tab.py — 결과 탭

영상 미리보기 4종, 썸네일 미리보기 4종, 저장 경로 표시,
최종 업로드 컨펌 (업로드/취소) 기능.
"""

import logging

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QMessageBox, QFileDialog,
)
from PyQt6.QtCore import Qt

from gui.components.video_preview import VideoPreview

logger = logging.getLogger(__name__)


class ResultTab(QWidget):
    """결과 탭 위젯."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._state: dict = {}
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # 제목
        title = QLabel("결과물")
        title.setStyleSheet("font-size: 16px; font-weight: bold; padding: 4px;")
        layout.addWidget(title)

        # 영상 미리보기
        self._preview = VideoPreview()
        layout.addWidget(self._preview)

        # 저장 경로
        path_layout = QHBoxLayout()
        path_label = QLabel("저장 경로:")
        path_label.setStyleSheet("font-weight: bold;")
        path_layout.addWidget(path_label)

        self._path_display = QLabel("(아직 결과 없음)")
        self._path_display.setStyleSheet("color: #555;")
        self._path_display.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        path_layout.addWidget(self._path_display, stretch=1)

        open_btn = QPushButton("폴더 열기")
        open_btn.clicked.connect(self._open_folder)
        path_layout.addWidget(open_btn)
        layout.addLayout(path_layout)

        # 업로드 버튼
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self._upload_btn = QPushButton("유튜브 업로드")
        self._upload_btn.setStyleSheet(
            "padding: 10px 30px; font-size: 14px; font-weight: bold; "
            "background-color: #D32F2F; color: white; border-radius: 4px;"
        )
        self._upload_btn.setEnabled(False)
        self._upload_btn.clicked.connect(self._on_upload)
        btn_layout.addWidget(self._upload_btn)

        # 큐에 추가 버튼
        self._queue_btn = QPushButton("업로드 큐에 추가")
        self._queue_btn.setStyleSheet(
            "padding: 10px 30px; font-size: 14px; "
            "background-color: #FF9800; color: white; border-radius: 4px;"
        )
        self._queue_btn.setEnabled(False)
        self._queue_btn.clicked.connect(self._on_add_to_queue)
        btn_layout.addWidget(self._queue_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def load_results(self, state: dict) -> None:
        """파이프라인 결과를 로드한다."""
        self._state = state

        # 영상 경로
        self._preview.set_videos({
            "landscape_ko": state.get("video_landscape_ko", ""),
            "landscape_en": state.get("video_landscape_en", ""),
            "shorts_ko": state.get("video_shorts_ko", ""),
            "shorts_en": state.get("video_shorts_en", ""),
        })

        # 썸네일
        thumb_paths = state.get("thumbnail_paths", {})
        self._preview.set_thumbnails(thumb_paths)

        # 경로
        output_dir = state.get("output_dir", "")
        self._path_display.setText(output_dir or "(경로 없음)")

        # 버튼 활성화
        has_videos = bool(state.get("video_landscape_ko"))
        self._upload_btn.setEnabled(has_videos)
        self._queue_btn.setEnabled(has_videos)

    def _open_folder(self) -> None:
        import subprocess, sys
        path = self._state.get("output_dir", "")
        if not path:
            return
        if sys.platform == "win32":
            subprocess.Popen(["explorer", path])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])

    def _on_upload(self) -> None:
        reply = QMessageBox.question(
            self, "업로드 확인",
            "4개 영상을 유튜브에 업로드합니다.\n계속하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            from uploader.youtube_uploader import upload_video
            from uploader.metadata_builder import build_metadata

            for lang, v_key, s_key in [
                ("ko", "video_landscape_ko", "video_shorts_ko"),
                ("en", "video_landscape_en", "video_shorts_en"),
            ]:
                meta_long = build_metadata(self._state, lang=lang, is_shorts=False)
                meta_short = build_metadata(self._state, lang=lang, is_shorts=True)

                upload_video(
                    video_path=self._state[v_key],
                    thumbnail_path=self._state["thumbnail_paths"].get(f"landscape_{lang}", ""),
                    metadata=meta_long, lang=lang,
                )
                upload_video(
                    video_path=self._state[s_key],
                    thumbnail_path=self._state["thumbnail_paths"].get(f"shorts_{lang}", ""),
                    metadata=meta_short, lang=lang,
                )
            QMessageBox.information(self, "완료", "4개 영상 업로드 완료!")
        except Exception as e:
            QMessageBox.critical(self, "업로드 실패", str(e))

    def _on_add_to_queue(self) -> None:
        try:
            from scheduler.upload_queue import enqueue
            from uploader.metadata_builder import build_metadata

            count = 0
            for lang, v_key, s_key in [
                ("ko", "video_landscape_ko", "video_shorts_ko"),
                ("en", "video_landscape_en", "video_shorts_en"),
            ]:
                meta_long = build_metadata(self._state, lang=lang, is_shorts=False)
                meta_short = build_metadata(self._state, lang=lang, is_shorts=True)

                enqueue(
                    video_path=self._state[v_key],
                    thumbnail_path=self._state["thumbnail_paths"].get(f"landscape_{lang}", ""),
                    metadata=meta_long, lang=lang,
                )
                enqueue(
                    video_path=self._state[s_key],
                    thumbnail_path=self._state["thumbnail_paths"].get(f"shorts_{lang}", ""),
                    metadata=meta_short, lang=lang,
                )
                count += 2

            QMessageBox.information(self, "완료", f"{count}개 영상이 업로드 큐에 추가됐습니다.")
        except Exception as e:
            QMessageBox.critical(self, "오류", str(e))
