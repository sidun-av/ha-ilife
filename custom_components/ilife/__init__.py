"""ILIFE Vacuum integration (Alibaba IoT cloud)."""
from __future__ import annotations

import asyncio
import logging
import os
import time as _time  # aliased: a sibling submodule is named time.py (TimeEntity platform)
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_EMAIL,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_REGION,
    EVENT_HOMEASSISTANT_STARTED,
    EVENT_HOMEASSISTANT_STOP,
    Platform,
)
from homeassistant.core import CoreState, HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import ILifeAccount, ILifeAuthError, ILifeDevice, ILifeError
from .brands import DEFAULT_BRAND
from .const import (
    BACKEND_ILIFE_CLEAN,
    BACKEND_ILIFEHOME,
    CLEANING_MODES,
    CONF_ACCESS_ID,
    CONF_ACCESS_SECRET,
    CONF_BACKEND,
    CONF_BRAND,
    CONF_LOCAL,
    CONF_UID,
    DEFAULT_START_MODE,
    DOMAIN,
    LOCAL_PROTOCOL,
    TUYA_CATEGORY_VACUUM,
    TUYA_CONSUMABLES,
    TUYA_DP_DUST_FREQUENCY,
    TUYA_DP_RESET_MAP,
    TUYA_DP_STATUS,
    TUYA_DP_VOLUME,
    TUYA_STATUS_CLEANING,
)
from .tuya_api import (
    TuyaAuthError,
    TuyaClient,
    TuyaError,
    TuyaNoDevicesError,
    TuyaVacuum,
    parse_record_extend,
    parse_thing_model,
)
from .tuya_cache import (
    DeviceCache,
    map_rooms_from_cache,
    map_rooms_to_cache,
    pick,
    seed_status,
    status_save_due,
)
from .tuya_dpmap import DpMap, apply_local_dps, merge_cloud_status, split_local_dps
from .tuya_dynamic import parse_functions, range_values
from .tuya_local import (
    TuyaLocalError,
    TuyaLocalLink,
    TuyaLocalRefused,
    TuyaLocalTimeout,
    discover_device,
)
from .tuya_map import clean_map_path, clean_map_thumbnail
from .tuya_rooms import CLEAN_ROOMS_CODE, ROOM_INFO_CODES, parse_room_names
from .tuya_zones import CLEAN_ZONE_CODE
from .tuya_schedule import parse_schedules

_LOGGER = logging.getLogger(__name__)

ILIFEHOME_PLATFORMS = [
    Platform.VACUUM,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SELECT,
    Platform.SWITCH,
    Platform.TIME,
    Platform.CAMERA,
]
ILIFE_CLEAN_PLATFORMS = [
    Platform.VACUUM,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SWITCH,
    Platform.CAMERA,
]
PLATFORMS = ILIFEHOME_PLATFORMS

# ILIFE Clean cleaning history: how many stored maps (one per clean) to list.
HISTORY_SIZE = 10

# While the LAN link is up the cloud is read only for history and product properties.
LOCAL_POLL = timedelta(seconds=300)
CLOUD_POLL = timedelta(seconds=30)
# Look for the robot again after this many failed connection attempts in a row,
# and never more often than this.
REDISCOVER_AFTER_FAILURES = 3
REDISCOVER_EVERY = 120
# Setup with no status at all (cloud down, nothing cached): how long to wait for the
# robot's answer over the LAN before the platforms build their entities.
FIRST_LOCAL_WAIT = 10

CARD_URL = "/ilife_cards/ilife-vacuum-card.js"
CARD_FILENAME = "ilife-vacuum-card.js"


def _is_ilife_card_resource(url: str) -> bool:
    """Recognize both current and legacy/manual ILIFE card resource URLs."""
    base = str(url or "").split("?", 1)[0].rstrip("/")
    return (
        base == CARD_URL
        or base.endswith("/ilife-vacuum-card.js")
        or base.startswith("/ilife_cards/ilife-vacuum-card-")
    )


