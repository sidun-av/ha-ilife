"""Home Assistant tier: the integration's glue run inside a real Home Assistant.

The pure modules are tested in tests/ without Home Assistant. These tests cover what
only shows up with it: setup and its fallbacks, the coordinator's poll against a
LAN link, entity availability, the vacuum's command paths and the camera timer.
Nothing leaves the process: the Tuya cloud is a FakeClient answering from the
fixtures, the LAN link a FakeLink that plays the robot (harness.py). Skipped
without Home Assistant (see CONTRIBUTING.md for the venv).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("homeassistant")
pytest.importorskip("pytest_homeassistant_custom_component")

import custom_components.ilife as integ  # noqa: E402
from custom_components.ilife import vacuum as vacuum_module  # noqa: E402
from harness import (  # noqa: E402
    A30,
    A30_MODEL,
    A30_PRO,
    DEVICE_ID,
    ENTRY_ID,
    LOCAL_KEY,
    FakeClient,
    FakeLink,
    _noop,
    device,
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
def fakes(hass):
    """The cloud, the LAN and the frontend replaced; fast suction nudge."""
    hass.config.components.update({"frontend", "http"})
    # The camera component registers its image views on the HTTP server.
    hass.http = MagicMock()
    FakeClient.auth_fail = FakeClient.down = False
    FakeClient.product_id = A30_PRO
    FakeClient.instances.clear()
    FakeLink.answers = True
    FakeLink.instances.clear()
    with patch.object(integ, "TuyaClient", FakeClient), \
            patch.object(integ, "TuyaLocalLink", FakeLink), \
            patch.object(integ, "discover_device", _noop), \
            patch.object(integ, "_async_register_frontend", _noop), \
            patch.object(vacuum_module, "SUCTION_NUDGE_DELAY", 0.02), \
            patch.object(vacuum_module, "SUCTION_NUDGE_GAP", 0.01):
        yield


@pytest.fixture
def cached_robot(hass_storage):
    """A device cache from an earlier run: what lets setup go on without the cloud."""
    def _seed(product_id: str = A30_PRO) -> None:
        hass_storage[f"ilife.{ENTRY_ID}"] = {
            "version": 1, "minor_version": 1, "key": f"ilife.{ENTRY_ID}",
            "data": {DEVICE_ID: {
                "device": device(product_id), "local_key": LOCAL_KEY,
                "host": "robot.invalid", "status": dict(A30["status"]),
                "spec": A30["specification"], "model_raw": A30_MODEL}}}
    return _seed
