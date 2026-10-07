# Planetarische und Dunkelnebel: eigenständige Editionsauswahl

Stand: 2026-10-02. **Die PN-Mindestliste ist in Deep als Editionsregel aktiv;
die Dunkelnebel-Liste bleibt ein redaktioneller Vorschlag.**
Die vollständige, maschinenlesbare Liste steht in
[`PN_DARK_CURATION.csv`](PN_DARK_CURATION.csv). Die lokale NSOG-/AstroPlanner-Liste,
ihre Bewertungen und ihre Coverage-Berichte wurden für diese Auswahl **nicht**
verwendet. Auch keine der unten genannten Beobachtungslisten wurde vollständig
übernommen. Die CSV enthält nur unsere Zielentscheidung, Identifikatoren und
Quellverweise, keine fremden Beschreibungen, Koordinatentabellen oder Ratings.

## Was die drei Stufen bedeuten

`first_edition` ist die kleinste Edition, in der das **physische Ziel** nach
redaktioneller Prüfung erscheinen soll. Alle tieferen Editionen erben es:
Pocket ⊂ Standard ⊂ Deep. Die PN sind jetzt in der Auswahl vollständig;
Symbolgröße und Beschriftung auf fertigen Karten sind gesondert zu prüfen.

| Zieltyp | Pocket | Standard zusätzlich | Deep zusätzlich | Deep gesamt |
| --- | ---: | ---: | ---: | ---: |
| Planetarische Nebel | 18 | 35 | 51 | **104** |
| Dunkelnebel/-regionen | 5 | 12 | 16 | **33** |

Pocket erhält die besonders hilfreichen, weithin beobachteten PN und nur große,
gut identifizierbare Dunkelgebiete. Standard ergänzt starke Teleskopziele und
einzelne deutliche Dunkelwolken. Deep soll auch kleinere PN für ernsthafte
visuelle Beobachtung mit etwa 400 mm Öffnung und ausgewählte schwierige
Dunkelnebel auffindbar machen. Helligkeit allein entscheidet nicht: ein heller,
aber sternförmiger PN kann einen guten Finderpunkt brauchen; ein großer
Dunkelnebel braucht dagegen eine glaubhafte Form oder zumindest eine klar als
Position gekennzeichnete Beschriftung. Ein Eintrag in einer externen Liste
erzwingt keine Aufnahme.

