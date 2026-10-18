"""What an ILIFE Clean device needs to come up without the cloud.

Entities derive their features from the cloud `/specifications`; a restart while the
internet is down would otherwise set up a vacuum with no features at all. The last
good cloud answers are kept in an HA `Store`, one record per device:

    {device_id: {"device": {...list_devices entry...}, "spec": {...},
                 "model_raw": {...}, "properties": {...},
                 "local_key": str, "host": str, "status": {...last status...},
                 "map_rooms": {"<room id>": "<label>"},
                 "last_map_meta": {calibration_points, map_scale, rooms,
                                   png_sha256}}}

The last rendered map PNG itself is a file next to the Store
(`.storage/ilife_map_<device id>.png`, see `map_file_name`).

`merge_cache` and `pick` are pure (unit-tested without Home Assistant); `DeviceCache`
imports HA only when constructed. The local key is never logged.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

STORAGE_VERSION = 1
# Local pushes are frequent: the status snapshot is written at most this often,
# unless the set of codes changed.
STATUS_SAVE_EVERY = 300.0


def merge_cache(old: dict | None, **fresh: Any) -> dict:
    """A copy of `old` updated with every fresh value that is not None."""
    out = dict(old or {})
    for key, value in fresh.items():
        if value is not None:
            out[key] = value
    return out


def pick(fresh: dict | None, cached: dict | None) -> dict:
    """The cloud's answer when it gave one, else the cached one, else {}."""
    if fresh:
        return fresh
    return cached or {}


def seed_status(cached: Any) -> dict | None:
    """The cached status snapshot to start from when the first refresh failed."""
    return dict(cached) if isinstance(cached, dict) and cached else None


def status_save_due(saved: Any, status: dict, last_saved: float | None, now: float,
                    every: float = STATUS_SAVE_EVERY) -> bool:
    """Whether to persist `status`: always when its set of codes changed (an entity
    may depend on a code), else when it differs and the last save is `every` old."""
    if not status:
        return False
    if not isinstance(saved, dict) or set(saved) != set(status):
        return True
    if saved == status:
        return False
    return last_saved is None or now - last_saved >= every


def map_rooms_to_cache(rooms: dict) -> dict[str, str]:
    """{room id: label} with string keys (the Store is JSON)."""
    return {str(room_id): str(label) for room_id, label in (rooms or {}).items()}


def map_rooms_from_cache(cached: Any) -> dict[int, str]:
    """The cached map rooms back with int ids; anything malformed is skipped."""
    out: dict[int, str] = {}
    if not isinstance(cached, dict):
        return out
    for room_id, label in cached.items():
        try:
            out[int(room_id)] = str(label)
        except (TypeError, ValueError):
            continue
    return out


def map_file_name(device_id: str) -> str:
    """File name (in `.storage`) of a device's last rendered map PNG."""
    return "ilife_map_" + re.sub(r"[^A-Za-z0-9_-]", "_", str(device_id)) + ".png"


def map_meta_to_cache(meta: dict | None, png: bytes) -> dict:
    """The render metadata worth keeping with the cached PNG (JSON-safe)."""
    meta = meta or {}
    return {
        "calibration_points": meta.get("calibration_points") or [],
        "map_scale": meta.get("map_scale"),
        "rooms": map_rooms_to_cache(meta.get("rooms") or {}),
        "png_sha256": hashlib.sha256(png).hexdigest(),
    }


def map_meta_from_cache(cached: Any) -> dict | None:
    """Render metadata back from the cache (rooms with int ids), None if unusable."""
    if not isinstance(cached, dict) or not cached.get("png_sha256"):
        return None
    meta = {k: v for k, v in cached.items() if k != "png_sha256"}
    meta["rooms"] = map_rooms_from_cache(cached.get("rooms"))
    return meta


def map_persist_due(cached: Any, png: bytes | None) -> bool:
    """Whether `png` differs from the one the cached metadata describes."""
    if not png:
        return False
    if not isinstance(cached, dict):
        return True
    return cached.get("png_sha256") != hashlib.sha256(png).hexdigest()


def is_network_error(err: BaseException) -> bool:
    """A cloud call that failed because the cloud could not be reached at all."""
    text = str(err)
    return text.startswith("network error") or text.startswith("map file download failed")


class DeviceCache:
    """Per-entry persistent cache (`.storage/ilife.<entry_id>`); saves only on change."""

    def __init__(self, hass, entry_id: str) -> None:
        from homeassistant.helpers.storage import Store

        self._store = Store(hass, STORAGE_VERSION, f"ilife.{entry_id}")
        self._data: dict[str, dict] = {}

    async def load(self) -> dict:
        data = await self._store.async_load()
        self._data = data if isinstance(data, dict) else {}
        return self._data

    async def save(self, data: dict) -> None:
        self._data = data
        await self._store.async_save(data)

    def get(self, device_id: str) -> dict:
        entry = self._data.get(device_id)
        return entry if isinstance(entry, dict) else {}

    def devices(self) -> list[dict]:
        """The cached list_devices entries (for a setup while the cloud is down)."""
        out = []
        for entry in self._data.values():
            device = entry.get("device") if isinstance(entry, dict) else None
            if isinstance(device, dict) and device.get("id"):
                out.append(device)
        return out

    async def async_update(self, device_id: str, **fresh: Any) -> None:
        """Merge fresh values into one device's record; write only if it changed."""
        old = self.get(device_id)
        new = merge_cache(old, **fresh)
        if new != old:
            await self.save({**self._data, device_id: new})