class ILifeCoordinator(DataUpdateCoordinator):
    """Polls one vacuum's state; also refreshes online status, history and PNG archive."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, device: ILifeDevice) -> None:
        super().__init__(
            hass, _LOGGER, name=f"{DOMAIN}_{device.iot_id}",
            update_interval=timedelta(seconds=30), config_entry=entry,
        )
        self.api = device
        self.clean_mode = DEFAULT_START_MODE
        self.history: list[dict] = []
        self.online: bool | None = None
        self._hist_next = 0.0
        # live map accumulation: RealTimeMap.MapData is only a small rolling window,
        # so we merge successive windows into the full current-clean map.
        self._rtmap_cells: dict[tuple[int, int], int] = {}
        self._rtmap_session: Any = None

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            state = await self.hass.async_add_executor_job(self.api.get_state)
        except ILifeError as err:
            raise UpdateFailed(str(err)) from err
        try:
            self.online = await self.hass.async_add_executor_job(self.api.is_online)
        except Exception:  # noqa: BLE001
            _LOGGER.debug("ILIFE online status unavailable", exc_info=True)
        if _time.monotonic() >= self._hist_next:
            self._hist_next = _time.monotonic() + 300
            try:
                self.history = await self.hass.async_add_executor_job(self.api.clean_history, 20)
                await self.hass.async_add_executor_job(self._archive_maps)
            except Exception:  # noqa: BLE001
                _LOGGER.debug("ILIFE history unavailable", exc_info=True)
        self._merge_rtmap(state)
        return state

    def _merge_rtmap(self, state: dict) -> None:
        """While cleaning, accumulate the rolling RealTimeMap windows into the full
        map and inject it back so the camera renders the whole clean, not a fragment."""
        from .map import decode_cells, encode_cells

        rtm = state.get("RealTimeMap") or {}
        cleaning = state.get("WorkMode") in CLEANING_MODES
        if not cleaning:
            self._rtmap_session = None  # next clean starts a fresh map
            return
        md = rtm.get("MapData")
        if not md:
            return
        session = state.get("RealTimeMapStart")
        if session != self._rtmap_session:
            self._rtmap_session = session
            self._rtmap_cells = {}
        for x, y, t in decode_cells(md):
            self._rtmap_cells[(x, y)] = t
        merged = dict(rtm)
        merged["MapData"] = encode_cells(self._rtmap_cells)
        state["RealTimeMap"] = merged

    def _archive_maps(self) -> None:
        """Save each clean's map as a tiny PNG under www/ilife_maps/ (permanent gallery)."""
        import os

        from .map import render_clean_map_png

        folder = self.hass.config.path("www", "ilife_maps")
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError:
            return
        for c in self.history or []:
            start, cm = c.get("start"), c.get("map")
            if not start or not cm:
                continue
            path = os.path.join(folder, f"{self.api.iot_id}_{start}.png")
            if os.path.exists(path):
                continue
            png = render_clean_map_png(cm)
            if png:
                try:
                    with open(path, "wb") as f:
                        f.write(png)
                except OSError:
                    pass


