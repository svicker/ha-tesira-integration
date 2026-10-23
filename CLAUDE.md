# Auftrag: Home-Assistant-Integration `tesira` neu entwickeln

Diese Datei ist die Übergabe für Claude Code. Lege sie als `CLAUDE.md` in den Projektordner (z. B. `tesira-ha/`) und starte Claude Code dort. Erster Satz an Claude Code:

> Lies CLAUDE.md vollständig. Lies danach die alte Integration unter `old/custom_components/tesira/` und fasse zusammen, was sie kann und welche Werte sie fest verdrahtet hat. Erst dann plane die Neuentwicklung und warte auf mein OK.

---

## 1. Ziel

Eine moderne Custom Integration (Domain `tesira`) für eine **Biamp Tesira Forté AVB TI** im Schützenhaus (Schützenverein Icker e.V.). Sie steuert Quellenwahl, Lautstärke, Stumm und die Mikrofonfreigabe pro Zone über das **Tesira Text Protocol (TTP)** per Telnet.

Warum neu: Die alte Integration hat feste Quellenlisten im Code, keine Optionen und keine Diagnose. Nach Änderungen an der Tesira-Config (Mikrofon-Eingang aus den Routern entfernt) stimmen die Quellennummern nicht mehr. Alles Konfigurierbare soll künftig in der HA-Oberfläche einstellbar sein.

Die Integration wird aus einem Dashboard bedient, das Laien benutzen. Sie muss deshalb robust sein: Verbindungsabbruch, Neustart der Tesira und Neustart von HA dürfen nichts dauerhaft kaputt machen.

## 2. Umgebung

- Home Assistant 2026.10.x, Python wie im HA-Core vorgegeben, vollständig async, nichts Blockierendes im Event-Loop.
- Tesira: Host `172.30.1.12`, Port `23` (Telnet/TTP). Host und Port gehören in den Config Flow, nicht in den Code.
- Zielordner in HA: `/config/custom_components/tesira/`. Das Repo soll HACS-tauglich sein (`hacs.json`, `manifest.json` mit Version, `README.md`, `brand`-Ordner optional).
- Sprache der Oberfläche: Deutsch und Englisch (`translations/de.json`, `translations/en.json`).

## 3. Wichtig: bestehende Entities und IDs erhalten

Das Dashboard und Automationen verweisen auf die bisherigen Entities. Neue Version muss **dieselben `unique_id`s und `entity_id`s** liefern. Prüfe das zuerst im alten Code (aktuell `<entry_id>_<schlüssel>`).

| Entity | Schlüssel | Art |
|---|---|---|
| `media_player.tesira_klubraum` | `klubraum` | Quellen + Lautstärke + Stumm |
| `media_player.tesira_saal` | `saal` | Quellen + Lautstärke + Stumm |
| `media_player.tesira_ela_saal` | `ela_saal` | nur Lautstärke + Stumm, keine Quellen |
| `media_player.tesira_ela_kk_stand` | `ela_kk_stand` | Quellen + Lautstärke + Stumm |
| `media_player.tesira_ela_theke` | `ela_theke` | Quellen + Lautstärke + Stumm |
| `media_player.tesira_ela_aussen` | `ela_aussen` | Quellen + Lautstärke + Stumm |
| `media_player.tesira_ela_aussen_sitzen` | `ela_aussen_sitzen` | Quellen + Lautstärke + Stumm |
| `media_player.tesira_ela_toilette` | `ela_toilette` | Quellen + Lautstärke + Stumm |
| `media_player.tesira_ela_flur` | `ela_flur` | Quellen + Lautstärke + Stumm |

Alle gehören zu **einem** Gerät „Tesira“ (Hersteller Biamp, Modell „Tesira Forté AVB TI“).

## 4. Tesira-Config (Stand Export v3, Partition „Audio Partition1“)

### 4.1 Zonen, Router und Level-Blöcke

