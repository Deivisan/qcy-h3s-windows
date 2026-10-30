"""BLE worker: runs asyncio event loop in a daemon thread.
Qt signals carry results back to the UI thread.
"""
import asyncio
import threading

from PySide6.QtCore import QObject, Signal

from h3_device import H3Device, scan
from rcsp import parse_tlv, AdvType


class BleWorker(QObject):
    scan_result      = Signal(list)   # [(addr, name, rssi), ...]
    connected        = Signal(str)    # device address
    disconnected     = Signal()
    error            = Signal(str)
    battery_updated  = Signal(int)    # 0-100 %
    mode_updated     = Signal(int)    # 0-4 (NORMAL/TRANSP/ANC_LOW/MED/HIGH)
    eq_updated       = Signal(list)   # 10 ints (1/100-dB offsets)
    game_mode_updated = Signal(bool)  # True=game mode on

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._device: H3Device | None = None
        self._ready = threading.Event()

    # ------------------------------------------------------------------
    # Thread lifecycle
    # ------------------------------------------------------------------

    def start(self):
        t = threading.Thread(target=self._run_loop, name="BleThread", daemon=True)
        t.start()
        self._ready.wait(timeout=5.0)

    def _run_loop(self):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._ready.set()
        self._loop.run_forever()

    def _submit(self, coro):
        if self._loop is None:
            return
        asyncio.run_coroutine_threadsafe(coro, self._loop)

    # ------------------------------------------------------------------
    # Public API (called from Qt main thread)
    # ------------------------------------------------------------------

    def scan(self, timeout: float = 5.0):
        self._submit(self._do_scan(timeout))

    def connect_device(self, address: str):
        self._submit(self._do_connect(address))

    def disconnect_device(self):
        self._submit(self._do_disconnect())

    def set_mode(self, mode_bytes: bytes):
        self._submit(self._do_set_mode(mode_bytes))

    def set_eq(self, db_offsets: list[int], preset_id: int = 0x00):
        self._submit(self._do_set_eq(db_offsets, preset_id))

    def set_game_mode(self, enabled: bool):
        self._submit(self._do_set_game_mode(enabled))

    def refresh_status(self):
        self._submit(self._do_refresh())

    # ------------------------------------------------------------------
    # Coroutines (run inside BLE thread)
    # ------------------------------------------------------------------

    async def _do_scan(self, timeout: float):
        try:
            devices = await scan(timeout=timeout)
            self.scan_result.emit(devices)
        except Exception as e:
            self.error.emit(f"Scan error: {e}")

    async def _do_connect(self, address: str):
        try:
            self._device = H3Device(address)
            await self._device.connect()
            await self._device.notify_communication_way(way=0, reconnect=0)
            await asyncio.sleep(0.2)
            # Emit connected signal with device name (from adv or address)
            self.connected.emit(address)
            # Read current state
            await self._do_refresh()
        except Exception as e:
            self._device = None
            self.error.emit(f"Conexão falhou: {e}")

    async def _do_disconnect(self):
        if self._device:
            try:
                await self._device.disconnect()
            except Exception:
                pass
            self._device = None
        self.disconnected.emit()

    async def _do_refresh(self):
        dev = self._device
        if dev is None:
            return
        # Battery
        try:
            pkt = await dev.get_battery()
            if pkt and pkt.params:
                tlvs = parse_tlv(pkt.params)
                for t, v in tlvs:
                    if t == AdvType.BATTERY_QUANTITY and len(v) >= 1:
                        self.battery_updated.emit(v[0])
                        break
        except Exception:
            pass
        # Current mode
        try:
            mode = await dev.get_mode()
            if mode is not None:
                self.mode_updated.emit(mode)
        except Exception:
            pass
        # EQ
        try:
            offsets = await dev.get_eq()
            if offsets is not None:
                self.eq_updated.emit(offsets)
        except Exception:
            pass
        # Game mode
        try:
            game = await dev.get_work_mode()
            if game is not None:
                self.game_mode_updated.emit(game)
        except Exception:
            pass

    async def _do_set_mode(self, mode_bytes: bytes):
        dev = self._device
        if dev is None:
            self.error.emit("Não conectado.")
            return
        try:
            await dev.set_mode(mode_bytes)
        except Exception as e:
            self.error.emit(f"Erro ao trocar modo: {e}")

    async def _do_set_eq(self, db_offsets: list[int], preset_id: int = 0x00):
        dev = self._device
        if dev is None:
            self.error.emit("Não conectado.")
            return
        try:
            await dev.set_eq(db_offsets, preset_id)
        except Exception as e:
            self.error.emit(f"Erro ao aplicar EQ: {e}")

    async def _do_set_game_mode(self, enabled: bool):
        dev = self._device
        if dev is None:
            self.error.emit("Não conectado.")
            return
        try:
            await dev.set_game_mode(enabled)
        except Exception as e:
            self.error.emit(f"Erro ao trocar game mode: {e}")

    @property
    def is_connected(self) -> bool:
        return self._device is not None and self._device.is_connected
