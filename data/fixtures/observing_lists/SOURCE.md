# Observing-list fixtures

Curated visual observing lists used as DSO selection metadata.  Membership is
atlas metadata, not an astronomical fact: fixtures here are never merged into
the normalized catalogue and never modify `DeepSkyObject` fields.

Designations are normalized at load time (whitespace removed, NGC/IC leading
zeros stripped, Messier numbers canonicalized), so a fixture may list
`NGC 869`, `NGC869` or `M 42` interchangeably.

## herschel400.json

- **List:** Herschel 400 (400 catalogue entries)
- **Source:** Wikipedia, *Herschel 400 Catalogue*, revision 1369720351
  (<https://en.wikipedia.org/wiki/Herschel_400_Catalogue>)
- **License:** CC BY-SA 4.0 (Wikipedia text)
- **Retrieved:** 2026-09-16
- **Contents:** 402 normalized NGC designations.  Three Herschel rows carry a
  double NGC number and were expanded to one entry per designation
  (NGC 650/651, NGC 2371/2372, NGC 4038/4039), giving 402 entries for 400
  catalogue rows.
- **Known gaps:** nine designations have no matching OpenNGC object and
  therefore cannot be forced into a chart: NGC651, NGC2244, NGC2372, NGC2527,
  NGC3190, NGC3912, NGC4665, NGC6885, NGC7296.  NGC651 and NGC2372 are
  alternate numbers of objects already covered (NGC650 and NGC2371).
