"""Diagnostics download."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from . import TesiraConfigEntry
from .coordinator import key_text

TO_REDACT = {CONF_HOST, CONF_USERNAME, CONF_PASSWORD}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: TesiraConfigEntry
) -> dict[str, Any]:
    """Config (host hidden), connection state, last values and the last protocol lines."""
    coordinator = entry.runtime_data
    return {
        "config": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "connected": coordinator.connected,
        "last_error": coordinator.client.last_error,
        "values": {key_text(key): value for key, value in sorted(coordinator.values.items())},
        "protocol_log": list(coordinator.client.protocol_log),
    }
