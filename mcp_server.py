"""MCP Server for QCY H3S headphone control via BLE (Jieli RCSP).

Auditoria de risco completa em `docs/COMANDOS-DESTRUTIVOS.md`.

Regras que este servidor aplica (não são sugestões):

* **Um comando por vez**, globalmente (`_lock`). Antes disso duas chamadas
  simultâneas abriam dois `BleakClient` e corrompiam o contador `sn` do RCSP.
* **Comandos destrutivos exigem confirmação explícita** no campo `confirm`,
  com o nome da tool em maiúsculas. Sem isso a chamada é recusada.
* **Quarentena depois de destrutivo** (`COOLDOWN`): o H3S reinicia em
  `set_ldac`, e mandar o próximo comando em cima volta erro de conexão.
* A lista de tools é um dict, então não existe mais tool registrada em
  duplicidade (`set_ldac`, `set_sleep_mode` e `set_touch_tone` apareciam duas
  vezes na versão anterior).
"""
import asyncio
import datetime
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

import h3s_device
import h3s_device as h

BLE_ADDR = os.environ.get("QCY_H3_BLE_ADDRESS", "").strip()
SCAN_TIMEOUT = 6.0

READ = "read"
WRITE = "write"
DESTRUCTIVE = "destructive"

#: Quarentena em segundos depois de um comando destrutivo.
#: O fone reinicia de verdade nesses casos (medido: `set_ldac(False)` derruba
#: o A2DP e o fone volta ~8-12 s depois).
COOLDOWN = {
    "set_ldac": 12.0,
    "factory_reset": 15.0,
    "clear_pair": 12.0,
    "reset_default": 8.0,
}

_device = None
_lock = asyncio.Lock()
_cooldown_until = 0.0
_last_destructive: str | None = None

server = Server("qcy-h3s")


def _text(s: str) -> list[TextContent]:
    return [TextContent(type="text", text=s)]


async def _connect():
    """Conecta (ou reaproveita) o cliente BLE."""
    global _device
    if _device is not None and _device.is_connected:
        return _device

    # Endereço por instalação, nunca embutir o MAC pessoal de uma unidade no
    # código publicado. Sem configuração, aceitar somente um H3/H3S detectado.
    target = BLE_ADDR
    if target:
        dev = h3s_device.H3SDevice(target)
        try:
            await dev.connect()
        except Exception:
            try:
                await dev.disconnect()
            except Exception:
                pass
            target = ""

    if not target:
        found = await h3s_device.scan_including_paired(
            timeout=SCAN_TIMEOUT,
            known_addresses=[BLE_ADDR] if BLE_ADDR else [],
        )
        matches = [
            address for address, name, _rssi in found
            if name and any(marker in name.casefold() for marker in ("h3", "h3s"))
        ]
        if len(matches) != 1:
            raise RuntimeError(
                "Não foi possível identificar um único QCY H3/H3S. Ligue o fone, "
                "feche outros controladores BLE e defina QCY_H3_BLE_ADDRESS se "
                "houver mais de um dispositivo compatível."
            )
        target = matches[0]
        dev = h3s_device.H3SDevice(target)
        await dev.connect()

    await dev.notify_communication_way(way=0, reconnect=0)
    await asyncio.sleep(0.3)
    _device = dev
    return dev


# ── handlers ────────────────────────────────────────────────────────────────

async def h_get_battery(dev, a):
    pct = await dev.get_battery_percent()
    return f"Battery: {pct}%" if pct is not None else str(await dev.get_battery())

async def h_get_mode(dev, a):
    idx = await dev.get_mode()
    name = h.ANCMode.NAMES[idx] if idx is not None and idx < len(h.ANCMode.NAMES) else "?"
    return f"Mode index: {idx} ({name})"

