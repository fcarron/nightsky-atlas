# Project state

Handoff snapshot. The authoritative contract remains `AGENTS.md`; the granular
plan is `docs/DEVELOPMENT_PLAN.md`.

## Progress

- Targeted short DSO leaders (2026-10-07): the observer-reviewed rule is now
  configurable under `label.leader_lines.targeted_dso`, enabled for Pocket,
  Standard and Deep, including detail styles; Eyepiece remains disabled.
  All 615 main/detail pages were audited with unchanged label positions and
  source-association weight 20. Added lines: Pocket 5, Standard 2, Deep 2;
  zero new hard issue IDs. Existing issues remain 27/40/119 respectively.
  Local before/after proof and full audit are under
  `build/targeted-leaders-2026-10-07/`; methodology and small-sample limitations
  are in `docs/LEADER_LINE_EXPERIMENT.md`.

- Pocket DSO quality pass (2026-10-06): 1329 to 1317 selected DSO targets,
  counting both visibility passes and forced-list members. M102 and Rosette
  aliases, cluster/system types, M24 and printed Serpens abbreviations are
  corrected; 3 visual classics plus 1 recovered H400 alias target are added,
  and 16 component/specialist/stellar entries are removed from Pocket's DSO set.
  Seven-chart proof and full audit are in `build/research/pocket-dso-audit/`;
  decisions and remaining ambiguities are in `docs/POCKET_DSO_AUDIT.md`.

- M0–M14 complete. M15.1–M15.4 complete. M15.5 in progress (full current
  Standard build complete; field test remains).
- M16.1 complete (manual Stable-ID label overrides, including locked placements).
- M11.4 and M13.3 complete (live AI review through OpenRouter).
- Grid coordinate edge labels added (RA along top/bottom, Dec along left/right),
  configurable and independent of grid line spacing.
- Constellation stick figures (solid) and dotted IAU boundaries added, from a
  vendored BSD-3-Clause fixture. Stick figures are drawn as straight segments
  between the projected endpoint stars (no spherical interpolation), with a
  small gap at each star symbol; boundaries remain densified and curved.
- Bright-star gap fixed: the star store now merges Tycho-2 with the Hipparcos
  main catalogue, adding 1,319 stars that Tycho-2 omits (Deneb, Vega, Sirius,
  ...). Store count 2,539,913 -> 2,541,232.
