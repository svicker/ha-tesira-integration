## 1. Was sich in Tesira geändert hat

Ich habe für jeden Ducker einen eigenen Level-Block mit Stumm („MicGate…“) vor dem Sense-Eingang eingebaut. Stummschalten sperrt das Mikrofon in dieser Zone: Der Ducker erkennt keine Sprache mehr, und Mix Sense mischt nichts mehr hinein.

Neue Blöcke (Instance Tags, exakt so geschrieben):

| Zone / Entity | Gate-Tag (neu) | Ducker-Tag |
|---|---|---|
| `klubraum` | `MicGateKlub` | `DuckerKlubRaum` |
| `saal` | `MicGateSaal` | `DuckerSaal` |
| `ela_kk_stand` | `MicGateKKStand` | `DuckerELAKKStand` |
| `ela_theke` | `MicGateELATheke` | `DuckerELATheke` |
| `ela_aussen` | `MicGateELAAussen` | `DuckerELAAussen` |
| `ela_aussen_sitzen` | `MicGateELAAussenSitz` | **`DuckerELAAussenSitz`** (umbenannt) |
| `ela_toilette` | `MicGateELAToilette` | `DuckerELAToilette` |
| `ela_flur` | `MicGateELAFlur` | `DuckerELAFlur` |
| `ela_saal` | kein Gate | kein Ducker |

Wichtig:
- **Der Ducker für „Außen Sitzen“ heißt jetzt `DuckerELAAussenSitz`** (vorher `DuckerELAAussenSitzen`). In den gespeicherten Optionen steht noch der alte Name. Ändere die Standardwerte in `const.py`, und sorge dafür, dass ein vorhandener Eintrag mit dem alten Wert beim Laden einmalig auf den neuen Wert migriert wird (Config-Entry-Version erhöhen, `async_migrate_entry`). Der Ducker-Bypass- und Ducking-Pegel-Entity für diese Zone muss danach wieder funktionieren, ohne dass ihre `unique_id` oder `entity_id` wechselt.
- In der Tesira gibt es jetzt zwei Units (Spalte „Unit“ 1 und 2, manche Blöcke sind auf Unit 2). Es gibt trotzdem nur den einen TTP-Zugang unter dem bekannten Host. Prüfe nur lesend (`get mute 1`), dass auch Gates auf Unit 2 darüber erreichbar sind, bevor du etwas schreibst.

## 2. Was die Integration tun soll

### 2.1 Neue Entity pro Gate

Für jede Zone, bei der in den Optionen ein `gate`-Tag steht, legst du einen `switch` an:

- Name: „<Zone> Mikrofon“ (z. B. „Klubraum Mikrofon“), Gerät: dasselbe „Tesira“-Gerät.
- `unique_id`: `<entry_id>_<zonenschlüssel>_mic_gate`, Entity-ID z. B. `switch.tesira_klubraum_mikrofon`.
- **Bedeutung:** `on` = Mikrofon ist in der Zone hörbar, d. h. Gate **nicht** stumm. `off` = Gate stumm. Der Schalter ist also gegenüber dem Tesira-Parameter `mute` invertiert.
- Schreiben: `"<GateTag>" set mute 1 true|false`. Lesen und Abonnieren: `"<GateTag>" get mute 1` und `subscribe mute 1`, damit Änderungen von außen (Tesira-Software) sofort in HA ankommen.
- Standardmäßig **aktiviert** (nicht wie Ducker-Bypass).
- Bei fehlender Verbindung `unavailable`.
- Beim Start und beim Reconnect wird der Zustand nur **gelesen**, nie geschrieben. Die Integration darf nach einem Neustart kein Gate von sich aus ändern.

### 2.2 Standardwerte und Migration der Optionen

Die Tabelle in Abschnitt 1 ist der neue Standard für `gate` (und der Ducker-Name der Zone `ela_aussen_sitzen`). In einer vorhandenen Config Entry stehen die Gates auf `null`. Beim Migrieren fülle `gate` nur, wenn es leer ist, und überschreibe keinen Wert, den ich selbst gesetzt habe. Alle Tags bleiben im Options Flow änderbar.

Im Options Flow soll es beim Speichern einer Zone einen **lesenden** Verbindungstest geben: `"<Tag>" get mute 1` für das Gate und `get bypass` bzw. das Äquivalent beim Ducker. Wenn der Tag nicht existiert, zeig eine Fehlermeldung am Feld an. Es wird dabei nichts geschrieben.

### 2.3 Nicht ändern

- Alle bestehenden Entities, `unique_id`s und `entity_id`s bleiben gleich.
- Ducker-Bypass und Ducking-Pegel bleiben wie sie sind (standardmäßig deaktiviert).
- Keine freie Befehlseingabe.

## 3. Tests

- Fake-TTP-Server um die neuen Blöcke erweitern.
- Fälle: Schalter an/aus schreibt `mute` invertiert; Push vom Gerät ändert den Schalter; Verbindungsabbruch → `unavailable`, Reconnect → Zustand wird gelesen, nichts wird geschrieben; unbekannter Tag im Options Flow → Fehlermeldung; Migration setzt `DuckerELAAussenSitz` und füllt leere Gates, lässt gesetzte Gates in Ruhe.
- **Keine Tests gegen die echte Tesira, die schreiben.** Lesende Befehle sind in Ordnung. Die Gates wirken auf Live-Audio im Schützenhaus, und ich teste sie selbst.
- `ruff`, `mypy`, `pytest` grün. Version in `manifest.json` erhöhen, `CHANGELOG.md` ergänzen.

## 4. Definition of Done

- Für alle acht Gates gibt es einen Schalter, der den Zustand aus Tesira widerspiegelt und ihn schreibt.
- `DuckerELAAussenSitz` ist in den gespeicherten Optionen und in den Standardwerten gesetzt.
- Nach einem HA-Neustart steht kein Gate anders als vorher.
- Tests grün.

## 5. Offene Frage an mich (nicht raten)

Ich habe zusätzlich `MicGateSaal` und das bestehende `LevelELASaal`. Ich kläre selbst, welchen Weg `MicGateSaal` sperrt (Fullrange vor dem Ducker oder die ELA). Gib dazu nach der Umsetzung nur die Entities aus und baue für `ela_saal` **kein** Gate.
