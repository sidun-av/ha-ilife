"""Saved zones (ILIFE Clean laser models): named rectangles to clean again.

Each one is kept in the entry's cache (`saved_zones`, so it survives a restart),
listed on the vacuum as the `saved_zones` attribute (the card's chips) and gets a
button that cleans it (button.py), a one-tap shortcut for dashboards and
automations. Cleaning goes through `ilife.clean_zone`, so a saved zone gets the
same suction nudge as one drawn on the spot.
"""
from __future__ import annotations

import hashlib
from collections.abc import Callable

from .tuya_zones import MAX_ZONE_PASSES, clean_zone_value

MAX_NAME = 40


def normalize_zone(name: str, zone, repeats: int = 1) -> tuple[str, dict]:
    """The stored (name, {"zone", "repeats"}) for a save request; ValueError if bad."""
    name = " ".join(str(name or "").split())
    if not name:
        raise ValueError("a saved zone needs a name")
    if len(name) > MAX_NAME:
        raise ValueError(f"a zone name is at most {MAX_NAME} characters")
    zones = [[round(float(v)) for v in rect] for rect in zone]
    repeats = int(repeats)
    if repeats not in range(1, MAX_ZONE_PASSES + 1):
        raise ValueError(f"passes must be between 1 and {MAX_ZONE_PASSES}")
    clean_zone_value([tuple(rect) for rect in zones], repeats)   # same limits as a clean
    return name, {"zone": zones, "repeats": repeats}


def zone_key(name: str) -> str:
    """A stable id part for a zone's button: the same name always gives the same
    key, whatever its alphabet (names are often Cyrillic)."""
    return hashlib.sha1(name.casefold().encode()).hexdigest()[:10]


def stored_zones(raw) -> dict[str, dict]:
    """The cached `saved_zones`, keeping only well-formed entries."""
    out = {}
    if not isinstance(raw, dict):
        return out
    for name, item in raw.items():
        try:
            key, value = normalize_zone(name, (item or {}).get("zone") or [], (item or {}).get("repeats", 1))
        except (TypeError, ValueError, AttributeError):
            continue
        out[key] = value
    return out


def saved_zones_manager(coordinator) -> SavedZones:
    """The coordinator's saved zones, made on first use by any platform."""
    if getattr(coordinator, "saved_zones", None) is None:
        coordinator.saved_zones = SavedZones(coordinator)
    return coordinator.saved_zones


class SavedZones:
    def __init__(self, coordinator) -> None:
        self.coordinator = coordinator
        record = coordinator.cache.get(coordinator.api.device_id) if coordinator.cache else {}
        self.zones: dict[str, dict] = stored_zones(record.get("saved_zones"))
        self._listeners: list[Callable[[set[str], set[str]], None]] = []

    def add_listener(self, listener: Callable[[set[str], set[str]], None]) -> Callable[[], None]:
        """Call listener(added_or_changed, removed) on every change; returns the remover."""
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener) if listener in self._listeners else None

    def get(self, name: str) -> dict | None:
        return self.zones.get(name)

    async def async_save(self, name: str, zone, repeats: int = 1) -> str:
        name, value = normalize_zone(name, zone, repeats)
        self.zones = {**self.zones, name: value}
        await self._async_store()
        self._notify({name}, set())
        return name

    async def async_delete(self, name: str) -> None:
        name = " ".join(str(name or "").split())
        if name not in self.zones:
            raise KeyError(name)
        self.zones = {k: v for k, v in self.zones.items() if k != name}
        await self._async_store()
        self._notify(set(), {name})

    async def _async_store(self) -> None:
        await self.coordinator._async_cache(saved_zones=self.zones)  # noqa: SLF001 — its own store

    def _notify(self, changed: set[str], removed: set[str]) -> None:
        for listener in list(self._listeners):
            listener(changed, removed)
