"""Application entry point and visual theme."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from main_window import MainWindow


APP_VERSION = "0.1.0-beta"

STYLESHEET = """
QWidget {
    color: #e8f0f2;
    font-family: "Segoe UI Variable", "Segoe UI", sans-serif;
    font-size: 10pt;
}
QMainWindow, QDialog { background: #0b1117; }
#page { background: #0b1117; }
#mainScroll { background: #0b1117; }
QGroupBox#card {
    background: #111a22;
    border: 1px solid #22313b;
    border-radius: 16px;
    margin: 0;
}
QLabel#brandTitle { color: #f1f8f7; font-size: 20pt; font-weight: 700; letter-spacing: .2px; }
QLabel#sectionTitle { color: #eaf4f2; font-size: 12pt; font-weight: 650; }
QLabel#mutedText, QLabel#footerNote { color: #91a4ad; font-size: 9pt; }
QLabel#eyebrow { color: #7e969f; font-size: 8pt; font-weight: 700; letter-spacing: 1.3px; }
QLabel#versionBadge {
    color: #65e3c6; background: #142c2d; border: 1px solid #24534e;
    border-radius: 10px; padding: 7px 11px; font-size: 8pt; font-weight: 750; letter-spacing: .7px;
}
QLabel#deviceName { color: #e6f1f0; font-size: 11pt; font-weight: 600; }
QLabel#batteryValue { color: #d9f7ed; font-size: 11pt; font-weight: 700; min-width: 38px; }
QLabel#connectionDot { background: #56636b; border-radius: 5px; }
QLabel#connectionDot[connected="true"] { background: #5de0b8; }
QLabel#eqValue { color: #dffbf4; font-weight: 650; font-size: 9pt; }
QLabel#eqFrequency { color: #9aacb3; font-size: 8pt; }
QProgressBar#batteryBar { background: #26353b; border: none; border-radius: 4px; }
QProgressBar#batteryBar::chunk { background: #5de0b8; border-radius: 4px; }
QPushButton {
    background: #1a2730; color: #dbe7e9; border: 1px solid #2a3b44;
    border-radius: 9px; padding: 8px 13px; min-height: 22px;
}
QPushButton:hover { background: #22343d; border-color: #49616a; }
QPushButton:pressed { background: #142127; }
QPushButton:disabled { background: #141d23; color: #5d6b72; border-color: #202b31; }
QPushButton#primaryButton {
    color: #07201d; background: #65e3c6; border: 1px solid #65e3c6; font-weight: 750;
}
QPushButton#primaryButton:hover { background: #83f0d6; border-color: #83f0d6; }
QPushButton#primaryButton:pressed { background: #45c8aa; }
QPushButton#primaryButton:disabled { color: #72837f; background: #243c3b; border-color: #2e4b48; }
QPushButton#secondaryButton { background: #17232b; }
QPushButton#gameButton { color: #b7c8ce; background: #19242b; border-color: #31424a; font-weight: 650; }
QPushButton#gameButton:checked { color: #dffff5; background: #174238; border-color: #3d9e83; }
QPushButton#modeButton { min-height: 38px; padding: 8px 9px; font-weight: 570; }
QPushButton#modeButton:checked { color: #09211d; background: #65e3c6; border-color: #65e3c6; font-weight: 750; }
QPushButton#presetButton { min-height: 28px; padding: 5px 9px; font-size: 9pt; }
QPushButton#presetButton:checked { color: #09211d; background: #65e3c6; border-color: #65e3c6; font-weight: 700; }
QLineEdit, QListWidget {
    background: #0c141a; color: #e6f0f1; border: 1px solid #293942;
    border-radius: 9px; padding: 9px;
    selection-background-color: #23695c;
}
QListWidget::item { padding: 11px; border-radius: 7px; }
QListWidget::item:hover { background: #17272d; }
QListWidget::item:selected { background: #183a35; color: #e6fff8; }
QSlider::groove:vertical { background: #26353b; width: 5px; border-radius: 2px; }
QSlider::sub-page:vertical { background: #42bca1; border-radius: 2px; }
QSlider::add-page:vertical { background: #26353b; border-radius: 2px; }
QSlider::handle:vertical {
    background: #e3fff6; border: 2px solid #51cdb0; width: 15px; height: 15px;
    margin: 0 -6px; border-radius: 8px;
}
QSlider::handle:vertical:hover { background: #65e3c6; }
QSlider::tick-mark:vertical { background: #52656b; width: 5px; }
QStatusBar { background: #0e171d; color: #91a4ad; border-top: 1px solid #1b2930; }
QStatusBar::item { border: none; }
QScrollBar:vertical { background: #0b1117; width: 12px; margin: 0; }
QScrollBar::handle:vertical { background: #31434a; border-radius: 5px; min-height: 28px; }
QScrollBar::handle:vertical:hover { background: #48616a; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolTip { color: #edf7f5; background: #1c2b32; border: 1px solid #38515a; padding: 5px; }
QDialogButtonBox QPushButton { min-width: 86px; }
"""


def main():
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    app = QApplication(sys.argv)
    app.setApplicationName("Controle QCY H3")
    app.setOrganizationName("Deivison Santana")
    app.setApplicationVersion(APP_VERSION)
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(STYLESHEET)

    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    app.setWindowIcon(QIcon(str(root / "assets" / "qcy-h3-control.svg")))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