Ein Quellen-Router (Source Selector) kann mehrere Level-Blöcke versorgen. Quelle wählen = Router, Lautstärke und Stumm = Level.

| Zone (Entity) | Router (Instance Tag) | Level (Instance Tag) | Anmerkung |
|---|---|---|---|
| Klubraum | `SourceRouterKlubRaum` | `LevelKlubRaum` | |
| Saal | `SourceRouterSaal` | `LevelSaal` | aktive Fullrange-Lautsprecher, alle Quellen |
| ELA Saal | – | `LevelELASaal` | 100-V-ELA, **nur Mikrofone**, keine Quellenwahl |
| ELA KK-Stand | `SourceRouterKKStand` | `LevelELAKKStand` | |
| ELA Theke | `SourceRouterTheke` | `LevelELATheke` | |
| ELA Außen | `SourceRouterAussen` | `LevelELAAussen` | Router wird mit „Außen Sitzen“ geteilt |
| ELA Außen Sitzen | `SourceRouterAussen` | `LevelELAAussenSitzen` | gleicher Router wie Außen |
| ELA Toilette | `SourceRouterToiletteFlur` | `LevelELAToilette` | Router wird mit Flur geteilt |
| ELA Flur | `SourceRouterToiletteFlur` | `LevelELAFlur` | gleicher Router wie Toilette |

Folge: Wird bei Außen oder Außen Sitzen die Quelle gewählt, ändert sich der Router für beide. Die Quellen-Anzeige beider Entities muss deshalb aus demselben Routerwert kommen (kein Auseinanderlaufen).

### 4.2 Mikrofone und Ducking

- Mikrofon-Level: `LevelMic1`, `LevelMic2`. Automixer: `Mixer1` (Label „AutoMixerMic“). Mikrofone sind **nicht mehr** Quelle der Router.
- Ducker pro Zone, die Musik absenken, wenn gesprochen wird: `DuckerKlubRaum`, `DuckerSaal`, `DuckerELATheke`, `DuckerELAKKStand`, `DuckerELAAussen`, `DuckerELAAussenSitzen`, `DuckerELAToilette`, `DuckerELAFlur`.
- Geplant, aber in Tesira noch nicht entschieden: die Mikrofone sollen pro Zone ein- und ausschaltbar sein. Das Gate ist entweder ein Level-Block vor dem Sense-Eingang des Duckers oder das Stummschalten des Sense. Baue die Integration so, dass je Zone ein **frei wählbarer Instance Tag** für dieses Gate (Mute-Schalter) in den Optionen eingetragen werden kann und die Entity (`switch`) erst erscheint, wenn ein Tag gesetzt ist.
- Optional je Ducker: `Bypass` als `switch`, `Ducking Level` als `number` (dB). Standardmäßig deaktiviert („entity_registry_enabled_default = False“).

### 4.3 Quellen-Zuordnung (konfigurierbar!)

`sourceSelection` ist ein Integer: **0 = keine Quelle (Aus)**, 1…n = Eingang im Router. Die alte Liste war `1 Mikrofon, 2 Apple TV, 3 SAT TV, 4 Musik, 5 PC Theke`.

Nach dem Entfernen des Mikrofons ist die erwartete neue Liste (**nicht fest einbauen, vor Gebrauch am Gerät prüfen**):

| Index | Name |
|---|---|
| 0 | Aus |
| 1 | Apple TV |
| 2 | SAT TV |
| 3 | Musik |
| 4 | PC Theke |

Anforderungen:
- Die Zuordnung Name → Index wird **pro Router** im Options Flow gepflegt, mit obiger Liste als Vorschlag. Router können abweichende Listen haben.
- Optional beim Einrichten: Anzahl der Eingänge per `"<Tag>" get numInputs` und vorhandene Labels per `"<Tag>" get inputLabel <n>` abfragen, falls der Block das liefert. Nur als Hilfe zum Vorbefüllen, nie als alleinige Wahrheit.
- Unbekannter Wert vom Gerät (z. B. Index, der nicht in der Liste steht): Quelle als `None` melden und einmal eine Warnung loggen. Nicht abstürzen.
- Quellen-Namen müssen frei umbenennbar sein. Das Dashboard ruft `media_player.select_source` mit dem Namen auf.

