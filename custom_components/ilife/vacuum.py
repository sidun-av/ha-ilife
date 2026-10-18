"""ILIFE vacuum entity (ILIFEHOME) and ILIFE Clean (Tuya) vacuum entity."""
from __future__ import annotations

import asyncio
import logging

import voluptuous as vol

from homeassistant.components.vacuum import (
    StateVacuumEntity,
    VacuumActivity,
    VacuumEntityFeature,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, entity_platform

try:  # recent Home Assistant (2026.6 has it): native area cleaning
    from homeassistant.components.vacuum import Segment
except ImportError:  # pragma: no cover - older Home Assistant
    Segment = None

from .api import ILifeError, ILifeOfflineError
from .const import (
    BACKEND_ILIFE_CLEAN,
    CLEANING_MODES,
    DOCKED_MODES,
    DOMAIN,
    PAUSED_MODES,
    RETURNING_MODES,
    SUCTION_LEVELS,
    TUYA_DP_FAULT,
    TUYA_DP_LOCATE,
    TUYA_DP_MODE,
    TUYA_DP_PAUSE,
    TUYA_DP_POWER_GO,
    TUYA_DP_STATUS,
    TUYA_DP_SUCTION,
    TUYA_DP_SWITCH,
    TUYA_DP_TOTAL_CLEAN_AREA,
    TUYA_DP_TOTAL_CLEAN_COUNT,
    TUYA_DP_TOTAL_CLEAN_TIME,
    TUYA_MODE_FULL_CLEAN,
    TUYA_STATUS_CLEANING,
    TUYA_STATUS_DOCKED,
    TUYA_STATUS_IDLE,
    TUYA_STATUS_PAUSED,
    TUYA_STATUS_RETURNING,
    TUYA_STOP_HALT_ONLY_PRODUCTS,
    TUYA_SUCTION_NUDGE_PRODUCTS,
    pack_vws,
    suction_label,
)
from .entity import ILifeEntity
from .tuya_api import TuyaCommandUnconfirmed, TuyaError
from .tuya_dynamic import (
    command_for,
    enum_command,
    merge_commands,
    return_commands,
    run_flag,
    suction_detour,
    unpause_flag,
)
from .tuya_entity import TuyaEntity, tuya_command_error
from .tuya_pause import PauseTracker
from .tuya_rooms import (
    CLEAN_ROOMS_CODE,
    MAX_PASSES,
    clean_rooms_value,
    segments_from_rooms,
)
from .tuya_zones import CLEAN_ZONE_CODE, MAX_ZONE_PASSES, MAX_ZONES, clean_zone_value
from .tuya_schedule import (
    EMPTY_SLOT,
    MAX_CYCLES,
    SCHEDULE_CODES,
    build_schedule,
    parse_schedule,
)

_LOGGER = logging.getLogger(__name__)

# Seconds after a start before the suction is re-applied: the robot is off the dock
# and running by then.
SUCTION_NUDGE_DELAY = 10
# Seconds between the detour write and the write back. Each write is answered by a
# status push; back to back, the second could reach the firmware before the first
# took effect, which is the no-op change the nudge exists to avoid. One second is
# a margin over the LAN round trip, not a measured minimum.
SUCTION_NUDGE_GAP = 1

SERVICE_CLEAN_ROOMS = "clean_rooms"
CLEAN_ROOMS_SCHEMA = {
    vol.Required("rooms"): vol.All(cv.ensure_list, [vol.Any(vol.Coerce(int), cv.string)]),
    vol.Optional("passes", default=1): vol.All(vol.Coerce(int), vol.Range(1, MAX_PASSES)),
}
# Field names as the xiaomi-vacuum-map-card sends them: zones in vacuum
# coordinates, which are map cells in the robot frame (camera calibration_points).
SERVICE_CLEAN_ZONE = "clean_zone"
_ZONE = vol.All(vol.ExactSequence([vol.Coerce(float)] * 4, msg="a zone is [x1, y1, x2, y2]"), lambda zone: [round(v) for v in zone])
CLEAN_ZONE_SCHEMA = {
    vol.Required("zone"): vol.All(cv.ensure_list, vol.Length(1, MAX_ZONES), [_ZONE]),
    vol.Optional("repeats", default=1): vol.All(vol.Coerce(int), vol.Range(1, MAX_ZONE_PASSES)),
}
SERVICE_SET_SCHEDULE = "set_schedule"
SERVICE_DELETE_SCHEDULE = "delete_schedule"
_SLOT = vol.All(vol.Coerce(int), vol.Range(1, len(SCHEDULE_CODES)))
SET_SCHEDULE_SCHEMA = {
    # No slot: a new schedule in the first free one.
    vol.Optional("slot"): _SLOT,
    vol.Optional("time"): cv.string,
    vol.Optional("days"): vol.All(cv.ensure_list, [vol.All(vol.Coerce(int), vol.Range(0, 6))]),
    vol.Optional("enabled"): cv.boolean,
    # [] = whole home; names as in the app, or room numbers.
    vol.Optional("rooms"): vol.All(cv.ensure_list, [vol.Any(vol.Coerce(int), cv.string)]),
    vol.Optional("cycles"): vol.All(vol.Coerce(int), vol.Range(1, MAX_CYCLES)),
}
DELETE_SCHEDULE_SCHEMA = {vol.Required("slot"): _SLOT}


async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    if data.get("backend") == BACKEND_ILIFE_CLEAN:
        async_add_entities(TuyaVacuum(c) for c in data["coordinators"].values())
    else:
        async_add_entities(ILifeVacuum(c) for c in data["coordinators"].values())
    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_CLEAN_ROOMS, CLEAN_ROOMS_SCHEMA, "async_clean_rooms")
    platform.async_register_entity_service(
        SERVICE_CLEAN_ZONE, CLEAN_ZONE_SCHEMA, "async_clean_zone")
    platform.async_register_entity_service(
        SERVICE_SET_SCHEDULE, SET_SCHEDULE_SCHEMA, "async_set_schedule")
    platform.async_register_entity_service(
        SERVICE_DELETE_SCHEDULE, DELETE_SCHEDULE_SCHEMA, "async_delete_schedule")


