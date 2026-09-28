# Project state

Handoff snapshot. The authoritative contract remains `AGENTS.md`; the granular
plan is `docs/DEVELOPMENT_PLAN.md`.

## Progress

- M0–M14 complete. M15.1–M15.4 complete. M15.5 in progress (a full current
  Standard rebuild and field test remain).
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
- Pocket and Deep presets are implemented with physical 10-mm overlap targets,
  P/S/D chart codes, edition-specific DSO visibility and star-size curves.
  Representative renders exist; do not build the complete Deep atlas yet.
- Chart pages now show subdued constellation names. Front matter records frame,
  projection and scale and has an expanded observing-symbol key.
- `make check`: Ruff clean, 677 tests passing.
- Standard v0.2 full-sky tiling (draft): explicit declination rings every
  16 deg (-72 ... +72), stereographic polar caps, RA staggering, frozen
  config-driven counts.  Ordering is north-to-south (reading order):
  `standard-001` north cap, then +72 ... -72 rings each sorted by RA (0h -> 24h),
  `standard-116` south cap.  The requested 14/13/11/8/5 per hemisphere does not
  cover; the frozen minimum that passes a 0.25 deg sweep is
  `8/9/12/13/14/14/13/12/9/10` -> **116 charts**.  Numeric coverage at 0.5 deg:
  0 gaps, overlap 1..4; 458 N/S/E/W neighbour pairs, 0 without overlap.  Tiling
  code: `atlas/tiling.py`; draft report: `atlas/report.py`.

## Frozen Standard geometry (M14.1)

- Page A4 landscape 297 x 210 mm, margin 12 mm (printable 273 x 186 mm).
- Field 27 x 18.5 deg, ~10.05 mm/deg, stereographic, north up / east left.
- Stellar limit magnitude 9.0; deep-sky selection is per-type (8-10 inch dark
  sky: integrated magnitude 13.5, surface brightness 23.5, min axis 1.5 arcmin).
  There is no global deep-sky magnitude cut in the atlas config; per-type
  visibility is the only production path.
- Tiling (Standard v0.2): declination-ring tiling, ring step 16 deg, nominal
  vertical overlap 2 deg, staggered RA, stereographic polar caps; frozen counts
  `8/9/12/13/14/14/13/12/9/10` (south->north) -> **116 charts**, ids
  `standard-NNN` numbered north-to-south, N/S/E/W neighbour references (caps
  have no E/W).
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

- Re-run the complete 116-chart Standard build after `d915a6c`; the prior run
  stopped at `standard-036` on an unrendered WDS component, now covered by a
  regression test. `standard-036` itself rebuilds with zero hard issues.
- M15.5 remains a human checkpoint: print Orion, Cygnus, Virgo/Coma,
  Sagittarius and polar pages at 100% and use them under red light / at the
  telescope before treating Standard as publication-ready.
- M16.3 is implemented: `atlas build --publication` rejects subsets, coverage gaps,
  missing/empty core catalogues and source manifests whose processed checksum
  does not match. Code/config/geometry fingerprints and catalogue hashes are
  checked again after rendering. Publication is staged, and a previous output
  is retained on success or left untouched on failure. `atlas validate
  --publication` independently checks the finished manifest, inputs, chart set,
  hard-issue totals and output file checksums. A complete real-data Standard
  build remains the M15.5 field-test prerequisite.

- The alpha artifacts predate the Hipparcos bright-star supplement and must be
  rebuilt before the M15.5 field test; the regenerated `test-cygnus` test page
  already includes Deneb.
- Label prioritisation/selection in dense fields is implemented (see Progress),
  which resolved the `standard-109` violation and the Virgo density problem.
  One known hard violation remains on `standard-110` (LMC): the mandatory
  large-Magellanic-Cloud label has no valid candidate among the configured
  candidate rings in that dense field. Options are more mandatory candidate
  rings or a curated override; the earlier alpha's 14 hard violations on
  standard-007/008/009/020/059/060 belong to the superseded 135-chart band
  tiling and numbering, not the v0.2 ring tiling.
- The 116-chart count is geometry-driven: a coverage sweep at 0.25 deg fixed the
  minimum counts; the requested 14/13/11/8/5 per hemisphere leaves gaps. A later
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
