"""Rooms as Home Assistant vacuum segments."""
from __future__ import annotations

import importlib.util
import os
import pathlib
import sys

_PKG = pathlib.Path(
    os.environ.get("ILIFE_PKG")
    or pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "ilife"
)
_spec = importlib.util.spec_from_file_location("_ilife_rooms_segments", _PKG / "tuya_rooms.py")
tuya_rooms = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = tuya_rooms
_spec.loader.exec_module(tuya_rooms)


def test_segments_from_room_names():
    assert tuya_rooms.segments_from_rooms({4: "Office", 0: "Living"}) == [
        ("0", "Living"), ("4", "Office"),
    ]


def test_no_rooms_no_segments():
    assert tuya_rooms.segments_from_rooms({}) == []


def test_unnamed_map_rooms_get_fallback_names():
    assert tuya_rooms.segments_from_rooms({}, {0: "", 1: "", 2: "", 3: ""}) == [
        ("0", "Room 1"), ("1", "Room 2"), ("2", "Room 3"), ("3", "Room 4"),
    ]


def test_app_name_overrides_map_room():
    assert tuya_rooms.segments_from_rooms({2: "Hall"}, {0: "Room 1", 2: "Room 3"}) == [
        ("0", "Room 1"), ("2", "Hall"),
    ]
