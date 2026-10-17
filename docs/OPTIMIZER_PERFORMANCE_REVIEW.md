# Label optimizer performance review

2026-10-17, branch `perf/label-optimizer`; baseline commit `6c2d247`.

## Finding

Repeated contour-distance calculations dominate the slow LMC layouts. The
expensive work is repeated when verified detail-label transfers trigger another
optimization. The existing bounded searches are not an unbounded attempt to
find a conflict-free layout.

The preceding four-worker Deep proof recorded:

| Chart | Stars | DSOs | Complete chart work | First optimizer | Later validation/fallback phase | Optimizer calls |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| D473 | 1,700 | 230 | 669.79 s | 164.57 s | 481.88 s | 5 |
| D474 | 1,367 | 307 | 628.41 s | 226.67 s | 371.47 s | 3 |

The `validate` log field includes reoptimization after detail-label transfers;
it is not the time spent in `validate_layout` alone. An isolated validation of
the initial D473 layout took 6.68 s under cProfile. Catalogue/scene preparation
was about 0.3 s per main chart; candidate generation took 21–29 s.

## Reproduced initial D473 layout

The same scene has 249 selected labels and 26,723 candidates, before detail
transfers. Both profiled versions start from the identical serialized inputs.

| Metric | Baseline | Final prototype |
| --- | ---: | ---: |
| Profile wall time | 507.47 s | 158.93 s |
| Profile process CPU time | 507.41 s | 158.88 s |
| Python function calls | 2,354,340,729 | 766,135,129 |
| Exact contour-segment distance calls | 26,115,148 | 3,991,918 |
| Selected/placed labels | 249 / 249 | 249 / 249 |
| Hidden labels | 0 | 0 |
| Initial-layout hard issues | 25 | 25 |
| Changed label placements | — | 0 |

These initial-layout issues precede the detail fallback; the previous complete
D473 page has four remaining issues after its five optimizer calls. The cost
difference is approximately `1.2e-10`; label objects and issue IDs match. A
fresh unprofiled repeat took 54.04 s of wall/process CPU time and reproduced the
prototype's labels and cost exactly.

cProfile adds substantial overhead. Its seconds must not be compared directly
with ordinary build seconds; the profiled before/after comparison is about
3.2 times faster under the same instrumentation.

### Original expensive functions

Cumulative times overlap and must not be added.

| Function | Calls | Cumulative profile time |
| --- | ---: | ---: |
| `source_edge_distance` | 436,965 | 410.47 s |
| `_segment_rect_distance` | 26,115,148 | 326.98 s |
| `_ownership_result` | 29,513 | 247.09 s |
| `_CandidateScoreCache.breakdown` | 203,386 | 193.83 s |
| `score_candidate` | 23,661 | 189.32 s |
| `_is_valid` | 53,446 | 186.37 s |
| `_source_association_costs` | 23,622 | 177.01 s |
| `_greedy_place` | 1 | 158.81 s |
| `_local_repair` | 1 | 145.39 s |
| `_consider_dso_leader_fallbacks` | 1 | 78.60 s |

The joint component searches took 15.74 s, about 3% of the original profiled
optimizer call. There were 142,533 visited search nodes, 31 neighborhood
searches, and no exhausted node budgets. The largest candidate-conflict
component contains 201 labels and already takes the local fallback instead
of being searched as a whole.

## Prototype changes

- Find the nearest DSO by ordering conservative bounding-box lower bounds;
  measure exact contours only while a source can still beat the current best
  distance. Stable object-ID tie-breaking is retained. Contour bounds use the
  actual vertices, including contours extending beyond catalogue symbol sizes.
- Cache contour segments and their boxes. Skip segment distances whose box
  lower bound exceeds the best exact distance; retain the original exact
  segment calculation and stop at an exact zero.
- Use an analytic circle/rectangle boundary distance for circular symbols,
  including rectangles wholly inside the circle. General ellipses retain the
  existing numerical calculation.
- Stop checking candidate rectangles for label pairs already connected in the
  conflict graph. The connected components remain unchanged.

An isolated all-source ownership diagnostic improved from 45.05 to 1.09 s under
cProfile: 52,441 exact source distances became 612, with identical owner IDs
and classifications for all 230 DSOs. This is a diagnostic microbenchmark,
not the speedup of an entire page.

