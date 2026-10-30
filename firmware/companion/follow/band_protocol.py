"""Parse the wristband's BLE manufacturer-specific advertisement.

Layout (after the 2-byte manufacturer id), see firmware/wristband/src/main.cpp:
    [0] protocol version   [1] band id   [2] battery %   [3] button state
    [4..5] uptime seconds (little endian, low 16 bits)
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Optional

from .safety import BandButton

MANUFACTURER_ID = 0xFFFF
PROTOCOL_VERSION = 1
PAYLOAD_LEN = 6


@dataclass(frozen=True)
class BandStatus:
    band_id: int
    battery_pct: int
    button: BandButton
    uptime_s: int


def parse_manufacturer_data(data: bytes) -> Optional[BandStatus]:
    """Return a BandStatus, or None if the bytes are not from a compatible band."""
    if len(data) < 2 + PAYLOAD_LEN:
        return None
    (mfr,) = struct.unpack_from("<H", data, 0)
    if mfr != MANUFACTURER_ID:
        return None
    version, band_id, battery, button, uptime = struct.unpack_from("<BBBBH", data, 2)
    if version != PROTOCOL_VERSION:
        return None
    try:
        btn = BandButton(button)
    except ValueError:
        btn = BandButton.NONE
    return BandStatus(band_id, min(battery, 100), btn, uptime)


def encode_manufacturer_data(status: BandStatus) -> bytes:
    """Inverse of parse_manufacturer_data; used by tests and the simulator."""
    return struct.pack(
        "<HBBBBH",
        MANUFACTURER_ID,
        PROTOCOL_VERSION,
        status.band_id,
        status.battery_pct,
        int(status.button),
        status.uptime_s & 0xFFFF,
    )
