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
