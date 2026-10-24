# Changelog

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
