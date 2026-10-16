# Atlas build refactoring audit

Branch: `refactor/atlas-build`; baseline: `ee980e9`.
Scope: build coordination only; catalogue data, edition/style configuration,
projection, selection, optimization and drawing rules remain unchanged.

## Original phases and responsibilities

`build_atlas()` owns publication staging and the atomic directory swap, retaining
an existing publication as a backup. `_build_atlas_impl()` performs all work:

1. Load atlas/style/shared catalogues; select main charts; calculate geometric
   detail relationships; resolve detail stellar/DSO profiles.
2. Record sources, geometry inputs and fingerprints; run publication preflight;
   load overrides, star names and WDS overlays.
3. Build and optimize every included detail chart before main charts. Verify
   detail labels for main-chart fallback and intentional stellar exclusions.
4. Open the combined PDF; establish navigation; draw introduction, field guide,
   optional front directory and overview pages; retain locator geometry.
5. Dispatch main-chart workers, consume them in chart order, draw combined
   pages, collect diagnostics, index sources and applied overrides.
6. Verify excluded star names are printed on an included detail; incorporate
   detail index sources; construct the atlas index; render detail pages.
7. Append credits, index and optional back directory; finish the combined PDF.
8. Recheck publication inputs; build manifest, draft report and artifact
   checksums; validate publication output; return paths and page diagnostics.

The parent process owns the combined Cairo PDF and navigation. Spawned workers
write individual main-chart PDFs/PNGs and return scenes/labels/diagnostics;
results are consumed in definition order with a bounded submission queue.
Details are prepared serially before workers because suppression eligibility
must depend on their actually placed, validated labels.

## Baseline

- `build/atlas.py`: 2,594 Python lines.
- Entire `build/`: 3,466 Python lines across five modules.
- Entire `src/`: 37,821 Python lines.
- `_build_atlas_impl()`: 1,144 lines, 317 AST statement nodes, 92 branch nodes
  (`if`, `for`, `while`, conditional expression, exception handler or match),
  plus 29 extra Boolean operands. This is a transparent structural count,
  not a claim of a standard cyclomatic-complexity measurement.

Raw measurements and comparison proofs live under `build/atlas-refactor/`.

## Identified simplifications

- The second detail-preparation branch is unreachable: the first detail loop
  unconditionally fills the prepared mapping, and the index loop already
  indexes every selected entry before the supposed fallback can run.
- Detail style, scale/profile limits, presentation and faint-store eligibility
  are recalculated for rendering and manifest generation despite preparation
  having resolved them already.
- The same chart-directory drawing sequence exists for front and back placement.
- Main/detail index inputs and fallback-candidate diagnostics are duplicated.
- Selected main-chart IDs are repeatedly rebuilt inside the detail-filter
  predicate. Compute that set once.
- Source-path arguments are repeated when checking publication input stability;
  retain the resolved paths used for the initial provenance snapshot.

Keep main-chart optimization and fallback behavior unchanged. Distinct main
and detail semantics are deliberate: stellar exclusions apply only to main
charts; details can use different stellar/DSO profiles and UCAC4; only main
charts carry locators, detail markers and constellation-index sources.

## Implemented boundaries

- `build/atlas.py`: public entry, staging, chart plan, input provenance, main
  worker dispatch/composition, detail output, index and final artifact/report
  coordination. Public signatures and result types remain at the same imports.
- `build/details.py`: detail profile resolution, content/style overrides,
  one-time scene/layout preparation and verification of detail label coverage.
- `build/document.py`: combined PDF ownership/navigation, front matter,
  directories, overview pages, credits and index-page composition.
- `build/chart.py`: shared single-chart input/context creation and the existing
  mandatory-label error check used by main and detail builds.

The phase records group only cohesive data: selected geometry (`_ChartPlan`),
source snapshots (`_BuildProvenance`), accumulated page/index diagnostics
(`_AtlasPages`), PDF ownership (`AtlasPdf`) and opening-page metadata
(`OpeningPages`). They are plain dataclasses, not a new execution framework.
The worker shared state and public result records retain their existing shape.

Keep publication staging, ordered/bounded spawned workers, individual chart
rendering, detail fallback rules and every optimization call unchanged. Index
collection still uses constellation boundaries only on main charts. Detail
layouts are verified before main labels may fall back to them, and rendering
must consume those exact prepared layouts.

## Validation protocol

The baseline full suite completes before production changes. The graphics
baseline process imports the original build modules before refactoring; its
Pocket/Standard builds finish and all Deep workers initialize before source
replacement. The remaining experimental baseline cases execute serially in
that original process. The original atlas source is retained at
`build/atlas-refactor/baseline/atlas.py`.