No candidate selection, priorities, label suppression policy, search budgets,
collision thresholds, astronomical positions, symbol sizes or styles changed.
The circle calculation can change insignificant floating-point distance bits;
the tested initial D473 layout still matches exactly. Geometry caches are
bounded to 256 segment sets and 4,096 source bounds.

## Controls and checks

Complete chart work, including fallback reoptimization and rendering:

| Chart | Previous proof | Accelerated proof | Speedup |
| --- | ---: | ---: | ---: |
| D473, LMC | 669.79 s | 223.50 s | 3.00× |
| D474, LMC | 628.41 s | 192.82 s | 3.26× |
| D128, Coma | 212.01 s | 165.83 s | 1.28× |
| D157, Leo | 127.83 s | 91.13 s | 1.40× |
| D475, sparse control | 2.68 s | 2.34 s | 1.15× |

The earlier timing log is from the four-worker, 22-main-chart detail proof;
the accelerated proof uses two workers and five main charts. These ordinary
worker wall times are indicative rather than a matched whole-build benchmark.
The isolated before/after cProfile CPU measurements independently establish the
optimizer improvement. The accelerated five-main/eight-detail proof takes
456.50 s including preparation and document/index pages.

Serial Pocket P20 plus its Virgo detail took 61.82 s before and 50.47 s after.
Serial Standard S051 plus its three associated details took 100.51 s before
and 78.13 s after. All six control chart PNGs and layout hashes match; the
selected star/DSO counts, label counts, and zero hard-issue results match.

Across all **19** tested main/detail pages, PNG SHA-256 values, layout hashes,
hard-issue IDs, selected stars/DSOs, placed/hidden counts and permitted detail
transfers are identical. The Deep subset retains its 154 recorded hard issues;
this includes 113 on D128 and 28 on DD03. The Deep build returns 1 for those
layout issues, not a structural failure. Ordinary artifact validation passes
for all three proof editions; publication was not requested.

The offline suite passed: `make check`, 1,512 tests, 376.25 s; lint passed.
New regressions compare pruned searches with exhaustive geometry, cover circle
interior/exterior/tangency at several scales, separated contour paths, stable
ties, invalid contours, and duplicate conflict-graph edges.

Artifacts live under `build/perf-label-optimizer/`: original source snapshot,
serialized inputs/results, cProfile files, individual build logs, and the
Pocket/Standard/Deep proof PDFs. `proof-comparison.json` records each page's
equality checks; `timing-comparison.json` records each timed build phase.

To reproduce a complete serial page profile with the local processed catalogue:

```bash
.venv/bin/python -m cProfile -o build/deep-473.prof -m nightsky_atlas \
  atlas build --edition deep --charts deep-473 --jobs 1 \
  --star-store data/processed/stars/tycho2.sqlite \
  --outdir build/deep-473-profile --no-draft-report -v
```

The build profiles associated detail preparation and all parent fallback calls
as well. Reproduce the baseline from commit `6c2d247` with the same catalogue,
atlas/style files and worker count; no catalogue download is part of profiling.

## Recommendation

Keep the geometry acceleration before reducing search quality. The existing
limits remain `joint_max_component_labels=8`, `joint_beam_width=24`,
`joint_node_budget=24000`, `hard_repair_neighborhood_labels=8`, and
`hard_repair_search_limit=45`. Lowering these cannot address the dominant
original contour cost and can damage coordinated placements.

Remaining opportunities are sharing immutable candidate geometry/costs between
detail-fallback retries and memoizing repeated unsuccessful neighborhood
searches against an unchanged placement state. Such reuse must account for
leader-line and locked-label state. Dense galaxy-only fields benefit less from
the contour acceleration; Coma remains an expensive unresolved layout.

This is a representative-field performance study, not a complete three-edition
rebuild or a claim of a universally bounded per-page runtime.

## Bounded working geometry (follow-up)

The follow-up introduces approximation in the soft source-distance
terms of candidate scoring (`source_scoring_distance`). Rendering, candidate
generation, source ownership validity, hard collision tests and the final
geometric diagnostics retain their original geometry and distance routines.

- Irregular outlines use cached deterministic Ramer–Douglas–Peucker working
  paths with a maximum deviation of 0.05 mm in page coordinates. Each separate
  path keeps its endpoints; open clipped paths are not closed or joined.
  D473's 10,978 original contour segments become 608 working segments.
- Non-circular ellipses use a cached inscribed polygon. Its segment count is
  at least 16 and grows with the square root of the major radius, bounding
  interpolation error to 0.05 mm. Circles and square symbols retain the direct
  distance formulas.
