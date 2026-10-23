# Biamp Tesira für Home Assistant

Custom Integration (Domain `tesira`) für eine **Biamp Tesira Forté AVB TI**. Sie steuert pro Zone Quellenwahl, Lautstärke und Stumm über das **Tesira Text Protocol (TTP)** per Telnet. Gebaut für das Schützenhaus (Schützenverein Icker e.V.), aber nicht darauf beschränkt: Zonen, Quellen und Grenzen sind in der Oberfläche einstellbar.

> **Status:** Version 2.0.0 ist in Entwicklung. Fertig sind der Protokoll-Client und seine Tests. Die Abschnitte unten beschreiben den Zielzustand. Was davon schon läuft, steht im [CHANGELOG](CHANGELOG.md), sobald es existiert.

## Funktionen

- Pro Zone ein `media_player` mit Lautstärke, Stumm und (wo vorhanden) Quellenwahl.
- Änderungen in der Tesira-Software oder an anderer Stelle erscheinen sofort in Home Assistant (Subscriptions, `local_push`, kein Polling).
- Verbindungsabbruch oder Neustart der Tesira: Die Entities werden `unavailable` und kommen von selbst zurück. Der Reconnect wartet 1 s, dann bis zu 30 s.
- Quellenlisten, Zonen und Lautstärke-Grenzen sind im Options Flow änderbar.
- Optional: Mikrofon-Gate je Zone als `switch`, Ducker-Bypass als `switch`, Ducking Level als `number` (die Ducker-Entities sind standardmäßig deaktiviert).
- Diagnose-Download mit Konfiguration (ohne Host), Verbindungsstatus, zuletzt empfangenen Werten und den letzten 50 Protokollzeilen.
- Oberfläche auf Deutsch und Englisch.

Es gibt bewusst **keinen** Dienst für freie Befehle.

## Voraussetzungen

- Home Assistant 2026.10 oder neuer
- Tesira mit erreichbarem TTP-Port (Standard `23`)
- Das Tesira-Netz muss von Home Assistant aus erreichbar sein

## Installation

### Per HACS

1. HACS öffnen, Menü oben rechts, **Benutzerdefinierte Repositories**.
2. Die URL dieses Repositories eintragen, Kategorie **Integration**.
3. „Biamp Tesira“ installieren und Home Assistant neu starten.

### Manuell

1. Den Ordner `custom_components/tesira/` nach `/config/custom_components/tesira/` kopieren.
2. Home Assistant neu starten.

## Einrichtung

1. **Einstellungen → Geräte & Dienste → Integration hinzufügen → Biamp Tesira**.
2. Host (z. B. `172.30.1.12`), Port (`23`) und optional Benutzer und Passwort eintragen. Die Tesira im Schützenhaus läuft ohne Anmeldung.
3. Vor dem Anlegen wird die Verbindung getestet. Ein Gerät lässt sich nur einmal einrichten (Host ist die eindeutige Kennung).
4. Host und Port können später über **Neu konfigurieren** geändert werden.

### Quellenliste prüfen

Die Quellenwahl sendet eine Zahl: `0` = keine Quelle (Aus), `1…n` = Eingang im Router. Welche Zahl welcher Quelle entspricht, hängt von der Tesira-Konfiguration ab. Vorgeschlagen wird:

| Index | Name |
|---|---|
| 0 | Aus |
| 1 | Apple TV |
| 2 | SAT TV |
| 3 | Musik |
| 4 | PC Theke |

**Prüfe die Liste vor dem Gebrauch**, zum Beispiel in der Tesira-Software oder durch Hören. Die Reihenfolge stimmt nur, wenn das Mikrofon dort tatsächlich aus den Routern entfernt wurde. Die Liste wird **pro Router** gepflegt, weil Router unterschiedliche Eingänge haben können. Unter **Konfigurieren** lassen sich die Namen beliebig ändern. Das Dashboard ruft `media_player.select_source` mit dem Namen auf.

Meldet die Tesira einen Index, der nicht in der Liste steht, zeigt die Entity keine Quelle an (`None`) und das Log enthält einmal eine Warnung.

## Zonen und Entities

Alle Entities gehören zu **einem** Gerät „Tesira“ (Hersteller Biamp, Modell Tesira Forté AVB TI).

