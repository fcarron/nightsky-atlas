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
