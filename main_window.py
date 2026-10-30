"""Polished desktop UI for the independent QCY H3 / H3S controller."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QEasingCurve, Qt, QPropertyAnimation, QTimer
from PySide6.QtGui import QIcon, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QGraphicsOpacityEffect, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
    QProgressBar, QPushButton, QScrollArea, QSlider, QStatusBar, QVBoxLayout,
    QWidget,
)

from ble_worker import BleWorker
from h3s_device import ANCMode, EQ_BAND_LABELS, EQ_PRESET_NAMES, EQ_PRESET_IDS, EQ_PRESET_OFFSETS


APP_VERSION = "0.1.1-beta"
MODE_LABELS = ["Desligado", "Transparência", "ANC baixo", "ANC médio", "ANC alto", "ANC máximo", "ANC ultra", "Adaptativo"]
MODE_HINTS = ["Cancelamento desligado", "Som ambiente", "Nível de redução 1", "Nível de redução 2", "Nível de redução 3", "Nível de redução 4", "Nível de redução 5", "Adaptação automática"]
MODE_BYTES = ANCMode.ALL


def resource_path(relative: str) -> str:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return str(root / relative)


class ScanDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Conectar dispositivo")
        self.setMinimumSize(520, 390)
        self.setObjectName("scanDialog")
        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(self.accept)
        self._status = QLabel("Procurando dispositivos Bluetooth próximos…")
        self._status.setObjectName("mutedText")
        self._status.setWordWrap(True)
        self._manual_input = QLineEdit()
        self._manual_input.setPlaceholderText("AA:BB:CC:DD:EE:FF")
        self._manual_input.setToolTip("Endereço BLE do fone, se o scan não o encontrar")
        manual = QLabel("Ou informe manualmente o endereço BLE")
        manual.setObjectName("mutedText")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)
        layout.addWidget(self._status)
        layout.addWidget(self._list, 1)
        layout.addWidget(manual)
        layout.addWidget(self._manual_input)
        layout.addWidget(buttons)

    def populate(self, devices: list):
        self._list.clear()
        if not devices:
            self._status.setText("Nenhum dispositivo apareceu no scan. Verifique se o fone está ligado e tente novamente ou informe o endereço BLE.")
            return
        self._status.setText(f"{len(devices)} dispositivo(s) encontrado(s). Selecione o seu fone para conectar.")
        for address, name, rssi in devices:
            detail = f"{rssi} dBm" if rssi is not None else "dispositivo conhecido"
            item = QListWidgetItem(f"{name or 'Dispositivo Bluetooth'}   ·   {detail}\n{address}")
            item.setData(Qt.ItemDataRole.UserRole, (address, name))
            self._list.addItem(item)

    def selected_device(self) -> tuple | None:
        manual = self._manual_input.text().strip()
        if manual:
            return manual, "Dispositivo manual"
        item = self._list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None


class EqBand(QWidget):
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self.setObjectName("eqBand")
        self._slider = QSlider(Qt.Orientation.Vertical)
        self._slider.setRange(-24, 24)
        self._slider.setValue(0)
        self._slider.setTickPosition(QSlider.TickPosition.TicksBothSides)
        self._slider.setTickInterval(4)
        self._slider.setFixedHeight(164)
        self._slider.valueChanged.connect(self._update_db_label)
        self._db_label = QLabel("0.0 dB")
        self._db_label.setObjectName("eqValue")
        self._db_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._db_label.setFixedWidth(52)
        freq_label = QLabel(label)
        freq_label.setObjectName("eqFrequency")
        freq_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        freq_label.setFixedWidth(40)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(3, 4, 3, 4)
        layout.setSpacing(8)
        layout.addWidget(self._db_label)
        layout.addWidget(self._slider, 1, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(freq_label)

    def _update_db_label(self, value: int):
        db = value * 0.5
        self._db_label.setText(f"{db:+.1f} dB" if db else "0.0 dB")

    def value_hundredths(self) -> int:
        return self._slider.value() * 50

    def set_value_hundredths(self, value: int):
        self._slider.setValue(round(value / 50))

    def reset(self):
        self._slider.setValue(0)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Controle QCY H3")
        self.setWindowIcon(QIcon(resource_path("assets/qcy-h3-control.svg")))
        self.setMinimumSize(860, 680)
        self.resize(1080, 820)

        self._worker = BleWorker(self)
        self._worker.start()
        self._worker.scan_result.connect(self._on_scan_result)
        self._worker.connected.connect(self._on_connected)
        self._worker.disconnected.connect(self._on_disconnected)
        self._worker.error.connect(self._on_error)
        self._worker.status.connect(self._on_status)
        self._worker.battery_updated.connect(self._on_battery)
        self._worker.mode_updated.connect(self._on_mode_updated)
        self._worker.eq_updated.connect(self._on_eq_updated)
        self._worker.game_mode_updated.connect(self._on_game_mode_updated)

        self._scan_dialog: ScanDialog | None = None
        self._mode_buttons: list[QPushButton] = []
        self._eq_bands: list[EqBand] = []
        self._eq_preset_buttons: list[QPushButton] = []
        self._active_preset_idx = 0
        self._confirmed_eq: list[int] | None = None
        self._connected = False
        self._animations: list[QPropertyAnimation] = []

        self._battery_timer = QTimer(self)
        self._battery_timer.setInterval(60_000)
        self._battery_timer.timeout.connect(self._worker.refresh_status)

        self._build_ui()
        self._set_connected(False)
        self._install_shortcuts()
        QTimer.singleShot(80, self._animate_intro)

    def _card(self, title: str, subtitle: str | None = None) -> tuple[QGroupBox, QVBoxLayout]:
        box = QGroupBox()
        box.setObjectName("card")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)
        heading = QHBoxLayout()
        title_label = QLabel(title)
        title_label.setObjectName("sectionTitle")
        heading.addWidget(title_label)
        heading.addStretch()
        if subtitle:
            hint = QLabel(subtitle)
            hint.setObjectName("mutedText")
            heading.addWidget(hint)
        layout.addLayout(heading)
        return box, layout

    def _build_ui(self):
        page = QWidget()
        page.setObjectName("page")
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(10, 22, 10, 20)
        page_layout.setSpacing(18)

        # Branded masthead
        header = QHBoxLayout()
        mark = QLabel()
        mark.setFixedSize(54, 54)
        mark.setPixmap(QPixmap(resource_path("assets/qcy-h3-control.svg")).scaled(54, 54, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        header.addWidget(mark)
        brand = QVBoxLayout()
        title = QLabel("Controle QCY H3")
        title.setObjectName("brandTitle")
        subtitle = QLabel("H3 / H3S · gerenciador Bluetooth")
        subtitle.setObjectName("mutedText")
        brand.addWidget(title)
        brand.addWidget(subtitle)
        brand.setSpacing(2)
        header.addLayout(brand)
        header.addStretch()
        self._version_badge = QLabel(f"BETA  ·  {APP_VERSION.removesuffix('-beta')}")
        self._version_badge.setObjectName("versionBadge")
        header.addWidget(self._version_badge)
        help_button = QPushButton("Ajuda")
        help_button.setObjectName("secondaryButton")
        help_button.setIcon(QIcon(resource_path("assets/action-help.svg")))
        help_button.setToolTip("Ajuda e informações sobre compatibilidade (F1)")
        help_button.clicked.connect(self._show_help)
        header.addWidget(help_button)
        page_layout.addLayout(header)

        # Connection and battery overview
        connection_card, connection_layout = self._card("Dispositivo", "Bluetooth Low Energy")
        row = QHBoxLayout()
        self._connection_dot = QLabel()
        self._connection_dot.setObjectName("connectionDot")
        self._connection_dot.setFixedSize(10, 10)
        row.addWidget(self._connection_dot, 0, Qt.AlignmentFlag.AlignVCenter)
        self._device_label = QLabel("Nenhum fone conectado")
        self._device_label.setObjectName("deviceName")
        row.addWidget(self._device_label)
        row.addStretch(1)
        self._battery_title = QLabel("BATERIA")
        self._battery_title.setObjectName("eyebrow")
        row.addWidget(self._battery_title)
        self._battery_label = QLabel("—")
        self._battery_label.setObjectName("batteryValue")
        row.addWidget(self._battery_label)
        self._battery_bar = QProgressBar()
        self._battery_bar.setObjectName("batteryBar")
        self._battery_bar.setRange(0, 100)
        self._battery_bar.setValue(0)
        self._battery_bar.setTextVisible(False)
        self._battery_bar.setFixedWidth(110)
        self._battery_bar.setFixedHeight(8)
        row.addWidget(self._battery_bar)
        connection_layout.addLayout(row)
        actions = QHBoxLayout()
        self._scan_btn = QPushButton("Conectar fone")
        self._scan_btn.setObjectName("primaryButton")
        self._scan_btn.setIcon(QIcon(resource_path("assets/action-connect.svg")))
        self._scan_btn.setToolTip("Buscar dispositivos próximos (Ctrl+K)")
        self._scan_btn.clicked.connect(self._on_scan_clicked)
        actions.addWidget(self._scan_btn)
        self._disconnect_btn = QPushButton("Desconectar")
        self._disconnect_btn.setObjectName("secondaryButton")
        self._disconnect_btn.setIcon(QIcon(resource_path("assets/action-disconnect.svg")))
        self._disconnect_btn.clicked.connect(self._worker.disconnect_device)
        actions.addWidget(self._disconnect_btn)
        actions.addStretch()
        self._quick_game_btn = QPushButton("Game Mode")
        self._quick_game_btn.setObjectName("gameButton")
        self._quick_game_btn.setCheckable(True)
        self._quick_game_btn.setIcon(QIcon(resource_path("assets/action-game.svg")))
        self._quick_game_btn.setToolTip("Alternar baixa latência (Ctrl+G)")
        self._quick_game_btn.clicked.connect(self._on_game_mode_clicked)
        actions.addWidget(self._quick_game_btn)
        connection_layout.addLayout(actions)
        page_layout.addWidget(connection_card)

        # Noise modes
        mode_card, mode_layout = self._card("Modo de ruído", "Toque para enviar ao fone")
        modes = QGridLayout()
        modes.setHorizontalSpacing(10)
        modes.setVerticalSpacing(10)
        for index, label in enumerate(MODE_LABELS):
            button = QPushButton(label)
            button.setObjectName("modeButton")
            icon_name = ("mode-off.svg" if index == 0 else "mode-transparency.svg" if index == 1
                         else "mode-adaptive.svg" if index == 7 else "mode-anc.svg")
            button.setIcon(QIcon(resource_path(f"assets/{icon_name}")))
            button.setIconSize(QPixmap(18, 18).size())
            button.setCheckable(True)
            button.setEnabled(False)
            button.setToolTip(MODE_HINTS[index])
            button.clicked.connect(lambda _checked=False, idx=index: self._on_mode_changed(idx))
            modes.addWidget(button, index // 4, index % 4)
            self._mode_buttons.append(button)
        mode_layout.addLayout(modes)
        page_layout.addWidget(mode_card)

        # Equalizer
        eq_card, eq_layout = self._card("Equalizador", "10 bandas  ·  ±12 dB")
        eq_layout.setContentsMargins(16, 18, 16, 18)
        preset_title = QLabel("PRESETS")
        preset_title.setObjectName("eyebrow")
        eq_layout.addWidget(preset_title)
        preset_grid = QGridLayout()
        preset_grid.setHorizontalSpacing(7)
        preset_grid.setVerticalSpacing(6)
        for index, name in enumerate(EQ_PRESET_NAMES):
            button = QPushButton(name)
            button.setObjectName("presetButton")
            button.setCheckable(True)
            button.setEnabled(False)
            button.clicked.connect(lambda _checked=False, idx=index: self._on_preset_btn(idx))
            preset_grid.addWidget(button, index // 4, index % 4)
            self._eq_preset_buttons.append(button)
        self._eq_preset_buttons[0].setChecked(True)
        preset_grid.setColumnStretch(4, 1)
        eq_layout.addLayout(preset_grid)

        slider_row = QHBoxLayout()
        slider_row.setSpacing(2)
        for band_label in EQ_BAND_LABELS:
            band = EqBand(band_label)
            slider_row.addWidget(band, 1)
            self._eq_bands.append(band)
        eq_layout.addLayout(slider_row)

        footer = QHBoxLayout()
        self._eq_hint = QLabel("EQ confirmado por leitura do fone.")
        self._eq_hint.setObjectName("mutedText")
        footer.addWidget(self._eq_hint)
        footer.addStretch()
        reset_button = QPushButton("Resetar")
        reset_button.setObjectName("secondaryButton")
        reset_button.setToolTip("Zerar todas as bandas (Ctrl+0)")
        reset_button.clicked.connect(self._reset_eq)
        footer.addWidget(reset_button)
        self._apply_button = QPushButton("Aplicar EQ")
        self._apply_button.setObjectName("primaryButton")
        self._apply_button.setDefault(True)
        self._apply_button.setToolTip("Enviar ajustes ao fone (Ctrl+Enter)")
        self._apply_button.clicked.connect(self._apply_eq)
        footer.addWidget(self._apply_button)
        eq_layout.addLayout(footer)
        page_layout.addWidget(eq_card)

        note = QLabel("Para QCY H3 e H3S · ferramenta independente")
        note.setObjectName("footerNote")
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        page_layout.addWidget(note)
        page_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setObjectName("mainScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(page)
        self.setCentralWidget(scroll)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Pronto · conecte seu fone para começar")

    def _install_shortcuts(self):
        bindings = [("Ctrl+K", self._on_scan_clicked), ("Ctrl+G", self._toggle_game_mode),
                    ("Ctrl+Return", self._apply_eq), ("Ctrl+Enter", self._apply_eq),
                    ("Ctrl+0", self._reset_eq), ("F1", self._show_help)]
        self._shortcuts = []
        for key, callback in bindings:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(callback)
            self._shortcuts.append(shortcut)

    def _animate_intro(self):
        cards = self.findChildren(QGroupBox, "card")
        for index, card in enumerate(cards):
            effect = QGraphicsOpacityEffect(card)
            effect.setOpacity(0.45)
            card.setGraphicsEffect(effect)
            animation = QPropertyAnimation(effect, b"opacity", self)
            animation.setDuration(360)
            animation.setStartValue(0.45)
            animation.setEndValue(1.0)
            animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            animation.finished.connect(lambda a=animation: self._animations.remove(a) if a in self._animations else None)
            self._animations.append(animation)
            QTimer.singleShot(index * 75, animation.start)

    def _show_help(self):
        QMessageBox.information(
            self, "Ajuda · Controle QCY H3",
            "<h3>Conecte e controle</h3>"
            "<p>Ative o Bluetooth, ligue o fone e use <b>Conectar fone</b>. "
            "Os modos de ruído, Game Mode e equalizador são enviados diretamente pelo BLE.</p>"
            "<h3>Compatibilidade</h3>"
            "<p>O aplicativo foi feito para QCY H3 padrão e QCY H3S. O H3S foi validado "
            "em hardware; no H3 padrão, a compatibilidade depende da revisão e do firmware. "
            "Alguns estados e confirmações variam de acordo com o fone.</p>"
            "<h3>Atalhos</h3><p>Ctrl+K conectar · Ctrl+G Game Mode · Ctrl+Enter aplicar EQ · "
            "Ctrl+0 zerar EQ · F1 ajuda</p>"
            "<p>Projeto pessoal independente, sem afiliação oficial com a QCY. "
            f"Versão {APP_VERSION}.</p>"
        )

    def _set_connected(self, connected: bool):
        self._connected = connected
        self._scan_btn.setEnabled(True)
        self._disconnect_btn.setEnabled(connected)
        self._quick_game_btn.setEnabled(connected)
        for button in self._mode_buttons:
            button.setEnabled(connected)
        for band in self._eq_bands:
            band.setEnabled(connected)
        for button in self._eq_preset_buttons:
            button.setEnabled(connected)
        self._apply_button.setEnabled(connected)
        self._connection_dot.setProperty("connected", connected)
        self._connection_dot.style().unpolish(self._connection_dot)
        self._connection_dot.style().polish(self._connection_dot)
        if not connected:
            self._device_label.setText("Nenhum fone conectado")
            self._battery_label.setText("—")
            self._battery_bar.setValue(0)
            self._battery_timer.stop()
            self._confirmed_eq = None
            for button in self._mode_buttons:
                button.setChecked(False)
            self._quick_game_btn.setChecked(False)

    def _on_scan_clicked(self):
        self._scan_dialog = ScanDialog(self)
        self._worker.scan(timeout=5.0)
        self.statusBar().showMessage("Procurando dispositivos Bluetooth…")
        if self._scan_dialog.exec() == QDialog.DialogCode.Accepted:
            device = self._scan_dialog.selected_device()
            if device:
                address, name = device
                self._device_label.setText(f"Conectando a {name or address}…")
                self.statusBar().showMessage("Estabelecendo conexão BLE…")
                self._worker.connect_device(address)

    def _on_scan_result(self, devices: list):
        if self._scan_dialog:
            self._scan_dialog.populate(devices)
        self.statusBar().showMessage(f"Busca concluída · {len(devices)} dispositivo(s)", 5000)

    def _on_connected(self, address: str):
        self._device_label.setText(f"Conectado · {address}")
        self.statusBar().showMessage("Conexão ativa · lendo estado do fone", 5000)
        self._set_connected(True)
        self._battery_timer.start()

    def _on_disconnected(self):
        self._set_connected(False)
        self.statusBar().showMessage("Conexão encerrada")

    def _on_error(self, message: str):
        self._apply_button.setEnabled(self._connected)
        self.statusBar().showMessage(f"Falha · {message}", 8000)
        QMessageBox.warning(self, "Não foi possível concluir", message)

    def _on_status(self, message: str):
        self._apply_button.setEnabled(self._connected)
        self.statusBar().showMessage(message, 8000)
        self._eq_hint.setText(message)

    def _on_battery(self, percent: int):
        self._battery_label.setText(f"{percent}%")
        self._battery_bar.setValue(max(0, min(100, percent)))

    def _on_mode_updated(self, index: int):
        for i, button in enumerate(self._mode_buttons):
            button.setChecked(i == index)

    def _on_eq_updated(self, offsets: list):
        self._confirmed_eq = list(offsets)
        for i, band in enumerate(self._eq_bands):
            if i < len(offsets):
                band.set_value_hundredths(offsets[i])

    def _on_game_mode_updated(self, enabled: bool):
        self._quick_game_btn.setChecked(enabled)

    def _on_mode_changed(self, index: int):
        self._worker.set_mode(MODE_BYTES[index])
        self.statusBar().showMessage(f"Enviando modo · {MODE_LABELS[index]}…")

    def _on_preset_btn(self, index: int):
        self._active_preset_idx = index
        for i, button in enumerate(self._eq_preset_buttons):
            button.setChecked(i == index)
        preset_id = EQ_PRESET_IDS[index]
        if preset_id != 0:
            values = EQ_PRESET_OFFSETS.get(preset_id, [0] * 10)
            for i, band in enumerate(self._eq_bands):
                band.set_value_hundredths(values[i] if i < len(values) else 0)
        self._apply_eq()

    def _toggle_game_mode(self):
        if self._connected:
            self._quick_game_btn.setChecked(not self._quick_game_btn.isChecked())
            self._on_game_mode_clicked()

    def _on_game_mode_clicked(self):
        enabled = self._quick_game_btn.isChecked()
        self._worker.set_game_mode(enabled)
        self.statusBar().showMessage("Enviando Game Mode ao fone…")

    def _reset_eq(self):
        for band in self._eq_bands:
            band.reset()
        self._active_preset_idx = 0
        for i, button in enumerate(self._eq_preset_buttons):
            button.setChecked(i == 0)

    def _apply_eq(self):
        if not self._connected:
            self.statusBar().showMessage("Conecte o fone antes de aplicar o equalizador")
            return
        offsets = [band.value_hundredths() for band in self._eq_bands]
        preset_id = EQ_PRESET_IDS[self._active_preset_idx]
        self._apply_button.setEnabled(False)
        self._eq_hint.setText("Aplicando ajustes e aguardando confirmação do fone…")
        self._worker.set_eq(offsets, preset_id)
        # Worker status/read-back re-enable path. The safety timeout also handles
        # a silent firmware/adapter without leaving the control permanently busy.
        QTimer.singleShot(3500, lambda: self._apply_button.setEnabled(self._connected))

    def closeEvent(self, event):
        try:
            self._worker.disconnect_device()
        finally:
            super().closeEvent(event)