Proofs use local Tycho-2, the existing UCAC4 supplement where configured,
normalized DSO data and the actual edition/style files. No catalogue or atlas
configuration is modified. Pocket/Deep use two workers; Standard and the
experimental presets use one. Every case includes a combined vector PDF,
individual chart PDFs, 100-dpi PNG previews, text extraction, navigation
destinations and an ordinary output-validation pass. The combined PDF is
rasterized with Poppler at 100 dpi; all page pixels and preview bytes are
compared, not PDF timestamps or binary object ordering.

Manifest comparisons exclude only `generated_utc`, artifact hashes, and the
changed `input_fingerprints.code` entry. Each manifest checksum is independently
validated against its own artifact; PDF content is compared as pixels/text,
and PNG/draft-report bytes are compared directly. All other
source fingerprints, counts, costs, layout hashes, indices, detail references,
suppressions, intentional exclusions and issue records must be equal. Draft
reports, extracted PDF text and navigation destinations must also be equal.

Graphics verification and the after-suite run overlap to avoid serializing
long astronomical optimization and coverage calculations. Their timings are
indicative, not a controlled speed benchmark. A separate quiet Pocket repeat
is used for the representative build-time comparison after those runs finish.

## Structural outcome

| Metric | Before | After |
| --- | ---: | ---: |
| `build/atlas.py` lines | 2,594 | 1,859 |
| Entire `build/` lines | 3,466 | 3,817 |
| Entire `src/` lines | 37,821 | 38,172 |
| Build modules | 5 | 7 |
| Build functions/methods | 54 | 71 |
| `_build_atlas_impl` lines | 1,144 | 259 |
| `_build_atlas_impl` AST statements | 317 | 51 |
| `_build_atlas_impl` branch nodes | 92 | 17 |
| `_build_atlas_impl` extra Boolean operands | 29 | 3 |
| `_build_atlas_impl` bound variable names | 143 | 36 |
| Branch nodes across all build modules | 339 | 334 |

Two modules and 17 functions/methods are added: eight atlas phases, three
profile/detail operations, four PDF operations and two small record methods.
Five plain phase records are new; the existing prepared-detail record is
extended. Source grows by 351 lines (0.93%), mostly explicit phase signatures,
records and module imports. Overall decision count changes little; the benefit
is smaller responsibilities and local state, plus the concrete redundancies
removed above. There is no new optimizer or execution framework.

The public `build_atlas`, publication swap, worker initializer/queue and result
records retain identical ASTs. Main-chart construction/optimization also has
an identical AST after replacing only its duplicated diagnostic serialization
expression with the shared helper. Existing test expectations are unchanged;
two test modules import relocated private helpers from their new owners.

## Checks completed

- Baseline `make check`: Ruff passes, **1,444 passed in 355.05 s**
  (356.36 s wall).
- After `make check`: Ruff passes, **1,450 passed in 372.09 s**
  (373.44 s wall); no failures, skips or reported warnings. Timing includes
  concurrent verification workloads and six additional regression cases.
- Targeted detail/profile/credits checks: **11 passed**.
- Build suite without its five existing slow cases: **42 passed**.
- New regressions cover one-time detail preparation with optimization on/off,
  explicit empty override bookkeeping, two physical parents, profile reuse,
  serial versus two spawned workers, pixel equality and complete issue records.
- A real six-chart synthetic full-sky publication passes strict input/output
  validation with two workers and zero hard issues. Changing the style or DSO
  catalogue during subsequent builds raises the expected final-input errors;
  both failed staged builds preserve the existing PDF and remove staging
  directories. This tests publication mechanics, not release suitability of
  the real editions. Evidence: `publication/proof.json`.

## Remaining boundaries and existing findings

- Main-chart collision/fallback coordination is still a substantial function.
  Its optimization rules and candidate search are deliberately unchanged.
- The public build call still has many options; a broad options/context
  abstraction was avoided. Phase records group cohesive results explicitly.
- Fine sky audits and crowded LMC label optimization dominate runtime.
  This is a structure refactor, not an optimizer performance change.
- The experimental Eyepiece baseline report has **424 of 8,950 sampled
  neighbour-pair checks without detected overlap**, despite zero global
  sampled gaps. This is a pre-existing audit finding, not diagnosed or changed
  here; sampling warnings are not proof of continuous geometric gaps.
- Proofs cover representative subsets, not every page of complete editions.
  Full scientific/layout regressions remain in `make check`.

