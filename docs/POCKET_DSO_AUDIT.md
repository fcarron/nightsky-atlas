# Pocket DSO quality audit — 2026-10-06

This conservative pass preserves Pocket's rich visual-observing selection at
5 mm/degree. Editorial additions and exclusions use the existing observing-list
and edition-exception mechanisms. There is no new magnitude or density cut.
Raw source snapshots and canonical physical-object IDs are preserved.

## A. Corrected metadata and identities

- NGC 5866 carries the modern observer-facing M102 alias. NGC 5866 remains the
  canonical identity. The historical M102 ambiguity is acknowledged, without
  affecting chart formatting. [NASA identification](https://apod.nasa.gov/apod/ap240306.html).
- OpenNGC `GPair`, `GTrpl` and `GGroup` retain their source meaning in
  `semantic_subtype`: galaxy pair, triplet and group. The index prints Galaxy
  Pair / Galaxy Group rather than Galaxy Cluster. The existing group symbol and
  selection family remain available as `galaxy_cluster`; genuine clusters with
  no pair/group subtype still print Galaxy Cluster. This avoids adding a new
  selection taxonomy. [OpenNGC schema](https://github.com/mattiaverga/OpenNGC/blob/master/NGC_guide.txt).
- `Cl+N` means cluster **and** nebulosity, so it is not globally remapped.
  The identified cluster entries NGC 1981, NGC 2239/2244, NGC 6530, NGC 6823,
  NGC 6997 and NGC 7380 now use Open Cluster. Their composite source subtype is
  retained. M42 remains a nebula. Evidence:
  [NGC 1981 study](https://academic.oup.com/mnras/article/407/3/1875/1070988),
  [ESO on NGC 6530](https://www.eso.org/public/news/eso0936/),
  [NASA on NGC 6823 and NGC 6820](https://science.nasa.gov/photojournal/the-little-fox-and-the-giant-stars/),
  [Unified Cluster Catalogue on NGC 6997](https://ucc.ar/_clusters/ngc6997/),
  [NASA on NGC 7380](https://apod.nasa.gov/apod/ap200904.html).
- M24 / IC 4715 is Other with the subtype Star Cloud; the index prints Star
  Cloud. [NASA classification](https://science.nasa.gov/mission/hubble/science/explore-the-night-sky/hubble-messier-catalog/messier-24/).
- Printed DSO constellations map both `Se1` and `Se2` to `Ser`. Internal source
  subdivisions remain intact.
- OpenNGC's additional NGC/IC designation fields are now read. A designation
  that is also a different surviving canonical record is not imported as an
  exact alias. For example, the snapshot's NGC 7418 → IC 1459 reference conflicts
  with the separate IC 1459 galaxy. This does not merge or rename either target.
- NGC 2239 retains its stable ID and gains NGC 2244 as an alias; charts and
  indexes prefer NGC 2244. This was already a selected Rosette-cluster target,
  not a new physical object. [ESO identification](https://www.eso.org/public/images/b12/).
- PGC 70070 already has IC 5269B as a source alias. Both chart and index now
  prefer the IC designation; its internal PGC identity remains unchanged.
- NGC 405 is imported as Double Star, following the snapshot's explicit
  “Two Galactic stars” note and HD 6869 identification. It no longer contributes
  an artificial DSO symbol. The primary stellar catalogue is unaffected.

## B. Added Pocket targets

| Target | Previous status | Inclusion reason | Chart designation |
| --- | --- | --- | --- |
| Melotte 20 | Imported Melotte object; source not enabled for Pocket | Alpha Persei cluster: large, distinctive star-hopping target | Mel 20 |
| NGC 2359 | Database present; no usable photometry, excluded by visibility evaluator | Established visual emission-nebula target; explicit editorial exception | 2359 |
| NGC 281 | Database present; no usable photometry, excluded by visibility evaluator | Established extended visual nebula; explicit editorial exception | 281 |
| NGC 7295 / 7296 | Selected catalogue object lacked the NGC 7296 alias and H400 membership | Restored source alias activates the existing H400 rule | 7295 |

The three editorial additions are in `nightsky_pocket_classics.json`. NGC 7295
is a consequence of fixing source aliases, not a new curation list member.
NGC 2244 was already present as NGC 2239 and is normalized, not counted again.

[ESO on NGC 2359](https://eso.org/public/images/eso1238a/) and
[NASA on NGC 281](https://science.nasa.gov/photojournal/the-pacman-nebula/)
support their established identities. Inclusion is NightSkyAtlas's editorial
choice, not a claim that either object is easy under every sky condition.

## C. Removed or normalized Pocket entries

These exclusions apply only to Pocket and leave source records available to
other editions. Every item was selected automatically, with no Messier,
Caldwell, H400 or explicit Pocket-curation membership requiring it.

| Entry removed | Reason / retained target |
| --- | --- |
| NGC 1487 NED02 | Duplicate component marker; retain parent NGC 1487 |
| NGC 4656 NED01 | Duplicate component marker; retain H400 parent NGC 4656 |
| IC 2605 | Source identifies the southwestern arm of NGC 3395; retain NGC 3395 |
| IC 3668 | Source identifies a part of NGC 4618; retain NGC 4618 |
| IC 3669 | Source identifies a part of NGC 4618; retain NGC 4618 |
| PGC 25886 | Automatic galaxy-score/size inclusion; no Pocket editorial reason |
| PGC 30484 | Automatic RC3 inclusion; no Pocket editorial reason |
| PGC 46039 | Automatic RC3 inclusion; no Pocket editorial reason |
| PGC 66669 | Automatic RC3 inclusion; no Pocket editorial reason |
| PGC 71943 | Automatic RC3 inclusion; no Pocket editorial reason |
| PGC 71948 | Automatic RC3 inclusion; no Pocket editorial reason |
| ESO 208-021 | Automatic galaxy-score/size inclusion; no Pocket editorial reason |
| ESO 221-026 | Automatic galaxy-score/size inclusion; no Pocket editorial reason |
| ESO 383-087 | Automatic galaxy-score/size inclusion; no Pocket editorial reason |
| IC 3322A | Automatic galaxy-score/size inclusion; no Pocket editorial reason |
| NGC 405 | Stellar identity; excluded from the DSO layer after importer correction |

No component photometry or dimensions are copied onto parent systems, and no
component is silently merged with its parent.

## D. Reviewed and left unchanged

- NGC 3247: OpenNGC places an H II region at a different position from the
  SIMBAD open-cluster identification. Keep the source's Bright Nebula identity
  pending separate investigation.
  [Published H II identification](https://academic.oup.com/mnras/article/411/2/705/1270241),
  [SIMBAD](https://simbad.harvard.edu/simbad/sim-id?Ident=NGC+3247).
- NGC 4496 / NGC 4496A: keep both current records rather than pretending that
  A is an exact alias of the projected pair. A and B are unrelated galaxies at
  different distances. The overlapping aggregate remains an explicit review
  case. [ESA/Hubble](https://esahubble.org/images/potw2209a/).
- ESO 121-006, Sculptor Dwarf / ESO 351-030, Fornax Dwarf / ESO 356-004:
  retain the existing selection, including the observer-useful nearby dwarfs.
- PGC 70070 / IC 5269B: retain and improve the displayed designation, rather
  than infer obscurity from a PGC name alone.
- IC 1396: no new Pocket inclusion. Its combined database representation has
  a 14-arcminute extent and aliases to larger/embedded nebular components;
  cluster-versus-whole-nebula identity and footprint need separate review.
- IC 443: retain its current Pocket exclusion; no completeness-based addition.
- Compact/faint paired systems such as NGC 756, NGC 2949, NGC 5256, NGC 6692
  and NGC 6825 remain selected. This pass corrects their metadata without
  inventing a new general group-selection threshold.
- Missing source constellation metadata for Mel 20 and IC 5269B remains visible
  as an empty index field; no inferred values were inserted into the source DB.
- M40 remains an existing forced Messier stellar entry; the DSO counts below
  exclude Star/Double Star records. NGC 2527 remains an unresolved H400 identity.

## Counts and reproducibility

The count uses `visible or forced`, matching the scene builder, and excludes
Star/Double Star types. The old Pocket report used `visible` alone and omitted
91 forced targets. Thus its 1238 total was an undercount; the comparable baseline
is **1329**, and the revised total is **1317**.

| Rendering family | Before | After |
| --- | ---: | ---: |
| Galaxy | 565 | 553 |
| Galaxy system family | 17 | 17 |
| Open cluster | 469 | 476 |
| Globular cluster | 115 | 115 |
| Planetary nebula | 78 | 78 |
| Bright nebula | 74 | 70 |
| Dark nebula | 2 | 2 |
| SNR | 4 | 4 |
| Other, including Star Cloud | 5 | 2 |
| **Total** | **1329** | **1317** |

The revised galaxy-system index labels are 14 Galaxy Pairs and 3 Galaxy Groups.
The Other family contains M73 and M24 (printed Star Cloud).

Reproduce imports and the normal selection report:

```sh
.venv/bin/python -m nightsky_atlas data import-openngc
.venv/bin/python -m nightsky_atlas data import-vizier-dsos
.venv/bin/python -m nightsky_atlas data selection-report --json build/research/pocket-dso-audit/current-selection.json
```

Local audit artifacts in `build/research/pocket-dso-audit/` contain the saved
baseline, full before/after JSON, selected-object CSV, edition deltas and check
logs. The old Pocket-only report and its local audit runner belong to this
historical snapshot; the supported command above reports current selection
across all editions and uses a different JSON schema.

Importer corrections are shared factual metadata. No Standard/Deep/Reference
selection rules are edited. Reimporting can nevertheless change their selected
objects through corrected types, aliases and compatible crossmatches; see the
local `summary.json` edition deltas. In particular, cluster corrections stop
some associated nebulae being identified with the cluster entry itself.

## Verification

Synthetic tests cover modern M102 identity, Serpens presentation, galaxy
system types, the cluster corrections, M24, NGC 405, preserved parent/component
identities, Pocket-only additions/exclusions, conflicting canonical aliases,
and forced-target report counts. No live catalogue download is required.

The full `make check` baseline already had 13 failures. The post-change full
check has the same 13 failures, no additional failures, and 1150 passing tests.
These concern existing edition/style expectations, observing-list assertions
and obsolete production-count expectations; full logs are local artifacts.

The focused importer/index/label/data-quality suite passes all 108 tests;
repository-wide lint passes.

A seven-chart proof covers P02, P05, P08, P13, P22, P23 and P40, with front
matter and index. Five existing layout violations remain in this subset;
this data-quality pass does not repair the label optimizer or make a publication
preflight claim.

## Files changed in this pass

- `src/nightsky_atlas/catalog/openngc.py`: source subtypes, reviewed type
  corrections, Messier and NGC/IC aliases, conflicting-alias guard.
- `src/nightsky_atlas/layout/dso_labels.py`: shared preferred observer designation.
- `src/nightsky_atlas/atlas/index.py`: scientific display types, Serpens and
  preferred catalogue designations.
- `src/nightsky_atlas/catalog/selection.py`: an accurate reason for general
  edition-designation exclusions.
- `src/nightsky_atlas/catalog/pocket_selection.py`: forced-target count parity
  with the scene builder.
- `config/observing_lists.yaml`: Pocket-only editorial exceptions and exclusions.
- `data/fixtures/observing_lists/nightsky_pocket_classics.json`: three additions.
- `data/fixtures/observing_lists/SOURCE.md`: curation provenance and Rosette note.
- `tests/catalog/test_pocket_dso_quality.py`: 39 synthetic quality tests.
- `tests/catalog/test_production_selection_policy.py`: Rosette display assertion.
- `docs/POCKET_DSO_AUDIT.md`, `docs/DATA_SOURCES.md`, `docs/STATE.md`: decisions,
  provenance and handoff.

The generated catalogue JSON/manifests and research/proof artifacts remain
local and untracked. Existing unrelated worktree changes were preserved. No
commit was created.
