# Architecture

Detailed architecture and engineering reference. `AGENTS.md` holds the
condensed, always-relevant rules; this document is the full contract for the
non-AI, non-catalogue subsystems. AI review design lives in
`docs/AI_REVIEW.md`; catalogue strategy and licensing in
`docs/DATA_SOURCES.md`.

## Pipeline

```text
source catalogues
      │
      ▼
normalised catalogue store
      │
      ▼
chart definition
      │
      ▼
scene builder
      │
      ▼
projected chart scene
      │
      ▼
initial layout engine
      │
      ▼
deterministic layout optimizer
      │
      ▼
layout document
      │
      ├──────────────► chart renderer ──────► vector PDF / PNG
      │
      └──────────────► review renderer ─────► PNG + annotated PNG
                                                │
                                                ▼
                                           AI reviewer
                                                │
                                                ▼
                                          permitted actions
                                                │
                                                ▼
                                        layout action engine
                                                │
                                                ▼
                                         revised layout
                                                │
                                                └──► render/review loop
```

The explicit **Layout Document** between astronomy and rendering is the
defining architectural difference from a simple catalogue-to-PDF renderer.

## Fundamental design law: immutable astronomy, mutable layout

This rule must never be weakened without explicit human approval.

### Immutable astronomical facts

Once imported and normalized, layout optimization and AI review may **not**
modify:

- object identity;
- right ascension, declination;
- source epoch;
- catalogue magnitude values;
- normalized display magnitude (except through an explicitly documented
  conversion algorithm);
- object type;
- major/minor angular dimensions;
- position angle;
- constellation membership derived from coordinates;
- catalogue identifiers;
- chart geometry;
- projection parameters.

### Mutable presentation state

The layout system may modify only explicitly permitted presentation properties,
for example:

- label candidate selection;
- label offset within a permitted range;
- label alignment;
- leader-line usage and route among allowed choices;
- display-name variant;
- label priority within predefined rules;
- optional-label visibility;
- collision-avoidance displacement for decorative elements.

AI output must never directly mutate astronomical objects.

## Core domain model

- `Star`, `DeepSkyObject`, `ConstellationSegment`, `ConstellationPolygon`,
  `NebulaOutline`, `MilkyWayContour` — normalized sky data with no page
  coordinates.
- `StarSystem` — a catalogued visual double/multiple system (WDS overlay):
  `primary_star_id`, `component_star_ids`, `is_multiple`, `separation_arcsec`,
  `position_angle_deg`, `component_magnitudes`, `combined_magnitude`,
  `source`/`source_id`, `visual_priority` and a `match_status`
  (`exact`/`positional`/`ambiguous`/`unmatched`). It links to stars by ID and
  never mutates them; only safe matches may affect the chart.
- `ChartDefinition` — what part of the sky to render. Fields:
  `id`, `center_ra_deg`, `center_dec_deg`, `width_deg`, `height_deg`,
  `projection`, `rotation_deg`, `atlas_id`, `neighbours`.
- `ChartScene` — astronomical content selected after projection:
  `definition`, `stars`, `deep_sky_objects`, `star_systems`,
  `constellation_boundaries`, `constellation_lines`, `constellation_regions`,
  `nebula_outlines`, `milky_way_contours`.
  Contains chart-plane coordinates but no final typesetting decisions.
  Constellation stick figures are **symbolic** connections, not physical great
  circles: the builder projects only their two endpoints and the renderer draws
  a straight segment in the chart plane. Constellation boundaries and nebula
  outlines are densified along RA/Dec before projection so they curve
  correctly. The renderer shortens a stick-figure end by the radius of the star
  symbol it meets plus `constellation.lines.star_gap_extra_mm`, so the line
  stops at the symbol edge rather than its centre.
- `DsoMetadata` (attached to each `SceneDso`) — atlas selection metadata:
  `list_memberships`, `visual_score`, `importance_score`, `render_priority`,
  `label_priority`, `forced`, `visible`, `visibility_reasons`. Observing-list
  membership and priorities are atlas metadata, so they never mutate
  `DeepSkyObject`.
