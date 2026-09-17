# Development plan

The authoritative, granular plan. `AGENTS.md` links here so a coding agent can
find the first unfinished task with complete dependencies. Status markers:

```text
[ ] not started
[~] in progress
[x] complete
[!] blocked / human decision required
```

## Development philosophy

Proceed vertically rather than building every subsystem in isolation:

```text
small real catalogue
→ correct projection
→ one ugly but correct page
→ real typography
→ real labels
→ deterministic optimization
→ beautiful test page
→ AI review
→ multiple pages
→ whole atlas
```

Do not spend weeks designing complete catalogue infrastructure before the first
page is visible.

## Current position

- M0–M14 complete. M15.1–M15.4 complete. **M15.5 in progress** (alpha built,
  field test pending).
- M16.1 complete. M16.2–M16.4 not started (M16.4 document now seeded).
- M21.1–M21.4 complete (observing-list-driven DSO selection with per-type
  visibility; Herschel 400 forced into Standard). M21.5 not started.
- M11.4 and M13.3 complete (live OpenRouter review and model selection).
- Live snapshot of progress, artifacts and open issues: `docs/STATE.md`.

## M0 — Repository and executable skeleton

- [x] **M0.1 Repository skeleton** — `pyproject.toml`, `README.md`,
  `src/nightsky_atlas/`, `tests/`, `Makefile`, `.gitignore`; installable package;
  `python -m nightsky_atlas --help`; pytest and Ruff run; `make check` works.
- [x] **M0.2 Typed configuration foundation** — minimal chart/style YAML
  fixture; unknown keys fail; explicit page units; no atlas tiling; valid/invalid
  config tests.

## M1 — Geometry prototype

- [x] **M1.1 Core chart geometry models** — `ChartDefinition`, page geometry,
  chart-plane point, explicit units/conventions; serialization/repr tests;
  invalid dimensions rejected.
- [x] **M1.2 Stereographic projection** — documented forward projection from
  RA/Dec relative to chart center; renderer-independent; tests for center,
  cardinal offsets and symmetry; finite over supported FOV.
- [x] **M1.3 Page transform and clipping** — projection → physical page
  coordinates; mm/point-aware; printable rectangle; reliable in/out test; border
  and rotation=0 tests. Rotated charts deferred.

## M2 — First real stars

- [x] **M2.1 Normalized Star model** — catalogue-independent, with provenance;
  tiny committed fixture.
- [x] **M2.2 Sample star catalogue loader** — small CSV/fixture for one test
  field; no full Tycho ingestion yet.
- [x] **M2.3 First ChartScene** — select and project stars for a
  `ChartDefinition`; known fixture counts; projected positions tested; off-chart
  stars excluded.

## M3 — First visible PDF

- [x] **M3.1 Cairo page renderer** — page background, chart border, star
  circles, minimal title; PDF + PNG preview; no labels.
- [x] **M3.2 Magnitude-to-star-size mapping** — configurable, monotonic, sensible
  min/max print diameter, tested. Magnitude-scale diagnostic page available.
- [x] **M3.3 First standard test chart** — deterministic Virgo/Cygnus definition
  plus small source fixture; sample page via documented command.
  **Human checkpoint:** inspect PDF at 100% and preferably print once. Do not
  proceed to complex labels until page scale and star appearance are accepted.

## M4 — Real catalogue import

- [x] **M4.1 Star catalogue import pipeline** — selected full star source; source
  provenance; normalized magnitude; processed output manifest; deterministic;
  no hidden network download in normal atlas builds.
- [x] **M4.2 Indexed star queries** — simplest adequate storage/query; benchmark
  realistic standard-chart queries before optimizing; results recorded.
- [x] **M4.3 Verify standard chart stellar density** — render Cygnus and a sparse
  field to compare practical density at candidate limits.
  **Human checkpoint:** choose provisional standard stellar limit and star-size
  curve.

## M5 — Deep-sky foundation

- [x] **M5.1 Normalized DeepSkyObject model** — IDs, RA/Dec, type, magnitude,
  major/minor axes, position angle, common name, provenance.
- [x] **M5.2 OpenNGC sample loader** — committed fixture sufficient for Virgo.
- [x] **M5.3 Basic DSO symbols** — semantic symbols for common classes; simple,
  print-safe.
