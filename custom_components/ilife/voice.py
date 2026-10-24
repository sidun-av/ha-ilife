"""Voice packs inside Home Assistant (ILIFE Clean models with dp 35 voice_data).

Packs live in `<config>/ilife_voice/` (format: see tuya_voice). Choosing one builds
its archive, serves it from Home Assistant itself (the robot downloads it over the
LAN; the official CDN URL is too long for the 128-byte frame) and writes the
install frame to dp 35. A pack with several candidates per prompt is rebuilt with
a new random pick after each clean when shuffling is on: the robot plays one fixed
file per prompt, so the randomness is from one clean to the next.
"""
from __future__ import annotations

import asyncio
import logging
import random
from pathlib import Path

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.network import NoURLAvailableError, get_url

from .const import DOMAIN, TUYA_STATUS_CLEANING, TUYA_STATUS_DOCKED, TUYA_STATUS_RETURNING
from .tuya_api import TuyaError
from .tuya_entity import tuya_command_error
from .tuya_voice import (
    BUILD_DIR,
    OFFICIAL,
    OFFICIAL_URL,
    VOICE_CODE,
    VoicePack,
    build_file_name,
    build_pack,
    list_packs,
    md5_hex,
    parse_voice_report,
    pick_prompts,
    prompt_choices,
    unpack_official,
    voice_install_value,
)

_LOGGER = logging.getLogger(__name__)

VOICE_DIR = "ilife_voice"
VOICE_URL = "/ilife_voice"
# Ids the app may have used (50 = the official pack); ours start above them.
FIRST_PACK_ID = 100
KEEP_BUILDS = 3


def supports_voice(coordinator) -> bool:
    return VOICE_CODE in coordinator.spec_functions


def voice_manager(hass, coordinator) -> VoiceManager:
    """The coordinator's voice manager, made on first use by any platform."""
    if getattr(coordinator, "voice", None) is None:
        coordinator.voice = VoiceManager(hass, coordinator)
    return coordinator.voice