- Schematic nebula outlines added (M19.1 partial): project-authored RA/Dec
  polygons for extended objects, projected/clipped as true vector paths and drawn
  as faint dashed strokes. First set is Cygnus-centred (Veil NGC6960/NGC6992,
  Pickering's Triangle NGC6979, North America NGC7000, Pelican IC5070); new
  `test-veil` test chart for the Cygnus Loop.
- Bright-star labels added (M9/M14 partial): stars brighter than magnitude 5.5
  with a common name or Bayer/Flamsteed/variable designation are labelled
  (`label:star:<id>`), names from the d3-celestial starnames fixture. Tycho-2
  now records its Hipparcos cross-ID (`hip_id`) so Tycho-stored stars resolve to
  names. Labels are optional (only the brightest named stars are mandatory), so
  the optimizer may hide them in crowded fields.
- Observing-list-driven DSO selection (M21.1–M21.4): deep-sky *rendering* and
  *labelling* now have separate priorities (`render_priority`, `label_priority`).
  Membership lives in `data/fixtures/observing_lists/` (Herschel 400 first,
  402 NGC designations, CC BY-SA 4.0) and never mutates `DeepSkyObject`.
  `config/observing_lists.yaml` declares forced lists and priority weights per
  edition; Standard forces the complete resolvable Herschel 400 into every chart.
- Deep includes 72 confirmed Abell planetary-nebula targets, including objects
  without imported magnitude/size. The selection membership takes unflagged
  Abell rows plus the independently confirmed Abell 21 exception; possible or
  misclassified rows are not added wholesale.
- A source-neutral external observing-list audit is available under
  `nightsky research observing-list-coverage`. It reads local AstroPlanner
  CSV/TSV/text exports and normalized Astronomical League CSV/TSV/text, then
  reports designation matches, physical-target deduplication, production
  selection by edition, provenance families and unresolved review cases.
  NSOG/AL list content remains user-supplied and gitignored; this is a validation
  tool, not a production inclusion source. See
  `docs/EXTERNAL_OBSERVING_LISTS.md`.
- Deep's first NightSkyAtlas-owned visual-nebula curation is active: 45 dark
  target entries (47 object IDs, including selected LDN targets) and 42 bright
  nebula/SNR IDs. Dark targets render as position markers only; ambiguous LDN
  534 remains excluded and LDN 93 uses the B 86 locator. See
  `docs/NEBULA_CURATION_V1.md`; the curated memberships contain no NSOG ratings
  or descriptions.
- Per-type DSO visibility (M21.4): `catalog/visibility.py` evaluates each object
  type from integrated magnitude, derived mean surface brightness and angular
  size. Galaxies are surface-brightness limited, clusters use size/magnitude,
  planetary nebulae are magnitude-limited with no size penalty, and star /
  double-star entries are excluded from the DSO layer. Limits live in the atlas
  `visibility:` block (Standard default: 8-10 inch dark sky, integrated
  magnitude limit 13.5, surface-brightness limit 23.5, min axis 1.5 arcmin);
  forced observing-list members override.  Faint DSOs beyond the style's
  `dso_label_magnitude_limit` (12.5) are rendered without a label; mandatory
  labels and observing-list members stay labelled.
- DSO label formatting and hierarchy: a presentation-only layer
  (`layout/dso_labels.py`) renders catalogue identifiers compactly without
  touching the data model. The NGC prefix is dropped (a bare number means NGC,
  `NGC 4411B` -> `4411B`), IC renders as `I3476`, Messier wins over NGC/IC, and
  other catalogues use short abbreviations (`Sh2-101`, `Cr399`, `B168`).
  Typography lives under `label.dso_labels`: Messier bold at 1.0x, non-Messier
  Herschel 400 bold at normal size, ordinary objects regular. Each `Label`
  carries resolved `font_size_pt`/`font_weight`; common names no longer replace
  the designation. The corresponding deep-sky *symbol* is drawn with the heavier
  `dso.bold_line_width_mm` whenever its label is bold, so the map mark matches
  the name.
- Visual double/multiple stars (M22): the Washington Double Star Catalog
  remains an overlay on the base star catalogue (`catalog/wds.py`,
  `data/processed/double_stars/wds.json`). `StarSystem` retains WDS pair and
  component designations, magnitudes, separation and position angle; only
  `exact`/`positional` matches influence the chart. Pocket/Standard/Deep
  secondary-magnitude and separation rules plus the optional Δmag sanity filter
  are configured in each style. The projected pair clearance is measured from
  the two rendered symbol radii. An unresolved pair receives one horizontal
  marker on its real rendered primary; marginal and clearly resolved pairs do
  not receive a marker merely for being listed as a pair. WDS never inserts,
  moves, combines, or changes the magnitude of a base-catalogue star.
- Central DSO symbol extent: `render/symbols.py:dso_symbol_extent` is now the
  single source of DSO symbol geometry, returning a `SymbolExtent`
  (width/height/radii/rotation/collision radius). Globular and open clusters use
  the catalogue angular size (like galaxies) instead of fixed ~1.4 mm marks;
  galaxies still preserve axis ratio and position angle. Missing/unreliable
  sizes fall back to per-class `fallback_diameter_mm`, floored by
  `min_diameter_mm` and capped by `max_diameter_mm` only where required.
  Planetary nebulae now use reliable angular sizes too (with a 1.4-mm Standard
  fallback); remaining extended classes retain configured semantic fallbacks
  until better outline data exists. Renderer, debug zones,
  label exclusion and collision detection all consume the same extent. Config
  lives under `dso.<class>` in `styles/standard.yaml`.
- Deterministic label selection and central priorities: `catalog/priority.py`
  is the single priority scale (Messier, common name, prominent/other Herschel
  400, important NGC/IC, ordinary DSO; star name > bright Bayer main star >
  Bayer/Flamsteed > variable). `layout/selection.py` runs before placement:
  semantic de-duplication (one primary label per printed name, keeping the
  higher priority then brighter target) plus a local density selection that
  always keeps high-tier labels and thins medium/low labels by printed label
  area within `label.selection.density_radius_mm` (15 mm). A merely bright DSO
  is now high priority but not mandatory, so the optimizer hides it rather than
  forcing a collision. Standard Virgo (`standard-053`) drops from 211 labels to
  81 with 0 hard violations; `standard-109` also reaches 0. `standard-110`
  (LMC) keeps one known `label_dso` overlap where the mandatory LMC label has
  no valid candidate in the dense field. Review previews for the acceptance
  fields: `build/label-selection/standard/charts/{standard-001,021,031,053,
  063,083,116}/preview.png`.
- Standard detail-map label fallback is enabled for Virgo core (`SD053A`),
  southern Virgo (`SD053B`) and Fornax (`SD089`). An ordinary galaxy number is
  omitted from the parent only when that stable DSO ID has a placed, hard-clean
  label on the detail page. Symbols remain on both pages; Messier and H400
  labels remain on the parent. The build manifest records omitted label IDs by
  parent chart and detail code.
- Pocket uses the same three label-transfer fields on `P025` and `P032`, with
  compact parent-frame tags (`PD025A`, `PD025B`, `PD032`) to fit the smaller
  field footprints.
- Deep now has nine detail maps: NGC 7331/Stephan's Quintet, Pleiades, Coma
  core, Markarian chain, M42, Fornax core, 30 Doradus, LMC bar and NGC 346.
  Its ordinary-galaxy label fallback is limited to the four galaxy fields,
  catalogue magnitude 12.5 or fainter, and three neighbouring galaxies within
  15 mm on the parent. The detail label must still be placed and hard-clean;
  Messier and H400 labels remain on the parent. Printed detail scale bars fit
  their actual magnification.
- A standalone local blind-review tool for label variants lives in
  `tools/label_review/`. Its curated 23-case set uses crops from assembled
  Pocket, Standard and Deep atlas pages (14 changed areas, 9 identical
  controls); five dense pairs are preference-only because clicks cannot
  distinguish overlapping symbols. The original three-case pilot and its
  answers remain separate. The app records clicks and preferences append-only
  under `build/label-review/`; it does not invoke the optimizer or alter
  production inputs. See its README for startup and interpretation limits.
- Distant deep-sky labels can now carry a serialized leader-line state. The
  optimizer enables it only for legal far-ring placements; AI may request it
  for an individual DSO label, subject to the same deterministic route and
  hard gate. Vector PDF and PNG draw the same resolved segment.
- Footer/navigation: chart title is 8.5 pt with a bold chart code, and
  neighbour navigation is 7.5 pt with a bold code. E/W references are rotated
  along the narrow side margin so they stay outside the chart field without
  colliding with the Dec labels; N/S remain outside the top/bottom frame.
- Whole-sky overview pages and optional locator inset: `atlas/overview.py`
  builds a pole-centred azimuthal equidistant hemisphere map (simplified
  constellation lines/boundaries drawn as straight chords, a light RA/Dec grid,
  bright stars down to `overview.star_limit_magnitude`, and one trapezoidal
  declination-ring / RA-sector **cell** per Standard chart with the printed
  chart code at its centre); new `projection/azimuthal.py` supplies the
  projection.  Each chart contributes exactly one cell boundary, so overlapping
  chart fields never tangle the index.  `render/overview.py` draws the
  front-of-atlas north/south pages (after the front matter, controlled by
  `style.overview.enabled` / `atlas build --no-overviews`) and the compact
  per-chart locator inset (`style.locator.enabled`, default off; current cell
  dark, neighbours mid-grey).  Constellation full names come from the IAU
  abbreviation registry in `catalog/constellations.py`. Manifest records
  `overview_pages` with `star_count`.
- Deterministic atlas index: appended vector index pages contain canonical DSO
  designations, type, constellation and primary/secondary chart codes, plus a
  footprint-derived constellation index. Index entries are generated only from
  the edition's rendered/forced objects; no manual object list is maintained.
- Label/constellation-line geometry is centralised: line intersections and a
  0.4-mm safety margin contribute soft cost; final stick-figure segments are
  knocked out beneath labels when necessary. Grid and astronomical geometry are
  unchanged.
- AI review now receives candidate directions, distance steps, local fine-adjust
  radius and constellation-line conflict metadata. `move_label` expresses
  direction/distance intent; `fine_adjust_label` snaps to a deterministic
  0.5-mm grid within +/-3 mm and passes the normal hard gate. Leader-line and
  display-name actions remain deliberately unavailable until their presentation
  state exists.
- Pocket, Standard and Deep presets use P/S/D chart codes, edition-specific DSO
  visibility and star-size curves. Deep's stellar limit is 10.5; the complete
  Pocket, Standard and Deep builds are in
  `build/complete-2026-10-07/`. Field testing remains.
- Chart pages now show subdued constellation names. Front matter records frame,
  projection and scale and has an expanded observing-symbol key.
- `make check`: Ruff clean, 677 tests passing.
- Standard v0.3 full-sky tiling (draft): explicit declination rings every
  16 deg (-72 ... +72), stereographic polar caps, RA staggering, frozen
  config-driven counts.  Ordering is north-to-south (reading order):
  `standard-001` north cap, then +72 ... -72 rings each sorted by RA (0h -> 24h),
  `standard-118` south cap.  The requested 14/13/11/8/5 per hemisphere does not
  cover; the frozen minimum that passes a 0.25 deg sweep and is mirror-symmetric
  north/south is `10/9/12/13/14/14/13/12/9/10` -> **118 charts**.  Numeric
  coverage at 0.5 deg: 0 gaps, overlap 1..4; 629 N/S/E/W neighbour pairs, 0
  without overlap.  Tiling code: `atlas/tiling.py`; draft report: `atlas/report.py`.

## Frozen Standard geometry (M14.1)

- Page A4 landscape 297 x 210 mm, margin 12 mm (printable 273 x 186 mm).
- Field 27 x 18.5 deg, ~10.05 mm/deg, stereographic, north up / east left.
- Stellar limit magnitude 9.0; deep-sky selection is per-type (8-10 inch dark
  sky: integrated magnitude 13.5, surface brightness 23.5, min axis 1.5 arcmin).
  There is no global deep-sky magnitude cut in the atlas config; per-type
  visibility is the only production path.
- Tiling (Standard v0.3): declination-ring tiling, ring step 16 deg, nominal
  vertical overlap 2 deg, staggered RA, stereographic polar caps; mirror-
  symmetric frozen counts `10/9/12/13/14/14/13/12/9/10` (south->north) ->
  **118 charts**, ids `standard-NNN` numbered north-to-south, N/S/E/W neighbour
  references (caps have no E/W).
- Coverage: 0 gaps at 0.5 deg sampling, overlap 1..4, 259,200 samples.
- Star style: min 0.2 / max 2.4 mm, bright magnitude 0.0 / faint magnitude 9.0.
- Label candidates: 3 concentric rings, ring gap 3.0 mm.
- Grid labels: RA/Dec lines every 2 deg, but coordinate *labels* are a sparser
  layer: every second line (`label_ra_step_deg`/`label_dec_step_deg` 4 deg),
  a physical minimum spacing of 13 mm (`label_min_spacing_mm`) that drops
  crowded labels on the same page edge, and a 30 deg RA label step on polar
  charts (`label_polar_ra_step_deg`).  Drawn as furniture outside the frame
  (`grid.label_placement: outside`), beneath sky labels.  ~48% fewer coordinate
  labels than the every-line v0.1 draft.

## Data

- Tycho-2 (CDS I/259), **CC-BY-NC-3.0 IGO** (non-commercial). `data/raw/tycho2` + SQLite store.
- Hipparcos main catalogue (CDS I/239), **CC-BY-NC-3.0 IGO**, bright-star
  supplement: `data/raw/hipparcos/hip_main.dat` (118,218 records). Merged into
  the store with a 3 arcsec positional match (Tycho-2 wins); 1,319 stars added.
  Store: 2,541,232 stars (2,539,913 TYC2 + 1,319 HIP).
- OpenNGC, **CC-BY-SA-4.0**. Processed JSON, 13,372 objects.
- Constellation geometry: Stellarium Western (Sky & Telescope) stick figures,
  **CC BY-SA 2.0**, pinned at `014fbb5e59233d133c22f9811af96b67d05a95c9`;
  d3-celestial (Olaf Frohn)
  IAU boundary polygons, **BSD-3-Clause**. Vendored as
  `data/fixtures/constellations/{constellations.lines,constellations.bounds}.json`
  with `LICENSE`, `SOURCE.md` and a line-data manifest. 88 stick figures + 785
  deduplicated boundary segments.
- Schematic nebula outlines: project-authored (proprietary), vendored as
  `data/fixtures/outlines/nebulae.json` with `SOURCE.md`. 5 Cygnus-region outlines;
  stable IDs `outline:dso:<dso_id>`.
- Star names: d3-celestial, **BSD-3-Clause**, vendored as
  `data/fixtures/starnames/starnames.json` with `LICENSE` and `SOURCE.md`.
  ~4,600 Hipparcos stars keyed by Hipparcos number. The store records a
  `hip_id` cross-ID (121,059 rows) so Tycho-stored stars resolve to names.
- Observing lists (atlas metadata, not astronomy): Herschel 400, from Wikipedia
  (*Herschel 400 Catalogue*, revision 1369720351), **CC BY-SA 4.0**, vendored as
  `data/fixtures/observing_lists/herschel400.json` with `SOURCE.md`. 402
  normalized NGC designations; nine have no OpenNGC match (documented in
  `SOURCE.md`). Policy in `config/observing_lists.yaml`.
- Git-ignored: `data/raw/`, `data/processed/`, `build/`, `.env`, `benchmarks/ai_review/generated|results/`.

## AI review

- Default model `qwen/qwen3.7-flash`; `min_action_severity: 6`; key in git-ignored `.env` (`OPENROUTER_API_KEY`).
- Benchmark: 12 cases, schema compliance 1.00, detected 118/556, 40 false positives, $0.0073.
- Replay via `RecordedReviewer`; the loop records per-iteration layout hashes, review results and cost.
- Review requests list each label's available ring-0 candidates and only
  advertise actions the layout model can honour.  `apply_review_actions` repairs
  an unavailable/colliding `select_candidate` to the label's cheapest hard-clean
  candidate, and the optimization loop requires the soft cost not to increase,
  so an AI pass cannot degrade a page (live S044: optimized page unchanged at
  cost 250.6; raw page improved monotonically 11854 -> 3703).

## Full-sky Standard v0.2 draft

- `build/fullsky-v0.2/standard/atlas.pdf` (116 charts + front matter, 8.7 MB),
  per-page artifacts under `build/fullsky-v0.2/standard/charts/<id>/`
  (`chart.pdf` + `preview.png` at 100 dpi), `manifest.json` (with per-chart
  neighbours and frozen tiling) and `draft-report.json`.
- Order: north-to-south.  `standard-001` north cap, then +72 ... -72 rings each
  sorted by RA, `standard-116` south cap.
- Build result: 116 charts, **2 hard violations** (LMC field: `standard-109`,
  `standard-110`), 0 coverage gaps (259,200 samples at 0.5 deg), overlap 1..4,
  all 458 neighbour pairs overlap.
- Density: DSO mean 52 (max 255, `standard-053` Virgo; min 9), label mean 59
  (max 211), star mean 1,569 (max 3,467). Densest pages flagged in the report.
- Region review list: Virgo `standard-053`, Cygnus `standard-031`, Sagittarius
  `standard-084`, Orion `standard-063`, LMC `standard-110`, SMC `standard-108`,
  poles `standard-001` (north) / `standard-116` (south).

## Alpha artifacts (M15.5)

- Complete edition builds with 100-dpi page previews: `build/complete-2026-09-29/pocket/`
  (48 main + 3 detail charts, 32 hard issues) and
  `build/complete-2026-09-29/standard/` (118 main + 9 detail charts, 42 hard
  issues). Both atlas-level coverage reports show 0 gaps. Pocket's three
  detail-map galaxy-label fallbacks omit 3 numbers on P025 and 6 on P032;
  Standard omits 35 on S053 and 16 on S089. Both generated outputs pass
  `nightsky atlas validate`.
- Deep with nine detail maps: `build/complete-2026-09-30-deep-details-v3/deep/`
  (430 main + 9 detail charts, 65 hard issues). The four marked galaxy fields
  omit 5 numbers on D105, 23 on D121, 14 on D174 and 3 on D328, all backed
  by placed detail labels. Atlas output validation passes. Three of the hard
  issues are on detail pages: one M45 enclosing-cluster collision and one LMC
  enclosing-region collision on each of DD405A and DD405B.
- A bounded S053/D174 leader-line experiment is documented in
  `docs/LEADER_LINE_EXPERIMENT.md`. Allowing more distant DSO
  line candidates changed only three small areas on the two finished parent
  maps, without a clear print-scale legibility gain. The active 2.5-mm
  candidate limit remains unchanged; broader use awaits observer comparison.

- Rebuilt with grid labels + constellations: `build/standard/atlas.pdf` (135 charts
  + front matter), per-page artifacts under `build/standard/charts/<id>/`, and
  `build/standard/manifest.json`. Still 14 hard violations on 6 dense pages.
- Earlier pre-grid/constellation alpha: `build/standard-alpha/standard/atlas.pdf` (9.2 MB).
- Per-page `build/standard-alpha/standard/charts/<id>/chart.pdf` and `preview.png`.
- `build/standard-alpha/standard/manifest.json` with per-page diagnostics, limits and data-source manifests.
- 5,061 / 5,622 labels placed.
- Test-page previews (no AI, deterministic optimizer): `build/testpages/standard/charts/{test-virgo,test-cygnus,test-veil,test-sparse}/`.
- `test-orion` (RA 83.5, Dec -1.0) is an explicit test chart for the double-star
  overlay (belt/sword, Rigel, Alnitak, Mintaka); render it with
  `nightsky chart render --chart test-orion --star-store ... --optimize`.

## Open issues

- The complete current 118-chart Standard build is at
  `build/complete-2026-09-29/standard/`; its 42 hard layout issues are recorded
  per page in the manifest. `standard-035` and the LMC pages remain the largest
  known problem areas.
- M15.5 remains a human checkpoint: print Orion, Cygnus, Virgo/Coma,
  Sagittarius and polar pages at 100% and use them under red light / at the
  telescope before treating Standard as publication-ready.
- M16.3 is implemented: `atlas build --publication` rejects subsets, coverage gaps,
  missing/empty core catalogues and source manifests whose processed checksum
  does not match. Code/config/geometry fingerprints and catalogue hashes are
  checked again after rendering. Publication is staged, and a previous output
  is retained on success or left untouched on failure. `atlas validate
  --publication` independently checks the finished manifest, inputs, chart set,
  hard-issue totals and output file checksums. The current complete Standard
  build passes ordinary atlas validation; the M15.5 field test remains.

- The alpha artifacts predate the Hipparcos bright-star supplement and must be
  rebuilt before the M15.5 field test; the regenerated `test-cygnus` test page
  already includes Deneb.
- Label prioritisation/selection in dense fields is implemented (see Progress),
  but dense-page conflicts remain in the full builds. Pocket reports 32 hard
  issues, including 14 on `pocket-026` and 7 on `pocket-025`. Standard reports
  42, including 11 on `standard-035`, 7 each on `standard-110` and `standard-111`,
  and 4 on the Pleiades detail page. Per-page diagnostics are in the respective
  manifests; the earlier alpha's 14 issues belong to superseded geometry.
- The 118-chart count is geometry-driven: a coverage sweep at 0.25 deg fixed the
  minimum counts, constrained to be mirror-symmetric north/south; the requested
  14/13/11/8/5 per hemisphere leaves gaps. A later
  optional pass may nudge individual chart centres by +-1-2 deg or move important
  regions away from page edges; the draft deliberately uses a clean geometric
  grid only.
- Polar pages reuse the standard field and stereographic projection; coverage is
  complete but distortion near the pole is larger. The dec-parallel sampling bug
  (chords across the pole) is fixed, so the parallels form clean concentric
  circles. Fields whose near declination edge reaches the pole (`grid` detects
  this from the chart geometry) are now drawn with the dedicated polar grid:
  meridians as projected great-circle arcs converging on the pole image, filtered
  to those crossing the frame, at the coarser `grid.polar_ra_step_deg` (10 deg by
  default) instead of `ra_step_deg`, with RA labels picked up by the normal edge
  label pass.  The former open item (dense meridian fan) is now handled by
  `label_polar_ra_step_deg` (30 deg) and the physical minimum label spacing.
- The alpha manifest predates the first git commit, so its `git_commit` is null; a rebuild records the real commit.
- WDS overlay markers are now filtered by atlas profile and printed map scale;
  `visual_priority` and per-chart caps remain possible later refinements.
- Coordinate labels: the v0.2 thinning (4 deg label step, 13 mm minimum
  spacing, 30 deg polar RA label step) resolved the "every 8 minutes" density
  from the v0.1 draft; no follow-up needed unless field testing disagrees.

## CLI

`data fetch-stars|import-stars|fetch-hipparcos|fetch-openngc|import-openngc|fetch-wds|import-wds`,
`chart render|validate|review|magnitude-scale`,
`atlas tile|coverage|report|build`,
`benchmark ai-review`.

`chart render|validate|review` and `atlas build` accept `--overrides PATH`
(a single override file or a directory of them), `--constellations DIR`
(default `data/fixtures/constellations`; point elsewhere or leave empty to omit)
and `--outlines DIR` (default `data/fixtures/outlines`; empty to omit) and
`--star-names DIR` (default `data/fixtures/starnames`; empty to omit). DSO
selection additionally accepts `--observing-lists DIR` (default
`data/fixtures/observing_lists`; empty to omit) and `--observing-config PATH`
(default `config/observing_lists.yaml`). Double stars accept
`--double-stars PATH` (default `data/processed/double_stars/wds.json` when
present) and `--double-star-match-tolerance-arcsec` (default 2.0 primary
tolerance; the companion tolerance is 3.0 arcsec inside the builder).

## Manual overrides (M16.1)

- `overrides/<chart>.yaml` with `chart:` and stable-ID `labels:` entries
  (`candidate`, `locked`, `hidden`). Example: `overrides/test-virgo.yaml`.
- Applied after initial label layout; locked placements are preserved by the
  deterministic optimizer and by AI action application.
- Unknown label IDs or invalid candidates are hard errors; invalid locked
  geometry is honoured but reported by validation.

## Next

1. M15.5 print/field test of representative pages.
2. M16: M16.2 atlas-wide issue report, M16.3 preflight (`atlas validate --publication`), M16.4 `docs/DATA_SOURCES.md`.
3. M21.5 integrate further observing lists (license decision first). The
   per-chart label density budget is implemented as local density selection.
4. M17 Pocket, M18 Deep data expansion, M19 extended structures, M20 Deep atlas.
