# AGENTS.md — NightSky Atlas

> **Purpose:** Generate publication-quality printable star atlases for visual
> deep-sky observing, especially Dobsonian star-hopping.
> **Output:** vector PDF (primary); SVG, PNG preview, annotated review PNG,
> serialized layout JSON.
> **Language:** Python 3.12+. **Status:** M0–M14 done, Standard alpha in
> progress. Authoritative engineering contract for coding agents; keep it lean,
> push detail to `docs/`.

## Documentation map

| Document | Contents |
| --- | --- |
| `docs/PRODUCT.md` | Vision, non-goals, user, quality bar, MVP/RC, deferred features |
| `docs/ARCHITECTURE.md` | Full domain model, subsystem design, conventions, Python rules |
| `docs/DEVELOPMENT_PLAN.md` | Milestones M0–M20, acceptance criteria, human checkpoints |
| `docs/STATE.md` | Current progress, frozen geometry, artifacts, open issues |
| `docs/DATA_SOURCES.md` | Catalogue strategy, storage, licensing, provenance |
| `docs/CARTOGRAPHY.md` | Standard page/field/tiling design and coverage |
| `docs/AI_REVIEW.md` | Review rendering, AI architecture, loop, cost, benchmark |
| `docs/PERFORMANCE.md` | Catalogue-query benchmarks and storage decisions |

---

## 0. How an agent must work in this repository

Read this file before changing code; it is the authoritative contract.

**0.1 One task per agent run.** Unless told otherwise:

1. Find the **first unfinished task whose dependencies are complete** in
   `docs/DEVELOPMENT_PLAN.md`.
2. Implement **only that task**; run its checks and fix task-caused failures.
3. Update only that task's status in the plan.
4. Summarize files changed, checks executed and unresolved issues. Stop.

Do not opportunistically implement later milestones.

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
secrets. Prefer repository commands (`make check`) over invented checks. Do not
add code comments unless asked.

## 1. Product vision

Beautiful, practical paper charts for use at a telescope. Functional quality
inspired by Pocket Sky Atlas / Sky Atlas 2000.0 / Uranometria 2000.0; visual
design must not copy any existing atlas. Same engine, three editions:
**Pocket**, **Atlas** (primary, first), **Deep**. See `docs/PRODUCT.md`.

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
       ├─ vector renderer ─► PDF / SVG
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

- Sky objects (`Star`, `DeepSkyObject`, `ConstellationBoundary`,
  `ConstellationLine`, `NebulaOutline`, `MilkyWayFeature`): no page coordinates.
- `StarSystem` (double/multiple overlay; WDS): catalogue identity, components,
  separation, position angle, component magnitudes and a match status. It links
  to `Star` objects by stable ID and never mutates them.
- `ChartDefinition`: what sky to render (`id`, center RA/Dec, width/height,
  `projection`, `rotation_deg`, `atlas_id`, `neighbours`); geometry only.
- `ChartScene`: projected content (stars, DSOs, star systems, boundaries, lines,
  outlines); chart-plane coordinates, no typesetting decisions.
- `ChartLayout`: complete serializable page description (symbols, labels,
  selected candidate, text metrics, grid, borders, title, neighbours, optional
  legend, diagnostics, optimizer metadata). Serialized layout JSON is a
  first-class build artifact.

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
supplemented by Hipparcos for the bright stars Tycho-2 omits. DSOs:
OpenNGC. Visual double/multiple stars: the Washington Double Star Catalog (WDS)
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

## 11. Atlas tiling

Overlapping chart definitions covering every supported declination: sufficient
star-hop overlap, derivable neighbours, possible polar rules, no gaps, no
excessive duplication. Automated coverage tests required. Frozen Standard
geometry/tiling: `docs/CARTOGRAPHY.md`.

## 12. Symbol rendering

Symbols are semantic (`star`, `open_cluster`, `globular_cluster`, `galaxy`,
`planetary_nebula`, `bright_nebula`, `dark_nebula`, `galaxy_cluster`), not draw
commands. Star size is a configurable monotonic function of magnitude, stable
across PDF/PNG. Galaxies use major/minor axis and position angle where
available, with a minimum printable size preserving orientation. Large nebula
outlines (later) are true vector paths. Emphasized objects (Messier, Herschel
400) use a heavier configurable stroke, so the symbol is bold wherever its label
is; the renderer takes that emphasis from the layout's bold labels rather than
re-deriving catalogue facts. Visual double/multiple stars use three cases decided
by the printed separation, never a fixed angular separation: ordinary star (no
marker); unseparable pair (one symbol with combined magnitude plus a short
horizontal marker); separable pair (two real positions). The marker is a
cartographic symbol only, not the real position angle. Configurable under
`double_stars:` in the style.

## 13. Typography

