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

## Einparameter-Versuch zur Symbolzuordnung (06.10.2026)

Die kalibrierte Sieben-Fälle-Folgerunde wurde separat unter `build/label-review/followup-2026-10-06/` abgeschlossen. Alle zehn auswertbaren Klicks waren korrekt. Die fünf geänderten Fälle ergaben zweimal bisher, einmal Versuch, einmal gleich und einmal beidseits schlecht; die zwei Kontrollen wurden als gleich beurteilt. Zwei geänderte Fälle erlaubten keine Klickwertung.

Der neue Versuch verändert ausschließlich `label.source_association.ambiguity_weight` von **20 auf 60**. Kandidatenabstände und Linienlängen-Gewicht bleiben unverändert. Das Gewicht bestraft Beschriftungen, deren Nähe zu anderen Symbolen die Zuordnung erschwert. Es ist keine Produktionsänderung und liefert keine automatische Empfehlung.

Der eingefrorene Satz unter `build/label-review/ownership-2026-10-06-v1/` umfasst zwölf Fälle: pro Edition drei Änderungen und eine pixelgleiche Kontrolle. Alle Fälle erlauben Klickwertung. Die Bilder stammen aus den zusammengefügten Atlas-PDFs aktueller Teilbuilds, einschließlich des bestehenden Detailkarten-Labeltransfers. Baseline und Versuch enthalten dieselben Sterne, DSO-Symbole und sichtbaren Beschriftungen. Der Generator filtert überlagerte oder große Zielsymbole, mögliche Verwechslungen mit Sternen und harte Befunde innerhalb des Ausschnitts. Jede Änderung stammt von einer anderen Karte; die Auswahl erfolgt anhand bestehender Zuordnungsmehrdeutigkeit und tatsächlicher Platzierungsänderung, ohne einen besseren Versuchsscore zu verlangen. Die Ausschnitte wurden visuell geprüft.

Zwei Pocket-Karten wurden wegen neuer harter Befunde in der Versuchsfassung ausgeschlossen, auch wenn deren Gesamtzahl auf einer Karte gleich blieb. Bereits vorhandene Befunde außerhalb aufgenommener Ausschnitte bleiben dokumentiert. Die geprüften Ausschnitte bilden deshalb keinen Nachweis, dass das Gewicht 60 atlasweit sicher oder besser wäre. Vier weitere Karten bleiben für eine spätere Gegenprobe unbenutzt.

Start und Auswertung:

```bash
.venv/bin/python tools/label_review/server.py serve --port 8766 --manifest build/label-review/ownership-2026-10-06-v1/cases.json --responses build/label-review/ownership-2026-10-06-v1/responses.jsonl
.venv/bin/python tools/label_review/server.py summary --responses build/label-review/ownership-2026-10-06-v1/responses.jsonl
```

Die 50-mm-Kalibrierung ist verpflichtend; die Antworten früherer Runden bleiben getrennt. Der Seed ist `20261006`. Konfigurationskopien liegen unter `config/`, Parameter und zusätzliche Pocket-Karten in `experiment.json`, Auswahlbefunde und Bildprüfsummen in `curation.json`. SHA256-Werte dokumentieren den verwendeten Arbeitsstand der Python-Dateien und gebündelten Fonts; ein Git-Commit allein erfasst vorhandene uncommittete Änderungen nicht. Für erneute Builds muss derselbe dokumentierte Arbeitsstand und Datenbestand verfügbar sein.

Erzeugung eines neuen, getrennten Satzes:

```bash
.venv/bin/python tools/label_review/make_ownership_experiment.py --outdir build/label-review/ownership-repeat prepare
.venv/bin/python tools/label_review/make_ownership_experiment.py --outdir build/label-review/ownership-repeat build --edition pocket
.venv/bin/python tools/label_review/make_ownership_experiment.py --outdir build/label-review/ownership-repeat build --edition standard
.venv/bin/python tools/label_review/make_ownership_experiment.py --outdir build/label-review/ownership-repeat build --edition deep
.venv/bin/python tools/label_review/make_ownership_experiment.py --outdir build/label-review/ownership-repeat build --edition pocket --batch pocket-extra
.venv/bin/python tools/label_review/make_ownership_experiment.py --outdir build/label-review/ownership-repeat curate
```

Der Generator benötigt die vorhandenen Kataloge, Cairo, die installierte Atlas-Pipeline und `pdftoppm`. Er protokolliert Layouts über temporäre Funktionswrapper nur im eigenen Prozess; Produktionsmodule und -konfigurationen werden nicht verändert. Er erzeugt keine Karten während einer Bewertung. Neue Sätze sind vor der Bewertung erneut visuell zu prüfen. Der Generator verweigert das Überschreiben vorhandener Bilder mit anderen Pixelinhalten. Die aktuelle Bildnamenskonvention ist für diesen Versuch festgelegt: vor einer Wiederholung mit veränderten Quellen neue Asset-Präfixe verwenden, damit bereits bewertete Bilder unverändert bleiben.

