"""Sensors for Entopizo trackers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    DEGREE,
    EntityCategory,
    UnitOfElectricPotential,
    UnitOfLength,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DEVICE_STATUSES
from .coordinator import EntopizoConfigEntry, EntopizoCoordinator, parse_time, to_float
from .entity import (
    EntopizoEntity,
    async_setup_dynamic_entities,
    find_sensor,
    parse_numeric,
    sensor_bool,
    sensor_key,
    tracker_sensors,
)

type StateType = str | float | datetime | None


@dataclass(frozen=True, kw_only=True)
class EntopizoSensorDescription(SensorEntityDescription):
    """Describes a built-in Entopizo sensor."""

    value_fn: Callable[[dict[str, Any]], StateType]
    imperial_unit: str | None = None


def _status(device: dict[str, Any]) -> str | None:
    status = device.get("online")
    return status if status in DEVICE_STATUSES else None


SENSORS: tuple[EntopizoSensorDescription, ...] = (
    EntopizoSensorDescription(
        key="speed",
        translation_key="speed",
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        imperial_unit=UnitOfSpeed.MILES_PER_HOUR,
        value_fn=lambda d: to_float(d.get("speed")),
    ),
    EntopizoSensorDescription(
        key="course",
        translation_key="course",
        native_unit_of_measurement=DEGREE,
        value_fn=lambda d: to_float(d.get("course")),
    ),
    EntopizoSensorDescription(
        key="altitude",
        translation_key="altitude",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfLength.METERS,
        entity_registry_enabled_default=False,
        value_fn=lambda d: to_float(d.get("altitude")),
    ),
    EntopizoSensorDescription(
        key="odometer",
        translation_key="odometer",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        imperial_unit=UnitOfLength.MILES,
        suggested_display_precision=1,
        value_fn=lambda d: to_float(d.get("total_distance")),
    ),
    EntopizoSensorDescription(
        key="address",
        translation_key="address",
        value_fn=lambda d: (d.get("address") or None) and str(d["address"])[:255],
    ),
    EntopizoSensorDescription(
        key="status",
        translation_key="status",
        device_class=SensorDeviceClass.ENUM,
        options=DEVICE_STATUSES,
        value_fn=_status,
    ),
    EntopizoSensorDescription(
        key="last_update",
        translation_key="last_update",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: parse_time(d.get("time")),
    ),
    EntopizoSensorDescription(
        key="stop_duration",
        translation_key="stop_duration",
        value_fn=lambda d: d.get("stop_duration") or None,
    ),
)

UNIT_DEVICE_CLASSES = {
    UnitOfElectricPotential.VOLT: SensorDeviceClass.VOLTAGE,
    UnitOfTemperature.CELSIUS: SensorDeviceClass.TEMPERATURE,
    UnitOfTemperature.FAHRENHEIT: SensorDeviceClass.TEMPERATURE,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EntopizoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up built-in sensors and one sensor per non-boolean platform sensor."""

    def factory(
        coordinator: EntopizoCoordinator, device_id: int, device: dict[str, Any]
    ) -> list[Entity]:
        entities: list[Entity] = [
            EntopizoSensor(coordinator, device_id, description) for description in SENSORS
        ]
        entities.extend(
            EntopizoPlatformSensor(coordinator, device_id, sensor)
            for sensor in tracker_sensors(device)
            if sensor_bool(sensor) is None
        )
        return entities

    async_setup_dynamic_entities(entry, async_add_entities, factory)


class EntopizoSensor(EntopizoEntity, SensorEntity):
    """A value taken directly from the get_devices payload."""

    entity_description: EntopizoSensorDescription

    def __init__(
        self,
        coordinator: EntopizoCoordinator,
        device_id: int,
        description: EntopizoSensorDescription,
    ) -> None:
        super().__init__(coordinator, device_id, description.key)
        self.entity_description = description
        if coordinator.imperial and description.imperial_unit:
            self._attr_native_unit_of_measurement = description.imperial_unit

    @property
    def native_value(self) -> StateType:
        """Current value."""
        return self.entity_description.value_fn(self.device)


class EntopizoPlatformSensor(EntopizoEntity, SensorEntity):
    """A sensor configured on the Entopizo platform (battery, fuel, temperature, ...)."""

    def __init__(
        self, coordinator: EntopizoCoordinator, device_id: int, sensor: dict[str, Any]
    ) -> None:
        self._key = sensor_key(sensor)
        super().__init__(coordinator, device_id, self._key)
        self._attr_name = str(sensor["name"])
        numeric = parse_numeric(sensor.get("value"))
        self._numeric = numeric is not None
        if numeric is not None:
            unit = numeric[1] or None
            self._attr_native_unit_of_measurement = unit
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_device_class = UNIT_DEVICE_CLASSES.get(unit)

    @property
    def native_value(self) -> str | float | None:
        """Current value, numeric when the platform reports a number."""
        sensor = find_sensor(self.device, self._key)
        if sensor is None:
            return None
        value = sensor.get("value")
        if self._numeric:
            numeric = parse_numeric(value)
            return numeric[0] if numeric else None
        return None if value in (None, "") else str(value)[:255]
