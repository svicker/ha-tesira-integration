"""Push-based coordinator: owns the client and the last known values."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError

from .client import (
    BACKOFF_MAX,
    BACKOFF_START,
    TesiraClient,
    TesiraCommandError,
    TesiraError,
)
from .const import (
    ATTR_BYPASS,
    ATTR_DUCKING_LEVEL,
    ATTR_LEVEL,
    ATTR_MUTE,
    ATTR_SOURCE_SELECTION,
    LEVEL_INDEX,
    LEVEL_THROTTLE,
)
from .options import TesiraOptions, ZoneConfig

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)

# (instance tag, attribute, index or None)
type Key = tuple[str, str, int | None]

_BOOL_ATTRS = {ATTR_MUTE, ATTR_BYPASS}
_FLOAT_ATTRS = {ATTR_LEVEL, ATTR_DUCKING_LEVEL}


def key_label(key: Key) -> str:
    """Subscription label for a key; also used to route pushes back."""
    tag, attribute, index = key
    return f"{tag}.{attribute}" if index is None else f"{tag}.{attribute}.{index}"


def key_text(key: Key) -> str:
    """Readable form for diagnostics."""
    return key_label(key)


def coerce(attribute: str, value: Any) -> Any:
    """Bring a parsed TTP value to the type the attribute should have."""
    if value is None:
        return None
    try:
        if attribute in _BOOL_ATTRS:
            if isinstance(value, str):
                return value.lower() == "true"
            return bool(value)
        if attribute in _FLOAT_ATTRS:
            return float(value)
        if attribute == ATTR_SOURCE_SELECTION:
            return int(value)
    except (TypeError, ValueError):
        _LOGGER.debug("Unexpected value for %s: %r", attribute, value)
        return None
    return value


class TesiraCoordinator:
    """Holds the connection, the last known values and the listeners."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, options: TesiraOptions) -> None:
        self.hass = hass
        self.entry = entry
        self.options = options
        self.client = TesiraClient(
            entry.data[CONF_HOST],
            entry.data[CONF_PORT],
            username=entry.data.get(CONF_USERNAME) or None,
            password=entry.data.get(CONF_PASSWORD) or None,
            backoff_start=BACKOFF_START,
            backoff_max=BACKOFF_MAX,
        )
        self.values: dict[Key, Any] = {}

        self._watches: set[Key] = set()
        self._labels: dict[str, Key] = {}
        self._listeners: list[tuple[frozenset[str] | None, Callable[[], None]]] = []
        self._failed: set[Key] = set()
        self._warned_sources: set[tuple[str, int]] = set()
        self._level_targets: dict[str, float] = {}
        self._level_tasks: dict[str, asyncio.Task[None]] = {}

        for zone in options.zones.values():
            self._watch(self.level_key(zone))
            self._watch(self.mute_key(zone))
            if zone.router:
                self._watch(self.router_key(zone))
            if zone.gate:
                self._watch(self.gate_key(zone))

        self.client.set_callbacks(
            on_push=self._on_push,
            on_connect=self._async_sync_all,
            on_state=self._on_state,
        )

    # ------------------------------------------------------------------
    # Keys
    # ------------------------------------------------------------------

    @staticmethod
    def level_key(zone: ZoneConfig) -> Key:
        return (zone.level, ATTR_LEVEL, LEVEL_INDEX)

    @staticmethod
    def mute_key(zone: ZoneConfig) -> Key:
        return (zone.level, ATTR_MUTE, LEVEL_INDEX)

    @staticmethod
    def router_key(zone: ZoneConfig) -> Key:
        assert zone.router is not None
        return (zone.router, ATTR_SOURCE_SELECTION, None)

    @staticmethod
    def gate_key(zone: ZoneConfig) -> Key:
        assert zone.gate is not None
        return (zone.gate, ATTR_MUTE, LEVEL_INDEX)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @property
    def connected(self) -> bool:
        return self.client.connected

    def async_start(self) -> None:
        """Start connecting in the background; entities stay unavailable until then."""
        self.client.start()

    async def async_stop(self) -> None:
        for task in list(self._level_tasks.values()):
            task.cancel()
        await asyncio.gather(*self._level_tasks.values(), return_exceptions=True)
        self._level_tasks.clear()
        await self.client.stop()

    # ------------------------------------------------------------------
    # Listeners
    # ------------------------------------------------------------------

    @callback
    def async_add_listener(
        self, update: Callable[[], None], tags: set[str] | None = None
    ) -> Callable[[], None]:
        """Call ``update`` when a tag in ``tags`` (or anything, if None) changes."""
        item = (frozenset(tags) if tags is not None else None, update)
        self._listeners.append(item)

        @callback
        def remove() -> None:
            if item in self._listeners:
                self._listeners.remove(item)

        return remove

    @callback
    def _notify(self, tags: set[str] | None = None) -> None:
        for wanted, update in list(self._listeners):
            if wanted is None or tags is None or wanted & tags:
                update()

    # ------------------------------------------------------------------
    # Watches / synchronisation
    # ------------------------------------------------------------------

    def _watch(self, key: Key) -> None:
        self._watches.add(key)
        self._labels[key_label(key)] = key

    @callback
    def async_add_watch(self, key: Key) -> Callable[[], None]:
        """Track one more value (used by optional entities)."""
        self._watch(key)
        if self.client.connected:
            self.entry.async_create_background_task(
                self.hass, self._async_sync_key_safe(key), f"tesira sync {key_label(key)}"
            )

        @callback
        def remove() -> None:
            self._watches.discard(key)
            self._labels.pop(key_label(key), None)

        return remove

    async def _async_sync_all(self) -> None:
        """Runs on every (re)connect, before the entities become available.

        1. Forget everything: nothing from the previous connection may be shown.
        2. Read every value (routers, levels, mutes, ...).
        3. Only then subscribe, so later changes arrive as pushes.
        """
        keys = sorted(self._watches, key=key_label)
        _LOGGER.debug("Synchronising %d values", len(keys))
        self.values.clear()
        for key in keys:
            await self._async_read_key(key)
        for key in keys:
            if key in self.values:
                await self._async_subscribe_key(key)

    async def _async_sync_key_safe(self, key: Key) -> None:
        """Read and subscribe a single value (for watches added at runtime)."""
        try:
            await self._async_read_key(key)
            if key in self.values:
                await self._async_subscribe_key(key)
        except TesiraError as err:
            _LOGGER.debug("Sync of %s failed: %s", key_label(key), err)

    async def _async_read_key(self, key: Key) -> None:
        tag, attribute, index = key
        try:
            value = coerce(attribute, await self.client.get(tag, attribute, index))
        except TesiraCommandError as err:
            # Wrong tag or attribute: log once, keep going with the rest.
            if key not in self._failed:
                self._failed.add(key)
                _LOGGER.warning("Tesira rejected %s: %s", key_label(key), err)
            self.values.pop(key, None)
        else:
            self._failed.discard(key)
            if value is None:
                self.values.pop(key, None)
            else:
                self.values[key] = value
        self._notify({tag})

    async def _async_subscribe_key(self, key: Key) -> None:
        tag, attribute, index = key
        try:
            await self.client.subscribe(tag, attribute, key_label(key), index)
        except TesiraCommandError as err:
            _LOGGER.warning("Tesira rejected subscription %s: %s", key_label(key), err)

    @callback
    def _on_state(self, connected: bool) -> None:
        _LOGGER.debug("Connection state: %s", connected)
        self._notify()

    @callback
    def _on_push(self, label: str, value: Any) -> None:
        key = self._labels.get(label)
        if key is None or key not in self._watches:
            return
        self.values[key] = coerce(key[1], value)
        self._notify({key[0]})

    # ------------------------------------------------------------------
    # Readers
    # ------------------------------------------------------------------

    def key_rejected(self, key: Key) -> bool:
        """True if the device refused to read this value (e.g. unknown tag)."""
        return key in self._failed

    async def async_tag_exists(self, tag: str, attribute: str, index: int | None) -> bool | None:
        """Read-only check whether the device knows ``tag``.

        Returns None when it cannot be told (offline, other errors); only the
        device's "address not found" counts as a definite no.
        """
        if not self.client.connected:
            return None
        try:
            await self.client.get(tag, attribute, index)
        except TesiraCommandError as err:
            return False if "address not found" in str(err).lower() else None
        except TesiraError:
            return None
        return True

    def level_db(self, zone: ZoneConfig) -> float | None:
        value = self.values.get(self.level_key(zone))
        return value if isinstance(value, float) else None

    def muted(self, zone: ZoneConfig) -> bool:
        return self.values.get(self.mute_key(zone)) is True

    def source_index(self, zone: ZoneConfig) -> int | None:
        if not zone.router:
            return None
        value = self.values.get(self.router_key(zone))
        return value if isinstance(value, int) else None

    def sources_for(self, zone: ZoneConfig) -> dict[int, str]:
        if not zone.router:
            return {}
        return self.options.sources.get(zone.router, {})

    def source_name(self, zone: ZoneConfig) -> str | None:
        index = self.source_index(zone)
        if index is None:
            return None
        name = self.sources_for(zone).get(index)
        if name is None and zone.router and (zone.router, index) not in self._warned_sources:
            self._warned_sources.add((zone.router, index))
            _LOGGER.warning(
                "Router %s reports source %s, which is not in the source list",
                zone.router,
                index,
            )
        return name

    def level_to_volume(self, db: float | None) -> float:
        low, high = self.options.min_db, self.options.max_db
        if db is None:
            return 0.0
        return max(0.0, min(1.0, (db - low) / (high - low)))

    def volume_to_level(self, volume: float) -> float:
        low, high = self.options.min_db, self.options.max_db
        return low + volume * (high - low)

    # ------------------------------------------------------------------
    # Writers
    # ------------------------------------------------------------------

    async def async_set_value(self, key: Key, value: Any) -> None:
        """Write one value; the device's push confirms it afterwards."""
        tag, attribute, index = key
        try:
            await self.client.set(tag, attribute, value, index)
        except TesiraError as err:
            raise HomeAssistantError(f"Tesira: setting {key_label(key)} failed: {err}") from err
        self.values[key] = coerce(attribute, value)
        self._notify({tag})

    def request_level(self, zone: ZoneConfig, db: float) -> None:
        """Set a level; fast successive calls collapse to the last value."""
        db = round(max(self.options.min_db, min(self.options.max_db, db)), 1)
        key = self.level_key(zone)
        self.values[key] = db
        self._notify({zone.level})
        self._level_targets[zone.level] = db
        if zone.level not in self._level_tasks:
            self._level_tasks[zone.level] = self.entry.async_create_background_task(
                self.hass, self._async_send_level(zone), f"tesira level {zone.level}"
            )

    async def _async_send_level(self, zone: ZoneConfig) -> None:
        key = self.level_key(zone)
        try:
            while zone.level in self._level_targets:
                await asyncio.sleep(LEVEL_THROTTLE)
                db = self._level_targets.pop(zone.level)
                try:
                    await self.client.set(key[0], key[1], db, key[2])
                except TesiraError as err:
                    _LOGGER.warning("Setting level of %s failed: %s", zone.level, err)
                    self._level_targets.pop(zone.level, None)
                    try:
                        await self._async_read_key(key)
                    except TesiraError as read_err:
                        _LOGGER.debug("Re-read of %s failed: %s", zone.level, read_err)
        finally:
            self._level_tasks.pop(zone.level, None)

    async def async_read_input_labels(self, router: str) -> dict[int, str]:
        """Read-only helper: ask a router for its input labels (may be empty)."""
        from .const import ATTR_INPUT_LABEL, ATTR_NUM_INPUTS

        try:
            count = await self.client.get(router, ATTR_NUM_INPUTS)
        except TesiraCommandError:
            return {}
        if not isinstance(count, int) or not 0 < count <= 64:
            return {}
        labels: dict[int, str] = {0: "Aus"}
        for number in range(1, count + 1):
            try:
                label = await self.client.get(router, ATTR_INPUT_LABEL, number)
            except TesiraCommandError:
                label = ""
            labels[number] = str(label) if label else f"Eingang {number}"
        return labels
