"""Typed view on the config entry options, with defaults."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .const import (
    DEFAULT_MAX_DB,
    DEFAULT_MIN_DB,
    DEFAULT_SOURCES,
    DEFAULT_ZONES,
    OPT_MAX_DB,
    OPT_MIN_DB,
    OPT_SOURCES,
    OPT_ZONES,
)

_TAG_RE = re.compile(r'^[^"\\\r\n]+$')


def valid_tag(tag: str) -> bool:
    """True if ``tag`` can safely be put between quotes in a TTP command."""
    return bool(_TAG_RE.match(tag))


@dataclass(frozen=True, slots=True)
class ZoneConfig:
    """One zone = one media_player entity."""

    key: str
    name: str
    router: str | None
    level: str
    gate: str | None = None
    ducker: str | None = None


@dataclass(frozen=True, slots=True)
class TesiraOptions:
    """All user-editable settings."""

    zones: dict[str, ZoneConfig]
    sources: dict[str, dict[int, str]]
    min_db: float
    max_db: float

    def to_dict(self) -> dict[str, Any]:
        """JSON-compatible form for storing in ``entry.options``."""
        return {
            OPT_ZONES: {
                zone.key: {
                    "name": zone.name,
                    "router": zone.router,
                    "level": zone.level,
                    "gate": zone.gate,
                    "ducker": zone.ducker,
                }
                for zone in self.zones.values()
            },
            OPT_SOURCES: {
                router: {str(index): name for index, name in sources.items()}
                for router, sources in self.sources.items()
            },
            OPT_MIN_DB: self.min_db,
            OPT_MAX_DB: self.max_db,
        }


def default_options() -> TesiraOptions:
    """Defaults = the tables of the original Schützenhaus setup."""
    zones = {
        key: ZoneConfig(key, name, router, level, None, ducker)
        for key, (name, router, level, ducker) in DEFAULT_ZONES.items()
    }
    return parse_options({}, zones_default=zones)


def parse_options(
    raw: Mapping[str, Any], *, zones_default: dict[str, ZoneConfig] | None = None
) -> TesiraOptions:
    """Build options from stored data, filling every gap with defaults."""
    zones: dict[str, ZoneConfig]
    raw_zones = raw.get(OPT_ZONES)
    if raw_zones:
        zones = {
            key: ZoneConfig(
                key=key,
                name=str(zone.get("name") or key),
                router=zone.get("router") or None,
                level=str(zone["level"]),
                gate=zone.get("gate") or None,
                ducker=zone.get("ducker") or None,
            )
            for key, zone in raw_zones.items()
        }
    elif zones_default is not None:
        zones = zones_default
    else:
        zones = default_options().zones

    sources: dict[str, dict[int, str]] = {}
    raw_sources = raw.get(OPT_SOURCES) or {}
    for router, mapping in raw_sources.items():
        sources[router] = {int(index): str(name) for index, name in mapping.items()}
    for zone in zones.values():
        if zone.router and zone.router not in sources:
            sources[zone.router] = dict(DEFAULT_SOURCES)

    return TesiraOptions(
        zones=zones,
        sources=sources,
        min_db=float(raw.get(OPT_MIN_DB, DEFAULT_MIN_DB)),
        max_db=float(raw.get(OPT_MAX_DB, DEFAULT_MAX_DB)),
    )
