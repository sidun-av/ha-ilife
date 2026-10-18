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
    }
    new_status, new_props = dpmap.apply_local_dps(status, props, update, STANDARD)
    assert new_status == {"status": "smart", "suction": "strong", "power_go": True,
                          "electricity_left": 80}
    assert new_props == {"Schedule1": "new", "CleanPartitionData": "AQ=="}


def test_split_then_apply_never_meets_a_code_outside_the_model():
    """split_local_dps yields only thing-model codes and their standard aliases, so
    anything apply_local_dps does not call status is a thing-model property."""
    model = dpmap.DpMap({"1": "switch_go", "5": "status", "120": "Schedule1"})
    update = dpmap.split_local_dps({"1": True, "5": "smart", "120": "x", "999": 1}, model)
    assert update == {"power_go": True, "status": "smart", "Schedule1": "x"}
    new_status, new_props = dpmap.apply_local_dps({}, {}, update, STANDARD)
    assert new_status == {"power_go": True, "status": "smart"}
    assert new_props == {"Schedule1": "x"}


def test_apply_known_status_key_stays_status():
    # A code the cloud already reports as status is status even without a spec.
    new_status, new_props = dpmap.apply_local_dps(
        {"suction": "strong"}, {}, {"suction": "normal"})
    assert new_status == {"suction": "normal"} and new_props == {}


def test_apply_does_not_mutate_inputs():
    status, props = {"status": "standby"}, {"Schedule1": "old"}
    update = {"status": "smart", "Schedule1": "new"}
    new_status, new_props = dpmap.apply_local_dps(status, props, update, STANDARD)
    assert status == {"status": "standby"} and props == {"Schedule1": "old"}
    assert update == {"status": "smart", "Schedule1": "new"}
    assert new_status is not status and new_props is not props


def test_apply_tolerates_none_inputs():
    new_status, new_props = dpmap.apply_local_dps(None, None, {"status": "smart"},
                                                  STANDARD)
    assert new_status == {"status": "smart"} and new_props == {}


def test_cloud_status_overtaken_by_the_link_keeps_cloud_only_codes():
    # The A30 Pro leaves dp 25/38 out of its LAN query answer: a cloud read that
    # the link overtook must not lose them, while the LAN values stay fresher.
    cloud = {"status": "standby", "switch_disturb": False, "dust_collection_switch": False}
    local = {"status": "base_charging", "break_clean": True}
    lan = {"status", "break_clean"}
    assert dpmap.merge_cloud_status(cloud, local, lan) == {
        "status": "base_charging", "break_clean": True,
        "switch_disturb": False, "dust_collection_switch": False}
    assert dpmap.merge_cloud_status(None, local, lan) == local
    assert dpmap.merge_cloud_status(cloud, None, lan) == cloud


def test_fresh_cloud_read_beats_an_older_status_the_link_did_not_deliver():
    # `current` holds the previous cloud poll (DND off) plus the LAN answer, which
    # leaves DND out; the user turned DND on in the app meanwhile. The fresh read
    # must win for DND, the LAN for what it did deliver.
    current = {"status": "base_charging", "switch_disturb": False, "volume_set": 40}
    cloud = {"status": "standby", "switch_disturb": True}
    assert dpmap.merge_cloud_status(cloud, current, {"status"}) == {
        "status": "base_charging", "switch_disturb": True, "volume_set": 40}
    # Nothing delivered over the LAN yet: the cloud read wins outright.
    assert dpmap.merge_cloud_status(cloud, current) == {
        "status": "standby", "switch_disturb": True, "volume_set": 40}


def test_setting_value_falls_back_to_properties():
    assert dpmap.setting_value({"switch_disturb": True}, {"switch_disturb": False},
                               "switch_disturb") is True
    assert dpmap.setting_value({}, {"switch_disturb": False}, "switch_disturb") is False
    assert dpmap.setting_value(None, None, "switch_disturb") is None
    assert dpmap.setting_value({"other": 1}, {}, "switch_disturb") is None
