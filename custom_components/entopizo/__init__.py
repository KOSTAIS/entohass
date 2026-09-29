"""The Entopizo GPS tracking integration."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_DEVICE_ID, Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service import async_register_admin_service
from homeassistant.helpers.typing import ConfigType

from .api import EntopizoApi, EntopizoError
from .const import (
    ATTR_COMMAND_TYPE,
    ATTR_DATA,
    CONF_API_HASH,
    DOMAIN,
    SERVICE_SEND_COMMAND,
)
from .coordinator import EntopizoConfigEntry, EntopizoCoordinator

PLATFORMS = [Platform.BINARY_SENSOR, Platform.DEVICE_TRACKER, Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SEND_COMMAND_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Required(ATTR_COMMAND_TYPE): cv.string,
        vol.Optional(ATTR_DATA): cv.string,
    }
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the integration's services."""

    async def async_send_command(call: ServiceCall) -> ServiceResponse:
        device = dr.async_get(hass).async_get(call.data[ATTR_DEVICE_ID])
        if device is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="device_not_found"
            )
        tracker_id = next((ident for domain, ident in device.identifiers if domain == DOMAIN), None)
        entry: EntopizoConfigEntry | None = next(
            (
                candidate
                for entry_id in device.config_entries
                if (candidate := hass.config_entries.async_get_entry(entry_id))
                and candidate.domain == DOMAIN
                and candidate.state is ConfigEntryState.LOADED
            ),
            None,
        )
        if tracker_id is None or entry is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="device_not_found"
            )

        try:
            result = await entry.runtime_data.api.send_gprs_command(
                int(tracker_id), call.data[ATTR_COMMAND_TYPE], call.data.get(ATTR_DATA)
            )
        except EntopizoError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        return {"status": result.get("status"), "message": result.get("message")}

    # Commands can immobilize a vehicle, so only administrators may call this.
    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_SEND_COMMAND,
        async_send_command,
        schema=SEND_COMMAND_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: EntopizoConfigEntry) -> bool:
    """Set up Entopizo from a config entry."""
    api = EntopizoApi(async_get_clientsession(hass), entry.data[CONF_API_HASH])
    coordinator = EntopizoCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: EntopizoConfigEntry) -> None:
    """Reload when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: EntopizoConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
