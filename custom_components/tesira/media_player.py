"""Media player entities: one per Tesira zone."""

from __future__ import annotations

from homeassistant.components.media_player import MediaPlayerEntity
from homeassistant.components.media_player.const import (
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TesiraConfigEntry
from .const import FALLBACK_LEVEL_DB, VOLUME_STEP_DB
from .coordinator import TesiraCoordinator
from .entity import TesiraEntity
from .options import ZoneConfig

PARALLEL_UPDATES = 0

BASE_FEATURES = (
    MediaPlayerEntityFeature.VOLUME_SET
    | MediaPlayerEntityFeature.VOLUME_MUTE
    | MediaPlayerEntityFeature.VOLUME_STEP
)


async def async_setup_entry(
    hass: HomeAssistant, entry: TesiraConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        TesiraZoneMediaPlayer(coordinator, zone) for zone in coordinator.options.zones.values()
    )


class TesiraZoneMediaPlayer(TesiraEntity, MediaPlayerEntity):
    """Volume, mute and (if the zone has a router) source selection of one zone."""

    def __init__(self, coordinator: TesiraCoordinator, zone: ZoneConfig) -> None:
        tags = {zone.level}
        if zone.router:
            tags.add(zone.router)
        super().__init__(coordinator, tags)
        self._zone = zone
        self._attr_name = zone.name
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{zone.key}"
        if zone.router:
            self._attr_supported_features = BASE_FEATURES | MediaPlayerEntityFeature.SELECT_SOURCE
            self._attr_source_list = [
                name for _, name in sorted(coordinator.sources_for(zone).items())
            ]
        else:
            self._attr_supported_features = BASE_FEATURES

    @property
    def state(self) -> MediaPlayerState:
        if self.coordinator.muted(self._zone):
            return MediaPlayerState.IDLE
        return MediaPlayerState.ON

    @property
    def volume_level(self) -> float:
        return self.coordinator.level_to_volume(self.coordinator.level_db(self._zone))

    @property
    def is_volume_muted(self) -> bool:
        return self.coordinator.muted(self._zone)

    @property
    def source(self) -> str | None:
        return self.coordinator.source_name(self._zone)

    async def async_set_volume_level(self, volume: float) -> None:
        self.coordinator.request_level(self._zone, self.coordinator.volume_to_level(volume))

    async def async_mute_volume(self, mute: bool) -> None:
        await self.coordinator.async_set_value(self.coordinator.mute_key(self._zone), mute)

    async def async_volume_up(self) -> None:
        self._step(VOLUME_STEP_DB)

    async def async_volume_down(self) -> None:
        self._step(-VOLUME_STEP_DB)

    def _step(self, delta: float) -> None:
        current = self.coordinator.level_db(self._zone)
        base = FALLBACK_LEVEL_DB if current is None else current
        self.coordinator.request_level(self._zone, base + delta)

    async def async_select_source(self, source: str) -> None:
        for index, name in self.coordinator.sources_for(self._zone).items():
            if name == source:
                await self.coordinator.async_set_value(
                    self.coordinator.router_key(self._zone), index
                )
                return
        raise ServiceValidationError(f"Unknown source: {source}")