class ILifeTuyaCoordinator(DataUpdateCoordinator):
    """Polls one ILIFE Clean (Tuya) vacuum's status: {dp_code: value}."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, device: TuyaVacuum,
                 cache: DeviceCache | None = None) -> None:
        super().__init__(
            hass, _LOGGER, name=f"{DOMAIN}_{device.device_id}",
            update_interval=timedelta(seconds=30), config_entry=entry,
        )
        self.api = device
        # Last good cloud answers, for a restart while the cloud is unreachable.
        self.cache = cache
        self._cloud_online: bool | None = None
        self.spec: dict = {}
        self.spec_functions: dict = {}
        self._spec_loaded = False
        # Product DPs outside the standard instruction set (see tuya_rooms). They
        # change only when the map is edited in the app, so they are read slowly.
        self.model: dict[str, dict] = {}
        self.model_raw: dict = {}
        self.properties: dict[str, Any] = {}
        self.room_names: dict[int, str] = {}
        # Room ids on the decoded map, published by the map camera once it renders.
        self.map_rooms: dict[int, str] = {}
        self._properties_next = 0.0
        # Cleaning history: one stored map per clean (A30 Pro), newest first, in the
        # card's "cleans" shape; start, area and duration come from each record.
        self.history: list[dict] = []
        self._history_cache: dict[str, dict] = {}
        # Not during setup: listing the maps downloads up to HISTORY_SIZE files.
        self._history_next = _time.monotonic() + 30
        self._history_fast_until = 0.0
        self._was_cleaning = False
        # LAN link (Tuya local protocol 3.3), started after the first refresh.
        self.local: TuyaLocalLink | None = None
        self._dpmap: DpMap | None = None
        self._model_codes: set[str] = set()
        self._standard_codes: set[str] = set()
        self._local_closing = False
        self._discovering = False
        self._discover_next = 0.0
        self._local_refused = False
        # Codes the link has delivered since it came up: fresher than any cloud read
        # (see merge_cloud_status). Cleared when it goes down.
        self._lan_codes: set[str] = set()
        # Set by the first local status, for a setup that has nothing else.
        self.first_local_status = asyncio.Event()
        self._status_saved_at: float | None = None

    @property
    def local_connected(self) -> bool:
        return bool(self.local is not None and self.local.connected)

    @property
    def online(self) -> bool | None:
        """Reachable: the LAN link is up, else what the cloud says."""
        return True if self.local_connected else self._cloud_online

    @property
    def supports_room_clean(self) -> bool:
        return CLEAN_ROOMS_CODE in self.properties

    @property
    def supports_zone_clean(self) -> bool:
        # dp 139 reads back empty, so it may be missing from the properties while
        # the thing model still has it.
        return CLEAN_ZONE_CODE in self.properties or CLEAN_ZONE_CODE in self._model_codes

    @property
    def schedules(self) -> dict[int, dict]:
        return parse_schedules(self.properties)

    def _watch_run_end(self, status: dict[str, Any]) -> None:
        """A finished run is stored within a minute or so: look for it right away,
        then every minute for a while, instead of on the idle 5-minute cadence."""
        cleaning = str(status.get(TUYA_DP_STATUS) or "").lower() in TUYA_STATUS_CLEANING
        if self._was_cleaning and not cleaning:
            self._history_next = 0.0
            self._history_fast_until = _time.monotonic() + 600
        self._was_cleaning = cleaning

    async def _async_update_history(self) -> None:
        now = _time.monotonic()
        if now < self._history_next:
            return
        self._history_next = now + (60 if now < self._history_fast_until else 300)
        try:
            records = await self.hass.async_add_executor_job(
                self.api.stored_map_records, HISTORY_SIZE)
        except TuyaError:
            _LOGGER.debug("ILIFE Clean history unavailable", exc_info=True)
            return
        history = []
        for record in records:
            record_id = str(record["id"])
            entry = self._history_cache.get(record_id)
            if entry is None:
                entry = await self._async_history_entry(record)
            history.append(entry)
        self._history_cache = {
            entry["record_id"]: entry for entry in history if not entry.get("retry")
        }
        self.history = history

    async def _async_history_entry(self, record: dict) -> dict:
        """One history row with its map. A map that cannot be fetched right now is
        retried next cycle; one that cannot be decoded is kept without a picture."""
        record_id = str(record["id"])
        try:
            entry = self._history_entry(record)
        except Exception:  # noqa: BLE001 — history is optional, never fail the poll
            _LOGGER.debug("ILIFE Clean history record %s unreadable", record_id,
                          exc_info=True)
            entry = {"record_id": record_id, "start": 0, "area": None,
                     "duration": None, "thumb": None, "path": []}
        try:
            files = await self.hass.async_add_executor_job(
                self.api.stored_map_files, record)
        except TuyaError:
            _LOGGER.debug("ILIFE Clean history map %s unavailable", record_id,
                          exc_info=True)
            entry["retry"] = True
            return entry
        layout = next((f["payload"] for f in files if f.get("map_type") == 0), None)
        if layout:
            try:
                entry["thumb"] = await self.hass.async_add_executor_job(
                    clean_map_thumbnail, layout)
                entry["path"] = await self.hass.async_add_executor_job(
                    clean_map_path, layout)
            except Exception:  # noqa: BLE001 — e.g. a map version we cannot decode
                _LOGGER.debug("ILIFE Clean history map %s not decoded", record_id,
                              exc_info=True)
        return entry

    @staticmethod
    def _history_entry(record: dict) -> dict:
        """One card history row from a stored map record."""
        clean = parse_record_extend(record.get("extend"))
        if clean:
            # The robot writes its own wall-clock time: read it in HA's time zone.
            started = clean["started"].replace(tzinfo=dt_util.get_default_time_zone())
            start = int(started.timestamp())
        else:
            try:
                start = int(record.get("time") or 0)
            except (TypeError, ValueError):
                start = 0
        return {
            "record_id": str(record["id"]),
            "start": start,
            "area": clean["area"] if clean else None,
            "duration": clean["duration"] if clean else None,
            "thumb": None,
            "path": [],
        }

    def enum_range(self, code: str) -> list:
        """Every value `code` accepts: the thing model's range, else the spec's."""
        return (self.model.get(code) or {}).get("range") or range_values(
            self.spec_functions, code)

    def _is_standard_command(self, code: str, value) -> bool:
        spec_range = range_values(self.spec_functions, code)
        return code in self.spec_functions and (not spec_range or value in spec_range)

    async def async_send(self, commands: list[dict]) -> None:
        """Send [{code, value}] as one instruction: over the LAN when the link is up
        (one frame: the robot needs pause/mode/switch_go together), else, or when a
        code has no dp id or the LAN send fails, through the cloud."""
        if await self._async_send(commands):
            await self.async_request_refresh()

    async def _async_send(self, commands: list[dict]) -> bool:
        """True when it went through the cloud (whose status must be re-read)."""
        if self.local_connected and self._dpmap is not None:
            dps: dict[str, Any] | None = {}
            for command in commands:
                dp = self._dpmap.dp_for(command["code"])
                if dp is None:
                    dps = None
                    break
                dps[dp] = command["value"]
            if dps:
                try:
                    await self.local.set_dps(dps)
                except TuyaLocalRefused as err:
                    # The robot itself said no: the cloud would only relay the same
                    # command to the same robot.
                    raise TuyaError(f"local command refused: {err}") from err
                except TuyaLocalTimeout as err:
                    # The frame went out and only its acknowledgement was lost: the
                    # robot has most likely run it. Sending it again through the
                    # cloud an ACK_TIMEOUT later would restart a room or zone job
                    # (and keep the user waiting twice), so while the
                    # link still stands this is reported as a failure instead. A
                    # link that dropped meanwhile falls back like any lost link.
                    if self.local_connected:
                        raise TuyaError(f"local command not acknowledged: {err}") from err
                    _LOGGER.debug("ILIFE Clean local link lost during a send (%s); "
                                  "using the cloud", err)
                except TuyaLocalError as err:
                    # Not connected, or the connection was lost: not (fully) sent.
                    _LOGGER.debug("ILIFE Clean local send failed (%s); using the cloud", err)
                else:
                    return False
        # Standard commands by the instruction set; the rest through the thing model
        # (e.g. suction "closed", which /specifications leaves out).
        standard = [c for c in commands if self._is_standard_command(c["code"], c["value"])]
        product = {c["code"]: c["value"] for c in commands
                   if not self._is_standard_command(c["code"], c["value"])}
        if standard:
            await self.hass.async_add_executor_job(self.api.send_many, standard)
        if product:
            await self.hass.async_add_executor_job(self.api.issue_properties, product)
        return True

    async def async_write(self, code: str, value) -> None:
        """Write one DP (see async_send)."""
        via_cloud = await self._async_send([{"code": code, "value": value}])
        if not self._is_standard_command(code, value):
            self.properties[code] = value
            self._properties_next = 0.0
        elif code in self.properties:
            # A setting the status lacks reads from the properties (see
            # tuya_dpmap.setting_value): keep them in step with what was written.
            self.properties[code] = value
        if via_cloud:
            await self.async_request_refresh()

    # -- local (LAN) link ----------------------------------------------------

    def _on_local_dps(self, dps: dict[str, Any]) -> None:
        """A local push or query answer: {dp id: value}."""
        if self._local_closing or self._dpmap is None:
            return
        update = split_local_dps(dps, self._dpmap)
        if not update:
            return
        status, properties = apply_local_dps(
            self.data, self.properties, update, self._standard_codes)
        self.properties = properties
        self._lan_codes.update(update)
        if any(code in ROOM_INFO_CODES for code in update):
            self._set_room_names()
        was_cleaning = self._was_cleaning
        self._watch_run_end(status)
        # Not async_set_updated_data: that reschedules the poll on every push, and a
        # chatty robot would starve the cloud history/properties refresh for good.
        self.data = status
        self.last_update_success = True
        self.first_local_status.set()
        self.async_update_listeners()
        self._maybe_save_status(status)
        if was_cleaning and not self._was_cleaning:
            self._background(self.async_request_refresh(), "refresh after a run")

    def _on_local_state(self, up: bool) -> None:
        if self._local_closing:
            return
        if up:
            _LOGGER.info("ILIFE Clean %s: local link connected (%s)",
                         self.api.device_id, self.local.host if self.local else "?")
            self.update_interval = LOCAL_POLL
        else:
            _LOGGER.debug("ILIFE Clean %s: local link down, polling the cloud",
                          self.api.device_id)
            # Not on the way up: the query answer is delivered before the link
            # reports connected.
            self._lan_codes.clear()
            self.update_interval = CLOUD_POLL
            self._background(self.async_request_refresh(), "refresh, link down")
        self.async_update_listeners()

    def _background(self, target, name: str) -> None:
        """A fire-and-forget job tied to the config entry, so unloading it cancels
        the job instead of letting it run on (and write the cache) afterwards."""
        self.config_entry.async_create_background_task(
            self.hass, target, f"{DOMAIN} {self.api.device_id} {name}")

    def _local_wanted(self) -> bool:
        entry = self.config_entry
        return bool(
            entry is not None and entry.options.get(CONF_LOCAL, True)
            and not self._local_refused and not self._local_closing
            and self._dpmap is not None
            and self.cache is not None and self.cache.get(self.api.device_id).get("local_key")
        )

    async def _async_find_host(self) -> tuple[str, str] | None:
        """(host, version) from the robot's UDP broadcast; never the cloud's `ip`,
        which is the device's public address."""
        self._discover_next = _time.monotonic() + REDISCOVER_EVERY
        return await discover_device(self.api.device_id, timeout=10)

    def _refuse_protocol(self, version: str) -> None:
        self._local_refused = True
        _LOGGER.warning("ILIFE Clean %s: local protocol %s is not supported (only %s); "
                        "staying on the cloud", self.api.device_id, version, LOCAL_PROTOCOL)

    async def async_start_local(self) -> None:
        """Start the LAN link: host from the option, else the cache, else discovery."""
        if self.local is not None or self._discovering or not self._local_wanted():
            return
        self._discovering = True
        try:
            record = self.cache.get(self.api.device_id)
            option_host = self.config_entry.options.get(CONF_HOST) or None
            host = option_host or record.get("host") or None
            if not host:
                found = await self._async_find_host()
                if not found:
                    _LOGGER.debug("ILIFE Clean %s: not found on the LAN yet",
                                  self.api.device_id)
                    return
                host, version = found
                if version != LOCAL_PROTOCOL:
                    self._refuse_protocol(version)
                    return
                await self._async_cache(host=host)
            if not self._local_wanted() or self.local is not None:
                return
            # Protocol 3.3 assumed for a configured or cached host: the link only
            # reports connected once a 3.3 query is answered.
            self.local = TuyaLocalLink(
                self.api.device_id, record["local_key"], host,
                self._on_local_dps, self._on_local_state)
            await self.local.start()
        finally:
            self._discovering = False

    async def _async_rediscover(self) -> None:
        """The link keeps failing: the robot may have a new address."""
        self._discovering = True
        try:
            found = await self._async_find_host()
        finally:
            self._discovering = False
        if not found or self.local is None or self._local_closing:
            return
        host, version = found
        if version != LOCAL_PROTOCOL:
            self._refuse_protocol(version)
            await self.async_stop_local()
            return
        if host != self.local.host:
            _LOGGER.info("ILIFE Clean %s: robot moved to %s on the LAN",
                         self.api.device_id, host)
            self.local.host = host
            self.local.failures = 0
            await self._async_cache(host=host)

    def _maybe_start_local(self) -> None:
        """From the poll: start the link if it is not up, rediscover if it fails."""
        if self._discovering or _time.monotonic() < self._discover_next:
            return
        entry = self.config_entry
        if self.local is None:
            if self._local_wanted():
                entry.async_create_background_task(
                    self.hass, self.async_start_local(), f"{DOMAIN} local start")
        elif (not self.local.connected and not self.config_entry.options.get(CONF_HOST)
              and self.local.failures >= REDISCOVER_AFTER_FAILURES):
            entry.async_create_background_task(
                self.hass, self._async_rediscover(), f"{DOMAIN} local rediscover")

    async def async_stop_local(self) -> None:
        link, self.local = self.local, None
        if link is not None:
            await link.stop()
        self.update_interval = CLOUD_POLL

    async def async_shutdown_local(self) -> None:
        """Unload: stop() fires on_state(False), which must not schedule a refresh."""
        self._local_closing = True
        link, self.local = self.local, None
        if link is not None:
            await link.stop()

    def _maybe_save_status(self, status: dict[str, Any]) -> None:
        """Keep the last status for a restart without the cloud (see tuya_cache)."""
        if self.cache is None or self._local_closing:
            return
        now = _time.monotonic()
        if not status_save_due(self.cache.get(self.api.device_id).get("status"),
                               status, self._status_saved_at, now):
            return
        self._status_saved_at = now
        self._background(self._async_cache(status=dict(status)), "status cache")

    def set_map_rooms(self, rooms: dict[int, str]) -> None:
        """From the map camera: the rooms on the decoded map, kept for a restart so
        area cleaning has its segments before the camera renders again."""
        rooms = dict(rooms or {})
        if rooms == self.map_rooms:
            return
        self.map_rooms = rooms
        if rooms:
            self._background(self._async_cache(map_rooms=map_rooms_to_cache(rooms)),
                             "map rooms cache")

    def seed_from_cache(self) -> bool:
        """No status yet (first refresh failed): start from the cached one."""
        if self.data is not None or self.cache is None:
            return False
        seeded = seed_status(self.cache.get(self.api.device_id).get("status"))
        if seeded is None:
            return False
        _LOGGER.info("ILIFE Clean %s: cloud unavailable, starting from the last "
                     "known status", self.api.device_id)
        self.data = seeded
        return True

    def _set_room_names(self) -> None:
        try:
            self.room_names = parse_room_names(self.properties)
        except Exception:  # noqa: BLE001 — names are cosmetic, keep the old ones
            _LOGGER.debug("ILIFE Clean room names unreadable", exc_info=True)

    async def _async_cache(self, **fresh) -> None:
        """Persist fresh cloud answers; a storage failure never fails the poll.

        Nothing once the entry is unloading: a save finishing after
        async_remove_entry would write the record (local key included) back."""
        if self.cache is None or self._local_closing:
            return
        try:
            await self.cache.async_update(self.api.device_id, **fresh)
        except Exception:  # noqa: BLE001
            _LOGGER.debug("ILIFE Clean cache not saved", exc_info=True)

    async def _async_update_properties(self) -> None:
        if _time.monotonic() < self._properties_next:
            return
        self._properties_next = _time.monotonic() + 300
        try:
            self.properties = await self.hass.async_add_executor_job(self.api.properties)
        except (TuyaError, AttributeError, TypeError):
            _LOGGER.debug("ILIFE Clean product properties unavailable", exc_info=True)
            return
        self._set_room_names()
        await self._async_cache(properties=dict(self.properties) or None)

    async def _async_load_spec(self) -> None:
        """Specification, thing model and last properties, once per setup: from the
        cloud, else from the cache, so a restart offline keeps every feature."""
        cached = self.cache.get(self.api.device_id) if self.cache is not None else {}
        spec = model_raw = None
        try:
            spec = await self.hass.async_add_executor_job(self.api.specification)
        except TuyaError:
            _LOGGER.debug("ILIFE Clean specification unavailable", exc_info=True)
        try:
            model_raw = await self.hass.async_add_executor_job(self.api.model_raw)
        except (TuyaError, AttributeError, TypeError):
            _LOGGER.debug("ILIFE Clean thing model unavailable", exc_info=True)
        if (not spec or not model_raw) and cached:
            _LOGGER.info("ILIFE Clean %s: cloud specification/model unavailable, "
                         "using the cached copy", self.api.device_id)
        cached_spec, cached_model = cached.get("spec"), cached.get("model_raw")
        self.spec = pick(spec, cached_spec if isinstance(cached_spec, dict) else None)
        self.spec_functions = parse_functions(self.spec)
        self.model_raw = pick(model_raw, cached_model if isinstance(cached_model, dict) else None)
        try:
            self.model = parse_thing_model(self.model_raw)
        except (AttributeError, TypeError):
            _LOGGER.debug("ILIFE Clean thing model unreadable", exc_info=True)
            self.model = {}
        try:
            dpmap = DpMap.from_model(self.model_raw)
        except Exception:  # noqa: BLE001 — local control is optional
            _LOGGER.debug("ILIFE Clean dp map unreadable", exc_info=True)
            dpmap = DpMap({})
        self._dpmap = dpmap if dpmap.to_dict() else None
        self._model_codes = set(dpmap.to_dict().values())
        self._standard_codes = set(self.spec_functions) | {
            s.get("code") for s in self.spec.get("status") or []
            if isinstance(s, dict) and s.get("code")}
        if not self.properties and isinstance(cached.get("properties"), dict):
            # Replaced by the cloud read that follows when the cloud answers.
            self.properties = dict(cached["properties"])
            self._set_room_names()
        if not self.map_rooms:
            # Replaced when the map camera renders.
            self.map_rooms = map_rooms_from_cache(cached.get("map_rooms"))
        await self._async_cache(spec=spec or None, model_raw=model_raw or None)

    async def _async_update_data(self) -> dict[str, Any]:
        if not self._spec_loaded:
            await self._async_load_spec()
            self._spec_loaded = True
        await self._async_update_properties()
        if self.local_connected:
            # Status comes from local pushes; the cloud only for what it alone has.
            # Nothing here may fail the update: the entities are fine over the LAN.
            try:
                await self._async_update_history()
            except Exception:  # noqa: BLE001
                _LOGGER.debug("ILIFE Clean history update failed", exc_info=True)
            fast = _time.monotonic() < self._history_fast_until
            self.update_interval = timedelta(seconds=60) if fast else LOCAL_POLL
            return dict(self.data or {})
        self.update_interval = CLOUD_POLL
        self._maybe_start_local()
        try:
            detail = await self.hass.async_add_executor_job(self.api.detail)
        except TuyaError as err:
            # Entities are built from the codes in `data`: a restart with the cloud
            # down starts from the last status kept, so none goes missing.
            self.seed_from_cache()
            if self.local_connected and self.data is not None:
                # The link came up during the call (a restart with the trial
                # expired or the cloud down: its answer beats the cloud's error).
                # Failing the update now would mark every entity unavailable,
                # LAN control included, until the robot next pushes a change.
                # A robot that is really gone drops the link (DEAD_AFTER), and the
                # poll that follows fails as usual.
                _LOGGER.debug("ILIFE Clean %s: cloud read failed (%s), the local link "
                              "is up", self.api.device_id, err)
                return dict(self.data)
            raise UpdateFailed(str(err)) from err
        local_key = detail.get("local_key")
        if (isinstance(local_key, str) and local_key
                and self.config_entry is not None
                and self.config_entry.options.get(CONF_LOCAL, True)):
            old_key = self.cache.get(self.api.device_id).get("local_key") \
                if self.cache is not None else None
            await self._async_cache(local_key=local_key)
            if old_key and local_key != old_key and self.local is not None:
                # Re-paired: the robot has a new key and the link, built with the
                # old one, would never be answered again. Start over with the new.
                _LOGGER.info("ILIFE Clean %s: new local key, restarting the local link",
                             self.api.device_id)
                await self.async_stop_local()
                self._background(self.async_start_local(), "local restart")
        self._cloud_online = detail.get("online")
        status = {s["code"]: s.get("value") for s in detail.get("status") or [] if s.get("code")}
        if self.local_connected:
            # The link came up during the call: its pushes are fresher, but the
            # cloud has the codes the robot leaves out of its LAN answer.
            return merge_cloud_status(status, self.data, self._lan_codes)
        self._watch_run_end(status)
        self._maybe_save_status(status)
        try:
            await self._async_update_history()
        except Exception:  # noqa: BLE001 — the history must never fail the status poll
            _LOGGER.debug("ILIFE Clean history update failed", exc_info=True)
        if self.local_connected:
            # The history awaits downloads: a link that came up meanwhile delivered
            # its query answer then, which is fresher than this cloud status.
            return merge_cloud_status(status, self.data, self._lan_codes)
        return status


