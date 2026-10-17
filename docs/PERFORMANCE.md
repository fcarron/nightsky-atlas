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
