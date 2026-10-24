"""Constants for the Biamp Tesira integration."""

from __future__ import annotations

DOMAIN = "tesira"
DEFAULT_PORT = 23
DEFAULT_NAME = "Tesira"

MANUFACTURER = "Biamp"
MODEL = "Tesira Forté AVB TI"

CONFIG_VERSION = 3

# Throttle for volume writes: the last value within this window wins.
LEVEL_THROTTLE = 0.05

# Fallback when volume_up/down is used before the level is known.
FALLBACK_LEVEL_DB = -40.0
VOLUME_STEP_DB = 1.0

# Option keys
OPT_ZONES = "zones"
OPT_SOURCES = "sources"
OPT_MIN_DB = "min_db"
OPT_MAX_DB = "max_db"

DEFAULT_MIN_DB = -100.0
DEFAULT_MAX_DB = 12.0

# TTP attributes
ATTR_LEVEL = "level"
ATTR_MUTE = "mute"
ATTR_SOURCE_SELECTION = "sourceSelection"
ATTR_BYPASS = "bypass"
ATTR_DUCKING_LEVEL = "duckingLevel"
ATTR_NUM_INPUTS = "numInputs"
ATTR_INPUT_LABEL = "inputLabel"

# Level blocks (and gate level blocks) address channel 1.
LEVEL_INDEX = 1

# Default zones: key -> (name, router, level, gate, ducker). Keys are the
# unique_id suffixes of the existing entities and must never change. The gate
# is a level block with mute in front of the ducker's sense input.
DEFAULT_ZONES: dict[str, tuple[str, str | None, str, str | None, str | None]] = {
    "klubraum": (
        "Klubraum",
        "SourceRouterKlubRaum",
        "LevelKlubRaum",
        "MicGateKlub",
        "DuckerKlubRaum",
    ),
    "saal": ("Saal", "SourceRouterSaal", "LevelSaal", "MicGateSaal", "DuckerSaal"),
    "ela_saal": ("ELA Saal", None, "LevelELASaal", None, None),
    "ela_kk_stand": (
        "ELA KK-Stand",
        "SourceRouterKKStand",
        "LevelELAKKStand",
        "MicGateKKStand",
        "DuckerELAKKStand",
    ),
    "ela_theke": (
        "ELA Theke",
        "SourceRouterTheke",
        "LevelELATheke",
        "MicGateELATheke",
        "DuckerELATheke",
    ),
    "ela_aussen": (
        "ELA Außen",
        "SourceRouterAussen",
        "LevelELAAussen",
        "MicGateELAAussen",
        "DuckerELAAussen",
    ),
    "ela_aussen_sitzen": (
        "ELA Außen Sitzen",
        "SourceRouterAussen",
        "LevelELAAussenSitzen",
        "MicGateELAAussenSitz",
        "DuckerELAAussenSitz",
    ),
    "ela_toilette": (
        "ELA Toilette",
        "SourceRouterToiletteFlur",
        "LevelELAToilette",
        "MicGateELAToilette",
        "DuckerELAToilette",
    ),
    "ela_flur": (
        "ELA Flur",
        "SourceRouterToiletteFlur",
        "LevelELAFlur",
        "MicGateELAFlur",
        "DuckerELAFlur",
    ),
}

# Renamed in the Tesira project; migrated once in saved options.
OLD_DUCKER_AUSSEN_SITZEN = "DuckerELAAussenSitzen"

# Suggested source list for every router (index 0 = no source).
DEFAULT_SOURCES: dict[int, str] = {
    0: "Aus",
    1: "Apple TV",
    2: "SAT TV",
    3: "Musik",
    4: "PC Theke",
}
