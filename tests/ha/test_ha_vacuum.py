"""The vacuum's command paths in a real Home Assistant: Stop per model, the suction
nudge, and commands whose LAN acknowledgement was lost."""
from __future__ import annotations

import asyncio

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.ilife.tuya_local import TuyaLocalTimeout
from harness import FakeClient, FakeLink, coordinator, entity_id, make_entry


async def _setup(hass, *, local: bool):
    entry = make_entry(hass, local=local)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _setup_lan(hass, cached_robot):
    """Cloud fine, link up from the start (a cached host and key)."""
    cached_robot()
    entry = await _setup(hass, local=True)
    assert coordinator(hass).local_connected
    return entry, FakeLink.instances[-1]


async def _vacuum(hass, service, **data):
    await hass.services.async_call(
        "vacuum", service, {"entity_id": entity_id(hass, "vacuum"), **data}, blocking=True)


async def _settle(hass) -> None:
    """Long enough for a pending suction nudge (patched to milliseconds) to finish."""
    await asyncio.sleep(0.15)
    await hass.async_block_till_done()


def _nudge_tasks(entry):
    return [t for t in entry._background_tasks if "suction nudge" in t.get_name()]


# -- Stop ------------------------------------------------------------------------ #

async def test_a30_pro_stop_is_the_halt_alone(hass):
    await _setup(hass, local=False)
    await _vacuum(hass, "stop")
    assert FakeClient.instances[-1].sent[-1] == [{"code": "power_go", "value": False}]


async def test_other_models_stop_with_the_pause_flag_cleared(hass):
    FakeClient.product_id = "otherproduct0000"
    await _setup(hass, local=False)
    await _vacuum(hass, "stop")
    assert FakeClient.instances[-1].sent[-1] == [
        {"code": "power_go", "value": False}, {"code": "pause", "value": False}]


# -- the suction nudge ----------------------------------------------------------- #

async def test_start_nudges_the_suction_away_and_back(hass, cached_robot):
    entry, link = await _setup_lan(hass, cached_robot)
    await _vacuum(hass, "start")
    assert len(_nudge_tasks(entry)) == 1
    await _settle(hass)
    assert link.frames[1:] == [{"suction": "normal"}, {"suction": "strong"}]


async def test_no_nudge_on_other_models(hass):
    FakeClient.product_id = "otherproduct0000"
    entry = await _setup(hass, local=False)
    await _vacuum(hass, "start")
    assert not _nudge_tasks(entry)


async def test_stop_cancels_a_pending_nudge(hass, cached_robot):
    entry, link = await _setup_lan(hass, cached_robot)
    await _vacuum(hass, "start")
    tasks = _nudge_tasks(entry)
    await _vacuum(hass, "stop")
    await _settle(hass)
    assert tasks and all(t.cancelled() for t in tasks)
    assert not [f for f in link.frames if "suction" in f]


async def test_nudge_sets_the_level_back_after_an_unconfirmed_detour(hass, cached_robot):
    """The detour write's ack was lost: the robot most likely is on the detour
    level, so the wanted level is still written back."""
    _entry, link = await _setup_lan(hass, cached_robot)
    link.errors = [None, TuyaLocalTimeout("no acknowledgement from device")]
    await _vacuum(hass, "start")
    await _settle(hass)
    assert link.frames[1:] == [{"suction": "normal"}, {"suction": "strong"}]
    assert hass.states.get(entity_id(hass, "vacuum")).attributes["fan_speed"] == "strong"


async def test_unconfirmed_start_still_gets_the_nudge(hass, cached_robot):
    _entry, link = await _setup_lan(hass, cached_robot)
    link.errors = [TuyaLocalTimeout("no acknowledgement from device")]
    with pytest.raises(HomeAssistantError) as err:
        await _vacuum(hass, "start")
    assert err.value.translation_key == "local_unconfirmed"
    await _settle(hass)
    assert link.frames[1:] == [{"suction": "normal"}, {"suction": "strong"}]


def _suction_frames(link):
    return [f for f in link.frames if "suction" in f]


async def test_start_from_the_app_is_nudged_too(hass, cached_robot):
    """A clean started outside Home Assistant (app, schedule, the robot's button)
    has the same weak fan: the robot leaving the dock to clean gets the nudge."""
    entry, link = await _setup_lan(hass, cached_robot)
    link.push(status="smart", power_go=True)
    await hass.async_block_till_done()
    assert len(_nudge_tasks(entry)) == 1
    await _settle(hass)
    assert _suction_frames(link) == [{"suction": "normal"}, {"suction": "strong"}]