- Approximate contour distances at or below 0.2 mm fall back to the original
  calculation. Potential ties between competing DSO distances within 0.1 mm
  are refined. The own-object gap stays exact. Every foreign-object distance
  within the influence range of ambiguity, proximity or ownership penalties
  is recomputed exactly, with the approximation-error margin added to the
  range. Approximations therefore reject distant, irrelevant neighbours rather
  than changing an active penalty. Final checks do not use approximate
  collision geometry.

The tolerance is a numerical working precision in physical millimetres, not an
astronomical source modification or a new style option. A first trial allowed
approximate active costs; it retained the initial D473 layout but increased
D128's final hard issues from 113 to 118 and changed other placements. That
trial was rejected and its superseded Deep build interrupted. The retained
version refines all active distances. Deterministic output, label retention
and exact validation remain required; pixel equality is measured rather than
assumed. Segment caches now retain up to 1,024 sets to accommodate original and
working paths together; the working-geometry cache is limited to 512 sources.

### Retained version: measured results

Baseline for this follow-up is commit `0b2407a`, the committed exact-geometry
acceleration above. Two fresh-process D473 repeats start from the identical
serialized scene and candidates:

| Initial optimizer | Wall time | Process CPU time |
| --- | ---: | ---: |
| Exact accelerated baseline | 53.08 s | 52.98 s |
| Working geometry, repeat 1 | 46.66 s | 46.64 s |
| Working geometry, repeat 2 | 48.18 s | 48.18 s |

Both repeats retain all 249 labels, the same placements, cost components,
total cost and 25 initial hard-issue IDs. The repeats reproduce each other's
labels and cost exactly. The retained version improves this CPU control by
about 10–12%, rather than the larger gain of the rejected active-cost trial.

Complete chart work includes detail-fallback reoptimization and rendering:

| Chart | Exact accelerated baseline | Working geometry |
| --- | ---: | ---: |
| D128, Coma | 165.83 s | 144.43 s |
| D157, Leo | 91.13 s | 83.09 s |
| D473, LMC | 223.50 s | 193.45 s |
| D474, LMC | 192.82 s | 167.50 s |
| D475, sparse control | 2.34 s | 2.38 s |

Both Deep proofs use two main-chart workers and the same five main/eight detail
charts; the complete proof changes from 456.50 to about 404 s. Serial controls
including associated details change from 50.47 to 42.33 s for Pocket P20 and
78.13 to about 71 s for Standard S051. These ordinary timings can vary with
machine load; the CPU control above independently supports the improvement.

Across all 19 main/detail pages, preview PNG bytes, layout hashes, selected
star/DSO counts, placed/hidden counts, total layout costs, permitted detail-label
transfers and individual hard-issue IDs match. The Deep subset retains its
154 pre-existing hard issues, and Pocket/Standard controls remain clean.
No new issue is accepted. Deep's build exit status is 1 for the recorded layout
issues; ordinary artifact validation passes for all three editions. These are
representative proofs, not complete three-edition rebuilds or publication runs.

`make check` passes: **1,546 tests in 370.15 s**, with lint passing. The focused
layout suite passes 341 tests. New offline cases cover page-scale contour
error bounds, separate/open paths, original-geometry collision refinement,
rotated/eccentric ellipses, unchanged simple symbols, ambiguous neighbour
refinement and equality of active scoring components to exact calculations.

Artifacts under `build/perf-label-optimizer/`:

- `approx-final/<edition>/<edition>/atlas.pdf`: final proof PDFs.
- `approx-comparison.pdf`: alternating exact/working-geometry main-chart pages
  for P20, S051, D128, D157 and D473–D475.
- `approx-final-comparison.json`: all 19 per-page comparisons and determinism.
- `approx-final-timings.json`: complete Deep chart work and stage times.
- `exact-repeat.json`, `final1-repeat.json`, `final2-repeat.json`: isolated
  timing/validation controls, with adjacent serialized layouts.
- `approx-final-make-check.log`: complete check output.

Changed files for this follow-up are `layout/association.py` (working geometry),
`layout/scoring.py` (adaptive refinement), `tests/layout/test_association.py`,
`tests/layout/test_scoring.py`, this report and `docs/PERFORMANCE.md`. No new
dependency, configuration schema or renderer change is introduced. Repeated
whole-chart optimizer calls after detail transfers remain the next substantial
opportunity; this change does not remove those calls.

## Reusing immutable work between complete optimizer retries