Cairo for vector graphics; Pango/PangoCairo for shaping and exact metrics.
Never place labels with approximate character widths; renderer and collision
system share the same metrics. Style config controls family, size, weight,
category, priority, spacing and halo strategy. Fonts must have
redistribution/embedding rights.

## 14. Label system

- **14.1 Stable IDs** — `label:dso:NGC4565`, `label:star:HIP91262`,
  `label:constellation:VIR`; required for diffs, AI references, tests,
  overrides and reproducible optimization.
- **14.2 Candidates** — compass positions `N NE E SE S SW W NW`, offset from
  the anchor exclusion zone. Later: radial, along-path, leader-line candidates.
- **14.3 Priorities** — category weights plus local relevance: major/common
  name, Messier, bright NGC/IC, prominent named star, ordinary NGC/IC, fainter
  optional DSO, minor star designation.
- **14.4 Required collision checks** — label vs label, page border, important
  star, DSO, own exclusion zone, title/metadata; leader line vs labels and
  important symbols; excessive leader-line crossing. Grid lines have lower
  priority than labels and may be interrupted.
- **14.5 Deep-sky label text and hierarchy** — a presentation-only formatting
  layer renders catalogue identifiers compactly without mutating catalogue data:
  a bare number means NGC (`NGC 4565` → `4565`), `IC 3476` → `I3476`, Messier
  wins over NGC/IC, other catalogues use short abbreviations (`Sh2-101`,
  `Cr399`, `B168`). Common names do not replace the designation. Tiers are style
  config (`label.dso_labels`): Messier bold at 1.15×, non-Messier Herschel 400
  bold at normal size, ordinary regular. Each `Label` carries its resolved
  `font_size_pt`/`font_weight`.

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

The renderer is intentionally boring: it accepts a `ChartLayout` and draws
exactly what it specifies. It must not query catalogues, invent or move labels,
make content-selection decisions or change atlas geometry. Outputs: vector PDF
(text/lines retained), SVG, PNG preview, annotated review PNG. Reason in
physical page units.

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
- **18.4 Allowed actions** — whitelist only: `select_candidate`,
  `show_optional_label`, `hide_optional_label`, `use_leader_line`,
  `remove_leader_line`, `select_display_name_variant`; unknown actions rejected.
- **18.5 AI cannot approve invalid geometry** — apply permitted actions to a
  copied layout, run deterministic validation, compute cost, reject changes that
  add hard violations, re-render only if accepted. AI is advisory.

## 19. AI optimization loop

```text
layout_0 = deterministic_layout(scene); validate; render
repeat up to max_iterations:
    review = reviewer.review(rendered_page, metadata)
    if no significant issues: break
    proposal = apply_allowed_actions(layout, review)
    reject proposal if it adds hard violations
    if accepted: layout = proposal; render(layout); else stop
```

Terminate on: no significant issues; minimum score; no accepted changes;
iteration limit; cost budget; repeated layout hash. Infinite loops forbidden.

## 20. AI cost control

Track per request: provider, model, tokens, cost, latency, page ID, iteration,
prompt/schema version; persist an audit log. Tiered cheap-first /
strong-on-hard-pages policy is later, after reviewer benchmarking. Details:
`docs/AI_REVIEW.md`.

## 21. AI benchmark suite

Empirical model choice against difficult fields (Virgo/Coma, Cygnus Milky Way,
Sagittarius, Orion, M31, Pleiades, sparse high-latitude, chart-edge-heavy):
true detections, false positives, valid references, action usefulness, schema
compliance, repeatability, cost. Prefer the cheapest model meeting quality.
Fixtures and results: `docs/AI_REVIEW.md`.

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
- **Atlas-level (later):** complete coverage, no gaps, expected overlaps, unique
  numbering, consistent neighbours, index completeness, all pages generated.

## 24. Testing strategy

Deterministic geometry over coverage.

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
seconds, not minutes. Do not parallelize before single-page behavior is correct
and measured. Benchmarks: `docs/PERFORMANCE.md`.

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

`argparse` is sufficient; do not build the whole final CLI at once.

```bash
nightsky data fetch-stars | import-stars | star-count
nightsky data fetch-openngc | import-openngc
nightsky chart render | validate | review | magnitude-scale
nightsky atlas tile | coverage | build
nightsky benchmark ai-review
```

`chart render|validate|review` and `atlas build` accept `--overrides PATH`
(file or directory), `--constellations DIR` (default
`data/fixtures/constellations`; empty to omit), `--outlines DIR` (default
`data/fixtures/outlines`; empty to omit), `--star-names DIR` (default
`data/fixtures/starnames`; empty to omit), `--observing-lists DIR` (default
`data/fixtures/observing_lists`; empty to omit) and `--observing-config PATH`
(default `config/observing_lists.yaml`).

