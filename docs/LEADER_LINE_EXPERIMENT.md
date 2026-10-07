# Führungslinien als zusätzliche DSO-Platzierung (30.09.2026)

## Frage

Helfen weiter entfernte DSO-Labelkandidaten mit Führungslinie auf fertigen
Hauptkarten in dichten Galaxienfeldern? Der Versuch vergleicht S053 und D174.
Die vorhandene DSO-Nachbearbeitung kann bereits Kandidat und Linie zusammen
bewerten; bisher war der maximale Abstand eines Linienkandidaten an die
2,5-mm-Schwelle für eine hilfreiche Direktbeschriftung gekoppelt.

## Versuchsaufbau

`dso_candidate_max_gap_mm` trennt diese beiden Schwellen. Der Standardwert
bleibt 2,5 mm; alle bisherigen Editionsstile sind damit unverändert. Zwei
experimentelle Varianten, jeweils für Standard und Deep unter
`build/leader-experiment-2026-09-30/styles/`, erweitern die Kandidaten:

| Variante | Maximaler Label-Symbol-Abstand | Linienlängen-Gewicht |
| --- | ---: | ---: |
| Bisher | 2,5 mm | 4,0 |
| Konservativ | 5,0 mm | 1,0 |
| Explorativ | 8,0 mm | 0,3 |

Einzelkarten wurden mit realen Katalogen, deterministischer Optimierung,
Layout-JSON und 300-dpi-Vorschau gerendert. Zusätzlich wurde die konservative
Variante als Teilatlas mit den zugehörigen Detailkarten gebaut. Für den
Vollatlas-Vergleich stammen die bisherigen PDFs aus
`build/complete-2026-09-30-editions/`; beide Fassungen wurden aus dem PDF
mit Ghostscript bei 300 dpi gerastert. Die drei lokalen Änderungen auf den
fertigen Hauptkarten wurden in 300-dpi-Ausschnitten betrachtet; eine
kalibrierte Druckbeurteilung durch Beobachter steht noch aus.

## Einzelkarten-Stresstest

| Karte / Variante | DSO-Linien | Längste Linie | Ungelöste rechnerische Zuordnungsfälle | Optimiererzeit | Harte Label-Label / Label-DSO-Befunde |
| --- | ---: | ---: | ---: | ---: | ---: |
| S053 bisher | 16 | 1,41 mm | 60 | 33,45 s | 2 / 1 |
| S053 konservativ | 18 | 1,41 mm | 58 | 34,13 s | 2 / 1 |
| S053 explorativ | 17 | 1,44 mm | 59 | 33,57 s | 2 / 1 |
| D174 bisher | 7 | 1,02 mm | 25 | 22,59 s | 0 / 0 |
| D174 konservativ | 8 | 2,46 mm | 24 | 23,16 s | 0 / 0 |
| D174 explorativ | 8 | 2,46 mm | 24 | 23,05 s | 0 / 0 |

Die einzige deutlich längere neue Linie im Einzelkartentest gehört zu
IC 3443. Sie verschiebt dessen Nummer in die Nähe von NGC 4478. Der bisherige
Score bevorzugt diese Variante stark, weil eine gültige Linie den Großteil der
Zuordnungskosten abzieht. Im Druckausschnitt ist der visuelle Gewinn nicht
klar; die neue Nähe zu 4478 ist ein möglicher Nachteil. Ein Scoregewinn ist
hier kein Beleg für besseres Lesen.

[IC 3443 bisher](../build/leader-experiment-2026-09-30/baseline-D174-I3443-crop.png) ·
[IC 3443 mit Linie](../build/leader-experiment-2026-09-30/conservative-D174-I3443-crop.png)

## Fertige Atlasseiten

| Hauptkarte | Bisher | Konservative Variante | Bewertung |
| --- | --- | --- | --- |
| S053 | 191 Labels, 35 über SD053A/B übertragene Nummern, 1 harter Befund | dieselben Zahlen | nur zwei kleine Änderungen; keine längere Linie |
| D174 | 179 Labels, 14 über DD174 übertragene Nummern, 0 harte Befunde | dieselben Zahlen | eine Änderung an NGC 4478; keine neue längere Linie |

