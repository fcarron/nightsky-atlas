# AGENTS.md — NightSky Atlas

> **Project:** NightSky Atlas  
> **Purpose:** Generate publication-quality printable star atlases for visual deep-sky observing, especially Dobsonian star-hopping.  
> **Primary language:** Python  
> **Primary output:** vector PDF  
> **Secondary outputs:** SVG, PNG preview, annotated review PNG, machine-readable layout JSON  
> **Status:** architecture and implementation plan  
> **Audience:** Codex / coding agents and human maintainers

---

## 0. How an agent must work in this repository

This file is the authoritative product, architecture and engineering contract for the project.

### 0.1 One task per agent run

Unless the human explicitly asks otherwise:

1. Read this file completely before changing code.
2. Determine the **first unfinished task whose dependencies are complete**.
3. Implement **only that task**.
4. Run all checks listed for that task.
5. Fix failures caused by the task.
6. Update only that task's status in the development-plan section.
7. Summarize files changed, checks executed and any unresolved issues.
8. Stop.

Do not opportunistically implement later milestones.

### 0.2 Do not silently redesign the architecture

If a task appears to require violating an architectural rule in this document:

- do not work around the rule silently;
- explain the conflict;
- propose the smallest architecture change;
- wait for human approval before implementing that change.

### 0.3 Prefer simple code over premature framework building

The target is a serious atlas generator, but the early milestones must remain small.

Avoid introducing:

- Django, FastAPI or another web framework;
- a GUI;
- distributed jobs;
- message queues;
- a large ORM;
- Kubernetes;
- plugin frameworks;
- arbitrary dependency injection containers.

This is initially a local command-line publishing tool.

### 0.4 Reproducibility is mandatory

Given the same:

- source catalogue versions;
- atlas definition;
- style definition;
- random seed;
- optimizer version;
- AI review decisions;

NightSky Atlas must be able to reproduce the same layout and final PDF.

Any stochastic algorithm must accept and record an explicit seed.

---

# 1. Product vision

NightSky Atlas generates beautiful, practical paper star charts intended for use at a telescope rather than as an interactive planetarium.

The desired quality level is inspired by the strengths of classic printed atlases such as:

- Pocket Sky Atlas: fast field use, low clutter, practical overview;
- Sky Atlas 2000.0: strong balance between detail and usability;
- Uranometria 2000.0: deep coverage suitable for serious deep-sky observing.

NightSky Atlas must not copy the visual design, page layout or copyrighted creative expression of any existing atlas. These atlases are references for functional quality and information density only.

The eventual product family is:

1. **NightSky Pocket** — compact and fast to use at the telescope.
2. **NightSky Atlas** — the primary general-purpose Dobsonian atlas.
3. **NightSky Deep** — high-density deep-sky atlas approaching Uranometria-class depth.

All three editions must use the same engine.

---

# 2. Non-goals

NightSky Atlas is not intended to become:

- a planetarium;
- a telescope-control application;
- an observation-session planner;
- a SkySafari replacement;
- a photographic sky simulator;
- a real-time sky renderer;
- a general GIS package;
- a web-first application.

An observation planner is a separate project.

The atlas generator may eventually provide reusable chart-generation functionality to other projects, but architecture must not be distorted for that hypothetical use case during the initial development.

---

# 3. Primary user and field-use requirements

The primary user is a visual observer using a Dobsonian telescope.

The printed chart therefore optimizes for:

- star-hopping;
- recognition of stellar patterns;
- low-light readability;
- unambiguous object labels;
- useful deep-sky object selection;
- predictable chart overlap;
- rapid navigation between adjacent pages;
- high print quality;
- black-and-white or restrained-color printing;
- robustness when red light is used in the field.

A chart that is mathematically correct but visually cluttered is a failure.

A chart that looks attractive on screen but is awkward during star-hopping is also a failure.

---

# 4. High-level architecture

The core pipeline is:

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
      ├──────────────► vector renderer ─────► PDF / SVG
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

The architecture deliberately contains an explicit **Layout Document** between astronomy and rendering.

This is the defining architectural difference from a simple catalogue-to-PDF renderer.

---

# 5. Fundamental design law: immutable astronomy, mutable layout

This rule must never be weakened without explicit human approval.

## 5.1 Immutable astronomical facts

Once imported and normalized, layout optimization and AI review may **not** modify:

- object identity;
- right ascension;
- declination;
- source epoch;
- catalogue magnitude values;
- normalized display magnitude except through an explicitly documented conversion algorithm;
- object type;
- major/minor angular dimensions;
- position angle;
- constellation membership derived from coordinates;
- catalogue identifiers;
- chart geometry;
- projection parameters.

## 5.2 Mutable presentation state

The layout system may modify only explicitly permitted presentation properties, for example:

- label candidate selection;
- label offset within a permitted range;
- label alignment;
- leader-line usage;
- leader-line route among allowed choices;
- display-name variant;
- label priority within predefined rules;
- optional-label visibility;
- collision avoidance displacement for decorative elements.

AI output must never directly mutate astronomical objects.

---

# 6. Core domain model

The code must distinguish at least the following concepts.

## 6.1 Catalogue objects

Examples:

```python
Star
DeepSkyObject
ConstellationBoundary
ConstellationLine
NebulaOutline
MilkyWayFeature
```

Catalogue objects represent normalized sky data and have no page coordinates.

## 6.2 ChartDefinition

A `ChartDefinition` describes **what part of the sky should be rendered**.

Expected fields include:

```python
ChartDefinition(
    id="standard-042",
    center_ra_deg=...,      # internal angle convention must be explicit
    center_dec_deg=...,
    width_deg=...,
    height_deg=...,
    projection="stereographic",
    rotation_deg=0.0,
    atlas_id="standard",
)
```

It contains geometry, not visual label placements.

## 6.3 ChartScene

A `ChartScene` contains the astronomical content selected for one chart after projection.

Conceptually:

```python
ChartScene(
    definition=...,
    stars=[...],
    deep_sky_objects=[...],
    constellation_boundaries=[...],
    constellation_lines=[...],
    nebula_outlines=[...],
)
```

