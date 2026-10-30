"""MCP Server for QCY H3S headphone control via BLE (Jieli RCSP)."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from bleak import BleakScanner
import h3s_device

BLE_ADDR = "84:AC:60:F8:A6:BF"
_device = None
_loop = None

server = Server("qcy-h3s")


async def get_device():
    global _device
    if _device is None or not _device.is_connected:
        devices = await BleakScanner.discover(timeout=10.0)
        target = None
        for d in devices:
            if d.address.upper().replace(":", "") == "84AC60F8A6BF":
                target = d.address
                break
        if not target:
            raise RuntimeError("H3S-APP not found. Is the headphone on and nearby?")
        _device = h3s_device.H3SDevice(target)
        await _device.connect()
        await _device.notify_communication_way(way=0, reconnect=0)
        await asyncio.sleep(0.3)
    return _device


@server.list_tools()
async def list_tools():
    return [
        Tool(name="connect", description="Connect to QCY H3S via BLE", inputSchema={"type": "object", "properties": {}}),
        Tool(name="disconnect", description="Disconnect from QCY H3S", inputSchema={"type": "object", "properties": {}}),
        Tool(name="get_battery", description="Get battery level (0-100)", inputSchema={"type": "object", "properties": {}}),
        Tool(name="get_mode", description="Get current ANC mode index", inputSchema={"type": "object", "properties": {}}),
        Tool(name="set_anc_mode", description="Set ANC mode. mode: 0=off,1=transparency,2-6=ANC levels,7=adaptive", inputSchema={"type": "object", "properties": {"mode_index": {"type": "integer"}}, "required": ["mode_index"]}),
        Tool(name="set_game_mode", description="Enable/disable game mode (low latency)", inputSchema={"type": "object", "properties": {"enabled": {"type": "boolean"}}, "required": ["enabled"]}),
        Tool(name="get_game_mode", description="Get game mode state", inputSchema={"type": "object", "properties": {}}),
        Tool(name="get_eq", description="Get current EQ (10 bands)", inputSchema={"type": "object", "properties": {}}),
        Tool(name="set_volume", description="Set volume L/R (0-100)", inputSchema={"type": "object", "properties": {"left": {"type": "integer"}, "right": {"type": "integer"}}, "required": ["left", "right"]}),
        Tool(name="music_control", description="Music control: 1=play, 2=pause, 3=prev, 4=next", inputSchema={"type": "object", "properties": {"action": {"type": "integer"}}, "required": ["action"]}),
        Tool(name="set_ldac", description="Enable/disable LDAC codec", inputSchema={"type": "object", "properties": {"enabled": {"type": "boolean"}}, "required": ["enabled"]}),
        Tool(name="find_earphones", description="Play sound to find earphones", inputSchema={"type": "object", "properties": {}}),
        Tool(name="set_spatial_audio", description="Enable/disable spatial audio", inputSchema={"type": "object", "properties": {"enabled": {"type": "boolean"}}, "required": ["enabled"]}),
        Tool(name="set_wind_noise", description="Enable/disable wind noise reduction", inputSchema={"type": "object", "properties": {"enabled": {"type": "boolean"}}, "required": ["enabled"]}),
        Tool(name="set_wear_detection", description="Enable/disable wear detection", inputSchema={"type": "object", "properties": {"enabled": {"type": "boolean"}}, "required": ["enabled"]}),
        Tool(name="set_touch_tone", description="Enable/disable touch tone", inputSchema={"type": "object", "properties": {"enabled": {"type": "boolean"}}, "required": ["enabled"]}),
        Tool(name="set_ai_anc", description="Enable/disable AI ANC", inputSchema={"type": "object", "properties": {"enabled": {"type": "boolean"}}, "required": ["enabled"]}),
        Tool(name="set_sleep_mode", description="Enable/disable sleep mode", inputSchema={"type": "object", "properties": {"enabled": {"type": "boolean"}}, "required": ["enabled"]}),
        Tool(name="set_focus_mode", description="Enable/disable focus mode", inputSchema={"type": "object", "properties": {"enabled": {"type": "boolean"}}, "required": ["enabled"]}),
        Tool(name="set_privacy_mode", description="Enable/disable privacy mode", inputSchema={"type": "object", "properties": {"enabled": {"type": "boolean"}}, "required": ["enabled"]}),
        Tool(name="set_spatial_sound", description="Enable/disable spatial sound", inputSchema={"type": "object", "properties": {"enabled": {"type": "boolean"}}, "required": ["enabled"]}),
        Tool(name="set_adapt_volume", description="Enable/disable adaptive volume", inputSchema={"type": "object", "properties": {"enabled": {"type": "boolean"}}, "required": ["enabled"]}),
        Tool(name="set_env_adaptation", description="Enable/disable environment adaptation", inputSchema={"type": "object", "properties": {"enabled": {"type": "boolean"}}, "required": ["enabled"]}),
        Tool(name="set_led_mode", description="Enable/disable LED", inputSchema={"type": "object", "properties": {"enabled": {"type": "boolean"}}, "required": ["enabled"]}),
        Tool(name="set_led_switch", description="Enable/disable LED switch", inputSchema={"type": "object", "properties": {"enabled": {"type": "boolean"}}, "required": ["enabled"]}),
        Tool(name="set_touch_tone_volume", description="Set tone/notification volume (0-100)", inputSchema={"type": "object", "properties": {"volume": {"type": "integer"}}, "required": ["volume"]}),
        Tool(name="set_balance", description="Set L/R balance (0-255)", inputSchema={"type": "object", "properties": {"balance": {"type": "integer"}}, "required": ["balance"]}),
        Tool(name="set_button_func", description="Remap touch button", inputSchema={"type": "object", "properties": {"key_id": {"type": "integer"}, "func_id": {"type": "integer"}}, "required": ["key_id", "func_id"]}),
        Tool(name="set_in_ear_sensitivity", description="Set in-ear sensitivity", inputSchema={"type": "object", "properties": {"sensitivity": {"type": "integer"}}, "required": ["sensitivity"]}),
        Tool(name="get_device_info", description="Get device info", inputSchema={"type": "object", "properties": {}}),
        Tool(name="get_wear_status", description="Get wear detection status", inputSchema={"type": "object", "properties": {}}),
        Tool(name="get_hearing_safety", description="Get hearing safety data", inputSchema={"type": "object", "properties": {}}),
        Tool(name="get_wind_noise", description="Get wind noise state", inputSchema={"type": "object", "properties": {}}),
        Tool(name="get_spatial_audio", description="Get spatial audio state", inputSchema={"type": "object", "properties": {}}),
        Tool(name="get_spatial_sound", description="Get spatial sound state", inputSchema={"type": "object", "properties": {}}),
        Tool(name="get_ai_anc", description="Get AI ANC state", inputSchema={"type": "object", "properties": {}}),
        Tool(name="get_focus_mode", description="Get focus mode state", inputSchema={"type": "object", "properties": {}}),
        Tool(name="get_privacy_mode", description="Get privacy mode state", inputSchema={"type": "object", "properties": {}}),
        Tool(name="get_env_adaptation", description="Get environment adaptation state", inputSchema={"type": "object", "properties": {}}),
        Tool(name="get_adapt_volume", description="Get adaptive volume state", inputSchema={"type": "object", "properties": {}}),
        Tool(name="reset_default", description="Reset to default settings", inputSchema={"type": "object", "properties": {}}),
        Tool(name="clear_pair", description="Clear pairing records", inputSchema={"type": "object", "properties": {}}),
        Tool(name="factory_reset", description="Factory reset (CAUTION)", inputSchema={"type": "object", "properties": {}}),
        Tool(name="set_sleep_mode", description="Enable/disable sleep mode", inputSchema={"type": "object", "properties": {"enabled": {"type": "boolean"}}, "required": ["enabled"]}),
        Tool(name="set_touch_tone", description="Enable/disable touch tone", inputSchema={"type": "object", "properties": {"enabled": {"type": "boolean"}}, "required": ["enabled"]}),
        Tool(name="sync_time", description="Sync device clock", inputSchema={"type": "object", "properties": {}}),
        Tool(name="play_tone", description="Play test tone", inputSchema={"type": "object", "properties": {"tone_id": {"type": "integer"}}, "required": ["tone_id"]}),
        Tool(name="take_photo", description="Remote camera shutter", inputSchema={"type": "object", "properties": {}}),
        Tool(name="set_light", description="Enable/disable flashlight", inputSchema={"type": "object", "properties": {"enabled": {"type": "boolean"}}, "required": ["enabled"]}),
        Tool(name="set_ldac", description="Enable/disable LDAC (may restart headphone)", inputSchema={"type": "object", "properties": {"enabled": {"type": "boolean"}}, "required": ["enabled"]}),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    global _device
    try:
        dev = await get_device()
        result = None

        if name == "connect":
            result = "Connected"
        elif name == "disconnect":
            if _device:
                await _device.disconnect()
                _device = None
            result = "Disconnected"
        elif name == "get_battery":
            pkt = await dev.get_battery()
            result = str(pkt)
        elif name == "get_mode":
            m = await dev.get_mode()
            result = f"Mode index: {m}"
        elif name == "set_anc_mode":
            mode_bytes = h3s_device.ANCMode.ALL[arguments["mode_index"]] if arguments["mode_index"] < len(h3s_device.ANCMode.ALL) else None
            if mode_bytes:
                await dev.set_mode(mode_bytes)
                result = f"Set mode {arguments['mode_index']}"
            else:
                result = "Invalid mode index"
        elif name == "set_game_mode":
            await dev.set_game_mode(arguments["enabled"])
            result = f"Game mode {'on' if arguments['enabled'] else 'off'}"
        elif name == "get_game_mode":
            gm = await dev.get_work_mode()
            result = f"Game mode: {gm}"
        elif name == "get_eq":
            eq = await dev.get_eq()
            result = f"EQ: {eq}"
        elif name == "set_volume":
            await dev.set_volume(arguments["left"], arguments["right"])
            result = f"Volume set L={arguments['left']} R={arguments['right']}"
        elif name == "music_control":
            await dev.music_control(arguments["action"])
            result = f"Music action {arguments['action']} sent"
        elif name == "set_ldac":
            await dev.set_ldac(arguments["enabled"])
            result = f"LDAC {'on' if arguments['enabled'] else 'off'}"
        elif name == "find_earphones":
            await dev.find_earphones()
            result = "Find earphones triggered"
        elif name == "set_spatial_audio":
            await dev.set_spatial_audio(arguments["enabled"])
            result = f"Spatial audio {'on' if arguments['enabled'] else 'off'}"
        elif name == "set_wind_noise":
            await dev.set_wind_noise(arguments["enabled"])
            result = f"Wind noise {'on' if arguments['enabled'] else 'off'}"
        elif name == "set_wear_detection":
            await dev.set_wear_config(arguments["enabled"])
            result = f"Wear detection {'on' if arguments['enabled'] else 'off'}"
        elif name == "set_touch_tone":
            await dev.set_touch_tone(arguments["enabled"])
            result = f"Touch tone {'on' if arguments['enabled'] else 'off'}"
        elif name == "set_ai_anc":
            await dev.set_ai_anc(arguments["enabled"])
            result = f"AI ANC {'on' if arguments['enabled'] else 'off'}"
        elif name == "set_sleep_mode":
            await dev.set_sleep_mode(arguments["enabled"])
            result = f"Sleep mode {'on' if arguments['enabled'] else 'off'}"
        elif name == "set_focus_mode":
            await dev.set_focus_mode(arguments["enabled"])
            result = f"Focus mode {'on' if arguments['enabled'] else 'off'}"
        elif name == "set_privacy_mode":
            await dev.set_privacy_mode(arguments["enabled"])
            result = f"Privacy mode {'on' if arguments['enabled'] else 'off'}"
        elif name == "set_spatial_sound":
            await dev.set_space_sound(arguments["enabled"])
            result = f"Spatial sound {'on' if arguments['enabled'] else 'off'}"
        elif name == "set_adapt_volume":
            await dev.set_adapt_volume(arguments["enabled"])
            result = f"Adapt volume {'on' if arguments['enabled'] else 'off'}"
        elif name == "set_env_adaptation":
            await dev.set_env_adaptation(arguments["enabled"])
            result = f"Env adaptation {'on' if arguments['enabled'] else 'off'}"
        elif name == "set_led_mode":
            await dev.set_led_mode(arguments["enabled"])
            result = f"LED {'on' if arguments['enabled'] else 'off'}"
        elif name == "set_led_switch":
            await dev.set_led_switch(arguments["enabled"])
            result = f"LED switch {'on' if arguments['enabled'] else 'off'}"
        elif name == "set_touch_tone_volume":
            await dev.set_tone_volume(arguments["volume"])
            result = f"Tone volume set to {arguments['volume']}"
        elif name == "set_balance":
            await dev.set_balance(arguments["balance"])
            result = f"Balance set to {arguments['balance']}"
        elif name == "set_button_func":
            await dev.set_button_func(arguments["key_id"], arguments["func_id"])
            result = f"Button {arguments['key_id']} remapped to {arguments['func_id']}"
        elif name == "set_in_ear_sensitivity":
            await dev.set_inear_sensitivity(arguments["sensitivity"])
            result = f"In-ear sensitivity set to {arguments['sensitivity']}"
        elif name == "get_device_info":
            pkt = await dev.get_device_info()
            result = str(pkt)
        elif name == "get_wear_status":
            pkt = await dev.get_wear_status()
            result = str(pkt)
        elif name == "get_hearing_safety":
            pkt = await dev.get_hearing_safety()
            result = str(pkt)
        elif name == "get_wind_noise":
            pkt = await dev.get_wind_noise()
            result = str(pkt)
        elif name == "get_spatial_audio":
            pkt = await dev.get_spatial_audio()
            result = str(pkt)
        elif name == "get_spatial_sound":
            pkt = await dev.get_space_sound()
            result = str(pkt)
        elif name == "get_ai_anc":
            pkt = await dev.get_ai_anc()
            result = str(pkt)
        elif name == "get_focus_mode":
            pkt = await dev.get_focus_mode()
            result = str(pkt)
        elif name == "get_privacy_mode":
            pkt = await dev.get_privacy_mode()
            result = str(pkt)
        elif name == "get_env_adaptation":
            pkt = await dev.get_env_adaptation()
            result = str(pkt)
        elif name == "get_adapt_volume":
            pkt = await dev.get_adapt_volume()
            result = str(pkt)
        elif name == "reset_default":
            await dev.reset_default()
            result = "Reset to default done"
        elif name == "clear_pair":
            await dev.clear_pair()
            result = "Pairing cleared"
        elif name == "factory_reset":
            await dev.factory_reset()
            result = "Factory reset done"
        elif name == "sync_time":
            import datetime
            now = datetime.datetime.now()
            await dev.sync_time(now.year, now.month, now.day, now.hour, now.minute, now.second)
            result = "Time synced"
        elif name == "play_tone":
            await dev.play_tone(arguments["tone_id"])
            result = f"Tone {arguments['tone_id']} played"
        elif name == "take_photo":
            await dev.take_photo()
            result = "Photo shutter triggered"
        elif name == "set_light":
            await dev.set_light(arguments["enabled"])
            result = f"Light {'on' if arguments['enabled'] else 'off'}"
        else:
            result = f"Unknown tool: {name}"

        return [TextContent(type="text", text=result)]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {e}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