### 4.4 Lautstärke

- Level-Block: `"<Tag>" set level 1 <dB>`, `"<Tag>" set mute 1 <true|false>`.
- Die Abbildung dB ↔ 0.0…1.0 muss **das gleiche Verhalten** haben wie die alte Integration, weil das Dashboard darauf abgestimmt ist. Lies die Formel und die Grenzen (Min/Max dB) aus dem alten Code und übernimm sie als Optionen mit denselben Standardwerten. Beobachtet: `-100 dB` entspricht dem unteren Anschlag („0“), bei `-32.8 dB` meldet die Entity 0.6.
- Setzen der Lautstärke schnell hintereinander (Slider) darf die Verbindung nicht fluten: Befehle drosseln/zusammenfassen (letzter Wert gewinnt, z. B. 50 ms).
- Zustand der Entity: `on`, wenn nicht stumm und Quelle ≠ Aus oder Level-only-Zone nicht stumm. `idle` bei Stumm, `off` nur wenn die alte Integration das so tat. Übernimm das Verhalten der alten Version, sofern nichts Besseres in der Analyse auffällt, und dokumentiere es.

## 5. Protokoll (TTP über Telnet)

Gelerntes aus den Debug-Logs der alten Version:

```
>>  "SourceRouterKlubRaum" set sourceSelection 4
<<  "SourceRouterKlubRaum" set sourceSelection 4     (Echo)
<<  +OK
<<  ! "publishToken":"SourceRouterKlubRaum" "value":4  (Subscription-Push)
>>  "LevelSaal" set level 1 -32.8
<<  +OK
```

Verlange nichts, was nicht zu belegen ist. Prüfe gegen die offizielle Biamp-Dokumentation „Tesira Text Protocol“:
- Telnet-Aushandlung (IAC-Sequenzen beim Verbinden sauber verwerfen), Begrüßungstext, ggf. Login. Die Tesira läuft hier ohne Anmeldung, die Optionen sollen aber optional `username/password` zulassen.
- Mit `SESSION set verbose false` (falls unterstützt) kürzere, leichter parsbare Antworten.
- Antworten: `+OK` (mit optional `"value":…`), `-ERR …`. Push-Meldungen beginnen mit `!`.
- Subscriptions: `"<Tag>" subscribe sourceSelection <n> <customLabel>` bzw. `subscribe level`/`mute`. Beim Start abonnieren, damit HA Änderungen von außen (Tesira-Software, andere Bedienung) sofort sieht, ohne zu pollen.
- **Wichtig bei Fehlern:** Eine fehlerhafte Zeile darf nicht die Zuordnung Antwort ↔ Befehl durcheinanderbringen. Befehle seriell abarbeiten (eine Anfrage in Flug, Timeout 5 s), Push-Zeilen getrennt behandeln.

## 6. Architektur-Vorgaben

