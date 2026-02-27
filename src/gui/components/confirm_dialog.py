"""
gui/components/confirm_dialog.py — 컨펌 팝업

시나리오 확인, 업로드 확인 등 파이프라인 컨펌 시점에서
사용자에게 정보를 보여주고 OK/재생성/취소를 선택하게 한다.
"""

from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QScrollArea, QWidget,
)
from PyQt6.QtCore import Qt


class ConfirmDialog(QDialog):
    """
    파이프라인 컨펌 다이얼로그.

    사용법:
        dialog = ConfirmDialog(
            title="시나리오 확인",
            message="시나리오 생성 완료 — 확인 후 진행하세요.",
            data={"scenario": [...], "title_ko": "..."},
            parent=self,
        )
        result = dialog.exec()
        if result == QDialog.DialogCode.Accepted:
            ...  # 진행
    """

    def __init__(
        self,
        title: str = "컨펌",
        message: str = "",
        data: Optional[dict] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(600, 400)
        self._setup_ui(message, data or {})

    def _setup_ui(self, message: str, data: dict) -> None:
        layout = QVBoxLayout(self)

        # 메시지
        msg_label = QLabel(message)
        msg_label.setStyleSheet("font-size: 14px; font-weight: bold; padding: 8px;")
        msg_label.setWordWrap(True)
        layout.addWidget(msg_label)

        # 데이터 표시 영역
        if data:
            text_edit = QTextEdit()
            text_edit.setReadOnly(True)
            text_edit.setPlainText(self._format_data(data))
            text_edit.setStyleSheet("font-size: 12px;")
            layout.addWidget(text_edit, stretch=1)

        # 버튼 영역
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("취소")
        cancel_btn.setStyleSheet("padding: 8px 20px;")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        ok_btn = QPushButton("확인 (진행)")
        ok_btn.setStyleSheet(
            "padding: 8px 20px; background-color: #4CAF50; color: white; font-weight: bold;"
        )
        ok_btn.clicked.connect(self.accept)
        ok_btn.setDefault(True)
        btn_layout.addWidget(ok_btn)

        layout.addLayout(btn_layout)

    def _format_data(self, data: dict) -> str:
        """컨펌 데이터를 읽기 쉬운 텍스트로 포맷한다."""
        lines: list[str] = []

        # 시나리오 데이터
        if "scenario" in data:
            scenes = data["scenario"]
            lines.append(f"장면 수: {len(scenes)}")
            if data.get("title_ko"):
                lines.append(f"제목: {data['title_ko']}")
            lines.append("")
            for s in scenes:
                sid = s.get("scene_id", "?")
                stage = s.get("stage", "")
                narr = s.get("narration", "")
                dur = s.get("duration_sec", 0)
                lines.append(f"  [{sid}] ({stage}, {dur}s) {narr}")
            total_dur = sum(s.get("duration_sec", 0) for s in scenes)
            lines.append(f"\n총 시간: {total_dur}초 ({total_dur/60:.1f}분)")

        # 업로드 데이터
        for key in ("video_landscape_ko", "video_landscape_en",
                     "video_shorts_ko", "video_shorts_en"):
            if key in data:
                lines.append(f"{key}: {data[key]}")

        if "thumbnails" in data:
            lines.append("\n썸네일:")
            for k, v in data["thumbnails"].items():
                lines.append(f"  {k}: {v}")

        return "\n".join(lines) if lines else str(data)
