"""Tests for Entopizo setup, entities, events and services."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_EMAIL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.entopizo.const import BASE_URL, CONF_API_HASH, DOMAIN

DEVICES = [
    {
        "id": 0,
        "title": "Ungrouped",
        "items": [
            {
                "id": 1042,
                "name": "Truck YZX-1234",
                "online": "online",
                "time": "05-07-2026 14:32:10",
                "speed": 54,
                "course": 118,
                "lat": "37.97552",
                "lng": 23.73481,
                "altitude": 92,
                "address": "132 Gr. Lampraki Ave, Korydallos",
                "protocol": "teltonika",
                "total_distance": 48211.7,
                "stop_duration": "0s",
                "sensors": [
                    {"name": "Ignition", "value": "On"},
                    {"name": "Battery", "value": "12.6V"},
                    {"name": "Driver", "value": "Nikos"},
                ],
            }
        ],
    }
]


def events_payload(*ids: int) -> dict[str, Any]:
    return {
        "items": {
            "data": [
                {
                    "id": event_id,
                    "device_id": 1042,
                    "type": "overspeed",
                    "message": "Speed limit exceeded",
                    "speed": 112,
                    "latitude": 38.0142,
                    "longitude": 23.665,
                    "address": "Athinon Ave, Athens",
                    "time": "04-07-2026 16:44:31",
                }
                for event_id in sorted(ids, reverse=True)
            ],
            "current_page": 1,
            "last_page": 1,
        }
    }


@pytest.fixture
def entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="user@example.com",
        title="user@example.com",
        data={CONF_EMAIL: "user@example.com", CONF_API_HASH: "HASH"},
    )
    entry.add_to_hass(hass)
    return entry


def mock_api(aioclient_mock: AiohttpClientMocker, event_ids: tuple[int, ...] = (10,)) -> None:
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{BASE_URL}/edit_setup_data", json={"unit_of_distance": "km"})
    aioclient_mock.get(f"{BASE_URL}/get_devices", json=DEVICES)
    aioclient_mock.get(f"{BASE_URL}/get_events", json=events_payload(*event_ids))


async def test_setup_creates_entities(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    mock_api(aioclient_mock)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    tracker = hass.states.get("device_tracker.truck_yzx_1234")
    assert tracker is not None
    assert tracker.attributes["latitude"] == 37.97552
    assert tracker.attributes["longitude"] == 23.73481
    assert tracker.attributes["address"] == "132 Gr. Lampraki Ave, Korydallos"

    assert hass.states.get("sensor.truck_yzx_1234_speed").state == "54.0"
    assert hass.states.get("sensor.truck_yzx_1234_status").state == "online"
    assert hass.states.get("sensor.truck_yzx_1234_odometer").state == "48211.7"
    battery = hass.states.get("sensor.truck_yzx_1234_battery")
    assert battery.state == "12.6"
    assert battery.attributes["unit_of_measurement"] == "V"
    assert hass.states.get("sensor.truck_yzx_1234_driver").state == "Nikos"
    assert hass.states.get("binary_sensor.truck_yzx_1234_ignition").state == "on"
    assert hass.states.get("binary_sensor.truck_yzx_1234_connectivity").state == "on"
    assert hass.states.get("binary_sensor.truck_yzx_1234_moving").state == "on"

    # Only the token is sent, never the password.
    for _method, url, _data, _headers in aioclient_mock.mock_calls:
        assert url.query["user_api_hash"] == "HASH"

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_new_events_are_fired(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    mock_api(aioclient_mock, (10,))
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    events = async_capture_events(hass, "entopizo_event")

    mock_api(aioclient_mock, (10, 11, 12))
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
    await hass.async_block_till_done()

    assert [e.data["event_id"] for e in events] == [11, 12]
    assert events[0].data["device_name"] == "Truck YZX-1234"
    assert events[0].data["type"] == "overspeed"


async def test_revoked_token_starts_reauth(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{BASE_URL}/edit_setup_data", status=401)
    aioclient_mock.get(f"{BASE_URL}/get_devices", status=401)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [flow["context"]["source"] for flow in flows] == ["reauth"]


async def test_send_command(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    mock_api(aioclient_mock)
    aioclient_mock.post(
        f"{BASE_URL}/send_gprs_command", json={"status": 1, "message": "Command sent"}
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, "1042")})
    result = await hass.services.async_call(
        DOMAIN,
        "send_command",
        {"device_id": device.id, "command_type": "custom", "data": "setdigout 1"},
        blocking=True,
        return_response=True,
    )
    assert result == {"status": 1, "message": "Command sent"}
    _method, _url, data, _headers = aioclient_mock.mock_calls[-1]
    assert data == {
        "device_id": 1042,
        "type": "custom",
        "data": "setdigout 1",
        "user_api_hash": "HASH",
    }
