"""Synchronous USB CDC client for the ARES Pico LED controller."""

from __future__ import annotations

import glob
import struct
import threading
import time
from typing import Iterable, Optional

from .protocol import (
    Ack,
    DeviceStatus,
    MAX_LED_COUNT,
    MessageType,
    Packet,
    ProtocolError,
    ProtocolNack,
    ResultCode,
    StreamDecoder,
    rgb_bytes,
)


def find_device() -> str:
    """Return the most likely stable path for one connected controller."""
    preferred = []
    for path in sorted(glob.glob('/dev/serial/by-id/*')):
        lowered = path.lower()
        if any(token in lowered for token in ('ares', 'rp2040', 'pico')):
            preferred.append(path)
    if preferred:
        return preferred[0]
    fallback = sorted(glob.glob('/dev/ttyACM*'))
    if len(fallback) == 1:
        return fallback[0]
    if not fallback:
        raise FileNotFoundError('no RP2040 USB CDC serial device found')
    raise RuntimeError(
        'multiple /dev/ttyACM devices found; specify a /dev/serial/by-id path'
    )


class AresPicoClient:
    """Request/response client with strict sequence and ACK validation."""

    def __init__(
        self,
        port: str = 'auto',
        *,
        timeout: float = 0.5,
        serial_instance=None,
    ):
        self.port = port
        self.timeout = timeout
        self._serial = serial_instance
        self._owns_serial = serial_instance is None
        self._sequence = 0
        self._decoder = StreamDecoder()
        self._request_lock = threading.Lock()
        self.led_count: Optional[int] = None
        self.last_status: Optional[DeviceStatus] = None

    @property
    def is_open(self) -> bool:
        return self._serial is not None and bool(self._serial.is_open)

    def open(self) -> None:
        if self.is_open:
            return
        if not self._owns_serial:
            if hasattr(self._serial, 'open'):
                self._serial.open()
            return
        try:
            import serial
        except ImportError as exc:
            raise RuntimeError('pyserial is required; install python3-serial') from exc
        if not hasattr(serial, 'Serial'):
            module_path = getattr(serial, '__file__', '<unknown>')
            raise RuntimeError(
                'imported module "serial" is not pyserial '
                f'({module_path}); uninstall the package named "serial" and '
                'install python3-serial or pyserial'
            )
        resolved_port = find_device() if self.port == 'auto' else self.port
        self._serial = serial.Serial(
            resolved_port,
            baudrate=115200,
            timeout=min(self.timeout, 0.05),
            write_timeout=self.timeout,
            exclusive=True,
        )
        # Opening a CDC port can coincide with a board reset on some hosts.
        time.sleep(0.05)
        self._serial.reset_input_buffer()

    def close(self) -> None:
        if self._serial is not None and self._serial.is_open:
            self._serial.close()

    def __enter__(self) -> 'AresPicoClient':
        self.open()
        return self

    def __exit__(self, *_args) -> None:
        self.close()

    def _next_sequence(self) -> int:
        self._sequence = (self._sequence + 1) & 0xFFFF
        return self._sequence

    def _request(
        self,
        message_type: MessageType,
        payload: bytes = b'',
        *,
        expect_status: bool = False,
    ):
        if not self.is_open:
            self.open()
        with self._request_lock:
            sequence = self._next_sequence()
            self._serial.write(Packet(message_type, sequence, payload).encode())
            self._serial.flush()
            deadline = time.monotonic() + self.timeout

            while time.monotonic() < deadline:
                waiting = getattr(self._serial, 'in_waiting', 0)
                chunk = self._serial.read(max(1, min(waiting, 4096)))
                if not chunk:
                    continue
                for packet in self._decoder.feed(chunk):
                    if packet.message_type == MessageType.STATUS:
                        status = DeviceStatus.from_payload(packet.payload)
                        self.last_status = status
                        if expect_status and packet.sequence == sequence:
                            return status
                        continue
                    if packet.sequence != sequence:
                        continue
                    if packet.message_type not in (
                        MessageType.ACK,
                        MessageType.NACK,
                    ):
                        continue
                    if len(packet.payload) != 2:
                        raise ProtocolError('ACK/NACK payload must be two bytes')
                    command, result_value = packet.payload
                    if command != int(message_type):
                        raise ProtocolError('ACK command does not match request')
                    if packet.message_type == MessageType.NACK:
                        raise ProtocolNack(command, result_value)
                    try:
                        result = ResultCode(result_value)
                    except ValueError as exc:
                        raise ProtocolError('unknown ACK result code') from exc
                    return Ack(command, result, sequence)
            raise TimeoutError(
                f'timed out waiting for Pico response to 0x{int(message_type):02x}'
            )

    def ping(self) -> Ack:
        return self._request(MessageType.PING)

    def configure_led_count(self, led_count: int) -> Ack:
        if not 1 <= led_count <= MAX_LED_COUNT:
            raise ValueError(f'led_count must be in 1..{MAX_LED_COUNT}')
        ack = self._request(
            MessageType.CONFIG_LED_COUNT,
            struct.pack('<H', led_count),
        )
        self.led_count = led_count
        return ack

    def send_frame(self, values: Iterable[int]) -> Ack:
        if self.led_count is None:
            raise RuntimeError('configure_led_count() must succeed before send_frame()')
        payload = rgb_bytes(values, self.led_count)
        return self._request(MessageType.SET_FRAME, payload)

    def configure_and_send(self, values: Iterable[int]) -> Ack:
        payload = rgb_bytes(values)
        led_count = len(payload) // 3
        if led_count == 0:
            raise ValueError('an empty RGB frame does not configure a strip')
        if led_count != self.led_count:
            self.configure_led_count(led_count)
        return self.send_frame(payload)

    def get_status(self) -> DeviceStatus:
        return self._request(MessageType.GET_STATUS, expect_status=True)
