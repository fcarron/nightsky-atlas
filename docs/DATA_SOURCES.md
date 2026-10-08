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

The 2026-10-06 Pocket data-quality pass retains OpenNGC pair/group source
subtypes, corrects confirmed cluster identities within `Cl+N`, represents
M24 as a star cloud and NGC 405 as a stellar pair, and adds the modern M102
alias to NGC 5866. Additional NGC/IC alias columns are imported only when
they do not conflict with another surviving canonical entry. Scientific
references, editorial Pocket exceptions and remaining ambiguities are in
`docs/POCKET_DSO_AUDIT.md`.

The OpenNGC importer applies source-specific semantic corrections while
retaining the raw snapshot: IC 434 does not inherit the erroneous “Flame
Nebula” common name (the Flame is NGC 2024); NGC 6334 is an H II/star-forming
nebula rather than an SNR; NGC 3324 is the ionizing cluster within the
separate Gum 31/IC 2599 nebula; B033 (Barnard 33) and C099 (Coalsack) are
dark nebulae rather than unspecified objects. B033 carries `B 33` as a
cross-identifier, allowing the Barnard source record to merge into that
OpenNGC object. Supporting identifications:
[ASSA Orion chart](https://assa.saao.ac.za/wp-content/uploads/sites/23/2017/10/concards_v154.pdf),
[NASA on Horsehead/Barnard 33](https://science.nasa.gov/asset/hubble/the-horsehead-nebula/),
[NASA on Coalsack/Caldwell 99](https://science.nasa.gov/mission/hubble/science/explore-the-night-sky/hubble-caldwell-catalog/caldwell-99/),
[NASA on NGC 6334](https://science.nasa.gov/asset/webb/cats-paw-nebula-nircam-image/),
[NASA on Gum 31](https://science.nasa.gov/missions/webb/new-visualization-from-nasas-webb-telescope-explores-cosmic-cliffs/).

### Curated DSO common names

`data/fixtures/dso_common_names.json` is a small, explicit editorial mapping from
normalized physical-object ID to one widely used English common name. Each row
records at least two source references; the file's `sources` section gives the
public source URLs. NASA's Hubble Messier/Caldwell guides, observatory sources,
Sky & Telescope, SEDS and OpenNGC were cross-checked; the mapping is not
generated from arbitrary web results. Catalogue raw `common_name`, aliases,
observing-list membership and canonical chart designation remain separate.

Only names in this mapping appear as common-name cross-references in the printed
index or in searchable diagnostics. Pocket may append an iconic name after the
designation (`M42 · Orion Nebula`) where the local DSO field is sufficiently
uncrowded (configured Pocket default: at most five other plotted DSO anchors
within 8 mm); other editions currently retain designation-only chart labels.
The mapping is editorial metadata, not a source of astronomical coordinates,
dimensions or selection decisions. Ambiguous names for multi-object regions
are excluded unless the physical association is clear. Caldwell numbers remain
observing-list metadata, never common names.

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
| Completeness | approximately 99% to V=11.0 and 90% to V=11.5; see [ESO Tycho-2 catalogue properties](https://archive.eso.org/ASTROM/TYC-2/docs/htmfiles/property.html) |
| License | **CC-BY-NC-3.0 IGO** (non-commercial) |
| Transformations | Johnson `V = VT - 0.090 * (BT - VT)`, VT/BT fallback; ICRS mean J2000 position except `pflag=P` photocentre records, whose component-specific observed positions are propagated to J2000; observed-position fallback |
| Import | `nightsky data fetch-stars` then `nightsky data import-stars` |

The atlas stores Tycho-2 Johnson display magnitude as `V = VT - 0.090 * (BT - VT)`.
Counts near V=11.5 are observed catalogue counts and are not completeness-corrected.

The non-commercial restriction must be reviewed before any public or commercial
distribution of a generated atlas. Tycho-2 is the primary catalogue; the
Hipparcos supplement below adds the bright stars it omits.
The catalogue source terms are recorded as CC BY-NC 3.0 IGO; the ESA licence is
available at <https://creativecommons.org/licenses/by-nc/3.0/igo/>. This is a
data-source condition and does not alter the MIT licence on the generator.

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
| Transformations | sexagesimal RA/Dec to degrees; V-Mag preferred, B-Mag fallback; `B-Mag`, `V-Mag`, `SurfBr`, `Hubble` and `Sources` retained for the galaxy visibility model |
| Import | `nightsky data fetch-openngc` then `nightsky data import-openngc` |

OpenNGC attribution and share-alike terms apply to OpenNGC-derived catalogue
material. The project does not apply them to unrelated source code or
third-party data.

### UCAC4 faint-star supplement and APASS photometry

The optional local faint-star store uses UCAC4 positions and photometry, with
valid APASS Johnson V preferred where present. Other records use the empirical
UCAC4 fallback described in [`docs/FAINT_STAR_SUPPLEMENT.md`](FAINT_STAR_SUPPLEMENT.md).
The source is Zacharias et al. (2013), USNO, CDS I/322A. UCAC4 metadata describe
it as U.S. government work, but the NightSkyAtlas import manifest records that
it did not identify an explicit redistribution licence. APASS photometry is
incorporated in UCAC4; separate usage terms for that photometry have not been
established here. Do not treat either statement as blanket permission to
redistribute the faint-star store or products containing those records.

### Galaxy visibility model (derived, not a catalogue)

Galaxy contour weight is derived from the retained OpenNGC photometry and
morphology by a Crumey-based contrast-threshold model; it is **presentation
metadata**, not an astronomical fact, and never mutates the normalized
catalogue.  It is computed once per galaxy and cached.  Full description and
reference conditions: `docs/GALAXY_VISIBILITY.md`.

| Field | Value |
| --- | --- |
| Reference | A. Crumey, *Human Contrast Threshold and Astronomical Visibility*, MNRAS 442, 2600-2619 (2014), https://doi.org/10.1093/mnras/stu992 |
| Implementation | `nightsky_atlas/catalog/galaxy_visibility.py`; `scipy` (incomplete gamma, root finding) and `numpy` |
| Inputs used | `Type`, `Name`, `M`, `MajAx`, `MinAx`, `SurfBr`, `B-Mag`, `V-Mag`, `Hubble`, `PosAng`, `Sources` |
| Output | contour class `bold`/`normal`/`fine`/`dotted`/`unclassified` per galaxy, for 100/200/400 mm |
| Scope | `Type == "G"` only; `GPair`/`GTrpl`/`GGroup`/`GCl` are not scored as one galaxy |
| Attribution printed | `Data, credits and licence` page of every atlas |

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

The USNO acknowledgement is: *“This research has made use of the Washington
Double Star Catalog maintained at the U.S. Naval Observatory.”* See the
[USNO WDS page](https://crf.usno.navy.mil/wds). The source is not a source of
single-star chart positions.

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

Pocket mandatory-list snapshots are vendored as `messier.json` and
`caldwell.json`, alongside `herschel400.json`. Their provenance, list-version
notes, identity exceptions and unresolved rows are documented in
`data/fixtures/observing_lists/SOURCE.md`. Caldwell is selection metadata only;
the label formatter does not use Caldwell designations as chart labels.

### Constellation geometry

| Field | Value |
| --- | --- |
| Stick figures | Stellarium Western (Sky & Telescope), `western_SnT/index.json`, commit `014fbb5e59233d133c22f9811af96b67d05a95c9` |
| Stick-figure license | **CC BY-SA 2.0**; attribution: Paul Krizak and Jonathan E. Piskor; rework by Stellarium Team |
| Boundaries | d3-celestial (Olaf Frohn), `master`, fetched 2026-09-16 |
| Boundary license | **BSD-3-Clause** |
| Files | `data/fixtures/constellations/{constellations.lines,constellations.bounds}.json` |
| Companion | `SOURCE.md`, `constellations.lines.manifest.json`, `THIRD_PARTY_LICENSES.md`; boundary `LICENSE` |
| Content | 88 S&T figures (20 bold, 165 normal, 24 thin polylines); 785 deduplicated IAU boundary segments |
| Transformations | HIP references preserved; consecutive repeated IDs removed; HIP positions resolved via NightSky stellar catalog; boundaries deduplicated at load time |
| Committed | yes; atlas builds remain offline and reproducible |

### Schematic nebula outlines

| Field | Value |
| --- | --- |
| Source | authored for NightSky Atlas (project-authored schematic tracing) |
| Files | `data/fixtures/outlines/nebulae.json` |
| Companion | `SOURCE.md` in the same directory |
| License | CC BY 4.0 for this project-authored schematic artwork |
| Content | coarse closed RA/Dec outlines for extended objects where an ellipse would mislead (Veil, North America, Pelican, ...) |
| Stable IDs | `outline:dso:<dso_id>` (e.g. `outline:dso:NGC7000`) |
| Transformations | edges densified along RA/Dec, projected with the chart projection, clipped to the chart field |
| Committed | yes; build must be reproducible offline |

### Milky Way brightness contours

| Field | Value |
| --- | --- |
| Source project | d3-celestial by Olaf Frohn |
| Original outline source cited upstream | José R. Vieira, *Milky Way Outline Catalog* |
| File | `data/third_party/d3-celestial/mw.json` |
| Upstream revision | `7e720a3de062059d4c5400a379146a601d9010e0` |
| Upstream URL | <https://github.com/ofrohn/d3-celestial/blob/7e720a3de062059d4c5400a379146a601d9010e0/data/mw.json> |
| License | BSD-3-Clause for the GeoJSON as distributed by d3-celestial; adjacent `LICENSE` and `SOURCE.md` retain the notice. This does not claim Vieira released the original catalogue under BSD. |
| Geometry | Five GeoJSON MultiPolygon outline levels, `ol1`–`ol5`, at J2000 |
| Transformation | GeoJSON longitude is converted back to RA; paths are projected with the chart stereographic projection and clipped. Source geometry is not regenerated or edited. |
| SHA-256 | `aee221a7a0e879418e685de00c3e68fbdfac5667c0a8aab74929ef9cf4aab4fb` |

Edition styles select levels 1 for Pocket, 1+3 for Standard and Eyepiece,
and 1+3+5 for Deep. Rendering is stroke-only; levels 2 and 4 are not selected.

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

Standard's printed proper names are an original, HIP-keyed editorial subset
(`data/fixtures/starnames/curated.yaml`: 99 core, 86 standard, 17 extended).
Canonical spellings and HIP identities were checked against the IAU Catalog of
Star Names, 2022-04-04 snapshot (IAU-produced data, Creative Commons
Attribution; version unspecified in the snapshot); see
`data/fixtures/starnames/SOURCE.md` for the IAU citation and snapshot URL.
The source list is retained independently as d3-celestial BSD-3-Clause data;
uncurated names remain available as aliases but are not automatically printed.
The IAU snapshot is identified by its source as Creative Commons Attribution;
the snapshot does not specify a version. This does not establish terms for
later IAU catalogue releases.

`curated.yaml` also identifies a small set of conspicuous visual variable
stars by HIP number for a printed open-ring finding symbol. Selection was
cross-checked against the [AAVSO Variable Star Index (VSX)](https://www.aavso.org/search-and-download-data/)
on 2026-09-26. No VSX catalogue records are redistributed; this is an
intentionally incomplete atlas aid, not a variable-star observing sequence.
See `data/fixtures/starnames/SOURCE.md` for scope and acknowledgement details.

### VizieR nebula catalogues (Deep / Reference expansion)

The importer is explicit and offline after acquisition:

```text
nightsky data fetch-vizier-dsos [--catalogues ...]
nightsky data import-vizier-dsos
nightsky data dso-info 'NGC 7000'
nightsky atlas catalog-object 'HCG 92' --edition reference
nightsky data selection-report --json build/selection-report.json
nightsky atlas why-object 'NGC 891'
```

`data selection-report` summarizes current edition eligibility without changing
selection policy. It reports unique physical objects separately from source
entries/aliases, with type/source breakdowns, metadata availability,
distributions and policy warnings; optional `--csv PATH` writes a tabular
export. `atlas why-object DESIGNATION` resolves a canonical designation or
alias and explains the current Standard, Deep and Reference decisions with
machine-readable reason codes. These diagnostics are generated from the same
selection function used by atlas builds.

The fetch command saves each VizieR TSV response under `data/raw/vizier_dso/`,
including the service-computed ICRS coordinate columns, and writes a manifest
with retrieval timestamp, table/version metadata, raw row count, query URL and
SHA-256. Partial fetches merge into the existing manifest. Import verifies
those checksums and writes the merged physical-object
catalogue plus a cross-match report. Builds do not contact VizieR. The processed
catalogue retains every external designation and a source record with the raw
fields and match decision. Cross-match uncertainty is reported, never silently
merged. A positional footprint estimate derived from LDN area is explicitly an
equivalent circular diameter, not a source-reported ellipse.

| Source / table | Reference and VizieR URL | Rows seen (2026-09-24) | Input frame / fields used |
| --- | --- | ---: | --- |
| Sharpless H-II regions, `VII/20/catalog` | Sharpless 1959, ApJS 4, 257; [VizieR VII/20](https://vizier.cds.unistra.fr/viz-bin/VizieR-3?-source=VII%2F20) | 313 | FK4 B1900; `Sh2`, `RA1900`, `DE1900`, `Diam`, plus computed `_RAJ2000`, `_DEJ2000` |
| Lynds Dark Nebulae, `VII/7A/ldn` | Lynds 1962, ApJS 7, 1; [VizieR VII/7A](https://vizier.cds.unistra.fr/viz-bin/VizieR-3?-source=VII%2F7A) | 1,787 | FK4 B1950; `LDN`, `RA1950`, `DE1950`, `Area`, `Opacity`, `Lynds2`, `Barn`, plus computed J2000 |
| Lynds Bright Nebulae, `VII/9/catalog` | Lynds 1965, ApJS 12, 163; [VizieR VII/9](https://vizier.cds.unistra.fr/viz-bin/VizieR-3?-source=VII%2F9) | 1,125 | FK4 B1950; `Seq`, `RA1950`, `DE1950`, `Diam1/2`, `Area`, `Bright`, `Name`, plus computed J2000 |
| van den Bergh reflection nebulae, `VII/21/catalog` | van den Bergh 1966, AJ 71, 990 (corrected VizieR table 2022-11-13); [VizieR VII/21](https://vizier.cds.unistra.fr/viz-bin/VizieR-3?-source=VII%2F21) | 158 | Original positions are absent; retains SIMBAD `_RA`, `_DE` J2000 positions, `Type`, `SurfBr`, radii and original Galactic fields |
| Barnard dark nebulae, `VII/220A/barnard` | Barnard 1927; [VizieR VII/220A](https://vizier.cds.unistra.fr/viz-bin/VizieR-3?-source=VII%2F220A) | 349 | FK4 B1875; `Barn`, `RA1875`, `DE1875`, `Diam`, plus computed J2000 |

The Sharpless importer classifies Sh 2-240 (Simeis 147) as an SNR rather than
an H II region; its raw Sharpless row is preserved. The SNR identification is
supported by [multiwavelength research on Simeis 147](https://arxiv.org/abs/2401.17312).

The importer requests VizieR's computed J2000/ICRS coordinate columns explicitly
for every table (`_RAJ2000`/`_DEJ2000` or `_RA.icrs`/`_DE.icrs`, as supplied by
the source). These are the normalized atlas coordinates.
Original historical coordinates and their frames remain in
`CatalogSourceRecord` for audit. The importer does not reinterpret old
coordinates as J2000. Nebulae map
to bright/H-II, dark, or reflection subtypes while retaining those subtypes in
the normalized object. It does not assign the galaxy-only Crumey visibility
class. Historical brightness/classification fields (including van den Bergh's
photographic `SurfBr`) are retained as raw metadata, not misrepresented as
calibrated visual magnitudes or mag/arcsec².

Cross-matching first compares normalized catalogue identifiers against existing
canonical IDs and aliases. Only explicit, qualified identifiers are treated as
aliases: LDN Barnard cross-references become `B n`; Lynds' `Lynds2` update
sequence numbers are retained as raw metadata but are not global IDs. Otherwise
matching uses compatible nebula classes and
extent-aware angular proximity: smaller dark-cloud radii, larger nebula radii,
and a wider ambiguity-search radius. A unique candidate inside the conservative
match radius is merged; multiple or near-but-not-secure candidates are retained
as separate objects and marked `uncertain`. Explicit LDN Barnard cross-IDs are
used where present. Each source record records the distance, decision,
confidence and reason. Review the generated report before publication, in
particular around North America/Pelican, Crescent, Cocoon, Orion and overlapping
dark clouds.

Edition policy is independent of ingestion and is configured in
`config/observing_lists.yaml`. Standard keeps conservative galaxy visibility,
prominence-based cluster rules and explicit observing-list overrides. Deep
uses the galaxy visibility classes and aperture-400 score, plus broader
object-specific size, brightness and catalogue-family rules. Reference covers
valid classified galaxies and valid objects from the intentionally imported
observer catalogues; it does not promote unclassified galaxies or poorly typed
OpenNGC “Other” entries. Uncertain auxiliary matches remain excluded except in
Reference, where they are shown as conditional records. Arp is alias-only:
unmatched Arp entries are not introduced as extra plotted galaxies. Hickson
groups are separate `galaxy_cluster` objects with member relationships, while
individual galaxies remain separate. The selection report and
`atlas why-object` expose the production decision and its reason codes.
These thresholds are editorial atlas policy, not astronomical visibility
claims.

### RC3 galaxy catalogue (ingested, not enabled for edition selection)

The [revised Third Reference Catalogue of Bright Galaxies, RC3](https://cdsarc.cds.unistra.fr/viz-bin/ReadMe/VII/155?format=html&tex=true),
by de Vaucouleurs, de Vaucouleurs, Corwin, Buta, Paturel and Fouqué (1991),
is imported from VizieR `VII/155/rc3`. The corrected electronic table contains
23,011 rows; the printed catalogue's often quoted 23,022 is not the row count
of this revision. Retrieval date, exact query and SHA-256 are in the local
VizieR source manifest. The source positions are FK4 B2000; VizieR's computed
J2000/FK5 positions are used for the atlas, and original positions remain in
source metadata. The VizieR acknowledgement above applies. RC3 asks users to
credit its authors; unaltered electronic copies may be shared with its
documentation and notice, while reproduction of the printed work is restricted.
The raw snapshot is not committed to this repository.

Each RC3 row is keyed by its PGC identifier where present (otherwise `name`).
`name`, `altname` and `desig`
are alternate identifiers; matching first uses these against the normalized
OpenNGC and existing catalogue aliases. A unique explicit match retains the
existing canonical object, including its OpenNGC photometry, and adds RC3
provenance and aliases. A positional-only galaxy match is allowed only within
15 arcsec, with no other candidate inside 30 arcsec and compatible reported
extent. Discordant identifiers or multiple plausible matches remain uncertain
and separate. PGC leading zeros are normalized for matching, while NGC/IC
component suffixes are significant (`NGC 1023A` is not `NGC 1023`).
Large/overlapping systems still require manual review before a
future edition-selection expansion.

RC3 `D25` is logarithmic in units of 0.1 arcmin: major-axis arcmin =
`10**D25 / 10`. `R25` is the logarithmic major/minor ratio: minor-axis
arcmin = major / `10**R25`. `PA` is retained. Valid `BT` is stored as a B-band
magnitude, but `BT_code=V` is **not** mislabelled as B. The photographic `Bmag`,
colour `B-VT`, morphology `type`/`T`, axis-uncertainty flags and mean-brightness
`m'25` are preserved in raw source fields;
the latter is in mag/arcmin² and is not silently fed to the existing
mag/arcsec² galaxy-visibility model. Matched OpenNGC data are not overwritten.

The 2026-09-27 snapshot parsed 23,011 rows: 7,259 aliases merged, 15,663
unambiguous new objects, and 89 uncertain records retained separately. RC3
adds 15,752 galaxy records to the normalized physical-DSO pool, including
uncertain records. RC3-only galaxies are deliberately **not yet eligible** for
Pocket, Standard, Deep or Reference; enabling them requires a separate visual
selection policy and validation. With the current selection configuration,
the edition totals are identical with and without RC3.

### Second observer-oriented VizieR batch

The 2026-09-24 snapshots add these source families. Lyngå VII/92A is one
authoritative open-cluster table: sequence codes 6, 27 and 11 identify
Collinder, Melotte and Stock respectively. VizieR-computed ICRS positions are
used; B1950 input coordinates remain in provenance. The Abell PN filter uses
the `A nn` alternate names in Kohoutek's galactic PN table, retains only rows
not flagged misclassified (`f_PK` blank or `*`), and keeps PK cross-IDs. This is
not an Abell galaxy-cluster import (`VII/110A`). Harris VII/202 is used for
Palomar/Terzan names, integrated V magnitude and raw structural parameters
including `Rh`, `Rc`, and `muV`; half-mass/core radii are not misrepresented as
full visible diameters. Hickson groups and member galaxies come from separate
tables. Arp VII/74A is an alias/system cross-reference layer only.

| Family | VizieR table | Original reference | Family rows | Details |
| --- | --- | --- | ---: | --- |
| Collinder | `VII/92A/catalog`, `ClSeq=6` | Lyngå, *Catalogue of Open Cluster Data*, 5th ed. (1987), sequence code 6 | 67 | `ClNum`, `RA1950`, `DE1950`, `Diam`, `OCL`, cluster metadata |
| Melotte | `VII/92A/catalog`, `ClSeq=27` | Lyngå 1987, sequence code 27 | 9 | same source fields; designation `Mel n` |
| Stock | `VII/92A/catalog`, `ClSeq=11` | Lyngå 1987, sequence code 11 | 20 | same source fields; designation `Stock n` |
| Abell planetary nebulae | `IV/24/table1` | Kohoutek, *Catalogue of Galactic Planetary Nebulae* (2001), `2001A&A...378..843K`; Abell names originate in Abell 1966, `1966ApJ...144..259A` | 74 | parent table 1,759 rows; selected `Name=A n` rows; `PK`, `RAB1950`, `DEB1950`, `f_PK`; computed J2000 coordinates |
| Four curated planetary nebulae | `IV/24/table1` | Same Kohoutek source and provenance as the Abell PN import | 4 | only `M 1-64`, `Jn 1`, `J 900`, `Sp 1`; PK aliases and computed J2000 coordinates; no magnitude or diameter imported |
| Palomar globulars | `VII/202/catalog`, `ID` beginning `Pal` | Harris, AJ 112, 1487 (1996; VizieR 1997 table), `1996AJ....112.1487H` | 13 | J2000, `Vt`, `Name`, `Rh`, `Rc`, `muV`, `MVt`, `[Fe/H]` |
| Terzan globulars | `VII/202/catalog`, `ID` beginning `Ter` | Harris 1996 / VII/202 | 11 | same fields as Palomar |
| Hickson Compact Groups | `VII/213/groups` + `VII/213/galaxies` | Hickson, ApJ 255, 382 (1982), `1982ApJ...255..382H`, with 1989/1992 catalogue updates | 100 groups; 463 member rows | B1950 group positions with computed J2000; `AngSize`, `Totmag`, `MCount`; member `HCG`, `m_HCG`, `Names` |
| Arp peculiar galaxies | `VII/74A/table2` | Arp, ApJS 14, 1 (1966), `1966ApJS....14....1A` | 338 | Arp number, `Name`, RA1970/DE1970 and computed ICRS; alias-only |

Deep selection is narrower than the imported Abell candidate rows. The local
`nightsky_confirmed_abell_pn.json` membership selects `f_PK`-blank Abell targets
and independently confirmed Abell 21; rows flagged as possible PN are not
automatically included. It contains 72 physical targets after canonical
NGC aliases are deduplicated. Missing photometry or size does not prevent these
targets from appearing in Deep. This membership is selection metadata, not new
photometric or dimensional data.

Exact table URLs, queries, retrieval timestamps, checksums, imported fields,
selection filters, member-table hashes, and VizieR acknowledgement are recorded
in `data/raw/vizier_dso/manifest.json` and copied to the processed catalogue
manifest. The source table revisions are pinned operationally by the archived
response bytes and SHA-256, rather than by a moving `master` URL. VizieR
catalogue landing pages: [VII/92A](https://cdsarc.cds.unistra.fr/viz-bin/cat/VII/92A),
[IV/24](https://cdsarc.cds.unistra.fr/viz-bin/cat/IV/24),
[VII/202](https://cdsarc.cds.unistra.fr/viz-bin/cat/VII/202),
[VII/213](https://cdsarc.cds.unistra.fr/viz-bin/cat/VII/213), and
[VII/74A](https://cdsarc.cds.unistra.fr/viz-bin/cat/VII/74A).

The import added 266 unambiguous new physical objects in this batch, merged
175 aliases into existing objects, and retained 8 uncertain non-Arp rows as
separate Reference-only candidates. Arp contributed 155 matched aliases, 70
uncertain associations and 113 unmatched alias-only records; no Arp row created
a second plotted object. Across both VizieR batches, 3,436 rows were new
physical records, 356 aliases were merged, 459 positional associations remain
uncertain, and the normalized catalogue contains 17,197 physical records.
Counts and examples are reproducibly generated by `nightsky data
catalogue-report`; the raw snapshots are local/ignored and not committed.

No blanket redistribution licence for these historical catalogues is asserted
here. VizieR provides the tables but that is not itself
an open-data licence; consult each source publication/rights holder before
redistributing raw or processed records. The source manifest records each table
citation, VizieR URL, fetched-at time, checksum, fields and coordinate handling.
When citing use the catalogue references above and the requested service
acknowledgement: *“This research has made use of the VizieR catalogue access
tool, CDS, Strasbourg, France (DOI: 10.26093/cds/vizier).”*

## Alpha open-cluster selection

Pocket retains its forced Messier, Caldwell, Herschel 400 and NightSkyAtlas
Pocket Classics targets. Other open clusters from Pocket-enabled catalogues are
selected when integrated magnitude is known and at most 9.0 with a major axis
of at least 3 arcmin, or when the major axis is at least 20 arcmin regardless
of magnitude. Standard inherits Pocket and adds eligible OpenNGC NGC/IC open
clusters with magnitude at most 10.0 and size at least 3 arcmin, or size at
least 10 arcmin regardless of magnitude. Its existing list memberships remain
eligible. This does not select every NGC/IC cluster. Deep retains its existing
open-cluster rules; Eyepiece uses the Deep target set.

These are catalogue-selection thresholds. They do not change the separate
symbol sizing thresholds used for printing (Pocket 20′, Standard 10′, Deep 5′,
Eyepiece 2.5′). C014 remains in catalogue metadata but is excluded from plotted
targets in every edition because NGC 869 and NGC 884 are represented separately.

## Committed versus ignored

Git-ignored (regenerate, do not commit): `data/raw/`, `data/processed/`,
`build/`, `benchmarks/ai_review/generated/`, `benchmarks/ai_review/results/`,
`.env`.

Committed: small fixtures under `data/fixtures/` and `overrides/`.

## Editorial fonts

All non-chart editorial text, including the Introduction title, uses locally
bundled Source Sans 3. Charts use locally bundled Lato Regular and Bold. The
font files are registered from `src/nightsky_atlas/assets/fonts/` with the
active Fontconfig instance before Pango creates layouts. System-installed Lato
faces are excluded for the atlas process, and runtime checks ensure that the
regular and bold chart faces resolve to the bundled files. The fonts are
embedded by the PDF renderer. The upstream projects are [Source Sans](https://github.com/adobe-fonts/source-sans)
and [Lato](https://github.com/latofonts/lato).
Bundled SHA-256 checksums:

| File | SHA-256 |
| --- | --- |
| `SourceSans3-Variable.ttf` | `042fe82cc9b933e328410d7acbd0aa6a1873dca5aef81875f4bc214b08825c7b9` |
| `Lato-Regular.ttf` | `6f6940be0835c3ddec9199e5fc42be4cbc61ebcfd58c623fdf719366253f1780` |
| `Lato-Bold.ttf` | `bf1b8130069b44b9148eeece35e5423bedac49777ba746615b826b8276574a7b` |

Lato Regular and Bold are from the Lato project, copyright Łukasz Dziedzic,
licensed under the SIL Open Font License 1.1. Source Sans 3 is copyright Adobe
and is also licensed under OFL 1.1. The full notices are bundled as
`OFL-Lato.txt` and `OFL-SourceSans3.txt` beside the font files. The repository's
MIT licence does not apply to third-party font software.

The existing chart-label font configuration remains independent of these
editorial fonts.

## Project-authored cartography

Original NightSky Atlas cartographic design, page layout and explicitly marked
project-authored artwork are licensed under CC BY 4.0 where identified. This
includes the schematic nebula outlines in
`data/fixtures/outlines/nebulae.json`. Third-party figures, boundaries,
contours, fonts and catalogue data retain their own terms. Generated PDFs are
not automatically MIT-licensed merely because the generator is MIT-licensed.
