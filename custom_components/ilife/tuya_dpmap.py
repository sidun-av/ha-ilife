"""Datapoint id <-> code mapping for local (LAN) Tuya traffic.

Locally the robot reports numeric dp ids ({"5": "smart"}); the rest of the
integration works in codes. The thing model carries both (`abilityId`, `code`).
Some products name standard datapoints differently from the standard instruction
set (A30 Pro: `switch_go` for `power_go`); those are reported under the standard
name so the cloud and local paths feed the coordinator the same keys.

Pure functions, no Home Assistant, no network.
"""
from __future__ import annotations

from collections.abc import Collection
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
    standard_codes: set[str] = frozenset(),
) -> tuple[dict, dict]:
    """Route one local push into (status, product properties); new dicts, inputs intact.

    Status is what the cloud's device detail reports (standard codes, the ones
    `const.TUYA_DP_*` name); product properties are the thing-model-only DPs
    (Schedule1, CleanPartitionData, MapRoomInfo1, ...). A code counts as status when
    the spec lists it, it is a standard alias target, or status already holds it;
    else it is a product property: `split_local_dps` only yields thing-model codes
    and standard aliases, so a code that is not status is one only the thing model
    knows. Product codes stay out of status so they never turn into generic sensors.
    """
    new_status, new_props = dict(status or {}), dict(properties or {})
    aliases = set(MODEL_TO_STANDARD.values())
    for code, value in (update or {}).items():
        is_status = code in standard_codes or code in aliases or code in new_status
        if is_status:
            new_status[code] = value
        else:
            new_props[code] = value
    return new_status, new_props


def merge_cloud_status(cloud: dict | None, current: dict | None,
                       lan_codes: Collection[str] = ()) -> dict:
    """A cloud status read that the LAN link overtook: the codes the link delivered
    win, the fresh cloud read wins over everything else.

    `current` is the coordinator's whole status, `lan_codes` the codes the link has
    delivered since it came up. The rest of `current` is an older read (the previous
    cloud poll, the cache): kept for the codes this read lacks, never over it.

    The robot leaves some datapoints out of its answer to a LAN query (the A30 Pro:
    do-not-disturb, auto-empty, the reset and joystick DPs) and only pushes them
    when they change, so a status built from the LAN alone lacks them. Dropping the
    cloud read because the link came up during it left those entities `unknown`
    until the next restart that happened to go the other way; letting the older
    status win kept a setting changed in the app meanwhile wrong until it changed
    again.
    """
    current = current or {}
    return {**current, **(cloud or {}),
            **{code: current[code] for code in lan_codes if code in current}}


def setting_value(status: dict | None, properties: dict | None, code: str) -> Any:
    """A setting DP's value: the status first (LAN pushes, cloud detail), else the
    product properties, which the cloud reads out of the thing model and which do
    carry the DPs the robot leaves out of its LAN answer. None when neither has it."""
    value = (status or {}).get(code)
    if value is None:
        value = (properties or {}).get(code)
    return value