IC 3443 ist auf der fertigen D174-Hauptkarte bereits ohne Nummer und auf DD174
beschriftet. Der interessante längere Linienfall aus der Einzelkarte wird
somit gar nicht gedruckt. Die neue Konfiguration verändert den Hauptkarten-
Layout-Hash, erzielt dort aber keinen klaren Lesbarkeitsgewinn.

[Ganzer Basisausschnitt S053](../build/leader-experiment-2026-09-30/atlas-baseline-S053.png) ·
[Ganzer Versuchsausschnitt S053](../build/leader-experiment-2026-09-30/atlas-trial-S053.png) ·
[Ganzer Basisausschnitt D174](../build/leader-experiment-2026-09-30/atlas-baseline-D174.png) ·
[Ganzer Versuchsausschnitt D174](../build/leader-experiment-2026-09-30/atlas-trial-D174.png)

[D174 mit NGC 4478 bisher](../build/leader-experiment-2026-09-30/atlas-baseline-D174-center-crop.png) ·
[D174 mit NGC 4478 im Versuch](../build/leader-experiment-2026-09-30/atlas-trial-D174-center-crop.png)

Die Gesamtkosten aus zwei verschiedenen Stilen sind nicht direkt vergleichbar,
weil das Linienlängen-Gewicht geändert wurde. Die vergleichbaren Geometrie-
und Befundzahlen sowie die Druckausschnitte tragen die Entscheidung.

## Entscheidung

Keine Erweiterung der aktiven Linienregel auf alle Karten. Die neue
Konfigurationsschwelle bleibt mit dem bisherigen Standardwert vorhanden, um
denselben Versuch reproduzierbar an weiteren Feldern zu wiederholen. Der
geprüfte Suchraum machte die beiden fertigen Hauptkarten nur geringfügig
anders und löste keine nachweisbare Zuordnungsschwäche.

Vor einer Änderung der Bewertungsgewichte braucht es vorab ausgewählte
Druckausschnitte mit klarer Frage: Welches Symbol gehört zu dieser Nummer?
Dabei sollten Karten mit korrekter Direktbeschriftung als Kontrollen enthalten
sein. Für echte Fernplatzierungen könnte später ein begrenzter gemeinsamer
Label-und-Linien-Suchschritt in einem lokalen Konfliktgebiet geprüft werden;
dieser Versuch liefert dafür noch keinen positiven Beleg.

## Blindbewertung des erweiterten Satzes (01.10.2026)

Die lokale Bewertungs-App unter `tools/label_review/` sammelte eine vollständige
Runde mit 23 Fällen aus fertigen Atlas-PDF-Seiten: 14 mit tatsächlicher Änderung
und 9 pixelgleichen Kontrollen. Es war ein Beobachter in einer Sitzung. Keine
Antwort wurde übersprungen; alle Antworten wurden ohne 50-mm-Anzeigekalibrierung
abgegeben. Fünf der geänderten Fälle erlauben wegen eng überlagerter Symbole
keine belastbare Klickwertung.

| Edition | Geänderte Fälle | Bisher bevorzugt | Versuch bevorzugt | Gleich | Beide schlecht |
| --- | ---: | ---: | ---: | ---: | ---: |
| Pocket | 4 | 1 | 3 | 0 | 0 |
| Standard | 4 | 1 | 2 | 0 | 1 |
| Deep | 6 | 4 | 1 | 1 | 0 |
| Insgesamt | 14 | 6 | 6 | 1 | 1 |