- [x] **M5.4 Real OpenNGC import** — reproducible normalized processed data plus
  provenance manifest.
- [x] **M5.5 Oriented galaxy ellipses** — major/minor dimensions and position
  angle where available; minimum printable sizing; orientation transformation
  tests.

## M6 — Text and initial labels

- [x] **M6.1 Pango text metrics** — exact measurement in physical page
  coordinates; measured bounds available before rendering; renderer and
  collision system share metrics.
- [x] **M6.2 Label and LabelCandidate models** — stable IDs, target object ID,
  candidate list, selected candidate, priority, mandatory/optional, text bounds,
  serialization.
- [x] **M6.3 Compass label candidates** — N/NE/E/SE/S/SW/W/NW around
  stellar/DSO exclusion geometry.
- [x] **M6.4 Render unoptimized labels** — deterministic fixed candidate
  preference; page expected to collide; proves text/layout separation.

## M7 — Collision and validation engine

- [x] **M7.1 Geometric primitives** — rectangles, circles/ellipse
  approximations, intersection tests, page bounds, distance metrics.
- [x] **M7.2 Hard label collision checks** — label-label, label-page,
  label-important-star, label-DSO; expose issues with stable IDs.
- [x] **M7.3 Layout validator** — unresolved hard violations fail validation;
  CLI prints concise diagnostics.
- [x] **M7.4 Debug rendering** — optional flags for label boxes, exclusion zones,
  element IDs, candidate points. Required before optimizer work.

## M8 — Deterministic label optimization

- [x] **M8.1 Priority-ordered greedy placement** — lowest-cost valid candidate by
  priority; optional labels may stay hidden if no acceptable candidate exists.
- [x] **M8.2 Decomposed soft-cost function** — explicit overlap, anchor distance,
  edge proximity, preferred direction and crowding metrics; diagnostics expose
  component values.
- [x] **M8.3 Local repair pass** — deterministic candidate swaps for conflict/cost
  reduction after greedy placement.
- [x] **M8.4 Virgo label benchmark** — dense Virgo chart stressing the optimizer;
  save scene summary, layout JSON, debug PNG, clean PDF.
  **Human checkpoint:** judge whether the deterministic result is field-usable.
  If not, improve deterministic algorithms before AI integration.

## M9 — Publication-oriented chart furniture

- [x] **M9.1 Coordinate grid** — configurable RA/Dec grid with clipping; labels
  take priority over grid lines.
- [x] **M9.2 Chart title and scale information** — page furniture separate from
  sky labels.
- [x] **M9.3 Neighbour placeholders/navigation model** — neighbour references for
  manually defined charts before automatic tiling exists.
- [x] **M9.4 Refine print typography/style configuration** — move visual constants
  out of code into typed style config.
  **Human checkpoint:** standard test pages should look like an intentional
  atlas, not a plotting-library output.
- [x] **M9.5 Deep-sky label formatting and hierarchy** — presentation-only
  formatter drops the NGC prefix (a bare number means NGC), compacts IC and
  other catalogues, gives Messier precedence over NGC/IC, and applies configured
  bold/size tiers (`label.dso_labels`).  Each `Label` carries resolved
  `font_size_pt`/`font_weight`; emphasized symbols use the heavier
  `dso.bold_line_width_mm` so the mark is bold wherever the name is.  Catalogue
  data is never mutated.

## M10 — Review artifacts

- [x] **M10.1 Review PNG renderer** — annotated image with element IDs/bounding
  boxes while preserving legibility.
- [x] **M10.2 ReviewRequest model** — page ID, image(s), visible element
  metadata, permitted actions, quality diagnostics, schema/prompt version. Avoid
  dumping the full layout.
- [x] **M10.3 ReviewResult schema** — strictly validate element IDs, issue types,
  severities, action type, candidate values; malformed reviews never alter a
  layout.

## M11 — OpenRouter AI reviewer

- [x] **M11.1 Reviewer interface and MockReviewer** — all AI logic testable
  without a network.
- [x] **M11.2 OpenRouterReviewer** — env API key, configurable model, image
  input, structured JSON, timeouts, retry only for transient failures, no silent
  prose fallback, usage/cost capture. Live tests opt-in.
