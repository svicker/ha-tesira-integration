"""Constants for the Biamp Tesira integration."""

DOMAIN = "tesira"
DEFAULT_PORT = 23
DEFAULT_NAME = "Tesira"
RECONNECT_INTERVAL = 10  # seconds
KEEP_ALIVE_INTERVAL = 30  # seconds

# ---------------------------------------------------------------------------
# Tesira Instance-Tag Names
# ---------------------------------------------------------------------------

# Source Router – ein Block pro Zone mit eigener Quellenwahl.
# ela_aussen und ela_aussen_sitzen teilen sich denselben Router-Block
# (physisch ein Attribut, wird für beide Zonen gespiegelt), ebenso
# ela_toilette und ela_flur. ela_saal hat keinen eigenen Router und
# taucht hier bewusst nicht auf.
ZONE_SOURCE_INSTANCES = {
    "klubraum":          "SourceRouterKlubRaum",
    "saal":              "SourceRouterSaal",
    "ela_aussen":        "SourceRouterAussen",
    "ela_aussen_sitzen": "SourceRouterAussen",
    "ela_kk_stand":      "SourceRouterKKStand",
    "ela_theke":         "SourceRouterTheke",
    "ela_toilette":      "SourceRouterToiletteFlur",
    "ela_flur":          "SourceRouterToiletteFlur",
}

# Level/Mute Blocks – ein Block pro Zone
ZONE_LEVEL_INSTANCES = {
    "klubraum":          "LevelKlubRaum",
    "saal":              "LevelSaal",
    "ela_aussen":        "LevelELAAussen",
    "ela_aussen_sitzen": "LevelELAAussenSitzen",
    "ela_kk_stand":      "LevelELAKKStand",
    "ela_saal":          "LevelELASaal",
    "ela_theke":         "LevelELATheke",
    "ela_toilette":      "LevelELAToilette",
    "ela_flur":          "LevelELAFlur",
}

# Mute hängt immer am selben Block wie Level
ZONE_MUTE_INSTANCES = ZONE_LEVEL_INSTANCES

# Friendly Names
ZONE_NAMES = {
    "klubraum":          "Klubraum",
    "saal":              "Saal",
    "ela_aussen":        "ELA Außen",
    "ela_aussen_sitzen": "ELA Außen Sitzen",
    "ela_kk_stand":      "ELA KK-Stand",
    "ela_saal":          "ELA Saal",
    "ela_theke":         "ELA Theke",
    "ela_toilette":      "ELA Toilette",
    "ela_flur":          "ELA Flur",
}

# Alle Zonen sind media_player-Entities (Lautstärke/Mute, Quellenwahl nur
# wo ein Eintrag in ZONE_SOURCE_INSTANCES existiert).
PLAYER_ZONES = list(ZONE_NAMES.keys())

# ---------------------------------------------------------------------------
# Input Quellen – gleiche Liste für alle Zonen (Index 1-basiert)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Input Quellen – gleiche Liste für alle Zonen (Index 1-basiert)
# ---------------------------------------------------------------------------
SOURCES = {
    "Aus":              0,
    "Mikrofon":         1,
    "Apple TV":         2,
    "SAT TV":           3,
    "Musik":            4,
    "PC Theke":         5,
}
SOURCES_REVERSE = {v: k for k, v in SOURCES.items()}

# Index, der an den Tesira Source Selector gesendet wird, um "Aus" zu
# realisieren – setzt sourceSelection auf einen Wert außerhalb des
# gültigen Eingangsbereichs (1..5), wodurch der Selector keinen Eingang
# mehr auswählt und der Zonen-Bus stumm bleibt.
SOURCE_OFF_INDEX = 0

# ---------------------------------------------------------------------------
# Tesira TTP Protokoll-Konstanten
# ---------------------------------------------------------------------------
TTP_SESSION_READY     = "Welcome to the Tesira"
TTP_OK                = "+OK"
TTP_ERROR             = "-ERR"
TTP_PUBLISH_PREFIX    = "! "

ATTR_LEVEL            = "level"
ATTR_MUTE             = "mute"
ATTR_SOURCE_SELECTION = "sourceSelection"

MIN_LEVEL = -100.0
MAX_LEVEL =   12.0
