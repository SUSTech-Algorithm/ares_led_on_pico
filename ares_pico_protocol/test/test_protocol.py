import struct

import pytest

from ares_pico_protocol.protocol import (
    DeviceStatus,
    MessageType,
    Packet,
    ProtocolError,
    ResultCode,
    StreamDecoder,
    cobs_decode,
    cobs_encode,
    crc16_ccitt,
    decode_packet,
    rgb_bytes,
)


@pytest.mark.parametrize(
    'payload',
    [
        b'\x00',
        b'abc',
        b'a\x00b\x00c',
        bytes(range(256)),
        bytes([0x55]) * 3000,
    ],
)
def test_cobs_round_trip(payload):
    encoded = cobs_encode(payload)
    assert b'\x00' not in encoded
    assert cobs_decode(encoded) == payload


def test_crc_known_vector():
    assert crc16_ccitt(b'123456789') == 0x29B1


def test_packet_round_trip_with_binary_rgb_data():
    original = Packet(MessageType.SET_FRAME, 0x1234, b'\x00\xff\x00' * 10)
    decoded = decode_packet(original.encode())
    assert decoded == original


def test_packet_crc_corruption_is_rejected():
    encoded = bytearray(Packet(MessageType.PING, 7).encode())
    encoded[2] ^= 0x40
    with pytest.raises(ProtocolError, match='CRC mismatch'):
        decode_packet(bytes(encoded))


def test_stream_decoder_handles_fragmentation_and_noise_delimiters():
    first = Packet(MessageType.PING, 1).encode()
    second = Packet(MessageType.GET_STATUS, 2).encode()
    decoder = StreamDecoder()
    assert decoder.feed(b'\x00' + first[:3]) == []
    assert decoder.feed(first[3:] + b'\x00' + second) == [
        Packet(MessageType.PING, 1),
        Packet(MessageType.GET_STATUS, 2),
    ]


def test_status_payload_decode():
    payload = struct.pack('<HHHIIIIB', 144, 1000, 321, 10, 8, 2, 3, 1)
    status = DeviceStatus.from_payload(payload)
    assert status.led_count == 144
    assert status.max_led_count == 1000
    assert status.actual_fps == 32.1
    assert status.dropped_frames == 2
    assert status.busy is True


def test_rgb_validation():
    assert rgb_bytes([255, 0, 1], 1) == b'\xff\x00\x01'
    with pytest.raises(ValueError, match='divisible by 3'):
        rgb_bytes([1, 2])
    with pytest.raises(ValueError, match='expected 2'):
        rgb_bytes([1, 2, 3], 2)


def test_result_values_are_stable():
    assert int(ResultCode.OK) == 0
    assert int(ResultCode.REPLACED_PENDING_FRAME) == 1
