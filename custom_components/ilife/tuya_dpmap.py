"""Datapoint id <-> code mapping for local (LAN) Tuya traffic.

Locally the robot reports numeric dp ids ({"5": "smart"}); the rest of the
integration works in codes. The thing model carries both (`abilityId`, `code`).
Some products name standard datapoints differently from the standard instruction
set (A30 Pro: `switch_go` for `power_go`); those are reported under the standard
name so the cloud and local paths feed the coordinator the same keys.

Pure functions, no Home Assistant, no network.
"""
from __future__ import annotations

from typing import Any

MODEL_TO_STANDARD = {
    "switch_go": "power_go",
    "residual_electricity": "electricity_left",
    "clean_area_total": "total_clean_area",
    "clean_count_total": "total_clean_count",
    "clean_time_total": "total_clean_time",
}
_STANDARD_TO_MODEL = {v: k for k, v in MODEL_TO_STANDARD.items()}


class DpMap:
    """dp id (str) -> model code, with the standard-name alias on top."""

    def __init__(self, id_to_code: dict[str, str]) -> None:
        self._id_to_code = dict(id_to_code)
        self._code_to_id = {code: dp for dp, code in self._id_to_code.items()}

    @classmethod
    def from_model(cls, raw_model: dict) -> "DpMap":
        mapping: dict[str, str] = {}
        services = raw_model.get("services") if isinstance(raw_model, dict) else None
        for service in services or []:
            if not isinstance(service, dict):
                continue
            for prop in service.get("properties") or []:
                if not isinstance(prop, dict):
                    continue
                ability, code = prop.get("abilityId"), prop.get("code")
                if isinstance(ability, bool) or not isinstance(ability, (int, str)) or not code:
                    continue
                mapping[str(ability)] = str(code)
        return cls(mapping)

    def code_for(self, dp_id: str) -> str | None:
        code = self._id_to_code.get(str(dp_id))
        return MODEL_TO_STANDARD.get(code, code) if code else None

    def dp_for(self, code: str) -> str | None:
        """The dp id for a model code or its standard alias."""
        dp = self._code_to_id.get(code)
        if dp is None and code in _STANDARD_TO_MODEL:
            dp = self._code_to_id.get(_STANDARD_TO_MODEL[code])
        return dp

    def to_dict(self) -> dict[str, str]:
        return dict(self._id_to_code)

    @classmethod
    def from_dict(cls, data: dict) -> "DpMap":
        return cls({str(k): str(v) for k, v in (data or {}).items()})


def split_local_dps(dps: dict[str, Any], dpmap: DpMap) -> dict[str, Any]:
    """{dp id: value} -> {code: value}; ids the model doesn't know are dropped."""
    out: dict[str, Any] = {}
    for dp_id, value in (dps or {}).items():
        code = dpmap.code_for(dp_id)
        if code is not None:
            out[code] = value
    return out


def apply_local_dps(
    status: dict | None,
    properties: dict | None,
    update: dict[str, Any],
    model_codes: set[str],
    standard_codes: set[str] = frozenset(),
) -> tuple[dict, dict]:
    """Route one local push into (status, product properties); new dicts, inputs intact.

    Status is what the cloud's device detail reports (standard codes, the ones
    `const.TUYA_DP_*` name); product properties are the thing-model-only DPs
    (Schedule1, CleanPartitionData, MapRoomInfo1, ...). A code counts as status when
    the spec lists it, it is a standard alias target, or status already holds it; as
    a product property when only the thing model knows it; unsure codes go to both.
    Product codes stay out of status so they never turn into generic sensors.
    """
    new_status, new_props = dict(status or {}), dict(properties or {})
    aliases = set(MODEL_TO_STANDARD.values())
    for code, value in (update or {}).items():
        is_status = code in standard_codes or code in aliases or code in new_status
        if is_status:
            new_status[code] = value
        elif code in model_codes:
            new_props[code] = value
        else:
            new_status[code] = value
            new_props[code] = value
    return new_status, new_props
