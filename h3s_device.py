"""QCY H3 BLE device controller."""
import asyncio
import sys
from types import SimpleNamespace
from typing import Callable

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

from rcsp import AdvType, HEADER, OpCode, Packet, TYPE_COMMAND, hex_str

# ANC/mode command bytes (Custom opCode 255)
class ANCMode:
    # ATENÇÃO: o byte que decide o modo é `params[2]` — ver `from_params()`.
    #   0x02 = ANC desligado | 0x03 = transparência | 0x01 = ANC por grupo/nível
    #
    # Até 29/10/2026 as duas primeiras constantes tinham NOME TROCADO em relação
    # ao payload (a chamada `TRANSPARENCY` na verdade mandava ANC desligado, e
    # `NORMAL` mandava transparência). A ordem de `ALL` estava certa, então o
    # app funcionava; mas o nome mentia e qualquer refactor "arrumando" a ordem
    # fazia o fone trocar os dois modos. Nomes corrigidos, ordem preservada.
    ANC_OFF         = bytes([0x17, 0x03, 0x02, 0x00, 0x00])  # ANC desligado
    TRANSPARENCY    = bytes([0x17, 0x03, 0x03, 0x01, 0x04])  # Transparência (ambiente)

    NOISY_LOW       = bytes([0x17, 0x03, 0x01, 0x01, 0x00])  # Ruído baixo
    NOISY_MED       = bytes([0x17, 0x03, 0x01, 0x01, 0x01])  # Ruído médio
    NOISY_HIGH      = bytes([0x17, 0x03, 0x01, 0x01, 0x02])  # Ruído alto
    NOISY_MAX       = bytes([0x17, 0x03, 0x01, 0x01, 0x03])  # Ruído máximo
    NOISY_ULTRA     = bytes([0x17, 0x03, 0x01, 0x01, 0x04])  # Ruído ultra (AI)

    COMMUTING_LOW   = bytes([0x17, 0x03, 0x01, 0x02, 0x00])  # Transporte baixo
    COMMUTING_MED   = bytes([0x17, 0x03, 0x01, 0x02, 0x01])  # Transporte médio
    COMMUTING_HIGH  = bytes([0x17, 0x03, 0x01, 0x02, 0x02])  # Transporte alto

    INDOOR_LOW      = bytes([0x17, 0x03, 0x01, 0x03, 0x00])  # Interior baixo
    INDOOR_MED      = bytes([0x17, 0x03, 0x01, 0x03, 0x01])  # Interior médio
    INDOOR_HIGH     = bytes([0x17, 0x03, 0x01, 0x03, 0x02])  # Interior alto

    ANTIWIND        = bytes([0x17, 0x03, 0x01, 0x04, 0x00])  # Anti-vento
    ADAPTIVE        = bytes([0x17, 0x03, 0x01, 0x05, 0x00])  # Adaptativo (AI)

    # Alias legado: o nome antigo `NORMAL` significava transparência.
    NORMAL = TRANSPARENCY

    # Ordem canônica: TEM de casar com a numeração devolvida por `from_params()`.
    # 0 = ANC desligado, 1 = transparência, 2..6 = níveis de ANC, 7 = adaptativo.
    ALL = [
        ANC_OFF, TRANSPARENCY,
        NOISY_LOW, NOISY_MED, NOISY_HIGH, NOISY_MAX, NOISY_ULTRA,
        ADAPTIVE,
    ]

    NAMES = [
        "ANC desligado", "Transparência",
        "ANC baixo", "ANC médio", "ANC alto", "ANC máximo", "ANC ultra",
        "Adaptativo (AI)",
    ]

    @staticmethod
    def from_params(params: bytes) -> int | None:
        if len(params) < 5:
            return None
        sub   = params[2]
        group = params[3]
        level = params[4]
        if sub == 0x02:
            return 0   # ANC Desligado
        if sub == 0x03:
            return 1   # Transparência
        if sub == 0x01:
            # IMPORTANTE: checar o grupo ANTES do nível. O H3S aceita e devolve
            # níveis fora da faixa (testado com 0x05, 0x06, 0x0A e 0xFF), então
            # `2 + level` colidia com o índice 7 do adaptativo e estourava para 8.
            if group == 0x05:
                return 7           # Adaptativo (AI)
            if group == 0x01 and level <= 4:
                return 2 + level   # ANC Low..Ultra
        return None


# EQ band configuration (10 bands matching QCY app)
EQ_BANDS_FREQS = [0x0037, 0x00DC, 0x01F4, 0x03E8, 0x0708, 0x0AF0, 0x1194, 0x1D4C, 0x2710, 0x55F0]
EQ_BAND_LABELS = ["55 Hz", "220 Hz", "500 Hz", "1 kHz", "1.8 kHz", "2.8 kHz", "4.5 kHz", "7.5 kHz", "10 kHz", "22 kHz"]
# (ref_gain, Q) per frequency - sourced from device GET response & HCI capture
EQ_BAND_DEFAULTS = {
    0x0037: (40,  2),   # 55 Hz
    0x00DC: (120, 2),   # 220 Hz
    0x01F4: (150, 2),   # 500 Hz
    0x03E8: (150, 2),   # 1 kHz
    0x0708: (120, 2),   # 1.8 kHz
    0x0AF0: (80,  2),   # 2.8 kHz
    0x1194: (130, 2),   # 4.5 kHz  (Q=2 entry from GET)
    0x1D4C: (120, 2),   # 7.5 kHz
    0x2710: (120, 2),   # 10 kHz
    0x55F0: (80,  2),   # 22 kHz   (extrapolated)
}
# EQ preset IDs: 0x00 = custom (user-defined via sliders), 0x01-0x06 = named presets
EQ_PRESETS = [
    ("Custom",      0x00),
    ("Default",     0x01),
    ("Pop",         0x02),
    ("Heavy Bass",  0x03),
    ("Rock",        0x04),
    ("Soft",        0x05),
    ("Classic",     0x06),
]
EQ_PRESET_NAMES = [name for name, _ in EQ_PRESETS]
EQ_PRESET_IDS   = [pid  for _, pid  in EQ_PRESETS]

