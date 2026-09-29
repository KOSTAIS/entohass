"""GPS position of each Entopizo tracker."""

from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import EntopizoConfigEntry, EntopizoCoordinator, to_float
from .entity import EntopizoEntity, async_setup_dynamic_entities


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EntopizoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up one tracker entity per device."""

    def factory(
        coordinator: EntopizoCoordinator, device_id: int, device: dict[str, Any]
    ) -> list[EntopizoTracker]:
        return [EntopizoTracker(coordinator, device_id)]

    async_setup_dynamic_entities(entry, async_add_entities, factory)


class EntopizoTracker(EntopizoEntity, TrackerEntity):
    """Live position from get_devices."""

    _attr_name = None

    def __init__(self, coordinator: EntopizoCoordinator, device_id: int) -> None:
        super().__init__(coordinator, device_id, "tracker")

    @property
    def source_type(self) -> SourceType:
        """GPS receiver."""
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        """Last known latitude."""
        return to_float(self.device.get("lat"))

    @property
    def longitude(self) -> float | None:
        """Last known longitude."""
        return to_float(self.device.get("lng"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Extra position details."""
        device = self.device
        return {
            "address": device.get("address"),
            "speed": to_float(device.get("speed")),
            "course": to_float(device.get("course")),
            "altitude": to_float(device.get("altitude")),
            "status": device.get("online"),
            "last_update": device.get("time"),
            "entopizo_id": self._device_id,
        }