- [x] **M11.3 AI action application** — whitelisted actions only, applied to
  copied state, then deterministic validation; reject invalid actions
  individually where practical.
- [x] **M11.4 One-step AI review command** — `nightsky chart review
  test-virgo --model MODEL`; review JSON only, no iteration yet.
  **Human checkpoint:** inspect whether the cheap vision model identifies
  genuinely bad label placements.

## M12 — AI optimization loop

- [x] **M12.1 Bounded optimization loop** — max iterations, min target score,
  repeated-layout detection, no-change termination, cost budget.
- [x] **M12.2 Persist review history** — per iteration: layout hash, request
  metadata, result, accepted/rejected actions, new hash, usage/cost.
- [x] **M12.3 RecordedReviewer/replay** — reproduce a previous AI optimization
  offline.
- [x] **M12.4 Compare before/after metrics** — record whether deterministic cost
  improved/worsened; never accept AI changes blindly.

## M13 — AI benchmark and model selection

- [x] **M13.1 First benchmark dataset** — ~10–20 curated page/problem examples
  from Virgo, Cygnus and additional fields.
- [x] **M13.2 Benchmark runner** — schema compliance, correct issue detection,
  false positives, valid actions, cost, latency.
- [x] **M13.3 Compare cheap multimodal models** — do not encode assumptions about
  the winning provider/model; choose the default from measured quality/cost.
  **Human checkpoint:** approve default reviewer model and fallback policy.

## M14 — Standard atlas tiling

- [x] **M14.1 Standard page/FOV target** — freeze page size, drawing area, FOV
  strategy, overlap target, stellar limit from printed test experience.
- [x] **M14.2 Declination-band tiling** — generate complete chart definitions
  programmatically; handle RA convergence with declination.
- [x] **M14.3 Polar charts** — appropriate polar tiling/projection if required.
- [x] **M14.4 Coverage validator** — automated complete-coverage and overlap
  test.
- [x] **M14.5 Chart numbering and neighbours** — stable deterministic IDs/page
  numbers.

## M15 — Complete Standard atlas build

- [x] **M15.1 Atlas build orchestration** — definitions → scenes → deterministic
  layouts → validation → optional AI review → page PDFs; subset builds for
  development.
- [x] **M15.2 Merge page PDFs** — one atlas PDF preserving vector content.
- [x] **M15.3 Atlas front matter/minimal legend** — keep the first version small.
- [x] **M15.4 Build manifest** — git commit, catalogue versions, configs, AI
  reviewer/model, prompt/schema versions, per-page layout hashes, timestamp.
- [~] **M15.5 Standard alpha atlas** — generate the complete atlas.
  **Major human checkpoint:** print/use representative pages at a telescope.
  Evaluate star-hop usability, faint star visibility, page density, typography
  under red light, object-label ambiguity and page navigation. Do not begin
  Pocket/Deep merely because a full PDF exists; Standard must first be useful.

## M16 — Manual override workflow and publication hardening

- [x] **M16.1 Override files** — stable-ID overrides including locked label
  candidates.
- [ ] **M16.2 Atlas-wide issue report** — pages with hard errors, high
  deterministic costs, AI warnings, manual overrides, missing data.
- [ ] **M16.3 Preflight command** — `nightsky atlas validate standard
  --publication`; fail on any unresolved publication blocker.
- [~] **M16.4 Data-source/license documentation** — `docs/DATA_SOURCES.md` now
  exists with all current sources; review before redistribution.

## M17 — Pocket edition

Only begin after Standard is stable.

- [ ] **M17.1 Pocket atlas configuration** — reduce stellar depth, DSO density
  and label density; increase field size/usability.
- [ ] **M17.2 Pocket tiling** — may differ substantially from Standard.
- [ ] **M17.3 Pocket style** — prioritize quick recognition and uncluttered
  navigation.
- [ ] **M17.4 Build and field-test Pocket alpha**.

## M18 — Deep edition data expansion

Only begin after Standard/Pocket architecture proves stable.

- [ ] **M18.1 Deep data requirements** — which additional catalogues materially
  improve visual observing.
- [ ] **M18.2 License review per proposed dataset** — no ingestion before a
  license/provenance decision.