async def h_get_game_mode(dev, a):      return f"Game mode: {await dev.get_work_mode()}"
async def h_get_eq(dev, a):             return f"EQ: {await dev.get_eq()}"
async def h_get_spatial_sound(dev, a):
    p = await dev.read_custom(0x2D)
    return f"Spatial sound: {p[2] == 1} (raw {p.hex(' ')})" if p and len(p) >= 3 else _DEAD.format(cmd="0x2D")
async def h_get_state(dev, a):          return json.dumps(await dev.get_state(), indent=2)


async def _remap_button(dev, a):
    """Remapeia um botao e devolve o mapa antes/depois, como evidencia."""
    before = await dev.get_key_settings()
    if not before:
        return "fone nao devolveu o mapa de botoes; nada foi gravado"
    await dev.set_button_func(a["key_id"], a["func_id"], action=a["action"])
    await asyncio.sleep(2.5)
    after = await dev.get_key_settings()
    return (f"antes: {before}\n"
            f"pedido: key {a['key_id']} action {a['action']} -> func {a['func_id']:#04x}\n"
            f"depois: {after}")


def _dead(cmd: str, what: str):
    """Leitura que este firmware NAO responde - verificado, nao e bug do app."""
    async def handler(dev, a):
        return _DEAD.format(cmd=cmd, what=what)
    return handler


_DEAD = (
    "nao suportado: o H3S nao responde ao GET {cmd} ({what}). "
    "Varredura 0x01..0x63 em 29/10/2026: so 13 IDs respondem leitura. "
    "O SET funciona como fire-and-forget, mas nao ha como confirmar o estado."
)

h_get_device_info    = _dead("0xF7", "device info")
h_get_wear_status    = _dead("0x62", "wear status")
h_get_hearing_safety = _dead("0x58", "hearing safety")
h_get_wind_noise     = _dead("0x2A", "wind noise")
h_get_spatial_audio  = _dead("0x5B", "spatial audio")
h_get_ai_anc         = _dead("0x54", "AI ANC")
h_get_focus_mode     = _dead("0x39", "focus mode")
h_get_privacy_mode   = _dead("0x5F", "privacy mode")
h_get_env_adaptation = _dead("0x32", "env adaptation")
h_get_adapt_volume   = _dead("0x40", "adaptive volume")
h_get_button_func    = _dead("0x2B", "button map - use get_state()")


async def h_set_anc_mode(dev, a):
    idx = a["mode_index"]
    if not 0 <= idx < len(h3s_device.ANCMode.ALL):
        raise ValueError(f"mode_index fora de 0..{len(h3s_device.ANCMode.ALL) - 1}")
    await dev.set_mode(h3s_device.ANCMode.ALL[idx])
    return f"ANC -> {idx} ({h3s_device.ANCMode.NAMES[idx]})"


async def h_set_game_mode(dev, a):
    await dev.set_game_mode(a["enabled"])
    return f"Game mode {'on' if a['enabled'] else 'off'}"


async def h_set_eq(dev, a):
    await dev.set_eq(a["offsets"], a.get("preset_id", 0))
    return f"EQ set: {a['offsets']} preset={a.get('preset_id', 0)}"


async def h_set_volume(dev, a):
    await dev.set_volume(a["left"], a["right"])
    return f"Volume L={a['left']} R={a['right']}"


async def h_music_control(dev, a):
    await dev.music_control(a["action"])
    return f"Music action {a['action']} sent"


async def h_find_earphones(dev, a):
    await dev.find_earphones()
    return "Find earphones triggered (bipe alto — cuidado com o volume)"


async def h_play_tone(dev, a):
    await dev.play_tone(a["tone_id"])
    return f"Tone {a['tone_id']} played"


async def h_take_photo(dev, a):
    await dev.take_photo()
    return "Photo shutter triggered"


async def h_sync_time(dev, a):
    now = datetime.datetime.now()
    await dev.sync_time(now.year % 100, now.month, now.day,
                        now.hour, now.minute, now.second, now.isoweekday())
    return "Time synced"


