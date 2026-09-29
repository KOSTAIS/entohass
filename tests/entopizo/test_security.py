"""Security-related tests for Entopizo."""

from __future__ import annotations

import json

import aiohttp
import pytest
from homeassistant.auth.models import User
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import Unauthorized
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.entopizo.api import EntopizoApi, EntopizoConnectionError
from custom_components.entopizo.const import BASE_URL, DOMAIN
from custom_components.entopizo.diagnostics import async_get_config_entry_diagnostics

from .test_init import entry, mock_api  # noqa: F401

SECRET = "HASH"


async def test_connection_errors_do_not_leak_token(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(
        f"{BASE_URL}/get_devices",
        exc=aiohttp.ClientConnectionError(f"{BASE_URL}/get_devices?user_api_hash={SECRET}"),
    )
    api = EntopizoApi(async_get_clientsession(hass), SECRET)
    with pytest.raises(EntopizoConnectionError) as err:
        await api.get_devices()
    assert SECRET not in str(err.value)
    assert err.value.__cause__ is None
    assert err.value.__suppress_context__


async def test_redirects_are_rejected(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(
        f"{BASE_URL}/login",
        status=302,
        headers={"Location": "http://attacker.example/steal"},
    )
    api = EntopizoApi(async_get_clientsession(hass))
    with pytest.raises(EntopizoConnectionError):
        await api.login("user@example.com", "secret")


async def test_send_command_requires_admin(
    hass: HomeAssistant,
    entry: MockConfigEntry,  # noqa: F811
    aioclient_mock: AiohttpClientMocker,
    hass_read_only_user: User,
) -> None:
    mock_api(aioclient_mock)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, "1042")})

    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            DOMAIN,
            "send_command",
            {"device_id": device.id, "command_type": "engineStop"},
            blocking=True,
            context=Context(user_id=hass_read_only_user.id),
        )
    assert not any("send_gprs_command" in str(call[1]) for call in aioclient_mock.mock_calls)


async def test_diagnostics_contain_no_personal_data(
    hass: HomeAssistant,
    entry: MockConfigEntry,  # noqa: F811
    aioclient_mock: AiohttpClientMocker,
) -> None:
    mock_api(aioclient_mock)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    dump = json.dumps(await async_get_config_entry_diagnostics(hass, entry), default=str)
    for secret in (
        SECRET,
        "user@example.com",
        "Truck",
        "37.97",
        "23.73",
        "Lampraki",
        "Nikos",
        "1042",
    ):
        assert secret not in dump
    assert '"kind": "binary"' in dump
    assert '"unit": "V"' in dump
