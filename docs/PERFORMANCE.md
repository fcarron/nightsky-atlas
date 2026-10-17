# Performance notes

## Dense label layouts

The 2026-10-17 [optimizer performance review](OPTIMIZER_PERFORMANCE_REVIEW.md)
profiles the slow Deep LMC fields. Repeated exact contour distances dominate;
conservative geometry pruning speeds the tested optimizer call by about 3.2×
under cProfile while preserving its placements. The review records the ordinary
build controls, unchanged search budgets, validation and remaining work.
The follow-up uses bounded 0.05-mm working contours and ellipse polygons to
screen distant neighbours; distances affecting penalties and final collision
checks retain the original precision.
The next stage shares bounded immutable candidate work between detail-transfer
retries. On the measured D473 page, complete chart time changes from about
200 to 102 seconds; all 18 tested main/detail previews and layout costs match.
See the review for CPU controls, cache hit rates and the additional memory cost.

## Remaining label-optimizer work after cross-retry caching

Measured on branch `perf/label-optimizer`, checkpoint `0d5cb16`, with the
processed Tycho-2 store and the same Deep definitions, style and detail charts
as the prior benchmark. The four main charts were built together with two
workers. Times below sum optimizer process CPU across all optimizer calls for
the main chart; they exclude detail charts and the rest of atlas build. The
diagnostic wrapper also counts exact repeated search inputs, so these CPU times
are profiling figures, not clean user-facing build timings.

| Chart | Optimizer calls | Optimizer CPU | Greedy | Local repair | Hard repair | DSO leader fallback | Final hard issues |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| D128 | 4 | 97.0 s | 32.8 s | 6.1 s | 45.0 s | 3.2 s | 113 |
| D157 | 3 | 51.9 s | 14.0 s | 4.5 s | 13.5 s | 9.1 s | 0 |
| D473 | 5 | 82.7 s | 18.1 s | 5.6 s | 16.8 s | 20.8 s | 4 |
| D474 | 3 | 87.6 s | 22.3 s | 9.2 s | 23.3 s | 18.9 s | 5 |

Hard-issue totals are from the final chart manifests. One accepted hard-repair
move strictly lowers the optimizer's hard-conflict count, but it can remove
more than one conflict; move counts are not issue counts.

### Repair yield and repeated states

| Chart | Neighborhood searches | Accepted hard-reducing moves | Search yield | Local-repair moves with positive recorded cost gain | Exact full-state search repeats |
| --- | ---: | ---: | ---: | ---: | ---: |
| D128 | 180 | 8 | 4.4% | 134 / 149 | 0 |
| D157 | 57 | 15 | 26.3% | 100 / 126 | 0 |
| D473 | 38 | 9 | 23.7% | 19 / 27 | 0 |
| D474 | 44 | 10 | 22.7% | 101 / 130 | 2 |

There were no neighborhood-search budget hits in these calls. The repeated
search inputs on D474 returned a solution each time, but the profiler did not
observe repeated *unsuccessful* searches with the same complete placement
state. Thus memoizing failed searches alone has no demonstrated payoff yet.
The accepted hard-repair moves are the only search attempts counted as lowering
the hard-conflict count. Ordinary local repair separately recorded positive
soft-cost gains for the counts shown above; those are label moves, not a global
cost reduction guarantee for every pass.

The hard-repair phase revisits seeds as the layout changes between retries.
That explains why D128 repeats 45 searches in each of four calls while the
complete placement fingerprints differ. D473 stops issuing neighborhood
searches after its second retry, although its leader fallback still costs about
2.6–2.8 CPU seconds on each of the last three calls. D474 similarly retains
about 3.1 seconds of leader fallback work on its third call.

### Candidate-conflict density as a predictor

The existing candidate-conflict graph gives a useful coarse measure of search
scope, but it is not yet a validated predictor of success. On the first call,
the largest graph component had 132 labels on D128, 55 on D157, 201 on D473
and 288 on D474. D128 also had the largest hard-repair cost and the lowest
accepted-move rate. However, D474's component was larger than D128's while its
repair CPU and yield were better. Component size can flag potentially expensive
fields, but cannot decide that a search is unproductive. Record per-component
candidate-overlap density and repair yield before considering any density-based
search shortcut; do not use it to skip a search or change budgets.

### Prioritized next steps