In den neun geänderten Fällen mit Klickwertung waren bei sieben beide Fassungen
richtig und bei zwei beide falsch. Es gab keinen Fall mit richtigem Klick nur
in einer Fassung. Bei den neun pixelgleichen Kontrollen wurde achtmal „gleich“
gewählt und einmal die bisherige Variante. Zwei Kontrollfälle hatten jeweils
einen richtigen und einen falschen Klick auf dasselbe Bildmotiv. Die
Klickgrenze von 1 mm erzeugt somit sichtbares Messrauschen. Der falsch
geklickte Fall P039/M7 betrifft außerdem ein ausgedehntes Sternhaufensymbol;
die Zielmitte ist hier als binäre Klickfrage wenig aussagekräftig.

Die konkreten Problemfälle sind D201/NGC 4266 (beide Klicks falsch; Notiz:
„kann es nicht richtig erkennen“) und S027/NGC 4618 (beide Fassungen schlecht;
Vorschlag des Beobachters: drei Führungslinien). Bei D174/NGC 4478 wurde die
bisherige Fassung trotz korrekter Zuordnung in beiden Bildern bevorzugt. Diese
Fälle eignen sich für gezielte Varianten mit explizit geprüften Linien und
Nachbarlabels. Der Versuch zeigt weder einen generellen Gewinn durch größere
Kandidatenabstände noch einen Grund, die bisherige Regel atlasweit zu ersetzen.
Weil Kandidatenabstand und Linienlängen-Gewicht gleichzeitig geändert wurden,
ist selbst eine lokale Präferenz keinem Einzelparameter zuzuordnen. Vor einer
erneuten Druckbeurteilung sollte die 50-mm-Anzeige kalibriert oder ein
tatsächlicher Ausdruck verwendet werden.

## Kalibrierte Folgerunde und Zuordnungsgewicht (06.10.2026)

Die sieben Fälle der Folgerunde wurden mit 50-mm-Anzeigekalibrierung bewertet.
In allen fünf auswertbaren Fällen waren beide Symbolklicks richtig. Bei den
fünf geänderten Ausschnitten wurde zweimal die bisherige Fassung und einmal
die Versuchsfassung bevorzugt; einmal waren sie gleich und einmal beide
schlecht. Zwei Änderungen blieben wegen überlagerter Symbole ohne Klickwertung.
Die beiden pixelgleichen Kontrollen wurden als gleich beurteilt. Die lokale
Auswertung liegt unter `build/label-review/followup-2026-10-06/analysis.md`.

Als nächste Hypothese wird ausschließlich das vorhandene Gewicht
`label.source_association.ambiguity_weight` von 20 auf 60 erhöht. Die Regel
bestraft konkurrierende Symbole nahe einer Beschriftung. Kandidatenabstände,
Führungslinienkosten und Produktionskonfiguration bleiben unverändert.
Gesamtkosten mit verschiedenen Gewichten sind kein Lesbarkeitsvergleich.

`tools/label_review/make_ownership_experiment.py` erzeugt passende Teilatlanten
mit eingefrorenen Konfigurationen und Ausschnitten aus den zusammengesetzten
PDFs. Der neue Satz umfasst neun Änderungen von neun verschiedenen Karten und
drei pixelgleiche Kontrollen, gleichmäßig über Pocket, Standard und Deep.
Alle zwölf Zielsymbole sind getrennt anklickbar. Die Auswahl verlangt identische
astronomische Symbolgeometrie und sichtbare Beschriftungen, keine neuen harten
Befunde auf der Quellkarte und keine harten Befunde im Ausschnitt. Sie verlangt
keine Verbesserung des Optimiererscores.

Zwei Pocket-Karten des Kandidatenpools wurden wegen neuer harter Befunde
verworfen. Der stärkere Wert ist deshalb bislang ausschließlich ein Versuch;
die ausgesuchten gültigen Ausschnitte dürfen diese Regressionen nicht verdecken.
Vier weitere Karten bleiben für eine spätere Gegenprobe reserviert.

Manifest, eingefrorene Konfigurationen, Auswahlbefunde und spätere Antworten
liegen unter `build/label-review/ownership-2026-10-06-v1/`. Die Bilder wurden
visuell geprüft; Bewertung und Auswertung stehen noch aus. Start- und
Erzeugungsbefehle sind in `tools/label_review/README.md` dokumentiert.

