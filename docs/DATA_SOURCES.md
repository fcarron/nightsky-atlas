# Data sources and storage

Catalogue strategy, storage and licensing. `AGENTS.md` links here. This is the
authoritative provenance record required before any public distribution (plan
item M16.4).

## Strategy

Catalogue ingestion is isolated from rendering. The import layer retains source
provenance; source-specific column semantics never leak outside their importer.

### Stars

Initial preferred source: **Tycho-2**, supplemented by the **Hipparcos** main
catalogue for the brightest stars. Tycho's star mapper saturated on stars
brighter than roughly V=2.5, so Tycho-2 omits Deneb, Vega, Altair, Sirius and
other bright stars that are essential to a usable star atlas. Hipparcos (the
companion mission) contains them and shares the same license.

Required normalized fields:

```text
id
ra
Dec
visual magnitude or documented display magnitude
source catalogue
source identifier
```

Optional later fields: `B-V`/colour index, proper motion, spectral class,
variable-star flags, common names, Bayer/Flamsteed designations.

### Deep-sky objects

Initial source: **OpenNGC** (structured, suitable for prototyping). The
normalized DSO model supports:

```text
canonical id
cross identifiers
RA
Dec
object type
magnitude
magnitude type/source
major axis
minor axis
position angle
common name
constellation
source provenance
```

The model must not assume every field exists.

### Later catalogues

NightSky Deep may need additional legally compatible datasets for non-NGC/IC
galaxies, planetary nebulae, dark/emission/reflection nebulae, galaxy clusters,
large stellar associations, nebula outlines and Milky Way brightness contours.

Do not ingest additional catalogues merely to increase object count. Each
source requires:

1. license review;
2. provenance metadata;
3. field mapping;
4. duplicate/cross-ID strategy;
5. explicit visual-observing value.

## Licensing

Never assume that data visible through an astronomy service can be freely
redistributed. For every data source, record:

- source name, URL/reference, version/date;
- license;
- redistribution constraints;
- attribution requirements;
- imported fields;
- transformations performed.

## Storage

- raw downloaded catalogue files: `data/raw/`;
- normalized build data: `data/processed/`;
- metadata/provenance: adjacent JSON manifest;
- build artifacts: `build/`.

Do not commit large catalogue files unless license and repository size make that
appropriate. The repository provides scripts to reproduce processed data from
raw inputs. Potential formats: Parquet for large stellar tables, SQLite for
indexed lookup, compact JSON only for small fixtures/tests.

Format decisions follow profiling, not preference. SQLite was retained after the
M4 benchmark (see `docs/PERFORMANCE.md`); Parquet was rejected because it would
add a large dependency without a spatial index while query latency is already
acceptable.

Tests must use small committed fixtures and must not depend on multi-gigabyte
external catalogues.

## Current sources

### Tycho-2 (stars)

| Field | Value |
| --- | --- |
| Source | The Tycho-2 Catalogue (Høg et al. 2000), CDS I/259 |
| Raw | `data/raw/tycho2/` (20 gzip parts, ~159 MB) |
| Processed | `data/processed/stars/tycho2.sqlite` (2,539,913 stars, ~364 MB) |
| Manifest | `data/processed/stars/tycho2.manifest.json` |
| License | **CC-BY-NC-3.0 IGO** (non-commercial) |
| Transformations | Johnson `V = VT - 0.090 * (BT - VT)`, VT/BT fallback; ICRS mean J2000 position, observed-position fallback |
| Import | `nightsky data fetch-stars` then `nightsky data import-stars` |

The non-commercial restriction must be reviewed before any public or commercial
distribution of a generated atlas. Tycho-2 is the primary catalogue; the
Hipparcos supplement below adds the bright stars it omits.

### Hipparcos (bright-star supplement)

| Field | Value |
| --- | --- |
| Source | The Hipparcos and Tycho Catalogues (ESA 1997), CDS I/239, `hip_main.dat` |
| Raw | `data/raw/hipparcos/hip_main.dat` (118,218 records, ~53 MB) |
| Processed | merged into `data/processed/stars/tycho2.sqlite` |
| Manifest | `data/processed/stars/tycho2.manifest.json` (`bright_star_supplement`) |
| License | **CC-BY-NC-3.0 IGO** (non-commercial) |
| Transformations | Johnson `V` (`Vmag`; `Hpmag` fallback); ICRS position at J1991.25 propagated to J2000 with catalogue proper motion |
| Duplicates | a Hipparcos star is dropped when a Tycho-2 star lies within 3 arcsec (Tycho-2 wins) |
| Import | `nightsky data fetch-hipparcos` then `nightsky data import-stars` |

### OpenNGC (deep-sky)

| Field | Value |
| --- | --- |
| Source | OpenNGC (mattiaverga/OpenNGC) |
| Raw | `data/raw/openngc/{NGC.csv,addendum.csv}` |
| Processed | `data/processed/dso/openngc.json` (13,372 objects) |
| Manifest | `data/processed/dso/openngc.manifest.json` |
| License | **CC-BY-SA-4.0** |
| Transformations | sexagesimal RA/Dec to degrees; V-Mag preferred, B-Mag fallback |
| Import | `nightsky data fetch-openngc` then `nightsky data import-openngc` |

### Visual double/multiple stars (overlay)

Tycho-2 remains the source of truth for single-star positions and magnitudes.
WDS is a **semantic overlay** for visual double/multiple systems: it identifies
systems and components, and records separation, position angle and component
magnitudes, but it never overwrites Tycho-2 data. Systems are linked to the star
base per chart (`catalog/systems.py`), and only `exact`/`positional` matches may
influence the printed chart.

