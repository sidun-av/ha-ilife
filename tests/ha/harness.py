"""Fakes and helpers for the Home Assistant tier (see conftest.py).

Nothing leaves the process: the Tuya cloud is a FakeClient answering from the
fixtures, the LAN link a FakeLink that plays the robot. Ids and the local key are
made up; the product id is the A30 Pro's public model id.
"""
from __future__ import annotations

import copy
import json
import pathlib

from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ilife.tuya_api import TuyaAuthError, TuyaError
from custom_components.ilife.tuya_local import TuyaLocalTimeout
from custom_components.ilife.tuya_dpmap import DpMap

FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "fixtures"
A30 = json.loads((FIXTURES / "ilife_a30_pro.json").read_text())
A30_MODEL = json.loads((FIXTURES / "a30pro_model.json").read_text())
DPMAP = DpMap.from_model(A30_MODEL)
A30_PRO = "5309qt4sjd4uz4qz"
DEVICE_ID = "testdevice0000000001"
ENTRY_ID = "testentry"
LOCAL_KEY = "0123456789abcdef"


def device(product_id: str = A30_PRO) -> dict:
    return {"id": DEVICE_ID, "name": "Robot", "product_name": "A30 Pro",
            "category": "sd", "product_id": product_id}


class FakeClient:
    """TuyaClient answering from the A30 Pro fixture; `auth_fail` / `down` make every
    call fail as an expired trial / an unreachable cloud."""

    auth_fail = False
    down = False
    product_id = A30_PRO
    instances: list[FakeClient] = []

    def __init__(self, *_args) -> None:
        self.status = dict(A30["status"])
        self.sent: list = []
        FakeClient.instances.append(self)

    def _check(self) -> None:
        if FakeClient.auth_fail:
            raise TuyaAuthError("28841002 trial expired", 28841002)
        if FakeClient.down:
            raise TuyaError("cloud unreachable")

    def authenticate(self) -> None:
        self._check()

    def list_devices(self) -> list[dict]:
        self._check()
        return [device(FakeClient.product_id)]

    def device_detail(self, _device_id) -> dict:
        self._check()
        return {"status": [{"code": k, "value": v} for k, v in self.status.items()],
                "online": True, "local_key": LOCAL_KEY}

    def device_specification(self, _device_id) -> dict:
        self._check()
        return copy.deepcopy(A30["specification"])

    def device_model_raw(self, _device_id) -> dict:
        self._check()
        return copy.deepcopy(A30_MODEL)

    def device_properties(self, _device_id) -> dict:
        self._check()
        return {"dust_collection_switch": True}

    def send_commands(self, _device_id, commands) -> bool:
        self._check()
        self.sent.append(list(commands))
        for command in commands:
            self.status[command["code"]] = command["value"]
            if command["code"] == "power_go":
                self.status["status"] = "smart" if command["value"] else "standby"
        return True

    def issue_properties(self, _device_id, properties) -> None:
        self._check()
        self.sent.append(dict(properties))

    def realtime_map_files(self, _device_id):
        raise TuyaError("no map")

    def stored_map_records(self, _device_id, _count=5):
        return []

    def stored_map_files(self, _device_id, _record):
        return []

    def latest_stored_map(self, _device_id):
        return None


class FakeLink:
    """TuyaLocalLink playing an A30 Pro on the LAN.

    `start` answers the query at once, as a robot on the LAN beats any cloud round
    trip: the dps first, then connected, in the real link's order. `set_dps` records
    each frame and pushes back what the robot would; an exception queued in
    `failures` is raised after that push, i.e. the robot ran the command and only
    the acknowledgement was lost (or never sent, for a non-timeout error)."""

    answers = True
    # Status codes the robot reports at connect on top of the fixture's (e.g. mid-clean).
    initial: dict = {}
    instances: list[FakeLink] = []

    def __init__(self, _device_id, _key, host, on_dps, on_state) -> None:
        self.host = host
        self.connected = False
        self.failures = 0
        self._on_dps, self._on_state = on_dps, on_state
        self.status = {DPMAP.dp_for(k): v for k, v in {**A30["status"], **FakeLink.initial}.items()
                       if DPMAP.dp_for(k)}
        self.frames: list[dict] = []
        self.errors: list[Exception] = []
        FakeLink.instances.append(self)

    async def start(self) -> None:
        if not FakeLink.answers:
            return
        self._on_dps(dict(self.status))
        self.connected = True
        self._on_state(True)

    async def stop(self) -> None:
        if self.connected:
            self.connected = False
            self._on_state(False)

    def drop(self) -> None:
        """The robot went silent: the link gives up (DEAD_AFTER)."""
        self.connected = False
        self._on_state(False)

    def push(self, **codes) -> None:
        dps = {DPMAP.dp_for(code): value for code, value in codes.items()}
        self.status.update(dps)
        self._on_dps(dps)

    async def set_dps(self, dps: dict) -> None:
        self.frames.append({DPMAP.code_for(dp): value for dp, value in dps.items()})
        error = self.errors.pop(0) if self.errors else None
        if error is not None and not isinstance(error, TuyaLocalTimeout):
            raise error
        pushed = dict(dps)
        power, pause = DPMAP.dp_for("power_go"), DPMAP.dp_for("pause")
        if dps.get(pause) is True:
            # A pause over the LAN leaves the robot in plain standby.
            pushed[DPMAP.dp_for("status")] = "standby"
        elif dps.get(power) is True:
            pushed[DPMAP.dp_for("status")] = "smart"
        elif dps.get(power) is False:
            pushed[DPMAP.dp_for("status")] = "standby"
        self.status.update(pushed)
        self._on_dps(pushed)
        if error is not None:
            raise error


async def _noop(*_args, **_kwargs):
    return None


def make_entry(hass, *, local: bool = True) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain="ilife", entry_id=ENTRY_ID,
        data={"backend": "ilife_clean", "access_id": "id", "access_secret": "secret",
              "uid": "uid", "region": "eu"},
        options={"local": local})
    entry.add_to_hass(hass)
    return entry


def coordinator(hass):
    return next(iter(hass.data["ilife"][ENTRY_ID]["coordinators"].values()))


def entity_id(hass, domain: str, key: str | None = None) -> str:
    registry = er.async_get(hass)
    unique_id = f"{DEVICE_ID}_{key or domain}"
    found = registry.async_get_entity_id(domain, "ilife", unique_id)
    assert found, unique_id
    return found
