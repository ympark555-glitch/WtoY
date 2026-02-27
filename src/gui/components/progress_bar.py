"""
gui/components/progress_bar.py — 진행 상황 바

파이프라인 STEP 진행률을 시각적으로 표시한다.
전체 스텝 진행 (1~11) + 현재 스텝 내 세부 진행률을 함께 보여준다.
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar
from PyQt6.QtCore import Qt, pyqtSlot


class PipelineProgressBar(QWidget):
    """
    파이프라인 진행 상황 위젯.

    사용법:
        progress = PipelineProgressBar()
        progress.update_progress(step=3, total=11, desc="이미지 생성 중", pct=0.4)
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 상단: 스텝 정보
        info_layout = QHBoxLayout()
        self._step_label = QLabel("대기 중")
        self._step_label.setStyleSheet("font-size: 13px; font-weight: bold;")
        info_layout.addWidget(self._step_label)

        info_layout.addStretch()

        self._pct_label = QLabel("")
        self._pct_label.setStyleSheet("font-size: 12px; color: #666;")
        info_layout.addWidget(self._pct_label)
        layout.addLayout(info_layout)

        # 전체 스텝 진행바
        self._step_bar = QProgressBar()
        self._step_bar.setRange(0, 11)
        self._step_bar.setValue(0)
        self._step_bar.setTextVisible(False)
        self._step_bar.setFixedHeight(8)
        self._step_bar.setStyleSheet("""
            QProgressBar { background-color: #E0E0E0; border-radius: 4px; }
            QProgressBar::chunk { background-color: #2196F3; border-radius: 4px; }
        """)
        layout.addWidget(self._step_bar)

        # 현재 스텝 세부 진행바
        self._detail_bar = QProgressBar()
        self._detail_bar.setRange(0, 100)
        self._detail_bar.setValue(0)
        self._detail_bar.setTextVisible(False)
        self._detail_bar.setFixedHeight(4)
        self._detail_bar.setStyleSheet("""
            QProgressBar { background-color: #E0E0E0; border-radius: 2px; }
            QProgressBar::chunk { background-color: #4CAF50; border-radius: 2px; }
        """)
        layout.addWidget(self._detail_bar)

    @pyqtSlot(int, int, str, float)
    def update_progress(self, step: int, total: int, desc: str, pct: float) -> None:
        """
        진행 상황을 업데이트한다.

        step:  현재 스텝 번호 (1~11)
        total: 전체 스텝 수 (11)
        desc:  현재 작업 설명
        pct:   현재 스텝 내 진행률 (0.0~1.0)
        """
        self._step_label.setText(f"STEP {step}/{total}  {desc}")
        self._pct_label.setText(f"{int(pct * 100)}%")

        # 전체 진행: 이전 스텝 완료 + 현재 스텝 비율
        overall = step - 1 + pct
        self._step_bar.setValue(int(overall))
        self._detail_bar.setValue(int(pct * 100))

    def reset(self) -> None:
        """진행바를 초기 상태로 리셋한다."""
        self._step_label.setText("대기 중")
        self._pct_label.setText("")
        self._step_bar.setValue(0)
        self._detail_bar.setValue(0)

    def set_complete(self) -> None:
        """완료 상태로 설정한다."""
        self._step_label.setText("완료!")
        self._pct_label.setText("100%")
        self._step_bar.setValue(11)
        self._detail_bar.setValue(100)