- `ChartLayout` — architectural concept for a complete machine-readable page
  description: symbol positions
  and visual properties; label objects; selected candidate; text metrics; grid
  paths; borders; title; neighbour references; optional legend; diagnostics;
  optimizer metadata. Must be serializable; the serialized layout is a
  first-class build artifact. There is currently no `ChartLayout` Python class:
  layout state is carried by `Label`/`LabelCandidate`, optimizer results,
  `ChartPresentation`, `PageTransform` and `StyleConfig`, alongside `ChartScene`.
  `chart render --write-layout` serializes chart/label/optimizer diagnostics.

Whether a deep-sky object is *rendered* and whether it is *labelled* are
separate decisions. The scene builder consumes `select_dso`
(`catalog/selection.py`), combining per-type visibility, catalogue/curation rules,
forced lists and canonical-target edition inheritance. Preserve
Pocket ⊆ Standard ⊆ Deep = Eyepiece. Star/double-star catalogue entries are
excluded from the DSO layer. Visibility evaluators return deterministic
`VisibilityAssessment` (`visible`, 0-100 `score`, reasons). The label builder
then uses `label_priority` (observing-list bonus plus the catalogue ordering in
section 14.3) and lets the optimizer hide optional labels.


Chart CLI artifact layout (JSON/review files are opt-in; atlas builds always
write per-chart PDFs and optionally previews):

```text
build/standard/charts/standard-042/
    chart.json
    chart.pdf
    preview.png
    review.png
    review.json
```

## Coordinate and astronomy conventions

These rules are encoded in tests.

- **Units in names:** `ra_deg`, `dec_deg`, `major_axis_arcmin`,
  `position_angle_deg`; no ambiguous naked numeric angle fields. Astropy
  quantities may be used at catalogue/astronomy boundaries; the
  performance-critical internal representation uses documented numeric units.
- **Epoch:** J2000/ICRS-compatible chart coordinates. Proper motion is not
  required for the first atlas prototype.
- **Orientation:** conventional naked-eye chart orientation, **north up, east
  left**. No telescope-specific mirror/reversal modes in the MVP.
- **Projection:** stereographic initially (conformal locally, preserves
  recognizable patterns, suitable for modest fields, easy to test). Projection
  code is independent of the renderer so alternatives can be added later.
- **Page units:** physical millimetres/points. Critical dimensions must never be
  derived solely from screen pixels; PNG is a derivative review format.

## Configuration

- `atlas/*.yaml` controls content and tiling, including the per-edition
  `visibility:` limits used by the type-specific deep-sky selection.
- `styles/*.yaml` controls visual appearance.
- `config/observing_lists.yaml` controls observing-list selection policy
  (per-edition forced lists, priority weights, inheritance).  Membership data
  itself lives in `data/fixtures/observing_lists/`.
- Do not mix those concerns.
- YAML is schema-validated by typed pydantic models (`extra="forbid"`,
  frozen). Unknown keys fail fast; physical quantities carry explicit units in
  field names. Avoid arbitrarily nested dicts passed through the system.
- Visual constants belong in style configuration, not code.
- The AI configuration (`ai.yaml`) is separate; see `docs/AI_REVIEW.md`.

## Symbol rendering

Symbols are semantic, not arbitrary draw calls: `star`, `open_cluster`,
`globular_cluster`, `galaxy`, `planetary_nebula`, `bright_nebula`,
`dark_nebula`, `galaxy_cluster`.

- Star symbol size is a monotonic function of magnitude, configurable per
  style: distinct bright stars, printable faintest stars, no absurd discs,
  stable across PDF and PNG. Covered by reference tests.
- Extended deep-sky symbols use the catalogue angular extent where sufficiently
  reliable: galaxies keep major/minor axis and position angle; globular and open
  clusters use their catalogued diameter. The semantic shape represents the
  object type; the printed extent represents angular size. Missing or
  unreliable sizes fall back to the class-specific `fallback_diameter_mm`,
  floored by `min_diameter_mm` and capped by `max_diameter_mm` only where
  genuinely required. Large objects are not shrunk back to a fixed size.