1. **Profile and reuse leader-fallback work under exact layout fingerprints.**
   D473/D474 spend 39.7 CPU seconds in this phase across their retries. The
   candidate-breakdown and route checks depend on current neighboring labels,
   leader lines and obstacle geometry, so a cache must include that state or
   limit reuse to proven immutable subcalculations. Expected impact: moderate;
   implementation complexity and layout risk: medium.
2. **Add component-level search-yield diagnostics.** Record candidate-conflict
   edge density, visited nodes, before/after hard counts and whether a found
   solution was accepted. Expected runtime impact: none until it guides later
   work; complexity and behavior risk: low. Four charts are not enough to
   calibrate a safe predictor.
3. **Consider partial reoptimization only after those measurements.** It could
   reduce greedy and repair passes after detail-label transfers, but placement
   dependencies include shared candidate regions, symbol conflicts and leader
   routes. Expected impact: potentially high; complexity and quality risk:
   high. Keep it separate from caching and require full layout/PDF comparisons.

No optimizer behavior or policy changed for this analysis. The profile rows,
manifests and reproduction harness are local ignored artifacts under
`build/perf-repeated-optimizer/remaining/`; they use the same four-chart Deep
command as the preceding matrix, with the diagnostic version of
`measure_build.py`. D128/D157/D473/D474 final manifest hashes and issue counts
match the preceding cached-final proof. The added source search-state counter
found two exact repeats on D474 and none on the other three charts.

## Leader-fallback caching

Checkpoint: `399b02b` on `perf/label-optimizer`. Both versions build D128,
D157, D473 and D474 together with their eight associated detail charts, the
same local catalogue inputs and two chart workers. Source code for the reference
is archived under `build/perf-leader-fallbacks/checkpoint/src/`.

### Profile and implementation

A separate five-call D473 replay profiles only `_consider_dso_leader_fallbacks`.
Under cProfile, the phase takes 46.5 seconds: candidate rejection accounts for
22.2 seconds, candidate breakdowns for 20.8 seconds and routing for 3.0 seconds
(these are inclusive times). The rejection path repeatedly determines related
stellar components inside its nearby-star loop.

The change hoists that immutable membership calculation out of the star loop
and adds one bounded rejection-reason store to the existing chart-local
`_CandidateScoreCache`. Only source overlap, ownership and stellar-clearance
rejections are cached. Page bounds, furniture and current label collisions are
checked first on every call, preserving the original rejection precedence.
Leader routes and line crossings are still checked against current placements.
The cache uses the existing full non-placement label versions, invalidating
changed targets, candidates, glyphs, text, locks or leader flags; the enclosing
cache replaces it on scene, transform, style, weights or furniture changes.
Transferred/restored labels go through the same invalidation. Its 65,536-entry
FIFO cap and chart-local lifetime also apply in parallel builds.

On the profiled replay, candidate-rejection time falls to 6.2 seconds and the
whole leader phase to 31.1 seconds. Related-star lookups fall from 73,821 to
9,420. Candidate breakdowns remain exactly 57,200, routing calls 4,913 and
whole-line resolutions 109. No search budget, candidate order, eligibility,
priority, threshold or stopping rule changes.

### Ordinary build measurements

The following times are unprofiled. Leader and optimizer columns sum process
CPU across all main-chart retries; complete chart time includes scene/label
preparation, validation, rendering and the detail-transfer/reoptimization work.

| Chart | Calls | Leader CPU before / after | Optimizer CPU before / after | Complete chart wall before / after |
| --- | ---: | ---: | ---: | ---: |
| D128 | 4 | 3.09 / 2.63 s | 85.79 / 89.02 s | 93.19 / 96.20 s |
| D157 | 3 | 5.61 / 5.71 s | 45.28 / 45.65 s | 52.80 / 53.31 s |
| D473 | 5 | 20.52 / 11.54 s | 79.59 / 71.64 s | 97.43 / 90.13 s |
| D474 | 3 | 19.24 / 15.40 s | 85.50 / 84.86 s | 101.11 / 101.78 s |

D473's leader phase improves by 44%, its complete chart by about 7.5%.
D474's leader phase improves by 20%, but this run does not demonstrate a
complete-chart speedup. The control charts show no overall gain: D128 is 3.2%
slower and D157 1.0% slower. These are single build samples and unrelated
phase timings also vary; no general atlas speedup is claimed. The full
four-main/eight-detail proof takes 282.52 / 285.52 seconds wall, with summed
worker CPU 358.00 / 355.95 seconds and parent CPU 87.66 / 87.05 seconds.