async def h_set_ldac(dev, a):
    await dev.set_ldac(a["enabled"])
    return (f"LDAC {'on' if a['enabled'] else 'off'} — o fone reinicia. "
            f"Quarentena de {COOLDOWN['set_ldac']:.0f}s aplicada.")


async def h_reset_default(dev, a):
    await dev.reset_default()
    return "Reset to default enviado — fone reinicia, configurações voltam ao padrão."


async def h_clear_pair(dev, a):
    await dev.clear_pair()
    return "Registros de pareamento apagados — será preciso parear de novo."


async def h_factory_reset(dev, a):
    await dev.factory_reset()
    return "Factory reset enviado — fone volta ao estado de fábrica."


def _bool_setter(method: str, label: str):
    async def handler(dev, a):
        await getattr(dev, method)(a["enabled"])
        return f"{label} {'on' if a['enabled'] else 'off'}"
    return handler


def _int_setter(method: str, arg: str, label: str):
    async def handler(dev, a):
        await getattr(dev, method)(a[arg])
        return f"{label} set to {a[arg]}"
    return handler


# ── registro ────────────────────────────────────────────────────────────────

def _b(name, desc, risk, handler):
    return (name, dict(desc=desc, risk=risk, handler=handler,
                       schema={"type": "object", "properties": {}}))


def _b1(name, desc, risk, handler, prop, typ):
    return (name, dict(desc=desc, risk=risk, handler=handler,
                       schema={"type": "object",
                               "properties": {prop: {"type": typ}},
                               "required": [prop]}))


def _b2(name, desc, risk, handler, props):
    return (name, dict(desc=desc, risk=risk, handler=handler,
                       schema={"type": "object",
                               "properties": {p: {"type": t} for p, t in props},
                               "required": [p for p, _ in props]}))