- **Single source of truth:** all DSO symbol geometry is computed by
  `render/symbols.py:dso_symbol_extent`, returning a `SymbolExtent`
  (`width_mm`, `height_mm`, `radius_x_mm`, `radius_y_mm`, `rotation_rad`,
  `collision_radius_mm`). Rendering, debug exclusion zones, label exclusion and
  collision detection all consume that same extent; no parallel size
  computation is permitted. Per-class fallback/min/max rules live in the style
  (`dso.galaxy`, `dso.globular_cluster`, `dso.open_cluster`, ...) under
  `use_angular_size`, so a class is only switched to true scale after review.
- Schematic nebula outlines are implemented as projected/clipped vector paths
  from RA/Dec source geometry, never raster backgrounds. Milky Way contours use
  `catalog/milky_way.py` and `data/third_party/d3-celestial/mw.json`; the style's
  `milky_way` settings control the unlabeled background layer.
- Emphasized symbols (Messier, Herschel 400) use `dso.bold_line_width_mm` so the
  mark is bold wherever its label is. The renderer derives the set of bold
  targets from the labels' `font_weight`; it never re-derives catalogue facts.
- WDS remains an overlay on the normal star catalogue. Profile-specific
  separation/secondary-magnitude limits and a shared minimum separation of
  0.5 arcsec select pairs; no Δmag filter is applied. The projected
  page separation minus the two real rendered star radii classifies a selected
  pair as unresolved, marginal, or clearly resolved. Only an unresolved pair
  produces a combined-magnitude disk at the real primary position plus a short
  horizontal bar; linked component disks are suppressed for that representation.
  Marginal and resolved pairs keep their plotted base-star disks without a marker
  from that pair. Stored base-star positions and magnitudes are never mutated,
  WDS inserts no new star positions, and the bar does not encode position angle.
  Selection lives in `catalog/wds_selection.py`; page-scale classification and
  marker aggregation live in `render/double_stars.py`.

## Typography

- Accurate text metrics via Cairo + Pango/PangoCairo. Never place labels using
  approximate character widths.
- Renderer and collision system use the same metrics; bounds are available
  before rendering.
- Style configuration controls font family, size, weight, label category,
  object priority, spacing and halo/background strategy.
- Selected fonts must have appropriate redistribution/embedding rights.

## Label system

- Every label has a stable ID: `label:dso:NGC4565`, `label:star:HIP91262`,
  `label:constellation:VIR`. Stable IDs are mandatory for layout diffs, AI
  issue references, regression tests, manual overrides and reproducible
  optimization.
- Candidate placement uses standard compass positions `N NE E SE S SW W NW`,
  with explicit offsets from the anchor's exclusion zone and concentric rings.
  DSO leader-line candidates/routes are implemented in `layout/leader_lines.py`.
  Other custom/along-path candidates remain potential extensions.
- Priority is explicit, using understandable category weights plus local
  relevance (not a giant global magic-number list): major/common name, Messier,
  bright NGC/IC, prominent named star, ordinary NGC/IC, fainter optional DSO,
  minor star designation.
- Deep-sky label *text* is produced by a dedicated formatting layer
  (`layout/dso_labels.py`), never by rewriting catalogue data. A bare number
  means NGC (`NGC 4565` -> `4565`); IC renders compactly (`IC 3476` ->
  `I3476`); Messier takes priority over NGC/IC; other catalogues use short
  abbreviations (`Sh2-101`, `Cr399`, `B168`, `Mel111`, `Abell426`, `HCG92`).
  Common names are additional information and do not replace the designation.
- Deep-sky labels form a typographic hierarchy configured under
  `label.dso_labels`: Messier is bold at the normal size
  (`size_factor` 1.0), a non-Messier
  Herschel 400 object is bold at the normal size, ordinary objects are regular.
  Each `Label` carries its resolved `font_size_pt`/`font_weight`, so the
  renderer draws typography exactly as the layout specifies.
- Required deterministic collision checks: label vs label; label vs page
  border; label vs important star symbol; label vs DSO symbol; label vs its own
  exclusion zone; label vs title/metadata; leader line vs labels; leader line
  vs important symbols; excessive leader-line crossing. Grid lines have lower
  priority than labels and may be interrupted.

## Deterministic layout optimizer

The first complete layout is generated **without AI**. AI improves a usable
layout; it must not be required to make an otherwise broken page valid.

