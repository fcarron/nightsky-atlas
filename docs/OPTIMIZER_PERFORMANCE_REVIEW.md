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
