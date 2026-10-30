import sys
import asyncio
asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QPalette, QColor
from main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Dark theme palette
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(30, 30, 30))
    palette.setColor(QPalette.WindowText, QColor(220, 220, 220))
    palette.setColor(QPalette.Base, QColor(40, 40, 40))
    palette.setColor(QPalette.AlternateBase, QColor(50, 50, 50))
    palette.setColor(QPalette.ToolTipBase, QColor(60, 60, 60))
    palette.setColor(QPalette.ToolTipText, QColor(220, 220, 220))
    palette.setColor(QPalette.Text, QColor(220, 220, 220))
    palette.setColor(QPalette.Button, QColor(50, 50, 50))
    palette.setColor(QPalette.ButtonText, QColor(220, 220, 220))
    palette.setColor(QPalette.BrightText, QColor(255, 80, 80))
    palette.setColor(QPalette.Link, QColor(80, 160, 255))
    palette.setColor(QPalette.Highlight, QColor(60, 120, 200))
    palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)

    # QSS stylesheet
    app.setStyleSheet("""
        QGroupBox {
            font-weight: bold;
            border: 1px solid #555;
            border-radius: 6px;
            margin-top: 8px;
            padding-top: 8px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 4px;
        }
        QPushButton {
            background-color: #3a3a3a;
            border: 1px solid #555;
            border-radius: 4px;
            padding: 6px 12px;
            min-height: 24px;
        }
        QPushButton:hover {
            background-color: #4a4a4a;
            border-color: #777;
        }
        QPushButton:pressed {
            background-color: #2a2a2a;
        }
        QPushButton:checked {
            background-color: #2a6a9a;
            border-color: #4a8aca;
        }
        QPushButton:disabled {
            background-color: #2a2a2a;
            color: #666;
        }
        QSlider::groove:horizontal {
            height: 6px;
            background: #444;
            border-radius: 3px;
        }
        QSlider::handle:horizontal {
            background: #6a9aca;
            width: 14px;
            margin: -4px 0;
            border-radius: 7px;
        }
        QLabel {
            color: #ddd;
        }
        QStatusBar {
            background-color: #2a2a2a;
            color: #aaa;
        }
        QLineEdit, QComboBox {
            background-color: #3a3a3a;
            border: 1px solid #555;
            border-radius: 4px;
            padding: 4px;
            color: #ddd;
        }
    """)

    font = QFont("Segoe UI", 10)
    app.setFont(font)

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
