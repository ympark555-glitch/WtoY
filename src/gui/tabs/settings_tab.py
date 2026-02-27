"""
gui/tabs/settings_tab.py — 설정 탭

저장 경로, 유튜브 채널, 영상 품질, 시나리오 & 템포, 이미지 스타일,
TTS 음성, BGM, 자막, 엔진 선택, API 키 등 전체 설정을 관리한다.
"""

import logging

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QComboBox, QSlider,
    QCheckBox, QGroupBox, QFormLayout, QFileDialog,
    QMessageBox, QTextEdit, QScrollArea, QSpinBox,
    QDoubleSpinBox,
)
from PyQt6.QtCore import Qt

from gui.components.engine_selector import EngineSelector

logger = logging.getLogger(__name__)


class SettingsTab(QWidget):
    """설정 탭 위젯."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._setup_ui()
        self._load_current_settings()

    def _setup_ui(self) -> None:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        container = QWidget()
        layout = QVBoxLayout(container)

        # 1. 저장 경로
        path_group = QGroupBox("1. 저장 경로")
        path_form = QFormLayout(path_group)
        path_layout = QHBoxLayout()
        self._output_dir = QLineEdit()
        self._output_dir.setPlaceholderText("영상 출력 폴더")
        path_layout.addWidget(self._output_dir)
        browse_btn = QPushButton("찾아보기")
        browse_btn.clicked.connect(self._browse_output_dir)
        path_layout.addWidget(browse_btn)
        path_form.addRow("출력 폴더:", path_layout)
        layout.addWidget(path_group)

        # 2. 유튜브 채널
        yt_group = QGroupBox("2. 유튜브 채널")
        yt_form = QFormLayout(yt_group)
        self._ko_channel = QLineEdit()
        self._ko_channel.setPlaceholderText("한국어 채널 ID")
        yt_form.addRow("한국어 채널:", self._ko_channel)
        self._en_channel = QLineEdit()
        self._en_channel.setPlaceholderText("영어 채널 ID")
        yt_form.addRow("영어 채널:", self._en_channel)
        self._privacy_combo = QComboBox()
        self._privacy_combo.addItems(["public", "unlisted", "private"])
        yt_form.addRow("공개 설정:", self._privacy_combo)
        self._category_input = QLineEdit("22")
        yt_form.addRow("카테고리 ID:", self._category_input)
        layout.addWidget(yt_group)

        # 3. 영상 품질
        quality_group = QGroupBox("3. 영상 품질")
        quality_form = QFormLayout(quality_group)
        self._resolution_combo = QComboBox()
        self._resolution_combo.addItems(["1080p", "720p", "480p"])
        quality_form.addRow("해상도:", self._resolution_combo)
        self._bitrate_input = QLineEdit("4000k")
        quality_form.addRow("비트레이트:", self._bitrate_input)
        layout.addWidget(quality_group)

        # 4. 시나리오 & 템포
        scenario_group = QGroupBox("4. 시나리오 & 템포")
        scenario_form = QFormLayout(scenario_group)
        self._target_duration = QSpinBox()
        self._target_duration.setRange(60, 600)
        self._target_duration.setValue(300)
        self._target_duration.setSuffix(" 초")
        scenario_form.addRow("영상 길이:", self._target_duration)
        self._scene_target = QDoubleSpinBox()
        self._scene_target.setRange(1.0, 10.0)
        self._scene_target.setValue(3.0)
        self._scene_target.setSuffix(" 초")
        scenario_form.addRow("장면당 목표:", self._scene_target)
        self._tone_combo = QComboBox()
        self._tone_combo.addItems(["informative", "dramatic", "casual"])
        scenario_form.addRow("톤:", self._tone_combo)
        self._hook_combo = QComboBox()
        self._hook_combo.addItems(["low", "medium", "high"])
        self._hook_combo.setCurrentIndex(2)
        scenario_form.addRow("후킹 강도:", self._hook_combo)
        layout.addWidget(scenario_group)

        # 5. 이미지 스타일
        style_group = QGroupBox("5. 이미지 스타일")
        style_layout = QVBoxLayout(style_group)
        self._style_input = QTextEdit()
        self._style_input.setMaximumHeight(80)
        self._style_input.setPlaceholderText("이미지 스타일을 자연어로 입력...")
        style_layout.addWidget(self._style_input)
        self._image_quality_combo = QComboBox()
        self._image_quality_combo.addItems(["hd", "standard"])
        style_form = QFormLayout()
        style_form.addRow("이미지 품질:", self._image_quality_combo)
        style_layout.addLayout(style_form)
        layout.addWidget(style_group)

        # 6. TTS 음성
        tts_group = QGroupBox("6. TTS 음성")
        tts_form = QFormLayout(tts_group)
        self._tts_speed = QDoubleSpinBox()
        self._tts_speed.setRange(0.5, 2.0)
        self._tts_speed.setValue(1.0)
        self._tts_speed.setSingleStep(0.1)
        tts_form.addRow("속도:", self._tts_speed)
        self._tts_ko_voice = QComboBox()
        self._tts_ko_voice.addItems(["alloy", "echo", "fable", "onyx", "nova", "shimmer"])
        self._tts_ko_voice.setCurrentText("nova")
        tts_form.addRow("한국어 성우:", self._tts_ko_voice)
        self._tts_en_voice = QComboBox()
        self._tts_en_voice.addItems(["alloy", "echo", "fable", "onyx", "nova", "shimmer"])
        self._tts_en_voice.setCurrentText("echo")
        tts_form.addRow("영어 성우:", self._tts_en_voice)
        layout.addWidget(tts_group)

        # 7. BGM
        bgm_group = QGroupBox("7. BGM")
        bgm_form = QFormLayout(bgm_group)
        self._bgm_slider = QSlider(Qt.Orientation.Horizontal)
        self._bgm_slider.setRange(10, 40)
        self._bgm_slider.setValue(15)
        self._bgm_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._bgm_label = QLabel("15%")
        self._bgm_slider.valueChanged.connect(
            lambda v: self._bgm_label.setText(f"{v}%")
        )
        bgm_row = QHBoxLayout()
        bgm_row.addWidget(self._bgm_slider)
        bgm_row.addWidget(self._bgm_label)
        bgm_form.addRow("볼륨 비율:", bgm_row)
        layout.addWidget(bgm_group)

        # 8. 자막
        sub_group = QGroupBox("8. 자막")
        sub_form = QFormLayout(sub_group)
        self._subtitle_check = QCheckBox("자막 표시")
        self._subtitle_check.setChecked(True)
        sub_form.addRow("", self._subtitle_check)
        self._sub_size = QSpinBox()
        self._sub_size.setRange(16, 72)
        self._sub_size.setValue(36)
        sub_form.addRow("폰트 크기:", self._sub_size)
        self._sub_position = QComboBox()
        self._sub_position.addItems(["top", "center", "bottom"])
        self._sub_position.setCurrentText("bottom")
        sub_form.addRow("위치:", self._sub_position)
        self._sub_color = QComboBox()
        self._sub_color.addItems(["white", "yellow", "cyan"])
        sub_form.addRow("색상:", self._sub_color)
        layout.addWidget(sub_group)

        # 9~10. 엔진 선택 + API 키
        self._engine_selector = EngineSelector()
        layout.addWidget(self._engine_selector)

        # 하단 버튼
        btn_layout = QHBoxLayout()
        reset_btn = QPushButton("기본값으로 초기화")
        reset_btn.clicked.connect(self._reset_defaults)
        btn_layout.addWidget(reset_btn)
        btn_layout.addStretch()
        save_btn = QPushButton("저장")
        save_btn.setStyleSheet(
            "padding: 8px 30px; background-color: #1976D2; color: white; "
            "font-weight: bold; border-radius: 4px;"
        )
        save_btn.clicked.connect(self._save_settings)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.addWidget(scroll)

    def _browse_output_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "출력 폴더 선택")
        if path:
            self._output_dir.setText(path)

    def _load_current_settings(self) -> None:
        """config.py의 현재 값을 위젯에 반영한다."""
        import config

        self._output_dir.setText(str(config.OUTPUT_DIR))
        self._ko_channel.setText(config.YOUTUBE_KO_CHANNEL_ID)
        self._en_channel.setText(config.YOUTUBE_EN_CHANNEL_ID)
        self._privacy_combo.setCurrentText(config.YOUTUBE_PRIVACY)
        self._category_input.setText(config.YOUTUBE_CATEGORY_ID)
        self._resolution_combo.setCurrentText(config.VIDEO_RESOLUTION)
        self._bitrate_input.setText(config.VIDEO_BITRATE)
        self._target_duration.setValue(config.TARGET_DURATION_SEC)
        self._scene_target.setValue(config.SCENE_TARGET_SEC)
        self._tone_combo.setCurrentText(config.NARRATIVE_TONE)
        self._hook_combo.setCurrentText(config.HOOK_INTENSITY)
        self._style_input.setPlainText(config.IMAGE_STYLE)
        self._image_quality_combo.setCurrentText(config.IMAGE_QUALITY)
        self._tts_speed.setValue(config.TTS_SPEED)
        self._tts_ko_voice.setCurrentText(config.TTS_KO_VOICE)
        self._tts_en_voice.setCurrentText(config.TTS_EN_VOICE)
        self._bgm_slider.setValue(int(config.BGM_VOLUME_RATIO * 100))
        self._subtitle_check.setChecked(config.SUBTITLE_ENABLED)
        self._sub_size.setValue(config.SUBTITLE_FONT_SIZE)
        self._sub_position.setCurrentText(config.SUBTITLE_POSITION)
        self._sub_color.setCurrentText(config.SUBTITLE_COLOR)

        self._engine_selector.set_values({
            "SCENARIO_ENGINE": config.SCENARIO_ENGINE,
            "IMAGE_ENGINE": config.IMAGE_ENGINE,
            "TTS_ENGINE": config.TTS_ENGINE,
            "OPENAI_API_KEY": config.OPENAI_API_KEY,
            "PIXABAY_API_KEY": config.PIXABAY_API_KEY,
            "GOOGLE_CLIENT_SECRET_PATH": config.GOOGLE_CLIENT_SECRET_PATH,
            "OLLAMA_HOST": config.OLLAMA_HOST,
            "SD_API_URL": config.SD_API_URL,
        })

    def _save_settings(self) -> None:
        """위젯 값을 config.py에 반영한다."""
        import config

        settings = {
            "YOUTUBE_KO_CHANNEL_ID": self._ko_channel.text().strip(),
            "YOUTUBE_EN_CHANNEL_ID": self._en_channel.text().strip(),
            "YOUTUBE_PRIVACY": self._privacy_combo.currentText(),
            "YOUTUBE_CATEGORY_ID": self._category_input.text().strip(),
            "VIDEO_RESOLUTION": self._resolution_combo.currentText(),
            "VIDEO_BITRATE": self._bitrate_input.text().strip(),
            "TARGET_DURATION_SEC": self._target_duration.value(),
            "SCENE_TARGET_SEC": self._scene_target.value(),
            "NARRATIVE_TONE": self._tone_combo.currentText(),
            "HOOK_INTENSITY": self._hook_combo.currentText(),
            "IMAGE_STYLE": self._style_input.toPlainText().strip(),
            "IMAGE_QUALITY": self._image_quality_combo.currentText(),
            "TTS_SPEED": self._tts_speed.value(),
            "TTS_KO_VOICE": self._tts_ko_voice.currentText(),
            "TTS_EN_VOICE": self._tts_en_voice.currentText(),
            "BGM_VOLUME_RATIO": self._bgm_slider.value() / 100.0,
            "SUBTITLE_ENABLED": self._subtitle_check.isChecked(),
            "SUBTITLE_FONT_SIZE": self._sub_size.value(),
            "SUBTITLE_POSITION": self._sub_position.currentText(),
            "SUBTITLE_COLOR": self._sub_color.currentText(),
        }

        # 출력 폴더 변경 시 Path로 변환
        output_dir = self._output_dir.text().strip()
        if output_dir:
            from pathlib import Path
            settings["OUTPUT_DIR"] = Path(output_dir)

        # 엔진 및 API 키
        engine_values = self._engine_selector.get_values()
        settings.update(engine_values)

        config.apply_settings(settings)
        QMessageBox.information(self, "저장 완료", "설정이 반영됐습니다.")

    def _reset_defaults(self) -> None:
        reply = QMessageBox.question(
            self, "초기화", "설정을 기본값으로 되돌리시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        import config
        # IMAGE_STYLE만 기본값 복원 (다른 값은 코드 기본값이므로 reload 대안)
        config.IMAGE_STYLE = config.IMAGE_STYLE_DEFAULT
        self._load_current_settings()
        QMessageBox.information(self, "초기화 완료", "기본값으로 복원됐습니다.")
