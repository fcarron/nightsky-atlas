# AGENTS.md — NightSky Atlas

> **Purpose:** Generate publication-quality printable star atlases for visual
> deep-sky observing, especially Dobsonian star-hopping.
> **Output:** vector PDF, PNG preview, annotated review PNG, optional layout JSON.
> **Language:** Python 3.12+. Main and experimental editions: see §10.
> Standard alpha field review remains in progress.
> Authoritative engineering contract for coding agents; keep it lean,
> push detail to `docs/`.

## Documentation map

| Document | Contents |
| --- | --- |
| `docs/PRODUCT.md` | Vision, non-goals, user, quality bar, MVP/RC, deferred features |
| `docs/ARCHITECTURE.md` | Full domain model, subsystem design, conventions, Python rules |
| `docs/DEVELOPMENT_PLAN.md` | Milestones, acceptance criteria, human checkpoints |
| `docs/STATE.md` | Current progress, frozen geometry, artifacts, open issues |
| `docs/DATA_SOURCES.md` | Catalogue strategy, storage, licensing, provenance |
| `docs/GALAXY_VISIBILITY.md` | Crumey-based galaxy visibility model, heuristics, contour classes |
| `docs/CARTOGRAPHY.md` | Standard page/field/tiling design and coverage |
| `docs/AI_REVIEW.md` | Review rendering, AI architecture, loop, cost, benchmark |
| `docs/PERFORMANCE.md` | Catalogue-query benchmarks and storage decisions |

---

## 0. How an agent must work in this repository

Read this file before changing code; it is the authoritative contract.

**0.1 Follow the user's task.** When the user provides an explicit task, follow
that task. Do not independently select another milestone from the development
plan. Only use the next unfinished milestone as the default when no specific
task has been provided; its dependencies must be complete.

Implement only the agreed scope, run relevant checks and fix task-caused
failures. Update relevant documentation and milestone status only when supported
by evidence. Summarize files changed, checks and unresolved issues.

For implemented behavior, code, validated configuration and tests take precedence
over historical documentation. `docs/STATE.md` includes older snapshots. Report
conflicts; do not change production behavior merely to match stale documentation.

**0.2 Do not silently redesign the architecture.** If a task seems to require
violating a rule here, explain the conflict, propose the smallest architecture
change, and wait for human approval.

**0.3 Prefer simple code over premature framework building.** No web framework,
GUI, distributed jobs, message queue, large ORM, Kubernetes, plugin framework or
DI container. This is a local CLI publishing tool. Do not create empty packages
speculatively.

**0.4 Reproducibility is mandatory.** Given the same catalogue versions, atlas
definition, style, seed, optimizer version and AI decisions, the layout and PDF
must be identical. Any stochastic algorithm must accept and record an explicit
seed.

**0.5 Change hygiene.** Do not commit unless explicitly asked. Never commit
secrets or large generated catalogues. Preserve existing unrelated worktree
changes. Prefer repository commands (`make check`) and checks appropriate to the
task. Do not add code comments unless asked.

## 1. Product vision

Beautiful, practical paper charts for use at a telescope. Functional quality
inspired by Pocket Sky Atlas / Sky Atlas 2000.0 / Uranometria 2000.0; visual
design must not copy any existing atlas. The main editions are **Pocket**,
**Standard** and **Deep**. **Eyepiece** and **Eyepiece Deep** are experimental
presets, not release editions. See `docs/PRODUCT.md`.

## 2. Non-goals

Not a planetarium, telescope control, session planner, SkySafari replacement,
photographic simulator, real-time renderer, GIS or web-first app. Do not
distort the architecture for hypothetical reuse. Full list: `docs/PRODUCT.md`.

## 3. Primary user and field-use requirements

A visual Dobsonian observer. Optimize for star-hopping, pattern recognition,
low-light readability, unambiguous labels, useful DSO selection, predictable
overlap, rapid page navigation, print quality, restrained colour, red-light
robustness. A correct but cluttered chart is a failure. Details:
`docs/PRODUCT.md`.

## 4. High-level architecture

```text
catalogues → normalised store → chart definition → scene builder
  → projected scene → initial layout → deterministic optimizer → layout document
       ├─ chart renderer ─► vector PDF / PNG
       ─ review renderer ► PNG + annotated PNG → AI reviewer
            → permitted actions → layout action engine → revised layout → loop
```

