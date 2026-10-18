"""The map camera's throttled save, on Home Assistant's own timer."""
from __future__ import annotations

import asyncio
from unittest.mock import patch

from custom_components.ilife import camera as camera_module


class _Cache:
    def __init__(self) -> None:
        self.records: dict = {}
        self.updates = 0

    def get(self, device_id):
        return self.records.get(device_id, {})

    async def async_update(self, device_id, **fresh) -> None:
        self.updates += 1
        self.records.setdefault(device_id, {}).update(fresh)


class _Api:
    device_id = "testdevice0000000001"
    device = {"name": "Robot"}


class _Coordinator:
    def __init__(self) -> None:
        self.api = _Api()
        self.cache = _Cache()
        self.data = {}

    def async_add_listener(self, *_args, **_kwargs):
        return lambda: None


def _camera(hass):
    coordinator = _Coordinator()
    camera = camera_module.TuyaMapCamera(coordinator)
    camera.hass = hass
    camera._render_metadata = {"calibration_points": [1]}
    camera._persist._every = 0.05
    return camera, coordinator.cache


async def test_a_throttled_save_is_flushed_later(hass):
    camera, cache = _camera(hass)
    with patch.object(camera_module, "_write_file", lambda _path, _data: None):
        camera._cache_png = b"png1"
        await camera._async_persist_map(force=True)
        assert cache.updates == 1
        camera._cache_png = b"png2"
        await camera._async_persist_map()  # within the limit: owed, not dropped
        assert camera._persist_unsub is not None and cache.updates == 1
        await asyncio.sleep(0.15)
        await hass.async_block_till_done()
        assert cache.updates == 2 and camera._persist_unsub is None


async def test_removal_cancels_an_owed_save(hass):
    camera, cache = _camera(hass)
    with patch.object(camera_module, "_write_file", lambda _path, _data: None):
        camera._cache_png = b"png1"
        await camera._async_persist_map(force=True)
        camera._cache_png = b"png2"
        await camera._async_persist_map()
        await camera.async_will_remove_from_hass()
        assert camera._persist_unsub is None
        await asyncio.sleep(0.15)
        await hass.async_block_till_done()
        assert cache.updates == 1
