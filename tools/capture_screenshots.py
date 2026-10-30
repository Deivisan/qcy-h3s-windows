"""Capture tasteful demo screenshots of the desktop UI (no headset required).

Screenshots deliberately use presentation-only sample state. They demonstrate
where controls live; they do not claim a live BLE connection or device values.
Run from the project root: .venv/Scripts/python tools/capture_screenshots.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QPoint, QTimer, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QGroupBox

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import APP_VERSION, STYLESHEET  # noqa: E402
from h3s_device import EQ_PRESET_OFFSETS, EQ_PRESET_IDS  # noqa: E402
from main_window import MainWindow, ScanDialog  # noqa: E402


def save_after_show(widget, path: Path, app: QApplication, after_save=None):
    def capture():
        pixmap = widget.grab()
        if isinstance(widget, MainWindow):
            cards = widget.findChildren(QGroupBox, "card")
            if cards:
                last_card = cards[-1]
                bottom = last_card.mapTo(widget, QPoint(0, 0)).y() + last_card.height() + 12
                pixmap = pixmap.copy(0, 0, pixmap.width(), round(bottom * pixmap.devicePixelRatio()))
        pixmap.save(str(path))
        if after_save:
            after_save()
        else:
            app.quit()

    QTimer.singleShot(900, capture)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Controle QCY H3")
    app.setApplicationVersion(APP_VERSION)
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(STYLESHEET)

    output = ROOT / "docs" / "images"
    output.mkdir(parents=True, exist_ok=True)

    window = MainWindow()
    window.resize(1440, 1100)
    window.centralWidget().setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    window._set_connected(True)
    window._device_label.setText("QCY H3S · estado ilustrativo")
    window._eq_hint.setText("Valores ilustrativos · leitura BLE não realizada")
    window._on_battery(90)
    window._on_mode_updated(2)
    window._on_game_mode_updated(True)
    window.statusBar().showMessage("Conectado · visualização demonstrativa")
    window._active_preset_idx = 0
    for i, button in enumerate(window._eq_preset_buttons):
        button.setChecked(i == 0)
    window._on_eq_updated([300, 200, 100, 0, 0, -100, -100, 0, 100, 200])
    window.show()

    def capture_eq():
        window._active_preset_idx = 2
        for i, button in enumerate(window._eq_preset_buttons):
            button.setChecked(i == 2)
        window._on_eq_updated(EQ_PRESET_OFFSETS.get(EQ_PRESET_IDS[2], [0] * 10))
        window._eq_hint.setText("Preset de exemplo · sem leitura do fone")
        window.statusBar().showMessage("Visualização demonstrativa · EQ Pop")
        save_after_show(window, output / "equalizador.png", app, capture_connection)

    def capture_connection():
        window.close()
        dialog = ScanDialog()
        dialog.populate([("XX:XX:XX:XX:XX:XX", "QCY H3S · dispositivo de exemplo", -48)])
        dialog.show()

        def finish():
            dialog.grab().save(str(output / "conectar-fone.png"))
            dialog.close()
            app.quit()

        QTimer.singleShot(650, finish)

    save_after_show(window, output / "painel.png", app, capture_eq)
    app.exec()


if __name__ == "__main__":
    main()
