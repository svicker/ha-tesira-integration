"""Shared base entity."""

from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import TesiraCoordinator


class TesiraEntity(Entity):
    """Base class: one device, push updates, available while connected."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: TesiraCoordinator, tags: set[str]) -> None:
        self.coordinator = coordinator
        self._tags = tags
        entry = coordinator.entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    @property
    def available(self) -> bool:
        return self.coordinator.connected

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.coordinator.async_add_listener(self._handle_update, self._tags))

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()