For a new agent, detail configuration/layout work is now confined to
`build/details.py`; editorial/navigation work is in `build/document.py`; worker
and final publication orchestration remain discoverable from `build_atlas`.
The main coordinator no longer requires tracking 143 local variable names
across every subsystem. This is the main maintainability gain.

## Graphics, layout and navigation results

All five proof comparisons pass: **72 combined-PDF pages, 19 exact PNG files,
10 main charts and nine detail charts**. All PDFs are vector outputs; their
100-dpi raster pixels, extracted text, outlines, page labels and navigation
destinations are equal. Six individual main/detail PDFs (Pocket P15/PD02,
Standard S070/SD07 and Deep D474/DD08) also have identical pixels at 200 dpi.
Pocket Cygnus, Standard Orion and Deep SMC previews were inspected visually.

| Proof | Main + detail charts | PDF pages | Hard issues before → after | Build seconds before → after |
| --- | ---: | ---: | ---: | ---: |
| pocket-color | 6 | 19 | 0 → 0 | 106.88 → 109.67 |
| standard-bw | 6 | 20 | 3 → 3 | 165.94 → 172.30 |
| deep-color | 5 | 19 | 9 → 9 | 739.29 → 743.06 |
| eyepiece-bw | 1 | 7 | 0 → 0 | 174.74 → 168.45 |
| eyepiece-deep-bw | 1 | 7 | 0 → 0 | 5.49 → 5.42 |

All counts, label hashes/costs, issue partners, detail fallback decisions,
intentional star exclusions, index contents and astronomical input fingerprints
match. Draft reports are byte-identical. There are **zero new or worsened hard
issues** in these samples; the existing issues are S070 (two), SD07 (one), D474
(eight) and DD08 (one). The existing Eyepiece sampling warnings also match.
The timings in this table include overlapping validation workloads; they do
not establish an algorithmic speed change.

### Proof locations

Both `baseline/` and `after/` below `build/atlas-refactor/` contain:

| Case | Combined PDF within case directory |
| --- | --- |
| `pocket-color` | `pocket/atlas.pdf` |
| `standard-bw` | `standard/atlas.pdf` |
| `deep-color` | `deep/atlas.pdf` |
| `eyepiece-bw` | `eyepiece/atlas.pdf` |
| `eyepiece-deep-bw` | `eyepieceDeep/atlas.pdf` |

Individual PDFs/previews are under `<atlas>/charts/<chart-id>/`; each case
has `proof.json`, a build log, rasterized PDF pages, extracted text and
navigation dumps. `comparison.json` records the complete comparison;
`print-proof/comparison.json` records the 200-dpi checks. Baseline/after JUnit
and `make-check.log` files contain full test results. Proof utilities are kept
with these local build artifacts; no new production CLI is introduced.

Reproduce with the same catalogues and source version using the existing CLI,
then rasterize the PDFs with Poppler:

```bash
.venv/bin/python -m nightsky_atlas atlas build \
  --atlas atlas/pocket.yaml \
  --style styles/experiments/color/pocket-open-cluster-cloud-a.yaml \
  --star-store data/processed/stars/tycho2.sqlite \
  --charts pocket-009,pocket-015,pocket-020,pocket-021 \
  --jobs 2 --png-dpi 100 --outdir build/atlas-refactor/reproduce
pdftoppm -r 100 -png build/atlas-refactor/reproduce/pocket/atlas.pdf /tmp/atlas-page
```

The other cases use the edition/style/chart tuples recorded in `proofs.py` and
individual `proof.json` files. Baseline source is commit `ee980e9`; use the
refactored source for the after comparison.

### Files changed

- `src/nightsky_atlas/build/atlas.py`, `chart.py`, new `details.py` and
  `document.py`.
- New `tests/build/test_atlas_pipeline.py`; only import paths change in
  `tests/atlas/test_editions.py` and `tests/build/test_credits.py`.
- `AGENTS.md`, `docs/ARCHITECTURE.md` and this audit.

No edition/style files, catalogues, astronomical models, rendering primitives
or optimizer algorithms are modified. No dependencies are added. Existing
untracked user files are preserved; there is no commit, push or merge.

### Quiet representative runtime repeat

The four-main/two-detail Pocket proof takes **106.88 s before and 107.57 s after**
in standalone runs with two workers (about +0.65%). This is effectively the
same wall time for this single measurement pair; no performance improvement
is claimed. The repeat also reproduces all 19 PDF-page pixel hashes and six
PNG files exactly. Evidence: `retimed/pocket-color/proof.json`.
