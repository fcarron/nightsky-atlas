# Test suite cleanup audit

Starting commit: `71685c4`; working branch: `refactor/test-cleanup`.
Measurements use the same local catalogues, Python environment and serial
pytest execution. No production code, catalogue, selection, geometry or style
is changed. Artifacts are local under `build/test-cleanup/`.
Environment: Python 3.12.3, pytest 9.1.1, Linux; no parallel test workers.

## Baseline and collection defect

The original `make check` passed **1,406 cases** in **263.90 s pytest time /
265.31 s wall time**, with no failures or reported warnings. There were 99
test files containing 20,756 Python lines, but only **94 modules** were actually
collected: pytest's default `norecursedirs` excludes every directory named
`build`, including `tests/build/`.

This silently excluded five modules and **41 cases**, including atlas build,
publication staging, checksums, provenance, credits and progress checks.
`norecursedirs` now excludes hidden/cache directories instead. An explicit
`--ignore=build` excludes generated artifacts at the repository root without
excluding `tests/build/`. The default `testpaths = ["tests"]` is preserved.

For an equivalent comparison, the original tests from `71685c4` are also run
with complete collection. The modified test tree is preserved and restored
with exact file-hash verification around that baseline run. A preliminary
isolated-directory attempt was discarded because a symlink-resolved path
assertion depended on the checkout location; the recorded complete baseline
runs at the actual repository path.

The complete original suite passes **1,447 cases in 419.14 s pytest time /
420.39 s wall time**, including all 41 previously omitted cases. There are no
failures or reported warnings. Counts include blank lines/docstrings; generated
files are excluded.

## Final measurements

| Metric | Original default run | Original with complete collection | Cleaned complete suite |
| --- | ---: | ---: | ---: |
| Test cases | 1,406 | 1,447 | 1,444 |
| Test files on disk | 99 | 99 | 99 |
| Modules actually collected | 94 | 99 | 99 |
| Python lines in `tests/` | 20,756 | 20,756 | 20,507 |
| Test function definitions | 1,085 | 1,085 | 1,047 |
| `make check` wall time | 265.31 s | 420.39 s | 352.79 s |
| Pytest time | 263.90 s | 419.14 s | 351.52 s |
| Failures / errors / skips | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |

All three runs include successful Ruff checks, with no reported
warnings. Compared at identical collection scope, cleanup saves **67.60 s /
16.1%**, with **249 fewer test lines (1.2%)** and 38 fewer function bodies.
The three fewer executable cases are the documented exact duplicates below;
all other consolidated cases remain separately executable parameters.

The original default run is faster because it omitted 41 important tests; it
is not a valid performance comparison against the final complete suite.
Times are single serial runs, not statistically averaged benchmarks.

`make test-fast` also passes: **1,414 passed, 30 deselected**, in **65.12 s
pytest time / 65.58 s wall time**, without failures or reported warnings.
Its deliberately reduced scope is separate from the full-suite comparison.
Results and timings are under `build/test-cleanup/fast/`.

| Module, including fixture setup | Complete baseline | Cleaned |
| --- | ---: | ---: |
| Production DSO selection policy | 92.58 s | 32.20 s |
| Draft atlas report | 14.02 s | 7.09 s |
| CLI chart tests | 8.94 s | 8.57 s |
| Edition/tiling checks | 106.88 s | 107.75 s |
| Atlas builds | 91.25 s | 91.14 s |
| Publication preflight | 66.81 s | 67.04 s |

Most savings come from report reuse, not from removing checks. The expensive
geometry/build paths retain essentially the same cost and behavior.

Artifacts: `baseline/` records the original default run;
`baseline-complete/` the comparable original run; `after/` the cleanup run;
`comparison.json` contains per-module totals, and `test-function-diff.json`
records every removed/renamed function. JUnit results retain individual cases.

## Analysis and concrete changes

All 99 files were inventoried by function, assertion count and repeated setup
shape. Similar syntax was a review aid, not evidence by itself for deletion.
The largest measured costs in the original default suite were:

| Module/work | Original time | Decision |
| --- | ---: | --- |
| Fine Deep tiling audit | 66.31 s | Preserve its 0.25° coverage and neighbour sampling; mark `slow`. |
| Four complete edition-selection reports | 82.61 s | One read-only module fixture serves distinct assertions. |
| Other edition tests | Included in 110.18 s module total | Preserve real-star, UCAC4, detail, transition/corner and parent checks. |
| Four draft-report computations | 14.14 s module total | Reuse one report for structure, regions and summary; density-input variant stays independent. |
| CLI chart tests | 9.27 s | Preserve real rendering integrations; spy only on two edition/path-dispatch cases. |
| Newly collected preflight tests | 66.81 s | Preserve complete geometry and manifest checks. |
| Newly collected tiled builds, with/without overviews | 58.83 s | Preserve both actual PDF workflows; outputs intentionally differ. |

The shared draft report uses the original structure test's 5° coverage grid;
the former 10° region/summary checks did not depend on the sampling density.
Their regions and text assertions are retained. The separate density test
continues to build a report with its own explicit page data.

### Deleted checks: exact reasons

Only these three test cases are deleted outright:

| Removed test | Retained stronger/equivalent check |
| --- | --- |
| `test_production_selection_matches_alpha_and_reference_counts` | `test_production_selection_hierarchy_and_type_counts` already asserts the identical five edition totals plus counts and hierarchy. |
| `test_standard_keeps_bayer_with_canonical_name_without_flamsteed` | `test_iconic_name_and_systematic_designation_form_one_label` already checks the exact Deneb variant tuple, one logical label and the same `50 Cyg` metadata. |
| `test_flamsteed_only_label_has_no_constellation_suffix` | `test_bayer_flamsteed_and_tycho_suppression` already checks the identical HIP 998/4.5-mag/61 Cyg input and text `61`. |

One repeated `VII/220A` assertion in observing-policy inheritance is removed.
No test is deleted just because it calls an internal function or has a similar
scene to another regression.

### Consolidated cases and setup

| Area | Change | Preserved distinctions |
| --- | --- | --- |
| Atlas/style configuration | 19 repeated rejection functions become two parametrized tests. | Every original invalid payload, exception type and explicitly checked error text. |
| AI configuration | Three rejection functions become three named cases. | Unknown key, blank model, unknown provider. |
| Review schema | Nine rejection functions become nine named cases. | Element/type/action validity, missing/invalid candidates, severity, missing display variant, zero movement, non-label visibility. Root-extra-key test stays separate. |
| Manual overrides | Three rejection functions become three named cases. | Unknown label, invalid candidate and lock without placement; original error messages remain. |
| WDS selection | Three edition-specific functions share one table. | All 34 original values, including inclusive band boundaries and the 0.49/0.5-arcsecond boundary. |
| Store queries | Two cases share one test body. | Ordinary RA interval and RA wrap remain independent parameters. |
| DSO fallback rendering | Shared renderer test covers all five original rows. | Bright/dark nebula and group shapes; STAR/DOUBLE_STAR explicitly keep the M40 identity and X symbol. Thin-X stroke test stays separate. |
| Detail fallback | H400 and Messier/H400 cases share their common scene setup. | H400 can transfer; Messier remains protected; priorities, aliases and result assertions remain distinct parameters. |
| Optimizer cache | Local fresh-cache fixture and standard wrapping mocks replace duplicated constructors and hand-written counters. | Static score and validity tests remain separate, with one static evaluation and changed-neighbour behavior checked. |
| CLI edition dispatch | Two cases inspect the renderer call rather than repeating raster output. | Preset and explicit-path precedence, resolved style and edition-dependent output path. Three existing artifact-producing render/scale integrations remain. |

Shared fixtures stay within their own modules. There is no new global
`conftest.py`, factory hierarchy, production cache or test dependency.

### Files changed

- Test execution/documentation: `pyproject.toml`, `Makefile`, `README.md`,
  `AGENTS.md`, this report.
- Configuration/dispatch: `tests/test_config.py`, `tests/test_cli_chart.py`,
  `tests/ai/test_ai_config.py`, `tests/review/test_schema.py`.
- Atlas/build: `tests/atlas/test_editions.py`,
  `tests/atlas/test_observing_config.py`, `tests/atlas/test_report.py`,
  `tests/build/test_atlas.py`, `tests/build/test_preflight.py`.