## 29. Configuration principles

YAML for human-edited atlas/style config, schema-validated. Unknown keys fail
fast; no silent ignores; physical values carry units in field names. Prefer
typed dataclasses/models over arbitrary nested dicts. Atlas config uses pydantic
strict models (`extra="forbid"`); see `docs/ARCHITECTURE.md`.

## 30. Repository structure

```text
nightsky-atlas/
├── AGENTS.md  README.md  pyproject.toml  Makefile  ai.yaml
├── src/nightsky_atlas/
│   ├── cli.py
│   ├── catalog/ astronomy/ projection/ chart/ atlas/ scene/
│   ├── layout/   # models, labels, candidates, collision, scoring,
│   │             # optimizer, overrides, validation
│   ├── render/   # cairo, symbols, text, grid, review
│   ├── review/   # models, schema, build
│   ├── ai/       # base, actions/schema, openrouter, recorded, loop,
│   │             # benchmark, config, credentials
│   └── build/    # chart, atlas
├── atlas/  styles/  data/  benchmarks/  overrides/  tests/  docs/  build/
```

## 31. Python engineering rules

- **Python 3.12+** (see `pyproject.toml`); type hints on public domain models and
  pipeline interfaces.
- Standard dataclasses for internal domain models; a schema-validation library
  only for external configuration and AI JSON.
- Tooling: **ruff**, **pytest**; add a type checker once interfaces stabilize.
- Justify every runtime dependency (numpy, astropy, pycairo, Pango bindings,
  PyYAML, httpx are likely justified). No large stacks for convenience.

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
- **Cygnus** — high stellar density, Milky Way context, extended nebulae later,
  faint-label legibility stress.

Exact centers/FOV are committed with the first chart prototype.

## 36. Development philosophy

Proceed vertically: small real catalogue → correct projection → one ugly but
correct page → real typography → real labels → deterministic optimization →
beautiful test page → AI review → multiple pages → whole atlas. Details:
`docs/DEVELOPMENT_PLAN.md`.

## 37. Development plan

Full plan, acceptance criteria and checkpoints: `docs/DEVELOPMENT_PLAN.md`.

- [x] M0–M14 (skeleton, projection, stars, PDF, catalogue import, DSOs, labels,
  collisions, optimizer, furniture, review artifacts, AI reviewer, AI loop,
  AI benchmark, tiling).
- [~] M15 Standard atlas build: M15.1–M15.4 done; **M15.5 alpha/field test in
  progress**.
- [x] M16.1 overrides; [ ] M16.2 atlas-wide issue report; [ ] M16.3 publication
  preflight; [~] M16.4 data-source/license documentation.
- [x] M21.1–M21.4 observing-list-driven DSO selection (separate render/label
  priorities; Herschel 400 forced into Standard; per-type visibility evaluators
  decide which objects are drawn); [ ] M21.5 further observing lists.
- [ ] M17 Pocket, M18 Deep data expansion, M19 extended structures, M20 Deep
  atlas.

Artifacts, frozen geometry and open issues: `docs/STATE.md`.

## 38. Explicit deferred features

Constellation artwork; artistic colour Milky Way; eyepiece orientation modes;
web viewer; GUI; custom atlas wizard; observing-list integration; finder/FOV
overlays; variable-star charts; photographic overlays; translated editions;
print-on-demand. Do not implement because they seem useful. List:
`docs/PRODUCT.md`.

## 39. Human decision checkpoints

Stop for explicit human evaluation at M3.3, M4.3, M8.4, M9.4, M11.4, M13.3,
M14.1, M15.5; before adopting each external catalogue; before final Pocket/Deep
specifications. Do not substitute coding-agent preference for product decisions.
Details: `docs/DEVELOPMENT_PLAN.md`.

## 40. Definition of MVP

Two publication-intent A4 test charts (Virgo/Coma, Cygnus): real stars, OpenNGC
DSOs, stereographic projection, magnitude sizing, semantic symbols, Pango
labels, deterministic optimization, furniture, vector PDF, preview/review PNG,
layout JSON, zero hard violations. AI review is not required for basic MVP.
Details: `docs/PRODUCT.md`.

## 41. Definition of first release candidate

Complete coverage, stable numbering, final provenance docs, reproducible clean
build, no hard validation errors, recorded AI review/skip policy per page,
deterministic replay of accepted AI decisions, atlas-wide PDF, field testing,
all high-severity issues fixed or explicitly accepted. Details:
`docs/PRODUCT.md`.

## 42. What success looks like

An observer can take the atlas to a Dobsonian and use it as a real observing
tool. The strongest criterion: a complete atlas can be regenerated from source
data and configuration with little or no manual label cleanup while staying
beautiful, readable and reliable at the telescope. Judge architecture against
this standard.