async def _async_setup_ilifehome_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    account = ILifeAccount(
        entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD],
        entry.data.get(CONF_REGION, "eu"),
        entry.data.get(CONF_BRAND, DEFAULT_BRAND),
    )
    try:
        devices = await hass.async_add_executor_job(account.login)
    except ILifeAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except ILifeError as err:
        raise ConfigEntryNotReady(str(err)) from err

    coordinators: dict[str, ILifeCoordinator] = {}
    for dev in devices:
        coordinator = ILifeCoordinator(hass, entry, ILifeDevice(account, dev))
        # per-device: one offline vacuum must not abort the whole account entry
        await coordinator.async_refresh()
        coordinators[dev["iotId"]] = coordinator
    if not coordinators:
        raise ConfigEntryNotReady("no device set up")

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "backend": BACKEND_ILIFEHOME, "account": account, "coordinators": coordinators,
        "platforms": ILIFEHOME_PLATFORMS,
    }


def _async_remove_replaced_generic_entities(
    hass: HomeAssistant, entry: ConfigEntry, coordinators: dict
) -> None:
    """Drop the generic entities that dedicated ones replaced in 0.7.0.

    Consumable life used to be a raw minutes sensor, volume and dust-collection
    frequency read-only sensors, and the resets switches. Their replacements have
    another unique_id or domain, so the old ones would linger as "no longer
    provided" forever.
    """
    registry = er.async_get(hass)
    sensors = [*TUYA_CONSUMABLES, TUYA_DP_VOLUME, TUYA_DP_DUST_FREQUENCY]
    switches = [TUYA_DP_RESET_MAP, *(reset for _, reset, _, _ in TUYA_CONSUMABLES.values())]
    for device_id in coordinators:
        for domain, codes in (("sensor", sensors), ("switch", switches)):
            for code in codes:
                entity_id = registry.async_get_entity_id(domain, DOMAIN, f"{device_id}_{code}")
                if entity_id:
                    entity = registry.async_get(entity_id)
                    if entity and entity.config_entry_id == entry.entry_id:
                        _LOGGER.info("ILIFE Clean: removing %s, replaced in 0.7.0", entity_id)
                        registry.async_remove(entity_id)


