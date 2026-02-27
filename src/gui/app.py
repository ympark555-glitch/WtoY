"""
gui/app.py — GUI 앱 진입점

PyQt6 메인 윈도우. 탭 위젯으로 6개 탭을 관리한다.
main.py에서 App().run()으로 실행된다.
"""

import sys
import logging

from PyQt6.QtWidgets import QApplication, QMainWindow, QTabWidget
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from gui.tabs.main_tab import MainTab
from gui.tabs.result_tab import ResultTab
from gui.tabs.history_tab import HistoryTab
from gui.tabs.schedule_tab import ScheduleTab
from gui.tabs.analytics_tab import AnalyticsTab
from gui.tabs.settings_tab import SettingsTab

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """메인 윈도우."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Webpage to YouTube")
        self.setMinimumSize(900, 650)
        self.resize(1000, 700)
        self._setup_ui()

    def _setup_ui(self) -> None:
        # 탭 위젯
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet("""
            QTabBar::tab {
                padding: 8px 20px;
                font-size: 13px;
            }
            QTabBar::tab:selected {
                font-weight: bold;
            }
        """)

        # 탭 추가
        self._main_tab = MainTab()
        self._result_tab = ResultTab()
        self._history_tab = HistoryTab()
        self._schedule_tab = ScheduleTab()
        self._analytics_tab = AnalyticsTab()
        self._settings_tab = SettingsTab()

        self._tabs.addTab(self._main_tab, "메인")
        self._tabs.addTab(self._result_tab, "결과")
        self._tabs.addTab(self._history_tab, "히스토리")
        self._tabs.addTab(self._schedule_tab, "스케줄")
        self._tabs.addTab(self._analytics_tab, "통계")
        self._tabs.addTab(self._settings_tab, "설정")

        self.setCentralWidget(self._tabs)

        # 파이프라인 완료 시 결과 탭 연동
        self._main_tab.pipeline_finished.connect(self.show_result)

        # 상태바
        self.statusBar().showMessage("준비")

    def show_result(self, state: dict) -> None:
        """파이프라인 완료 후 결과 탭으로 전환한다."""
        self._result_tab.load_results(state)
        self._tabs.setCurrentWidget(self._result_tab)


class App:
    """GUI 앱 래퍼. main.py에서 호출한다."""

    def __init__(self) -> None:
        self._app = QApplication(sys.argv)
        self._app.setStyle("Fusion")

        # 기본 폰트 설정
        font = QFont()
        font.setPointSize(10)
        self._app.setFont(font)

        self._window = MainWindow()

    def run(self) -> None:
        self._window.show()
        logger.info("GUI 앱 시작")
        sys.exit(self._app.exec())