- [ ] **M18.3 Additional catalogue importers** — keep source-specific logic
  isolated.
- [ ] **M18.4 Duplicate/cross-ID resolution** — deterministic and documented.
- [ ] **M18.5 Raise stellar limit and profile performance** — optimize only based
  on measured bottlenecks.

## M19 — Extended structures

- [~] **M19.1 Nebula outlines** — vector boundaries where suitable data exist.
  Pipeline done (project-authored schematic RA/Dec outlines -> projected/clipped
  vector paths -> dashed stroke, `data/fixtures/outlines/`); first Cygnus set only,
  coverage to be expanded.
- [ ] **M19.2 Milky Way representation** — print-friendly, from legal source
  data.
- [ ] **M19.3 Dark nebula representation** — contours/symbols designed for field
  usefulness, not decoration.
- [ ] **M19.4 Revisit AI review for extended structures** — expand schema only if
  needed.

## M20 — Deep atlas

- [ ] **M20.1 Deep page geometry and tiling** — likely larger page count / smaller
  FOV.
- [ ] **M20.2 High-density label optimization** — stronger algorithms only if
  evidence justifies them.
- [ ] **M20.3 Benchmark AI escalation policy** — cheap-first / strong-model-on-hard
  pages.
- [ ] **M20.4 Generate Deep alpha**.
- [ ] **M20.5 Telescope field testing** — difficult galaxy fields and dense Milky
  Way regions.

## M21 — Observing-list-driven DSO selection

Deep-sky selection must not be a single global magnitude cut.  Curated visual
observing lists act as forced-include/priority metadata, and object rendering is
decided separately from object labelling.  Membership, scores and priorities are
atlas metadata and never modify the astronomical model (`AGENTS.md` section 5).

- [x] **M21.1 DSO metadata model** — separate `DsoMetadata` carrying
  `list_memberships`, `visual_score`, `importance_score`, `render_priority` and
  `label_priority`; `SceneDso` carries it; `DeepSkyObject` stays pure astronomy.
- [x] **M21.2 Observing-list import/mapping** — fixture format, designation
  normalization (NGC/IC leading zeros, Messier), membership index, and a strict
  `config/observing_lists.yaml` policy with per-edition forced lists, weights and
  inheritance.
- [x] **M21.3 Herschel 400 integration** — vendored CC BY-SA fixture; Herschel 400
  is a Standard forced list and all resolvable members render regardless of
  magnitude.  `render_priority`/`label_priority` are used separately by the scene
  builder and label builder.
- [x] **M21.4 Per-type visibility evaluators** — `catalog/visibility.py` provides
  a `VisibilityEvaluator` per `DsoType` behind one interface, returning a
  `VisibilityAssessment` (`visible`, 0-100 `score`, reasons) from surface
  brightness, angular size and type-specific rules.  `SelectionPolicy` carries
  the edition `VisibilityLimits` (default: 8-10 inch dark sky) sourced from the
  atlas `visibility:` block, and the scene builder keeps an object when it is
  visible or forced.  Star/double-star entries are excluded from the DSO layer.
  A per-chart density budget remains a possible later refinement.
- [ ] **M21.5 Additional lists** — Messier, Caldwell, RASC, SAC, ASSA, Bennett and
  (licensing permitting) NSOG; Deep adds Herschel II and the Astronomical League
  programs.  Each needs a license/provenance decision before ingestion.

## Human decision checkpoints

Stop and request explicit human evaluation at these points:

1. **M3.3** — first printed stellar chart: scale/star appearance.
2. **M4.3** — standard stellar limiting magnitude.
3. **M8.4** — deterministic Virgo label quality.
4. **M9.4** — typography/cartographic visual identity.
5. **M11.4** — whether the AI reviewer sees useful visual problems.
6. **M13.3** — default OpenRouter model from the benchmark.
7. **M14.1** — final Standard page geometry/FOV/overlap.
8. **M15.5** — complete Standard alpha and telescope field test.
9. Before each additional external catalogue is adopted.
10. Before defining final Pocket or Deep publication specifications.

Do not substitute coding-agent preference for these product decisions.

MVP and first release-candidate definitions live in `docs/PRODUCT.md`.