### Ergebnis der Einparameter-Runde (07.10.2026)

Ein Beobachter hat alle zwölf Fälle kalibriert bewertet (4,65 CSS-px/mm), ohne
Skips. Bei den neun tatsächlich veränderten Ausschnitten ergibt sich:

| Edition | Versuch (60) bevorzugt | Bisher (20) bevorzugt | Gleich |
| --- | ---: | ---: | ---: |
| Pocket | 3 | 0 | 0 |
| Standard | 2 | 1 | 0 |
| Deep | 1 | 1 | 1 |
| Gesamt | 6 | 2 | 1 |

Die Symbolzuordnung war in beiden Fassungen vollständig richtig (je 12/12,
davon neun geänderte Fälle). Es ist damit ein lokaler Präferenzgewinn, kein
nachgewiesener Gewinn der Zuordnungsgenauigkeit. Von den drei pixelgleichen
Kontrollen wurden zwei als gleich beurteilt und eine zugunsten des Versuchs
(S026/3067). Die einfache CLI-Summe von sieben Versuch-Präferenzen enthält
diese Kontrollpräferenz; nur sechs betreffen wirkliche Änderungen.

Alle neun Zielbeschriftungen verwenden in beiden Fassungen keine Führungslinie.
Die Runde beurteilt direkte Labelpositionen und erlaubt keine Aussage zur
gewünschten Führungslinienzahl. S089/1495 und D174/I3635 bevorzugen weiterhin die
bisherige Fassung; ein geringerer gewichtbereinigter Mehrdeutigkeitsanteil reicht
somit nicht als Lesbarkeitskriterium.

Produktionsgewicht 20 bleibt bestehen. Vor einer möglichen Übernahme von 60
sollen die neuen harten Konflikte auf P12/P25 untersucht und danach unbenutzte
Felder geprüft werden. Das Pocket-Signal ist mit drei Fällen ermutigend, aber
für eine editionsweite Entscheidung zu klein. Lokale Einzelbefunde und JSON:
`build/label-review/ownership-2026-10-06-v1/analysis.{md,json}`. Die Rohantworten
bleiben unverändert; in dieser Auswertung wurden keine Produktionsregeln geändert.

### Konfliktdiagnose und Gegenprobe an weiteren Feldern (07.10.2026)

Ein Forschungswerkzeug zeichnet die bestehenden Optimierungsschritte für P12
und P25 auf (`tools/label_review/diagnose_ownership_conflicts.py`). Die vier
finalen Layouts und Befundlisten entsprechen exakt dem ersten Versuch.
Problematische Labels haben statisch gültige Kandidaten, aber keinen freien
Kandidaten bei festgehaltenen Nachbarn. Die relevanten Komponenten mit 20 bzw.
79 Labels überschreiten das Limit der gemeinsamen Suche (acht Labels); die
anschließende Reparatur in kleinen Nachbarschaften löst die Blockade nur
teilweise. Knoten- und Suchzahlbudgets werden nicht ausgeschöpft. Die
gemeinsame Lösbarkeit ist nicht bewiesen; höhere Zeitbudgets allein sind
durch diesen Befund nicht begründet. Details:
`build/label-review/ownership-2026-10-07-diagnostics-v1/report.md`.

Die Gegenprobe umfasst S083, S094, D120, D260 und acht zusätzliche Pocket-Karten.
Bei S083/S094 und den acht Pocket-Karten entstehen keine neuen harten Befunde.
Beide Deep-Karten erzeugen dagegen neue Konflikte:

- D120: 17 → 16 Befunde, aber neue Überlagerungen I3957/NGC4854 und I3957/4854.
- D260: 0 → 1 Befund, Labelüberlagerung 4724/4727.

