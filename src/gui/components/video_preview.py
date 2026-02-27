"""
gui/components/video_preview.py — 영상 미리보기

결과 탭에서 생성된 영상과 썸네일을 미리보기로 표시한다.
영상 파일을 외부 플레이어로 열거나, 썸네일을 이미지로 표시한다.
"""

import subprocess
import sys
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGroupBox, QGridLayout,
)
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt


class VideoPreview(QWidget):
    """
    영상 4종 + 썸네일 4종 미리보기 위젯.

    사용법:
        preview = VideoPreview()
        preview.set_videos({
            "landscape_ko": "/path/to/landscape_ko.mp4",
            "landscape_en": "/path/to/landscape_en.mp4",
            "shorts_ko": "/path/to/shorts_ko.mp4",
            "shorts_en": "/path/to/shorts_en.mp4",
        })
        preview.set_thumbnails({
            "landscape_ko": "/path/to/thumb_landscape_ko.jpg",
            ...
        })
    """

    _LABELS = {
        "landscape_ko": "5분 영상 (한국어)",
        "landscape_en": "5분 영상 (영어)",
        "shorts_ko": "쇼츠 (한국어)",
        "shorts_en": "쇼츠 (영어)",
    }

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._video_paths: dict[str, str] = {}
        self._thumb_labels: dict[str, QLabel] = {}
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        grid = QGridLayout()
        keys = ["landscape_ko", "landscape_en", "shorts_ko", "shorts_en"]

        for i, key in enumerate(keys):
            row, col = divmod(i, 2)
            group = self._create_card(key)
            grid.addWidget(group, row, col)

        layout.addLayout(grid)

    def _create_card(self, key: str) -> QGroupBox:
        """영상 카드 위젯을 생성한다."""
        group = QGroupBox(self._LABELS.get(key, key))
        vbox = QVBoxLayout(group)

        # 썸네일 표시
        thumb_label = QLabel("썸네일 없음")
        thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb_label.setFixedSize(240, 135)
        thumb_label.setStyleSheet("background-color: #F0F0F0; border: 1px solid #CCC;")
        thumb_label.setScaledContents(True)
        self._thumb_labels[key] = thumb_label
        vbox.addWidget(thumb_label)

        # 재생 버튼
        play_btn = QPushButton("재생")
        play_btn.clicked.connect(lambda _, k=key: self._play_video(k))
        vbox.addWidget(play_btn)

        return group

    def set_videos(self, paths: dict[str, str]) -> None:
        """영상 경로를 설정한다."""
        self._video_paths = paths

    def set_thumbnails(self, paths: dict[str, str]) -> None:
        """썸네일 이미지를 표시한다."""
        for key, path in paths.items():
            label = self._thumb_labels.get(key)
            if not label:
                continue
            p = Path(path)
            if p.exists():
                pixmap = QPixmap(str(p))
                label.setPixmap(pixmap.scaled(
                    240, 135,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                ))
            else:
                label.setText("파일 없음")

    def _play_video(self, key: str) -> None:
        """외부 미디어 플레이어로 영상을 연다."""
        path = self._video_paths.get(key)
        if not path or not Path(path).exists():
            return

        if sys.platform == "win32":
            subprocess.Popen(["start", "", path], shell=True)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
