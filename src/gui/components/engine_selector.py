"""
gui/components/engine_selector.py — 엔진 선택 + API 키 입력

설정 탭에서 시나리오/이미지/TTS 엔진을 선택하고,
선택에 따라 필요한 API 키 입력 필드를 동적으로 표시한다.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QLineEdit, QGroupBox, QFormLayout,
)
from PyQt6.QtCore import pyqtSignal


class EngineSelector(QWidget):
    """
    엔진 선택 + API 키 입력 위젯.

    Signals:
        engine_changed(str, str): (category, engine) — 엔진 변경 시 발생
    """

    engine_changed = pyqtSignal(str, str)  # (category, engine)

    _ENGINES = {
        "scenario": {"gpt4o": "GPT-4o (유료)", "ollama": "Ollama (로컬)"},
        "image": {"dalle3": "DALL-E 3 (유료)", "sd": "Stable Diffusion (로컬)"},
        "tts": {"openai": "OpenAI TTS (유료)", "edge": "Edge TTS (무료)"},
    }

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._combos: dict[str, QComboBox] = {}
        self._api_fields: dict[str, QLineEdit] = {}
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # 엔진 선택 그룹
        engine_group = QGroupBox("엔진 선택")
        engine_form = QFormLayout(engine_group)

        for category, engines in self._ENGINES.items():
            label_map = {"scenario": "시나리오", "image": "이미지", "tts": "TTS"}
            combo = QComboBox()
            for key, display in engines.items():
                combo.addItem(display, key)
            combo.currentIndexChanged.connect(
                lambda _, c=category: self._on_engine_changed(c)
            )
            self._combos[category] = combo
            engine_form.addRow(f"{label_map[category]}:", combo)

        layout.addWidget(engine_group)

        # API 키 입력 그룹
        api_group = QGroupBox("API 키")
        api_form = QFormLayout(api_group)

        self._api_fields["openai"] = QLineEdit()
        self._api_fields["openai"].setPlaceholderText("sk-...")
        self._api_fields["openai"].setEchoMode(QLineEdit.EchoMode.Password)
        api_form.addRow("OpenAI API Key:", self._api_fields["openai"])

        self._api_fields["pixabay"] = QLineEdit()
        self._api_fields["pixabay"].setPlaceholderText("Pixabay API Key")
        api_form.addRow("Pixabay API Key:", self._api_fields["pixabay"])

        self._api_fields["google_oauth"] = QLineEdit()
        self._api_fields["google_oauth"].setPlaceholderText("client_secret.json 경로")
        api_form.addRow("Google OAuth2:", self._api_fields["google_oauth"])

        # Ollama/SD URL (로컬 엔진 선택 시만 의미)
        self._api_fields["ollama_host"] = QLineEdit()
        self._api_fields["ollama_host"].setPlaceholderText("http://localhost:11434")
        api_form.addRow("Ollama 호스트:", self._api_fields["ollama_host"])

        self._api_fields["sd_url"] = QLineEdit()
        self._api_fields["sd_url"].setPlaceholderText("http://localhost:7860")
        api_form.addRow("SD API URL:", self._api_fields["sd_url"])

        layout.addWidget(api_group)

    def _on_engine_changed(self, category: str) -> None:
        combo = self._combos[category]
        engine = combo.currentData()
        self.engine_changed.emit(category, engine)

    def get_values(self) -> dict:
        """현재 설정값을 dict로 반환한다."""
        return {
            "SCENARIO_ENGINE": self._combos["scenario"].currentData(),
            "IMAGE_ENGINE": self._combos["image"].currentData(),
            "TTS_ENGINE": self._combos["tts"].currentData(),
            "OPENAI_API_KEY": self._api_fields["openai"].text().strip(),
            "PIXABAY_API_KEY": self._api_fields["pixabay"].text().strip(),
            "GOOGLE_CLIENT_SECRET_PATH": self._api_fields["google_oauth"].text().strip(),
            "OLLAMA_HOST": self._api_fields["ollama_host"].text().strip(),
            "SD_API_URL": self._api_fields["sd_url"].text().strip(),
        }

    def set_values(self, settings: dict) -> None:
        """설정값을 위젯에 반영한다."""
        engine_map = {
            "SCENARIO_ENGINE": "scenario",
            "IMAGE_ENGINE": "image",
            "TTS_ENGINE": "tts",
        }
        for config_key, category in engine_map.items():
            value = settings.get(config_key, "")
            combo = self._combos[category]
            idx = combo.findData(value)
            if idx >= 0:
                combo.setCurrentIndex(idx)

        field_map = {
            "OPENAI_API_KEY": "openai",
            "PIXABAY_API_KEY": "pixabay",
            "GOOGLE_CLIENT_SECRET_PATH": "google_oauth",
            "OLLAMA_HOST": "ollama_host",
            "SD_API_URL": "sd_url",
        }
        for config_key, field_key in field_map.items():
            value = settings.get(config_key, "")
            if value:
                self._api_fields[field_key].setText(value)