def _lan_ready_devices(entry: ConfigEntry, cache: DeviceCache) -> list[dict]:
    """Cached devices that can run without the cloud: LAN control on, and a local
    key kept for them (see tuya_cache)."""
    if not entry.options.get(CONF_LOCAL, True):
        return []
    return [device for device in cache.devices()
            if cache.get(device["id"]).get("local_key")]


async def _async_setup_ilife_clean_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    client = TuyaClient(
        entry.data[CONF_ACCESS_ID], entry.data[CONF_ACCESS_SECRET],
        entry.data[CONF_UID], entry.data.get(CONF_REGION, "eu"),
    )
    cache = DeviceCache(hass, entry.entry_id)
    try:
        await cache.load()
    except Exception:  # noqa: BLE001 — a broken cache file must not block setup
        _LOGGER.warning("ILIFE Clean: device cache unreadable, ignoring it", exc_info=True)
    try:
        devices = await hass.async_add_executor_job(client.list_devices)
    except TuyaAuthError as err:
        # Most often an expired Cloud Project trial (28841002), which lapses every
        # few months. The robot does not need the cloud to be driven over the LAN,
        # so a device the cache can bring up locally keeps working; the user is
        # asked to re-authenticate (after renewing the trial) instead of losing
        # the robot until then. Without such a device, failing setup is all
        # that is left.
        devices = _lan_ready_devices(entry, cache)
        if not devices:
            raise ConfigEntryAuthFailed(str(err)) from err
        _LOGGER.warning("ILIFE Clean: the Tuya cloud refused this setup (%s); running "
                        "%d cached device(s) over the local network until it is fixed",
                        err, len(devices))
        entry.async_start_reauth(hass)
    except TuyaNoDevicesError as err:
        # The cloud answered: nothing is bound. Not an outage, so no cached devices.
        raise ConfigEntryNotReady(str(err)) from err
    except TuyaError as err:
        devices = cache.devices()
        if not devices:
            raise ConfigEntryNotReady(str(err)) from err
        _LOGGER.warning("ILIFE Clean: cloud unreachable (%s); setting up %d cached "
                        "device(s)", err, len(devices))
    else:
        for dev in devices:
            if dev.get("id"):
                try:
                    await cache.async_update(dev["id"], device=dev)
                except Exception:  # noqa: BLE001
                    _LOGGER.debug("ILIFE Clean cache not saved", exc_info=True)

    vacuums = [d for d in devices if d.get("category") == TUYA_CATEGORY_VACUUM]
    if not vacuums:
        # Rather than set up nothing at all, trust the account over our category guess:
        # a model filed under an unexpected category still deserves to work, and the
        # extra entities are visible enough that it gets reported.
        _LOGGER.warning(
            "ILIFE Clean: none of the %d linked Tuya devices are in the robot-vacuum "
            "category (%r); setting all of them up. Please report this with the "
            "integration's diagnostics: %s",
            len(devices), TUYA_CATEGORY_VACUUM,
            sorted({d.get("category") for d in devices}),
        )
        vacuums = devices
    elif len(vacuums) != len(devices):
        _LOGGER.debug("ILIFE Clean: %d of %d linked Tuya devices are vacuums",
                      len(vacuums), len(devices))

    coordinators: dict[str, ILifeTuyaCoordinator] = {}
    for dev in vacuums:
        coordinator = ILifeTuyaCoordinator(hass, entry, TuyaVacuum(client, dev), cache)
        await coordinator.async_refresh()
        coordinators[dev["id"]] = coordinator
        # In the background: discovery can take a few seconds.
        entry.async_create_background_task(
            hass, coordinator.async_start_local(), f"{DOMAIN} local start {dev['id']}")
    if not coordinators:
        raise ConfigEntryNotReady("no device set up")

    async def _async_wait_first_local(coordinator: ILifeTuyaCoordinator) -> None:
        try:
            async with asyncio.timeout(FIRST_LOCAL_WAIT):
                await coordinator.first_local_status.wait()
        except TimeoutError:
            _LOGGER.debug("ILIFE Clean %s: no local status within %ss",
                          coordinator.api.device_id, FIRST_LOCAL_WAIT)

    # Nothing from the cloud and nothing cached: the entities are built from the
    # status codes, so give the LAN a moment to answer first. All robots at once,
    # so several of them cost FIRST_LOCAL_WAIT at most, not that much each.
    await asyncio.gather(*(
        _async_wait_first_local(coordinator) for coordinator in coordinators.values()
        if coordinator.data is None and coordinator._local_wanted()))
    _async_remove_replaced_generic_entities(hass, entry, coordinators)

    async def _async_stop_local(_event) -> None:
        for coordinator in coordinators.values():
            await coordinator.async_shutdown_local()

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop_local))

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "backend": BACKEND_ILIFE_CLEAN, "client": client, "coordinators": coordinators,
        "platforms": ILIFE_CLEAN_PLATFORMS,
    }


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if entry.data.get(CONF_BACKEND) == BACKEND_ILIFE_CLEAN:
        await _async_setup_ilife_clean_entry(hass, entry)
    else:
        await _async_setup_ilifehome_entry(hass, entry)
    # Both backends ship the same card: registering it only on the ILIFEHOME path left
    # ILIFE Clean users with no "ILIFE Vacuum Card" in the card picker at all, and
    # copying the .js into www/community by hand as the only way out (#23).
    await _async_register_frontend(hass)
    platforms = hass.data[DOMAIN][entry.entry_id]["platforms"]
    await hass.config_entries.async_forward_entry_setups(entry, platforms)
    if entry.data.get(CONF_BACKEND) == BACKEND_ILIFE_CLEAN:
        entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Apply changed LAN options by reloading the entry."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    store = hass.data.get(DOMAIN, {}).get(entry.entry_id) or {}
    platforms = store.get("platforms", ILIFEHOME_PLATFORMS)
    unloaded = await hass.config_entries.async_unload_platforms(entry, platforms)
    if unloaded:
        for coordinator in (store.get("coordinators") or {}).values():
            if isinstance(coordinator, ILifeTuyaCoordinator):
                await coordinator.async_shutdown_local()
        hass.data[DOMAIN].pop(entry.entry_id, None)
        # keep the '_card_*' flags; only drop DOMAIN when no entries remain
        if not any(isinstance(v, dict) and "coordinators" in v
                   for v in hass.data.get(DOMAIN, {}).values()):
            for k in ("_card_served", "_card_registered"):
                hass.data.get(DOMAIN, {}).pop(k, None)
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Drop the ILIFE Clean device cache: it holds the robot's local key."""
    if entry.data.get(CONF_BACKEND) != BACKEND_ILIFE_CLEAN:
        return
    from homeassistant.helpers.storage import Store

    from .tuya_cache import STORAGE_VERSION, map_file_name

    store = Store(hass, STORAGE_VERSION, f"ilife.{entry.entry_id}")
    try:
        cached = await store.async_load()
    except Exception:  # noqa: BLE001
        cached = None
    paths = [hass.config.path(".storage", map_file_name(device_id))
             for device_id in (cached if isinstance(cached, dict) else {})]

    def _remove_maps() -> None:
        for path in paths:
            try:
                os.remove(path)
            except OSError:
                pass

    try:
        await hass.async_add_executor_job(_remove_maps)
        await store.async_remove()
    except Exception:  # noqa: BLE001
        _LOGGER.debug("ILIFE Clean device cache not removed", exc_info=True)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: ConfigEntry, device: DeviceEntry
) -> bool:
    """Allow deleting a device from the UI only if it is gone from the account.

    A vacuum that was unbound (replaced, sold, reset) stays in the registry as an
    unavailable "ghost" device. This lets the user remove it. A device that is
    still bound is kept, since it would just be recreated on the next refresh.
    """
    store = hass.data.get(DOMAIN, {}).get(entry.entry_id) or {}
    active = set((store.get("coordinators") or {}).keys())
    iot_ids = {ident for (dom, ident) in device.identifiers if dom == DOMAIN}
    return iot_ids.isdisjoint(active)