- `custom_components/tesira/` mit: `__init__.py`, `manifest.json`, `const.py`, `config_flow.py` (inkl. Options Flow), `client.py` (reiner Protokoll-Client, **ohne HA-Importe**, einzeln testbar), `coordinator.py` oder `entity.py`, `media_player.py`, optional `switch.py`, `number.py`, `diagnostics.py`, `strings.json`, `translations/`.
- `iot_class: local_push`. `config_flow: true`. Version in `manifest.json` setzen.
- **Ein** TCP-Verbindungsobjekt pro Config Entry, automatischer Reconnect mit Backoff (1 s → max 30 s). Während getrennt: Entities `unavailable`, nach dem Reconnect Status per `get` neu laden und Subscriptions erneuern.
- Beim Entladen der Entry sauber schließen. Keine Tasks hinterlassen.
- Config Flow: Host, Port, optional Benutzer/Passwort, Verbindungstest vor dem Anlegen (`unique_id` = Host, doppelte verhindern). Reconfigure-Flow für Host/Port.
- Options Flow: Zonen (Router-Tag, Level-Tag(s), Anzeigename, mit Quellen oder ohne), Quellenliste pro Router, Level-Grenzen in dB, optionale Mikrofon-Gate-Tags. **Standardwerte = Tabellen in Abschnitt 4**, damit nach der Migration nichts eingegeben werden muss.
- Migration: Bestehende Config Entry der alten Version (hat keine Optionen) muss weiter laden und die Standardwerte bekommen (Config-Entry-Version erhöhen, `async_migrate_entry`). Entity-Registry nicht verändern.
- `diagnostics.py`: Konfiguration (Host ausblenden), Verbindungsstatus, zuletzt empfangene Werte pro Tag, letzte 50 Protokollzeilen.
- Logging: Protokollzeilen nur auf `DEBUG`, im Logger `custom_components.tesira.client`.
- Dienste (optional): `tesira.send_raw` ist **nicht** gewünscht. Keine freie Befehlseingabe.

## 7. Qualität und Tests

- Typannotationen, `ruff`, `mypy` sauber. Kein `time.sleep`, keine blockierenden Sockets.
- `tests/` mit `pytest` und `pytest-homeassistant-custom-component`.
- **Fake-TTP-Server** (`tests/fake_tesira.py`, asyncio), der die obigen Zeilen nachbildet, inkl. Echo, `+OK`, `-ERR`, Subscriptions, Verbindungsabbruch. Alle Tests laufen dagegen.
- Testfälle mindestens: Quelle setzen und Push zurücklesen; Lautstärkeabbildung hin und zurück; Stumm; geteilter Router Außen/Außen Sitzen; unbekannter Quellenindex; `-ERR`; Reconnect mit erneuter Subscription; Migration einer Alt-Entry; Options Flow ändert die Quellenliste.
- **Niemals Tests oder Experimente gegen die echte Tesira ausführen**, ohne dass ich es ausdrücklich bestätige. Im Schützenhaus läuft Musik. Lesende Befehle (`get`) sind in Ordnung, schreibende (`set`) nur nach Rückfrage.

## 8. Arbeitsweise und Ergebnis

1. Alten Code lesen, Zusammenfassung und offene Fragen zeigen, auf mein OK warten.
2. `client.py` + Fake-Server + Tests zuerst, dann Entities, dann Flows.
3. Nach jedem Schritt: Tests laufen lassen, kurz berichten.
4. Zum Schluss: `README.md` (Installation per HACS/manuell, Einrichtung, Quellenliste prüfen), `CHANGELOG.md`, Anleitung „Alt → Neu umziehen“ (Backup, Ordner ersetzen, HA neu starten, Entities prüfen).

Definition of Done:
- Alle neun Entities behalten ihre IDs, die Quellenliste ist im Options Flow änderbar, „Mikrofon“ kommt nicht mehr vor.
- Änderungen an der Tesira von außen erscheinen in HA ohne Verzögerung.
- Tesira aus- und einschalten bzw. Netzwerk trennen: Entities werden `unavailable` und kommen von selbst zurück.
- Tests grün, `ruff` und `mypy` ohne Fehler.

## 9. Offene Punkte, die ich selbst kläre

- Tatsächliche Eingangsreihenfolge je Router nach dem Entfernen des Mikrofons (per `get inputLabel` oder durch Hören).
- Gate für Mikrofone je Zone (Level-Block oder Sense-Mute) und damit die Tags für Abschnitt 4.2.
- Haus = ELA Theke + ELA KK-Stand + ELA Toilette/Flur und Outdoor = ELA Außen + ELA Außen Sitzen werden im Dashboard per Skript gebündelt, nicht in der Integration.
