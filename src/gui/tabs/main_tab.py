"""
gui/tabs/main_tab.py — 메인 탭

URL 입력, 포커스 입력, 시작 버튼, 진행 상황 바,
컨펌 영역, 비용 표시를 포함하는 메인 작업 화면.
"""

import logging
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QTextEdit, QMessageBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from gui.components.progress_bar import PipelineProgressBar
from gui.components.cost_display import CostDisplay
from gui.components.confirm_dialog import ConfirmDialog
from core.pipeline import Pipeline
from core.cost_tracker import CostTracker

logger = logging.getLogger(__name__)


class PipelineWorker(QThread):
    """파이프라인을 별도 스레드에서 실행한다."""

    progress = pyqtSignal(int, int, str, float)
    confirm_request = pyqtSignal(str, dict)
    finished = pyqtSignal(bool, str, dict)  # (success, message, state)
    cost_updated = pyqtSignal(float)

    def __init__(self, url: str, focus: str = "", parent=None) -> None:
        super().__init__(parent)
        self.url = url
        self.focus = focus
        self._confirm_result: Optional[bool] = None
        self._confirm_event = None
        self._stop_requested = False

    def request_stop(self) -> None:
        """안전한 중단 요청. 컨펌 대기 중이면 거부로 처리."""
        self._stop_requested = True
        if self._confirm_event:
            self._confirm_result = False
            self._confirm_event.set()

    def run(self) -> None:
        import threading
        self._confirm_event = threading.Event()

        cost_tracker = CostTracker(on_update=self._on_cost_update)
        pipeline = Pipeline(
            url=self.url,
            focus=self.focus,
            confirm_callback=self._on_confirm,
            progress_callback=self._on_progress,
        )
        pipeline.cost_tracker = cost_tracker

        try:
            pipeline.run()
            self.finished.emit(True, "파이프라인 완료!", pipeline.state)
        except Exception as e:
            self.finished.emit(False, str(e), pipeline.state)

    def _on_progress(self, step: int, total: int, desc: str, pct: float) -> None:
        self.progress.emit(step, total, desc, pct)

    def _on_confirm(self, message: str, data: dict) -> bool:
        self._confirm_result = None
        self._confirm_event.clear()
        self.confirm_request.emit(message, data)
        self._confirm_event.wait()  # GUI 스레드에서 결과 설정까지 대기
        return self._confirm_result or False

    def set_confirm_result(self, result: bool) -> None:
        self._confirm_result = result
        if self._confirm_event:
            self._confirm_event.set()

    def _on_cost_update(self, total_usd: float) -> None:
        self.cost_updated.emit(total_usd)


class MainTab(QWidget):
    """메인 탭 위젯."""

    pipeline_finished = pyqtSignal(dict)  # state dict — MainWindow에서 ResultTab 연동용

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._worker: Optional[PipelineWorker] = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # URL 입력
        url_layout = QHBoxLayout()
        url_label = QLabel("URL:")
        url_label.setStyleSheet("font-weight: bold;")
        url_layout.addWidget(url_label)

        self._url_input = QLineEdit()
        self._url_input.setPlaceholderText("변환할 웹페이지 URL을 입력하세요")
        self._url_input.setStyleSheet("padding: 8px; font-size: 13px;")
        url_layout.addWidget(self._url_input)
        layout.addLayout(url_layout)

        # 포커스 입력
        focus_layout = QHBoxLayout()
        focus_label = QLabel("포커스:")
        focus_label.setStyleSheet("font-weight: bold;")
        focus_layout.addWidget(focus_label)

        self._focus_input = QLineEdit()
        self._focus_input.setPlaceholderText("이 부분을 중심으로... (선택사항)")
        self._focus_input.setStyleSheet("padding: 8px; font-size: 13px;")
        focus_layout.addWidget(self._focus_input)
        layout.addLayout(focus_layout)

        # 시작 버튼
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self._start_btn = QPushButton("시작")
        self._start_btn.setStyleSheet(
            "padding: 10px 40px; font-size: 14px; font-weight: bold; "
            "background-color: #1976D2; color: white; border-radius: 4px;"
        )
        self._start_btn.clicked.connect(self._on_start)
        btn_layout.addWidget(self._start_btn)

        self._stop_btn = QPushButton("중단")
        self._stop_btn.setStyleSheet(
            "padding: 10px 20px; font-size: 14px; "
            "background-color: #D32F2F; color: white; border-radius: 4px;"
        )
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._on_stop)
        btn_layout.addWidget(self._stop_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # 진행 상황
        self._progress = PipelineProgressBar()
        layout.addWidget(self._progress)

        # 로그 영역
        self._log_area = QTextEdit()
        self._log_area.setReadOnly(True)
        self._log_area.setMaximumHeight(200)
        self._log_area.setStyleSheet("font-size: 11px; font-family: monospace;")
        layout.addWidget(self._log_area, stretch=1)

        # 비용 표시
        self._cost_display = CostDisplay()
        layout.addWidget(self._cost_display)

    def _on_start(self) -> None:
        url = self._url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "입력 오류", "URL을 입력하세요.")
            return

        self._set_running(True)
        self._progress.reset()
        self._cost_display.reset()
        self._log_area.clear()
        self._log("파이프라인 시작: " + url)

        self._worker = PipelineWorker(url=url, focus=self._focus_input.text().strip())
        self._worker.progress.connect(self._on_progress)
        self._worker.confirm_request.connect(self._on_confirm_request)
        self._worker.finished.connect(self._on_finished)
        self._worker.cost_updated.connect(self._cost_display.update_cost)
        self._worker.start()

    def _on_stop(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.request_stop()
            self._log("중단 요청됨 — 현재 작업 완료 후 중단됩니다")
            self._stop_btn.setEnabled(False)

    def _on_progress(self, step: int, total: int, desc: str, pct: float) -> None:
        self._progress.update_progress(step, total, desc, pct)
        if pct == 0.0:
            self._log(f"STEP {step}/{total}: {desc}")

    def _on_confirm_request(self, message: str, data: dict) -> None:
        dialog = ConfirmDialog(
            title="컨펌 필요",
            message=message,
            data=data,
            parent=self,
        )
        result = dialog.exec()
        accepted = result == ConfirmDialog.DialogCode.Accepted
        self._log(f"컨펌: {'승인' if accepted else '거부'}")
        if self._worker:
            self._worker.set_confirm_result(accepted)

    def _on_finished(self, success: bool, message: str, state: dict) -> None:
        self._set_running(False)
        if success:
            self._progress.set_complete()
            self._log(f"완료: {message}")
            self.pipeline_finished.emit(state)
            QMessageBox.information(self, "완료", message)
        else:
            self._log(f"실패: {message}")
            QMessageBox.critical(self, "오류", message)

    def _set_running(self, running: bool) -> None:
        self._start_btn.setEnabled(not running)
        self._stop_btn.setEnabled(running)
        self._url_input.setEnabled(not running)
        self._focus_input.setEnabled(not running)

    def _log(self, msg: str) -> None:
        self._log_area.append(msg)