- Catalogues: `tests/catalog/test_production_selection_policy.py`,
  `tests/catalog/test_galaxy_visibility.py`,
  `tests/catalog/test_pocket_dso_quality.py`, `tests/catalog/test_selection.py`,
  `tests/catalog/test_store.py`, `tests/catalog/test_wds_selection.py`.
- Layout/rendering: `tests/layout/test_optimizer.py`,
  `tests/layout/test_overrides.py`, `tests/layout/test_star_label_policy.py`,
  `tests/render/test_cairo.py`.

## Critical regressions deliberately retained

- Stereographic projection/inverse, orientation, poles, RA wrap and coordinate
  label placement, including final accepted annotations and full-edition audits.
- All main-edition geometry, westward numbering, fine sampled sky coverage,
  critical ring transitions, projected corners, neighbour overlap and detail
  relationships. The expensive Deep audit is not coarsened.
- OpenNGC, VizieR, UCC quality/matching, canonical IDs, source provenance,
  duplicate prevention, Tycho/Hipparcos, UCAC4 calibration and WDS tests.
- Pocket ⊆ Standard ⊆ Deep/Eyepiece, curated membership, excluded components,
  Crumey scores/classes and catalogue-count regressions.
- Mandatory labels, density bypass, locked placements, coordinated repair,
  ellipse/contour geometry, source ownership, leaders and close-star clearance.
  The near-identical binary-system and individual-component distance cases
  remain separate because they identify different sources.
- Star/DSO fill order, clipped frame strokes, foreground star visibility,
  compact galaxies near bright stars, Melotte-style fills, M40 thin X marks,
  monochrome/color separation and print-scale extents.
- Milky Way seam/antipode/overlap regressions, LMC/SMC contour validity,
  source-map provenance, deterministic Gaia generator and cloud-ellipse removal.
- PDF navigation, physical dimensions, glyph metrics, frontmatter/index,
  deterministic layout/replay and all publication checks. Build tests now
  participate in ordinary `make check` as intended.

## Focused mutation probes

Seven mutations are applied only to in-memory functions in separate pytest
processes; production files are never edited. Each mutation is detected by
assertion failures, with no collection/setup errors:

| Deliberate defect | Failing cases |
| --- | ---: |
| Accept invalid style configurations | 13 |
| Accept invalid review issues | 9 |
| Allow protected Messier-label suppression | 1 |
| Reinstate blanket H400 protection | 1 |
| Reject the inclusive 0.5″ WDS floor | 3 |
| Render every fallback shape as a square | 4 |
| Ignore changed-neighbour collisions in cached validity | 1 |

The normal targeted suite passes 245 cases. Mutation logs and JUnit results
are in `build/test-cleanup/mutations/`; `results.json` records exit codes,
failure counts and errors. These probes demonstrate specific retained guards;
they are not a comprehensive mutation or line/branch-coverage measurement.

## Developer workflow and limits

`make test-fast` runs `pytest -m "not slow and not integration"`. The three
measured fine-resolution tiling audits and five expensive build/preflight tests
that repeat full-sky sampling are `slow`. `integration` identifies full local
catalogue/store checks; synthetic import, layout, rendering, remaining
publication and coarse full-sky tests remain in the fast run. Neither marker is
excluded from `make test` or `make check`.

Prefer `pytest tests/<area>/test_<subject>.py` for a focused change, then
`make check` for complete validation. Available markers are listed by
`pytest --markers`. README and AGENTS document the distinction.

```bash
make check
make test-fast
.venv/bin/python -m pytest --collect-only -q
PYTEST_ADDOPTS="--durations=50 --junitxml=build/test-cleanup/results.xml" make check
```

The remaining cost is mostly meaningful geometric sampling and complete
catalogue evaluation. Further reductions would need independent evidence:
do not weaken the sky grid, replace full-catalogue checks with guessed counts,
or merge distinct star/DSO/contour collision cases to reduce a headline count.
The newly discovered preflight tests repeat Standard sky sampling for distinct
provenance errors. Sharing that read-only geometric result could save time, but
would also need explicit checks that each validation call uses the right chart
set and sampling step. It is left intact in this cleanup.
The line reduction is intentionally modest; most existing cases were useful.
Module-scoped report fixtures must remain read-only, and the fast target is
not a replacement for full validation. No new runtime/dev dependency is added.
