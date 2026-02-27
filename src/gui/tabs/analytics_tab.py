"""
gui/tabs/analytics_tab.py — 통계 탭

월별 비용 현황, 영상별 성과 (조회수/CTR/구독 증가),
이미지 재사용으로 절약한 비용.
"""

import logging

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QGroupBox, QTextEdit,
    QAbstractItemView, QComboBox,
)
from PyQt6.QtCore import Qt

logger = logging.getLogger(__name__)


class AnalyticsTab(QWidget):
    """통계 탭 위젯."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # 비용 요약
        cost_group = QGroupBox("비용 현황")
        cost_layout = QVBoxLayout(cost_group)

        self._cost_text = QTextEdit()
        self._cost_text.setReadOnly(True)
        self._cost_text.setMaximumHeight(180)
        self._cost_text.setStyleSheet("font-family: monospace; font-size: 12px;")
        cost_layout.addWidget(self._cost_text)

        cost_btn_layout = QHBoxLayout()
        refresh_cost_btn = QPushButton("비용 새로고침")
        refresh_cost_btn.clicked.connect(self._refresh_cost)
        cost_btn_layout.addWidget(refresh_cost_btn)
        cost_btn_layout.addStretch()
        cost_layout.addLayout(cost_btn_layout)

        layout.addWidget(cost_group)

        # 월별 비용 테이블
        monthly_group = QGroupBox("월별 비용")
        monthly_layout = QVBoxLayout(monthly_group)

        year_layout = QHBoxLayout()
        year_label = QLabel("연도:")
        year_layout.addWidget(year_label)
        self._year_combo = QComboBox()
        from datetime import datetime
        current_year = datetime.now().year
        for y in range(current_year, current_year - 5, -1):
            self._year_combo.addItem(str(y), y)
        self._year_combo.currentIndexChanged.connect(self._refresh_monthly)
        year_layout.addWidget(self._year_combo)
        year_layout.addStretch()
        monthly_layout.addLayout(year_layout)

        self._monthly_table = QTableWidget()
        cols = ["월", "영상수", "비용($)", "평균($)", "이미지", "재사용"]
        self._monthly_table.setColumnCount(len(cols))
        self._monthly_table.setHorizontalHeaderLabels(cols)
        self._monthly_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._monthly_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._monthly_table.setMaximumHeight(200)
        monthly_layout.addWidget(self._monthly_table)

        layout.addWidget(monthly_group)

        # 영상별 성과
        perf_group = QGroupBox("영상별 성과")
        perf_layout = QVBoxLayout(perf_group)

        perf_btn_layout = QHBoxLayout()
        refresh_perf_btn = QPushButton("성과 조회")
        refresh_perf_btn.clicked.connect(self._refresh_performance)
        perf_btn_layout.addWidget(refresh_perf_btn)
        perf_btn_layout.addStretch()
        perf_layout.addLayout(perf_btn_layout)

        self._perf_table = QTableWidget()
        perf_cols = ["제목", "유형", "조회수", "좋아요", "댓글"]
        self._perf_table.setColumnCount(len(perf_cols))
        self._perf_table.setHorizontalHeaderLabels(perf_cols)
        self._perf_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._perf_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        perf_layout.addWidget(self._perf_table)

        layout.addWidget(perf_group, stretch=1)

    def showEvent(self, event) -> None:
        """탭이 표시될 때 자동으로 비용 데이터를 새로고침한다."""
        super().showEvent(event)
        self._refresh_cost()
        self._refresh_monthly()

    def _refresh_cost(self) -> None:
        try:
            from analytics.cost_reporter import format_summary_text
            self._cost_text.setPlainText(format_summary_text())
        except Exception as e:
            self._cost_text.setPlainText(f"비용 조회 실패: {e}")

    def _refresh_monthly(self) -> None:
        try:
            from analytics.cost_reporter import monthly_summary
            year = self._year_combo.currentData()
            if not year:
                return
            data = monthly_summary(year)
            self._monthly_table.setRowCount(len(data))
            for row, d in enumerate(data):
                self._monthly_table.setItem(row, 0, QTableWidgetItem(f"{d['month']}월"))
                self._monthly_table.setItem(row, 1, QTableWidgetItem(str(d["video_count"])))
                self._monthly_table.setItem(row, 2, QTableWidgetItem(f"${d['total_cost']:.4f}"))
                self._monthly_table.setItem(row, 3, QTableWidgetItem(f"${d['avg_cost']:.4f}"))
                self._monthly_table.setItem(row, 4, QTableWidgetItem(str(d["image_count"])))
                self._monthly_table.setItem(row, 5, QTableWidgetItem(str(d["reused_images"])))
        except Exception as e:
            logger.error("월별 비용 조회 실패: %s", e)

    def _refresh_performance(self) -> None:
        try:
            from history.history_manager import get_all
            from analytics.youtube_analytics import fetch_stats_for_history

            records = get_all(limit=20)
            all_stats: list[dict] = []

            for record in records:
                stats = fetch_stats_for_history(record)
                all_stats.extend(stats)

            self._perf_table.setRowCount(len(all_stats))
            for row, s in enumerate(all_stats):
                self._perf_table.setItem(row, 0, QTableWidgetItem(s.get("title", "")))
                self._perf_table.setItem(row, 1, QTableWidgetItem(s.get("type", "")))
                self._perf_table.setItem(row, 2, QTableWidgetItem(f"{s.get('view_count', 0):,}"))
                self._perf_table.setItem(row, 3, QTableWidgetItem(f"{s.get('like_count', 0):,}"))
                self._perf_table.setItem(row, 4, QTableWidgetItem(f"{s.get('comment_count', 0):,}"))

            if not all_stats:
                self._perf_table.setRowCount(1)
                self._perf_table.setItem(0, 0, QTableWidgetItem("업로드된 영상이 없습니다"))
        except Exception as e:
            logger.error("성과 조회 실패: %s", e)
            self._perf_table.setRowCount(1)
            self._perf_table.setItem(0, 0, QTableWidgetItem(f"조회 실패: {e}"))
