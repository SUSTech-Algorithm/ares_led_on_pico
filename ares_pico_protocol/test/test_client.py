from collections import deque
import struct

import pytest

from ares_pico_protocol.client import AresPicoClient
from ares_pico_protocol.protocol import (
    MessageType,
    Packet,
    ResultCode,
    StreamDecoder,
)


class FakePicoSerial:
    def __init__(self):
        self.is_open = True
        self._responses = deque()
        self._decoder = StreamDecoder()
        self.configured_count = 0
        self.frames = []

    @property
    def in_waiting(self):
        return len(self._responses[0]) if self._responses else 0

    def write(self, data):
        for request in self._decoder.feed(data):
            if request.message_type == MessageType.CONFIG_LED_COUNT:
                self.configured_count = struct.unpack('<H', request.payload)[0]
                response = Packet(
                    MessageType.ACK,
                    request.sequence,
                    bytes((request.message_type, ResultCode.OK)),
                )
            elif request.message_type == MessageType.SET_FRAME:
                self.frames.append(request.payload)
                response = Packet(
                    MessageType.ACK,
                    request.sequence,
                    bytes((request.message_type, ResultCode.OK)),
                )
            else:
                response = Packet(
                    MessageType.ACK,
                    request.sequence,
                    bytes((request.message_type, ResultCode.OK)),
                )
            encoded = response.encode()
            self._responses.extend((encoded[:2], encoded[2:]))
        return len(data)

    def flush(self):
        pass

    def read(self, _size):
        return self._responses.popleft() if self._responses else b''

    def close(self):
        self.is_open = False


def test_configure_and_send_tracks_dynamic_count():
    fake = FakePicoSerial()
    client = AresPicoClient(serial_instance=fake, timeout=0.05)

    ack = client.configure_and_send([255, 0, 0, 0, 255, 0])
    assert ack.result is ResultCode.OK
    assert client.led_count == 2
    assert fake.configured_count == 2
    assert fake.frames == [b'\xff\x00\x00\x00\xff\x00']

    client.configure_and_send([0, 0, 255])
    assert client.led_count == 1
    assert fake.configured_count == 1


def test_send_requires_configuration():
    client = AresPicoClient(serial_instance=FakePicoSerial())
    with pytest.raises(RuntimeError, match='configure_led_count'):
        client.send_frame([0, 0, 0])
