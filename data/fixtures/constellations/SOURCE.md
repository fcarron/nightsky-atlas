# Constellation geometry sources

The two fixture files have distinct provenance and licenses.

## Western (Sky & Telescope) stick figures

- **File:** `constellations.lines.json`
- **Source:** Stellarium Sky Cultures, `western_SnT/index.json`, commit
  `014fbb5e59233d133c22f9811af96b67d05a95c9`.
- **Upstream:** https://github.com/Stellarium/stellarium-skycultures/tree/014fbb5e59233d133c22f9811af96b67d05a95c9/western_SnT
- **Source SHA-256:** `7c61c6f88f50b84e43e276c3f9f67422faec63f4a13ca8e60c22bfc3da064340`.
- **Attribution:** Paul Krizak and Jonathan E. Piskor; rework by the Stellarium Team.
- **License:** [CC BY-SA 2.0](https://creativecommons.org/licenses/by-sa/2.0/).
- **Transformation:** HIP polylines and bold/normal/thin classes are retained;
  consecutive duplicate IDs (zero-length steps) removed. HIP coordinates come
  from NightSky's Tycho-2/Hipparcos catalog, not Stellarium.
- **Rebuild:** `nightsky data fetch-stellarium-figures` then
  `nightsky data import-stellarium-figures`.

## IAU constellation boundaries

- **File:** `constellations.bounds.json`
- **Source:** [d3-celestial](https://github.com/ofrohn/d3-celestial) by Olaf
  Frohn, `master`, fetched 2026-09-16.
- **License:** BSD-3-Clause; see the adjacent `LICENSE` file.
- **Transformation:** none on import. Boundary polygons are converted to a
  deduplicated segment set at load time.

These committed fixtures make an offline build reproducible. The stick-figure
data is not MIT-licensed; see `THIRD_PARTY_LICENSES.md` and
`docs/DATA_SOURCES.md`.
