"""Wire protocol shared by the Linux host and ``ares_led_driver`` firmware."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
import struct
from typing import Iterable, List


PROTOCOL_VERSION = 1
MAX_LED_COUNT = 1000
MAX_PAYLOAD_SIZE = MAX_LED_COUNT * 3
HEADER = struct.Struct('<BBHH')
CRC = struct.Struct('<H')
STATUS_PAYLOAD = struct.Struct('<HHHIIIIB')


class MessageType(IntEnum):
    PING = 0x01
    CONFIG_LED_COUNT = 0x10
    SET_FRAME = 0x11
    GET_STATUS = 0x20
    ACK = 0x80
    STATUS = 0x81
    NACK = 0x82


class ResultCode(IntEnum):
    OK = 0
    REPLACED_PENDING_FRAME = 1
    BAD_VERSION = 2
    BAD_LENGTH = 3
    BAD_LED_COUNT = 4
    NOT_CONFIGURED = 5
    UNKNOWN_COMMAND = 6


class ProtocolError(ValueError):
    """Raised when a wire frame is malformed."""


class ProtocolNack(RuntimeError):
    """Raised when the Pico explicitly rejects a request."""

    def __init__(self, command: int, result: int):
        self.command = command
        self.result = result
        try:
            result_name = ResultCode(result).name
        except ValueError:
            result_name = f'UNKNOWN_{result}'
        super().__init__(f'Pico rejected command 0x{command:02x}: {result_name}')


def crc16_ccitt(data: bytes, initial: int = 0xFFFF) -> int:
    """Return CRC-16/CCITT-FALSE for *data*."""
    crc = initial
    for value in data:
        crc ^= value << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def cobs_encode(data: bytes) -> bytes:
    """Encode one payload with Consistent Overhead Byte Stuffing."""
    output = bytearray([0])
    code_index = 0
    code = 1

    for value in data:
        if value == 0:
            output[code_index] = code
            code_index = len(output)
            output.append(0)
            code = 1
        else:
            output.append(value)
            code += 1
            if code == 0xFF:
                output[code_index] = code
                code_index = len(output)
                output.append(0)
                code = 1

    output[code_index] = code
    return bytes(output)


def cobs_decode(data: bytes) -> bytes:
    """Decode one COBS frame without its trailing zero delimiter."""
    if not data:
        raise ProtocolError('empty COBS frame')

    output = bytearray()
    index = 0
    length = len(data)
    while index < length:
        code = data[index]
        if code == 0:
            raise ProtocolError('zero byte inside COBS frame')
        index += 1
        block_end = index + code - 1
        if block_end > length:
            raise ProtocolError('truncated COBS block')
        output.extend(data[index:block_end])
        index = block_end
        if code != 0xFF and index < length:
            output.append(0)
    return bytes(output)


@dataclass(frozen=True)
class Packet:
    message_type: int
    sequence: int
    payload: bytes = b''
    version: int = PROTOCOL_VERSION

    def encode(self) -> bytes:
        if not 0 <= self.sequence <= 0xFFFF:
            raise ValueError('sequence must fit uint16')
        if len(self.payload) > MAX_PAYLOAD_SIZE:
            raise ValueError('payload exceeds protocol maximum')
        body = HEADER.pack(
            self.version,
            int(self.message_type),
            self.sequence,
            len(self.payload),
        ) + self.payload
        raw = body + CRC.pack(crc16_ccitt(body))
        return cobs_encode(raw) + b'\x00'


def decode_packet(encoded: bytes) -> Packet:
    """Decode one COBS packet. A trailing delimiter is accepted."""
    if encoded.endswith(b'\x00'):
        encoded = encoded[:-1]
    raw = cobs_decode(encoded)
    if len(raw) < HEADER.size + CRC.size:
        raise ProtocolError('packet shorter than header and CRC')

    version, message_type, sequence, payload_length = HEADER.unpack_from(raw)
    expected_length = HEADER.size + payload_length + CRC.size
    if len(raw) != expected_length:
        raise ProtocolError(
            f'payload length mismatch: header says {payload_length}, '
            f'packet has {len(raw) - HEADER.size - CRC.size}'
        )
    if payload_length > MAX_PAYLOAD_SIZE:
        raise ProtocolError('payload exceeds protocol maximum')

    expected_crc = CRC.unpack_from(raw, len(raw) - CRC.size)[0]
    actual_crc = crc16_ccitt(raw[:-CRC.size])
    if expected_crc != actual_crc:
        raise ProtocolError(
            f'CRC mismatch: expected 0x{expected_crc:04x}, '
            f'calculated 0x{actual_crc:04x}'
        )
    if version != PROTOCOL_VERSION:
        raise ProtocolError(f'unsupported protocol version {version}')

    payload = raw[HEADER.size:-CRC.size]
    return Packet(message_type, sequence, payload, version)


class StreamDecoder:
    """Incrementally split a USB byte stream into protocol packets."""

    def __init__(self, max_encoded_size: int = MAX_PAYLOAD_SIZE + 32):
        self._buffer = bytearray()
        self.max_encoded_size = max_encoded_size
        self.error_count = 0

    def feed(self, data: bytes) -> List[Packet]:
        packets: List[Packet] = []
        for value in data:
            if value == 0:
                if not self._buffer:
                    continue
                try:
                    packets.append(decode_packet(bytes(self._buffer)))
                except ProtocolError:
                    self.error_count += 1
                self._buffer.clear()
            elif len(self._buffer) < self.max_encoded_size:
                self._buffer.append(value)
            else:
                self._buffer.clear()
                self.error_count += 1
        return packets


@dataclass(frozen=True)
class Ack:
    command: int
    result: ResultCode
    sequence: int


@dataclass(frozen=True)
class DeviceStatus:
    led_count: int
    max_led_count: int
    actual_fps: float
    received_frames: int
    displayed_frames: int
    dropped_frames: int
    crc_errors: int
    busy: bool

    @classmethod
    def from_payload(cls, payload: bytes) -> 'DeviceStatus':
        if len(payload) != STATUS_PAYLOAD.size:
            raise ProtocolError('invalid STATUS payload length')
        (
            led_count,
            max_led_count,
            actual_fps_x10,
            received_frames,
            displayed_frames,
            dropped_frames,
            crc_errors,
            busy,
        ) = STATUS_PAYLOAD.unpack(payload)
        return cls(
            led_count=led_count,
            max_led_count=max_led_count,
            actual_fps=actual_fps_x10 / 10.0,
            received_frames=received_frames,
            displayed_frames=displayed_frames,
            dropped_frames=dropped_frames,
            crc_errors=crc_errors,
            busy=bool(busy),
        )


def rgb_bytes(values: Iterable[int], led_count: int | None = None) -> bytes:
    """Validate and normalize an RGB byte iterable."""
    try:
        payload = bytes(values)
    except ValueError as exc:
        raise ValueError('RGB values must be integers in the range 0..255') from exc
    if len(payload) % 3:
        raise ValueError('RGB payload length must be divisible by 3')
    inferred_count = len(payload) // 3
    if led_count is not None and inferred_count != led_count:
        raise ValueError(
            f'RGB payload describes {inferred_count} LEDs, expected {led_count}'
        )
    if inferred_count > MAX_LED_COUNT:
        raise ValueError(f'RGB payload exceeds {MAX_LED_COUNT} LEDs')
    return payload