The working-geometry stage was committed first as **`bb27d41`**. This section
compares the next stage with that checkpoint, using the same catalogue inputs,
configuration, chart subsets and worker counts. The new changes remain
uncommitted for review. No partial/incremental optimization is implemented.

### Findings and implementation

D473 still needs five optimizer calls. Previously each rebuilt roughly
20,000–23,000 static scores. D474 needs three calls, D128 four and D157 three.
The second D473 call alone spent 37.21 CPU seconds rebuilding/reusing a fresh
per-call cache, despite unchanged scene geometry.

`OptimizationCache` now belongs to one `_build_main_chart` invocation and is
passed to the initial optimization and both grouped/sequential fallback paths.
It retains the existing `_CandidateScoreCache` and immutable chart geometry,
source/star spatial indices and anchors. The greedy pass now uses that cache's
geometry and validity methods too; candidate ordering and tie-breaking remain
unchanged.

Safe retained data:

- Candidate neighbourhood geometry: nearby printed stars and DSO symbols.
- Static cost components, excluding label overlap and crowding.
- Candidate validity against printable bounds, furniture, stars, DSO geometry
  and source ownership, calculated without other label placements.

Current label overlap and crowding are recomputed on every lookup. Placed-label
indices, conflict components, searches, repairs and leader routing/decisions are
rebuilt on every optimizer call. Search budgets, priorities, transfer eligibility
and hard-collision rules are unchanged.

Reuse requires the same immutable scene instance, transform, complete serialized
style, weights and furniture. A context change discards the cache. Before each
retry, full label/candidate definitions are compared, including target, text,
fonts, glyph geometry, locked state and leader state/reason. Only the selected
candidate and hidden flag are excluded from this immutable signature: their
effects enter the freshly built placement state. Removed or changed labels lose
their entries; restored labels are recalculated as necessary. This also handles
rollback from grouped to sequential transfers.

Each of the three entry dictionaries is capped at **65,536** entries with
deterministic FIFO eviction; label-version bookkeeping is bounded too. No
evictions occurred in these controls. Separate main-chart workers create their
own cache; there is no new global or cross-process mutable cache. The cache is
released when that chart finishes. No runtime dependency or style/CLI option is
added.

### Complete chart measurements

Timings below measure `_build_main_chart`, including context/candidate creation,
all optimizer calls, validation and rendering. Instrumentation serializes the
D473 replay after this timer, so CLI work logs can be about 0.5 seconds higher.

| Main chart | Wall before | Wall after | CPU before | CPU after |
| --- | ---: | ---: | ---: | ---: |
| D473 | 200.33 s | 101.73 s | 200.29 s | 101.72 s |
| D474 | 175.93 s | 106.51 s | 175.89 s | 106.46 s |
| D128 | 144.50 s | 98.44 s | 144.49 s | 98.42 s |
| D157 | 81.94 s | 58.00 s | 81.92 s | 58.00 s |
| P20 | 31.96 s | 23.45 s | 31.96 s | 23.45 s |
| S051 | 48.19 s | 29.24 s | 48.19 s | 29.25 s |

End-to-end proofs include their associated detail charts and document pages:

| Proof | Workers | Wall before / after | Parent CPU before / after | Worker/child CPU before / after |
| --- | ---: | ---: | ---: | ---: |
| Deep: 4 main + 8 detail | 2 | 409.31 / 297.33 s | 89.40 / 92.17 s | 616.12 / 376.96 s |
| Pocket: P20 + 1 detail | 1 | 45.24 / 35.42 s | 45.26 / 35.44 s | 0 / 0 s |
| Standard: S051 + 3 details | 1 | 75.31 / 53.63 s | 75.33 / 53.65 s | 0 / 0 s |

Child CPU is summed `RUSAGE_CHILDREN` CPU after worker shutdown, not elapsed
time; it includes small rendering/helper subprocess costs. One-worker builds
run in the parent. These are representative subsets, not full atlas builds.
Ordinary wall timings can fluctuate with other machine activity.

### Repeated calls and cache effectiveness

Per-call D473 process CPU from the complete Deep proofs:

| Call | CPU before | CPU after | Static-score misses before | Static-score misses after |
| --- | ---: | ---: | ---: | ---: |
| 1 | 48.59 s | 47.69 s | 22,899 | 22,899 |
| 2 | 37.21 s | 13.05 s | 20,910 | 1,885 |
| 3 | 31.43 s | 8.05 s | 20,156 | 244 |
| 4 | 32.37 s | 7.70 s | 19,955 | 161 |
| 5 | 32.56 s | 7.25 s | 19,716 | 1 |

