"""Switches: microphone gate per zone and ducker bypass."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TesiraConfigEntry
from .const import ATTR_BYPASS, DOMAIN
from .coordinator import Key, TesiraCoordinator
from .entity import TesiraEntity
from .options import ZoneConfig

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: TesiraConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    registry = er.async_get(hass)
    entities: list[TesiraEntity] = []
    for zone in coordinator.options.zones.values():
        if zone.gate:
            entities.append(MicGateSwitch(coordinator, zone))
        elif stale := registry.async_get_entity_id(
            "switch", DOMAIN, f"{entry.entry_id}_{zone.key}_mic_gate"
        ):
            # Gate tag was cleared: drop the switch instead of leaving a dead one.
            registry.async_remove(stale)
        if zone.ducker:
            entities.append(DuckerBypassSwitch(coordinator, zone))
    async_add_entities(entities)


class MicGateSwitch(TesiraEntity, SwitchEntity):
    """On = microphones are let through to this zone (gate not muted).

    Exists only when a gate tag is set for the zone in the options.
    """

    _attr_icon = "mdi:microphone"

    def __init__(self, coordinator: TesiraCoordinator, zone: ZoneConfig) -> None:
        assert zone.gate is not None
        super().__init__(coordinator, {zone.gate})
        self._key = coordinator.gate_key(zone)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{zone.key}_mic_gate"
        # Fixed name (not translated), so the entity_id does not depend on the
        # language: switch.tesira_<zone>_mikrofon
        self._attr_name = f"{zone.name} Mikrofon"

    @property
    def available(self) -> bool:
        # A tag the device rejects stays unavailable instead of "unknown".
        return super().available and not self.coordinator.key_rejected(self._key)

    @property
    def is_on(self) -> bool | None:
        muted = self.coordinator.values.get(self._key)
        return None if muted is None else not muted

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_value(self._key, False)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_value(self._key, True)


class DuckerBypassSwitch(TesiraEntity, SwitchEntity):
    """Bypass of the zone's ducker. Disabled by default."""

    _attr_translation_key = "ducker_bypass"
    _attr_entity_registry_enabled_default = False
    _attr_icon = "mdi:volume-minus"

    def __init__(self, coordinator: TesiraCoordinator, zone: ZoneConfig) -> None:
        assert zone.ducker is not None
        super().__init__(coordinator, {zone.ducker})
        self._key: Key = (zone.ducker, ATTR_BYPASS, None)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{zone.key}_ducker_bypass"
        self._attr_translation_placeholders = {"zone": zone.name}

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Only enabled entities are watched, so a disabled ducker costs nothing.
        self.async_on_remove(self.coordinator.async_add_watch(self._key))

    @property
    def is_on(self) -> bool | None:
        value = self.coordinator.values.get(self._key)
        return value if isinstance(value, bool) else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_value(self._key, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_value(self._key, False)
