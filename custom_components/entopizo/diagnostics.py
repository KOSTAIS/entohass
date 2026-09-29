"""Diagnostics support for Entopizo."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_EMAIL
from homeassistant.core import HomeAssistant

from .const import CONF_API_HASH
from .coordinator import EntopizoConfigEntry

TO_REDACT = {
    CONF_API_HASH,
    CONF_EMAIL,
    "title",
    "unique_id",
    "lat",
    "lng",
    "latitude",
    "longitude",
    "address",
    "tail",
    "imei",
    "sim_number",
    "plate_number",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: EntopizoConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "imperial": coordinator.imperial,
        "devices": async_redact_data(list(coordinator.data.values()), TO_REDACT),
    }
