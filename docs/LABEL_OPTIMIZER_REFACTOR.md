# Label optimizer refactor

Branch: `refactor/label-optimizer`, based on `1e29fd6`.
Scope: structural changes only; no selection, geometry, thresholds, weights,
search limits, candidates, priorities or optimization order changed.

## Architecture and decisions

Previously `optimizer.py` combined scene-derived obstacles, spatial queries,
score caches, placement, conflict repair, leader decisions and reporting.
The actual phases are unchanged:

1. `labels.py` / `candidates.py` construct measured, ordered candidates before
   optimization; `selection.py` handles semantic selection.
2. Prepare anchors, printed source geometry, indices, weights and initial costs.
3. Place locked overrides, then remaining labels greedily in `(-priority, id)` order.
4. Local repair → joint DSO component search → hard-conflict repair.
5. Stellar ambiguity leaders → direct/routed DSO fallbacks → final cost evaluation.
6. Diagnostics → targeted long-label leaders → diagnostics again if labels changed
   → aggregate metrics. Diagnostics feed decisions and cannot simply move last.

| Responsibility after refactoring | Location |
| --- | --- |
| Public entry and explicit phase sequence | `layout/optimizer.py:optimize_labels` |
| Greedy placement / stellar leader fallback | Named helpers in `optimizer.py` |
| Local, joint and hard repair / DSO leader decisions | `optimizer.py` |
| Printed geometry, indices, candidate validity, score cache and layout evaluation | New `layout/placement.py` |
| Per-label diagnostics and aggregate metrics | New `layout/diagnostics.py` |
| Cost formulas / source geometry / routing / hard validation | Existing `scoring.py`, `association.py`, `leader_lines.py`, `collision.py`, `validation.py` |

The existing score cache supplies immutable geometry/settings to the two
extracted phases. There is no new context class, framework or runtime dependency.
Nine unused parameters were removed from beam search and its joint-phase caller;
unused `symbols` / `labels` arguments were removed from local repair / anchor setup.
The existing weighted ownership sum is shared with diagnostics, preserving its
exact expression order. One trivial preference wrapper and one unused constant
were removed. All remaining public API signatures are unchanged.

Risk decisions:

- Moving shared geometry/cache and diagnostics is structural; original bodies and
  cache eviction/insertion semantics are retained. Diagnostics never import the
  optimizer, preventing a dependency cycle.
- Extracting greedy/stellar leader phases needs exact statement/order checks;
  the saved baseline, AST comparison and real-chart comparisons verify these.
- Hard repair's closures share mutable placements, rejection caches, budgets and
  nested searches. This necessary algorithmic complexity remains together.
- Validity and rejection diagnostics look similar but have different predicates
  and precedence. They were deliberately not unified.
- Cached scoring, direct breakdowns and full-layout evaluation use different
  symbol/query sets. No new caching or geometry reuse was introduced.

## Size

Python physical lines, including blanks/docstrings:

| Area | Before | After |
| --- | ---: | ---: |
| `optimizer.py` | 2,867 | 1,602 |
| Entire `layout/` | 7,079 | 7,129 |
| Entire `src/` | 38,172 | 38,222 |

Two new modules: `placement.py` (756 lines), `diagnostics.py` (559 lines).
Two named phase functions added, one forwarding function removed; no new classes.

| Function | Lines before → after | Other change |
| --- | ---: | --- |
| `optimize_labels` | 369 → 216 | Branch nodes 29 → 6; extracted branches preserved |
| `_joint_component_search` | 79 → 70 | Parameters 14 → 5 |
| `_joint_dso_optimize` | 85 → 67 | Parameters 14 → 5 |
| `_repair_dso_hard_conflicts` | 582 → 564 | Shorter beam-search calls; all 87 branch nodes retained |
| `_local_repair` | 108 → 107 | Parameters 16 → 15 |
| `_consider_dso_leader_fallbacks` | 197 → 197 | Unchanged algorithm |

## Validation

- Before `make check`: Ruff passed; **1,450 passed in 373.54 s**, wall 374.89 s.
- After `make check`: Ruff passed; **1,453 passed in 367.92 s**, wall 369.19 s.
- Focused layout/symbol tests: 395 passed after separation; 398 passed after
  simplification and three new phase-order/diagnostic/input-preservation cases.