The explicit **Layout Document** between astronomy and rendering is the
defining architectural difference from a catalogue-to-PDF renderer. Module map:
`docs/ARCHITECTURE.md`.

## 5. Fundamental design law: immutable astronomy, mutable layout

Never weaken without explicit human approval.

**5.1 Immutable astronomical facts** — once imported/normalized, optimization
and AI may not modify object identity; RA/Dec; source epoch; catalogue and
normalized display magnitude (except via documented conversion); object type;
major/minor angular dimensions; position angle; coordinate-derived constellation
membership; catalogue identifiers; chart geometry; projection parameters.

**5.2 Mutable presentation state** — only permitted properties: label candidate
selection; offset within a permitted range; alignment; leader-line usage and
route among allowed choices; display-name variant; priority within predefined
rules; optional-label visibility; collision-avoidance displacement for
decorative elements. AI must never directly mutate astronomical objects.

## 6. Core domain model

- Sky data (`Star`, `DeepSkyObject`, `ConstellationSegment`,
  `ConstellationPolygon`, `NebulaOutline`, `MilkyWayContour`): no page coordinates.
- `StarSystem` (double/multiple overlay; WDS): catalogue identity, components,
  separation, position angle, component magnitudes and a match status. It links
  to `Star` objects by stable ID and never mutates them.
- `ChartDefinition`: what sky to render (`id`, center RA/Dec, width/height,
  `projection`, `rotation_deg`, `atlas_id`, `neighbours`); geometry only.
- `ChartScene`: projected content (stars, DSOs, star systems, boundaries, lines,
  outlines); chart-plane coordinates, no typesetting decisions.
- Layout state: `Label`/`LabelCandidate`, resolved presentation, transform/style
  and optimizer results. `ChartLayout` is an architectural concept, not an
  implemented Python class; the renderer receives these existing structures.
  `chart render --write-layout` writes `chart.json` for diagnostics/replay.
  Serialized layout state remains a first-class build artifact.

Full model: `docs/ARCHITECTURE.md`.

## 7. Coordinate and astronomy conventions

Encoded in tests.

- **7.1 Units** — explicit names (`ra_deg`, `dec_deg`, `major_axis_arcmin`,
  `position_angle_deg`); never ambiguous naked angle fields. Astropy quantities
  allowed at catalogue/astronomy boundaries; internals use documented numeric
  units.
- **7.2 Epoch** — J2000/ICRS-compatible; proper motion not required initially.
- **7.3 Orientation** — north up, east left. No mirror/reversal modes in MVP.
- **7.4 Projection** — stereographic initially; renderer-independent so
  alternatives can be added later.

Page coordinates are physical millimetres/points, never screen pixels alone.

## 8. Catalogue strategy

Ingestion is isolated from rendering and retains provenance; source-specific
column semantics never leave their importer. Stars: Tycho-2 (preferred),
supplemented by Hipparcos for the bright stars Tycho-2 omits. Optional UCAC4 faint
stars live in a separate SQLite store and are unlabeled; keep them separate from
the primary named-star store. DSOs use OpenNGC plus imported catalogue
supplements. Visual double/multiple stars: the Washington Double Star Catalog (WDS)
is a semantic **overlay** on the star base, never a source of single-star
positions; it is linked per chart and never overwrites Tycho-2. Additional
catalogues require license decision, provenance, field mapping, duplicate
strategy and explicit visual value. Never assume redistributable. Sources,
licenses, storage: `docs/DATA_SOURCES.md`.

## 9. Storage strategy

- raw: `data/raw/`; normalized: `data/processed/`; provenance: adjacent JSON
  manifests; artifacts: `build/`.
- Do not commit large catalogue files; provide scripts to reproduce processed
  data from raw inputs.
- Tests use small committed fixtures only.
- Format choices follow profiling; SQLite retained for stars (Parquet
  rejected). See `docs/PERFORMANCE.md`.

## 10. Atlas definitions

Edition/content/tiling is `atlas/*.yaml`; appearance is `styles/*.yaml`.
Configuration, not separate engines. Do not mix those concerns.

| Edition | Scale | Atlas/style preset stem | Status |
| --- | --- | --- | --- |
| Pocket | 5 mm/° | `pocket` | Main |
| Standard | 10 mm/° | `standard` | Main |
| Deep | 20 mm/° | `deep` | Main |
| Eyepiece | 40 mm/° | `eyepiece` | Experimental |
| Eyepiece Deep | 80 mm/° | `eyepiece_deep` | Experimental test charts |