| Entity | Router | Level | Quellenwahl |
|---|---|---|---|
| `media_player.tesira_klubraum` | `SourceRouterKlubRaum` | `LevelKlubRaum` | ja |
| `media_player.tesira_saal` | `SourceRouterSaal` | `LevelSaal` | ja |
| `media_player.tesira_ela_saal` | – | `LevelELASaal` | nein |
| `media_player.tesira_ela_kk_stand` | `SourceRouterKKStand` | `LevelELAKKStand` | ja |
| `media_player.tesira_ela_theke` | `SourceRouterTheke` | `LevelELATheke` | ja |
| `media_player.tesira_ela_aussen` | `SourceRouterAussen` | `LevelELAAussen` | ja |
| `media_player.tesira_ela_aussen_sitzen` | `SourceRouterAussen` | `LevelELAAussenSitzen` | ja |
| `media_player.tesira_ela_toilette` | `SourceRouterToiletteFlur` | `LevelELAToilette` | ja |
| `media_player.tesira_ela_flur` | `SourceRouterToiletteFlur` | `LevelELAFlur` | ja |

Geteilte Router (Außen/Außen Sitzen, Toilette/Flur): Wird bei einer Zone die Quelle gewählt, ändert sich der Router für beide. Beide Entities zeigen dieselbe Quelle.

### Lautstärke

Die Lautstärke ist linear auf die dB-Grenzen abgebildet: `Lautstärke = (dB − Min) / (Max − Min)`. Standard sind **−100 dB** (0.0) bis **+12 dB** (1.0), also −32,8 dB ≙ 0.6. Die Grenzen sind im Options Flow änderbar. Schnell hintereinander gesetzte Werte (Slider) werden zusammengefasst, der letzte gewinnt.

### Zustand

- `idle`, wenn die Zone stumm ist
- `on`, sonst
- `unavailable`, solange die Verbindung getrennt ist

## Optionen

Unter **Einstellungen → Geräte & Dienste → Biamp Tesira → Konfigurieren**:

- **Zonen:** Anzeigename, Router-Tag, Level-Tag(s), mit oder ohne Quellenwahl
- **Quellenliste** je Router
- **Level-Grenzen** in dB
- **Mikrofon-Gate** je Zone: Instance Tag des Level-Blocks oder Sense-Mutes. Der `switch` erscheint erst, wenn ein Tag eingetragen ist.

Die Standardwerte entsprechen der Tabelle oben, nach einem Umzug muss also nichts eingegeben werden.

## Von der alten Version umziehen

1. **Backup** erstellen (Einstellungen → System → Backups). Optional den Ordner `/config/custom_components/tesira/` sichern.
2. Den Ordner `/config/custom_components/tesira/` durch den neuen ersetzen.
3. Home Assistant neu starten. Die bestehende Config Entry wird automatisch migriert und bekommt die Standard-Optionen. Die Entity-Registry wird nicht verändert.
4. Prüfen, ob alle neun Entities mit den alten IDs vorhanden sind und das Dashboard funktioniert.
5. **Quellenliste prüfen** (siehe oben). Die alte Liste enthielt „Mikrofon“ als Index 1, die neue nicht mehr.

## Fehlersuche

- **Entities `unavailable`:** Host, Port und Netzwerk prüfen. Die Integration verbindet sich selbst wieder.
- **Falsche Quelle wird angezeigt:** Die Quellenliste des Routers stimmt nicht mit der Tesira überein.
- **Protokoll mitlesen:** Für den Logger `custom_components.tesira.client` das Level `debug` setzen.

  ```yaml
  logger:
    logs:
      custom_components.tesira.client: debug
  ```

- **Diagnose:** Beim Gerät **Diagnose herunterladen** wählen und die Datei an ein Problem anhängen. Der Host ist darin ausgeblendet.

## Entwicklung

```bash
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python pytest-homeassistant-custom-component ruff mypy
.venv/bin/python -m pytest
.venv/bin/ruff check . && .venv/bin/mypy
```

Alle Tests laufen gegen einen Fake-TTP-Server (`tests/fake_tesira.py`). **Tests und Experimente laufen nie gegen die echte Tesira.**
