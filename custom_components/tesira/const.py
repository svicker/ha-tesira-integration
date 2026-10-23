"""Constants for the Biamp Tesira integration."""

from __future__ import annotations

DOMAIN = "tesira"
DEFAULT_PORT = 23
DEFAULT_NAME = "Tesira"

MANUFACTURER = "Biamp"
MODEL = "Tesira Forté AVB TI"

CONFIG_VERSION = 2

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

# Default zones: key -> (name, router, level, ducker). Keys are the unique_id
# suffixes of the existing entities and must never change.
DEFAULT_ZONES: dict[str, tuple[str, str | None, str, str | None]] = {
    "klubraum": ("Klubraum", "SourceRouterKlubRaum", "LevelKlubRaum", "DuckerKlubRaum"),
    "saal": ("Saal", "SourceRouterSaal", "LevelSaal", "DuckerSaal"),
    "ela_saal": ("ELA Saal", None, "LevelELASaal", None),
    "ela_kk_stand": (
        "ELA KK-Stand",
        "SourceRouterKKStand",
        "LevelELAKKStand",
        "DuckerELAKKStand",
    ),
    "ela_theke": ("ELA Theke", "SourceRouterTheke", "LevelELATheke", "DuckerELATheke"),
    "ela_aussen": ("ELA Außen", "SourceRouterAussen", "LevelELAAussen", "DuckerELAAussen"),
    "ela_aussen_sitzen": (
        "ELA Außen Sitzen",
        "SourceRouterAussen",
        "LevelELAAussenSitzen",
        "DuckerELAAussenSitzen",
    ),
    "ela_toilette": (
        "ELA Toilette",
        "SourceRouterToiletteFlur",
        "LevelELAToilette",
        "DuckerELAToilette",
    ),
    "ela_flur": ("ELA Flur", "SourceRouterToiletteFlur", "LevelELAFlur", "DuckerELAFlur"),
}

# Suggested source list for every router (index 0 = no source).
DEFAULT_SOURCES: dict[int, str] = {
    0: "Aus",
    1: "Apple TV",
    2: "SAT TV",
    3: "Musik",
    4: "PC Theke",
}