## Gegenprobe und Konfliktdiagnose (07.10.2026)

Die Konflikte von P12/P25 wurden mit `diagnose_ownership_conflicts.py` reproduziert. Das Werkzeug zeichnet Greedy-Zustand, lokale Reparatur, gemeinsame Suche, harte Reparatur und finales Layout auf. Alle vier finalen Seiten stimmen in Labelgeometrie und Befund-IDs exakt mit dem ursprünglichen Versuch überein. Die betroffenen Labels haben statisch gültige Kandidaten, aber keinen freien Kandidaten bei festgehaltenen Nachbarlabels. Große Komponenten werden nicht gemeinsam optimiert; die begrenzte lokale Reparatur löst die Blockaden nicht vollständig. Ihre Knoten- und Suchzahlbudgets werden dabei nicht ausgeschöpft. Diagnose: `build/label-review/ownership-2026-10-07-diagnostics-v1/report.md`.

Die neuen Teilatlanten enthalten die vorab reservierten S083, S094, D120, D260 sowie acht weitere Pocket-Karten. Beide Deep-Gegenproben erzeugen neue harte Befund-IDs bei Gewicht 60: D120 hat 17 → 16 Befunde, aber zwei neue; D260 verschlechtert sich von null auf einen. Beide werden ausgeschlossen und bleiben im vollständigen Seitenaudit sichtbar. Gewicht 60 ist damit vorerst keine sichere allgemeine Produktionsregel.

Der verbleibende eingefrorene Satz enthält **acht Fälle: vier Pocket-Änderungen, zwei Standard-Änderungen und zwei pixelgleiche Kontrollen**. Jede Änderung stammt von einer anderen Karte. Die Ausschnitte sind visuell geprüft, klickauswertbar und ohne harte Befunde; ihre Quellkarten sind ebenfalls konfliktfrei. Seed `20261007`, neues Asset-Präfix `own2`, eigener Antwortpfad. Es wurden keine anderen Gewichte oder Reparaturparameter geändert.

```bash
.venv/bin/python tools/label_review/server.py serve --port 8766 --manifest build/label-review/ownership-validation-2026-10-07/cases.json --responses build/label-review/ownership-validation-2026-10-07/responses.jsonl
.venv/bin/python tools/label_review/server.py summary --responses build/label-review/ownership-validation-2026-10-07/responses.jsonl
```

Reproduktion in neuen Verzeichnissen:

```bash
.venv/bin/python tools/label_review/diagnose_ownership_conflicts.py --from-experiment build/label-review/ownership-2026-10-06-v1 --outdir build/label-review/ownership-diagnostic-repeat
.venv/bin/python tools/label_review/make_ownership_experiment.py --outdir build/label-review/ownership-validation-repeat prepare --preset validation
.venv/bin/python tools/label_review/make_ownership_experiment.py --outdir build/label-review/ownership-validation-repeat build --edition pocket
.venv/bin/python tools/label_review/make_ownership_experiment.py --outdir build/label-review/ownership-validation-repeat build --edition standard
.venv/bin/python tools/label_review/make_ownership_experiment.py --outdir build/label-review/ownership-validation-repeat build --edition deep
.venv/bin/python tools/label_review/make_ownership_experiment.py --outdir build/label-review/ownership-validation-repeat curate
```

`--preset validation` legt Kartenpool, Zielquoten und Mindestzahl vor dem Build fest. Ungültige Seiten werden nicht durch andere Deep-Felder ersetzt. Selbst eine positive Bewertung der gültigen Ausschnitte hebt die bekannten Deep- und Pocket-Regressionen nicht auf.

Die Reservierung der vier S/D-Karten gilt für den Einparameter-Versuch. Ein nachträglicher Abgleich mit dem älteren Führungslinienversuch zeigt: S083/S094 kamen dort bereits als Kontrollen anderer Ziele vor, D120/D260 als Änderungen anderer Ziele. Die jetzigen sechs Änderungsausschnitte wurden zuvor nicht bewertet; Centaurus A war allerdings bereits ein Standard-Kontrollziel. Alle vier Pocket-Änderungskarten sind neu. Der Satz ist somit eine Gegenprobe mit neuen Ausschnitten, keine vollständig ungesehene Kartenstichprobe für denselben Beobachter.

## Kurze Linien bei langen Beschriftungen (07.10.2026)

Nach den Hinweisen zu ESO274-001 und Centaurus A prüft ein separater Satz ausschließlich eine zusätzliche kurze Führungslinie. Das Zuordnungsgewicht bleibt **20**; Labelpositionen, Kandidaten, Texte und Karteninhalt bleiben identisch. Die Baselines reproduzieren die gespeicherten Baseline-Layouts der Gegenprobe exakt. Beide Ziele wurden bereits gesehen; dies ist ein gezielter Vergleich, keine ungesehene Validierungsstichprobe.

