"""
gui/tabs/history_tab.py — 히스토리 탭

검색/필터, 영상별 카드 (제목/날짜/이미지 장수/비용/업로드 상태),
재활용/이미지보기/삭제 버튼, 누적 총 비용 표시.
"""

import logging

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QAbstractItemView,
)
from PyQt6.QtCore import Qt

logger = logging.getLogger(__name__)


class HistoryTab(QWidget):
    """히스토리 탭 위젯."""

    _COLUMNS = ["ID", "제목", "날짜", "장면수", "이미지", "재사용", "비용($)", "업로드"]

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._records: list[dict] = []
        self._setup_ui()
        self._refresh()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # 검색 바
        search_layout = QHBoxLayout()
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("제목 또는 URL 검색...")
        self._search_input.setStyleSheet("padding: 6px;")
        self._search_input.returnPressed.connect(self._on_search)
        search_layout.addWidget(self._search_input)

        search_btn = QPushButton("검색")
        search_btn.clicked.connect(self._on_search)
        search_layout.addWidget(search_btn)

        refresh_btn = QPushButton("새로고침")
        refresh_btn.clicked.connect(self._refresh)
        search_layout.addWidget(refresh_btn)
        layout.addLayout(search_layout)

        # 테이블
        self._table = QTableWidget()
        self._table.setColumnCount(len(self._COLUMNS))
        self._table.setHorizontalHeaderLabels(self._COLUMNS)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self._table.setColumnWidth(0, 40)
        layout.addWidget(self._table, stretch=1)

        # 하단 버튼
        btn_layout = QHBoxLayout()

        self._total_label = QLabel("누적 비용: $0.0000")
        self._total_label.setStyleSheet("font-weight: bold; color: #E65100;")
        btn_layout.addWidget(self._total_label)
        btn_layout.addStretch()

        del_btn = QPushButton("선택 삭제")
        del_btn.setStyleSheet("color: #D32F2F;")
        del_btn.clicked.connect(self._on_delete)
        btn_layout.addWidget(del_btn)

        layout.addLayout(btn_layout)

    def _refresh(self) -> None:
        """히스토리를 DB에서 다시 불러온다."""
        try:
            from history.history_manager import get_all, total_cost
            self._records = get_all(limit=200)
            self._populate_table(self._records)
            cost = total_cost()
            krw = int(cost * 1380)
            self._total_label.setText(f"누적 비용: ${cost:.4f} (약 {krw:,}원)")
        except Exception as e:
            logger.error("히스토리 로드 실패: %s", e)

    def _on_search(self) -> None:
        keyword = self._search_input.text().strip()
        if not keyword:
            self._refresh()
            return
        try:
            from history.history_manager import search
            results = search(keyword)
            self._records = results
            self._populate_table(results)
        except Exception as e:
            logger.error("히스토리 검색 실패: %s", e)

    def _populate_table(self, records: list[dict]) -> None:
        self._table.setRowCount(len(records))
        for row, r in enumerate(records):
            self._table.setItem(row, 0, QTableWidgetItem(str(r.get("id", ""))))
            self._table.setItem(row, 1, QTableWidgetItem(r.get("title_ko", "") or r.get("title_en", "")))
            self._table.setItem(row, 2, QTableWidgetItem(r.get("created_at", "")[:16]))
            self._table.setItem(row, 3, QTableWidgetItem(str(r.get("scene_count", 0))))
            self._table.setItem(row, 4, QTableWidgetItem(str(r.get("image_count", 0))))
            self._table.setItem(row, 5, QTableWidgetItem(str(r.get("reused_images", 0))))
            self._table.setItem(row, 6, QTableWidgetItem(f"${r.get('cost_usd', 0.0):.4f}"))
            self._table.setItem(row, 7, QTableWidgetItem(r.get("upload_status", "")))

    def _on_delete(self) -> None:
        selected = self._table.selectedItems()
        if not selected:
            return

        rows = set(item.row() for item in selected)
        ids = [self._records[r]["id"] for r in rows if r < len(self._records)]

        reply = QMessageBox.question(
            self, "삭제 확인",
            f"{len(ids)}개 이력을 삭제하시겠습니까?\n(영상 파일은 삭제되지 않습니다)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            from history.history_manager import delete_record
            for record_id in ids:
                delete_record(record_id)
            self._refresh()
        except Exception as e:
            QMessageBox.critical(self, "오류", str(e))
