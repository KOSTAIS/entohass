"""Shared entity helpers for Entopizo."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import DOMAIN
from .coordinator import EntopizoConfigEntry, EntopizoCoordinator

BOOLEAN_VALUES = {
    "on": True,
    "off": False,
    "true": True,
    "false": False,
    "yes": True,
    "no": False,
    "open": True,
    "opened": True,
    "closed": False,
}
NUMERIC_RE = re.compile(r"^\s*(-?\d+(?:[.,]\d+)?)\s*(.*?)\s*$")


def tracker_sensors(device: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the platform-defined sensors of a device (ignition, battery, ...)."""
    return [s for s in device.get("sensors") or [] if isinstance(s, dict) and s.get("name")]


def sensor_key(sensor: dict[str, Any]) -> str:
    """Stable identifier for a platform sensor."""
    if sensor.get("id") is not None:
        return f"sensor_{sensor['id']}"
    return f"sensor_{slugify(str(sensor['name']))}"


def sensor_bool(sensor: dict[str, Any]) -> bool | None:
    """Interpret a platform sensor as on/off, or None if it isn't boolean."""
    if isinstance(sensor.get("val"), bool):
        return sensor["val"]
    value = sensor.get("value")
    if isinstance(value, str):
        return BOOLEAN_VALUES.get(value.strip().lower())
    return None


def parse_numeric(value: Any) -> tuple[float, str] | None:
    """Split values like "12.6V" into (12.6, "V")."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value), ""
    match = NUMERIC_RE.match(str(value))
    if not match:
        return None
    return float(match.group(1).replace(",", ".")), match.group(2)


def find_sensor(device: dict[str, Any], key: str) -> dict[str, Any] | None:
    """Look up a platform sensor of a device by its key."""
    return next((s for s in tracker_sensors(device) if sensor_key(s) == key), None)


class EntopizoEntity(CoordinatorEntity[EntopizoCoordinator]):
    """Base entity bound to one Entopizo tracker."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: EntopizoCoordinator, device_id: int, key: str) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{device_id}_{key}"
        device = coordinator.data[device_id]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(device_id))},
            name=device.get("name") or f"Tracker {device_id}",
            manufacturer="Entopizo",
            model=device.get("protocol"),
            configuration_url="https://go.entopizo.gr",
        )

    @property
    def device(self) -> dict[str, Any]:
        """Latest data for this tracker."""
        return self.coordinator.data.get(self._device_id, {})

    @property
    def available(self) -> bool:
        """Unavailable if the tracker disappears from the account."""
        return super().available and self._device_id in self.coordinator.data


def async_setup_dynamic_entities(
    entry: EntopizoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
    factory: Callable[[EntopizoCoordinator, int, dict[str, Any]], Iterable[Entity]],
) -> None:
    """Add entities now and whenever new trackers or sensors appear."""
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def _add_new() -> None:
        new: list[Entity] = []
        for device_id, device in coordinator.data.items():
            for entity in factory(coordinator, device_id, device):
                if entity.unique_id not in known:
                    known.add(entity.unique_id)
                    new.append(entity)
        if new:
            async_add_entities(new)

    _add_new()
    entry.async_on_unload(coordinator.async_add_listener(_add_new))
