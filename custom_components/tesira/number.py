"""Number: ducking level of a zone's ducker (disabled by default)."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TesiraConfigEntry
from .const import ATTR_DUCKING_LEVEL
from .coordinator import Key, TesiraCoordinator
from .entity import TesiraEntity
from .options import ZoneConfig

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: TesiraConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        DuckingLevelNumber(coordinator, zone)
        for zone in coordinator.options.zones.values()
        if zone.ducker
    )


class DuckingLevelNumber(TesiraEntity, NumberEntity):
    """How far the ducker lowers the music, in dB."""

    _attr_translation_key = "ducking_level"
    _attr_entity_registry_enabled_default = False
    _attr_native_unit_of_measurement = "dB"
    _attr_native_min_value = -100.0
    _attr_native_max_value = 0.0
    _attr_native_step = 0.5
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:volume-minus"

    def __init__(self, coordinator: TesiraCoordinator, zone: ZoneConfig) -> None:
        assert zone.ducker is not None
        super().__init__(coordinator, {zone.ducker})
        self._key: Key = (zone.ducker, ATTR_DUCKING_LEVEL, None)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{zone.key}_ducking_level"
        self._attr_translation_placeholders = {"zone": zone.name}

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.async_add_watch(self._key))

    @property
    def native_value(self) -> float | None:
        value = self.coordinator.values.get(self._key)
        return value if isinstance(value, float) else None

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_value(self._key, round(value, 1))