# --------------------------------------------------------------------------- #
#  Lovelace card auto-registration (safe: never wipes the user's resources)
# --------------------------------------------------------------------------- #
async def _async_register_frontend(hass: HomeAssistant) -> None:
    data = hass.data.setdefault(DOMAIN, {})
    if not data.get("_card_served"):
        try:
            from homeassistant.components.http import StaticPathConfig

            path = hass.config.path(f"custom_components/{DOMAIN}/www/{CARD_FILENAME}")
            await hass.http.async_register_static_paths([StaticPathConfig(CARD_URL, path, True)])
            data["_card_served"] = True
        except Exception:  # noqa: BLE001
            _LOGGER.debug("ILIFE: could not serve card static path", exc_info=True)

    if hass.state is CoreState.running:
        await _async_register_card_resource(hass)
    else:
        async def _on_started(_event):
            await _async_register_card_resource(hass)
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _on_started)


async def _async_register_card_resource(hass: HomeAssistant) -> None:
    """Register the card as a Lovelace resource in storage mode.

    Guards against HA core issue #165767: writing before the resource collection is
    loaded rewrites .storage/lovelace_resources and would wipe ALL the user's resources.
    We only act once resources.loaded is True.
    """
    data = hass.data.setdefault(DOMAIN, {})
    if data.get("_card_registered"):
        return
    lovelace = hass.data.get("lovelace")
    if lovelace is None:
        return
    # Detect a storage-backed resource collection by what it can do, not by the name of
    # a mode attribute. `LovelaceData.mode` was renamed to `resource_mode` in Home
    # Assistant, and reading the old name through a getattr default meant this function
    # silently returned every single time: the card stopped being registered for anyone,
    # and installs that had it kept whatever URL version they were on (#23). Only
    # ResourceStorageCollection has async_create_item; the YAML one is read-only and is
    # the documented manual case.
    resources = getattr(lovelace, "resources", None)
    if resources is None or not hasattr(resources, "async_create_item"):
        _LOGGER.debug("ILIFE: Lovelace resources are not storage-backed; add %s manually",
                      CARD_URL)
        return
    if not getattr(resources, "loaded", False):
        async def _retry(_now):
            await _async_register_card_resource(hass)
        async_call_later(hass, 5, _retry)
        return

    from homeassistant.loader import async_get_integration

    version = "0"
    try:
        version = (await async_get_integration(hass, DOMAIN)).version or "0"
    except Exception:  # noqa: BLE001
        pass
    want = f"{CARD_URL}?v={version}"
    existing = [r for r in resources.async_items()
                if _is_ilife_card_resource(r.get("url", ""))]
    try:
        if not existing:
            await resources.async_create_item({"res_type": "module", "url": want})
            _LOGGER.info("ILIFE: Lovelace card resource added (%s)", want)
        else:
            primary = existing[0]
            if primary.get("url") != want:
                await resources.async_update_item(
                    primary["id"], {"res_type": "module", "url": want}
                )
                _LOGGER.info("ILIFE: Lovelace card resource updated to %s", want)
            for duplicate in existing[1:]:
                if hasattr(resources, "async_delete_item"):
                    await resources.async_delete_item(duplicate["id"])
                elif duplicate.get("url") != want:
                    await resources.async_update_item(
                        duplicate["id"], {"res_type": "module", "url": want}
                    )
    except Exception:  # noqa: BLE001
        # Loud on purpose: a silent failure here leaves the user with no card in the
        # picker and nothing to go on, which is how #23 was spent.
        _LOGGER.warning(
            "ILIFE: could not register the Lovelace card resource automatically. Add it "
            "by hand under Settings > Dashboards > Resources: URL %s, type JavaScript "
            "module.", want, exc_info=True)
    finally:
        data["_card_registered"] = True