- Existing test expectations retained; private helper imports/patch targets now
  point to their owning modules. No scientific/layout regression test removed.
- All 45 original top-level functions/classes checked: unchanged ASTs, or exact
  equivalence after inlining extracted phases, removing unused arguments and
  expanding the shared sum. The sole removed function was the preference wrapper.
- 15 real optimizer invocations: exact input equality and exact complete output
  equality, including all candidates, coordinates, hidden flags, assignments,
  leader routes, cost components, repair/search stats and diagnostics.
  Only the measured `optimizer_runtime_s` field is excluded.
- Crowded P21 with detailed candidate diagnostics: original, refactored and
  repeated refactored results exactly equal; runtimes 35.46 / 35.14 / 35.19 s.
- 12 main/detail charts, 47 combined PDF pages: identical pixels at 100 dpi;
  all 12 preview PNG files byte-identical. Six individual PDFs also pixel-identical
  at 200 dpi. PDF text, destinations, bookmarks and page labels identical.
- All manifests match after excluding timestamps, source fingerprints and artifact
  checksums; draft reports match byte-for-byte. Ordinary output validation passes.
- Final proof manifests retain 936 placed labels; P20/P21 retain exactly seven
  permitted detail-label suppressions each; no new
  missing labels or hard issues. Existing Deep detail issue on DD01 remains unchanged:
  `label:dso:NGC7335` overlaps `NGC7331` on the NGC7331/Stephan's Quintet detail.
- Manual preview review: Pocket Virgo P20, Standard NGC7331 S029, Deep Cygnus D096.

## Performance and artifacts

Identical inputs/styles, two spawned workers, full atlas assembly for each subset:

| Proof subset | Main + detail charts | PDF pages | Hard before/after | Wall before/after |
| --- | ---: | ---: | ---: | ---: |
| Pocket color: P09, P15, P20, P21; PD01/PD02 | 6 | 19 | 0 / 0 | 113.32 / 112.74 s |
| Standard B&W: S029, S033 (NGC7331, M13) | 2 | 12 | 0 / 0 | 45.30 / 46.53 s |
| Deep color: D093, D096, D100; NGC7331 detail | 4 | 16 | 1 / 1 | 120.93 / 120.81 s |

First optimizer call: P20 21.13 → 20.34 s; P21 22.36 → 22.51 s;
Deep Cygnus 18.75 → 18.70 s. These initial runs overlap the full test suite;
small differences do not establish a speed improvement. Total proof process CPU
403.47 → 402.07 s; peak reported RSS 960,712 → 952,804 KiB. RSS is the reported
process/child maximum, not summed simultaneous worker memory.

A sequential Pocket repeat without parallel test/proof jobs loads the archived
original optimizer, then the refactored optimizer: **109.67 → 110.00 s** (+0.30%).
Reported peak RSS: **783,580 → 783,648 KiB** (+68 KiB). Both repeated builds match
the original baseline: all 19 PDF pages, six preview files, complete layout/
selection metadata and every captured optimizer result. No meaningful runtime or
memory regression is measured. The 15 original/refactored capture JSON files and
all three detailed P21 outputs are also byte-identical after omitting runtime.

Artifacts: `build/optimizer-refactor/` contains original source/input snapshots,
`baseline/`, `after/`, `detailed/`, AST/numeric/PDF comparison JSON, logs and scripts.
Reproduce with `.venv/bin/python build/optimizer-refactor/proofs.py baseline`,
then the same command with `after`. Run `compare.py`, `compare_captures.py` and
`print_proof.py` from that directory through the same interpreter. The archived
baseline optimizer allows replaying original behavior without modifying the checkout.

Limits/recommendation: these are representative subset builds, not new full
39/129/492-chart atlases or publication approval. Keep hard repair and the DSO
leader search unchanged for now. A future performance task can profile repeated
geometry queries separately. Agents can now inspect one named phase or the
reporting module without loading all optimizer mechanics; hard repair still
requires its complete shared search context.
