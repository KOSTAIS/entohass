"""Binary sensors for Entopizo trackers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import STATUS_OFFLINE, STATUS_ONLINE
from .coordinator import EntopizoConfigEntry, EntopizoCoordinator, to_float
from .entity import (
    EntopizoEntity,
    async_setup_dynamic_entities,
    find_sensor,
    sensor_bool,
    sensor_key,
    tracker_sensors,
)


@dataclass(frozen=True, kw_only=True)
class EntopizoBinarySensorDescription(BinarySensorEntityDescription):
    """Describes a built-in Entopizo binary sensor."""

    value_fn: Callable[[dict[str, Any]], bool | None]


BINARY_SENSORS: tuple[EntopizoBinarySensorDescription, ...] = (
    EntopizoBinarySensorDescription(
        key="connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=lambda d: d.get("online") != STATUS_OFFLINE if d.get("online") else None,
    ),
    EntopizoBinarySensorDescription(
        key="moving",
        device_class=BinarySensorDeviceClass.MOVING,
        value_fn=lambda d: d.get("online") == STATUS_ONLINE and (to_float(d.get("speed")) or 0) > 0,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EntopizoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up built-in binary sensors and on/off platform sensors (ignition, doors...)."""

    def factory(
        coordinator: EntopizoCoordinator, device_id: int, device: dict[str, Any]
    ) -> list[Entity]:
        entities: list[Entity] = [
            EntopizoBinarySensor(coordinator, device_id, description)
            for description in BINARY_SENSORS
        ]
        entities.extend(
            EntopizoPlatformBinarySensor(coordinator, device_id, sensor)
            for sensor in tracker_sensors(device)
            if sensor_bool(sensor) is not None
        )
        return entities

    async_setup_dynamic_entities(entry, async_add_entities, factory)


class EntopizoBinarySensor(EntopizoEntity, BinarySensorEntity):
    """A state derived from the get_devices payload."""

    entity_description: EntopizoBinarySensorDescription

    def __init__(
        self,
        coordinator: EntopizoCoordinator,
        device_id: int,
        description: EntopizoBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator, device_id, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Current state."""
        return self.entity_description.value_fn(self.device)


class EntopizoPlatformBinarySensor(EntopizoEntity, BinarySensorEntity):
    """An on/off sensor configured on the Entopizo platform."""

    def __init__(
        self, coordinator: EntopizoCoordinator, device_id: int, sensor: dict[str, Any]
    ) -> None:
        self._key = sensor_key(sensor)
        super().__init__(coordinator, device_id, self._key)
        self._attr_name = str(sensor["name"])
        if "ignition" in self._attr_name.lower() or sensor.get("type") in ("acc", "ignition"):
            self._attr_icon = "mdi:engine"
        elif "door" in self._attr_name.lower() or sensor.get("type") == "door":
            self._attr_device_class = BinarySensorDeviceClass.DOOR

    @property
    def is_on(self) -> bool | None:
        """Current state."""
        sensor = find_sensor(self.device, self._key)
        return sensor_bool(sensor) if sensor else None
