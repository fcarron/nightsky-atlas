# Lokale Blindbewertung von Kartenlabels

Das Werkzeug zeigt gepaarte Ausschnitte aus Atlas-Builds, erfasst die Symbolzuordnung und eine anschließende Präferenz. Es ändert weder Layouts noch Konfiguration oder astronomische Daten. Es verwendet Python-Standardbibliothek und statische HTML/CSS/JavaScript-Dateien.

## Start

Im Repository ausführen:

```bash
.venv/bin/python tools/label_review/server.py serve
```

Dann `http://127.0.0.1:8765/` öffnen. Mit Strg+C wird der Server beendet. Er bindet ausschließlich an `127.0.0.1`. Die Antworten des kuratierten Satzes landen append-only unter `build/label-review/curated-2026-10-01.jsonl`. Die drei Antworten des ersten Bedienungsversuchs bleiben in `build/label-review/responses.jsonl`.

Zusammenfassung anzeigen:

```bash
.venv/bin/python tools/label_review/server.py summary
```

Andere lokale Port- und Antwortdatei innerhalb von `build/`:

```bash
.venv/bin/python tools/label_review/server.py serve --port 8766 --responses build/label-review/run-2.jsonl
```

Die Fallliste liegt in `tools/label_review/cases.json`; Bilder müssen unter `tools/label_review/cases/assets/` liegen. Der HTTP-Endpunkt nimmt nur Fall-IDs und die Slots A/B an und kann keine beliebigen Dateipfade oder URLs öffnen.

## Ablauf

Vor dem ersten Fall kann die Anzeige anhand einer 50-mm-Linie kalibriert werden. Der daraus abgeleitete CSS-px/mm-Wert bleibt während einer Runde fest. Die Bilder werden anhand ihrer physischen Breite skaliert und nicht an das Fenster angepasst. Ohne Kalibrierung kann die Runde trotzdem gestartet werden; jede Antwort erhält dann `calibrated: false`.

Die App balanciert die A/B-Zuordnung anhand des im Manifest gespeicherten Seeds. Sie zeigt nur Fallcode, Frage und A/B-Bilder. Varianten-IDs, Zielpunkte und Kontrollstatus bleiben auf dem Server. Nach Klicks auf das mutmaßliche Zielsymbol in beiden Bildern wird die Präferenz abgefragt. Erst danach speichert der Server die Trefferbewertung. Die App zeigt kein richtig/falsch-Feedback während der Runde.

## Case-Format

Jeder Eintrag enthält:

- `case_id`, `chart_id`, `chart_code`, `label_id`, `object_id`, `label_text`, `question`;
- gemeinsame Quellseitengröße, Pixel-Ausschnitt und physische Bildgröße unter `crop`;
- zwei `variants` mit interner ID, lokalem Bildpfad und Quellseite;
- je Variante denselben `crop_box_px`, `source_page_size_px` und `registration_id` sowie `target_px` im Ausschnitt;
- `control: true` für pixelgenau identische Kontrollfälle;
- `accuracy_evaluable: false`, wenn mehrere Objektsymbole innerhalb der Klicktoleranz zusammenfallen. Die Präferenz wird erfasst, die Klickrichtigkeit bleibt dort `null`.

Beim Laden prüft der Server, dass Bilder vorhanden sind, beide PNGs die erwarteten Pixelmaße haben, Quellseiten und Ausschnitte übereinstimmen, die Registrierung gleich ist und die Zielpunkte praktisch deckungsgleich sind. Die Metadaten dokumentieren die Registrierung; sie erkennen keine falsch beschnittenen Pixelinhalte automatisch. Neue Fälle müssen deshalb vor Aufnahme visuell kontrolliert werden.

Der aktuelle Satz enthält **23 Fälle** aus Pocket (6), Standard (8) und Deep (9): **14 Ausschnitte mit einer tatsächlichen Beschriftungsänderung** und **9 pixelgenau identische Kontrollen**. Fünf der geänderten Fälle mit dicht überlagerten Galaxiensymbolen dienen nur der qualitativen Präferenz. Die Ausschnitte stammen aus den fertigen, zusammengefügten Atlas-PDFs, auf 300 dpi gerastert. `source_page` im Manifest nennt PDF und genaue Seitennummer; `crop.box_px` legt auf beiden Seiten denselben Ausschnitt fest. Der frühere Dreifallsatz liegt in `cases-pilot.json`.

Die einzige Versuchsregel ist die konservative Führungslinien-Konfiguration aus `docs/LEADER_LINE_EXPERIMENT.md` (maximaler DSO-Kandidatenabstand 5 statt 2,5 mm; Linienlängen-Gewicht 1 statt 4). Die Versuchsatlanten liegen unter `build/label-review/atlas-conservative*`; die App selbst baut keine Karten. Die zugeschnittenen PNGs liegen bei den Cases und bleiben auch ohne die lokalen Build-Artefakte benutzbar.

## Antwortformat und Auswertung

