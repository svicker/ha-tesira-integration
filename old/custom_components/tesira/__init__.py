"""Biamp Tesira Home Assistant Integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant

from .client import TesiraClient
from .const import (
    ATTR_LEVEL,
    ATTR_MUTE,
    ATTR_SOURCE_SELECTION,
    DOMAIN,
    MAX_LEVEL,
    MIN_LEVEL,
    PLAYER_ZONES,
    SOURCES_REVERSE,
    ZONE_LEVEL_INSTANCES,
    ZONE_MUTE_INSTANCES,
    ZONE_SOURCE_INSTANCES,
    ZONE_NAMES,
)

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.MEDIA_PLAYER]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = TesiraCoordinator(hass, entry.data[CONF_HOST], entry.data[CONF_PORT])
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await coordinator.start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator: TesiraCoordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.stop()
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


class TesiraCoordinator:
    """Manages state and communication for one Tesira device."""

    def __init__(self, hass: HomeAssistant, host: str, port: int) -> None:
        self.hass = hass
        self.levels:  dict[str, float] = {}
        self.mutes:   dict[str, bool]  = {}
        self.sources: dict[str, int]   = {}   # per-zone source index

        self._listeners: list[Any] = []
        self._client = TesiraClient(host, port, self._on_state_change)

    async def start(self) -> None:
        await self._client.start()

    async def stop(self) -> None:
        await self._client.stop()

    def register_listener(self, listener: Any) -> None:
        self._listeners.append(listener)

    def unregister_listener(self, listener: Any) -> None:
        self._listeners.remove(listener)

    # ------------------------------------------------------------------
    # State callback
    # ------------------------------------------------------------------

    def _on_state_change(self, instance: str, attribute: str, value: Any) -> None:
        if instance == "__connected__":
            self.hass.async_create_task(self._initialize())
            return

        if attribute == ATTR_LEVEL:
            zones = self._zones_for(instance, ZONE_LEVEL_INSTANCES)
            if zones:
                for zone in zones:
                    self.levels[zone] = float(value)
                self._notify()

        elif attribute == ATTR_MUTE:
            zones = self._zones_for(instance, ZONE_MUTE_INSTANCES)
            if zones:
                for zone in zones:
                    self.mutes[zone] = bool(value)
                self._notify()

        elif attribute == ATTR_SOURCE_SELECTION:
            zones = self._zones_for(instance, ZONE_SOURCE_INSTANCES)
            if zones:
                for zone in zones:
                    self.sources[zone] = int(value)
                self._notify()

    def _zones_for(self, instance: str, mapping: dict) -> list[str]:
        """Return all zone keys whose instance tag matches (multiple zones
        can share the same Tesira block, e.g. a shared source router)."""
        return [zone for zone, inst in mapping.items() if inst == instance]

    def _notify(self) -> None:
        for listener in self._listeners:
            listener.schedule_update_ha_state(True)

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    async def _initialize(self) -> None:
        _LOGGER.debug("Initializing Tesira state")

        for zone in PLAYER_ZONES:
            # Level
            inst_l = ZONE_LEVEL_INSTANCES.get(zone)
            if inst_l:
                try:
                    val = await self._client.get_attribute(inst_l, ATTR_LEVEL)
                    if val is not None:
                        self.levels[zone] = float(val)
                    await self._client.subscribe(inst_l, ATTR_LEVEL, inst_l)
                except Exception as exc:
                    _LOGGER.warning("Level read failed %s: %s", zone, exc)

            # Mute
            inst_m = ZONE_MUTE_INSTANCES.get(zone)
            if inst_m:
                try:
                    val = await self._client.get_attribute(inst_m, ATTR_MUTE)
                    if val is not None:
                        self.mutes[zone] = bool(val)
                    await self._client.subscribe(inst_m, ATTR_MUTE, inst_m)
                except Exception as exc:
                    _LOGGER.warning("Mute read failed %s: %s", zone, exc)

        # Source routers – some are shared by multiple zones (e.g. ELA Außen
        # + ELA Außen Sitzen), so group by instance tag first to avoid
        # sending duplicate get/subscribe commands for the same block.
        zones_by_router: dict[str, list[str]] = {}
        for zone, inst_r in ZONE_SOURCE_INSTANCES.items():
            zones_by_router.setdefault(inst_r, []).append(zone)

        for inst_r, zones in zones_by_router.items():
            try:
                val = await self._client.get_attribute(inst_r, ATTR_SOURCE_SELECTION, channel=None)
                if val is not None:
                    for zone in zones:
                        self.sources[zone] = int(val)
                await self._client.subscribe(inst_r, ATTR_SOURCE_SELECTION, inst_r)
            except Exception as exc:
                _LOGGER.warning("Source read failed %s: %s", inst_r, exc)

        self._notify()

    # ------------------------------------------------------------------
    # Zone control API
    # ------------------------------------------------------------------

    async def set_level(self, zone: str, level_db: float) -> None:
        level_db = max(MIN_LEVEL, min(MAX_LEVEL, level_db))
        inst = ZONE_LEVEL_INSTANCES.get(zone)
        if inst:
            await self._client.set_attribute(inst, ATTR_LEVEL, round(level_db, 1))
            self.levels[zone] = level_db

    async def set_mute(self, zone: str, mute: bool) -> None:
        inst = ZONE_MUTE_INSTANCES.get(zone)
        if inst:
            await self._client.set_attribute(inst, ATTR_MUTE, "true" if mute else "false")
            self.mutes[zone] = mute

    async def set_source(self, zone: str, source_index: int) -> None:
        """Select input source for a specific zone.

        Some zones share the same router block (e.g. ELA Außen + ELA Außen
        Sitzen), so the new source is applied to every zone mapped to that
        instance, not just the one the user interacted with.
        """
        inst = ZONE_SOURCE_INSTANCES.get(zone)
        if inst:
            await self._client.set_attribute(inst, ATTR_SOURCE_SELECTION, source_index, channel=None)
            for z in self._zones_for(inst, ZONE_SOURCE_INSTANCES):
                self.sources[z] = source_index
            self._notify()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def level_to_volume(self, zone: str) -> float:
        db = self.levels.get(zone, MIN_LEVEL)
        return max(0.0, min(1.0, (db - MIN_LEVEL) / (MAX_LEVEL - MIN_LEVEL)))

    def volume_to_level(self, volume: float) -> float:
        return MIN_LEVEL + volume * (MAX_LEVEL - MIN_LEVEL)

    def source_name(self, zone: str) -> str | None:
        idx = self.sources.get(zone)
        return SOURCES_REVERSE.get(idx) if idx is not None else None

    @property
    def connected(self) -> bool:
        return self._client.connected