The scale refers to main charts; detail charts can override it. Eyepiece Deep
currently has explicit test charts, not a full-sky tiling. The `--edition`
shortcut supports only `pocket`, `standard`, `deep`; experimental presets use
explicit `--atlas` and `--style` paths.
DSO policy composition lives in `config/observing_lists.yaml` and
`catalog/selection.py`: preserve Pocket ⊆ Standard ⊆ Deep = Eyepiece using
canonical physical identities, not display names.

## 11. Atlas tiling

Overlapping chart definitions covering every supported declination: sufficient
star-hop overlap, derivable neighbours, possible polar rules, no gaps, no
excessive duplication. Automated coverage tests required. Frozen Standard
geometry/tiling: `docs/CARTOGRAPHY.md`.

## 12. Symbol rendering

Symbols are semantic; type controls shape and style controls size. Star size is
monotonic with magnitude and stable across PDF/PNG. Extended DSO symbols use
reliable catalogue sizes when `use_angular_size` is enabled. Preserve galaxy
axis ratio and position angle; galaxy diameter limits act on the major axis.
Missing/unreliable sizes use `fallback_diameter_mm`, floored by
`min_diameter_mm` and capped by `max_diameter_mm` where configured; do not shrink
large objects to fixed sizes. The detailed rules live in `docs/ARCHITECTURE.md`.
All DSO geometry must use `render/symbols.py:dso_symbol_extent` and its
`SymbolExtent`, including rendering, label exclusion and collision detection.
PN size classes derive from the configured angular floor in that same path.
Schematic nebula outlines are implemented as projected/clipped vector paths.
Milky Way brightness contours from the vendored d3-celestial data are an
unlabeled background layer, controlled by `milky_way` in the style; keep them
separate from DSO geometry and label collision obstacles.
Emphasized objects (Messier, Herschel 400) use the configured heavier stroke.
The renderer takes emphasis from resolved bold labels, not catalogue queries.

WDS pair selection uses configured separation/companion-magnitude bands with a
0.5-arcsec minimum and no Δmag filter (`catalog/wds_selection.py`). Printed
clearance between the two symbol edges then classifies pairs as unresolved,
marginal or resolved (`render/double_stars.py`). For unresolved pairs, the current
renderer suppresses linked component disks and draws one disk sized by combined
magnitude at the real primary position, plus a horizontal marker. Marginal and
resolved pairs keep their plotted base stars without a marker from that pair.
WDS does not add star positions or mutate stored stars; combined magnitude is
presentation state. The marker does not encode position angle. Keep selection
and representation separate; settings live under `double_stars:` in the style.

## 13. Typography

Cairo for vector graphics; Pango/PangoCairo for shaping and exact metrics.
Never place labels with approximate character widths; renderer and collision
system share the same metrics. Style config controls family, size, weight,
category, priority, spacing and halo strategy. Fonts must have
redistribution/embedding rights. Bundled Lato is used for charts; bundled Source
Sans 3 for editorial/index pages. Register package assets through
`render/fonts.py`; do not depend on system-installed copies.

## 14. Label system

- **14.1 Stable IDs** — `label:dso:NGC4565`, `label:star:HIP91262`,
  `label:constellation:VIR`; required for diffs, AI references, tests,
  overrides and reproducible optimization.
- **14.2 Candidates** — compass positions `N NE E SE S SW W NW`, offset from
  the anchor exclusion zone, on concentric rings. DSO leader-line routes are
  implemented in `layout/leader_lines.py`; do not invent routes in the renderer.
- **14.3 Priorities** — category weights plus local relevance: major/common
  name, Messier, bright NGC/IC, prominent named star, ordinary NGC/IC, fainter
  optional DSO, minor star designation. The single numeric scale lives in
  `catalog/priority.py`; `tier_for` maps it onto HIGH/MEDIUM/LOW. Herschel 400
  is split by visual significance (prominent members are high, the rest
  medium). A merely bright DSO is high priority but **not** mandatory.
- **14.4 Required collision checks** — label vs label, page border, important
  star, DSO, own exclusion zone, title/metadata; leader line vs labels and
  important symbols; excessive leader-line crossing. Grid lines have lower
  priority than labels and may be interrupted.
