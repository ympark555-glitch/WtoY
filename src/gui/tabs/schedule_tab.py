"""
gui/tabs/schedule_tab.py — 스케줄 탭

업로드 큐 목록, 반복 업로드 설정, 업로드 시간 설정.
"""

import logging

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QComboBox, QTimeEdit, QGroupBox,
    QFormLayout, QMessageBox, QAbstractItemView,
)
from PyQt6.QtCore import Qt, QTime

logger = logging.getLogger(__name__)


class ScheduleTab(QWidget):
    """스케줄 탭 위젯."""

    _COLUMNS = ["ID", "파일명", "언어", "상태", "예약시간", "업로드완료", "video_id"]

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._runner = None
        self._setup_ui()
        self._refresh_queue()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # 스케줄 설정
        schedule_group = QGroupBox("반복 업로드 설정")
        sched_layout = QFormLayout(schedule_group)

        self._repeat_combo = QComboBox()
        self._repeat_combo.addItem("없음", "none")
        self._repeat_combo.addItem("매일", "daily")
        self._repeat_combo.addItem("월수금", "mwf")
        self._repeat_combo.addItem("평일", "weekdays")
        sched_layout.addRow("반복:", self._repeat_combo)

        self._time_edit = QTimeEdit()
        self._time_edit.setTime(QTime(9, 0))
        self._time_edit.setDisplayFormat("HH:mm")
        sched_layout.addRow("업로드 시간:", self._time_edit)

        sched_btn_layout = QHBoxLayout()
        self._apply_btn = QPushButton("스케줄 적용")
        self._apply_btn.clicked.connect(self._on_apply_schedule)
        sched_btn_layout.addWidget(self._apply_btn)

        self._runner_btn = QPushButton("스케줄러 시작")
        self._runner_btn.setStyleSheet("background-color: #4CAF50; color: white;")
        self._runner_btn.clicked.connect(self._on_toggle_runner)
        sched_btn_layout.addWidget(self._runner_btn)

        self._status_label = QLabel("중지됨")
        self._status_label.setStyleSheet("color: #D32F2F; font-weight: bold;")
        sched_btn_layout.addWidget(self._status_label)
        sched_btn_layout.addStretch()
        sched_layout.addRow("", sched_btn_layout)

        layout.addWidget(schedule_group)

        # 큐 테이블
        queue_label = QLabel("업로드 큐")
        queue_label.setStyleSheet("font-size: 14px; font-weight: bold; padding: 4px;")
        layout.addWidget(queue_label)

        self._table = QTableWidget()
        self._table.setColumnCount(len(self._COLUMNS))
        self._table.setHorizontalHeaderLabels(self._COLUMNS)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self._table, stretch=1)

        # 하단 버튼
        btn_layout = QHBoxLayout()
        refresh_btn = QPushButton("새로고침")
        refresh_btn.clicked.connect(self._refresh_queue)
        btn_layout.addWidget(refresh_btn)

        retry_btn = QPushButton("실패 항목 재시도")
        retry_btn.clicked.connect(self._on_retry)
        btn_layout.addWidget(retry_btn)

        cancel_btn = QPushButton("선택 취소")
        cancel_btn.clicked.connect(self._on_cancel)
        btn_layout.addWidget(cancel_btn)

        remove_btn = QPushButton("선택 삭제")
        remove_btn.setStyleSheet("color: #D32F2F;")
        remove_btn.clicked.connect(self._on_remove)
        btn_layout.addWidget(remove_btn)

        btn_layout.addStretch()

        # 큐 상태 요약
        self._queue_summary = QLabel("")
        self._queue_summary.setStyleSheet("color: #555;")
        btn_layout.addWidget(self._queue_summary)
        layout.addLayout(btn_layout)

    def _refresh_queue(self) -> None:
        try:
            from scheduler.upload_queue import get_all, count_by_status
            items = get_all()
            self._table.setRowCount(len(items))
            for row, item in enumerate(items):
                from pathlib import Path
                self._table.setItem(row, 0, QTableWidgetItem(str(item.get("id", ""))))
                self._table.setItem(row, 1, QTableWidgetItem(Path(item.get("video_path", "")).name))
                self._table.setItem(row, 2, QTableWidgetItem(item.get("lang", "")))
                self._table.setItem(row, 3, QTableWidgetItem(item.get("status", "")))
                self._table.setItem(row, 4, QTableWidgetItem(item.get("scheduled_at", "") or "즉시"))
                self._table.setItem(row, 5, QTableWidgetItem(item.get("uploaded_at", "") or ""))
                self._table.setItem(row, 6, QTableWidgetItem(item.get("video_id", "") or ""))

            counts = count_by_status()
            parts = [f"{k}: {v}" for k, v in counts.items()]
            self._queue_summary.setText(" | ".join(parts) if parts else "큐 비어있음")
        except Exception as e:
            logger.error("큐 로드 실패: %s", e)

    def _get_selected_ids(self) -> list[int]:
        items = self._table.selectedItems()
        rows = set(item.row() for item in items)
        ids = []
        for r in rows:
            id_item = self._table.item(r, 0)
            if id_item:
                ids.append(int(id_item.text()))
        return ids

    def _on_apply_schedule(self) -> None:
        if not self._runner:
            from scheduler.cron_runner import CronRunner
            self._runner = CronRunner()

        mode = self._repeat_combo.currentData()
        upload_time = self._time_edit.time().toString("HH:mm")
        self._runner.set_repeat(mode=mode, upload_time=upload_time)
        QMessageBox.information(self, "적용", f"스케줄 설정 완료: {mode} / {upload_time}")

    def _on_toggle_runner(self) -> None:
        if not self._runner:
            from scheduler.cron_runner import CronRunner
            self._runner = CronRunner()

        if self._runner.is_running():
            self._runner.stop()
            self._runner_btn.setText("스케줄러 시작")
            self._runner_btn.setStyleSheet("background-color: #4CAF50; color: white;")
            self._status_label.setText("중지됨")
            self._status_label.setStyleSheet("color: #D32F2F; font-weight: bold;")
        else:
            self._runner.start()
            self._runner_btn.setText("스케줄러 중지")
            self._runner_btn.setStyleSheet("background-color: #D32F2F; color: white;")
            self._status_label.setText("실행 중")
            self._status_label.setStyleSheet("color: #4CAF50; font-weight: bold;")

    def _on_retry(self) -> None:
        ids = self._get_selected_ids()
        if not ids:
            return
        try:
            from scheduler.upload_queue import retry
            for qid in ids:
                retry(qid)
            self._refresh_queue()
        except Exception as e:
            QMessageBox.critical(self, "오류", str(e))

    def _on_cancel(self) -> None:
        ids = self._get_selected_ids()
        if not ids:
            return
        try:
            from scheduler.upload_queue import cancel
            for qid in ids:
                cancel(qid)
            self._refresh_queue()
        except Exception as e:
            QMessageBox.critical(self, "오류", str(e))

    def _on_remove(self) -> None:
        ids = self._get_selected_ids()
        if not ids:
            return
        reply = QMessageBox.question(
            self, "삭제 확인", f"{len(ids)}개 항목을 삭제하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            from scheduler.upload_queue import remove
            for qid in ids:
                remove(qid)
            self._refresh_queue()
        except Exception as e:
            QMessageBox.critical(self, "오류", str(e))