class ILifeVacuum(ILifeEntity, StateVacuumEntity):
    _attr_name = None  # main entity: uses the device name
    _attr_supported_features = (
        VacuumEntityFeature.START
        | VacuumEntityFeature.PAUSE
        | VacuumEntityFeature.STOP
        | VacuumEntityFeature.RETURN_HOME
        | VacuumEntityFeature.FAN_SPEED
        | VacuumEntityFeature.STATE
        | VacuumEntityFeature.LOCATE
    )
    _attr_fan_speed_list = list(SUCTION_LEVELS)

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = f"{self.api.iot_id}_vacuum"

    @property
    def activity(self):
        wm = (self.coordinator.data or {}).get("WorkMode")
        if wm in CLEANING_MODES:
            return VacuumActivity.CLEANING
        if wm in RETURNING_MODES:
            return VacuumActivity.RETURNING
        if wm in DOCKED_MODES:
            return VacuumActivity.DOCKED
        if wm in PAUSED_MODES:
            return VacuumActivity.PAUSED
        return VacuumActivity.IDLE

    @property
    def fan_speed(self):
        return suction_label((self.coordinator.data or {}).get("VacWateState"))

    async def _cmd(self, fn, *args):
        try:
            await self.hass.async_add_executor_job(fn, *args)
        except ILifeOfflineError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="device_offline"
            ) from err
        except ILifeError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_request_refresh()

    async def async_start(self):
        await self._cmd(self.api.work_mode, self.coordinator.clean_mode)

    async def async_pause(self):
        await self._cmd(self.api.work_mode, 12)

    async def async_stop(self, **kwargs):
        await self._cmd(self.api.work_mode, 2)

    async def async_return_to_base(self, **kwargs):
        await self._cmd(self.api.work_mode, 8)

    async def async_locate(self, **kwargs):
        await self._cmd(self.api.set_prop, "FindRobot", 1, 1)

    async def async_set_fan_speed(self, fan_speed, **kwargs):
        if fan_speed not in SUCTION_LEVELS:
            return
        cur = (self.coordinator.data or {}).get("VacWateState")
        await self._cmd(self.api.set_prop, "VacWateState", pack_vws(cur, suction=fan_speed), None, False)

    def _unsupported(self, action):
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="ilife_clean_only",
            translation_placeholders={"action": action},
        )

    async def async_clean_rooms(self, rooms, passes=1):
        self._unsupported("clean rooms")

    async def async_clean_zone(self, zone, repeats=1):
        self._unsupported("clean zone")

    async def async_set_schedule(self, **kwargs):
        self._unsupported("set schedule")

    async def async_delete_schedule(self, slot):
        self._unsupported("delete schedule")