- **14.5 Deep-sky label text and hierarchy** — a presentation-only formatting
  layer renders catalogue identifiers compactly without mutating catalogue data:
  a bare number means NGC (`NGC 4565` → `4565`), `IC 3476` → `I3476`, Messier
  wins over NGC/IC, other catalogues use short abbreviations (`Sh2-101`,
  `Cr399`, `B168`). Common names do not replace the designation. Tiers are style
  config (`label.dso_labels`): Messier bold at normal size (1.0×), non-Messier
  Herschel 400 bold at normal size, ordinary regular. Each `Label` carries its
  resolved `font_size_pt`/`font_weight`.
- **14.6 Deterministic selection before placement** — `object visible != label
  visible`. Candidate labels pass semantic de-duplication (one primary visible
  label per printed name; catalogue aliases and duplicated star names collapse
  to the higher priority, then the brighter target, then the stable id). Every
  selected star and DSO label is retained for geometric placement, regardless
  of local density. The optimizer tries alternate candidates and reports any
  remaining conflicts rather than hiding selected labels. After optimization,
  a DSO label may be suppressed only when a geometrically overlapping detail
  chart covers the object and prints that same label without a hard issue; the
  DSO symbol remains on the main chart. Density selection remains for other
  optional presentation labels. Manual overrides are protected from selection.

## 15. Deterministic layout optimizer

Complete layout is generated **without AI**; AI improves a usable layout but is
never required for a valid page.

- **15.1 Hard constraints** — text outside printable bounds, severe label
  overlap, invalid candidate, references to missing elements, invalid geometry,
  overlapping mandatory furniture. Unresolved hard violations fail validation.
- **15.2 Soft cost** — separately measurable components (never an opaque score):
  label-label overlap, label-symbol overlap, anchor distance, leader-line
  length/crossing, candidate preference, edge proximity, local crowding, visual
  imbalance. Expose component diagnostics.
- **15.3 Strategy** — priority-ordered greedy candidate selection, local
  improvement passes, deterministic conflict repair. Add simulated annealing /
  CP-SAT only if benchmarks show clear need; any stochastic optimizer is seeded.

## 16. Renderer architecture

The renderer draws the supplied scene and resolved labels using their transform,
style and presentation. It must not query catalogues, invent or move labels,
make content-selection decisions or change atlas geometry. Current outputs are
vector PDF and PNG; annotated PNG uses the review renderer. SVG is not currently
exposed. Reason in physical page units.

## 17. Review rendering

Per chart: clean preview PNG, annotated review PNG, compact metadata JSON.
Annotations (short label IDs, subtle boxes, anchor markers, numbered dense
regions) must not hide the chart and never enter final PDFs. Full-page preview
first; high-density crops with page/element mapping later. Details:
`docs/AI_REVIEW.md`.

## 18. AI review architecture

AI is first-class but optional; the atlas always builds with AI disabled.

- **18.1 Provider abstraction** — `ChartReviewer.review(request) -> result`
  Protocol. OpenRouter first; no OpenRouter-specific structures elsewhere.
  Implementations: `MockReviewer`, `OpenRouterReviewer`, `RecordedReviewer`.
- **18.2 Configuration** — model choice lives in `ai.yaml`, never layout logic;
  keys include `enabled`, `provider`, `reviewer_model`, `fallback_models`,
  `max_iterations`, `max_cost_per_chart_usd`.
- **18.3 Structured output only** — validated schema; never parse prose. All
  responses pass schema validation before affecting layout.
- **18.4 Allowed actions** — use the schema whitelist and actions actually
  advertised by `review/build.py`, enforced by `ai/actions.py`. Bounded label
  moves, optional visibility and DSO leader enable/remove actions are available.
  Display-name variant actions remain unadvertised. Never advertise an action
  without serializable presentation state and deterministic validation.
- **18.5 AI cannot approve invalid geometry** — apply permitted actions to a
  copied layout, run deterministic validation, compute cost, reject changes that
  add hard violations, re-render only if accepted. AI is advisory.

## 19. AI optimization loop

Start from a deterministic layout. Review, apply permitted actions to a copy,
validate and render accepted changes; reject new hard violations and worsening
soft cost. Terminate on no significant issues, target score, no accepted changes,
iteration/cost limits or repeated layout hash. Infinite loops are forbidden.
Loop and replay details: `docs/AI_REVIEW.md`.

## 20. AI cost control

Track per request: provider, model, tokens, cost, latency, page ID, iteration,
prompt/schema version; persist an audit log. Tiered cheap-first /
strong-on-hard-pages policy is later, after reviewer benchmarking. Details:
`docs/AI_REVIEW.md`.

