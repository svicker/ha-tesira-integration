"""Media player entities for Biamp Tesira zones."""
from __future__ import annotations

import logging

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TesiraCoordinator
from .const import DOMAIN, PLAYER_ZONES, SOURCES, ZONE_NAMES, ZONE_SOURCE_INSTANCES

_LOGGER = logging.getLogger(__name__)

BASE_FEATURES = (
    MediaPlayerEntityFeature.VOLUME_SET
    | MediaPlayerEntityFeature.VOLUME_MUTE
    | MediaPlayerEntityFeature.VOLUME_STEP
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: TesiraCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        TesiraZoneMediaPlayer(coordinator, entry, zone)
        for zone in PLAYER_ZONES
    ])


class TesiraZoneMediaPlayer(MediaPlayerEntity):
    """Media player entity for one Tesira audio zone – own source selector."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: TesiraCoordinator, entry: ConfigEntry, zone: str) -> None:
        self._coordinator = coordinator
        self._zone = zone
        self._attr_name = ZONE_NAMES[zone]
        self._attr_unique_id = f"{entry.entry_id}_{zone}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Biamp",
            model="Tesira Forté AVB TI",
        )

        # Nicht jede Zone hat einen eigenen Source-Router-Block am Tesira
        # (z.B. ELA Saal) – Quellenwahl gibt es nur, wenn ein Instance-Tag
        # hinterlegt ist.
        if zone in ZONE_SOURCE_INSTANCES:
            self._attr_supported_features = BASE_FEATURES | MediaPlayerEntityFeature.SELECT_SOURCE
            self._attr_source_list = list(SOURCES.keys())
        else:
            self._attr_supported_features = BASE_FEATURES

    async def async_added_to_hass(self) -> None:
        self._coordinator.register_listener(self)

    async def async_will_remove_from_hass(self) -> None:
        self._coordinator.unregister_listener(self)

    @property
    def state(self) -> MediaPlayerState:
        if not self._coordinator.connected:
            return MediaPlayerState.OFF
        if self._coordinator.mutes.get(self._zone, False):
            return MediaPlayerState.IDLE
        return MediaPlayerState.ON

    @property
    def volume_level(self) -> float | None:
        return self._coordinator.level_to_volume(self._zone)

    @property
    def is_volume_muted(self) -> bool:
        return self._coordinator.mutes.get(self._zone, False)

    @property
    def source(self) -> str | None:
        if self._zone not in ZONE_SOURCE_INSTANCES:
            return None
        return self._coordinator.source_name(self._zone)

    @property
    def available(self) -> bool:
        return self._coordinator.connected

    async def async_set_volume_level(self, volume: float) -> None:
        await self._coordinator.set_level(self._zone, self._coordinator.volume_to_level(volume))
        self.async_write_ha_state()

    async def async_mute_volume(self, mute: bool) -> None:
        await self._coordinator.set_mute(self._zone, mute)
        self.async_write_ha_state()

    async def async_select_source(self, source: str) -> None:
        idx = SOURCES.get(source)
        if idx is not None:
            await self._coordinator.set_source(self._zone, idx)
            self.async_write_ha_state()

    async def async_volume_up(self) -> None:
        current = self._coordinator.levels.get(self._zone, -40.0)
        await self._coordinator.set_level(self._zone, current + 1.0)
        self.async_write_ha_state()

    async def async_volume_down(self) -> None:
        current = self._coordinator.levels.get(self._zone, -40.0)
        await self._coordinator.set_level(self._zone, current - 1.0)
        self.async_write_ha_state()

    async def async_update(self) -> None:
        pass
