"""Diagnostics support for Entopizo."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .coordinator import EntopizoConfigEntry
from .entity import parse_numeric, sensor_bool, sensor_key, tracker_sensors

# Allow-list: the API returns much more (IMEI, SIM, VIN, plate, driver contact
# details, raw position history...), none of which is needed to debug the
# integration, so only these non-identifying fields are exported.
DEVICE_FIELDS = (
    "online",
    "time",
    "speed",
    "course",
    "altitude",
    "protocol",
    "total_distance",
    "stop_duration",
)


def _sensor(sensor: dict[str, Any]) -> dict[str, Any]:
    numeric = parse_numeric(sensor.get("value"))
    if sensor_bool(sensor) is not None:
        kind = "binary"
    elif numeric is not None:
        kind = "numeric"
    else:
        kind = "text"
    return {
        "key": sensor_key(sensor),
        "type": sensor.get("type"),
        "kind": kind,
        "unit": numeric[1] or None if numeric else None,
    }


def _device(device: dict[str, Any]) -> dict[str, Any]:
    return {
        "has_position": device.get("lat") is not None and device.get("lng") is not None,
        **{field: device.get(field) for field in DEVICE_FIELDS},
        "sensors": [_sensor(sensor) for sensor in tracker_sensors(device)],
        "keys": sorted(device),
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: EntopizoConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry.

    Contains no token, email, device names, ids, positions or sensor values.
    """
    coordinator = entry.runtime_data
    return {
        "options": dict(entry.options),
        "imperial": coordinator.imperial,
        "track_events": coordinator.track_events,
        "last_update_success": coordinator.last_update_success,
        "devices": [_device(device) for device in coordinator.data.values()],
    }