`make_long_label_line_experiment.py` erzeugt zwei Änderungen und zwei pixelgleiche Kontrollen aus zusammengesetzten Atlas-PDFs. Die Linien sind 1,394 mm (P37/Centaurus A) und 1,545 mm (S094/ESO274-001) lang. Bestehende Linienrouten bleiben unverändert. Alle vier Quellseiten sind ohne harte Layoutbefunde; die Ausschnitte wurden visuell geprüft. Der Eingriff erfolgt nach der Optimierung ausschließlich im Forschungsprozess. Gespeicherte Optimiererkosten beschreiben die ursprüngliche Platzierung; sie entscheiden nicht über die Aufnahme der Linienvariante.

```bash
.venv/bin/python tools/label_review/server.py serve --port 8766 --manifest build/label-review/long-label-lines-2026-10-07/cases.json --responses build/label-review/long-label-lines-2026-10-07/responses.jsonl
.venv/bin/python tools/label_review/server.py summary --responses build/label-review/long-label-lines-2026-10-07/responses.jsonl
```

Reproduktion mit neuem Ausgabeverzeichnis und neuem Asset-Präfix/Experiment-ID im Generator:

```bash
.venv/bin/python tools/label_review/make_long_label_line_experiment.py --outdir build/label-review/long-label-repeat prepare
.venv/bin/python tools/label_review/make_long_label_line_experiment.py --outdir build/label-review/long-label-repeat build --edition pocket --variant baseline
.venv/bin/python tools/label_review/make_long_label_line_experiment.py --outdir build/label-review/long-label-repeat build --edition pocket --variant trial
.venv/bin/python tools/label_review/make_long_label_line_experiment.py --outdir build/label-review/long-label-repeat build --edition standard --variant baseline
.venv/bin/python tools/label_review/make_long_label_line_experiment.py --outdir build/label-review/long-label-repeat build --edition standard --variant trial
.venv/bin/python tools/label_review/make_long_label_line_experiment.py --outdir build/label-review/long-label-repeat curate
```

Identische Reproduktionen dürfen dieselben Bilddateien wiederverwenden; abweichende Pixel werden nicht überschrieben. Die 50-mm-Kalibrierung ist verpflichtend, Antworten bleiben im eigenen JSONL. Zwei bekannte Ziele können einen späteren allgemeinen Automatismus für lange Beschriftungen noch nicht begründen.

## Gezielte deterministische Linienregel (07.10.2026)

Die nächste Forschungsvariante liegt unter `build/label-review/targeted-lines-2026-10-07/`. `make_targeted_line_experiment.py` verwendet gemessene Schriftbreite (≥8 mm), Breite/Höhe (≥4) und vorhandene Mehrdeutigkeitssignale. Nur gültige Linien bis 3 mm werden ergänzt; bestehende Routen und alle Labelpositionen bleiben erhalten. Gewicht 20 bleibt unverändert. Das sind explorative Schwellen, keine Produktionsregel.

Vier Himmelsregionen pro Edition und zwei ergänzte südliche Galaxienfelder ergeben 14 geprüfte Hauptkartenpaare. Drei zusätzliche Linien, keine neuen harten Befunde. Fünf bereits bestehende Befunde bleiben dokumentiert. Der kleine Bewertungssatz enthält zwei Änderungen und drei pixelgleiche Kontrollen. Bei den Änderungen wird wegen großem Symbol beziehungsweise nahem Stern ausschließlich die Präferenz ausgewertet. Frühere Zielobjekte werden ausgeschlossen; die adaptive Felderweiterung und bekannte Quellkarten begrenzen die Aussagekraft. Der lokale Bericht enthält sämtliche Entscheidungen und den Seitenvergleich.

```bash
.venv/bin/python tools/label_review/server.py serve --port 8766 --manifest build/label-review/targeted-lines-2026-10-07/cases.json --responses build/label-review/targeted-lines-2026-10-07/responses.jsonl
.venv/bin/python tools/label_review/server.py summary --responses build/label-review/targeted-lines-2026-10-07/responses.jsonl
```

Reproduktion: `make_targeted_line_experiment.py --outdir <neues Verzeichnis> prepare`, dann `build --edition pocket|standard|deep --variant baseline|trial` für jede Kombination. Zusätzlich beide Varianten mit `--edition standard --batch southern-standard` und `--edition deep --batch southern-deep` bauen. Anschließend `curate`. Neue Versuche mit abweichenden Quellen benötigen neue Experiment-ID und neues Asset-Präfix. Vorhandene Bilder werden bei abweichenden Pixeln nicht überschrieben. Konfigurationen, Seed und Quellenprüfsummen werden gespeichert; Kartenbau und Bewertung bleiben getrennt.
