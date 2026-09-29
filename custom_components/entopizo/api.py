"""Minimal async client for the Entopizo REST API (https://go.entopizo.gr/api)."""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp

from .const import BASE_URL

REQUEST_TIMEOUT = 30


class EntopizoError(Exception):
    """Base error for the Entopizo API."""


class EntopizoConnectionError(EntopizoError):
    """The API could not be reached or returned an unexpected response."""


class EntopizoAuthError(EntopizoError):
    """Credentials or user_api_hash were rejected."""


class EntopizoApi:
    """Thin wrapper around the endpoints used by the integration.

    Every request except ``login`` is authenticated by passing the static
    ``user_api_hash`` token as a parameter (no Bearer headers).
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        api_hash: str | None = None,
        base_url: str = BASE_URL,
    ) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")
        self.api_hash = api_hash

    async def login(self, email: str, password: str) -> str:
        """Exchange account credentials for the user_api_hash token."""
        result = await self._request(
            "POST",
            "login",
            data={"email": email, "password": password},
            auth=False,
            auth_error_on_status_0=True,
        )
        api_hash = result.get("user_api_hash") if isinstance(result, dict) else None
        if not api_hash:
            raise EntopizoAuthError("Login did not return a user_api_hash")
        self.api_hash = api_hash
        return api_hash

    async def get_devices(self) -> list[dict[str, Any]]:
        """Return all devices, flattened out of their groups."""
        result = await self._request("GET", "get_devices", params={"lang": "en"})
        if not isinstance(result, list):
            raise EntopizoConnectionError("Unexpected get_devices response")
        devices: list[dict[str, Any]] = []
        for group in result:
            if not isinstance(group, dict):
                continue
            for item in group.get("items") or []:
                if isinstance(item, dict) and item.get("id") is not None:
                    devices.append(item)
        return devices

    async def get_events(self, page: int = 1) -> list[dict[str, Any]]:
        """Return a page of events, newest first."""
        result = await self._request("GET", "get_events", params={"page": page, "lang": "en"})
        items = result.get("items") if isinstance(result, dict) else None
        if isinstance(items, dict):
            items = items.get("data")
        return [item for item in items or [] if isinstance(item, dict)]

    async def get_setup_data(self) -> dict[str, Any]:
        """Return account settings (timezone, distance / capacity units, ...)."""
        result = await self._request("GET", "edit_setup_data")
        return result if isinstance(result, dict) else {}

    async def send_gprs_command(
        self, device_id: int, command_type: str, data: str | None = None
    ) -> dict[str, Any]:
        """Send a GPRS command to a device."""
        payload: dict[str, Any] = {"device_id": device_id, "type": command_type}
        if data is not None:
            payload["data"] = data
        result = await self._request("POST", "send_gprs_command", data=payload)
        return result if isinstance(result, dict) else {}

    async def _request(
        self,
        method: str,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        auth: bool = True,
        auth_error_on_status_0: bool = False,
    ) -> Any:
        params = dict(params or {})
        if auth:
            if not self.api_hash:
                raise EntopizoAuthError("No user_api_hash available")
            if method == "GET":
                params["user_api_hash"] = self.api_hash
            else:
                data = {**(data or {}), "user_api_hash": self.api_hash}

        url = f"{self._base_url}/{endpoint}"
        try:
            async with self._session.request(
                method,
                url,
                params=params or None,
                data=data,
                headers={"Accept": "application/json"},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as resp:
                if resp.status == 401:
                    raise EntopizoAuthError("user_api_hash is invalid or revoked")
                if resp.status == 429:
                    raise EntopizoConnectionError("Rate limit exceeded")
                if resp.status >= 400:
                    raise EntopizoConnectionError(f"{endpoint} returned HTTP {resp.status}")
                try:
                    result = await resp.json(content_type=None)
                except (aiohttp.ContentTypeError, ValueError) as err:
                    raise EntopizoConnectionError(f"{endpoint} returned invalid JSON") from err
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise EntopizoConnectionError(f"Error requesting {endpoint}: {err}") from err

        if isinstance(result, dict) and result.get("status") == 0:
            message = result.get("message") or f"{endpoint} failed"
            if auth_error_on_status_0:
                raise EntopizoAuthError(message)
            raise EntopizoError(message)
        return result