| Chart / call | Optimizer CPU before / after | Leader CPU before / after |
| --- | ---: | ---: |
| D473 / 1 | 44.31 / 44.53 s | 8.570 / 7.972 s |
| D473 / 2 | 11.69 / 9.91 s | 3.087 / 1.492 s |
| D473 / 3 | 7.31 / 6.07 s | 2.695 / 0.908 s |
| D473 / 4 | 8.85 / 5.92 s | 3.442 / 0.624 s |
| D473 / 5 | 7.43 / 5.21 s | 2.724 / 0.546 s |
| D474 / 1 | 58.74 / 60.11 s | 11.861 / 10.899 s |
| D474 / 2 | 16.63 / 15.68 s | 4.651 / 2.974 s |
| D474 / 3 | 10.13 / 9.07 s | 2.730 / 1.525 s |

The raw `timings.json` includes every call on the two control charts as well.
Two fresh-process, identical-input D473 replay pairs reduce optimizer CPU
77.16 → 68.42 seconds and 80.54 → 67.90 seconds. Every replay call matches
the saved labels, routes, diagnostics and costs exactly.

### Cache effectiveness, memory and correctness

| Chart | Rejection hits / misses | Hit rate | Final retained entries |
| --- | ---: | ---: | ---: |
| D128 | 1,181 / 818 | 59.1% | 499 |
| D157 | 1,502 / 1,609 | 48.3% | 1,102 |
| D473 | 5,325 / 2,469 | 68.3% | 1,745 |
| D474 | 3,205 / 3,100 | 50.8% | 2,223 |

No eviction occurs in these proofs. D473's final rejection dictionary and owned
key tuples occupy 171,528 bytes (0.16 MiB), excluding strings already referenced
by labels and shared rejection literals. Linux `/proc/self/status` gives peak
process memory of 229.6 / 229.2 MiB in the fresh replay pair: no measurable peak
increase beyond allocation variability, rather than evidence of a memory saving.
This uses `VmHWM`; the tool launcher's inherited `ru_maxrss` does not isolate
the Python execution in this environment.

All twelve chart pages match in complete label/candidate values, leader flags,
reasons and route endpoints, costs, diagnostic values, hard-issue IDs, detail
transfers and preview PNG bytes/SHA-256. All fifteen main-chart optimizer-call
results and all eight detail results are compared. Existing hard issues remain
D128 113, D157 0, D473 4 and D474 5; including the detail pages the subset retains
154 issues. Both ordinary atlas validations pass. Build exit status 1 records
those existing layout issues; neither is a publication build.

Regression tests cover cached success/failure with moving neighbors, furniture
precedence, changed related-star targets, complete label-version invalidation
and bounded eviction. `make check` passes lint and all 1,562 tests in 364.12
seconds. Focused layout checks passed 356 tests before the final target-change
case was added; that case and all final changes are included in `make check`.

Artifacts and local reproduction scripts live in `build/perf-leader-fallbacks/`:
`measure.py`, `profile_leaders.py`, `replay_control.py`, `compare.py`,
`comparison.json`, `timings.json`, profiles, replay records and logs. To rerun
the comparison, use the same command with `BENCH_TAG=baseline` and
`PYTHONPATH=build/perf-leader-fallbacks/checkpoint/src`, then with
`BENCH_TAG=optimized` and the current package:

```bash
.venv/bin/python build/perf-leader-fallbacks/measure.py atlas build \
  --edition deep --charts deep-128,deep-157,deep-473,deep-474 --jobs 2 \
  --star-store data/processed/stars/tycho2.sqlite \
  --outdir build/perf-leader-fallbacks/optimized/deep --no-draft-report -v
.venv/bin/python build/perf-leader-fallbacks/compare.py
```

Use fresh tag directories when collecting timings; the harness appends JSONL
rows. Generated data and harnesses are ignored local artifacts.

The next useful investigation is the 6,126 remaining static-score misses in
the D473 fallback profile, especially source-association/contour distances.
Measure whether exact owner-gap screening can avoid full scoring for candidates
already excluded by the existing maximum-gap rule. Routing itself is a smaller
cost here, and D128's hard repair remains a separate large bottleneck. Partial
reoptimization and adaptive stopping remain deferred.

## Static scoring and contour cache-key follow-up

This stage starts from `399b02b` plus the validated, still uncommitted
leader-rejection cache above. The exact starting source tree and worktree diff
are preserved under `build/perf-owner-gap/checkpoint/`; previous pending changes
were preserved. No commit was made during this follow-up.

