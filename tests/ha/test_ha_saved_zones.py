"""Saved zones in a real Home Assistant: the services, the per-zone button and the
vacuum's `saved_zones` attribute, across a reload."""
from __future__ import annotations

import asyncio

import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from custom_components.ilife.saved_zones import zone_key
from custom_components.ilife.tuya_zones import CLEAN_ZONE_CODE, clean_zone_value
from harness import DEVICE_ID, FakeLink, entity_id, make_entry

KITCHEN = [[8, -79, 58, -36]]


async def _setup_lan(hass, cached_robot):
    cached_robot()
    entry = make_entry(hass, local=True)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry, FakeLink.instances[-1]


async def _save(hass, name, zone, repeats=1):
    await hass.services.async_call("ilife", "save_zone", {
        "entity_id": entity_id(hass, "vacuum"), "name": name, "zone": zone, "repeats": repeats},
        blocking=True)
    await hass.async_block_till_done()


def _button(hass, name):
    return er.async_get(hass).async_get_entity_id("button", "ilife", f"{DEVICE_ID}_zone_{zone_key(name)}")


async def test_save_adds_a_button_and_the_attribute(hass, cached_robot):
    await _setup_lan(hass, cached_robot)
    await _save(hass, "Угол кухни", KITCHEN)
    assert _button(hass, "Угол кухни")
    attrs = hass.states.get(entity_id(hass, "vacuum")).attributes
    assert attrs["saved_zones"] == {"Угол кухни": {"zone": KITCHEN, "repeats": 1}}
    state = hass.states.get(_button(hass, "Угол кухни"))
    assert state.attributes["zone_name"] == "Угол кухни"


async def test_pressing_the_button_cleans_the_zone_with_the_nudge(hass, cached_robot):
    _entry, link = await _setup_lan(hass, cached_robot)
    await _save(hass, "Угол кухни", KITCHEN, repeats=2)
    await hass.services.async_call(
        "button", "press", {"entity_id": _button(hass, "Угол кухни")}, blocking=True)
    link.push(status="zone_clean", power_go=True)   # what the robot answers a zone write
    await asyncio.sleep(0.15)                       # the nudge, patched to milliseconds
    await hass.async_block_till_done()
    zone_writes = [f for f in link.frames if CLEAN_ZONE_CODE in f]
    assert zone_writes == [{CLEAN_ZONE_CODE: clean_zone_value([tuple(KITCHEN[0])], 2)}]
    assert [f for f in link.frames if "suction" in f] == [{"suction": "normal"}, {"suction": "strong"}]


async def test_saving_the_same_name_replaces_it(hass, cached_robot):
    await _setup_lan(hass, cached_robot)
    await _save(hass, "Угол", KITCHEN)
    first = _button(hass, "Угол")
    await _save(hass, "  Угол ", [[0, 0, 10, 10]], repeats=2)
    assert _button(hass, "Угол") == first
    attrs = hass.states.get(entity_id(hass, "vacuum")).attributes
    assert attrs["saved_zones"] == {"Угол": {"zone": [[0, 0, 10, 10]], "repeats": 2}}


async def test_delete_removes_the_button(hass, cached_robot):
    await _setup_lan(hass, cached_robot)
    await _save(hass, "Угол", KITCHEN)
    button = _button(hass, "Угол")
    await hass.services.async_call("ilife", "delete_zone", {
        "entity_id": entity_id(hass, "vacuum"), "name": "Угол"}, blocking=True)
    await hass.async_block_till_done()
    assert _button(hass, "Угол") is None
    assert hass.states.get(button) is None
    assert "saved_zones" not in hass.states.get(entity_id(hass, "vacuum")).attributes
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call("ilife", "delete_zone", {
            "entity_id": entity_id(hass, "vacuum"), "name": "Угол"}, blocking=True)


async def test_a_bad_zone_is_refused(hass, cached_robot):
    await _setup_lan(hass, cached_robot)
    with pytest.raises(HomeAssistantError):
        await _save(hass, "   ", KITCHEN)
    assert "saved_zones" not in hass.states.get(entity_id(hass, "vacuum")).attributes


async def test_saved_zones_survive_a_reload(hass, cached_robot):
    entry, _link = await _setup_lan(hass, cached_robot)
    await _save(hass, "Угол кухни", KITCHEN)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(_button(hass, "Угол кухни")) is not None
    attrs = hass.states.get(entity_id(hass, "vacuum")).attributes
    assert attrs["saved_zones"] == {"Угол кухни": {"zone": KITCHEN, "repeats": 1}}
