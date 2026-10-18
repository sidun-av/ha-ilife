"""Zone-clean encoding (dp 139 CleanAreaData) for ILIFE Clean laser models.

The expected value is the payload that started a zone clean on an A30 Pro over
the LAN (docs/re/a30pro-zone-formats.md, "Live verification").
"""
from __future__ import annotations

import base64
import importlib.util
import os
import pathlib
import struct
import sys

import pytest

_PKG = pathlib.Path(
    os.environ.get("ILIFE_PKG")
    or pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "ilife"
)
_spec = importlib.util.spec_from_file_location("_ilife_zones", _PKG / "tuya_zones.py")
tuya_zones = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = tuya_zones
_spec.loader.exec_module(tuya_zones)


def test_zone_value_matches_live_capture():
    assert tuya_zones.CLEAN_ZONE_CODE == "CleanAreaData"
    assert tuya_zones.clean_zone_value([(2, -5, 12, 5)], 1) == "AQEBAAIABQAMAAUADP/7AAL/+w=="


def test_zone_corners_are_normalised():
    assert (tuya_zones.clean_zone_value([(12, 5, 2, -5)])
            == tuya_zones.clean_zone_value([(2, -5, 12, 5)]))


def test_passes_and_several_zones():
    raw = base64.b64decode(tuya_zones.clean_zone_value([(0, 0, 1, 1), (-3, -4, -1, -2)], 2))
    assert raw[:3] == bytes([1, 2, 2])
    assert len(raw) == 3 + 2 * 16
    assert struct.unpack(">8h", raw[19:]) == (-3, -2, -1, -2, -1, -4, -3, -4)


def test_zone_bounds():
    value = tuya_zones.clean_zone_value
    with pytest.raises(ValueError):
        value([])
    with pytest.raises(ValueError):
        value([(0, 0, 1, 1)] * 6)
    value([(0, 0, 1, 1)] * 5)
    for passes in (0, 3):
        with pytest.raises(ValueError):
            value([(0, 0, 1, 1)], passes)
    for bad in ((0, 0, 32768, 1), (-32769, 0, 1, 1)):
        with pytest.raises(ValueError):
            value([bad])
    value([(-32768, -32768, 32767, 32767)])