# Default band values per preset in 1/100-dB units (10 bands)
# Custom starts flat so user can adjust from scratch
EQ_PRESET_OFFSETS: dict[int, list[int]] = {
    0x00: [0,   0,   0,    0,    0,    0,    0,    0,    0,   0],   # Custom
    0x01: [0,   0,   0,    0,    0,    0,    0,    0,    0,   0],   # Default
    0x02: [0,   150, 150,  100,  0,    100,  200,  200,  150, 100], # Pop
    0x03: [500, 400, 200,  0,   -100,  0,    0,    100,  200, 100], # Heavy Bass
    0x04: [400, 300, 0,   -200, -100,  0,    200,  300,  400, 200], # Rock
    0x05: [100, 100, 100,  100,  100,  100,  100,  100,  100, 100], # Soft
    0x06: [0,   0,   100,  300,  300,  300,  200,  100,  100, 0],   # Classic
}

SERVICE_UUID = "0000a002-0000-1000-8000-00805f9b34fb"
WRITE_UUID = "00000001-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "00000002-0000-1000-8000-00805f9b34fb"


def _clamp(value: int, lo: int, hi: int, name: str) -> int:
    """Clamp an int to [lo, hi] and refuse non-ints.

    Sem isso, `set_volume(300, 300)` virava `bytes([44, 44])` silenciosamente
    porque o valor era truncado com `& 0xFF`.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be int, got {type(value).__name__}")
    return max(lo, min(hi, value))


class H3SDevice:
    def __init__(self, address: str):
        self.address = address
        self._client: BleakClient | None = None
        self._sn = 0
        # BLE GATT command/response is a single RCSP channel. Concurrent
        # coroutines can otherwise consume each other's sequence-number reply.
        self._send_lock = asyncio.Lock()
        self._pending: dict[int, asyncio.Future[Packet]] = {}
        self._rx_buffer = bytearray()
        self.on_notification: Callable[[Packet], None] | None = None
        self.on_raw: Callable[[bytes], None] | None = None

    async def connect(self, on_disconnect=None) -> None:
        # On Windows, passing a MAC string makes Bleak launch an implicit BLE
        # scan. Paired/connected H3S devices often stop advertising, although
        # WinRT can still resolve their cached BluetoothLEDevice by address.
        target = _ble_device_for_address(self.address)
        self._client = BleakClient(
            target,
            timeout=15.0,
            disconnected_callback=on_disconnect,
        )
        await self._client.connect()
        await self._client.start_notify(NOTIFY_UUID, self._handle_notify)

    async def disconnect(self) -> None:
        if self._client and self._client.is_connected:
            try:
                await self._client.stop_notify(NOTIFY_UUID)
            except Exception:
                pass
            await self._client.disconnect()

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    def _next_sn(self) -> int:
        self._sn = (self._sn + 1) & 0xFF
        if self._sn == 0:
            self._sn = 1
        return self._sn

    def _handle_notify(self, _sender, data: bytearray) -> None:
        if self.on_raw:
            self.on_raw(bytes(data))
        self._rx_buffer.extend(data)
        while True:
            idx = self._rx_buffer.find(HEADER)
            if idx < 0:
                self._rx_buffer.clear()
                return
            if idx > 0:
                del self._rx_buffer[:idx]
            if len(self._rx_buffer) < 8:
                return
            param_len = (self._rx_buffer[5] << 8) | self._rx_buffer[6]
            total = 7 + param_len + 1
            if len(self._rx_buffer) < total:
                return
            pkt_bytes = bytes(self._rx_buffer[:total])
            del self._rx_buffer[:total]
            pkt = Packet.decode(pkt_bytes)
            if pkt is None:
                continue
            fut = self._pending.pop(pkt.sn, None)
            if fut and not fut.done():
                fut.set_result(pkt)
            elif self.on_notification:
                self.on_notification(pkt)

    async def send(self, pkt: Packet, timeout: float = 2.0) -> Packet | None:
        async with self._send_lock:
            if not self._client or not self._client.is_connected:
                raise RuntimeError("Not connected")
            if pkt.sn == 0:
                pkt.sn = self._next_sn()
            data = pkt.encode()
            fut: asyncio.Future[Packet] | None = None
            if pkt.has_response:
                fut = asyncio.get_running_loop().create_future()
                self._pending[pkt.sn] = fut
            await self._client.write_gatt_char(WRITE_UUID, data, response=False)
            if fut is None:
                return None
            try:
                return await asyncio.wait_for(fut, timeout=timeout)
            except asyncio.TimeoutError:
                self._pending.pop(pkt.sn, None)
                return None

    async def notify_communication_way(self, way: int = 0, reconnect: int = 0) -> Packet | None:
        """Tell device we're on BLE (way=0) vs SPP (way=1). Required after BLE connect."""
        return await self.send(
            Packet(op_code=OpCode.NOTIFY_COMMUNICATION_WAY, params=bytes([way, reconnect]))
        )

    async def get_target_info(self) -> Packet | None:
        return await self.send(Packet(op_code=OpCode.GET_TARGET_INFO, params=b""))

    async def get_target_feature_map(self) -> Packet | None:
        return await self.send(Packet(op_code=OpCode.GET_TARGET_FEATURE_MAP, params=b""))

    async def set_anc_mode(self, mode: int) -> Packet | None:
        """Set ANC level. mode=0 (low), 1 (medium), 2 (high)."""
        return await self.send(
            Packet(op_code=OpCode.CUSTOM, params=bytes([0x17, 0x03, 0x01, 0x01, mode & 0xFF]))
        )

    async def set_mode(self, mode_bytes: bytes) -> Packet | None:
        """Set noise mode using raw 5-byte ANCMode constant."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=mode_bytes))

    async def get_mode(self) -> int | None:
        """Get current mode. Returns mode index 0-4 (NORMAL/TRANSP/ANC_LOW/MED/HIGH) or None."""
        resp = await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0xFE, 0x01, 0x17])))
        if resp is None or len(resp.params) < 5:
            return None
        return ANCMode.from_params(resp.params)

    async def get_anc_state(self) -> Packet | None:
        """Get current ANC state raw packet."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0xFE, 0x01, 0x17])))

    async def get_eq(self) -> list[int] | None:
        """Get current EQ. Returns 10 db_offset values in 1/100-dB units, or None.
        For duplicate frequencies (e.g. 4500 Hz appears twice in device response),
        the last entry wins — which is the user-adjustable Q=2 copy."""
        resp = await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0xFE, 0x01, 0x22])))
        if resp is None or len(resp.params) < 2 or resp.params[0] != 0x22:
            return None
        ll = resp.params[1]
        data = resp.params[2:2 + ll]
        if len(data) < 3 + 7 * 7:
            return None
        bands: dict[int, int] = {}
        num_entries = (len(data) - 3) // 7
        for i in range(num_entries):
            base = 3 + i * 7
            b = data[base:base + 7]
            freq = int.from_bytes(b[0:2], "little")
            db_off = int.from_bytes(b[2:4], "little", signed=True)
            if freq in EQ_BANDS_FREQS:
                bands[freq] = db_off  # last entry wins for duplicates
        if not bands:
            return None
        return [bands.get(f, 0) for f in EQ_BANDS_FREQS]

    async def set_eq(self, db_offsets: list[int], preset_id: int = 0x00) -> Packet | None:
        """Set EQ. db_offsets: 10 values in 1/100-dB (-1200..+1200).
        preset_id: 0x00=custom, 0x01=Default, 0x02=Pop ... 0x06=Classic."""
        if not isinstance(db_offsets, (list, tuple)):
            raise TypeError("db_offsets must be a list of 10 ints")
        if len(db_offsets) != len(EQ_BANDS_FREQS):
            raise ValueError(f"db_offsets must have {len(EQ_BANDS_FREQS)} values, got {len(db_offsets)}")
        preset_id = _clamp(preset_id, 0x00, 0x06, "preset_id")
        band_bytes = bytearray()
        for i, freq in enumerate(EQ_BANDS_FREQS):
            ref_gain, q = EQ_BAND_DEFAULTS[freq]
            db_off = _clamp(db_offsets[i], -1200, 1200, f"db_offsets[{i}]")
            band_bytes += freq.to_bytes(2, "little")
            band_bytes += db_off.to_bytes(2, "little", signed=True)
            band_bytes += ref_gain.to_bytes(2, "little")
            band_bytes += bytes([q])
        header = bytes([preset_id & 0xFF, 0x70, 0xFE])
        data_len = len(header) + len(band_bytes)  # 3 + 10*7 = 73
        payload = bytes([0x22, data_len & 0xFF]) + header + bytes(band_bytes)
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=payload))

    async def get_work_mode(self) -> bool | None:
        """Get current work mode. Returns True=game mode, False=normal, None=unknown."""
        pkt = await self.get_adv_info(1 << AdvType.WORK_MODE)
        if pkt is None or not pkt.params:
            return None
        from rcsp import parse_tlv
        for t, v in parse_tlv(pkt.params):
            if t == AdvType.WORK_MODE and len(v) >= 1:
                return v[0] == 0x02
        return None

    async def set_game_mode(self, enabled: bool) -> Packet | None:
        """Enable or disable game mode (low-latency audio)."""
        val = 0x02 if enabled else 0x01
        return await self.send(
            Packet(op_code=OpCode.SET_ADV_INFO, params=bytes([0x02, AdvType.WORK_MODE, val]))
        )

    async def get_sys_info(self, function: int, mask: int) -> Packet | None:
        """GetSysInfo with function (BT=0, PUBLIC=0xFF, etc.) and 32-bit attr mask."""
        params = bytes([function & 0xFF]) + mask.to_bytes(4, "big")
        return await self.send(Packet(op_code=OpCode.GET_SYS_INFO, params=params))

    async def get_adv_info(self, mask: int) -> Packet | None:
        """Get ADV info. mask is a 32-bit bitfield: bit N = AdvType N.
        Examples: 0x0001 = battery only, 0xFFFFFFFF = all."""
        return await self.send(
            Packet(
                op_code=OpCode.GET_ADV_INFO,
                params=mask.to_bytes(4, "big"),
            )
        )

    async def get_battery(self) -> Packet | None:
        return await self.get_adv_info(1 << AdvType.BATTERY_QUANTITY)

    # ── H3S-specific features (Jieli RCSP Custom sub-protocol) ──

    async def get_wind_noise(self) -> Packet | None:
        """Get wind noise reduction state (cmd 0x2A)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0xFE, 0x01, 0x2A])))

    async def set_wind_noise(self, enabled: bool) -> Packet | None:
        """Enable/disable wind noise reduction (cmd 0x2A)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0x2A, 0x01, 0x01 if enabled else 0x00])))

    async def get_wear_status(self) -> Packet | None:
        """Get wear detection status (cmd 0x62)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0xFE, 0x01, 0x62])))

    async def set_wear_config(self, enabled: bool) -> Packet | None:
        """Enable/disable wear detection (cmd 0x2C).

        Formato correto (Quicky): [0x2C, 0x03, enable, musicIndex, ancIndex]
        enable: 0x01=on, 0x02=off. musicIndex=0x01 (pausa música ao remover),
        ancIndex=0x00 (sem mudança de ANC).
        """
        val = 0x01 if enabled else 0x02
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0x2C, 0x03, val, 0x01, 0x00])))

    async def set_music_mode(self, mode: int) -> Packet | None:
        """Set audio scene mode (cmd 0x2E): 0=Music, 1=Movie, 2=Game."""
        mode = _clamp(mode, 0, 2, "music mode")
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0x2E, 0x01, mode])))

    async def get_music_mode(self) -> int | None:
        """Read audio scene mode (cmd 0x2E), if returned by this firmware."""
        params = await self.read_custom(0x2E)
        return params[2] if params and len(params) >= 3 else None

    async def set_multipoint(self, enabled: bool) -> Packet | None:
        """Enable/disable multipoint (dual connection) (cmd 0x24).

        Pode reiniciar o fone; use com cuidado. LDAC deve estar off.
        """
        val = 0x01 if enabled else 0x00
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0x24, 0x01, val])))

    async def get_spatial_audio(self) -> Packet | None:
        """Get spatial audio mode (cmd 0x5B)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0xFE, 0x01, 0x5B])))

    async def set_spatial_audio(self, enabled: bool) -> Packet | None:
        """Enable/disable spatial audio (cmd 0x5B)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0x5B, 0x01, 0x01 if enabled else 0x00])))

    async def find_earphones(self) -> Packet | None:
        """Trigger find earphones (play sound) (cmd 0x4B)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0x4B, 0x01, 0x01])))

    async def get_ai_anc(self) -> Packet | None:
        """Get AI ANC state (cmd 0x54)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0xFE, 0x01, 0x54])))

    async def set_ai_anc(self, enabled: bool) -> Packet | None:
        """Enable/disable AI ANC (cmd 0x54)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0x54, 0x01, 0x01 if enabled else 0x00])))

    async def get_hearing_safety(self) -> Packet | None:
        """Get hearing safety state (cmd 0x58)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0xFE, 0x01, 0x58])))

    async def get_device_info(self) -> Packet | None:
        """Get device info (cmd 0xF7)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0xFE, 0x01, 0xF7])))

    async def get_touch_tone(self) -> Packet | None:
        """Get touch tone state (cmd 0x31)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0xFE, 0x01, 0x31])))

    async def set_touch_tone(self, enabled: bool) -> Packet | None:
        """Enable/disable touch tone (cmd 0x31)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0x31, 0x01, 0x01 if enabled else 0x00])))

    async def get_power_manager(self) -> Packet | None:
        """Get power manager info (cmd 0x14)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0xFE, 0x01, 0x14])))

    async def get_head_action(self) -> Packet | None:
        """Get head action / wear detection config (cmd 0x50)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0xFE, 0x01, 0x50])))

    async def get_focus_mode(self) -> Packet | None:
        """Get focus mode state (cmd 0x39)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0xFE, 0x01, 0x39])))

    async def get_privacy_mode(self) -> Packet | None:
        """Get privacy mode state (cmd 0x5F)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0xFE, 0x01, 0x5F])))

    async def get_anc_wear(self) -> Packet | None:
        """Get ANC wear detection state (cmd 0x29)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0xFE, 0x01, 0x29])))

    async def get_env_adaptation(self) -> Packet | None:
        """Get environment adaptation state (cmd 0x32)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0xFE, 0x01, 0x32])))

    async def get_led_effect(self) -> Packet | None:
        """Get LED effect (cmd 0x36)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0xFE, 0x01, 0x36])))

    async def get_led_switch(self) -> Packet | None:
        """Get LED switch (cmd 0x35)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0xFE, 0x01, 0x35])))

    async def get_space_sound(self) -> Packet | None:
        """Get spatial sound state (cmd 0x2D)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0xFE, 0x01, 0x2D])))

    # ── Music & Audio ──

    async def music_control(self, action: int) -> Packet | None:
        """Music control (cmd 0x04). action: 1=play, 2=pause, 3=prev, 4=next."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0x04, 0x01, action])))

    async def set_volume(self, left: int, right: int) -> Packet | None:
        """Set volume L/R (cmd 0x08). Validado em 0-100."""
        left = _clamp(left, 0, 100, "left")
        right = _clamp(right, 0, 100, "right")
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0x08, 0x03, left, right, 0x00])))

    async def set_music_mode(self, mode: int) -> Packet | None:
        """Set music mode (cmd 0x2E)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0x2E, 0x01, mode])))

    async def set_play_mode(self, mode: int) -> Packet | None:
        """Set play mode (cmd 0x37)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0x37, 0x01, mode])))

    async def get_music_state(self) -> Packet | None:
        """Get music state (cmd 0x3A)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0xFE, 0x01, 0x3A])))

    async def get_music_info(self) -> Packet | None:
        """Get music info (cmd 0x3B)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0xFE, 0x01, 0x3B])))

    # ── LDAC ──

    async def set_ldac(self, enabled: bool) -> Packet | None:
        """Enable/disable LDAC (cmd 0x23). Warning: may restart headphone."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0x23, 0x01, 0x01 if enabled else 0x00])))

    # ── Sleep / Standby / Power ──

    async def set_sleep_mode(self, enabled: bool) -> Packet | None:
        """Enable/disable sleep mode (cmd 0x10)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0x10, 0x01, 0x01 if enabled else 0x00])))

    async def set_disconnect_power(self, timeout: int) -> Packet | None:
        """Set disconnect power timeout (cmd 0x1F). timeout in seconds (0=never)."""
        low = timeout & 0xFF
        high = (timeout >> 8) & 0xFF
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0x1F, 0x02, low, high])))

    async def set_power_manager(self, timeout: int) -> Packet | None:
        """Set power manager timeout (cmd 0x14)."""
        low = timeout & 0xFF
        high = (timeout >> 8) & 0xFF
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0x14, 0x04, low, high, 0x00, 0x00])))

    # ── Sync Time ──

    async def sync_time(self, year, month, day, hour, minute, second, weekday=1) -> Packet | None:
        """Sync device clock (cmd 0x3E / CMDID_SYNC_TIME). weekday: 1=Mon..7=Sun.

        ATENÇÃO: até 29/10/2026 isso mandava `month + 1`, o que em dezembro
        gerava mês 13. O layout do protocolo não está confirmado; assumimos
        mês 1-based. Marca como NÃO TESTADO em docs/COMANDOS-DESTRUTIVOS.md.
        """
        payload = bytes([
            0x3E, 0x07,
            _clamp(year, 0, 99, "year"),
            _clamp(month, 1, 12, "month"),
            _clamp(day, 1, 31, "day"),
            _clamp(hour, 0, 23, "hour"),
            _clamp(minute, 0, 59, "minute"),
            _clamp(second, 0, 59, "second"),
            1 << (_clamp(weekday, 1, 7, "weekday") - 1),
        ])
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=payload))

    # ── Alarm ──

    async def set_alarm(self, data: bytes) -> Packet | None:
        """Set alarm (cmd 0x3F). data = alarm config bytes."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0x3F]) + bytes([len(data)]) + data))

    # ── Take Photo ──

    async def take_photo(self) -> Packet | None:
        """Remote shutter (cmd 0x1E)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0x1E, 0x01, 0x01])))

    # ── Light ──

    async def set_light(self, enabled: bool) -> Packet | None:
        """Enable/disable flashlight (cmd 0x05)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0x05, 0x01, 0x01 if enabled else 0x00])))

    # ── Reset / Pair ──

    async def reset_default(self) -> Packet | None:
        """Reset to default settings (cmd 0x01)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0x01, 0x00])))

    async def clear_pair(self) -> Packet | None:
        """Clear pairing records (cmd 0x02)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0x02, 0x00])))

    async def factory_reset(self) -> Packet | None:
        """Factory reset (cmd 0x03)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0x03, 0x00])))

    # ── TWS ──

    async def set_tws_enable(self, enabled: bool) -> Packet | None:
        """Enable/disable TWS (cmd 0x34)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0x34, 0x01, 0x01 if enabled else 0x00])))

    # ── LED ──

    async def set_led_mode(self, enabled: bool) -> Packet | None:
        """Enable/disable LED (cmd 0x12)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0x12, 0x01, 0x01 if enabled else 0x00])))

    async def get_led_mode(self) -> Packet | None:
        """Get LED mode (cmd 0x12 read)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0xFE, 0x01, 0x12])))

    async def set_led_switch(self, enabled: bool) -> Packet | None:
        """Enable/disable LED switch (cmd 0x35)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0x35, 0x01, 0x01 if enabled else 0x00])))

    # ── Tone ──

    async def set_tone_volume(self, volume: int) -> Packet | None:
        """Set tone/notification volume (cmd 0x1D). Faixa real: 0-8.

        O firmware espera `[0x1D, 0x02, volume, 0x00]` - payload de DOIS bytes.
        Antes daqui o codigo mandava `[0x1D, 0x01, volume]` (um byte) e o fone
        descartava em silencio: `set_tone_volume(10)` deixava o valor em 6 e
        ninguem percebia, porque a leitura tambem nao era feita.
        Medido em 29/10/2026: 0x00..0x08 sao aceitos e ecoados na leitura
        `1D 02 <valor> 08`; o 4o byte (0x08) e o maximo e pode ir 0x00 no SET.
        """
        volume = _clamp(volume, 0, 8, "tone volume")
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0x1D, 0x02, volume, 0x00])))

    async def play_tone(self, tone_id: int) -> Packet | None:
        """Play test tone (cmd 0x3D)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0x3D, 0x01, tone_id & 0xFF])))

    async def set_tone_name(self, name: str) -> Packet | None:
        """Set voice/tone name language (cmd 0x19)."""
        data = name.encode("utf-8")
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0x19, len(data)]) + data))

    async def set_voice_language(self, lang: int) -> Packet | None:
        """Set voice language (cmd 0x1A)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0x1A, 0x01, lang & 0xFF])))

    # ── Pair Name ──

    async def set_pair_name(self, name: str) -> Packet | None:
        """Set pairing name (cmd 0x18)."""
        data = name.encode("utf-8")
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0x18, len(data)]) + data))

    async def get_pair_name(self) -> Packet | None:
        """Get pairing name (cmd 0x18 read)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0xFE, 0x01, 0x18])))

    # ── Balance ──

    async def set_balance(self, balance: int) -> Packet | None:
        """Set L/R balance (cmd 0x16). Validado em 0-255."""
        balance = _clamp(balance, 0, 255, "balance")
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0x16, 0x01, balance])))

    # ── In-Ear Sensitivity ──

    async def set_inear_sensitivity(self, sensitivity: int) -> Packet | None:
        """Set in-ear sensitivity (cmd 0x48). Validado em 0-255."""
        sensitivity = _clamp(sensitivity, 0, 255, "sensitivity")
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0x48, 0x01, sensitivity])))

    async def get_inear_sensitivity(self) -> Packet | None:
        """Get in-ear sensitivity (cmd 0x48 read)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0xFE, 0x01, 0x48])))

    # ── Compactness / Fit Test ──

    async def set_compactness(self, left: bool, right: bool) -> Packet | None:
        """Fit test / compactness (cmd 0x11)."""
        l = 0x01 if left else 0x02
        r = 0x01 if right else 0x02
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0x11, 0x02, l, r])))

    async def get_compactness(self) -> Packet | None:
        """Get compactness result (cmd 0x11 read)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0xFE, 0x01, 0x11])))

    # ── Adapt Volume ──

    async def set_adapt_volume(self, enabled: bool) -> Packet | None:
        """Enable/disable adaptive volume (cmd 0x40)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0x40, 0x01, 0x01 if enabled else 0x00])))

    async def get_adapt_volume(self) -> Packet | None:
        """Get adaptive volume state (cmd 0x40 read)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0xFE, 0x01, 0x40])))

    # ── Device Color ──

    async def set_device_color(self, color: int) -> Packet | None:
        """Set device color (cmd 0x42)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0x42, 0x01, color & 0xFF])))

    async def get_device_color(self) -> Packet | None:
        """Get device color (cmd 0x42 read)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0xFE, 0x01, 0x42])))

    # ── Touch Button Remap (KEYFUN) ──

    async def set_key_settings(self, triples: list[tuple[int, int, int]]) -> Packet | None:
        """Grava o mapa de botoes via SET_ADV_INFO (0xC0), tipo 2.

        O APK NAO usa `0x2B` para isso: `BtRcspOpImpl.configKeySettings()` monta
        um LTV (`packLTVPacket(2, dados)`) e chama `modifyAdvInfo(2, ...)`.
        Ou seja payload `[len, 0x02, keyNum, action, function, ...]`, com
        `len = 1 + 3*N`. Para as 15 entradas do H3S: `[0x2E, 0x02, ...]`.

        NUNCA mande lista parcial: o SDK trata a lista inteira como a config
        completa dos botoes.
        """
        value = b"".join(bytes((k & 0xFF, a & 0xFF, f & 0xFF)) for k, a, f in triples)
        if not value:
            raise ValueError("lista de botoes vazia")
        if len(value) > 254:
            raise ValueError(f"mapa grande demais ({len(triples)} entradas)")
        ltv = bytes((len(value) + 1, 0x02)) + value
        return await self.send(Packet(op_code=OpCode.SET_ADV_INFO, params=ltv))

    async def set_adv_info(self, param: bytes) -> Packet | None:
        """Envia SET_ADV_INFO cru (0xC0). `param` deve ser um LTV completo."""
        return await self.send(Packet(op_code=OpCode.SET_ADV_INFO, params=param))

    async def set_button_func(self, key_id: int, func_id: int, action: int = 1) -> Packet | None:
        """Remapeia UM botao (key_id + action) preservando o resto do mapa.

        Le o mapa atual, troca a entrada e regrava a lista inteira. `func_id`
        0x00 = sem funcao, 0xFF = trocar modo ANC, 0x7F tambem = sem funcao
        (o APK traduz 127 -> 0 em `changeJL2QCY`).
        """
        key_id = _clamp(key_id, 0, 255, "key_id")
        action = _clamp(action, 1, 5, "action")
        func_id = _clamp(func_id, 0, 255, "func_id")
        current = await self.get_key_settings()
        if not current:
            raise RuntimeError("fone nao devolveu o mapa de botoes; abortando sem gravar")
        updated = [
            (k, a, func_id if (k == key_id and a == action) else f)
            for k, a, f in current
        ]
        return await self.set_key_settings(updated)

    async def get_button_func(self) -> Packet | None:
        """Get button mapping (cmd 0x2B read)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0xFE, 0x01, 0x2B])))

    # ── Environment Adaptation ──

    async def set_env_adaptation(self, enabled: bool) -> Packet | None:
        """Enable/disable environment adaptation (cmd 0x32)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0x32, 0x01, 0x01 if enabled else 0x00])))

    async def get_env_adaptation(self) -> Packet | None:
        """Get environment adaptation (cmd 0x32 read)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0xFE, 0x01, 0x32])))

    # ── LED Effect ──

    async def set_led_effect(self, speed: int, bright: int, effect_index: int, colors: list[int]) -> Packet | None:
        """Set LED effect (cmd 0x36). colors: list of RGB triples (flat)."""
        color_bytes = bytearray()
        for c in colors:
            color_bytes.append((c >> 16) & 0xFF)
            color_bytes.append((c >> 8) & 0xFF)
            color_bytes.append(c & 0xFF)
        params = bytes([0x36, 3 + len(color_bytes), speed & 0xFF, bright & 0xFF, effect_index & 0xFF]) + bytes(color_bytes)
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=params))

    # ── Focus Mode ──

    async def set_focus_mode(self, enabled: bool) -> Packet | None:
        """Enable/disable focus mode (cmd 0x39)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0x39, 0x01, 0x01 if enabled else 0x00])))

    async def get_focus_mode(self) -> Packet | None:
        """Get focus mode (cmd 0x39 read)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0xFE, 0x01, 0x39])))

    # ── Privacy Mode ──

    async def set_privacy_mode(self, enabled: bool) -> Packet | None:
        """Enable/disable privacy mode (cmd 0x5F)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0x5F, 0x01, 0x01 if enabled else 0x00])))

    async def get_privacy_mode(self) -> Packet | None:
        """Get privacy mode (cmd 0x5F read)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0xFE, 0x01, 0x5F])))

    # ── Spatial Sound ──

    async def set_space_sound(self, enabled: bool) -> Packet | None:
        """Enable/disable spatial sound (cmd 0x2D)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0x2D, 0x01, 0x01 if enabled else 0x00])))

    # ── Hearing Safety ──

    async def get_hearing_safety(self) -> Packet | None:
        """Get hearing safety data (cmd 0x58)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0xFE, 0x01, 0x58])))

    # ── AI ANC Config ──

    async def set_ai_anc_config(self, data: bytes) -> Packet | None:
        """Set AI ANC config (cmd 0x55)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0x55, len(data)]) + data))

    async def set_ai_anc_config2(self, data: bytes) -> Packet | None:
        """Set AI ANC config v2 (cmd 0x56)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0x56, len(data)]) + data))

    async def get_ai_anc_preview(self) -> Packet | None:
        """Get AI ANC preview (cmd 0x5A)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0xFE, 0x01, 0x5A])))

    # ── Tone Name ──

    async def get_tone_name(self) -> Packet | None:
        """Get tone/voice name (cmd 0x19 read)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0xFE, 0x01, 0x19])))

    async def get_voice_language(self) -> Packet | None:
        """Get voice language (cmd 0x1A read)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0xFE, 0x01, 0x1A])))

    # ── Phone Info ──

    async def get_phone_info(self) -> Packet | None:
        """Get phone info (cmd 0x4D)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0xFE, 0x01, 0x4D])))

    async def get_phone_status(self) -> Packet | None:
        """Get phone status (cmd 0x4F)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0xFE, 0x01, 0x4F])))

    # ── Music Status/Info ──

    async def get_music_status(self) -> Packet | None:
        """Get music status (cmd 0x3A)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0xFE, 0x01, 0x3A])))

    # ── Space Audio Mode ──

    async def set_space_audio_mode(self, enabled: bool) -> Packet | None:
        """Enable/disable spatial audio mode (cmd 0x5B)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0x5B, 0x01, 0x01 if enabled else 0x00])))

    async def get_space_audio_mode(self) -> Packet | None:
        """Get spatial audio mode (cmd 0x5B read)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0xFE, 0x01, 0x5B])))

    # ─────────────────────────────────────────────────────────────────────────
    # Leituras QUE EXISTEM neste firmware
    #
    # Varredura de 0x01..0x63 em 29/10/2026: dos 99 command IDs, só 13 respondem
    # ao `0xFE 0x01 <id>`. Os outros 86 dão timeout — inclusive quase todas as
    # leituras que o APK sugere (0x2A vento, 0x31 toque, 0x35/0x36 LED, 0x39
    # foco, 0x40 volume adaptativo, 0x48 sensibilidade, 0x5B espacial, 0x62
    # wear). Ou seja: escrever nesses IDs pode até funcionar, mas LER de volta
    # não. Nada de "None" silencioso — quem chama precisa saber disso.
    # ─────────────────────────────────────────────────────────────────────────

    READABLE = {
        0x10: "sleep_mode",
        0x14: "power_manager",
        0x17: "anc",
        0x19: "voice_name",
        0x1D: "tone_volume",
        0x1F: "standby",
        0x22: "eq",
        0x23: "ldac",
        0x24: "one_to_two",
        0x2D: "space_sound",
        0x2E: "music_mode",
        0x2F: "battery",
        0x30: "version",
    }

    async def read_custom(self, cmd: int) -> bytes | None:
        """Leitura crua `0xFE 0x01 <cmd>`. Retorna os params ou None (timeout)."""
        resp = await self.send(
            Packet(op_code=OpCode.CUSTOM, params=bytes([0xFE, 0x01, cmd]))
        )
        return resp.params if resp is not None else None

    async def get_ldac(self) -> bool | None:
        p = await self.read_custom(0x23)
        return p[2] == 0x01 if p and len(p) >= 3 else None

    async def get_sleep_mode(self) -> int | None:
        p = await self.read_custom(0x10)
        return p[2] if p and len(p) >= 3 else None

    async def get_tone_volume(self) -> int | None:
        p = await self.read_custom(0x1D)
        return p[2] if p and len(p) >= 3 else None

    async def get_battery_percent(self) -> int | None:
        """Bateria por AdvType.BATTERY_QUANTITY (3 bytes: pct, left, right)."""
        pkt = await self.get_adv_info(1 << AdvType.BATTERY_QUANTITY)
        if not pkt or not pkt.params:
            return None
        from rcsp import parse_tlv
        for t, v in parse_tlv(pkt.params):
            if t == AdvType.BATTERY_QUANTITY and v:
                return v[0]
        return None

    async def get_key_settings(self) -> list[tuple[int, int, int]] | None:
        """Mapeamento dos botoes fisicos (ADV_TYPE_KEY_SETTINGS = 2).

        Cada entrada e [keyNum, action, function] - formato do
        `ADVInfoResponse.KeySettings.toData()` do APK. O H3S devolve 15
        entradas: keyNum 3, 5 e 7, cada um com action 1..5.
        function 0x7F/0x00 = "sem funcao"; 0xFF = trocar modo ANC.
        """
        pkt = await self.get_adv_info(1 << AdvType.KEY_SETTINGS)
        if not pkt or not pkt.params:
            return None
        from rcsp import parse_tlv
        for t, v in parse_tlv(pkt.params):
            if t != AdvType.KEY_SETTINGS:
                continue
            out = []
            for i in range(0, len(v) - 2, 3):
                out.append((v[i], v[i + 1], v[i + 2]))
            return out
        return None

    async def get_state(self) -> dict:
        """Tudo que este firmware sabe responder, numa conexao so."""
        state: dict = {}

        pct = await self.get_battery_percent()
        state["battery_pct"] = pct

        anc = await self.get_mode()
        state["anc_index"] = anc
        state["anc_name"] = ANCMode.NAMES[anc] if anc is not None and anc < len(ANCMode.NAMES) else None

        state["game_mode"] = await self.get_work_mode()
        state["eq"] = await self.get_eq()
        state["ldac"] = await self.get_ldac()

        p = await self.read_custom(0x2D)
        state["space_sound"] = (p[2] == 0x01) if p and len(p) >= 3 else None

        state["sleep_mode"] = await self.get_sleep_mode()
        state["tone_volume"] = await self.get_tone_volume()

        p = await self.read_custom(0x30)
        state["version_raw"] = p.hex(" ") if p else None

        state["key_settings"] = await self.get_key_settings()
        return state