- **Hard constraints:** text outside printable bounds, severe label overlap,
  invalid candidate selection, references to missing elements, invalid
  geometry, overlapping mandatory page furniture. A page with unresolved hard
  violations fails validation.
- **Soft cost function** (separately measurable components, never an opaque
  single score): label-label overlap, label-symbol overlap, label distance from
  anchor, leader-line length, leader-line crossing, candidate preference,
  page-edge proximity, local crowding, visual imbalance.
- **Strategy:** priority-ordered greedy candidate selection, local improvement
  passes, deterministic conflict repair. Only add simulated annealing/CP-SAT if
  benchmark charts show a clear need; any stochastic algorithm must take and
  record an explicit seed.

Optimizer implementation boundaries:

| Responsibility | Entry/module | Regression tests |
| --- | --- | --- |
| Candidate generation and measured text | `labels.py`, `candidates.py` | `test_labels.py`, `test_candidates.py` |
| Cost formulas / source geometry | `scoring.py`, `association.py` | `test_scoring.py`, `test_association.py` |
| Spatial queries, static score cache, candidate validity | `placement.py` | `test_optimizer.py`, `test_spatial.py` |
| Ordered placement, local/joint/hard repair and leader decisions | `optimizer.py:optimize_labels` | `test_optimizer.py`, `test_leader_lines.py` |
| Association diagnostics and aggregate metrics | `diagnostics.py` | `test_optimizer.py`, `test_double_stars.py` |
| Leader route geometry / hard validation | `leader_lines.py`, `validation.py`, `collision.py` | `test_leader_lines.py`, `test_collision.py` |

The flow remains greedy → local repair → joint DSO search → hard repair →
stellar/DSO leader fallbacks → diagnostics → targeted leaders → final metrics.
Diagnostics feed the targeted leader phase; they are not a separate post-build
report. Placement dictionaries and spatial index insertion order are intentional.
Hard repair retains its bounded nested searches and shared closure state.

## Renderer

The renderer is intentionally boring. It accepts the scene, resolved labels,
transform, style and presentation, and draws their specified state. It must not
query catalogues, invent or move labels,
make content-selection decisions or change atlas geometry.

- Current outputs: vector PDF (retaining vector text/lines), PNG preview and
  annotated review PNG. SVG is not exposed by the current chart renderer.
- Reasons in physical page units (mm/points), never screen pixels alone.

## Manual overrides

Never patch renderer code for one troublesome object. Instead use an override
document:

```yaml
chart: standard-042
labels:
  label:dso:NGC4565:
    candidate: SW
    locked: true
```

Overrides are reviewable in Git, use stable element IDs, apply after initial
layout generation, and are respected by later optimizers when locked. They are
an escape hatch, not the primary layout method. Manual override details and the
current implementation live in `docs/STATE.md`.

## Atlas build phases

`build/atlas.py:build_atlas` retains the publication staging/swap boundary.
Its `_build_atlas_impl` plans charts, captures input provenance, prepares
details, composes main charts, appends details/editorial pages and writes
artifacts. `build/details.py` resolves detail profiles and prepares each layout
once, before main-chart fallback eligibility is determined. `build/document.py`
owns combined-PDF navigation, opening/overview pages, credits and directories.
Main workers write individual artifacts; only the parent composes the combined
PDF, consuming bounded spawned-worker results in chart order.

Build regressions live in `tests/build/`; `test_atlas_pipeline.py` checks detail
reuse and identical serial/parallel previews and page diagnostics.

## Validation

A chart is not publishable because it rendered successfully.

- **Structural:** unique IDs, finite coordinates, known object references,
  valid candidate selections, page dimensions, no missing required elements.
- **Geometry:** printable bounds, hard collisions, symbol dimensions, text
  metrics, grid clipping, neighbour references.
- **Atlas-level:** sampled coverage and neighbour-overlap checks are implemented
  in `atlas/tiling.py`; `atlas/report.py` reports coverage/density/navigation.
  `atlas validate` checks manifest/chart-list consistency and recorded artifact
  checksums. Ordinary validation may pass with recorded hard layout issues.