### Exact distance screening trial

The existing leader maximum-gap rule rejects 11,026 of 56,131 alternative
candidate evaluations on D473 and 9,594 of 48,107 on D474. However, only 1,354
of D473's 6,126 uncached alternative scores and 2,014 of D474's 8,904 uncached
scores belong to those rejected candidates. Much of the apparent opportunity
is already inexpensive cached work. The discarded full breakdowns account for
about 1.75 / 2.51 CPU seconds across the five / three leader-fallback calls.

A trial exact owner-gap precheck matched the scoring rule for contours,
ellipses, circles, dashed symbols, missing owners, associated stars and the
threshold boundary. All five D473 outputs also matched. Its measured complete
optimizer CPU changed only 66.11 → 65.15 seconds. The extra distance API and
cache were removed; the trial source, tests and measurements remain as ignored
artifacts in `build/perf-owner-gap/trial-exact-gap/`.

### Retained change: cheaper source-geometry hashing

The distance caches repeatedly hashed every contour vertex even when a lookup
returned an already cached result. `SourceGeometry.__hash__` now uses its ID,
page centre, two radii and rotation. Full dataclass equality still compares
every field, including contours, object type, shape and stroke/dash parameters.
Different geometries with the same hash therefore remain distinct cache keys.
No geometry, scoring formula, search order, threshold or cache limit changes.

The retained implementation is six production lines, adds no object state or
cache, and preserves the existing bounded LRUs and process-local ownership.
There is no persisted hash value to invalidate across serialization or workers.
A regression test deliberately exercises colliding contour hashes, distinct
exact/working/hard distances, dictionary membership and a pickle round trip.

Two fresh-process five-call D473 comparisons reduce optimizer CPU
66.11 → 56.69 seconds and 68.90 → 64.08 seconds. All recorded labels,
candidate values, routes, costs and diagnostics match. The second comparison
also has exactly equal hit/miss deltas for all five geometric caches:
`source_edge_distance`, `source_scoring_distance`,
`source_outline_edge_distance`, `_source_bounds` and `_scoring_geometry`.
Thus no geometric evaluation or validation was omitted. Peak process memory
in that pair is 229.4 / 229.3 MiB; no new retained cache state is introduced.

### Complete proof and output checks

The same four main charts and eight associated detail charts were built before
and after with identical catalogue/configuration inputs and two workers. CPU
below sums every optimizer retry on the main chart; wall time includes its
complete preparation, optimization, transfer retries, validation and rendering.

| Chart | Optimizer CPU before / after | Complete chart wall before / after | Final hard issues |
| --- | ---: | ---: | ---: |
| D128 | 86.37 / 87.34 s | 93.93 / 94.86 s | 113 |
| D157 | 44.84 / 44.95 s | 52.65 / 52.94 s | 0 |
| D473 | 70.16 / 64.41 s | 88.09 / 81.70 s | 4 |
| D474 | 78.55 / 73.87 s | 94.40 / 88.89 s | 5 |

Complete chart savings are 7.3% for D473 and 5.8% for D474; the controls show
no gain. These are individual build samples, with control differences around
1%. The entire proof changes 275.24 → 267.90 seconds wall, summed worker CPU
343.55 → 332.47 seconds and parent CPU 85.89 → 82.88 seconds. Per-call timings
for all fifteen main-chart optimizer calls, including phase CPU, are in the
local `timings.json`; no retry is skipped.

All twelve chart pages and all recorded optimizer results are identical in
labels/candidates, hidden counts, leader routes, costs, diagnostics, hard-issue
IDs, verified detail transfers and preview PNG bytes/SHA-256 values. The subset
retains the same 154 existing hard issues including detail pages. Both ordinary
atlas validations pass; the build exit status of 1 records those known layout
issues, and these are not publication builds. Focused layout checks pass all
358 cases; `make check` passes lint and all 1,563 tests in 368.13 seconds.

Reproduction artifacts live in `build/perf-owner-gap/`: the initial worktree
snapshot, before/after PDFs and manifests, serialized optimizer inputs/results,
`comparison.json`, `timings.json`, gap-trial profiles and controlled replay logs.
`measure.py`, `compare.py`, `summarize.py` and `replay_control.py` reproduce the
measurements with the same local catalogues. The build command is the preceding
four-chart command with this artifact root; use the checkpoint's `src/` on
`PYTHONPATH` for the reference. Use fresh tag directories because timings append
JSONL rows. The final implementation leaves `scoring.py` and candidate/leader
selection logic unchanged from the initial worktree. The next substantial
bottleneck remains hard-conflict repair in D128; no further search optimization
is implemented here.

