"""BLE worker: runs asyncio event loop in a daemon thread.
Qt signals carry results back to the UI thread.
"""
import asyncio
import threading

from PySide6.QtCore import QObject, Signal

from h3s_device import H3SDevice, scan, scan_including_paired
from rcsp import parse_tlv, AdvType


class BleWorker(QObject):
    scan_result      = Signal(list)   # [(addr, name, rssi), ...]
    connected        = Signal(str)    # device address
    disconnected     = Signal()
    error            = Signal(str)
    status           = Signal(str)
    battery_updated  = Signal(int)    # 0-100 %
    mode_updated     = Signal(int)    # 0-4 (NORMAL/TRANSP/ANC_LOW/MED/HIGH)
    eq_updated       = Signal(list)   # 10 ints (1/100-dB offsets)
    game_mode_updated = Signal(bool)  # True=game mode on

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._device: H3SDevice | None = None
        self._ready = threading.Event()
        self._operation_lock: asyncio.Lock | None = None

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
        self._operation_lock = asyncio.Lock()
        self._ready.set()
        self._loop.run_forever()

    def _submit(self, coro):
        if self._loop is None:
            coro.close()
            return

        async def run_serialized():
            # RCSP usa um canal request/response único; não intercalar refresh,
            # scan e ações disparadas rapidamente pela UI.
            async with self._operation_lock:
                await coro

        asyncio.run_coroutine_threadsafe(run_serialized(), self._loop)

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
            if self._device and self._device.is_connected:
                dev = self._device
                self.scan_result.emit([(dev.address, "QCY H3S (conectado)", None)])
                return
            devices = await scan_including_paired(timeout=timeout)
            self.scan_result.emit(devices)
        except Exception as e:
            self.error.emit(f"Scan error: {e}")

    async def _do_connect(self, address: str):
        candidate = H3SDevice(address)
        try:
            if self._device and self._device.is_connected and self._device.address.casefold() == address.casefold():
                self.connected.emit(address)
                await self._do_refresh()
                return
            if self._device:
                try:
                    await self._device.disconnect()
                except Exception:
                    pass
            self._device = candidate
            await candidate.connect(
                on_disconnect=lambda client: self._on_device_disconnected(candidate, client)
            )
            await candidate.notify_communication_way(way=0, reconnect=0)
            if not candidate.is_connected:
                raise RuntimeError("O link BLE caiu durante o handshake RCSP.")
            await asyncio.sleep(0.2)
            # Emit connected signal with device name (from adv or address)
            self.connected.emit(address)
            # Read current state
            await self._do_refresh()
        except Exception as e:
            if self._device is candidate:
                self._device = None
            try:
                await candidate.disconnect()
            except Exception:
                pass
            self.error.emit(f"Conexão/handshake falhou: {e}")

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
        if not dev.is_connected:
            self._on_device_disconnected(dev)
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
            if not dev.is_connected:
                self._on_device_disconnected(dev)
                return
        # Current mode
        try:
            mode = await dev.get_mode()
            if mode is not None:
                self.mode_updated.emit(mode)
        except Exception:
            if not dev.is_connected:
                self._on_device_disconnected(dev)
                return
        # EQ
        try:
            offsets = await dev.get_eq()
            if offsets is not None:
                self.eq_updated.emit(offsets)
        except Exception:
            if not dev.is_connected:
                self._on_device_disconnected(dev)
                return
        # Game mode
        try:
            game = await dev.get_work_mode()
            if game is not None:
                self.game_mode_updated.emit(game)
        except Exception:
            if not dev.is_connected:
                self._on_device_disconnected(dev)
                return

    async def _do_set_mode(self, mode_bytes: bytes):
        dev = self._device
        if dev is None:
            self.error.emit("Não conectado.")
            return
        try:
            response = await dev.set_mode(mode_bytes)
            from h3s_device import ANCMode
            requested = ANCMode.from_params(mode_bytes)
            await asyncio.sleep(0.25)
            if not dev.is_connected:
                self._on_device_disconnected(dev)
                return
            observed = await dev.get_mode()
            # GET 0x17 pode ecoar o payload do SET neste firmware. Não pintar
            # a UI com o valor pedido: só aceitar leitura que corresponda.
            if observed is not None and requested is not None and observed == requested:
                self.mode_updated.emit(observed)
                self.status.emit(f"Modo confirmado pelo fone: {ANCMode.NAMES[observed]}.")
            elif response is not None and response.status == 0:
                self.status.emit("Comando ANC entregue, mas o fone não confirmou o modo por leitura.")
            else:
                self.status.emit("O fone não confirmou a troca de modo; mantendo o estado anterior.")
            if observed is not None and requested is not None and observed != requested:
                self.mode_updated.emit(observed)
        except Exception as e:
            if not dev.is_connected:
                self._on_device_disconnected(dev)
            self.error.emit(f"Erro ao trocar modo: {e}")

    def _on_device_disconnected(self, device: H3SDevice, _client=None):
        if self._device is device:
            self._device = None
            self.disconnected.emit()

    async def _do_set_eq(self, db_offsets: list[int], preset_id: int = 0x00):
        dev = self._device
        if dev is None:
            self.error.emit("Não conectado.")
            return
        try:
            await dev.set_eq(db_offsets, preset_id)
            await asyncio.sleep(0.25)
            actual = await dev.get_eq()
            if actual is not None and actual == db_offsets:
                self.eq_updated.emit(actual)
                self.status.emit("Equalizador confirmado pelo fone.")
            elif actual is not None:
                self.eq_updated.emit(actual)
                self.status.emit("O fone não aplicou os valores pedidos; sliders restaurados ao EQ lido.")
            else:
                self.status.emit("EQ enviado, mas o fone não devolveu leitura para confirmar.")
        except Exception as e:
            if not dev.is_connected:
                self._on_device_disconnected(dev)
            self.error.emit(f"Erro ao aplicar EQ: {e}")

    async def _do_set_game_mode(self, enabled: bool):
        dev = self._device
        if dev is None:
            self.error.emit("Não conectado.")
            return
        try:
            await dev.set_game_mode(enabled)
            actual = await dev.get_work_mode()
            if actual is not None:
                self.game_mode_updated.emit(actual)
                self.status.emit(f"Modo de baixa latência {'ativado' if actual else 'desativado'} (lido do fone).")
            else:
                self.status.emit("Comando de baixa latência enviado; o fone não devolveu o estado.")
        except Exception as e:
            if not dev.is_connected:
                self._on_device_disconnected(dev)
            self.error.emit(f"Erro ao trocar game mode: {e}")

    @property
    def is_connected(self) -> bool:
        return self._device is not None and self._device.is_connected
