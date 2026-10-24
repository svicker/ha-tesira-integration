# Changelog

## 2.1.0

### Neu
- **Mikrofon-Gates:** Für jede Zone mit Gate gibt es jetzt standardmäßig einen Schalter `switch.tesira_<zone>_mikrofon` („<Zone> Mikrofon“). An = Mikrofon hörbar (Gate nicht stumm), Aus = Gate stumm, also invertiert zum Tesira-Parameter `mute`. Standardwerte: `MicGateKlub`, `MicGateSaal`, `MicGateKKStand`, `MicGateELATheke`, `MicGateELAAussen`, `MicGateELAAussenSitz`, `MicGateELAToilette`, `MicGateELAFlur`. `ela_saal` hat kein Gate.
- Das Gate wird beim Start und beim Reconnect nur gelesen und abonniert, nie geschrieben.
- Options Flow: Geänderte Gate- und Ducker-Tags werden beim Speichern nur lesend gegen die Tesira geprüft. Ein unbekannter Tag wird am Feld gemeldet, es wird nichts geschrieben. Ist die Tesira offline, entfällt die Prüfung.
- Ein Gate, dessen Tag die Tesira ablehnt, ist `unavailable`. Wird das Tag geleert, verschwindet der Schalter samt Registry-Eintrag.

### Geändert
- Der Ducker der Zone „ELA Außen Sitzen“ heißt in der Tesira jetzt `DuckerELAAussenSitz` (vorher `DuckerELAAussenSitzen`). Standardwert und gespeicherte Optionen sind umgestellt. Ducker-Bypass und Ducking-Pegel behalten ihre `unique_id`s und `entity_id`s.
- Der Name des Gate-Schalters ist fest deutsch, damit die Entity-ID nicht von der HA-Sprache abhängt.
- Config-Entry-Version 3. Die Migration füllt **leere** Gates mit den Standardwerten und benennt den Ducker nur um, wenn dort noch der alte Name steht. Werte, die du selbst gesetzt hast, bleiben. Ein bewusst geleertes Gate wird dabei wieder mit dem Standard gefüllt.

### Intern
- Fake-Server und Tests um die Gates erweitert (67 Tests).

## 2.0.2

### Behoben
- Steuerzeichen in empfangenen Zeilen (zum Beispiel ein Backspace mitten im Tag einer Echo-Zeile) werden sofort beim Einlesen entfernt. Dadurch passen Tags und Labels immer, und das Protokoll-Log (Diagnose) enthält nur lesbaren Text.

### Intern
- Der Fake-Server kann Steuerzeichen in Echo-Zeilen und Pushes einstreuen. Neue Tests dafür (58 insgesamt).

## 2.0.1

### Geändert
- Beim Verbinden werden jetzt zuerst alle Werte gelesen (`get sourceSelection` je Router, `get level 1` und `get mute 1` je Level-Block) und erst danach die Subscriptions angelegt. Vorher wurde pro Wert abwechselnd abonniert und gelesen.
- Die Entities werden erst verfügbar, wenn das abgeschlossen ist. Werte der vorigen Verbindung werden vorher verworfen, nach einem Reconnect erscheint also nie die alte Quelle.
- Ein Router ohne Wert vom Gerät zeigt keine Quelle an (nie „Aus“).

### Intern
- Tests: Router steht beim Verbinden schon auf einer Quelle, Reihenfolge der Befehle, Reconnect, Änderung zwischen `get` und `subscribe`. Eine Race im Fake-Server beim Stoppen ist behoben.

## 2.0.0

Neuentwicklung der Integration. Die neun `media_player`-Entities behalten ihre `unique_id`s und `entity_id`s.

### Neu
- Protokoll-Client ohne HA-Importe: eine Verbindung, serielle Befehle mit 5 s Timeout, Push-Zeilen getrennt, Reconnect mit Backoff (1 s bis 30 s), Telnet-Aushandlung, optionaler Login.
- Subscriptions für Level, Stumm und Quelle: Änderungen von außen erscheinen sofort, ohne Polling.
- Entities sind `unavailable`, solange die Verbindung fehlt, und laden nach dem Reconnect Werte und Subscriptions neu. Ist die Tesira beim Start aus, bleibt die Integration geladen und verbindet sich später.
- Options Flow: Zonen (Name, Router, Level, Gate, Ducker), Quellenliste je Router, Lautstärke-Grenzen in dB. Standardwerte entsprechen der bisherigen Konfiguration.
- Reconfigure-Flow für Host, Port und Zugangsdaten.
- Optionale Entities: Mikrofon-Gate je Zone (`switch`, nur mit Tag), Ducker-Bypass (`switch`) und Ducking-Pegel (`number`), beide standardmäßig deaktiviert.
- Diagnose-Download (Host ausgeblendet, letzte Werte, letzte 50 Protokollzeilen).
- Übersetzungen Deutsch und Englisch.
- Eigenes Icon im Ordner `brand/` (neutrales Lautsprecher-Symbol, nicht das Biamp-Logo).
- Lautstärkebefehle werden gedrosselt: der letzte Wert innerhalb von 50 ms gewinnt.

### Geändert
- Quellenliste ohne „Mikrofon“: Aus 0, Apple TV 1, SAT TV 2, Musik 3, PC Theke 4. **Vor Gebrauch mit der Tesira abgleichen.**
- Ein Quellenindex, der nicht in der Liste steht, ergibt keine Quelle (`None`) und eine einmalige Warnung je Index.
- Die Quelle kommt aus dem Router, nicht aus der Zone: Zonen mit geteiltem Router (Außen/Außen Sitzen, Toilette/Flur) zeigen immer dieselbe Quelle.
- Fehler der Tesira (`-ERR`) und Timeouts werden gemeldet statt verschluckt. Nach einem Timeout wird die Verbindung neu aufgebaut.
- Die Config Entry wird beim Start migriert (Version 1 auf 2): Standard-Optionen, Kennung `host:port` auf `host`. Die Entity-Registry bleibt unverändert.
- Lautstärke-Abbildung unverändert: linear von −100 dB (0.0) bis +12 dB (1.0).
- Zustand unverändert: `idle` bei Stumm, sonst `on`.

### Bekannte Einschränkungen
- Nicht gegen die echte Tesira getestet (siehe README, „Unbelegte Annahmen“).
- Zonen lassen sich nicht anlegen oder löschen.