Die [Astronomical League PN-Seite](https://www.astroleague.org/planetary-nebula-observing-program/)
weist selbst darauf hin, dass ihre ursprüngliche Liste nur bis −40°26′ reicht.
Darum wurden ihre [Südliste](https://www.astroleague.org/wp-content/uploads/2022/02/The-Southern-Planetary-Nebula-Program.pdf)
und die südliche [ASSA Top 100](https://assa.saao.ac.za/sections/deep-sky/assa-top-100/)
separat berücksichtigt. Von den 104 vorgeschlagenen PN liegen nach den
momentanen NightSkyAtlas-Positionen 23 südlich von −40°; der noch fehlende
südliche Shapley 1 kommt dazu. Das ist eine bewusste Korrektur gegen eine
rein nördliche Auswahl, keine Quote.

## Quellenschlüssel der CSV

`source_evidence` bezeichnet **Beobachtungsevidenz oder Identitätshinweise**,
keine Redistributionslizenz und keine automatische Selektionsregel.

| Kürzel | Quelle |
| --- | --- |
| AL-PN | [Astronomical League, PN-Programm](https://www.astroleague.org/wp-content/uploads/2022/02/Planetary-Nebula-List.pdf) |
| AL-SOUTH | [Astronomical League, südliches PN-Programm](https://www.astroleague.org/wp-content/uploads/2022/02/The-Southern-Planetary-Nebula-Program.pdf) |
| AL-ALT | [Astronomical League, nördliche PN-Alternativen](https://www.astroleague.org/files/u3/list%20of%20alt%20PN.pdf) |
| RASC-FNGC | [RASC Finest NGC](https://www.rasc.ca/sites/default/files/RASC_FNGC_checklist_1.pdf) |
| RASC-DSC | [RASC Deep-Sky Challenge](https://rasc.ca/sites/default/files/Deep-Sky_Challenge_Final_220227_0.pdf) |
| RASC-JOURNAL | [RASC Journal: PN in Lyra, einschließlich Minkowski 1-64](https://rasc.ca/sites/default/files/publications/JRASC-2002-08.pdf) |
| RASC-HAL | [RASC Halifax: Abell 70](https://mail.halifax.rasc.ca/images/documents/novanotes/nn3205.pdf) |
| RASC-SKY | [RASC: NGC 7139](https://rasc.ca/news/sky-month-september-2011) |
| RASC-CALGARY | [RASC Calgary: B 86](https://calgary.rasc.ca/constellations/sagittarius.htm) |
| ASSA-100 | [ASSA Top 100](https://assa.saao.ac.za/sections/deep-sky/assa-top-100/) |
| ASSA-BIG5 | [ASSA Big 5: Coalsack](https://assa.saao.ac.za/sections/deep-sky/big5/) |
| ASSA-DARK | [ASSA: Seeing the Dark / Musca](https://assa.saao.ac.za/wp-content/uploads/sites/23/2021/07/Special-Report-4-Seeing-the-Dark.pdf) |
| ASSA-NF | [ASSA Nightfall: Abell 39](https://assa.saao.ac.za/wp-content/uploads/sites/23/2017/11/NF_v2n1_Supplement_Catalogues_resources.pdf) |
| ESA | [ESA: Musca-Filament / Dark Doodad](https://www.esa.int/ESA_Multimedia/Images/2020/06/The_Musca_molecular_clouds_viewed_by_Herschel_and_Planck) |
| AL-DN | [Astronomical League, erforderliche Dunkelnebel](https://www.astroleague.org/files/obsclubs/DarkNebula/DN-RequiredObjects.pdf) |
| AL-DN-OPT | [Astronomical League, zusätzliche Dunkelnebel](https://www.astroleague.org/files/obsclubs/DarkNebula/DN-Optional.pdf) |
| SAC | [Saguaro Astronomy Club: ausgewählte Barnard-Nebel](https://www.saguaroastro.org/the-best-of-barnards-dark-nebulae/) |

## Identität und Kartendarstellung

- `atlas_ids` nennt **stabile lokale Objekt-IDs**. Alle 104 PN haben jetzt eine
  passende ID im normalisierten Katalog. Jones 1, J 900, Minkowski 1-64 und
  Shapley 1 kommen gezielt aus `IV/24:CuratedPN`; die anderen 100 waren schon
  vorhanden. Die Importquelle speichert historische Koordinaten und die von
  VizieR berechnete ICRS-Position getrennt und lässt Magnitude/Größe leer.
- Die fünf Dunkelziele ohne passende lokale ID sind Dark Doodad/Black Python,
  die R-CrA-Wolke, B 5 sowie SL 7 und SL 11. Die weiteren 28 Zielzeilen
  referenzieren vorhandene lokale Dunkelnebel-IDs oder, bei Regionen, mehrere
  Komponenten. Eine Region ist **nicht** die Summe der Katalogflächen ihrer
  Komponenten.
- **M 76** ist ein PN; `NGC 650` und `NGC 651` bezeichnen Teile desselben
  Ziels. **NGC 2371/2372** ist ebenfalls ein physisches PN-Ziel. Nicht zwei
  Symbole nur wegen zweier NGC-Nummern erzeugen.
- **NGC 2818** erfordert beim Alias-Abgleich besondere Sorgfalt: PN und
  Sternhaufen liegen im selben Feld, und die Bezeichnung wird für beide
  verwendet. Die CSV meint ausdrücklich den PN-Datensatz `NGC2818`.
- **Pipe** und **Barnard's E** sind Beobachtungsregionen mit Komponenten.
  Der Dark Doodad ist das lange Musca-Filament. Die ASSA Top 100 nennt einen
  Abschnitt „Black Python“, während andere ASSA-Materialien beide Namen
  koppeln. Vor einer einzelnen Atlas-ID sind Abschnitt und Gesamtregion
  sauber zu trennen. LDN-Einträge, die Barnard-Ziele überlappen, sind Aliase
  oder Teilgebiete, keine automatisch zusätzlichen Ziele.
- `region_contour` und `filament_contour` sind redaktionelle Anforderungen.
  Ohne verlässliche Form soll ein großer Dunkelnebel **nicht** als beliebige
  Katalogellipse oder Quadrat ausgegeben werden. Bei kompakten Zielen ist
  `small_locator` eine bewusst positionsbezogene Darstellung; die
  Katalogausdehnung wird dadurch nicht als Silhouette behauptet. Besonders
  Pocket braucht für Coalsack, Pipe und Musca eine ruhige, lesbare Regionform.
- **Abell 12/21/39/70/74** stehen als gezielte Deep-Herausforderungen in der
  Liste. Ihre lokalen Einträge haben derzeit keine ausreichende Photometrie
  oder Größe für eine automatische Sichtbarkeitsentscheidung. Sie werden nun
  durch die belegte PN-Kuration ausgewählt; Symbolgröße und Lesbarkeit sind
  vor der nächsten Veröffentlichung einzeln zu prüfen.
  [Abell 70](https://noirlab.edu/public/images/noao-abell70durkin/) überlagert
  am Rand eine Hintergrundgalaxie; beides sind getrennte physische Objekte.
- **Minkowski 1-64** gehört als bewusst ausgewählte Deep-Ausnahme dazu.
  Die [SIMBAD-Identität](https://simbad.u-strasbg.fr/simbad/sim-id?Ident=PN+G064.9%2B15.5&protocol=html)
  ist PN G064.9+15.5 / PK 064+15.1. Die stabile ID
  `Minkowski 1-64` stammt nun aus dem gezielten IV/24-Import.

## PN ohne belastbare Nebelhelligkeit: Editionsregel

**Astronomische Messwerte und redaktionelle Auswahl getrennt halten.** Ein
fehlender Magnitudenwert bleibt `null`. Weder die Helligkeit des Zentralsterns
noch Hβ-Fluss oder fotografische Schätzungen dürfen stillschweigend als visuelle
Gesamthelligkeit des Nebels in das vorhandene Magnitudenfeld gelangen. Der
[Strasbourg-ESO-Katalog bei HEASARC](https://heasarc.gsfc.nasa.gov/W3Browse/catalog/plnebulae.html)
führt optische Durchmesser mit Qualitäts-/Grenzwertkennzeichen, Hβ-Fluss und
**separat** Zentralstern-Photometrie; er ist deshalb eine mögliche Quelle für
Identität und Größe, aber nicht automatisch für eine visuelle PN-Helligkeit.

Die 104 unabhängig kuratierten PN-Ziele stehen als NightSkyAtlas-eigene
Mitgliedschaft in `nightsky_curated_pn.json`. Deep nimmt sie über
`curated_memberships` zusätzlich zur normalen PN-Auswahl auf; Reference erbt
diese Regel. Der Selektionsgrund `curated_membership_policy` bleibt von
photometrischen Sichtbarkeitsentscheidungen unterscheidbar. Diese Regel ändert
weder das Sichtbarkeitsmodell noch die Messwerte und übernimmt keine
vollständige fremde Beobachtungsliste. Die vorhandene Regel
`curated_designations` wäre ungeeignet, weil sie für einen Objekttyp die
normale Auswahl ersetzen würde.
Ein kleiner Deep-Listenbonus von 10 hebt PN ohne Magnitude von der niedrigen
in die mittlere Label-Priorität; er macht ihr Label nicht obligatorisch.

| Ziel | Evidenz und Darstellungsprüfung für Deep |
| --- | --- |
| Abell 12 | [RASC Deep-Sky Challenge](https://rasc.ca/sites/default/files/Deep-Sky_Challenge_Final_220227_0.pdf): etwa 37″; OIII-Beobachtung dicht an μ Orionis. Position und kleines PN-Symbol prüfen. |
| Abell 21 / Medusa | [Astronomical League](https://www.astroleague.org/wp-content/uploads/2022/02/Planetary-Nebula-List.pdf) und [RASC](https://rasc.ca/sites/default/files/Deep-Sky_Challenge_Final_220227_0.pdf): groß und sehr flächenlichtschwach. Die beiden Listen nennen unterschiedliche integrierte Magnituden (11,3 bzw. ungefähr 13); einen Wert nicht ungeprüft als präzise Photometrie übernehmen. |
| Abell 39 | [ASSA Nightfall](https://assa.saao.ac.za/wp-content/uploads/sites/23/2017/11/NF_v2n1_Supplement_Catalogues_resources.pdf): rund 2′; die schwache Scheibe ist ein gezieltes visuelles PN-Ziel. |
| Abell 70 | [RASC Halifax](https://mail.halifax.rasc.ca/images/documents/novanotes/nn3205.pdf) und [NOIRLab](https://noirlab.edu/public/images/noao-abell70durkin/): beobachteter PN; die überlagerte Hintergrundgalaxie bleibt ein eigenes Objekt. Symbol und Beschriftung auf Verwechslung prüfen. |
| Abell 74 | [Astronomical League, nördliche Alternativen](https://www.astroleague.org/files/u3/list%20of%20alt%20PN.pdf) und [Reiner Vogels eigene Beobachtungen](https://www.reinervogel.net/Abell_PN/Abell_PN_e.html): sehr großes, extrem schwaches Feldziel. Die dort genannte Magnitude 12,2 ist keine hinreichende Sichtbarkeitsaussage; Feldgröße und Filterhinweis sind wichtiger. |
| Minkowski 1-64 | [SIMBAD](https://simbad.u-strasbg.fr/simbad/sim-id?Ident=PN+G064.9%2B15.5&protocol=html): PN G064.9+15.5 / PK 064+15.1. [Eigenbeobachtung und Skizzenbericht](https://www.astronomy.com/observing/sketch-minkowskis-nebulae/) nennen etwa 17″ und 13. Größe; dies ist Evidenz für ein kompaktes Deep-Ziel, zunächst kein Katalog-Magnitudenimport. |

### Abell-PN in Deep

Deep nimmt jetzt alle als PN bestätigten Abell-Ziele auf, unabhängig davon, ob
Magnitude oder Durchmesser im normalisierten Katalog vorhanden sind. Die
explizite Membership-Liste `nightsky_confirmed_abell_pn.json` enthält 72
physische Ziele: Abell-Einträge ohne `f_PK`-Kennzeichnung in Kohouteks
`IV/24`-Tabelle sowie Abell 21 als unabhängig bestätigte Ausnahme. Bereits unter
NGC geführte physische Objekte bleiben über ihre kanonische ID dedupliziert.

Mit `f_PK=*` markierte mögliche PN werden nicht automatisch aufgenommen;
Fehlidentifikationen werden nicht als planetarische Nebel geplottet. Abell 21
ist ausdrücklich enthalten, weil unabhängige Beobachtungsquellen es als
visuelles PN-Ziel bestätigen. Diese Auswahl ändert weder astronomische
Messwerte noch Pocket-/Standard-Regeln. Kleine PN erhalten den üblichen
Positionsmarker, solange kein belastbarer Durchmesser verfügbar ist.

### Gegenprüfung: In-The-Sky.org und Abell 1966

Der [Abell-Katalog auf In-The-Sky.org](https://in-the-sky.org/data/catalogue.php?cat=Abell&const=1&type=&sort=0&view=1)
ist ein nützlicher Finder für Namen und Größen. Einzelne Objektseiten geben
auch angebliche `V`-Magnituden mit Verweis auf
[Abell (1966), *Properties of Some Old Planetary Nebulae*](https://adsabs.harvard.edu/pdf/1966ApJ...144..259A)
an. Die Originalarbeit beschreibt jedoch **integrierte Nebelhelligkeiten**
aus fotografischen blauen (`m_pg`, etwa 405 nm) und roten (`m_pr`, etwa 644 nm)
Palomar-Platten. Sie führt Johnson-`V` nur **für Zentralsterne** auf. Daher
sind die Website-`V`-Werte ohne dokumentierte Umrechnung oder weitere Quelle
keine direkt übernehmbaren V-Messungen des Nebels.

| PN | In-The-Sky-Angabe | Abell 1966, integrierter Nebel (`m_pg` / `m_pr`) |
| --- | --- | --- |
| Abell 12 | Objektseite zurzeit nicht zuverlässig abrufbar | 13,9 / höchstens 11,7 |
| [Abell 21](https://in-the-sky.org/data/object.php?id=Abell_21) | „V“ 10,2; 12,4′ × 8,5′ | 11,2–11,4 / 7,7 |
| [Abell 39](https://in-the-sky.org/data/object.php?amp=1&id=Abell_39) | „V“ 12,9; 2,9′ | 13,7 / 12,1 |
| Abell 70 | Objektseite zurzeit nicht zuverlässig abrufbar | 14,3 / 12,7 |
| [Abell 74](https://in-the-sky.org/data/object.php?id=Abell_74) | „V“ 15,8; 13,8′ | schwächer als 12,2 / 10,0 |

Die starke Blau/Rot-Differenz bei Abell 21 und 74 zeigt, warum ein einzelner
„visueller“ Wert für diese Emissionsnebel irreführend sein kann. Auch die
12,2-mag-Angabe für Abell 74 in der AL-Alternativliste ist im Original nur
eine **Grenze** im fotografischen Blau, keine gemessene V-Magnitude. Größen
können nach Identitäts- und Qualitätsprüfung aus der Originalarbeit oder dem
[HEASARC/Strasbourg-ESO-Katalog](https://heasarc.gsfc.nasa.gov/W3Browse/catalog/plnebulae.html)
übernommen werden. Für die Deep-Auswahl bleibt die belegte Einzelfallregel
vorzuziehen. Minkowski 1-64 gehört nicht zum Abell-Katalog und wird durch
diese Website nicht ergänzt.

## Nächster redaktioneller Schritt

Die Zielzeilen mit `size_review`, `visibility_and_size_review` oder
`region_contour` zuerst auf den fertigen Karten prüfen. Die PN-Auswahl deckt
die Soll-Liste jetzt vollständig ab; eine bestätigte Symbolgröße für große PN
ist damit noch nicht erreicht.
Die PN-Liste ist eine **kuratierte Mindestabdeckung** für die drei Editionen,
kein Verbot weiterer, nach der normalen Sichtbarkeitsregel sinnvoller PN.
Für Dunkelnebel ist sie eine Ziel- und Identitätsliste; die endgültige
Kartendarstellung bleibt an die Formqualität gebunden.

## Gegenprobe mit der momentanen Auswahl

Snapshot mit `data/processed/dso/catalogue.json`, der gegenwärtigen
`config/observing_lists.yaml` und dem **gleichen Selektor wie der Atlas-Build**.
Eine Region gilt hier erst als ausgewählt, wenn alle in der CSV genannten
Komponenten ausgewählt sind. „Ausgewählt“ sagt noch nichts über eine lesbare
Kontur, platzierte Beschriftung oder eine fertige Karte aus.

| Edition/Zieltyp | Soll-Ziele | IDs ausgewählt | IDs vorhanden, nicht ausgewählt | Ohne passende ID |
| --- | ---: | ---: | ---: | ---: |
| Pocket PN | 18 | 18 | 0 | 0 |
| Standard PN | 53 | 53 | 0 | 0 |
| Deep PN | 104 | 104 | 0 | 0 |
| Pocket dunkel | 5 | 1 | 3 | 1 |
| Standard dunkel | 17 | 1 | 14 | 2 |
| Deep dunkel | 33 | 13 | 15 | 5 |

Bei Dunkelnebeln ist die Lücke weiterhin wesentlich größer. Auffällig ist
**Coalsack**: Pocket und Deep
wählen `C099`, Standard derzeit nicht. Diese Gegenprobe ist ein Befund für
eine spätere Editionsentscheidung, keine Änderung der heutigen Regeln.