# UUID do serviço RCSP/JieLi do QCY H3S (usado para filtrar o scan)
QCY_SERVICE_UUID = "0000a002-0000-1000-8000-00805f9b34fb"
# Endereço BLE GATT validado no hardware H3S deste projeto. O Windows pode
# não anunciar o GATT quando o headset já está conhecido/conectado; o MAC
# clássico mostrado em Configurações Bluetooth não é intercambiável com este.
QCY_H3S_BLE_ADDRESS = "84:AC:60:F8:A6:BF"
_BLE_DEVICE_CACHE: dict[str, BLEDevice] = {}


def _ble_device_for_address(address: str):
    """Prefer the scanned BLEDevice; on Windows resolve a cached device w/o scan.

    Bleak's WinRT backend accepts BLEDevice and uses its native bluetooth
    address directly. This avoids its implicit discovery, which fails when a
    paired headset is connected/cached but not advertising.
    """
    cached = _BLE_DEVICE_CACHE.get(address.casefold())
    if cached is not None:
        return cached
    if sys.platform != "win32":
        return address
    try:
        from bleak.backends.winrt.scanner import RawAdvData

        mac_int = int(address.replace(":", "").replace("-", ""), 16)
        # WinRT's scanner detail type is used only for its bluetooth_address;
        # no fabricated advertisement is consumed by the GATT client.
        details = RawAdvData(None, SimpleNamespace(bluetooth_address=mac_int))
        return BLEDevice(address, "QCY H3S (Windows cache)", details)
    except (ImportError, ValueError):
        return address

