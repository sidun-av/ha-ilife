"""dp id <-> code mapping from the thing model. Pure, HA-free."""
from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import pytest

_PKG = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "ilife"
_spec = importlib.util.spec_from_file_location("_ilife_dpmap", _PKG / "tuya_dpmap.py")
dpmap = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = dpmap
_spec.loader.exec_module(dpmap)

MODEL = json.loads((pathlib.Path(__file__).parent / "fixtures" / "a30pro_model.json").read_text())


@pytest.fixture
def m():
    return dpmap.DpMap.from_model(MODEL)


def test_standard_codes_are_aliased(m):
    assert m.code_for("1") == "power_go"
    assert m.code_for("8") == "electricity_left"
    assert m.dp_for("power_go") == m.dp_for("switch_go") == "1"


def test_product_codes_map(m):
    assert m.code_for("129") == "CleanPartitionData"
    assert m.code_for("120") == "Schedule1"
    assert m.dp_for("CleanPartitionData") == "129"


def test_unknown_dp_ids_are_dropped(m):
    assert dpmap.split_local_dps({"999": 1, "5": "smart"}, m) == {"status": "smart"}
    assert m.code_for("999") is None and m.dp_for("nope") is None


def test_already_standard_code_is_unchanged():
    model = {"services": [{"properties": [{"abilityId": 1, "code": "power_go"}]}]}
    mm = dpmap.DpMap.from_model(model)
    assert mm.code_for("1") == "power_go" and mm.dp_for("power_go") == "1"


def test_malformed_model_entries_are_skipped():
    mm = dpmap.DpMap.from_model({"services": [None, {"properties": [{"code": "x"}, 5,
                                 {"abilityId": 3, "code": "ok"}]}]})
    assert mm.code_for("3") == "ok"
    assert dpmap.DpMap.from_model({}).code_for("3") is None


def test_round_trip_dict(m):
    again = dpmap.DpMap.from_dict(json.loads(json.dumps(m.to_dict())))
    assert again.code_for("1") == "power_go" and again.dp_for("switch_go") == "1"
    assert again.to_dict() == m.to_dict()


def test_every_a30_status_has_a_meaning():
    # An unlisted status fell through to "idle": the robot full on its dock
    # ("base_sleeping") showed as idle instead of docked.
    spec = importlib.util.spec_from_file_location("_ilife_const", _PKG / "const.py")
    const = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(const)
    status = next(item for item in MODEL["services"][0]["properties"] if item["code"] == "status")
    known = (const.TUYA_STATUS_DOCKED | const.TUYA_STATUS_RETURNING | const.TUYA_STATUS_IDLE
             | const.TUYA_STATUS_PAUSED | const.TUYA_STATUS_CLEANING)
    assert set(status["typeSpec"]["range"]) - known == set()
    assert "base_sleeping" in const.TUYA_STATUS_DOCKED
