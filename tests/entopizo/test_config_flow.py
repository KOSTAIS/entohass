"""Tests for the Entopizo config flow."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.entopizo.const import BASE_URL, CONF_API_HASH, DOMAIN

LOGIN_URL = f"{BASE_URL}/login"
CREDENTIALS = {CONF_EMAIL: "User@Example.com", CONF_PASSWORD: "secret"}


async def test_user_flow_stores_token_not_password(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(LOGIN_URL, json={"status": 1, "user_api_hash": "$2y$10$HASH"})

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDENTIALS)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_EMAIL: "User@Example.com", CONF_API_HASH: "$2y$10$HASH"}
    assert result["result"].unique_id == "user@example.com"
    assert aioclient_mock.mock_calls[0][2] == {
        "email": "User@Example.com",
        "password": "secret",
    }


async def test_user_flow_invalid_auth(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(LOGIN_URL, json={"status": 0, "message": "Wrong email or password"})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDENTIALS)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_user_flow_cannot_connect(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(LOGIN_URL, status=500)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDENTIALS)
    assert result["errors"] == {"base": "cannot_connect"}


async def test_duplicate_account_aborts(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    MockConfigEntry(domain=DOMAIN, unique_id="user@example.com").add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDENTIALS)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_updates_token(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="user@example.com",
        data={CONF_EMAIL: "user@example.com", CONF_API_HASH: "OLD"},
    )
    entry.add_to_hass(hass)
    aioclient_mock.post(LOGIN_URL, json={"status": 1, "user_api_hash": "NEW"})
    aioclient_mock.get(f"{BASE_URL}/edit_setup_data", json={})
    aioclient_mock.get(f"{BASE_URL}/get_devices", json=[])
    aioclient_mock.get(f"{BASE_URL}/get_events", json={"items": {"data": []}})

    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "new-secret"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_API_HASH] == "NEW"


async def test_options_flow(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="user@example.com",
        data={CONF_EMAIL: "user@example.com", CONF_API_HASH: "HASH"},
    )
    entry.add_to_hass(hass)
    aioclient_mock.get(f"{BASE_URL}/edit_setup_data", json={})
    aioclient_mock.get(f"{BASE_URL}/get_devices", json=[])
    aioclient_mock.get(f"{BASE_URL}/get_events", json={"items": {"data": []}})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"scan_interval": 120, "track_events": False}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options == {"scan_interval": 120, "track_events": False}
    assert entry.runtime_data.update_interval.total_seconds() == 120
    assert entry.runtime_data.track_events is False
