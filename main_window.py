"""QCY H3 Controller - Main Window."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QColor, QPalette
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QGroupBox, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
    QPushButton, QSlider, QStatusBar, QVBoxLayout, QWidget,
)

from ble_worker import BleWorker
from h3_device import ANCMode, EQ_BAND_LABELS, EQ_PRESET_NAMES, EQ_PRESET_IDS, EQ_PRESET_OFFSETS


MODE_LABELS = ["ANC Desligado", "Transparência", "ANC Baixo", "ANC Médio", "ANC Alto", "Adaptativo"]
MODE_BYTES  = ANCMode.ALL


# -----------------------------------------------------------------------
# Scan dialog
# -----------------------------------------------------------------------

class ScanDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Selecionar Dispositivo")
        self.setMinimumWidth(360)
        self._selected: tuple | None = None

        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(self.accept)

        self._status = QLabel("Escaneando…")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addWidget(self._status)
        lay.addWidget(self._list)
        lay.addWidget(btns)

    def populate(self, devices: list):
        self._list.clear()
        if not devices:
            self._status.setText("Nenhum dispositivo encontrado.")
            return
        self._status.setText(f"{len(devices)} dispositivo(s) encontrado(s).")
        for addr, name, rssi in devices:
            label = f"{name or '(sem nome)'}  [{addr}]  {rssi} dBm"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, (addr, name))
            self._list.addItem(item)

    def selected_device(self) -> tuple | None:
        item = self._list.currentItem()
        if item:
            return item.data(Qt.ItemDataRole.UserRole)
        return None


# -----------------------------------------------------------------------
# EQ band widget (vertical slider + labels)
# -----------------------------------------------------------------------

class EqBand(QWidget):
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self._slider = QSlider(Qt.Orientation.Vertical)
        self._slider.setRange(-24, 24)   # ×50 = -1200 .. +1200 (1/100 dB)
        self._slider.setValue(0)
        self._slider.setTickPosition(QSlider.TickPosition.TicksBothSides)
        self._slider.setTickInterval(4)
        self._slider.setFixedHeight(130)
        self._slider.valueChanged.connect(self._update_db_label)

        self._db_label = QLabel("0.0 dB")
        self._db_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._db_label.setFixedWidth(52)

        freq_label = QLabel(label)
        freq_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        freq_label.setFixedWidth(52)
        font = freq_label.font()
        font.setPointSize(8)
        freq_label.setFont(font)

        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(self._db_label, alignment=Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(self._slider, alignment=Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(freq_label, alignment=Qt.AlignmentFlag.AlignHCenter)
        lay.setSpacing(4)
        lay.setContentsMargins(2, 2, 2, 2)

    def _update_db_label(self, val: int):
        db = val * 50 / 100.0
        self._db_label.setText(f"{db:+.1f} dB" if db != 0 else "0.0 dB")

    def value_hundredths(self) -> int:
        return self._slider.value() * 50

    def set_value_hundredths(self, v: int):
        self._slider.setValue(round(v / 50))

    def reset(self):
        self._slider.setValue(0)


# -----------------------------------------------------------------------
# Main Window
# -----------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("QCY H3 Controller")
        self.setMinimumSize(780, 560)

        self._worker = BleWorker(self)
        self._worker.start()
        self._worker.scan_result.connect(self._on_scan_result)
        self._worker.connected.connect(self._on_connected)
        self._worker.disconnected.connect(self._on_disconnected)
        self._worker.error.connect(self._on_error)
        self._worker.battery_updated.connect(self._on_battery)
        self._worker.mode_updated.connect(self._on_mode_updated)
        self._worker.eq_updated.connect(self._on_eq_updated)
        self._worker.game_mode_updated.connect(self._on_game_mode_updated)

        self._scan_dialog: ScanDialog | None = None
        self._mode_buttons: list[QPushButton] = []
        self._eq_bands: list[EqBand] = []
        self._eq_preset_buttons: list[QPushButton] = []
        self._active_preset_idx: int = 0  # "Custom" by default

        # Battery refresh every 60 s when connected
        self._battery_timer = QTimer(self)
        self._battery_timer.setInterval(60_000)
        self._battery_timer.timeout.connect(lambda: self._worker.refresh_status())

        self._build_ui()
        self._set_connected(False)

    # ------------------------------------------------------------------
    # UI build
    # ------------------------------------------------------------------

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(10)
        root.setContentsMargins(12, 12, 12, 12)

        # ---- Header bar ----
        header = QHBoxLayout()
        title = QLabel("QCY H3 Controller")
        title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        self._battery_label = QLabel("🔋 —")
        self._battery_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._game_mode_btn = QPushButton("Game Mode")
        self._game_mode_btn.setCheckable(True)
        self._game_mode_btn.setEnabled(False)
        self._game_mode_btn.setToolTip("Modo de baixa latência para jogos")
        self._game_mode_btn.clicked.connect(self._on_game_mode_clicked)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self._game_mode_btn)
        header.addWidget(self._battery_label)
        root.addLayout(header)

        # ---- Connection bar ----
        conn = QHBoxLayout()
        self._scan_btn = QPushButton("Escanear")
        self._scan_btn.clicked.connect(self._on_scan_clicked)
        self._disconnect_btn = QPushButton("Desconectar")
        self._disconnect_btn.clicked.connect(lambda: self._worker.disconnect_device())
        self._device_label = QLabel("Não conectado")
        conn.addWidget(self._scan_btn)
        conn.addWidget(self._disconnect_btn)
        conn.addWidget(self._device_label)
        conn.addStretch()
        root.addLayout(conn)

        # ---- Mode group ----
        mode_group = QGroupBox("Modo de Ruído")
        mode_lay = QHBoxLayout(mode_group)
        for i, label in enumerate(MODE_LABELS):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setEnabled(False)
            btn.clicked.connect(lambda _, idx=i: self._on_mode_changed(idx))
            mode_lay.addWidget(btn)
            self._mode_buttons.append(btn)
        root.addWidget(mode_group)

        # ---- EQ group ----
        eq_group = QGroupBox("Equalizador")
        eq_root = QVBoxLayout(eq_group)

        # Preset selector row
        preset_lay = QHBoxLayout()
        preset_lay.setSpacing(4)
        preset_label = QLabel("Preset:")
        preset_lay.addWidget(preset_label)
        for i, name in enumerate(EQ_PRESET_NAMES):
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setEnabled(False)
            btn.clicked.connect(lambda _, idx=i: self._on_preset_btn(idx))
            preset_lay.addWidget(btn)
            self._eq_preset_buttons.append(btn)
        preset_lay.addStretch()
        eq_root.addLayout(preset_lay)
        # Select "Custom" by default
        self._eq_preset_buttons[0].setChecked(True)

        sliders_lay = QHBoxLayout()
        sliders_lay.setSpacing(2)
        for label in EQ_BAND_LABELS:
            band = EqBand(label)
            sliders_lay.addWidget(band)
            self._eq_bands.append(band)
        eq_root.addLayout(sliders_lay)

        eq_btns = QHBoxLayout()
        eq_btns.addStretch()
        reset_btn = QPushButton("Resetar")
        reset_btn.clicked.connect(self._reset_eq)
        apply_btn = QPushButton("Aplicar EQ")
        apply_btn.setDefault(True)
        apply_btn.clicked.connect(self._apply_eq)
        eq_btns.addWidget(reset_btn)
        eq_btns.addWidget(apply_btn)
        eq_root.addLayout(eq_btns)

        root.addWidget(eq_group)
        root.addStretch()

        # ---- Status bar ----
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Pronto.")

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def _set_connected(self, connected: bool):
        self._scan_btn.setEnabled(not connected)
        self._disconnect_btn.setEnabled(connected)
        self._game_mode_btn.setEnabled(connected)
        for btn in self._mode_buttons:
            btn.setEnabled(connected)
        for band in self._eq_bands:
            band.setEnabled(connected)
        for btn in self._eq_preset_buttons:
            btn.setEnabled(connected)
        if not connected:
            self._device_label.setText("Não conectado")
            self._battery_label.setText("🔋 —")
            self._battery_timer.stop()
            for btn in self._mode_buttons:
                btn.setChecked(False)
            self._game_mode_btn.setChecked(False)

    def _set_mode_active(self, idx: int):
        for i, btn in enumerate(self._mode_buttons):
            btn.setChecked(i == idx)

    # ------------------------------------------------------------------
    # Signal handlers
    # ------------------------------------------------------------------

    def _on_scan_clicked(self):
        self._scan_dialog = ScanDialog(self)
        self._worker.scan(timeout=5.0)
        self.statusBar().showMessage("Escaneando…")
        result = self._scan_dialog.exec()
        if result == QDialog.DialogCode.Accepted:
            dev = self._scan_dialog.selected_device()
            if dev:
                addr, name = dev
                self._device_label.setText(f"Conectando em {name or addr}…")
                self.statusBar().showMessage("Conectando…")
                self._worker.connect_device(addr)

    def _on_scan_result(self, devices: list):
        if self._scan_dialog:
            self._scan_dialog.populate(devices)
        self.statusBar().showMessage(f"Scan concluído: {len(devices)} dispositivo(s).")

    def _on_connected(self, address: str):
        self._device_label.setText(f"Conectado: {address}")
        self.statusBar().showMessage("Conectado!")
        self._set_connected(True)
        self._battery_timer.start()

    def _on_disconnected(self):
        self._set_connected(False)
        self.statusBar().showMessage("Desconectado.")

    def _on_error(self, msg: str):
        self.statusBar().showMessage(f"Erro: {msg}")
        QMessageBox.warning(self, "Erro", msg)

    def _on_battery(self, pct: int):
        self._battery_label.setText(f"🔋 {pct}%")

    def _on_mode_updated(self, idx: int):
        self._set_mode_active(idx)

    def _on_eq_updated(self, offsets: list):
        for i, band in enumerate(self._eq_bands):
            if i < len(offsets):
                band.set_value_hundredths(offsets[i])

    def _on_game_mode_updated(self, enabled: bool):
        self._game_mode_btn.setChecked(enabled)

    # ------------------------------------------------------------------
    # User actions
    # ------------------------------------------------------------------

    def _on_mode_changed(self, idx: int):
        self._set_mode_active(idx)
        self._worker.set_mode(MODE_BYTES[idx])
        self.statusBar().showMessage(f"Modo: {MODE_LABELS[idx]}")

    def _on_preset_btn(self, idx: int):
        self._active_preset_idx = idx
        for i, btn in enumerate(self._eq_preset_buttons):
            btn.setChecked(i == idx)
        preset_id = EQ_PRESET_IDS[idx]
        # Carregar valores do preset nos sliders (exceto Custom que preserva os sliders)
        if preset_id != 0x00:
            offsets = EQ_PRESET_OFFSETS.get(preset_id, [0] * 10)
            for i, band in enumerate(self._eq_bands):
                band.set_value_hundredths(offsets[i] if i < len(offsets) else 0)
        # Aplicar automaticamente ao dispositivo
        self._apply_eq()

    def _on_game_mode_clicked(self):
        enabled = self._game_mode_btn.isChecked()
        self._worker.set_game_mode(enabled)
        label = "ativado" if enabled else "desativado"
        self.statusBar().showMessage(f"Game Mode {label}.")

    def _reset_eq(self):
        for band in self._eq_bands:
            band.reset()

    def _apply_eq(self):
        offsets = [b.value_hundredths() for b in self._eq_bands]
        preset_id = EQ_PRESET_IDS[self._active_preset_idx]
        self._worker.set_eq(offsets, preset_id)
        self.statusBar().showMessage(f"EQ aplicado ({EQ_PRESET_NAMES[self._active_preset_idx]}).")
