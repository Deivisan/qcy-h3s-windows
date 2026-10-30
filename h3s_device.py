"""QCY H3 BLE device controller."""
import asyncio
from typing import Callable

from bleak import BleakClient, BleakScanner

from rcsp import AdvType, HEADER, OpCode, Packet, TYPE_COMMAND, hex_str

# ANC/mode command bytes (Custom opCode 255)
class ANCMode:
    TRANSPARENCY    = bytes([0x17, 0x03, 0x02, 0x00, 0x00])  # ANC desligado
    NORMAL          = bytes([0x17, 0x03, 0x03, 0x01, 0x04])  # Transparência (ambiente)

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

    ALL = [
        TRANSPARENCY, NORMAL,
        NOISY_LOW, NOISY_MED, NOISY_HIGH, NOISY_MAX, NOISY_ULTRA,
        ADAPTIVE,
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
            if group == 0x01:
                return 2 + level   # ANC Low/Med/High/Max/Ultra
            if group == 0x05:
                return 7           # Adaptativo
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


class H3SDevice:
    def __init__(self, address: str):
        self.address = address
        self._client: BleakClient | None = None
        self._sn = 0
        self._pending: dict[int, asyncio.Future[Packet]] = {}
        self._rx_buffer = bytearray()
        self.on_notification: Callable[[Packet], None] | None = None
        self.on_raw: Callable[[bytes], None] | None = None

    async def connect(self) -> None:
        self._client = BleakClient(self.address, timeout=15.0)
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
        band_bytes = bytearray()
        for i, freq in enumerate(EQ_BANDS_FREQS):
            ref_gain, q = EQ_BAND_DEFAULTS[freq]
            db_off = db_offsets[i] if i < len(db_offsets) else 0
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
        """Enable/disable wear detection (cmd 0x2C)."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0x2C, 0x01, 0x01 if enabled else 0x00])))

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


async def scan(timeout: float = 6.0) -> list:
    result = await BleakScanner.discover(timeout=timeout, return_adv=True)
    items = []
    for dev, adv in result.values():
        name = dev.name or adv.local_name or ""
        items.append((dev.address, name, adv.rssi))
    items.sort(key=lambda x: x[2] or -999, reverse=True)
    return items