Projected objects contain chart-plane coordinates but not final typesetting decisions.

## 6.4 ChartLayout

A `ChartLayout` is the complete machine-readable description of the page to be rendered.

It includes:

- symbol positions and visual properties;
- label objects;
- selected label candidate;
- text metrics;
- grid paths;
- borders;
- chart title;
- neighbour references;
- optional legend elements;
- diagnostics;
- optimizer metadata.

This object must be serializable.

The serialized layout is a first-class build artifact.

Example output:

```text
build/standard/charts/042/
    chart.json
    chart.pdf
    chart.svg
    preview.png
    review.png
    review.json
```

---

# 7. Coordinate and astronomy conventions

These rules must be encoded in tests.

## 7.1 Internal units

Prefer explicit names such as:

- `ra_deg`;
- `dec_deg`;
- `major_axis_arcmin`;
- `position_angle_deg`.

Do not store ambiguous naked numeric angle fields.

Astropy quantities may be used at catalogue/astronomy boundaries, but the internal performance-critical representation may use documented numeric units.

## 7.2 Epoch

Initial atlas coordinates should use a single documented epoch, expected to be **J2000/ICRS-compatible chart coordinates** unless a later design decision explicitly changes this.

Proper motion can be considered later, but is not required for the first atlas prototype.

## 7.3 Orientation

Orientation must be explicit and tested.

The first printed atlas should use a conventional naked-eye chart orientation rather than eyepiece inversion.

Do not add telescope-specific mirror/reversal modes to the MVP.

## 7.4 Projection

The initial projection is **stereographic**.

Reasons:

- conformal locally;
- stellar pattern shapes remain useful for star-hopping;
- well understood mathematically;
- suitable for modest chart fields;
- straightforward to test.

Projection code must be independent of the renderer so alternative projections can be added later.

---

# 8. Catalogue strategy

Catalogue ingestion is isolated from rendering.

## 8.1 Stars

Initial preferred source: **Tycho-2 or another legally distributable catalogue suitable for the chosen stellar magnitude limits**.

The import layer must retain source provenance.

Do not hard-code Tycho column semantics outside its importer.

Required normalized stellar fields for the first useful atlas:

```text
id
ra
Dec
visual magnitude or documented display magnitude
source catalogue
source identifier
```

Optional later fields:

```text
B-V / colour index
proper motion
spectral class
variable-star flags
common names
Bayer designation
Flamsteed designation
```

## 8.2 Deep-sky objects

Initial source: **OpenNGC**, because it is structured and suitable for prototyping.

The normalized DSO model should support:

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

## 8.3 Later catalogues

NightSky Deep may eventually require additional legally compatible datasets for:

- non-NGC/IC galaxies;
- planetary nebulae;
- dark nebulae;
- emission/reflection nebulae;
- galaxy clusters;
- large stellar associations;
- nebula outlines;
- Milky Way brightness contours.

Do not ingest additional catalogues merely to increase object count. Each source requires:

1. license review;
2. provenance metadata;
3. field mapping;
4. duplicate/cross-ID strategy;
5. explicit visual-observing value.

## 8.4 Licensing

The project must maintain a catalogue licensing document before public distribution.

Create later:

```text
docs/DATA_SOURCES.md
```

For every data source include:

- source name;
- source URL/reference;
- version/date;
- license;
- redistribution constraints;
- attribution requirements;
- imported fields;
- transformations performed.

Never assume that data visible through an astronomy service can be freely redistributed.

---

# 9. Storage strategy

The first implementation should optimize for simplicity and repeatable builds.

Recommended split:

- raw downloaded catalogue files: `data/raw/`;
- normalized build data: `data/processed/`;
- metadata/provenance: adjacent JSON/YAML manifest;
- build artifacts: `build/`.

Do not commit large catalogue files unless their license and repository size make that appropriate.

The repository should provide scripts to reproduce processed data from raw inputs.

Potential formats:

- Parquet for large tabular stellar data;
- SQLite for indexed object lookup;
- compact JSON only for small fixtures/tests.

Do not decide between Parquet and SQLite before profiling the first realistic star query.

Tests must use small committed fixtures and must not depend on multi-gigabyte external catalogues.

---

# 10. Atlas definitions

Atlas edition and rendering style are configuration, not separate engines.

Expected configuration files:

```text
atlas/
    pocket.yaml
    standard.yaml
    deep.yaml

styles/
    pocket.yaml
    standard.yaml
    deep.yaml
```

`atlas/*.yaml` controls content and tiling.

`styles/*.yaml` controls visual appearance.

Do not mix those concerns.

## 10.1 Tentative editions

These are goals, not frozen specifications.

### NightSky Pocket

Target characteristics:

- roughly Pocket Sky Atlas class density;
- stellar limit around magnitude 7.5–8;
- selected visually relevant DSO set;
- large fields;
- very low label clutter;
- convenient A4/A5-oriented print use.

### NightSky Atlas

This is the first edition to implement fully.

Target characteristics:

- roughly Sky Atlas 2000.0 class stellar density;
- stellar limit around magnitude 8.5–9;
- richer DSO content;
- practical A4 landscape pages;
- strong focus on 8–16 inch Dobsonian star-hopping.

### NightSky Deep

Target characteristics:

- stellar limit around magnitude 9.75–10 or somewhat deeper where justified;
- much larger DSO catalogue;
- more precise galaxy geometry;
- large nebula outlines;
- higher chart count;
- Uranometria-like observing depth without copying its design.

Final limiting magnitudes, page counts and fields of view must be chosen based on printed prototypes, not by blindly matching historic atlases.

---

# 11. Atlas tiling

A complete atlas consists of overlapping chart definitions.

Requirements:

- every supported declination must be covered;
- adjacent charts must overlap sufficiently for practical star-hopping;
- neighbour page numbers must be derivable;
- polar regions may use different tiling rules;
- no accidental coverage gaps;
- overlap should avoid excessive duplicate page count.

Tiling must have automated coverage tests.

The exact tiling algorithm is not part of the MVP.

Initial development uses manually specified test charts.

---

# 12. Symbol rendering

Symbols must be defined semantically rather than embedded as arbitrary drawing commands.

Examples:

```text
star
open_cluster
globular_cluster
galaxy
planetary_nebula
bright_nebula
dark_nebula
galaxy_cluster
```

## 12.1 Stars

Star symbol size is a monotonic function of magnitude.

Requirements:

- visually distinct bright stars;
- faintest stars remain printable;
- no absurdly large discs;
- magnitude mapping configurable per style;
- output stable across PDF and PNG renderers.

The mapping should be defined mathematically and covered by snapshot/reference tests.

## 12.2 Galaxies

Where source data support it, galaxies should eventually use:

- major axis;
- minor axis;
- position angle.

This is particularly valuable for visual field recognition.

For very small galaxies, enforce a minimum printable symbol size while preserving orientation where practical.

## 12.3 Extended nebulae

Large nebula outlines are a later milestone.

They must use true vector paths derived from source geometry rather than raster backgrounds.

---

# 13. Typography

Typography is a core atlas feature.

The engine must use accurate text metrics.

Preferred stack:

- Cairo for vector graphics;
- Pango/PangoCairo for text shaping and metrics.

Do not place labels using approximate character widths.

Style configuration must control:

- font family;
- font size;
- weight;
- label category;
- object priority;
- spacing;
- halo/background strategy if used.

The final selected fonts must have appropriate redistribution/embedding rights.

---

# 14. Label system

Label placement is the central technical challenge of the project.

## 14.1 Every label has a stable ID

Example:

```text
label:dso:NGC4565
label:star:HIP91262
label:constellation:VIR
```

Stable IDs are mandatory for:

- layout diffs;
- AI issue references;
- regression tests;
- manual override files;
- reproducible optimization.

## 14.2 Candidate placement

The initial candidate model should support the standard compass positions:

```text
N NE E SE S SW W NW
```

Candidate positions include explicit offsets from the anchor object's exclusion zone.

Future versions may add:

- custom radial candidates;
- along-path constellation labels;
- leader-line candidates;
- object-specific candidates.

## 14.3 Label priorities

Priority must be explicit.

Example conceptual ordering:

```text
major/common object name
Messier object
bright NGC/IC
prominent named star
ordinary NGC/IC
fainter optional DSO
minor star designation
```

Do not encode a giant global magic-number list. Use understandable category weights plus local relevance.

## 14.4 Required deterministic collision checks

At minimum:

- label vs label;
- label vs page border;
- label vs important star symbol;
- label vs DSO symbol;
- label vs its own object exclusion zone;
- label vs chart title/metadata;
- leader line vs labels;
- leader line vs important symbols;
- excessive leader-line crossing.

Grid lines should have lower visual priority than labels and may be interrupted if the style calls for it.

---

# 15. Deterministic layout optimizer

The first complete layout must be generated **without AI**.

AI improves a usable layout; it must not be required to make an otherwise broken page valid.

## 15.1 Hard constraints

Hard violations include:

- text outside printable bounds;
- severe label overlap;
- invalid candidate selection;
- references to missing elements;
- invalid geometry;
- overlapping mandatory page furniture.

A page with unresolved hard violations must fail validation.

## 15.2 Soft cost function

A configurable cost function may include terms for:

```text
label-label overlap
label-symbol overlap
label distance from anchor
leader-line length
leader-line crossing
candidate preference
page-edge proximity
local crowding
visual imbalance
```

Every cost component must be separately measurable for diagnostics.

Avoid an opaque single score with no breakdown.

## 15.3 Optimizer strategy

Begin simple:

1. priority-ordered greedy candidate selection;
2. local improvement passes;
3. deterministic conflict repair.

Only add simulated annealing, CP-SAT or another stronger optimizer if benchmark charts demonstrate a clear need.

If stochastic optimization is introduced, seed it explicitly.

---

# 16. Renderer architecture

The renderer must be intentionally boring.

It accepts a `ChartLayout` and draws exactly what that document specifies.

It must not:

- query astronomical catalogues;
- invent labels;
- move labels;
- make content-selection decisions;
- change atlas geometry.

## 16.1 Output types

Required eventually:

- vector PDF page;
- SVG page;
- PNG preview;
- annotated review PNG.

The PDF must retain vector text and lines wherever possible.

## 16.2 Print fidelity

The renderer must reason in physical page units, preferably millimetres or points.

Critical dimensions must never be derived solely from screen pixels.

PNG is a derivative review format, not the layout coordinate system.

---

# 17. Review rendering

AI review needs a machine-friendly representation in addition to the clean chart.

For each chart, generate:

1. clean preview PNG;
2. annotated review PNG;
3. compact review metadata JSON.

## 17.1 Review image annotations

Annotations should allow a vision model to identify elements reliably without hiding the underlying chart.

Possible annotations:

- short label IDs;
- subtle bounding boxes;
- anchor markers;
- numbered high-density regions.

Review annotations are never included in final PDFs.

## 17.2 Full page plus crops

The review pipeline should support:

- one full-page preview for global balance;
- automatically generated high-density crops for fine collision analysis.

Crops must retain a mapping to page coordinates and element IDs.

Do not implement crop-based review before full-page structured review works.

---

# 18. AI review architecture

AI optimization is a first-class subsystem but must remain optional.

The atlas can always be built with AI review disabled.

## 18.1 Provider abstraction

Define an interface conceptually equivalent to:

```python
class ChartReviewer(Protocol):
    def review(self, request: ReviewRequest) -> ReviewResult:
        ...
```

OpenRouter is the first external implementation.

The rest of the application must not import OpenRouter-specific request structures.

Expected implementations eventually:

```text
MockReviewer
OpenRouterReviewer
RecordedReviewer
```

A `RecordedReviewer` allows deterministic replay of previously accepted AI responses.

## 18.2 OpenRouter configuration

Model selection must be configuration-driven.

Example:

```yaml
ai:
  enabled: false
  provider: openrouter
  reviewer_model: "..."
  fallback_models: []
  max_iterations: 4
  max_cost_per_chart_usd: 0.05
```

Never hard-code model names in layout logic.

Model prices and availability change; configuration must permit cheap model benchmarking without code changes.

## 18.3 Structured AI output only

The AI reviewer must return a validated structured schema.

