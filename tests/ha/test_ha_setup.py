"""Setup, its cloud-less fallbacks and entity availability, in a real Home Assistant."""
from __future__ import annotations

import logging
from unittest.mock import patch

from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.helpers.translation import async_get_translations

from harness import FakeClient, FakeLink, _noop, coordinator, entity_id, make_entry


async def _setup(hass, entry) -> None:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _state(hass, domain, key=None):
    return hass.states.get(entity_id(hass, domain, key)).state


async def test_setup_in_russian(hass, caplog):
    """A normal cloud setup: entities carry their translated names, the sensors their
    device classes, and Home Assistant's platforms log no entity warnings."""
    caplog.set_level(logging.WARNING)
    hass.config.language = "ru"
    entry = make_entry(hass, local=False)
    await _setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED
    dnd = hass.states.get(entity_id(hass, "switch", "switch_disturb"))
    assert dnd.attributes["friendly_name"].endswith("Не беспокоить")
    water = hass.states.get(entity_id(hass, "select", "cistern"))
    assert water.attributes["friendly_name"].endswith("Подача воды")
    total_area = hass.states.get(entity_id(hass, "sensor", "total_area"))
    assert total_area.attributes.get("device_class") == "area"
    translations = await async_get_translations(hass, "ru", "entity", ["ilife"])
    assert any("fan_speed.state" in key for key in translations)
    # E.g. a device class / state class / unit mismatch, logged by the platforms.
    assert not [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING
                and r.name.startswith(("homeassistant.components.", "homeassistant.helpers."))]
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_expired_trial_lan_answer_first_keeps_entities_available(
        hass, cached_robot):
    """An expired trial at startup, with the LAN answering before the cloud call
    fails (the usual order): the entities stay available and controllable instead
    of waiting for the robot's next push, and a reauth flow is offered."""
    FakeClient.auth_fail = True
    cached_robot()
    entry = make_entry(hass)
    await _setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED
    assert coordinator(hass).local_connected
    assert coordinator(hass).last_update_success
    assert _state(hass, "vacuum") == "docked"
    assert _state(hass, "switch", "switch_disturb") == "off"
    assert _state(hass, "switch", "dust_collection_switch") == "off"
    flows = hass.config_entries.flow.async_progress_by_handler("ilife")
    reauth = [f for f in flows if f["context"]["source"] == SOURCE_REAUTH]
    assert reauth and reauth[0]["step_id"] == "reauth_confirm_tuya"

    # The trial renewed: the reauth form reloads the entry with the cloud back.
    FakeClient.auth_fail = False
    with patch("custom_components.ilife.config_flow._validate_ilife_clean", _noop):
        result = await hass.config_entries.flow.async_configure(
            reauth[0]["flow_id"], {"access_id": "id", "access_secret": "renewed"})
        await hass.async_block_till_done()
    assert result["type"] == "abort" and result["reason"] == "reauth_successful"
    assert entry.state is ConfigEntryState.LOADED
    assert entry.data["access_secret"] == "renewed"
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_cloud_down_lan_answer_first_keeps_entities_available(hass, cached_robot):
    FakeClient.down = True
    cached_robot()
    entry = make_entry(hass)
    await _setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED
    assert _state(hass, "vacuum") == "docked"
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_dead_robot_and_dead_cloud_end_up_unavailable(hass, cached_robot):
    """Keeping the data while the link is up must not hide a robot that is gone."""
    FakeClient.auth_fail = True
    FakeLink.answers = False
    cached_robot()
    entry = make_entry(hass)
    await _setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED
    assert not coordinator(hass).local_connected
    assert _state(hass, "vacuum") == STATE_UNAVAILABLE
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_link_dropping_with_the_cloud_dead_makes_entities_unavailable(
        hass, cached_robot):
    FakeClient.auth_fail = True
    cached_robot()
    entry = make_entry(hass)
    await _setup(hass, entry)
    assert _state(hass, "vacuum") == "docked"
    FakeLink.instances[-1].drop()  # the robot went silent
    await hass.async_block_till_done()
    assert not coordinator(hass).last_update_success
    assert _state(hass, "vacuum") == STATE_UNAVAILABLE
    assert await hass.config_entries.async_unload(entry.entry_id)