TOOLS: dict[str, dict] = dict([
    _b("connect", "Connect to QCY H3S via BLE", WRITE,
       lambda dev, a: _done("Connected")),
    _b("disconnect", "Disconnect from QCY H3S", WRITE,
       lambda dev, a: _done("Disconnected")),

    # leitura
    _b("get_state", "TUDO que o firmware responde numa conexao: bateria, ANC, "
       "game mode, EQ, LDAC, spatial sound, sleep mode, tone volume, versao e "
       "o mapa dos botoes fisicos (keyNum/action/function)", READ, h_get_state),
    _b("get_battery", "Battery level (via ADV info)", READ, h_get_battery),
    _b("get_mode", "Current ANC mode index (0=off,1=transparency,2-6=levels,7=adaptive)", READ, h_get_mode),
    _b("get_game_mode", "Game mode state (via ADV work mode)", READ, h_get_game_mode),
    _b("get_eq", "Current EQ, 10 bands", READ, h_get_eq),
    _b("get_device_info", "NAO SUPORTADO: firmware nao responde GET 0xF7", READ, h_get_device_info),
    _b("get_wear_status", "NAO SUPORTADO: firmware nao responde GET 0x62", READ, h_get_wear_status),
    _b("get_hearing_safety", "NAO SUPORTADO: firmware nao responde GET 0x58", READ, h_get_hearing_safety),
    _b("get_wind_noise", "NAO SUPORTADO: firmware nao responde GET 0x2A", READ, h_get_wind_noise),
    _b("get_spatial_audio", "NAO SUPORTADO: firmware nao responde GET 0x5B", READ, h_get_spatial_audio),
    _b("get_spatial_sound", "Spatial sound state (GET 0x2D - funciona)", READ, h_get_spatial_sound),
    _b("get_ai_anc", "NAO SUPORTADO: firmware nao responde GET 0x54", READ, h_get_ai_anc),
    _b("get_focus_mode", "NAO SUPORTADO: firmware nao responde GET 0x39", READ, h_get_focus_mode),
    _b("get_privacy_mode", "NAO SUPORTADO: firmware nao responde GET 0x5F", READ, h_get_privacy_mode),
    _b("get_env_adaptation", "NAO SUPORTADO: firmware nao responde GET 0x32", READ, h_get_env_adaptation),
    _b("get_adapt_volume", "NAO SUPORTADO: firmware nao responde GET 0x40", READ, h_get_adapt_volume),
    _b("get_button_func", "Mapa dos botoes - leia com get_state (GET 0x2B nao responde)",
       READ, h_get_button_func),

    # escrita reversível
    _b1("set_anc_mode", "Set ANC mode index (0=off,1=transparency,2-6=levels,7=adaptive)",
        WRITE, h_set_anc_mode, "mode_index", "integer"),
    _b1("set_game_mode", "Enable/disable game mode (low latency)", WRITE,
        h_set_game_mode, "enabled", "boolean"),
    _b2("set_volume", "Set volume L/R (clamped 0-100)", WRITE, h_set_volume,
        [("left", "integer"), ("right", "integer")]),
    _b1("set_balance", "Set L/R balance (clamped 0-255)", WRITE,
        _int_setter("set_balance", "balance", "Balance"), "balance", "integer"),
    _b1("set_touch_tone_volume", "Set tone/notification volume (0-8; acima de 8 vira 8)", WRITE,
        _int_setter("set_tone_volume", "volume", "Tone volume"), "volume", "integer"),
    _b1("set_in_ear_sensitivity", "Set in-ear sensitivity (clamped 0-255)", WRITE,
        _int_setter("set_inear_sensitivity", "sensitivity", "In-ear sensitivity"),
        "sensitivity", "integer"),
    _b1("set_spatial_audio", "Enable/disable spatial audio", WRITE,
        _bool_setter("set_spatial_audio", "Spatial audio"), "enabled", "boolean"),
    _b1("set_spatial_sound", "Enable/disable spatial sound", WRITE,
        _bool_setter("set_space_sound", "Spatial sound"), "enabled", "boolean"),
    _b1("set_wind_noise", "Enable/disable wind noise reduction", WRITE,
        _bool_setter("set_wind_noise", "Wind noise"), "enabled", "boolean"),
    _b1("set_wear_detection", "Enable/disable wear detection", WRITE,
        _bool_setter("set_wear_config", "Wear detection"), "enabled", "boolean"),
    _b1("set_touch_tone", "Enable/disable touch tone", WRITE,
        _bool_setter("set_touch_tone", "Touch tone"), "enabled", "boolean"),
    _b1("set_ai_anc", "Enable/disable AI ANC", WRITE,
        _bool_setter("set_ai_anc", "AI ANC"), "enabled", "boolean"),
    _b1("set_sleep_mode", "Enable/disable sleep mode", WRITE,
        _bool_setter("set_sleep_mode", "Sleep mode"), "enabled", "boolean"),
    _b1("set_focus_mode", "Enable/disable focus mode", WRITE,
        _bool_setter("set_focus_mode", "Focus mode"), "enabled", "boolean"),
    _b1("set_privacy_mode", "Enable/disable privacy mode", WRITE,
        _bool_setter("set_privacy_mode", "Privacy mode"), "enabled", "boolean"),
    _b1("set_adapt_volume", "Enable/disable adaptive volume", WRITE,
        _bool_setter("set_adapt_volume", "Adapt volume"), "enabled", "boolean"),
    _b1("set_env_adaptation", "Enable/disable environment adaptation", WRITE,
        _bool_setter("set_env_adaptation", "Env adaptation"), "enabled", "boolean"),
    _b1("set_led_mode", "Enable/disable LED", WRITE,
        _bool_setter("set_led_mode", "LED"), "enabled", "boolean"),
    _b1("set_led_switch", "Enable/disable LED switch", WRITE,
        _bool_setter("set_led_switch", "LED switch"), "enabled", "boolean"),
    _b1("set_light", "Enable/disable flashlight", WRITE,
        _bool_setter("set_light", "Light"), "enabled", "boolean"),
    _b2("set_button_func", "Remapeia UM botao (keyNum+action) regravando o mapa "
        "inteiro via SET_ADV_INFO 0xC0. O que cada action 1..5 faz NAO foi "
        "validado - leia o mapa com get_state() antes e confira depois. "
        "func: 0x00/0x7F=sem funcao, 0xFF=trocar modo ANC, 0x01=play/pause.",
        WRITE, _remap_button,
        [("key_id", "integer"), ("func_id", "integer"), ("action", "integer")]),
    _b1("music_control", "Music control on the paired phone: 1=play,2=pause,3=prev,4=next",
        WRITE, h_music_control, "action", "integer"),
    _b("take_photo", "Remote camera shutter on the paired phone", WRITE, h_take_photo),
    _b("find_earphones", "Play a loud locate sound on the headphone", WRITE, h_find_earphones),
    _b1("play_tone", "Play a test tone on the headphone", WRITE,
        h_play_tone, "tone_id", "integer"),
    _b2("set_eq", "Set EQ. offsets: exactly 10 ints (1/100 dB, -1200..1200); "
                  "preset_id: 0=custom..6=Classic", WRITE, h_set_eq,
        [("offsets", "array"), ("preset_id", "integer")]),
    _b("sync_time", "Sync the device clock from the PC", WRITE, h_sync_time),

    # destrutivos
    _b1("set_ldac", "DESTRUCTIVE: toggle LDAC. The headphone RESTARTS and drops "
                    "A2DP. Requires confirm='SET_LDAC'",
        DESTRUCTIVE, h_set_ldac, "enabled", "boolean"),
    _b("reset_default", "DESTRUCTIVE: reset all settings to defaults. Requires "
                        "confirm='RESET_DEFAULT'", DESTRUCTIVE, h_reset_default),
    _b("clear_pair", "DESTRUCTIVE: erase pairing records. Requires "
                     "confirm='CLEAR_PAIR'", DESTRUCTIVE, h_clear_pair),
    _b("factory_reset", "DESTRUCTIVE: factory reset. Requires "
                        "confirm='FACTORY_RESET'", DESTRUCTIVE, h_factory_reset),
])