Diese Seiten werden nicht durch andere Deep-Karten ersetzt. Das Gewicht 60
bleibt eine Forschungsvariante; ein allgemeiner Wechsel ist angesichts der
Regressionen nicht gerechtfertigt. Der verbleibende Bewertungssatz umfasst
sechs Änderungen von sechs verschiedenen Karten (vier Pocket, zwei Standard)
und zwei pixelgleiche Kontrollen. Alle Ausschnitte und ihre Quellkarten sind
hard-clean; die Zielsymbole sind getrennt anklickbar. Manifest und vollständiger
Seitenaudit: `build/label-review/ownership-validation-2026-10-07/`.
Neue Antwortdatei, Seed 20261007 und Asset-Präfix `own2` erhalten frühere Runden
unverändert. Produktionscode, Styles und Suchregeln wurden nicht geändert.

Beim Abgleich sämtlicher früherer Manifeste zeigt sich eine Einschränkung der
Reservierung: S083/S094 waren bereits mit anderen Zielobjekten als Kontrollen
im älteren Führungslinienversuch enthalten; D120/D260 ebenfalls mit anderen
Zielen als Änderungen. Die sechs neuen Bewertungsausschnitte wurden dort nicht
beurteilt; Centaurus A war allerdings als Standard-Kontrollziel enthalten.
Alle vier zusätzlichen Pocket-Felder sind neu. Die reservierten
Karten sind jedoch keine vollständig ungesehenen Karten für diesen Beobachter.
Sie dürfen deshalb nicht als unabhängige Kartenstichprobe bezeichnet werden.

### Bewertung der acht Gegenprobenfälle (07.10.2026)

Alle acht Fälle wurden kalibriert bewertet, ohne Skips. Die sechs tatsächlichen
Änderungen ergeben vier Präferenzen für Gewicht 60 und zwei für Gewicht 20:
Pocket 2:2, Standard 2:0. Beide pixelgleichen Kontrollen wurden als gleich
beurteilt. Die Symbolzuordnung ist in beiden Fassungen vollständig richtig
(je 8/8). Die erste gemessene Falldauer enthält eine lange Unterbrechung und
wird nicht als reine Bearbeitungszeit interpretiert.

Zusammen mit der vorherigen Einparameter-Runde: 15 Änderungen, zehnmal Versuch,
viermal bisher, einmal gleich. Das ist eine beschreibende Zusammenfassung eines
Beobachters auf ausgewählten gültigen Ausschnitten. Wegen der bekannten neuen
harten Konflikte bleibt Produktionsgewicht 20 bestehen.

Bei ESO274-001 (S094) und Centaurus A (P37) wünscht der Beobachter ausdrücklich
eine Führungslinie für die lange Beschriftung. Beide Zuordnungen waren bereits
richtig; alle sechs Zielbeschriftungen sind in beiden Fassungen ohne Linie.
Ein separater Versuch sollte kurze gültige Linien bei konkreter
Zuordnungsmehrdeutigkeit prüfen, ohne gleichzeitig das Zuordnungsgewicht zu
ändern. Labelbreite allein ist noch kein ausreichendes Linienkriterium.
Lokale Auswertung: `build/label-review/ownership-validation-2026-10-07/analysis.{md,json}`.

## Isolierter Linienversuch für lange Beschriftungen (07.10.2026)

`build/label-review/long-label-lines-2026-10-07/` enthält vier neue Fälle:
P37/Centaurus A und S094/ESO274-001 mit jeweils einer zusätzlichen kurzen
Führungslinie sowie zwei pixelgleiche Kontrollen aus denselben Seiten. Seed
`20261009`; die 50-mm-Anzeigekalibrierung ist verpflichtend.

Die Vergleichsseiten verwenden unverändert Gewicht 20. Gegenüber der Baseline
werden ausschließlich `leader_line` und `leader_line_reason` des jeweiligen
Labels geändert; Position, Kandidat, Text, sichtbare Labels und astronomischer
Inhalt bleiben identisch. Die Baseline reproduziert die gespeicherten Layouts
der vorigen Runde exakt. Die Linien sind 1,394 mm und 1,545 mm lang. Alle vier
Quellseiten haben null harte Layoutbefunde; bestehende Linienrouten bleiben
unverändert. Ausschnitte aus den zusammengesetzten Atlas-PDFs wurden visuell
geprüft. Produktionscode und Produktionskonfiguration bleiben unverändert.