async def test_start_from_home_assistant_is_nudged_once(hass, cached_robot):
    """Our own start nudges itself; the status it brings back is not a second start,
    not even when it only shows with a later update."""
    _entry, link = await _setup_lan(hass, cached_robot)
    await _vacuum(hass, "start")
    link.push(status="standby", power_go=False)   # a status blip, then cleaning again
    link.push(status="smart", power_go=True)
    await hass.async_block_till_done()
    await _settle(hass)
    assert _suction_frames(link) == [{"suction": "normal"}, {"suction": "strong"}]


async def test_resume_after_a_pause_is_not_nudged(hass, cached_robot):
    """A resume carries on the same run; only a new clean gets the nudge."""
    _entry, link = await _setup_lan(hass, cached_robot)
    link.push(status="smart", power_go=True)
    await hass.async_block_till_done()
    await _settle(hass)
    nudged = len(_suction_frames(link))
    link.push(status="paused", pause=True)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id(hass, "vacuum")).state == "paused"
    link.push(status="smart", pause=False)
    await hass.async_block_till_done()
    await _settle(hass)
    assert len(_suction_frames(link)) == nudged == 2


async def test_cleaning_at_setup_is_not_nudged(hass, cached_robot):
    """Already cleaning when Home Assistant starts: how the run began is unknown."""
    cached_robot()
    FakeLink.initial = {"status": "smart", "power_go": True}
    try:
        entry = await _setup(hass, local=True)
    finally:
        FakeLink.initial = {}
    link = FakeLink.instances[-1]
    await _settle(hass)
    assert not _nudge_tasks(entry)
    assert not _suction_frames(link)


async def test_app_start_on_other_models_is_left_alone(hass, cached_robot):
    cached_robot("otherproduct0000")
    FakeClient.product_id = "otherproduct0000"
    entry = await _setup(hass, local=True)
    link = FakeLink.instances[-1]
    link.push(status="smart", power_go=True)
    await hass.async_block_till_done()
    await _settle(hass)
    assert not _nudge_tasks(entry)
    assert not _suction_frames(link)


# -- a pause whose acknowledgement was lost --------------------------------------- #

async def test_unconfirmed_pause_stays_a_pause(hass, cached_robot):
    """The robot paused (plain standby over the LAN) but its ack was lost: the
    entity still shows paused, and Start resumes instead of a new full clean."""
    _entry, link = await _setup_lan(hass, cached_robot)
    link.push(status="smart", power_go=True)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id(hass, "vacuum")).state == "cleaning"

    link.errors = [TuyaLocalTimeout("no acknowledgement from device")]
    with pytest.raises(HomeAssistantError) as err:
        await _vacuum(hass, "pause")
    assert err.value.translation_key == "local_unconfirmed"
    await hass.async_block_till_done()
    assert hass.states.get(entity_id(hass, "vacuum")).state == "paused"

    await _vacuum(hass, "start")
    resume = link.frames[-1]
    assert resume == {"pause": False, "power_go": True}, resume  # no `mode`: not a restart


async def test_refused_pause_is_not_tracked(hass, cached_robot):
    """A refusal means it did not run: nothing is left paused."""
    from custom_components.ilife.tuya_local import TuyaLocalRefused

    _entry, link = await _setup_lan(hass, cached_robot)
    link.push(status="smart", power_go=True)
    await hass.async_block_till_done()
    link.errors = [TuyaLocalRefused(1)]
    with pytest.raises(HomeAssistantError) as err:
        await _vacuum(hass, "pause")
    assert err.value.translation_key == "local_refused"
    assert hass.states.get(entity_id(hass, "vacuum")).state == "cleaning"
    # The refusal is the robot's answer: the cloud is not asked to relay it.
    assert not [c for c in FakeClient.instances[-1].sent if "pause" in str(c)]


# -- Charging -------------------------------------------------------------------- #

async def test_status_and_charging_attributes(hass, cached_robot):
    """The card tells charging from a full battery by the robot's own status."""
    _entry, link = await _setup_lan(hass, cached_robot)
    link.push(status="base_charging")
    await hass.async_block_till_done()
    state = hass.states.get(entity_id(hass, "vacuum"))
    assert state.attributes["status"] == "base_charging"
    assert state.attributes["charging"] is True
    link.push(status="charge_done")
    await hass.async_block_till_done()
    state = hass.states.get(entity_id(hass, "vacuum"))
    assert state.attributes["charging"] is False
