"""Data update coordinator for Entopizo."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import EntopizoApi, EntopizoAuthError, EntopizoError
from .const import (
    CONF_TRACK_EVENTS,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TRACK_EVENTS,
    DOMAIN,
    EVENT_ENTOPIZO,
)

_LOGGER = logging.getLogger(__name__)

type EntopizoConfigEntry = ConfigEntry[EntopizoCoordinator]

TIME_FORMATS = ("%d-%m-%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d-%m-%Y %H:%M")


def parse_time(value: Any) -> datetime | None:
    """Parse an API timestamp (account timezone, assumed to match Home Assistant's)."""
    if not isinstance(value, str) or not value.strip():
        return None
    for fmt in TIME_FORMATS:
        try:
            parsed = datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
        return parsed.replace(tzinfo=dt_util.get_default_time_zone())
    return None


def to_float(value: Any) -> float | None:
    """Convert API numbers (sometimes sent as strings) to float."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _find_key(data: Any, key: str) -> Any:
    """Depth-first search for a key in a nested JSON structure."""
    if isinstance(data, dict):
        if key in data and not isinstance(data[key], (dict, list)):
            return data[key]
        for value in data.values():
            found = _find_key(value, key)
            if found is not None:
                return found
    elif isinstance(data, list):
        for value in data:
            found = _find_key(value, key)
            if found is not None:
                return found
    return None


class EntopizoCoordinator(DataUpdateCoordinator[dict[int, dict[str, Any]]]):
    """Polls get_devices and relays new events to the Home Assistant bus."""

    config_entry: EntopizoConfigEntry

    def __init__(self, hass: HomeAssistant, entry: EntopizoConfigEntry, api: EntopizoApi) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
        )
        self.api = api
        self.track_events: bool = entry.options.get(CONF_TRACK_EVENTS, DEFAULT_TRACK_EVENTS)
        self.imperial = False
        self._last_event_id: int | None = None

    async def _async_setup(self) -> None:
        """Read the account's unit settings once."""
        try:
            setup = await self.api.get_setup_data()
        except EntopizoAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except EntopizoError as err:
            _LOGGER.debug("Could not read account settings, assuming km: %s", err)
            return
        unit = _find_key(setup, "unit_of_distance")
        self.imperial = isinstance(unit, str) and unit.lower().startswith("mi")

    async def _async_update_data(self) -> dict[int, dict[str, Any]]:
        try:
            devices = await self.api.get_devices()
        except EntopizoAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except EntopizoError as err:
            raise UpdateFailed(f"Error fetching Entopizo devices: {err}") from err

        data = {int(device["id"]): device for device in devices}

        if self.track_events:
            await self._async_fire_new_events(data)

        return data

    async def _async_fire_new_events(self, devices: dict[int, dict[str, Any]]) -> None:
        """Fire entopizo_event for events newer than the last one seen."""
        try:
            events = await self.api.get_events()
        except EntopizoAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except EntopizoError as err:
            _LOGGER.debug("Could not fetch events: %s", err)
            return

        ids = [int(e["id"]) for e in events if str(e.get("id", "")).isdigit()]
        if not ids:
            if self._last_event_id is None:
                self._last_event_id = 0
            return

        if self._last_event_id is None:
            # First poll: remember where we are, don't replay history.
            self._last_event_id = max(ids)
            return

        new_events = [
            e
            for e in events
            if str(e.get("id", "")).isdigit() and int(e["id"]) > self._last_event_id
        ]
        for event in sorted(new_events, key=lambda e: int(e["id"])):
            device_id = event.get("device_id")
            device = devices.get(int(device_id)) if str(device_id).isdigit() else None
            self.hass.bus.async_fire(
                EVENT_ENTOPIZO,
                {
                    "event_id": int(event["id"]),
                    "device_id": device_id,
                    "device_name": event.get("device_name") or (device or {}).get("name"),
                    "type": event.get("type"),
                    "message": event.get("message"),
                    "speed": event.get("speed"),
                    "latitude": to_float(event.get("latitude")),
                    "longitude": to_float(event.get("longitude")),
                    "address": event.get("address"),
                    "time": event.get("time"),
                },
            )
        self._last_event_id = max(self._last_event_id, *ids)