Der Forschungs-Generator `tools/label_review/make_long_label_line_experiment.py`
ergänzt den Präsentationszustand nach der Optimierung im eigenen Prozess.
Optimiererkosten beschreiben die ursprüngliche Platzierung; es gibt keinen
Score-Filter. Layoutvergleich, Liniengeometrie und Bildprüfsummen sind lokal
dokumentiert. Beide Ziele wurden bereits betrachtet. Dieser kleine Versuch
prüft die konkreten Hinweise des Beobachters und liefert allein keinen Beleg
für eine allgemeine Linienregel anhand der Textlänge.

### Bewertung des isolierten Linienversuchs (07.10.2026)

Alle vier Fälle wurden kalibriert bewertet, ohne Skips. Bei Centaurus A und
ESO274-001 wurde jeweils die Fassung mit kurzer Linie bevorzugt; beide
pixelgleichen Kontrollen wurden als gleich beurteilt. Alle acht Klicks waren
korrekt (je 4/4 pro Variante). Da ausschließlich die Linie geändert wurde,
spricht die Präferenz in diesen beiden Fällen für die Linie. Eine höhere
Zuordnungsgenauigkeit ist nicht nachgewiesen; beide Fassungen waren bereits
korrekt. Ein Beobachter und zwei bekannte Ziele begründen keine allgemeine
Textlängen-Schwelle.

Die Kontrollnotizen weisen auf einen zweiten, getrennten Aspekt hin: Bei
ESO221-026 kann das Galaxiensymbol wie ein vorangestelltes O wirken; bei IC1023
wird mehr Symbolabstand gewünscht. Das sind Hinweise auf den wahrgenommenen
Glyphen-/Symbolabstand, keine Begründung für global größere Abstände.

Nächster Forschungsschritt: eine begrenzte deterministische Linienregel für
lange, mehrdeutig zuordenbare Beschriftungen formulieren und an weiteren
vorab ausgewählten Fällen prüfen. Gültige kurze Route und unveränderte
Labelposition sind zunächst die Voraussetzung. Gewicht 20 bleibt bestehen;
die früheren Regressionen bei Gewicht 60 werden durch diese Runde nicht
aufgehoben. Produktionsregeln bleiben unverändert. Lokale Auswertung:
`build/label-review/long-label-lines-2026-10-07/analysis.{md,json}`.

## Deterministische gezielte Linienregel als Forschungsvariante (07.10.2026)

`tools/label_review/make_targeted_line_experiment.py` prüft ausschließlich
vorhandene Positionen sichtbarer, nicht gesperrter DSO-Beschriftungen ohne
bestehende Linie. Die sichtbare Schriftbreite muss mindestens 8 mm betragen,
das Breite/Höhe-Verhältnis mindestens 4. Zusätzlich muss eines der vorhandenen
Mehrdeutigkeitssignale vorliegen: `competing_owner_cost >= 1`,
`association_corridor_cost > 0` oder `ownership_margin_weak`.

Die vorhandene Linienführung muss eine gültige Route von höchstens 3 mm
liefern. Bestehende Linienrouten bleiben erhalten; neue harte Befund-IDs
verwerfen den Vorschlag. Reihenfolge: Priorität absteigend, stabile Label-ID
aufsteigend. Diese Zahlen sind vor dem Versuch festgelegte Hypothesen, keine
empirisch optimierten Produktionsschwellen. Zuordnungsgewicht bleibt 20.
Kein Label wird verschoben, kein Text oder astronomischer Inhalt verändert.

