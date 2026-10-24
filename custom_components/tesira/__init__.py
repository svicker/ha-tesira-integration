"""Biamp Tesira integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant

from .const import CONFIG_VERSION, DEFAULT_ZONES, OLD_DUCKER_AUSSEN_SITZEN, OPT_ZONES
from .coordinator import TesiraCoordinator
from .options import default_options, parse_options

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.MEDIA_PLAYER, Platform.SWITCH, Platform.NUMBER]

type TesiraConfigEntry = ConfigEntry[TesiraCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: TesiraConfigEntry) -> bool:
    """Set up one Tesira device.

    A device that is offline does not fail the setup: the entities stay
    unavailable and the client keeps retrying in the background.
    """
    coordinator = TesiraCoordinator(hass, entry, parse_options(entry.options))
    entry.runtime_data = coordinator

    async def _async_shutdown(_event: Event) -> None:
        await coordinator.async_stop()

    entry.async_on_unload(coordinator.async_stop)
    entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_shutdown))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    coordinator.async_start()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TesiraConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: TesiraConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate entries step by step: 1 -> 2 -> 3."""
    if entry.version > CONFIG_VERSION:
        return False
    if entry.version == 1:
        # Old integration: no options, unique_id was host:port.
        options = {**default_options().to_dict(), **entry.options}
        hass.config_entries.async_update_entry(
            entry,
            options=options,
            unique_id=str(entry.data[CONF_HOST]).lower(),
            version=2,
        )
        _LOGGER.info("Migrated Tesira config entry to version 2")
    if entry.version == 2:
        hass.config_entries.async_update_entry(
            entry, options=_migrate_options_v3(entry.options), version=3
        )
        _LOGGER.info("Migrated Tesira config entry to version 3")
    return True


def _migrate_options_v3(stored: Mapping[str, Any]) -> dict[str, Any]:
    """Fill empty gates with the defaults and rename the Außen-Sitzen ducker.

    Values the user has set are never overwritten.
    """
    options = dict(stored)
    zones = {key: dict(zone) for key, zone in (stored.get(OPT_ZONES) or {}).items()}
    for key, zone in zones.items():
        default = DEFAULT_ZONES.get(key)
        if default is not None and not zone.get("gate"):
            zone["gate"] = default[3]
        if key == "ela_aussen_sitzen" and zone.get("ducker") == OLD_DUCKER_AUSSEN_SITZEN:
            zone["ducker"] = default[4] if default else zone["ducker"]
    if zones:
        options[OPT_ZONES] = zones
    return options
