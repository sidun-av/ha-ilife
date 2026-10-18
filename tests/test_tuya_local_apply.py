"""Routing local pushes into the coordinator's status and product properties. Pure."""
from __future__ import annotations

import importlib.util
import pathlib
import sys

_PKG = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "ilife"
_spec = importlib.util.spec_from_file_location("_ilife_dpmap_apply", _PKG / "tuya_dpmap.py")
dpmap = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = dpmap
_spec.loader.exec_module(dpmap)

MODEL_CODES = {"switch_go", "status", "suction", "Schedule1", "MapRoomInfo1",
               "CleanPartitionData"}
STANDARD = {"power_go", "status", "suction", "pause"}


def test_apply_routes_standard_and_product_codes():
    status = {"status": "standby", "suction": "strong"}
    props = {"Schedule1": "old"}
    update = {
        "status": "smart",            # standard
        "power_go": True,             # alias target of the model's switch_go
        "electricity_left": 80,       # alias target, not in the spec list given
        "Schedule1": "new",           # product
        "CleanPartitionData": "AQ==", # product
        "mystery": 1,                 # neither: unsure -> both
    }
    new_status, new_props = dpmap.apply_local_dps(status, props, update, MODEL_CODES, STANDARD)
    assert new_status == {"status": "smart", "suction": "strong", "power_go": True,
                          "electricity_left": 80, "mystery": 1}
    assert new_props == {"Schedule1": "new", "CleanPartitionData": "AQ==", "mystery": 1}


def test_apply_known_status_key_stays_status():
    # A code the cloud already reports as status is status even without a spec.
    new_status, new_props = dpmap.apply_local_dps(
        {"suction": "strong"}, {}, {"suction": "normal"}, MODEL_CODES)
    assert new_status == {"suction": "normal"} and new_props == {}


def test_apply_does_not_mutate_inputs():
    status, props = {"status": "standby"}, {"Schedule1": "old"}
    update = {"status": "smart", "Schedule1": "new"}
    new_status, new_props = dpmap.apply_local_dps(status, props, update, MODEL_CODES, STANDARD)
    assert status == {"status": "standby"} and props == {"Schedule1": "old"}
    assert update == {"status": "smart", "Schedule1": "new"}
    assert new_status is not status and new_props is not props


def test_apply_tolerates_none_inputs():
    new_status, new_props = dpmap.apply_local_dps(None, None, {"status": "smart"},
                                                  MODEL_CODES, STANDARD)
    assert new_status == {"status": "smart"} and new_props == {}