Der erste Pool umfasst Orion, Cygnus, Carina und Sagittarius in allen drei
Editionen. Wegen zu weniger isolierter Änderungsziele wurden S081 und D314
ergänzt, ohne die Regel zu ändern. Damit wurden 14 Hauptkartenpaare geprüft.
Es entstehen drei zusätzliche Linien (Pocket: M27 und M6; Standard:
ESO507-025; Deep: keine). Null neue harte Befunde, fünf unveränderte bestehende
Befunde. Detailkarten bleiben unverändert. Diese adaptive Felderweiterung ist
keine vollständig vorab festgelegte Validierungsstichprobe.

Der eingefrorene Satz unter `build/label-review/targeted-lines-2026-10-07/`
enthält fünf Fälle: zwei Änderungen und drei pixelgleiche Kontrollen. Beide
Änderungen liefern nur Präferenzdaten: M27 hat ein großes Symbol,
ESO507-025 einen nahen Stern. Die Klickwertung ist dort ausgesetzt. Die
Kontrollen haben normale Klickwertung. Alle aufgenommenen Ausschnitte sind
ohne harte Befunde und wurden visuell geprüft. Ziele aus früheren Manifesten
werden ausgeschlossen; manche Quellkarten waren bereits bekannt.

Seed `20261010`, Asset-Präfix `target1`, separate Antwortdatei. Produktionscode
und Produktionskonfiguration bleiben unverändert. Regelentscheidungen,
vollständiger Seitenvergleich und Einschränkungen stehen im lokalen
`report.md`, `rule-audit.json`, `decisions/` und `curation.json`.

### Bewertung der gezielten Regel (07.10.2026)

Alle fünf Fälle wurden kalibriert bewertet, ohne Skips. Beide bewerteten
automatisch erzeugten Linien (M27 und ESO507-025) wurden bevorzugt; die drei
pixelgleichen Kontrollen wurden als gleich beurteilt. Die Kontrollklicks sind
je 3/3 pro Variante korrekt. Bei beiden Änderungen war die Klickwertung
ausgesetzt; ein Genauigkeitsgewinn ist daher nicht belegt. M6 erhielt eine
Linie, war jedoch kein Bewertungsfall. In Deep entstanden keine zusätzlichen
Linien; positive Deep-Linienwirkung wurde damit nicht geprüft.

Zusammen mit dem vorherigen gezielten Vergleich wurden vier Linien an vier
Objekten bevorzugt. Es bleibt ein Beobachter; nur zwei dieser Beispiele wurden
von der allgemeinen Forschungsregel auf neuen Zielen erzeugt. Die Ergebnisse
sind qualitativ konsistent, bestimmen jedoch keine optimalen Schwellenwerte.

Empfohlener nächster Schritt ist eine vorsichtige, konfigurierbare Integration
mit atlasweiter Prüfung und visueller Übersicht aller neuen Linien. Gewicht
20, unveränderte Positionen, gültige kurze Routen und Erhalt bestehender
Linien bleiben Voraussetzungen. Keine weitere Produktionsänderung wurde
durch diese Auswertung vorgenommen. Lokal:
`build/label-review/targeted-lines-2026-10-07/analysis.{md,json}`.

### Konfigurierbare Integration und vollständige Kartenprüfung (07.10.2026)

Nach Zustimmung des Beobachters ist die Forschungsregel als abschließender
Präsentationsschritt in `layout/targeted_leaders.py` integriert. Die oben
beschriebenen Schwellen bleiben unverändert. `label.leader_lines.targeted_dso`
aktiviert sie in Standard und den davon abgeleiteten Pocket-/Deep-Stilen,
einschließlich ihrer Detailkarten. Eyepiece bleibt ausdrücklich deaktiviert.
Ohne Konfigurationsblock ist die Regel aus. Zuordnungsgewicht bleibt 20.

Die Entscheidung wird mit stabiler Label-ID und Ablehnungsgrund in den
Optimierermetriken gespeichert; akzeptierte Linien erhalten den Grund
`targeted_long_label`. Die abschließenden Labeldiagnosen werden aktualisiert.
Die Regel verschiebt keine Beschriftungen, verändert keine Inhalte und
optimiert keine bestehenden Linien um.