async def _done(msg):
    return msg


async def _todo(awaitable, msg):
    await awaitable
    return msg


@server.list_tools()
async def list_tools():
    out = []
    for name, spec in TOOLS.items():
        schema = dict(spec["schema"])
        if spec["risk"] == DESTRUCTIVE:
            props = dict(schema.get("properties", {}))
            props["confirm"] = {"type": "string"}
            schema = {**schema, "properties": props,
                      "required": list(schema.get("required", [])) + ["confirm"]}
        out.append(Tool(name=name, description=spec["desc"], inputSchema=schema))
    return out


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    global _device, _cooldown_until, _last_destructive

    spec = TOOLS.get(name)
    if spec is None:
        return _text(f"Unknown tool: {name}")

    arguments = arguments or {}

    if spec["risk"] == DESTRUCTIVE:
        expected = name.upper()
        if arguments.get("confirm") != expected:
            return _text(
                f"REFUSED: '{name}' é destrutivo. Reenvie com confirm='{expected}'. "
                f"Ver docs/COMANDOS-DESTRUTIVOS.md."
            )

    async with _lock:
        wait = _cooldown_until - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)

        try:
            if name == "disconnect":
                if _device:
                    await _device.disconnect()
                _device = None
                return _text("Disconnected")

            dev = await _connect()
            result = await spec["handler"](dev, arguments)

            if spec["risk"] == DESTRUCTIVE:
                _last_destructive = name
                try:
                    await dev.disconnect()
                except Exception:
                    pass
                _device = None
                _cooldown_until = time.monotonic() + COOLDOWN.get(name, 10.0)

            return _text(result)
        except Exception as e:
            return _text(f"Error: {e}")


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