# Serviços secundários que o QCY H3S anuncia quando já pareado/conectado
QCY_SECONDARY_SERVICES = ("0000fee8-0000-1000-8000-00805f9b34fb",)

# Marcadores de nome que identificam o fone (case-insensitive)
QCY_NAME_MARKERS = ("qcy", "kcey", "h3s", "h3 ")


def _is_qcy_device(name: str, service_uuids: list) -> bool:
    """True se o dispositivo parece ser o QCY H3S (por nome ou serviço BLE)."""
    if name:
        low = name.lower()
        if any(m in low for m in QCY_NAME_MARKERS):
            return True
    for u in service_uuids or []:
        ul = str(u).lower()
        if ul == QCY_SERVICE_UUID or ul in QCY_SECONDARY_SERVICES:
            return True
    return False


def _resolve_name(name: str, service_uuids: list) -> str:
    """Garante um nome amigável para dispositivos QCY sem nome no adv."""
    if name:
        return name
    uls = [str(u).lower() for u in (service_uuids or [])]
    if QCY_SERVICE_UUID in uls or any(s in uls for s in QCY_SECONDARY_SERVICES):
        return "QCY H3S (BLE)"
    return ""


async def scan_including_paired(timeout: float = 6.0) -> list:
    """Scan BLE + tenta incluir fones QCY já pareados que não advertising.

    Windows pode não anunciar dispositivos já pareados/conectados. O MAC
    clássico listado pelo PnP não é o endereço BLE GATT, então usamos o
    endereço BLE validado do H3S como fallback de conexão (não como prova de
    que o dispositivo está ligado; a tentativa BLE confirma isso).
    """
    items = await scan(timeout=timeout, only_qcy=True)
    found_addrs = {a.casefold() for a, _, _ in items}
    if QCY_H3S_BLE_ADDRESS.casefold() not in found_addrs:
        items.append((QCY_H3S_BLE_ADDRESS, "QCY H3S (endereço BLE conhecido)", None))
    items.sort(key=lambda x: x[2] if x[2] is not None else -999, reverse=True)
    return items


async def scan(timeout: float = 6.0, only_qcy: bool = True) -> list:
    """Escaneia BLE.

    Por padrão retorna apenas dispositivos QCY H3S (filtrando o ruído de
    outros aparelhos). Cada item é (address, name, rssi). Dispositivos que
    anunciam o serviço RCSP mas sem nome recebem o nome 'QCY H3S (BLE)'.
    """
    result = await BleakScanner.discover(timeout=timeout, return_adv=True)
    items = []
    for dev, adv in result.values():
        _BLE_DEVICE_CACHE[dev.address.casefold()] = dev
        name = dev.name or adv.local_name or ""
        svcs = list(adv.service_uuids or [])
        if only_qcy and not _is_qcy_device(name, svcs):
            continue
        items.append((dev.address, _resolve_name(name, svcs), adv.rssi))
    items.sort(key=lambda x: x[2] if x[2] is not None else -999, reverse=True)
    return items