class VoiceManager:
    def __init__(self, hass, coordinator) -> None:
        self.hass = hass
        self.coordinator = coordinator
        self.root = Path(hass.config.path(VOICE_DIR))
        self.packs: list[VoicePack] = []
        record = coordinator.cache.get(coordinator.api.device_id) if coordinator.cache else {}
        self.current: str | None = record.get("voice_pack")
        self.shuffle: bool = bool(record.get("voice_shuffle", False))
        self.last_id: int = int(record.get("voice_id") or FIRST_PACK_ID)
        self.last_url: str | None = None
        self._ran = False
        self._lock = asyncio.Lock()
        self._prepared = False

    # -- setup ------------------------------------------------------------------

    async def async_prepare(self) -> None:
        """Serve the build directory and list the packs (once, for all platforms)."""
        async with self._lock:
            if self._prepared:
                return
            build = self.root / BUILD_DIR
            await self.hass.async_add_executor_job(lambda: build.mkdir(parents=True, exist_ok=True))
            data = self.hass.data.setdefault(DOMAIN, {})
            if not data.get("_voice_served"):
                try:
                    from homeassistant.components.http import StaticPathConfig

                    await self.hass.http.async_register_static_paths(
                        [StaticPathConfig(VOICE_URL, str(build), False)])
                    data["_voice_served"] = True
                except Exception:  # noqa: BLE001
                    _LOGGER.debug("ILIFE: could not serve the voice packs", exc_info=True)
            await self._async_scan()
            self._prepared = True

    async def _async_scan(self) -> None:
        self.packs = await self.hass.async_add_executor_job(list_packs, self.root)

    # -- options ----------------------------------------------------------------

    @property
    def options(self) -> list[str]:
        """`official` (translated by the select) and each pack's name."""
        return [OFFICIAL, *self._names()]

    def _names(self) -> list[str]:
        seen: dict[str, int] = {}
        names = []
        for pack in self.packs:
            name = pack.name if pack.name != OFFICIAL else pack.pack_id
            seen[name] = seen.get(name, 0) + 1
            names.append(name if seen[name] == 1 else f"{name} ({pack.pack_id})")
        return names

    def option_for(self, pack_id: str | None) -> str | None:
        if pack_id == OFFICIAL:
            return OFFICIAL
        for pack, name in zip(self.packs, self._names()):
            if pack.pack_id == pack_id:
                return name
        return None

    def pack_for(self, option: str) -> VoicePack | None:
        for pack, name in zip(self.packs, self._names()):
            if name == option:
                return pack
        return None

    def current_pack(self) -> VoicePack | None:
        return next((p for p in self.packs if p.pack_id == self.current), None)

    @property
    def report(self) -> dict | None:
        """The robot's last install report (dp 35), when it sent one."""
        return parse_voice_report((self.coordinator.data or {}).get(VOICE_CODE))

    # -- installing ---------------------------------------------------------------

    async def async_select(self, option: str) -> None:
        await self._async_scan()
        if option == OFFICIAL:
            await self.async_install(OFFICIAL)
            return
        pack = self.pack_for(option)
        if pack is None:
            raise HomeAssistantError(f"no voice pack named {option!r} in {self.root}")
        await self.async_install(pack.pack_id)

    async def async_install(self, pack_id: str, seed: int | None = None) -> None:
        async with self._lock:
            await self._async_ensure_official()
            pack = None if pack_id == OFFICIAL else next(
                (p for p in self.packs if p.pack_id == pack_id), None)
            if pack_id != OFFICIAL and pack is None:
                raise HomeAssistantError(f"voice pack {pack_id!r} is gone from {self.root}")
            if seed is None:
                seed = random.SystemRandom().randrange(1 << 32)
            name, md5 = await self.hass.async_add_executor_job(self._build, pack_id, pack, seed)
            url = self._url(name)
            pack_number = self.last_id + 1
            try:
                value = voice_install_value(pack_number, md5, url)
            except ValueError as err:
                raise HomeAssistantError(str(err)) from err
            try:
                await self.coordinator.async_write(VOICE_CODE, value)
            except TuyaError as err:
                raise tuya_command_error(err) from err
            self.last_id, self.current, self.last_url = pack_number, pack_id, url
            await self._async_save()
            _LOGGER.info("ILIFE Clean %s: voice pack %s sent (id %s, %s)",
                         self.coordinator.api.device_id, pack_id, pack_number, url)
        self.coordinator.async_update_listeners()

    def _build(self, pack_id: str, pack: VoicePack | None, seed: int) -> tuple[str, str]:
        official = prompt_choices(self.root / OFFICIAL / "audio_cloud")
        own = prompt_choices(pack.path / "audio_cloud") if pack else {}
        archive = build_pack(pick_prompts(own, official, seed))
        build = self.root / BUILD_DIR
        build.mkdir(parents=True, exist_ok=True)
        name = build_file_name(pack_id, seed)
        (build / name).write_bytes(archive)
        # Keep a few: the robot may still be downloading the previous one.
        old = sorted((p for p in build.glob("*.tgz") if p.name != name),
                     key=lambda p: p.stat().st_mtime, reverse=True)
        for path in old[KEEP_BUILDS - 1:]:
            path.unlink(missing_ok=True)
        return name, md5_hex(archive)

    def _url(self, name: str) -> str:
        try:
            base = get_url(self.hass, allow_external=False, allow_cloud=False,
                           prefer_external=False)
        except NoURLAvailableError as err:
            raise HomeAssistantError(
                "voice packs need Home Assistant's local network URL "
                "(Settings > System > Network)") from err
        if not base.startswith("http://"):
            raise HomeAssistantError(
                f"the robot downloads voice packs over plain HTTP; the local URL is {base}")
        return f"{base.rstrip('/')}{VOICE_URL}/{name}"

    async def _async_ensure_official(self) -> None:
        """The official prompts: the fallback of every pack, and a pack of their own."""
        audio = self.root / OFFICIAL / "audio_cloud"
        if await self.hass.async_add_executor_job(lambda: any(audio.glob("*.wav"))):
            return
        try:
            session = async_get_clientsession(self.hass)
            async with session.get(OFFICIAL_URL, timeout=120) as response:
                response.raise_for_status()
                archive = await response.read()
            count = await self.hass.async_add_executor_job(
                unpack_official, archive, self.root / OFFICIAL)
        except Exception as err:  # noqa: BLE001 — a network or archive problem
            raise HomeAssistantError(f"could not fetch the official voice pack: {err}") from err
        _LOGGER.info("ILIFE: official voice pack fetched (%s prompts)", count)

    # -- shuffling ------------------------------------------------------------------

    async def async_set_shuffle(self, on: bool) -> None:
        self.shuffle = on
        await self._async_save()
        self.coordinator.async_update_listeners()

    async def async_reshuffle(self) -> None:
        """A new random pick of the current pack (the button)."""
        await self._async_scan()
        pack = self.current_pack()
        if pack is None or not pack.shuffle:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="voice_not_shuffled")
        await self.async_install(pack.pack_id)

    def on_status(self, status: str) -> None:
        """Watch the runs: once one ends (back to the dock), reshuffle if asked to."""
        status = str(status or "").lower()
        if status in TUYA_STATUS_CLEANING:
            self._ran = True
            return
        if not self._ran or status not in TUYA_STATUS_DOCKED | TUYA_STATUS_RETURNING:
            return
        self._ran = False
        pack = self.current_pack()
        if self.shuffle and pack is not None and pack.shuffle:
            self.coordinator.config_entry.async_create_background_task(
                self.hass, self._async_reshuffle_quietly(pack.pack_id),
                f"{DOMAIN} {self.coordinator.api.device_id} voice shuffle")

    async def _async_reshuffle_quietly(self, pack_id: str) -> None:
        try:
            await self.async_install(pack_id)
        except HomeAssistantError as err:
            _LOGGER.warning("ILIFE Clean %s: voice reshuffle failed: %s",
                            self.coordinator.api.device_id, err)

    async def _async_save(self) -> None:
        await self.coordinator._async_cache(  # noqa: SLF001 — the coordinator's own store
            voice_pack=self.current, voice_shuffle=self.shuffle, voice_id=self.last_id)
