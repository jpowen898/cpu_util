import sys
from pathlib import Path
from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout,
                              QWidget)
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QIcon

from helpers import INTERVAL
from panels import CpuThroughputPanel, CpuTemperaturePanel, RamUtilizationPanel

APP_NAME = "CPU Monitor"
APP_ID = "cpu-monitor"

# =========================
# Dark theme stylesheet
# =========================
DARK_STYLE = """
QMainWindow, QWidget {
    background-color: #1a1a2e;
    color: #e0e0e0;
}
QLabel {
    color: #e0e0e0;
}
"""


# =========================
# Main window
# =========================
class MainWindow(QMainWindow):
    """
    Top-level window that holds monitoring panels.
    To add a new panel, create a BasePanel subclass and call add_panel().
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1100, 700)

        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(6)

        # Panels scale to fill the current window height.
        self.panel_layout = QVBoxLayout()
        self.panel_layout.setContentsMargins(0, 0, 0, 0)
        self.panel_layout.setSpacing(8)
        outer.addLayout(self.panel_layout, stretch=1)

        # Panel registry
        self.panels = []

        # --- Register panels here ---
        self.add_panel(CpuThroughputPanel())
        self.add_panel(CpuTemperaturePanel())
        self.add_panel(RamUtilizationPanel())
        # Future: self.add_panel(TemperaturePanel())
        # Future: self.add_panel(FanSpeedPanel())

        # Update timer
        self.timer = QTimer()
        self.timer.timeout.connect(self._update_all)
        self.timer.start(INTERVAL)

    def add_panel(self, panel):
        self.panels.append(panel)
        self.panel_layout.addWidget(panel, stretch=1)

    def _update_all(self):
        for panel in self.panels:
            panel.update_data()


# =========================
# Entry point
# =========================
def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_ID)
    app.setApplicationDisplayName(APP_NAME)
    app.setDesktopFileName(APP_ID)
    icon_path = Path(__file__).with_name("icon.png")
    icon = QIcon(str(icon_path)) if icon_path.exists() else QIcon()
    if icon_path.exists():
        app.setWindowIcon(icon)
    app.setStyleSheet(DARK_STYLE)
    window = MainWindow()
    if not icon.isNull():
        window.setWindowIcon(icon)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
