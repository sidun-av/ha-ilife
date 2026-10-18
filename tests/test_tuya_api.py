"""What a refused Tuya call tells the user (#30).

The map endpoints belong to a Tuya service of their own. A permission error there
used to carry the setup hint ("IoT Core / Smart Home Basic Service"), which names
services the user already has, and to be raised as an authentication failure,
although everything but the map works without it.

Pure functions, no Home Assistant and no network: the transport is replaced.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import types

import pytest

_PKG = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "ilife"
_pkg = types.ModuleType("_ilife_api")
_pkg.__path__ = [str(_PKG)]
sys.modules["_ilife_api"] = _pkg
_spec = importlib.util.spec_from_file_location("_ilife_api.tuya_api", _PKG / "tuya_api.py")
tuya_api = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = tuya_api
_spec.loader.exec_module(tuya_api)

NOT_SUBSCRIBED = {"success": False, "code": 28841101,
                  "msg": "No permissions. This API is not subscribed."}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(tuya_api, "_do", lambda *args: NOT_SUBSCRIBED)
    tuya = tuya_api.TuyaClient("access-id", "access-secret", "uid")
    tuya._token, tuya._token_expiry = "token", float("inf")
    return tuya


def test_a_refused_map_endpoint_names_the_map_service(client):
    with pytest.raises(tuya_api.TuyaError) as caught:
        client.realtime_map_files("device")
    assert "Sweeping Robot Open Service" in str(caught.value)
    assert "Smart Home Basic Service" not in str(caught.value)
    # the rest of the integration works without the map service
    assert not isinstance(caught.value, tuya_api.TuyaAuthError)


def test_the_stored_map_endpoints_say_the_same(client):
    with pytest.raises(tuya_api.TuyaError) as caught:
        client.stored_map_records("device")
    assert "Sweeping Robot Open Service" in str(caught.value)


def test_other_endpoints_keep_the_setup_hint(client):
    with pytest.raises(tuya_api.TuyaAuthError) as caught:
        client.device_detail("device")
    assert "Smart Home Basic Service" in str(caught.value)


def test_device_model_raw_returns_parsed_model_and_device_model_flattens_it(monkeypatch):
    raw = {"services": [{"properties": [{"abilityId": 1, "code": "switch_go",
                                          "accessMode": "rw", "typeSpec": {"type": "bool"}}]}]}
    reply = {"success": True, "result": {"model": json.dumps(raw)}}
    monkeypatch.setattr(tuya_api, "_do", lambda *args: reply)
    tuya = tuya_api.TuyaClient("access-id", "access-secret", "uid")
    tuya._token, tuya._token_expiry = "token", float("inf")
    assert tuya.device_model_raw("dev") == raw
    assert tuya.device_model("dev") == {"switch_go": {"type": "bool", "access": "rw"}}
    reply["result"]["model"] = "[1]"
    with pytest.raises(tuya_api.TuyaError):
        tuya.device_model_raw("dev")


@pytest.mark.parametrize("error", [TimeoutError("timed out"), ConnectionResetError(54, "reset")])
def test_bare_timeout_or_socket_error_is_a_tuya_error(monkeypatch, error):
    # Not wrapped in URLError by urllib: must still be a TuyaError, so an offline
    # setup falls back to the device cache instead of failing.
    def boom(*args, **kwargs):
        raise error

    monkeypatch.setattr(tuya_api.urllib.request, "urlopen", boom)
    with pytest.raises(tuya_api.TuyaError):
        tuya_api._do("openapi.tuyaeu.com", "GET", "/v1.0/token", {}, None)
