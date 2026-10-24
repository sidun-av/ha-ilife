"""Saved zones: what a save stores and the button key a name gets."""
from __future__ import annotations

import importlib
import os
import pathlib
import sys
import types

import pytest

_PKG = pathlib.Path(
    os.environ.get("ILIFE_PKG")
    or pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "ilife"
)
# saved_zones imports its sibling tuya_zones relatively: a bare package around the
# directory is enough, without Home Assistant.
_pkg = types.ModuleType("_ilife_zones_pkg")
_pkg.__path__ = [str(_PKG)]
sys.modules[_pkg.__name__] = _pkg
saved_zones = importlib.import_module("_ilife_zones_pkg.saved_zones")


def test_normalize_rounds_and_trims():
    name, value = saved_zones.normalize_zone("  Угол   кухни ", [[8.4, -79.6, 58, -36]], 2)
    assert name == "Угол кухни"
    assert value == {"zone": [[8, -80, 58, -36]], "repeats": 2}


@pytest.mark.parametrize("name, zone, repeats", [
    ("", [[0, 0, 1, 1]], 1),                       # no name
    ("x" * 41, [[0, 0, 1, 1]], 1),                 # too long a name
    ("a", [], 1),                                  # no rectangle
    ("a", [[0, 0, 1, 1]] * 6, 1),                  # more than 5
    ("a", [[0, 0, 1]], 1),                         # not four numbers
    ("a", [[0, 0, 1, 1]], 3),                      # 3 passes
])
def test_normalize_refuses(name, zone, repeats):
    with pytest.raises((ValueError, TypeError)):
        saved_zones.normalize_zone(name, zone, repeats)


def test_zone_key_is_stable_and_case_blind():
    assert saved_zones.zone_key("Угол кухни") == saved_zones.zone_key("угол КУХНИ")
    assert saved_zones.zone_key("Угол кухни") != saved_zones.zone_key("Угол спальни")
    assert len(saved_zones.zone_key("Угол кухни")) == 10


def test_stored_zones_drops_broken_entries():
    raw = {"Угол": {"zone": [[8, -79, 58, -36]], "repeats": 1},
           "bad": {"zone": [[1, 2]]}, "": {"zone": [[0, 0, 1, 1]]}, "none": None}
    assert saved_zones.stored_zones(raw) == {"Угол": {"zone": [[8, -79, 58, -36]], "repeats": 1}}
    assert saved_zones.stored_zones(None) == {}
