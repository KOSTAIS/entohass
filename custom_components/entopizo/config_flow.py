"""Config flow for Entopizo."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import EntopizoApi, EntopizoAuthError, EntopizoError
from .const import (
    CONF_API_HASH,
    CONF_TRACK_EVENTS,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TRACK_EVENTS,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.EMAIL)
        ),
        vol.Required(CONF_PASSWORD): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        ),
    }
)

REAUTH_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PASSWORD): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        ),
    }
)


class EntopizoConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Entopizo.

    The password is only used to obtain the user_api_hash token; it is never stored.
    """

    VERSION = 1

    async def _async_login(self, email: str, password: str) -> tuple[str | None, dict[str, str]]:
        api = EntopizoApi(async_get_clientsession(self.hass))
        try:
            return await api.login(email, password), {}
        except EntopizoAuthError:
            return None, {"base": "invalid_auth"}
        except EntopizoError:
            return None, {"base": "cannot_connect"}
        except Exception:
            _LOGGER.exception("Unexpected error logging in to Entopizo")
            return None, {"base": "unknown"}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the Entopizo account credentials."""
        errors: dict[str, str] = {}
        if user_input is not None:
            email = user_input[CONF_EMAIL].strip()
            await self.async_set_unique_id(email.lower())
            self._abort_if_unique_id_configured()

            api_hash, errors = await self._async_login(email, user_input[CONF_PASSWORD])
            if api_hash:
                return self.async_create_entry(
                    title=email, data={CONF_EMAIL: email, CONF_API_HASH: api_hash}
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                USER_SCHEMA, {CONF_EMAIL: user_input[CONF_EMAIL]} if user_input else None
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Handle a revoked token (e.g. after a password change)."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the password again and issue a new token."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            api_hash, errors = await self._async_login(
                entry.data[CONF_EMAIL], user_input[CONF_PASSWORD]
            )
            if api_hash:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_API_HASH: api_hash}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=REAUTH_SCHEMA,
            description_placeholders={"email": entry.data[CONF_EMAIL]},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> EntopizoOptionsFlow:
        """Return the options flow."""
        return EntopizoOptionsFlow()


class EntopizoOptionsFlow(OptionsFlow):
    """Polling interval and event options."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL,
                        max=MAX_SCAN_INTERVAL,
                        step=1,
                        unit_of_measurement="s",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_TRACK_EVENTS, default=DEFAULT_TRACK_EVENTS
                ): selector.BooleanSelector(),
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(schema, self.config_entry.options),
        )