Jede JSONL-Zeile enthält unter anderem Fall- und Objekt-IDs, Seed, Sitzung, Zuordnung von A/B zu Varianten-IDs, relative Klickkoordinaten, Präferenz, Bearbeitungszeit, Notiz und Anzeige-Kalibrierung. Bei Fällen mit eindeutigem Symbol gilt ein Klick bei höchstens 1,0 mm Abstand zum hinterlegten Symbolzentrum als richtige Zuordnung. Bei `accuracy_evaluable: false` werden die Klickkoordinaten gespeichert, aber nicht als richtig oder falsch gewertet.

`summary` zeigt die Antwort- und Skip-Zahl, die nicht auswertbaren Klickfälle, richtige Symbolzuordnungen pro Variante und Präferenzen pro Variante. „Gleich gut“ und „Beide schlecht“ bleiben eigene Kategorien. Die Auswertung schlägt keine Optimierergewichte vor.

## Grenzen und nächste Kuratierung

Der Satz ist vor der neuen Bewertungsrunde festgelegt. Er enthält bewusst unveränderte Kontrollen, doch die geänderten Fälle stammen überwiegend aus dichten Feldern und teils mehrfach aus derselben Karte. Fünf enge Galaxienpaare liefern nur Präferenzdaten. Einige Quellkarten haben bereits harte Layoutbefunde; die Versuchsseiten haben auf diesen Karten keine zusätzlichen harten Befunde. Da zugleich Abstandsschwelle und Liniengewicht geändert wurden, kann ein beobachteter Effekt nicht einem einzelnen Parameter zugeschrieben werden. Für eine belastbare Entscheidung fehlen noch unabhängige Beobachter, mehr isolierte Änderungsfälle und eine Auswertung je Edition und Objekttyp. Die 23 Fälle sind keine unabhängige Zufallsstichprobe aller Atlaslabels.

Die Kalibrierung gleicht Bildschirm und physische Größe näherungsweise ab. Druckqualität, Monitorkontrast und Betrachtungsabstand können weiterhin von einem tatsächlichen Ausdruck abweichen. Antworten sind subjektive Einzelbeobachtungen; mehrere unabhängige Beobachter sind nötig, bevor Gewichte angepasst werden.

## Lokale Folgerunde vom 01.10.2026

Die erste Runde ergab keinen allgemeinen Zuordnungsgewinn. `cases-followup.json` enthält deshalb nur sieben Fälle: zwei neue lokale Varianten (D201/NGC 4266 und S027/NGC 4618), die früheren Vergleiche D174/NGC 4478, P012/NGC 3227 und P022/NGC 2252 als Gegenprobe sowie zwei pixelgleiche Kontrollen. Die erste 23-Fälle-Runde und ihre Antworten bleiben unverändert.

Diese Runde verlangt eine 50-mm-Anzeigekalibrierung. Vor dem Start die Linie mit einem Lineal messen und `px/mm` anpassen:

```bash
.venv/bin/python tools/label_review/server.py serve --port 8766 --manifest tools/label_review/cases-followup.json --responses build/label-review/followup-2026-10-01.jsonl
```

Die neuen Kartenseiten werden aus realen Katalogen und dem gespeicherten deterministischen Layout erzeugt. Die lokalen Änderungen sind ausschließlich Präsentationszustand; `make_followup_pages.py` setzt feste Kandidaten-IDs, prüft die Linienrouten und verwirft Seiten mit harten Layoutbefunden. Die diagnostischen Ausgangslayouts entstehen mit:

```bash
.venv/bin/python -m nightsky_atlas chart render --chart deep-201 --edition deep --star-store data/processed/stars/tycho2.sqlite --optimize --write-layout --placement-diagnostics --outdir build/leader-followup-2026-10-01/diagnostic-deep --png-dpi 300
.venv/bin/python -m nightsky_atlas chart render --chart standard-027 --edition standard --star-store data/processed/stars/tycho2.sqlite --optimize --write-layout --placement-diagnostics --outdir build/leader-followup-2026-10-01/diagnostic-standard --png-dpi 300
.venv/bin/python tools/label_review/make_followup_pages.py
```

Die neuen Ausschnitte stammen von vollständigen Kartenseiten mit derselben Seite, Projektion und Druckgröße wie im Atlas. D201 und S027 haben keinen Detailkarten-Labeltransfer. Vor einer Produktionsentscheidung sollten die gewählten Änderungen trotzdem noch in einem vollständig zusammengesetzten Atlas geprüft werden.

Bei S027 liegen die Symbolzentren von NGC 4618, IC 3668 und IC 3669 innerhalb von 0,3 mm. Die Variante verteilt zwei Beschriftungen und führt drei Linien zur Gruppe; eine eindeutige Klickwertung für diese drei Symbole ist auf der Standard-Hauptkarte nicht möglich. Der Fall misst ausschließlich die wahrgenommene Lesbarkeit. Auch die Katalogauswahl der beiden IC-Objekte sollte gesondert geprüft werden: Beide sind im importierten OpenNGC als `other` klassifiziert, IC 3669 mit Magnitude 19,07.