## Atlas page parallelism

The atlas builder can compute independent main chart pages in separate processes
with `atlas build --jobs N`. The combined PDF, navigation and index are assembled
in chart order in the main process. The CLI uses two workers by default; one
worker preserves the serial path.

On 2026-09-29, four dense Pocket charts (P025, P039, P045, P046), including two
Virgo detail charts, at 100 DPI gave these wall times and peak summed process-tree
proportional set sizes (PSS):

| Workers | Wall time | Peak PSS |
| --- | ---: | ---: |
| 1 | 81.4 s | 494 MiB |
| 2 | 52.3 s | 1,274 MiB |
| 4 | 37.8 s | 1,973 MiB |

The 51-page complete Pocket build took 136.9 s with four workers. All 51 layout
hashes, hard-issue counts and preview PNGs matched the serial build. PDF bytes
can differ because Cairo writes PDF metadata. Two workers are the CLI default
because four workers nearly doubled peak memory for a smaller additional speedup.

## M4 — indexed star queries (SQLite)

Environment: Ubuntu 24.04, Python 3.12, SQLite via the standard library,
single-threaded. Hardware is a normal development workstation.

### Import

Tycho-2 (CDS I/259), 20 gzip parts, ~159 MB compressed, merged with the
Hipparcos main catalogue (CDS I/239) bright-star supplement:

| Measure | Value |
| --- | --- |
| Stars imported | 2 541 232 (2 539 913 TYC2 + 1 319 HIP) |
| Import wall time | ~18 s |
| SQLite file size | ~364 MB |
| Indexes | `(dec_deg, magnitude)`, `(ra_deg)` |

The importer streams raw Tycho-2 parts, derives Johnson `V = VT - 0.090 * (BT - VT)`,
and merges the Hipparcos supplement with a 3 arcsec positional match (Tycho-2
wins). Bulk loading happens inside a single transaction with indexing deferred
until after insertion.

### Per-chart query benchmark

A chart query is a declination/magnitude range plus an RA range (RA wrapping is
handled for fields that cross 0h). Times are the best of 5 runs for the SQLite
query only; `in_scene` is the count after the exact chart-field test in the
scene builder.

Chart FOV: 20° x 14°.

| Chart | Magnitude limit | Query | Rows | In scene |
| --- | --- | --- | --- | --- |
| test-virgo (187.5, 12) | 8.5 | 30 ms | 484 | 268 |
| test-virgo | 9.0 | 31 ms | 771 | 443 |
| test-virgo | 9.5 | 32 ms | 1 220 | 735 |
| test-virgo | 10.0 | 33 ms | 1 829 | 1 109 |
| test-cygnus (307, 41) | 8.5 | 88 ms | 1 905 | 1 134 |
| test-cygnus | 9.0 | 91 ms | 3 371 | 2 040 |
| test-cygnus | 9.5 | 96 ms | 5 723 | 3 420 |
| test-cygnus | 10.0 | 103 ms | 9 561 | 5 708 |
| test-sparse (192, 27) | 8.5 | 35 ms | 499 | 311 |
| test-sparse | 9.0 | 35 ms | 764 | 479 |
| test-sparse | 9.5 | 36 ms | 1 181 | 720 |
| test-sparse | 10.0 | 37 ms | 1 762 | 1 065 |

Per-chart selection is comfortably interactive (tens of milliseconds). SQLite
is retained as the store; no further optimization is warranted yet. Parquet is
not adopted: it would add a large dependency without a spatial index, and query
latency is already acceptable (`AGENTS.md` section 25).

### Reproduction

```bash
nightsky data fetch-stars          # ~159 MB download (explicit network use)
nightsky data fetch-hipparcos      # ~53 MB download (explicit network use)
nightsky data import-stars         # writes data/processed/stars/tycho2.sqlite
nightsky chart render --chart test-cygnus \
    --star-store data/processed/stars/tycho2.sqlite --magnitude-limit 9.0
```

Raw and processed catalogue data are build inputs and are not committed.

### Licence

Tycho-2 (CDS I/259) and the Hipparcos main catalogue (CDS I/239) are distributed
under **CC-BY-NC-3.0 IGO** (non-commercial). That restriction must be reviewed
before any public or commercial distribution of a generated atlas; see
`AGENTS.md` section 8.4.
