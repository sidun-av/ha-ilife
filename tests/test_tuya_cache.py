"""Offline cache: the pure helpers that decide what survives a restart without
internet. HA-free: `DeviceCache` imports Home Assistant only when constructed."""
from __future__ import annotations

import importlib.util
import pathlib
import sys

_PKG = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "ilife"
_spec = importlib.util.spec_from_file_location("_ilife_cache", _PKG / "tuya_cache.py")
cache = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = cache
_spec.loader.exec_module(cache)

SPEC = {"category": "sd", "functions": [{"code": "power_go", "type": "Boolean",
                                         "values": "{}"}]}


def test_merge_keeps_old_when_fresh_is_none():
    old = {"device": {"id": "x"}, "spec": SPEC, "local_key": "0123456789abcdef",
           "host": "192.0.2.10"}
    merged = cache.merge_cache(old, spec=None, local_key=None, host=None,
                               properties={"a": 1})
    assert merged == {**old, "properties": {"a": 1}}
    assert old.get("properties") is None  # old dict not mutated


def test_merge_replaces_with_fresh_and_tolerates_no_old():
    assert cache.merge_cache(None, local_key="0123456789abcdef") == {
        "local_key": "0123456789abcdef"}
    assert cache.merge_cache({"spec": {"old": 1}}, spec=SPEC) == {"spec": SPEC}


def test_cached_spec_is_used_when_cloud_fails():
    # cloud call failed (None) or answered nothing ({}) -> cached spec
    assert cache.pick(None, SPEC) == SPEC
    assert cache.pick({}, SPEC) == SPEC
    # cloud answered -> fresh wins
    fresh = {"functions": []}
    assert cache.pick({"category": "sd", **fresh}, SPEC) == {"category": "sd", **fresh}
    # nothing anywhere -> empty dict, never None
    assert cache.pick(None, None) == {}


def test_seed_status_only_from_a_non_empty_dict():
    assert cache.seed_status(None) is None
    assert cache.seed_status({}) is None
    assert cache.seed_status(["x"]) is None
    cached = {"status": "standby", "electricity_left": 87}
    seeded = cache.seed_status(cached)
    assert seeded == cached and seeded is not cached


def test_status_save_debounce():
    status = {"status": "smart", "electricity_left": 80}
    # Nothing saved yet, or a code appeared/disappeared: save now.
    assert cache.status_save_due(None, status, None, 0.0)
    assert cache.status_save_due({"status": "smart"}, status, 10.0, 11.0)
    # Same codes, same values: never.
    assert not cache.status_save_due(dict(status), status, 0.0, 10_000.0)
    # Same codes, new values: only once the last save is old enough.
    changed = {**status, "electricity_left": 79}
    assert not cache.status_save_due(status, changed, 100.0, 399.0)
    assert cache.status_save_due(status, changed, 100.0, 400.0)
    assert not cache.status_save_due(status, {}, None, 0.0)


def test_map_rooms_round_trip_through_json_keys():
    rooms = {1: "Room 1", 12: "Kitchen"}
    stored = cache.map_rooms_to_cache(rooms)
    assert stored == {"1": "Room 1", "12": "Kitchen"}
    assert cache.map_rooms_from_cache(stored) == rooms
    assert cache.map_rooms_from_cache({"x": "bad", "3": "Room 3"}) == {3: "Room 3"}
    assert cache.map_rooms_from_cache(None) == {}


def test_map_file_name_is_filesystem_safe():
    assert cache.map_file_name("abc123") == "ilife_map_abc123.png"
    assert cache.map_file_name("a/../b c") == "ilife_map_a____b_c.png"


def test_map_meta_roundtrip_and_persist_due():
    png = b"\x89PNG-fake"
    meta = {"calibration_points": [{"vacuum": {"x": 0, "y": 0}, "map": {"x": 1.5, "y": 2}}],
            "map_scale": 8, "rooms": {3: "Kitchen"}, "other": object()}
    stored = cache.map_meta_to_cache(meta, png)
    assert stored["rooms"] == {"3": "Kitchen"} and "other" not in stored
    back = cache.map_meta_from_cache(stored)
    assert back["rooms"] == {3: "Kitchen"} and back["map_scale"] == 8
    assert back["calibration_points"] == meta["calibration_points"]
    assert not cache.map_persist_due(stored, png)
    assert cache.map_persist_due(stored, png + b"x")
    assert cache.map_persist_due(None, png)
    assert not cache.map_persist_due(None, None)


def test_map_meta_from_cache_rejects_junk():
    assert cache.map_meta_from_cache(None) is None
    assert cache.map_meta_from_cache({"rooms": {}}) is None


def test_is_network_error():
    assert cache.is_network_error(Exception("network error: <urlopen error>"))
    assert cache.is_network_error(Exception("map file download failed: x"))
    assert not cache.is_network_error(Exception("1106: permission deny"))