The first call is not universally faster: D128's first CPU time increases from
59.08 to 63.22 seconds, and D157's from 33.14 to 34.58 seconds. The later calls
recover substantially more than that overhead. No optimizer call is omitted.

A separate fresh-process replay of the five identical serialized D473 inputs
reduces accumulated optimizer CPU from **184.95 to 78.70 seconds (2.35×)**.
Every call reproduces the checkpoint's recorded label/candidate values, hidden
counts, costs and component totals exactly. Across those calls:

- Static-score misses: 103,636 → 25,190; cumulative hit rate 81.8% → **95.6%**.
- Cached geometry hit rate: **82.1%**; static-validity hit rate: **95.9%**.
- Exact source-edge cache misses: 1,055,269 → 250,541.
- Working source-distance cache misses: 886,168 → 232,917.
- Hard outline-distance lookups are unchanged: 33,819 hits and 22,961 misses.

The source-distance figures are underlying LRU lookup/miss counts, not new
search budgets. Validity/geometry rates are for the retained implementation;
the old greedy pass bypassed those caches, so its method-level rates are not
directly comparable.

### Memory

The controlled replay peak process RSS rises from **235.1 to 300.4 MiB**,
approximately **65.3 MiB** extra. At its last call the retained cache structures
occupy an estimated **30.8 MiB**, counting containers, cost values, rectangle
values and label-version objects while excluding referenced scene/candidate
graphs. This estimate is calculated after the final timed/RSS measurement.
The RSS delta also includes Python allocation/retention effects and is the more
conservative practical overhead measurement.

Whole-build worker high-water RSS was about 805 versus 775 MiB, dominated by
shared prepared detail data and allocator behaviour. That lower high-water
value is not evidence that the cache consumes no additional memory. Budget
additional memory per active chart; the cache's lifetime and entry caps prevent
unbounded accumulation across the atlas.

### Validation, artifacts and remaining work

All **18** main/detail pages match in selected/placed/hidden counts, layout
hashes, exact before/after costs, individual hard-issue IDs, optimization-run
counts, detail-label transfers and preview PNG bytes/SHA-256 values. The Deep
subset retains 154 existing hard issues; Pocket/Standard remain clean. Ordinary
artifact validation passes for all three editions. Deep build exit status 1
records those existing layout issues; this is not a publication build.
All non-code input fingerprints match between the two versions.

`make check` passes **1,559 tests in 377.84 seconds**, including lint. Focused
layout checks pass 354 tests and build checks pass 48 tests. Added cases protect
changed candidate/glyph geometry under stable IDs, text/target changes, locked
and leader state, transfer rollback/restoration, current neighbour collisions,
context changes and bounded eviction. No test baselines were weakened.

Files changed: `build/atlas.py`, `layout/optimizer.py`, `layout/placement.py`,
`tests/layout/test_optimizer.py`, this report and `docs/PERFORMANCE.md`.

Local artifacts under `build/perf-repeated-optimizer/` include:

- `baseline-source/src/`: archived checkpoint code.
- `baseline/` and `cached-final/`: profiles, per-chart/process timings and
  `<edition>/<edition>/atlas.pdf` proof PDFs.
- `comparison.json`: all 18 exact output comparisons; `timings.json`: CPU and
  wall measurements, per-call phase costs and cache statistics.
- `baseline/deep-473-replay.pkl`, `replay-baseline.json`, `replay-cached.json`:
  identical-input controls, source-distance statistics and memory measurements.
- `measure_build.py`, `run_matrix.py`, `replay.py`, `compare.py`: local
  measurement/reproduction scripts; `final-make-check.log`: complete checks.

With the same local processed data, `run_matrix.py baseline` uses the archived
checkpoint and `run_matrix.py cached-final` uses the current implementation.
`replay.py` reruns the saved five-call control in fresh processes. These tools
and generated catalogues/artifacts are not committed.

Remaining D473 CPU across all five calls is concentrated in leader fallbacks
(20.62 s), hard-conflict repair (17.58 s), greedy placement (17.60 s) and joint
optimization (6.97 s). Repeated dynamic conflict checks/searches and the cold
first pass remain. Next, profile the remaining repair/leader work and assess
partial reoptimization as a separate stage with equivalent quality controls;
neither is implemented here.
