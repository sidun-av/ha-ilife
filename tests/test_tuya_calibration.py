"""Map calibration: vacuum (map cell, robot frame, y up) -> camera image pixel.

Header values are those of the A30 Pro map in tests/fixtures; a pure dict is
enough, the calibration only reads the header.
"""
from __future__ import annotations

import importlib.util
import os
import pathlib
import sys
import types

_PKG = pathlib.Path(
    os.environ.get("ILIFE_PKG")
    or pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "ilife"
)
_pkg = types.ModuleType("_ilife_cal")
_pkg.__path__ = [str(_PKG)]
sys.modules["_ilife_cal"] = _pkg


def _load(name):
    spec = importlib.util.spec_from_file_location(f"_ilife_cal.{name}", _PKG / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_load("tuya_lz4")
tuya_map = _load("tuya_map")

A30_HEADER = {"origin_x": 850, "origin_y": 610, "resolution_cm": 5, "width": 159, "height": 153}


def test_calibration_points_on_a30_header():
    points = tuya_map.calibration_points(A30_HEADER, 6)
    assert points == [
        # Cell centres: half a cell (3 px at scale 6) past the cell's corner.
        {"vacuum": {"x": 0, "y": 0}, "map": {"x": 513, "y": 369}},
        {"vacuum": {"x": 10, "y": 0}, "map": {"x": 573, "y": 369}},
        {"vacuum": {"x": 0, "y": 10}, "map": {"x": 513, "y": 309}},
    ]
    # Inside the 954 x 918 image.
    for point in points:
        assert 0 <= point["map"]["x"] < 159 * 6 and 0 <= point["map"]["y"] < 153 * 6


def test_calibration_follows_scale():
    points = tuya_map.calibration_points(A30_HEADER, 3)
    assert points[0]["map"] == {"x": 256.5, "y": 184.5}