- **Publication preflight:** `build/preflight.py` and `atlas build/validate
  --publication` check complete chart sets, sampled coverage, catalogue/source
  checksums, current input fingerprints and zero hard layout issues. Builds use
  staging and retain the previous publication. Neither field acceptance nor
  legal redistribution permission is established by these checks.

## Testing strategy

Emphasize deterministic geometry, not just code coverage.

- **Unit tests:** coordinate conversion, stereographic projection, angular
  distance, chart clipping, magnitude-to-symbol mapping, ellipse orientation,
  label candidate generation, rectangle/path collision, cost components, AI
  action validation, serialization round trips.
- **Golden/reference tests:** a sparse chart, a crowded galaxy field, a dense
  star field. Compare layout JSON, object counts, key positions within
  tolerance, selected candidates and deterministic render metadata. Avoid
  fragile full-PDF byte comparisons; optional raster perceptual-diff later.
- **Property tests:** center of projection maps to chart center; projected
  coordinates stay finite in supported FOV; increasing faintness never
  increases star diameter; serialization preserves state; the hard validator
  never accepts out-of-page mandatory labels.

## Performance and caching

- One standard-density A4 chart should build interactively; deterministic
  layout takes seconds, not minutes. Parallelize by page only after single-page
  behavior is correct and measured. AI calls may later be parallelized within
  provider rate limits, but deterministic builds and cache behavior come first.
- Potential caches (later): catalogue query → scene; scene+style → initial
  layout; layout → preview; review-request hash → AI result; final layout →
  PDF page. AI responses should be replayable to avoid paying twice.
- Measured catalogue-query numbers and the decision to keep SQLite live in
  `docs/PERFORMANCE.md`.

## Logging and diagnostics

Build commands provide useful diagnostics without flooding output. Per chart:
stars/DSOs selected; labels requested, placed, hidden; hard violations; soft
cost before/after optimization; AI iterations and cost.

Debug mode can render bounding boxes, exclusion zones, candidate positions,
collision edges, label IDs and object IDs. These diagnostics are designed
early.

## Repository layout

```text
nightsky-atlas/
├── AGENTS.md              # condensed contract (read first)
├── README.md
├── pyproject.toml
├── Makefile
├── ai.yaml                # AI review config
├── src/nightsky_atlas/
│   ├── cli.py             # dispatch, chart and atlas commands
│   ├── cli_data.py        # catalogue command adapters
│   ├── catalog/           # models, store, tycho, openngc, constellations
│   ├── astronomy/         # angles, coordinates
│   ├── projection/        # base, stereographic
│   ├── chart/             # models (ChartDefinition, PageGeometry), page transform
│   ├── atlas/             # config, tiling
│   ├── scene/             # models, builder
│   ├── layout/            # models, labels, candidates, collision, scoring,
│   │                      # optimizer, overrides, validation
│   ├── render/            # cairo, symbols, text, grid, review
│   ├── review/            # models, schema, build
│   ├── ai/                # base, schema/actions, openrouter, recorded, loop,
│   │                      # benchmark, config, credentials
│   └── build/             # chart, atlas, details, document, preflight, progress
├── atlas/                 # main and experimental edition definitions
├── styles/                # matching edition/detail styles
├── config/                # observing policy and curated memberships
├── data/                  # raw/, processed/, fixtures/  (raw+processed ignored)
├── benchmarks/ai_review/
├── overrides/
├── tests/
├── docs/
└── build/                 # ignored build artifacts
```

Do not create empty packages speculatively. Add directories as milestones
require them.

## Python engineering rules

- Supported Python: **3.12+** (recorded in `pyproject.toml`).
- Type hints on public domain models and important pipeline interfaces; not
  maximal ceremony inside trivial local functions.
- Prefer standard dataclasses for internal immutable/simple domain models. Use a
  schema-validation library only where it clearly pays off: external
  configuration and external AI JSON. Avoid coupling every internal object to a
  validation framework.
- Formatting/linting baseline: **ruff**, **pytest**. Add a type checker once
  interfaces stabilize.
- Every new runtime dependency must justify itself. Likely justified: numpy,
  astropy, pycairo, PyGObject/Pango or equivalent, PyYAML, httpx (for
  OpenRouter). Do not add large scientific or web stacks for convenience.