| Field | Value |
| --- | --- |
| Source | The Washington Visual Double Star Catalog (WDS), Mason et al. 2001, CDS `B/wds` |
| Edition | `2026-08-10` |
| Raw | `data/raw/wds/wds.dat.gz` (~6.5 MB, 157,917 records) |
| Processed | `data/processed/double_stars/wds.json` (157,644 systems, ~57 MB) |
| Manifest | `data/processed/double_stars/wds.manifest.json` |
| License | **Public domain** (U.S. Naval Observatory); acknowledgement requested |
| Transformations | sexagesimal RA/Dec to degrees; latest-epoch separation/position angle (first-epoch fallback, negative sentinels dropped); component magnitudes `mag1`/`mag2`, combined as `-2.5*log10(sum(10**(-0.4*m_i)))` |
| Fixture | `data/fixtures/double_stars/wds_subset.dat` (nine verbatim records) + `SOURCE.md` |
| Import | `nightsky data fetch-wds` then `nightsky data import-wds` |

The USNO requests the acknowledgement: *"This research has made use of the
Washington Double Star Catalog maintained at the U.S. Naval Observatory."*
Linkage is positional (default 2 arcsec primary / 3 arcsec companion tolerance)
and per chart, so the overlay scales with the atlas edition instead of baking a
fixed angular separation into the data.

### Observing-list membership (atlas metadata)

Curated visual observing lists drive DSO selection (forced include plus
priority bonuses).  Membership is **atlas metadata**, not an astronomical fact:
it is loaded from vendored fixtures and never merged into the normalized
catalogue or written back onto a `DeepSkyObject` (see `config/observing_lists.yaml`
for the per-edition policy).  Designations are normalized at load time, so
`NGC 869`, `NGC0869` and `M 42` compare equal.

| Field | Value |
| --- | --- |
| Source | Wikipedia, *Herschel 400 Catalogue*, revision 1369720351 |
| Files | `data/fixtures/observing_lists/herschel400.json` |
| Companion | `SOURCE.md` in the same directory |
| License | **CC BY-SA 4.0** (compatible with the OpenNGC share-alike terms) |
| Content | 402 normalized NGC designations for 400 Herschel 400 catalogue rows (three double designations expanded) |
| Known gaps | nine designations have no OpenNGC object: NGC651, NGC2244, NGC2372, NGC2527, NGC3190, NGC3912, NGC4665, NGC6885, NGC7296 |
| Committed | yes (~6 kB); build must be reproducible offline |

Additional lists (Messier, Caldwell, RASC, SAC, ASSA, Bennett, NSOG, Herschel II,
Astronomical League programs, Hickson, Abell) are already named and weighted in
`config/observing_lists.yaml`; they are integrated one at a time as legally
clean fixtures become available.  NSOG-derived data is **not** imported until
its licensing is resolved.

### Constellation geometry

| Field | Value |
| --- | --- |
| Stick figures | IAU/MacRobert design, via Dominic Ford's `dcf21/constellation-stick-figures`, `constellation_lines_iau.dat`, commit `75d29c207bbd752023c447ddd1f9f4ff0eb47538` |
| Stick-figure license | **CC BY 4.0**; attribution: Alan MacRobert et al., imported via Dominic Ford |
| Boundaries | d3-celestial (Olaf Frohn), `master`, fetched 2026-09-16 |
| Boundary license | **BSD-3-Clause** |
| Files | `data/fixtures/constellations/{constellations.lines,constellations.bounds}.json` |
| Companion | `LICENSE`, `SOURCE.md` in the same directory |
| Content | 89 IAU/MacRobert stick figures; 785 deduplicated IAU boundary segments |
| Transformations | stick-figure Hipparcos IDs resolved to J2000 RA/Dec without changing connectivity; boundary polygons converted to a deduplicated segment set at load time |
| Committed | yes (~68 kB); build must be reproducible offline |

### Schematic nebula outlines

| Field | Value |
| --- | --- |
| Source | authored for NightSky Atlas (project-authored schematic tracing) |
| Files | `data/fixtures/outlines/nebulae.json` |
| Companion | `SOURCE.md` in the same directory |
| License | proprietary, covered by the project license (no third-party data) |
| Content | coarse closed RA/Dec outlines for extended objects where an ellipse would mislead (Veil, North America, Pelican, ...) |
| Stable IDs | `outline:dso:<dso_id>` (e.g. `outline:dso:NGC7000`) |
| Transformations | edges densified along RA/Dec, projected with the chart projection, clipped to the chart field |
| Committed | yes; build must be reproducible offline |

### Star names and designations

| Field | Value |
| --- | --- |
| Source | d3-celestial (Olaf Frohn), `data/starnames.json`, `master`, fetched 2026-09-16 |
| Files | `data/fixtures/starnames/starnames.json` |
| Companion | `LICENSE` (BSD-3-Clause), `SOURCE.md` in the same directory |
| License | **BSD-3-Clause** |
| Content | common names plus Bayer/Flamsteed/variable designations for ~4,600 Hipparcos stars, keyed by Hipparcos number |
| Transformations | derived from the raw d3-celestial file, keeping only name/designation/constellation fields; thin spaces stripped |
| Committed | yes (~207 kB); build must be reproducible offline |

## Committed versus ignored

Git-ignored (regenerate, do not commit): `data/raw/`, `data/processed/`,
`build/`, `benchmarks/ai_review/generated/`, `benchmarks/ai_review/results/`,
`.env`.

Committed: small fixtures under `data/fixtures/` and `overrides/`.