`tools/label_review/audit_targeted_leaders.py` prüft den Zustand unmittelbar
vor und nach diesem Schritt im regulären Atlas-Build. Jede Änderung außerhalb
der beiden Linienattribute sowie jede neue harte Befund-ID bricht die Prüfung
ab. Alle Haupt- und Detailkarten müssen einen Auditdatensatz besitzen. Die
Prüfung verwendet vier Prozesse je Edition und benötigt keine KI-Abfragen.

```bash
.venv/bin/python tools/label_review/audit_targeted_leaders.py build --edition pocket --jobs 4
.venv/bin/python tools/label_review/audit_targeted_leaders.py build --edition standard --jobs 4
.venv/bin/python tools/label_review/audit_targeted_leaders.py build --edition deep --jobs 4
.venv/bin/python tools/label_review/audit_targeted_leaders.py summarize
```

Die lokalen Ergebnisse liegen unter `build/targeted-leaders-2026-10-07/`.
`implementation.json` hält Quell- und Konfigurationsprüfsummen fest;
`audit-summary.json` enthält die aggregierten Ergebnisse. `new-lines.pdf`
zeigt jede neue Linie bei nomineller Druckgröße links ohne und rechts mit
Linie; `new-lines.html` bietet dieselben Ausschnitte zum Vergrößern.
Vergleichsrenderings verwenden die tatsächlichen optimierten Szenen und
Positionen sowie die Navigation und Symbolüberlagerungen der regulären
Atlas-Seitenrenderung. Die vollständigen Prüf-Atlas-PDFs
enthalten reguläre Karten und Index, jedoch weder Einleitung noch Übersichten.
Sie sind keine neuen Publikationsausgaben.

Ergebnis der vollständigen Prüfung:

| Edition | Hauptkarten | Detailkarten | Neue Linien | Geänderte Karten | Bestehende harte Befunde | Neue harte Befunde |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Pocket | 48 | 1 | 5 | 4 | 27 | 0 |
| Standard | 118 | 9 | 2 | 2 | 40 | 0 |
| Deep | 430 | 9 | 2 | 2 | 119 | 0 |

Keine Detailkarte erhält eine zusätzliche Linie. Pocket betrifft M57 auf
P16, M27 auf P17, Centaurus A und Omega Centauri auf P37 sowie M6 auf P39.
Standard betrifft ESO507-025 auf S081 und ESO274-001 auf S094. Deep betrifft
die gemeinsame Beschriftung des Doppelsternhaufens auf D031 und IC3322A auf
D202. Die Linien sind 1,236–2,315 mm lang. D202 hat einen unveränderten
Labelkonflikt zwischen NGC4342 und NGC4343 außerhalb des Vergleichsziels;
die anderen sieben geänderten Karten haben keine harten Befunde.

Für die endgültigen Vergleiche wurden nur die acht geänderten Karten nochmals
mit vollständigem Atlas-Renderkontext erzeugt. Vorher-/Nachher-Layout-Hashes
und Entscheidungen stimmen mit dem vollständigen Lauf überein; die
Nachher-Raster stimmen pixelgenau mit dessen Einzelkarten-PDFs überein.
`proof-verification.json` dokumentiert diese Prüfung. Produktionsquellen und
Stil-/Atlaskonfigurationen bleiben während der Läufe unverändert.

Die vollständige Kartenprüfung belegt die geometrische Begrenzung der Regel,
keinen atlasweiten Wahrnehmungsgewinn. M57, Omega Centauri, M6 und die beiden
Deep-Ergänzungen sind noch nicht durch den Beobachter blind bewertet.
Bestehende Layoutbefunde werden durch diese Änderung nicht behoben.
`make lint` besteht; in diesem Integrationslauf wurden keine Unit-Tests ergänzt
oder ausgeführt.
