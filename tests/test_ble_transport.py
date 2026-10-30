import asyncio
import unittest
from types import SimpleNamespace

from h3s_device import H3SDevice
from rcsp import OpCode, Packet


class FakeCharacteristic:
    max_write_without_response_size = 20


class FakeServices:
    def get_characteristic(self, _uuid):
        return FakeCharacteristic()


class FakeClient:
    is_connected = True
    services = FakeServices()

    def __init__(self):
        self.fragments = []

    async def write_gatt_char(self, _uuid, data, response=False):
        assert response is False
        self.fragments.append(bytes(data))


class BleTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_rcsp_frame_is_fragmented_without_byte_loss_or_reordering(self):
        device = H3SDevice("00:00:00:00:00:00")
        client = FakeClient()
        device._client = client
        params = bytes(range(73))
        packet = Packet(op_code=OpCode.CUSTOM, has_response=0, params=params)

        result = await device.send(packet)

        self.assertIsNone(result)
        self.assertGreater(len(client.fragments), 1)
        self.assertTrue(all(len(part) <= 20 for part in client.fragments))
        self.assertEqual(b"".join(client.fragments), packet.encode())


if __name__ == "__main__":
    unittest.main()