def _unconfirmed(err: HomeAssistantError) -> bool:
    """The error stands for a command that most likely ran (its ack was lost)."""
    return isinstance(err.__cause__, TuyaCommandUnconfirmed)


class TuyaVacuum(TuyaEntity, StateVacuumEntity):
    """ILIFE Clean (Tuya) vacuum. Features/commands are derived from the device's own
    live /specifications response — nothing here assumes a DP the device didn't advertise."""

    _attr_name = None
    # the name stays the device's; the key only names the fan_speed values
    _attr_translation_key = "vacuum"

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = f"{self.api.device_id}_vacuum"
        functions = coordinator.spec_functions

        # Each action is resolved once, against this device's own spec, into the list of
        # data points to write for it. A feature is advertised only when there is a
        # command to back it.
        #
        # The run flag and the pause flag are written **together**, in one Tuya command.
        # That is not belt and braces: ILIFE firmware ignores `power_go` on its own
        # (v0.6.0 sent exactly that, Tuya accepted it, and three vacuums did nothing —
        # #3, #23, #24), while tuya-local drives the same robots locally by always
        # writing both flags in the same frame, and works. Home Assistant's own Tuya
        # integration sends `power_go` alone, so it has the same blind spot.
        run = run_flag(functions)
        halt = command_for(functions, TUYA_DP_POWER_GO, "stop", "standby", "idle",
                           boolean=False) \
            or command_for(functions, TUYA_DP_SWITCH, "stop", "standby", "idle",
                           boolean=False)
        # Never derive pause from a Boolean power_go: false there means stop, not pause.
        hold = command_for(functions, TUYA_DP_PAUSE, "pause", boolean=True) \
            or enum_command(functions, TUYA_DP_POWER_GO, "pause")
        unhold = unpause_flag(functions)
        full_clean = enum_command(functions, TUYA_DP_MODE, *TUYA_MODE_FULL_CLEAN)

        # Each list is mode first, then the run flag, then the pause flag.
        #
        # START means "clean the place", so it asks for the full-clean mode as well:
        # writing `mode` is what demonstrably starts these robots (#24), and a device
        # left in `part`/`zone` would otherwise answer Start with a spot clean. The
        # Cleaning mode select remains the way to ask for those.
        #
        # Each action only exists if something can really perform it. In particular
        # PAUSE requires a genuine pause data point: a Boolean `power_go` set to false
        # means stop, and offering that as pause would quietly lose the user's place.
        self._cmd_start = (merge_commands(full_clean, run, unhold)
                           if (full_clean or run) else [])
        self._cmd_resume = merge_commands(unhold, run) if (run or unhold) else []
        self._cmd_pause = merge_commands(hold, halt) if hold else []
        # STOP is the halt, with the pause flag cleared so the robot is not left
        # paused; on the models in TUYA_STOP_HALT_ONLY_PRODUCTS it is the halt alone,
        # whatever `pause` reads: there `pause: false` means "carry on", and a stop
        # that sent it resumed the clean on the second press.
        product_id = str(self.api.device.get("product_id") or "")
        if product_id in TUYA_STOP_HALT_ONLY_PRODUCTS:
            self._cmd_stop = merge_commands(halt) if halt else []
        else:
            self._cmd_stop = merge_commands(halt, unhold) if halt else []
        self._cmd_return = return_commands(functions)
        self._cmd_locate = merge_commands(
            command_for(functions, TUYA_DP_LOCATE, "seek", boolean=True))
        # Suction is the fan speed every ILIFE Clean model advertises; exposing it as
        # the vacuum's own fan_speed is what the Lovelace card (and HA's stock vacuum
        # card) drive, instead of a nameless generic select nothing knows about.
        # The thing model may accept more than the spec (A30 Pro: "closed", for
        # mopping only); coordinator.async_write routes those values accordingly.
        self._suction_range = [str(v) for v in coordinator.enum_range(TUYA_DP_SUCTION)]

        features = VacuumEntityFeature.STATE
        if self._cmd_start:
            features |= VacuumEntityFeature.START
        if self._cmd_stop:
            features |= VacuumEntityFeature.STOP
        if self._cmd_pause:
            features |= VacuumEntityFeature.PAUSE
        if self._cmd_return:
            features |= VacuumEntityFeature.RETURN_HOME
        if self._cmd_locate:
            features |= VacuumEntityFeature.LOCATE
        if self._suction_range:
            features |= VacuumEntityFeature.FAN_SPEED
            self._attr_fan_speed_list = self._suction_range
        self._attr_supported_features = features
        self._pause = PauseTracker(TUYA_STATUS_CLEANING)
        # The suction nudge (see _reassert_suction): only on the models known to
        # need it, one at a time, cancelled by any later run command.
        self._suction_nudge = product_id in TUYA_SUCTION_NUDGE_PRODUCTS
        self._nudge_task = None
        self._nudge_writing = False

    @property
    def supported_features(self):
        features = self._attr_supported_features
        # Rooms come with the product properties, which can arrive after setup.
        clean_area = getattr(VacuumEntityFeature, "CLEAN_AREA", None)
        if clean_area is not None and Segment is not None \
                and self.coordinator.supports_room_clean:
            features |= clean_area
        return features

    async def async_will_remove_from_hass(self) -> None:
        self._cancel_nudge(force=True)
        await super().async_will_remove_from_hass()

    def _handle_coordinator_update(self) -> None:
        data = self.coordinator.data or {}
        power_go = data.get(TUYA_DP_POWER_GO)
        self._pause.on_status(data.get(TUYA_DP_STATUS),
                              power_go if isinstance(power_go, bool) else None)
        super()._handle_coordinator_update()

    @property
    def activity(self):
        data = self.coordinator.data or {}
        status = data.get(TUYA_DP_STATUS)
        if isinstance(status, str):
            s = status.lower()
            # A pause sent over the LAN leaves the robot in plain `standby`.
            if s == "standby" and self._pause.paused_by_us():
                return VacuumActivity.PAUSED
            if s in TUYA_STATUS_DOCKED:
                return VacuumActivity.DOCKED
            if s in TUYA_STATUS_RETURNING:
                return VacuumActivity.RETURNING
            if s in TUYA_STATUS_PAUSED:
                return VacuumActivity.PAUSED
            if s in TUYA_STATUS_IDLE:
                return VacuumActivity.IDLE
            if s in TUYA_STATUS_CLEANING:
                return VacuumActivity.CLEANING
            # An unrecognised status used to mean "cleaning", which reported a docked
            # vacuum as cleaning for good. Charging is the value models rename most, so
            # try that, then believe the run flags over a guess.
            if "charg" in s or "dock" in s:
                return VacuumActivity.DOCKED
        if data.get(TUYA_DP_PAUSE) is True:
            return VacuumActivity.PAUSED
        if data.get(TUYA_DP_POWER_GO) is True or data.get(TUYA_DP_SWITCH) is True:
            return VacuumActivity.CLEANING
        return VacuumActivity.IDLE

    @property
    def fan_speed(self):
        v = (self.coordinator.data or {}).get(TUYA_DP_SUCTION)
        return None if v is None else str(v)

    def _tuya_attributes(self):
        data = self.coordinator.data or {}
        attrs = {}
        fault = data.get(TUYA_DP_FAULT)
        if fault:
            attrs["fault"] = fault
        for key, code in (
            ("total_clean_count", TUYA_DP_TOTAL_CLEAN_COUNT),
            ("total_clean_area", TUYA_DP_TOTAL_CLEAN_AREA),
            ("total_clean_time", TUYA_DP_TOTAL_CLEAN_TIME),
        ):
            value = data.get(code)
            if value is not None:
                attrs[key] = value
        return attrs

    async def _send_many(self, commands, pause=False):
        """Send through the coordinator (LAN first, else cloud).

        Only a LAN pause of a running clean is tracked (the cloud path keeps the
        v0.7.1 behaviour). It is armed before the send, because the robot's
        answering push can beat the acknowledgement; any other command ends a
        tracked pause only once it went through. A command whose acknowledgement
        was lost (TuyaCommandUnconfirmed) has most likely run, so it counts as
        sent here: the user is still told it was not confirmed."""
        before = self._pause.snapshot()
        if pause and self.activity == VacuumActivity.CLEANING \
                and self.coordinator.local_connected:
            self._pause.on_pause_sent()
        _LOGGER.debug("ILIFE Clean %s: sending %s (%s)", self.api.device_id, commands,
                      "local" if self.coordinator.local_connected else "cloud")
        try:
            await self.coordinator.async_send(commands)
        except TuyaCommandUnconfirmed as err:
            self._after_send(pause)
            raise tuya_command_error(err) from err
        except TuyaError as err:
            self._after_failed_send(before, pause)
            raise tuya_command_error(err) from err
        self._after_send(pause)

    def _after_send(self, pause) -> None:
        """A pause stays armed (see _send_many); any other command ends a pause."""
        if not pause:
            self._pause.on_command_sent()

    def _after_failed_send(self, before, pause) -> None:
        """A failed pause leaves nothing paused; any other failed command leaves a
        real pause in place (the robot never got it)."""
        if pause:
            self._pause.on_command_sent()
        else:
            self._pause.restore(before)

    async def _run(self, commands, action, pause=False):
        if not commands:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="command_unsupported",
                translation_placeholders={
                    "action": action,
                    "device": self.api.device.get("product_name") or "this vacuum",
                },
            )
        await self._send_many(commands, pause=pause)

    @property
    def _is_paused(self):
        data = self.coordinator.data or {}
        if data.get(TUYA_DP_PAUSE) is True or self.activity == VacuumActivity.PAUSED:
            return True
        return str(data.get(TUYA_DP_STATUS) or "").lower() in TUYA_STATUS_PAUSED

    async def async_start(self):
        # Resuming a paused clean must not restart it from scratch, which asking for
        # the full-clean mode again would do.
        if self._is_paused and self._cmd_resume:
            await self._send_many(self._cmd_resume)
            return
        try:
            await self._run(self._cmd_start, "start")
        except HomeAssistantError as err:
            if _unconfirmed(err):
                # Most likely started: the nudge itself checks that it runs.
                self._reassert_suction()
            raise
        self._reassert_suction()

    def _reassert_suction(self) -> None:
        """Make the fan really run at the level the robot reports, once it is off.

        An A30 Pro started cleans with its fan at the lowest level while reporting
        "strong", and writing "strong" again was a no-op; changing the level away and
        back fixed it at once. So after a start, step through another level and back,
        on the models in TUYA_SUCTION_NUDGE_PRODUCTS only. It runs in the background,
        tied to the config entry so an unload cancels it: the start itself has
        already gone through."""
        if not self._suction_nudge:
            return
        if self._nudge_writing:
            # The previous one is between its two writes: let it set the level back.
            return
        self._cancel_nudge()
        wanted = self.fan_speed
        detour = suction_detour(self._suction_range, wanted)
        if detour is None:
            return
        self._nudge_task = self.coordinator.config_entry.async_create_background_task(
            self.hass, self._async_nudge_suction(wanted, detour),
            f"{DOMAIN} {self.api.device_id} suction nudge")

    def _cancel_nudge(self, *, force: bool = False) -> None:
        """Drop a pending nudge. One already between its two writes is left to
        finish unless `force` (removal), or the fan would stay on the detour."""
        task = self._nudge_task
        if task is None or task.done() or (self._nudge_writing and not force):
            return
        self._nudge_task = None
        task.cancel()

    async def _async_nudge_suction(self, wanted, detour) -> None:
        try:
            await asyncio.sleep(SUCTION_NUDGE_DELAY)
            # Stopped, paused, docked, or the start was refused (a fault, a full
            # bin): there is no running fan to fix.
            if self.activity != VacuumActivity.CLEANING:
                return
            # The user may have changed it meanwhile: theirs wins.
            if self.fan_speed != wanted:
                return
            self._nudge_writing = True
            try:
                await self.coordinator.async_write(TUYA_DP_SUCTION, detour)
            except TuyaCommandUnconfirmed as err:
                # Most likely on the detour level now: set it back all the same.
                _LOGGER.debug("ILIFE Clean %s: suction detour %s unconfirmed (%s)",
                              self.api.device_id, detour, err)
            await asyncio.sleep(SUCTION_NUDGE_GAP)
            try:
                await self.coordinator.async_write(TUYA_DP_SUCTION, wanted)
            except TuyaCommandUnconfirmed:
                # Most likely set back; writing it again could only repeat that.
                pass
            except TuyaError as err:
                # Left as it is, the fan would run on the detour level: once more.
                _LOGGER.debug("ILIFE Clean %s: suction %s not set back (%s), retrying",
                              self.api.device_id, wanted, err)
                await asyncio.sleep(SUCTION_NUDGE_GAP)
                await self.coordinator.async_write(TUYA_DP_SUCTION, wanted)
        except TuyaError as err:
            _LOGGER.warning("ILIFE Clean %s: could not re-apply suction %s: %s",
                            self.api.device_id, wanted, err)
        finally:
            self._nudge_writing = False

    async def async_pause(self):
        self._cancel_nudge()
        await self._run(self._cmd_pause, "pause", pause=True)

    async def async_stop(self, **kwargs):
        self._cancel_nudge()
        await self._run(self._cmd_stop, "stop")

    async def async_return_to_base(self, **kwargs):
        self._cancel_nudge()
        await self._run(self._cmd_return, "return to base")

    async def async_locate(self, **kwargs):
        await self._run(self._cmd_locate, "locate")

    async def async_set_fan_speed(self, fan_speed, **kwargs):
        if fan_speed not in self._suction_range:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="fan_speed_unsupported",
                translation_placeholders={
                    "fan_speed": str(fan_speed),
                    "options": ", ".join(self._suction_range) or "none",
                },
            )
        await self._write(TUYA_DP_SUCTION, fan_speed)

    @property
    def extra_state_attributes(self):
        attrs = self._tuya_attributes()
        if self.coordinator.room_names:
            attrs["rooms"] = self.coordinator.room_names
        return attrs

    def _room_id(self, room) -> int:
        """A room given by id or by its name in the app (case-insensitive)."""
        names = self.coordinator.room_names
        if isinstance(room, int) or str(room).strip().isdigit():
            return int(room)
        wanted = str(room).strip().casefold()
        for room_id, name in names.items():
            if name.casefold() == wanted:
                return room_id
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="room_unknown",
            translation_placeholders={
                "room": str(room),
                "rooms": ", ".join(f"{name} ({room_id})" for room_id, name in
                                   sorted(names.items())) or "none",
            },
        )

    async def async_clean_rooms(self, rooms, passes=1):
        """Clean the given rooms, each `passes` times (2 adds a crosswise pass)."""
        if not self.coordinator.supports_room_clean:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="command_unsupported",
                translation_placeholders={
                    "action": "clean rooms",
                    "device": self.api.device.get("product_name") or "this vacuum",
                },
            )
        try:
            value = clean_rooms_value([self._room_id(room) for room in rooms], passes)
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err
        await self._write_run(CLEAN_ROOMS_CODE, value)

    async def async_clean_zone(self, zone, repeats=1):
        """Clean rectangles [x1, y1, x2, y2] in map cells (robot frame, y up)."""
        if not self.coordinator.supports_zone_clean:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="command_unsupported",
                translation_placeholders={
                    "action": "clean zone",
                    "device": self.api.device.get("product_name") or "this vacuum",
                },
            )
        try:
            value = clean_zone_value([tuple(z) for z in zone], repeats)
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err
        await self._write_run(CLEAN_ZONE_CODE, value)

    async def async_get_segments(self):
        """The rooms of the vacuum's map, for Home Assistant's area cleaning.

        Mapped rooms come from the map camera: while it is disabled or has not
        rendered yet, only the rooms named in the app are offered."""
        return [Segment(id=segment_id, name=name)
                for segment_id, name in segments_from_rooms(
                    self.coordinator.room_names, self.coordinator.map_rooms)]

    async def async_clean_segments(self, segment_ids, **kwargs):
        try:
            rooms = [int(segment_id) for segment_id in segment_ids]
        except ValueError as err:
            raise HomeAssistantError(f"unknown segment in {segment_ids}") from err
        await self.async_clean_rooms(rooms)

    async def _write(self, code, value):
        try:
            await self.coordinator.async_write(code, value)
        except TuyaError as err:
            raise tuya_command_error(err) from err

    async def _write_run(self, code, value):
        """A room or zone clean: a new run, so it ends a pause and gets the suction
        nudge, also when its acknowledgement was lost (it most likely started)."""
        try:
            await self._write(code, value)
        except HomeAssistantError as err:
            if _unconfirmed(err):
                self._pause.on_command_sent()
                self._reassert_suction()
            raise
        self._pause.on_command_sent()
        self._reassert_suction()

    async def async_set_schedule(self, slot=None, time=None, days=None, enabled=None,
                                 rooms=None, cycles=None):
        """Create a schedule (no slot) or change the given fields of one."""
        properties = self.coordinator.properties
        if slot is None:
            slot = next((n for n, code in enumerate(SCHEDULE_CODES, start=1)
                         if code in properties
                         and parse_schedule(properties.get(code)) is None), None)
            if slot is None and any(code in properties for code in SCHEDULE_CODES):
                raise HomeAssistantError("all schedule slots are in use")
        self._check_schedule_slot(slot, "set schedule")
        code = SCHEDULE_CODES[slot - 1]
        existing = properties.get(code)
        if parse_schedule(existing) is None and (time is None or not days):
            raise HomeAssistantError("a new schedule needs a time and at least one day")
        try:
            value = build_schedule(
                existing, time=time, days=days, enabled=enabled, cycles=cycles,
                rooms=None if rooms is None else [self._room_id(room) for room in rooms],
            )
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err
        await self._write(code, value)

    async def async_delete_schedule(self, slot):
        self._check_schedule_slot(slot, "delete schedule")
        await self._write(SCHEDULE_CODES[slot - 1], EMPTY_SLOT)

    def _check_schedule_slot(self, slot, action):
        """Only write a schedule slot this vacuum actually reports."""
        if slot is None or SCHEDULE_CODES[slot - 1] not in self.coordinator.properties:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="command_unsupported",
                translation_placeholders={
                    "action": action,
                    "device": self.api.device.get("product_name") or "this vacuum",
                },
            )