## 21. AI benchmark suite

Choose models empirically on difficult and sparse fields, measuring useful
detections/actions, false positives, schema compliance, repeatability and cost.
Prefer the cheapest model meeting quality. Fixtures/results: `docs/AI_REVIEW.md`.

## 22. Manual overrides

Never patch renderer code for one object. Use stable-ID override documents:

```yaml
chart: standard-042
labels:
  label:dso:NGC4565: {candidate: SW, locked: true}
```

Reviewable in Git, applied after initial layout, respected by later optimizers
when locked. Escape hatch, not the primary layout method.

## 23. Validation

Rendering is not publishability.

- **Structural:** unique IDs, finite coordinates, known references, valid
  candidates, page dimensions, required elements present.
- **Geometry:** printable bounds, hard collisions, symbol dimensions, text
  metrics, grid clipping, neighbour references.
- **Atlas-level:** sampled sky coverage and neighbour-overlap checks exist in
  `atlas/tiling.py`; `atlas/report.py` reports coverage/density/navigation.
  `atlas validate` checks manifest consistency and artifact checksums; ordinary
  validation can pass with recorded hard layout issues.
- **Publication:** `atlas build --publication` and `atlas validate --publication`
  additionally require complete chart sets, sampled coverage, traceable catalogue
  checksums, current input fingerprints and zero hard layout issues. Builds are
  staged and the prior publication is retained. See `build/preflight.py`.
  These checks do not establish field usability or legal redistribution rights.

## 24. Testing strategy

Deterministic geometry over coverage.

Run focused tests under the matching `tests/<area>/` directory. `make test-fast`
omits `slow` full-sky audits and `integration` local-catalogue checks;
`make check` always includes both, including the `tests/build/` subtree.

- **24.1 Unit** — coordinate conversion, projection, angular distance, clipping,
  magnitude-to-symbol mapping, ellipse orientation, candidates, collision, cost
  components, AI action validation, serialization round trips.
- **24.2 Golden/reference** — sparse chart, crowded galaxy field, dense star
  field; compare layout JSON, counts, positions within tolerance, selected
  candidates, render metadata. Avoid full-PDF byte comparisons.
- **24.3 Property** — center maps to chart center; finite projections in FOV;
  fainter never means larger star; serialization preserves state; validator
  rejects out-of-page mandatory labels.

## 25. Performance targets

One standard-density A4 chart builds interactively; deterministic layout in
seconds, not minutes. Existing atlas builds support per-page workers; preserve
deterministic output order and measure before further parallelization.
Benchmarks: `docs/PERFORMANCE.md`.

## 26. Caching

Later, but design for it: catalogue query → scene; scene+style → layout;
layout → preview; review-request hash → AI result; layout → PDF page. AI
responses must be cacheable/replayable.

## 27. Logging and diagnostics

Per chart: stars/DSOs selected; labels requested/placed/hidden; hard
violations; soft cost before/after; AI iterations and cost. Debug mode renders
bounding boxes, exclusion zones, candidate positions, collision edges, label and
object IDs. Design diagnostics early.

## 28. Command-line interface

Keep the existing `argparse` CLI. `cli.py` owns dispatch and chart/atlas
commands; `cli_data.py` registers catalogue import/inspection commands. Keep
scientific logic in the existing domain modules. Specialized development
utilities live in `tools/`, including `benchmark_ai_review.py`.
Use `--help` to check current options.

```bash
nightsky data star-count --help
nightsky data selection-report --help
nightsky chart render --chart test-virgo --edition standard
nightsky atlas coverage --edition standard
nightsky atlas build --edition standard
nightsky atlas validate --edition standard --publication
.venv/bin/python tools/benchmark_ai_review.py --help
```

`chart render|validate|review` and `atlas build` accept `--overrides PATH`
(file or directory) and custom input directories. Use explicit
`--no-constellations`, `--no-outlines`, `--no-star-names`,
`--no-observing-lists`, `--no-double-stars` to omit layers; empty paths do not
disable them. Observing policy defaults to `config/observing_lists.yaml`.

## 29. Configuration principles

YAML for human-edited atlas/style config, schema-validated. Unknown keys fail
fast; no silent ignores; physical values carry units in field names. Prefer
typed dataclasses/models over arbitrary nested dicts. Atlas config uses pydantic
strict models (`extra="forbid"`); see `docs/ARCHITECTURE.md`.

