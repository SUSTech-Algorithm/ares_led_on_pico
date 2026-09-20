"""Host-side API for the ARES RP2040 LED controller."""

from .client import AresPicoClient, find_device
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
)

__all__ = [
    'Ack',
    'AresPicoClient',
    'DeviceStatus',
    'MAX_LED_COUNT',
    'MessageType',
    'Packet',
    'ProtocolError',
    'ProtocolNack',
    'ResultCode',
    'StreamDecoder',
    'find_device',
]
