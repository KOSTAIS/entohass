"""Constants for the Entopizo integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "entopizo"

BASE_URL: Final = "https://go.entopizo.gr/api"

CONF_API_HASH: Final = "api_hash"
CONF_TRACK_EVENTS: Final = "track_events"

DEFAULT_SCAN_INTERVAL: Final = 60
MIN_SCAN_INTERVAL: Final = 15
MAX_SCAN_INTERVAL: Final = 3600
DEFAULT_TRACK_EVENTS: Final = True

# Fired on the Home Assistant event bus for every new Entopizo event
# (overspeed, geofence in/out, ignition, SOS, ...).
EVENT_ENTOPIZO: Final = "entopizo_event"

SERVICE_SEND_COMMAND: Final = "send_command"
ATTR_COMMAND_TYPE: Final = "command_type"
ATTR_DATA: Final = "data"

# Values of the "online" field in get_devices.
STATUS_ONLINE: Final = "online"
STATUS_ACK: Final = "ack"
STATUS_OFFLINE: Final = "offline"
STATUS_ENGINE: Final = "engine"
DEVICE_STATUSES: Final = [STATUS_ONLINE, STATUS_ACK, STATUS_OFFLINE, STATUS_ENGINE]
