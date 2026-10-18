"""Zone cleaning on ILIFE Clean laser models (A30 Pro): dp 139 `CleanAreaData`.

    CleanAreaData   string, base64 of
        01, passes (1 or 2), zone count, then per zone four corners, each a
        big-endian signed 16-bit (x, y) in map cells from the map header's
        origin, robot frame (y up): (x1, y2) (x2, y2) (x2, y1) (x1, y1).

Verified over the LAN (docs/re/a30pro-zone-formats.md, "Live verification"):
writing it alone starts the zone clean; the robot reports `zone_clean`.
"""
from __future__ import annotations

import base64
import struct
from collections.abc import Iterable, Sequence

CLEAN_ZONE_CODE = "CleanAreaData"
MAX_ZONES = 5
MAX_ZONE_PASSES = 2
_S16 = range(-32768, 32768)


def clean_zone_value(zones: Iterable[Sequence[int]], passes: int = 1) -> str:
    """The CleanAreaData value that cleans each (x1, y1, x2, y2) zone `passes` times."""
    zones = [tuple(int(v) for v in zone) for zone in zones]
    if not zones:
        raise ValueError("no zone given")
    if len(zones) > MAX_ZONES:
        raise ValueError(f"at most {MAX_ZONES} zones")
    if passes not in range(1, MAX_ZONE_PASSES + 1):
        raise ValueError(f"passes must be between 1 and {MAX_ZONE_PASSES}")
    raw = bytearray([1, passes, len(zones)])
    for zone in zones:
        if len(zone) != 4:
            raise ValueError(f"a zone is [x1, y1, x2, y2], got {list(zone)}")
        if any(v not in _S16 for v in zone):
            raise ValueError(f"zone {list(zone)} is outside the map")
        x1, x2 = sorted((zone[0], zone[2]))
        y1, y2 = sorted((zone[1], zone[3]))
        raw += struct.pack(">8h", x1, y2, x2, y2, x2, y1, x1, y1)
    return base64.b64encode(bytes(raw)).decode()
