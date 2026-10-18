"""Base entity for the ILIFE Clean (Tuya) backend. Mirrors entity.py."""
from __future__ import annotations

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .tuya_api import (
    TuyaCommandRefused,
    TuyaCommandUnconfirmed,
    TuyaError,
    TuyaOfflineError,
)

# Failures with a translated message; any other TuyaError shows its own text.
_ERROR_KEYS = (
    (TuyaOfflineError, "device_offline"),
    (TuyaCommandRefused, "local_refused"),
    (TuyaCommandUnconfirmed, "local_unconfirmed"),
)


def tuya_command_error(err: TuyaError) -> HomeAssistantError:
    """The error a failed command shows the user, raised `from err`."""
    for error_type, key in _ERROR_KEYS:
        if isinstance(err, error_type):
            return HomeAssistantError(translation_domain=DOMAIN, translation_key=key)
    return HomeAssistantError(str(err))


def tuya_device_info(device) -> DeviceInfo:
    dev = device.device or {}
    return DeviceInfo(
        identifiers={(DOMAIN, device.device_id)},
        manufacturer="ILIFE",
        model=dev.get("product_name") or dev.get("category") or "Vacuum",
        name=dev.get("name") or dev.get("product_name") or "ILIFE",
    )


class TuyaEntity(CoordinatorEntity):
    """Common base: entity naming + availability tied to the vacuum being online."""

    _attr_has_entity_name = True

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self.api = coordinator.api
        self._attr_device_info = tuya_device_info(self.api)
