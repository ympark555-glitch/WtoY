"""
gui/components/cost_display.py — 비용 표시

메인 탭 하단에 현재 예상 비용을 실시간으로 표시한다.
CostTracker의 콜백으로 연동된다.
"""

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel
from PyQt6.QtCore import pyqtSlot


class CostDisplay(QWidget):
    """
    실시간 비용 표시 위젯.

    사용법:
        cost_display = CostDisplay()
        cost_tracker.set_callback(cost_display.update_cost)
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        icon_label = QLabel("\U0001f4b0")
        icon_label.setStyleSheet("font-size: 16px;")
        layout.addWidget(icon_label)

        self._cost_label = QLabel("$0.0000 (0원)")
        self._cost_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #E65100;")
        layout.addWidget(self._cost_label)

        layout.addStretch()

    @pyqtSlot(float)
    def update_cost(self, total_usd: float) -> None:
        """비용을 업데이트한다. CostTracker 콜백으로 사용."""
        krw = int(total_usd * 1380)
        self._cost_label.setText(f"${total_usd:.4f} (약 {krw:,}원)")

    def reset(self) -> None:
        """비용을 초기화한다."""
        self._cost_label.setText("$0.0000 (0원)")