Never parse prose instructions such as:

> move the M51 label a bit to the left

Instead require something like:

```json
{
  "page_score": 8.8,
  "issues": [
    {
      "element_id": "label:dso:NGC5194",
      "issue_type": "ambiguous_association",
      "severity": 7,
      "action": {
        "type": "select_candidate",
        "candidate": "SW"
      }
    }
  ]
}
```

All responses must pass schema validation before they affect layout.

## 18.4 Allowed AI actions

Initial action whitelist:

```text
select_candidate
show_optional_label
hide_optional_label
use_leader_line
remove_leader_line
select_display_name_variant
```

Later, tightly bounded offset adjustments may be added.

Any unknown action is rejected.

## 18.5 AI cannot directly approve invalid geometry

After every AI change:

1. apply permitted actions to a copied layout;
2. run deterministic validation;
3. compute cost metrics;
4. reject changes that introduce hard violations;
5. render again only if accepted.

AI is advisory, never authoritative over geometry.

---

# 19. AI optimization loop

Conceptual algorithm:

```text
layout_0 = deterministic_layout(scene)
validate(layout_0)
render(layout_0)

for iteration in range(max_iterations):
    review = reviewer.review(rendered_page, metadata)

    if review has no significant issues:
        break

    proposal = apply_allowed_actions(layout, review)

    if proposal violates hard constraints:
        reject invalid actions

    if proposal is accepted:
        layout = proposal
        render(layout)
    else:
        stop or request another review depending on policy
```

Termination conditions must include:

- no significant issues;
- minimum quality score reached;
- no accepted changes;
- iteration limit;
- cost budget reached;
- repeated layout hash detected.

Infinite AI loops are forbidden.

---

# 20. AI cost control

AI review must be designed for hundreds of atlas pages.

Track per request:

- provider;
- model;
- input token estimate/actual usage if available;
- output tokens;
- cost if available;
- latency;
- page ID;
- review iteration;
- prompt/schema version.

Persist an audit log.

The system should eventually support a tiered policy:

```text
cheap vision reviewer
        │
        ├── good page ──► done
        │
        └── uncertain/problematic
                    │
                    ▼
             stronger reviewer
```

Do not implement escalation until reviewer benchmarking exists.

---

# 21. AI benchmark suite

Model choice must be empirical.

Create a benchmark set from difficult sky regions.

Initial candidates:

- Virgo/Coma galaxy fields;
- Cygnus Milky Way fields;
- Sagittarius dense fields;
- Orion extended-nebula region;
- M31 region;
- Pleiades / bright-star labels;
- sparse high-galactic-latitude field;
- chart-edge-heavy field.

A benchmark fixture should contain:

- rendered page;
- layout document;
- known layout problems;
- expected acceptable actions;
- forbidden actions;
- human quality notes.

Evaluate models on:

```text
true issue detection
false positives
valid element references
action usefulness
schema compliance
repeatability
cost per page
```

The cheapest model meeting quality requirements should be preferred.

---

# 22. Manual overrides

Fully automatic generation is the goal, but final publishing must support deterministic human overrides.

Never patch renderer code for one troublesome object.

Instead support an override document such as:

```yaml
chart: standard-042
labels:
  label:dso:NGC4565:
    candidate: SW
    locked: true
```

Overrides must:

- be reviewable in Git;
- use stable element IDs;
- apply after initial layout generation;
- be respected by later optimizers when locked;
- remain edition-specific where necessary.

Manual overrides are an escape hatch, not the primary layout method.

---

# 23. Validation

A chart cannot be considered publishable because it rendered successfully.

## 23.1 Structural validation

Check:

- unique IDs;
- finite coordinates;
- known object references;
- valid candidate selections;
- page dimensions;
- no missing required page elements.

## 23.2 Geometry validation

Check:

- printable bounds;
- hard collisions;
- symbol dimensions;
- text metrics;
- grid clipping;
- neighbour references where applicable.

## 23.3 Atlas-level validation

Eventually check:

- complete sky coverage;
- no unintended gaps;
- expected overlaps;
- unique chart numbering;
- consistent neighbouring-chart links;
- index completeness;
- all PDF pages generated.

---

# 24. Testing strategy

Tests must emphasize deterministic geometry rather than only code coverage.

## 24.1 Unit tests

Required areas:

- coordinate conversion;
- stereographic projection;
- angular-distance calculations;
- chart clipping;
- magnitude-to-symbol mapping;
- ellipse orientation;
- label candidate generation;
- rectangle/path collision checks;
- cost-function components;
- AI action validation;
- serialization round trips.

## 24.2 Golden/reference tests

Use small intentional reference fixtures for:

- a sparse chart;
- a crowded galaxy field;
- a dense star field.

Avoid fragile full-PDF byte comparisons.

Prefer comparing:

- layout JSON;
- object counts;
- key element positions within tolerance;
- selected label candidates;
- deterministic render metadata.

Optional raster perceptual-diff tests may be added later.

## 24.3 Property tests

Useful invariants include:

- center of projection maps to chart center;
- projected coordinates remain finite inside supported FOV;
- increasing faintness never increases star diameter;
- serialization preserves layout state;
- hard validator never accepts out-of-page mandatory labels.

---

# 25. Performance targets

Do not optimize prematurely, but architecture should permit a complete atlas build on a normal development workstation.

The first meaningful target:

- one standard-density A4 chart should build interactively during development;
- deterministic layout should take seconds, not minutes;
- complete atlas generation can later be parallelized by page because chart layouts are largely independent.

Do not introduce multiprocessing until single-page behavior is correct and measured.

AI calls may later be parallelized within provider rate limits, but deterministic builds and cache behavior come first.

---

# 26. Caching

The project will benefit from content-addressed or metadata-aware caches.

Potential cached stages:

```text
catalogue query -> ChartScene
ChartScene + style -> initial ChartLayout
ChartLayout -> preview
review request hash -> AI ReviewResult
final ChartLayout -> PDF page
```

Caching is a later milestone.

AI responses should eventually be cacheable/replayable to avoid paying for identical reviews repeatedly.

---

# 27. Logging and diagnostics