## 30. Repository structure

Python modules live under `src/nightsky_atlas/`; configuration under `atlas/`,
`styles/` and `config/`; tests under `tests/`; generated outputs under ignored
`build/`. The module/directory map is in `docs/ARCHITECTURE.md`.

## 31. Python engineering rules

- **Python 3.12+** (see `pyproject.toml`); type hints on public domain models and
  pipeline interfaces.
- Standard dataclasses for internal domain models; a schema-validation library
  only for external configuration and AI JSON.
- Tooling: **ruff**, **pytest**; add a type checker once interfaces stabilize.
- Justify every new runtime dependency; check `pyproject.toml` and the README's
  Linux prerequisites first. No large stacks for convenience.

## 32. Build/repository commands

```bash
make setup   # create .venv and install package + dev tools
make test    # pytest
make lint    # ruff check .
make check   # lint + test (standard pre-commit verification)
```

Use `.venv/bin/python -m nightsky_atlas --help` or the `nightsky` script.
Catalogue workflow and artifact paths: `README.md`.

## 33. Security and secrets

OpenRouter credentials are secrets. Never commit keys; read from
`OPENROUTER_API_KEY` or a git-ignored `.env`; keep `.env.example` placeholder
only; scrub secrets from logs. Tests must not require live credentials; live AI
tests are explicitly opt-in.

## 34. Quality bar

Level A technically correct; Level B practically usable (release minimum);
Level C publication quality (long term). Definitions: `docs/PRODUCT.md`.

## 35. Reference development fields

- **Virgo/Coma** — many galaxies, dense DSO labels, ambiguous associations,
  leader-line stress.
- **Cygnus** — high stellar density, Milky Way contours, schematic nebula outlines,
  faint-label legibility stress.

Committed test fields live in `atlas/standard.yaml`.

## 36. Development philosophy

Develop through usable end-to-end charts before expanding infrastructure.
The original vertical development sequence is in `docs/DEVELOPMENT_PLAN.md`.

## 37. Development plan

Milestone criteria live in `docs/DEVELOPMENT_PLAN.md`; artifact evidence and
open issues in `docs/STATE.md`. Avoid duplicating their checkbox status here.
Implemented features include the core pipeline, all three main-edition tilings,
DSO selection/inheritance, WDS, outlines, Milky Way contours, atlas reporting and
publication preflight. Additional catalogue/legal review and issue-report work
remain partial.

Full Pocket, Standard and Deep build artifacts exist. Ordinary output validation
passes for the recorded 2026-10-07 builds, which still contain hard layout issues
and were not publication builds. This does not validate them against later input
changes. Track feature completion, full-build success, validation mode, visual
review, telescope field testing and release approval separately. M15.5 field
acceptance remains pending; a PDF or a passing test suite is not release approval.

## 38. Explicit deferred features

Illustrative constellation artwork (stick figures are implemented); artistic
colour Milky Way (grayscale contours are implemented); eyepiece mirror/orientation
modes (distinct from the experimental editions); web viewer; GUI; custom atlas
wizard; finder/FOV overlays; variable-star charts; photographic overlays;
translated editions; print-on-demand. Do not implement because they seem useful. List:
`docs/PRODUCT.md`.

## 39. Human decision checkpoints

Respect recorded decisions at M3.3, M4.3, M8.4, M9.4, M11.4, M13.3 and M14.1;
do not request them again for routine work already authorized. Explicit human
evaluation remains necessary for M15.5 field acceptance, new catalogue adoption
and final Pocket/Deep publication specifications. Revisit an accepted decision
when the task changes its scope, not merely because its historical checkpoint
appears in the plan. Details: `docs/DEVELOPMENT_PLAN.md`.

## 40. Definition of MVP

The MVP criteria are in `docs/PRODUCT.md`: real-data Virgo/Coma and Cygnus pages
with deterministic layout, vector/review artifacts and zero hard violations.
AI review is not required for the basic MVP.

## 41. Definition of first release candidate

Release criteria live in `docs/PRODUCT.md`: reproducible complete coverage,
stable navigation, final provenance, zero hard errors, recorded AI review/skip
policy and replay, field testing and accepted/fixed high-severity issues.

## 42. What success looks like

The atlas must be useful at a Dobsonian and reproducible from source data and
configuration with little manual label cleanup. Judge changes against field
readability and reliability; see `docs/PRODUCT.md`.