Build commands must provide useful diagnostics without flooding output.

At chart level report:

```text
stars selected
deep-sky objects selected
labels requested
labels placed
optional labels hidden
hard violations
soft cost before optimization
soft cost after optimization
AI iterations
AI cost
```

Debug mode should be able to render:

- bounding boxes;
- exclusion zones;
- candidate positions;
- collision edges;
- label IDs;
- object IDs.

These diagnostics are important enough to design early.

---

# 28. Command-line interface

A coherent CLI should emerge gradually.

Target commands may include:

```bash
nightsky data import-stars ...
nightsky data import-openngc ...

nightsky chart render test-virgo --style standard
nightsky chart validate test-virgo
nightsky chart review test-virgo
nightsky chart optimize test-virgo

nightsky atlas build standard
nightsky atlas validate standard
```

Do not implement the entire final CLI at once.

Use a lightweight CLI library only if it improves clarity; `argparse` is sufficient initially.

---

# 29. Configuration principles

Use YAML for human-edited atlas/style configuration unless a later need justifies another format.

Configuration must be schema-validated.

Avoid:

- arbitrary nested dictionaries passed through the whole system;
- silently ignored config keys;
- configuration values without units.

Prefer typed configuration dataclasses/models.

Unknown configuration keys should fail fast.

---

# 30. Repository structure

Target structure:

```text
nightsky-atlas/
├── AGENTS.md
├── README.md
├── pyproject.toml
├── Makefile
│
├── src/
│   └── nightsky_atlas/
│       ├── __init__.py
│       ├── cli.py
│       │
│       ├── catalog/
│       │   ├── models.py
│       │   ├── store.py
│       │   ├── tycho.py
│       │   └── openngc.py
│       │
│       ├── astronomy/
│       │   ├── angles.py
│       │   └── coordinates.py
│       │
│       ├── projection/
│       │   ├── base.py
│       │   └── stereographic.py
│       │
│       ├── atlas/
│       │   ├── config.py
│       │   └── tiling.py
│       │
│       ├── scene/
│       │   ├── models.py
│       │   └── builder.py
│       │
│       ├── layout/
│       │   ├── models.py
│       │   ├── labels.py
│       │   ├── candidates.py
│       │   ├── collision.py
│       │   ├── scoring.py
│       │   ├── optimizer.py
│       │   ├── overrides.py
│       │   └── validation.py
│       │
│       ├── render/
│       │   ├── cairo.py
│       │   ├── symbols.py
│       │   ├── text.py
│       │   ├── preview.py
│       │   └── review.py
│       │
│       ├── review/
│       │   ├── models.py
│       │   └── crops.py
│       │
│       ├── ai/
│       │   ├── base.py
│       │   ├── schema.py
│       │   ├── actions.py
│       │   ├── openrouter.py
│       │   └── recorded.py
│       │
│       └── build/
│           ├── chart.py
│           └── atlas.py
│
├── atlas/
│   ├── pocket.yaml
│   ├── standard.yaml
│   └── deep.yaml
│
├── styles/
│   ├── pocket.yaml
│   ├── standard.yaml
│   └── deep.yaml
│
├── data/
│   ├── raw/
│   ├── processed/
│   └── fixtures/
│
├── benchmarks/
│   └── ai_review/
│
├── overrides/
│
├── tests/
│
├── docs/
│   ├── ARCHITECTURE.md
│   ├── DATA_SOURCES.md
│   ├── CARTOGRAPHY.md
│   └── AI_REVIEW.md
│
└── build/
```

Do not create empty packages speculatively. Add directories as milestones require them.

---

# 31. Python engineering rules

## 31.1 Supported Python

Use a modern supported Python version. Prefer Python 3.13 unless the development environment requires another supported 3.x release.

Record the minimum supported version in `pyproject.toml`.

## 31.2 Type hints

Public domain models and important pipeline interfaces must be typed.

Do not pursue maximal typing ceremony inside trivial local functions.

## 31.3 Dataclasses vs validation models

Prefer standard dataclasses for internal immutable/simple domain models.

Use a schema-validation library only where it provides clear value, particularly:

- external configuration;
- external AI JSON responses.

Avoid coupling every internal object to a validation framework.

## 31.4 Formatting/linting

Recommended baseline:

```text
ruff
pytest
```

Add a type checker once the first interfaces stabilize.

## 31.5 Dependencies

Every new runtime dependency must justify itself.

Likely justified:

```text
numpy
astropy
pycairo
PyGObject / Pango bindings or equivalent text integration
PyYAML or equivalent
httpx (when OpenRouter is introduced)
```

Do not add large scientific or web stacks for convenience if a small implementation suffices.

---

# 32. Build/repository commands

As the repository matures, provide a small stable command surface through `make` or equivalent.

Desired eventual commands:

```bash
make setup
make test
make lint
make check
make sample
make benchmark-ai
```

`make check` should become the standard pre-commit verification command.

Agents should use repository-provided commands rather than inventing alternate check sequences once these commands exist.

---

# 33. Security and secrets

OpenRouter credentials are secrets.

Rules:

- never commit API keys;
- read credentials from environment variables;
- provide `.env.example` only with placeholder values if needed;
- scrub secrets from logs;
- tests must not require live credentials;
- live AI integration tests must be explicitly opt-in.

Recommended variable:

```text
OPENROUTER_API_KEY
```

---

# 34. Quality bar

The project has three quality levels.

## Level A — technically correct

- objects appear at correct coordinates;
- projection is correct;
- PDF is valid;
- no hard layout failures.

This is necessary but not sufficient.

## Level B — practically usable

- labels are readable;
- star patterns are recognizable;
- useful DSO density;
- chart navigation works;
- printed page works under red light.

This is the minimum for a released atlas.

## Level C — publication quality

- visually balanced pages;
- excellent typography;
- very low ambiguity;
- difficult dense fields remain readable;
- consistent visual rhythm across the atlas;
- minimal or zero manual cleanup.

The long-term objective is Level C.

---

# 35. Reference development fields

Two sky regions are mandatory development benchmarks.

## 35.1 Virgo / Coma

Purpose:

- many nearby galaxies;
- dense DSO labels;
- ambiguous object-label relationships;
- stress test for leader lines and label optimization.

The exact chart center/FOV should be committed once the first chart prototype exists.

## 35.2 Cygnus

Purpose:

- high stellar density;
- Milky Way context;
- extended nebulae later;
- stress test for star symbol scale and faint-label legibility.

These fields should be kept through the project as regression charts.

---

# 36. Development philosophy

The project should proceed vertically rather than building every subsystem in isolation.

The preferred sequence is:

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

Do not spend weeks designing complete catalogue infrastructure before the first page is visible.

---

# 37. Development plan

Status markers:

```text
[ ] not started
[~] in progress
[x] complete
[!] blocked / human decision required
```

The plan is intentionally granular so a coding agent can execute one task at a time.

---

## M0 — Repository and executable skeleton

### [x] M0.1 Create repository skeleton

Create only the minimum initial structure:

```text
pyproject.toml
README.md
src/nightsky_atlas/
tests/
Makefile
.gitignore
```

Requirements:

- installable package;
- `python -m nightsky_atlas --help` works;
- pytest runs;
- Ruff runs;
- `make test`, `make lint`, `make check` work.

Do not create the full future directory tree yet.

Acceptance checks:

```bash
python -m nightsky_atlas --help
make check
```

### [x] M0.2 Add typed configuration foundation

Implement typed loading for a minimal chart/style YAML fixture.

Requirements:

- unknown keys fail;
- page units explicit;
- no atlas tiling yet;
- tests cover valid/invalid configuration.

Acceptance:

```bash
make check
```

---

## M1 — Geometry prototype

### [x] M1.1 Define core chart geometry models

Implement:

- `ChartDefinition`;
- page geometry;
- chart-plane point representation;
- explicit units/conventions.

No rendering yet.

Acceptance:

- serialization/repr tests;
- invalid dimensions rejected.

### [x] M1.2 Implement stereographic projection

Implement forward projection from RA/Dec relative to chart center.

Requirements:

- mathematically documented;
- no dependency on renderer;
- tests for center, cardinal offsets and symmetry;
- finite behavior over supported chart FOV.

Acceptance:

```bash
pytest tests/projection/
make check
```

### [x] M1.3 Implement page transform and clipping

Convert projection coordinates into physical page coordinates.

Requirements:

- millimetre/point-aware mapping;
- printable chart rectangle;
- reliable in/out-of-chart test;
- tests for borders and rotation=0.

Do not implement rotated charts unless needed later.

---

## M2 — First real stars

### [x] M2.1 Define normalized Star model

Implement a catalogue-independent stellar model with provenance.

Use a tiny committed fixture.

### [x] M2.2 Implement sample star catalogue loader

Load a small CSV/fixture sufficient for one test field.

Do not implement full Tycho ingestion yet.

### [x] M2.3 Build first ChartScene

Given a `ChartDefinition`, select and project stars into a `ChartScene`.

Acceptance:

- known fixture star counts;
- projected positions tested;
- off-chart stars excluded.

---

## M3 — First visible PDF

### [x] M3.1 Add Cairo page renderer

Render:

- page background;
- chart border;
- star circles;
- minimal title.

Output:

```text
PDF
PNG preview
```

No labels.

Goal: first astronomically correct printed star field.

### [x] M3.2 Implement magnitude-to-star-size mapping

Requirements:

- configurable;
- monotonic;
- sensible minimum/maximum print diameter;
- tests.

Create a magnitude scale diagnostic page if useful.

### [x] M3.3 Establish first standard test chart

Commit a deterministic Virgo or Cygnus test definition and small source fixture.

Generate a sample page through a documented command.

This is the first visual human checkpoint.

**Human checkpoint:** inspect PDF at 100% and preferably print once.

Do not proceed to complex labels until page scale and star appearance are accepted.

---

## M4 — Real catalogue import

### [x] M4.1 Implement star catalogue import pipeline

Implement importer for the selected full star source.

Requirements:

- source provenance;
- normalized magnitude field;
- processed output manifest;
- deterministic import;
- no network download hidden inside normal atlas builds.

### [x] M4.2 Implement indexed star queries

Choose the simplest storage/query approach that performs adequately.

Benchmark realistic standard-chart queries before optimizing further.

Record benchmark results in docs or test notes.

### [x] M4.3 Verify standard chart stellar density

Render Cygnus and a sparse field to compare practical density at candidate limiting magnitudes.

**Human checkpoint:** choose the provisional standard-edition stellar limit and star-size curve.

---

## M5 — Deep-sky foundation

### [x] M5.1 Define normalized DeepSkyObject model

Support at least:

- IDs;
- RA/Dec;
- type;
- magnitude;
- major/minor axes;
- position angle;
- common name;
- provenance.

### [x] M5.2 Implement OpenNGC sample loader

Start with a committed fixture sufficient for Virgo.

### [x] M5.3 Render basic DSO symbols

Implement semantic symbols for the common object classes.

Keep styling simple but print-safe.

### [x] M5.4 Add real OpenNGC import

Create reproducible normalized processed data plus provenance manifest.

### [x] M5.5 Render oriented galaxy ellipses

Use major/minor dimensions and position angle when available.

Add minimum printable symbol sizing.

Tests must verify orientation transformations.

---

## M6 — Text and initial labels

### [x] M6.1 Integrate Pango text metrics

Implement exact text measurement in physical page coordinates.

Acceptance:

- measured bounds are available before rendering;
- renderer and collision system use the same metrics.

### [x] M6.2 Define Label and LabelCandidate models

Requirements:

- stable IDs;
- target object ID;
- candidate list;
- selected candidate;
- priority;
- mandatory/optional status;
- text bounds;
- serialization.

### [x] M6.3 Generate compass label candidates

Implement N/NE/E/SE/S/SW/W/NW placements around stellar/DSO exclusion geometry.

### [x] M6.4 Render unoptimized labels

Render labels using a deterministic fixed candidate preference.

This page is expected to contain collisions.

Its purpose is to prove text/layout separation.

---

## M7 — Collision and validation engine

### [x] M7.1 Implement geometric primitives

Implement/test:

- rectangles;
- circles/ellipses approximations as needed;
- intersection tests;
- page bounds;
- distance metrics.

### [x] M7.2 Implement hard label collision checks

Detect at least:

- label-label;
- label-page;
- label-important-star;
- label-DSO.

Expose issues with stable IDs.

### [x] M7.3 Implement layout validator

A layout with unresolved hard violations must fail validation.

CLI should print concise diagnostics.

### [x] M7.4 Add debug rendering

Optional flags render:

- label boxes;
- object exclusion zones;
- element IDs;
- candidate points.

This is required before optimizer work.

---

## M8 — Deterministic label optimization

### [x] M8.1 Implement priority-ordered greedy placement

Place labels by priority using the lowest-cost valid candidate.

Optional labels may remain hidden if no acceptable candidate exists.

### [x] M8.2 Implement decomposed soft-cost function

Create explicit metrics for:

- overlap penalties;
- anchor distance;
- edge proximity;
- preferred candidate direction;
- crowding.

Diagnostics must expose component values.

### [x] M8.3 Implement local repair pass

Attempt candidate swaps for conflict/cost reduction after greedy placement.

Keep behavior deterministic.

### [x] M8.4 Establish Virgo label benchmark

Generate a dense Virgo chart containing enough galaxies to stress the optimizer.

Save:

- input scene summary;
- resulting layout JSON;
- debug PNG;
- clean PDF.

**Human checkpoint:** judge whether the deterministic result is already field-usable.

If not, improve deterministic algorithms before AI integration.

---

## M9 — Publication-oriented chart furniture

### [x] M9.1 Add coordinate grid

Implement configurable RA/Dec grid with clipping.

Labels have priority over grid lines where style requires.

### [x] M9.2 Add chart title and scale information

Keep page furniture separate from sky labels.

### [x] M9.3 Add neighbour placeholders/navigation model

For manually defined development charts, support neighbour references even before automatic atlas tiling exists.

### [x] M9.4 Refine print typography/style configuration

Move visual constants out of code into typed style configuration.

**Human checkpoint:** standard test pages should now look like an intentional atlas, not a plotting-library output.

---

## M10 — Review artifacts

### [x] M10.1 Implement review PNG renderer

Generate annotated image with element IDs/bounding boxes while preserving legibility.

### [x] M10.2 Implement ReviewRequest model

Include only the information a reviewer needs:

- page ID;
- image(s);
- visible relevant element metadata;
- permitted actions;
- current quality diagnostics;
- schema/prompt version.

Avoid dumping an enormous full layout unnecessarily.

### [x] M10.3 Implement ReviewResult schema

Strictly validate:

- referenced element IDs;
- issue types;
- severities;
- action type;
- candidate values.

Malformed reviews must never alter a layout.

---

## M11 — OpenRouter AI reviewer

### [x] M11.1 Implement reviewer interface and MockReviewer

All AI optimization logic must be testable without a network.

### [x] M11.2 Implement OpenRouterReviewer

Requirements:

- environment-based API key;
- configurable model;
- image input;
- structured JSON response;
- timeouts;
- retry policy only for transient failures;
- no silent fallback to prose parsing;
- usage/cost metadata capture where available.

Live tests must be opt-in.

### [x] M11.3 Implement AI action application

Apply only whitelisted actions to copied layout state.

Then run deterministic validation.

Reject invalid actions individually where practical.

### [x] M11.4 Implement one-step AI review command

Example target behavior:

```bash
nightsky chart review test-virgo --model MODEL
```

Outputs review JSON but does not yet automatically iterate.

**Human checkpoint:** manually inspect whether the selected cheap vision model identifies genuinely bad label placements.

---

## M12 — AI optimization loop

### [x] M12.1 Implement bounded optimization loop

Support:

- max iterations;
- minimum target score;
- repeated-layout detection;
- no-change termination;
- cost budget.

### [x] M12.2 Persist review history

For every iteration save:

```text
layout hash
review request metadata
review result
actions accepted/rejected
new layout hash
usage/cost
```

### [x] M12.3 Implement RecordedReviewer/replay

A previous AI optimization must be reproducible offline.

### [x] M12.4 Compare before/after layout metrics

AI changes should not be accepted blindly because a model suggests them.

Record whether deterministic cost improved/worsened while allowing human-quality judgments to be represented separately.

---

## M13 — AI benchmark and model selection

### [x] M13.1 Build first benchmark dataset

Create approximately 10–20 curated page/problem examples from Virgo, Cygnus and additional representative fields.

### [x] M13.2 Implement benchmark runner

Run a configured model against recorded benchmark inputs.

Collect:

- schema compliance;
- correct issue detection;
- false positives;
- valid actions;
- cost;
- latency.

### [x] M13.3 Compare cheap multimodal models through OpenRouter

Do not encode assumptions about which provider/model wins.

Select the default model based on measured quality/cost.

**Human checkpoint:** approve default reviewer model and fallback policy.

---

## M14 — Standard atlas tiling

### [x] M14.1 Define standard-edition page/FOV target

Use printed test experience rather than historical-atlas imitation alone.

Freeze provisional:

- page size;
- chart drawing area;
- FOV strategy;
- overlap target;
- stellar magnitude limit.

### [x] M14.2 Implement declination-band tiling

Generate complete chart definitions programmatically.

Handle RA convergence with declination.

### [x] M14.3 Implement polar charts

Use appropriate polar tiling/projection behavior if required.

### [x] M14.4 Add coverage validator

Automated test for complete sky coverage and overlap.

### [x] M14.5 Assign chart numbering and neighbours

Ensure stable deterministic IDs/page numbers.

---

## M15 — Complete Standard atlas build

### [x] M15.1 Implement atlas build orchestration

Pipeline:

```text
chart definitions
→ scenes
→ deterministic layouts
→ validation
→ optional AI review
→ final page PDFs
```

Support building a subset of pages for development.

### [x] M15.2 Merge page PDFs

Create one atlas PDF while preserving vector content.

### [x] M15.3 Add atlas front matter/minimal legend

Keep first version small.

### [x] M15.4 Add build manifest

Record:

- Git commit;
- catalogue versions;
- configs;
- AI reviewer/model;
- AI prompt/schema versions;
- per-page layout hashes;
- build timestamp.

### [~] M15.5 Produce Standard alpha atlas

Generate the complete atlas.

**Major human checkpoint:** print/use representative pages at a telescope.

Evaluate:

- star-hop usability;
- faint star visibility;
- page density;
- typography under red light;
- object-label ambiguity;
- page navigation.

Do not begin Pocket/Deep merely because a full PDF exists. Standard must first be useful.

---

## M16 — Manual override workflow and publication hardening

### [x] M16.1 Implement override files

Stable ID-based overrides, including locked label candidates.

### [ ] M16.2 Implement atlas-wide issue report

Summarize pages with:

- hard errors;
- high deterministic costs;
- AI warnings;
- manual overrides;
- missing data.

### [ ] M16.3 Add final preflight command

Target:

```bash
nightsky atlas validate standard --publication
```

Fail on any unresolved publication blocker.

### [ ] M16.4 Create data-source/license documentation

`docs/DATA_SOURCES.md` must be complete before redistribution.

---

## M17 — Pocket edition

Only begin after Standard is stable.

### [ ] M17.1 Define Pocket atlas configuration

Reduce:

- stellar depth;
- DSO density;
- label density;

Increase field size and field usability.

### [ ] M17.2 Implement Pocket tiling

May differ substantially from Standard.

### [ ] M17.3 Tune Pocket style

Prioritize quick recognition and uncluttered navigation.

### [ ] M17.4 Build and field-test Pocket alpha

---

## M18 — Deep edition data expansion

Only begin after Standard/Pocket architecture proves stable.

### [ ] M18.1 Define Deep data requirements

Determine which additional object catalogues materially improve visual observing.

### [ ] M18.2 Perform license review for each proposed dataset

No ingestion before license/provenance decision.

### [ ] M18.3 Implement additional catalogue importers

Keep source-specific logic isolated.

### [ ] M18.4 Implement duplicate/cross-ID resolution

Must be deterministic and documented.

### [ ] M18.5 Raise stellar limiting magnitude and profile performance

Only optimize storage/query code based on measured bottlenecks.

---

## M19 — Extended structures

### [ ] M19.1 Add nebula outlines

Vector boundaries where suitable data exist.

### [ ] M19.2 Add Milky Way representation

Choose a print-friendly representation based on legal source data.

### [ ] M19.3 Add dark nebula representation

If included, design symbols/contours for field usefulness rather than decorative appearance.

### [ ] M19.4 Revisit AI review for complex extended structures

Expand review schema only if needed.

---

## M20 — Deep atlas

### [ ] M20.1 Define Deep page geometry and tiling

Likely larger page count / smaller FOV.

### [ ] M20.2 Tune high-density label optimization

This may justify stronger optimization algorithms.

Do not introduce them earlier without evidence.

### [ ] M20.3 Benchmark AI escalation policy

Evaluate cheap-first / strong-model-on-hard-pages workflow.

### [ ] M20.4 Generate Deep alpha

### [ ] M20.5 Telescope field testing

Use difficult galaxy fields and dense Milky Way regions.

---

# 38. Explicit deferred features

The following are intentionally deferred until the core atlas is proven:

- constellation artwork;
- colour-rich artistic Milky Way rendering;
- eyepiece orientation modes;
- interactive web viewer;
- desktop GUI;
- user-specific custom atlas wizard;
- automatic observing-list integration;
- finder-circle overlays;
- telescope/FOV overlays;
- variable-star specialist charts;
- photographic plate overlays;
- automatic translated editions;
- print-on-demand integration.

Agents must not implement these merely because they seem useful.

---

# 39. Key human decision checkpoints

Stop and request explicit human evaluation at these points:

1. **M3.3** — first printed stellar chart: scale/star appearance.
2. **M4.3** — standard stellar limiting magnitude.
3. **M8.4** — deterministic Virgo label quality.
4. **M9.4** — typography/cartographic visual identity.
5. **M11.4** — whether AI reviewer sees useful visual problems.
6. **M13.3** — default OpenRouter model based on benchmark.
7. **M14.1** — final Standard page geometry/FOV/overlap.
8. **M15.5** — complete Standard alpha and telescope field test.
9. Before each additional external catalogue is adopted.
10. Before defining final Pocket or Deep publication specifications.

Do not substitute coding-agent preference for these product decisions.

---

# 40. Definition of MVP

The MVP is deliberately much smaller than a complete atlas.

MVP is reached when the project can reproducibly generate **two publication-intent A4 test charts**:

- Virgo/Coma;
- Cygnus.

Each must contain:

- real stars;
- real OpenNGC DSO data;
- stereographic projection;
- meaningful star magnitude sizing;
- semantic DSO symbols;
- Pango-quality labels;
- deterministic label optimization;
- chart border/grid/basic furniture;
- vector PDF;
- preview PNG;
- review PNG;
- serialized layout JSON;
- hard validation with zero unresolved violations.

AI review is planned from the start but is **not required to define the basic MVP as usable**.

A second milestone, **AI-MVP**, is reached when a cheap OpenRouter vision model can review those pages, return schema-valid issue/action data, and produce at least some demonstrably useful automatic label improvements without corrupting geometry.

---

# 41. Definition of first release candidate

A first Standard release candidate requires:

- complete sky coverage;
- stable chart numbering;
- final source/provenance documentation;
- complete deterministic build from clean checkout + prepared catalogue data;
- no hard validation errors;
- successful AI review or explicitly recorded skip/override policy per page;
- deterministic replay of accepted AI decisions;
- atlas-wide PDF generation;
- printed field testing;
- all known high-severity cartographic issues fixed or explicitly accepted.

---

# 42. What success looks like

The project is successful when an observer can take the generated atlas to a Dobsonian telescope and treat it as a real observing tool rather than as a software demo.

The strongest technical success criterion is not the number of catalogued objects or the sophistication of the AI system.

It is this:

> A complete atlas can be regenerated automatically from source data and configuration, and the resulting pages require little or no manual label cleanup while remaining beautiful, readable and reliable at the telescope.

That is the standard against which architectural decisions should be judged.
