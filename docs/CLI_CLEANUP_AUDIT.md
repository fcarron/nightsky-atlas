# CLI cleanup audit

Baseline: `3fe896a`, branch `refactor/cli-cleanup`, 2026-10-15.
Scope: CLI adapters and exclusively used research code. Atlas definitions,
catalogue data, selection policies, layout and rendering are preserved.
Local evidence is in `build/cli-cleanup/`; original input files stay untracked.

## Command decisions

The baseline exposes 42 command paths, including two aliases of `data dso-info`.
Each row below accounts for one path. KEEP means the command remains supported;
MOVE retains the workflow outside the main CLI; REMOVE deletes obsolete or
redundant functionality, including its exclusive implementation and tests.

| Command | Decision | Evidence and reason |
| --- | --- | --- |
| `chart render` | KEEP | README and CLI/build tests; single-page PDF, preview and layout diagnostics. |
| `chart validate` | KEEP | CLI/layout tests; deterministic geometry validation. |
| `chart review` | KEEP | Active review artifacts, AI provider/loop tests and recorded M11/M13 decisions; retains optional one-step AI review. |
| `chart magnitude-scale` | KEEP | README and CLI tests; practical physical print-size proof. |
| `data fetch-stellarium-figures` | KEEP | Pinned, checksum-verified source used by current charts. |
| `data import-stellarium-figures` | KEEP | Current constellation importer; tested in `test_stellarium_figures.py`. |
| `data fetch-stars` | KEEP | README; production Tycho-2 source. |
| `data fetch-hipparcos` | KEEP | README; production bright-star supplement. |
| `data import-stars` | KEEP | README; scientific parsing/merge/store tests. |
| `data star-count` | KEEP | Small, useful import verification. |
| `data tycho-density-report` | REMOVE | Completed calibration in `TYCHO_DENSITY_CALIBRATION.md`; only CLI, its tests and the faint-density report call this module. No production dependency. |
| `data star-label-report` | KEEP | CLI test and recent stellar-label completeness work; useful selection diagnostic. |
| `data reindex-stars` | KEEP | Store maintenance and idempotence tests; supports existing local databases. |
| `data fetch-ucac4` | KEEP | Active optional faint-star source, including PD02 and Eyepiece. |
| `data import-ucac4-faint` | KEEP | UCAC4 parsing, photometry and deduplication remain production code. |
| `data faint-star-count` | KEEP | Verifies the optional store and its magnitude-source counts. |
| `data faint-star-density-report` | REMOVE | Completed paper-density study in `FAINT_STAR_SUPPLEMENT.md`; no importer/build dependency. |
| `data faint-star-performance-report` | REMOVE | Old regional query microbenchmark; no importer/build dependency. Store/query tests remain. |
| `data fetch-openngc` | KEEP | README; current DSO source. |
| `data import-openngc` | KEEP | README and importer/selection tests; stable physical identities. |
| `data fetch-vizier-dsos` | KEEP | README; supplements used by current selections. |
| `data import-vizier-dsos` | KEEP | Current crossmatching and provenance workflow. |
| `data fetch-ucc` | KEEP | Pinned UCC 260615 source and integrity checks. |
| `data import-ucc` | KEEP | Current conservative merge and quality rules. |
| `data dso-info` | KEEP | Canonical object, aliases and source records; complementary to `why-object`. |
| `data catalog-object` | REMOVE | Alias of `dso-info`; no independent behavior or callers. |
| `data catalogue-report` | KEEP | Referenced in `DATA_SOURCES.md`; source/import inventory used in catalogue audits. |
| `data selection-report` | KEEP | Current cross-edition curation and regression tests; includes Pocket and hierarchy diagnostics. |
| `data pocket-selection-report` | REMOVE | Older Pocket-only audit superseded by the current all-edition report; only CLI and one report-specific test call the 471-line module. Historical results remain documented. |
| `data fetch-wds` | KEEP | README; current semantic double-star overlay. |
| `data import-wds` | KEEP | README and catalogue/system tests; not replaced by single-star imports. |
| `benchmark ai-review` | MOVE | Completed model-selection study but still useful for provider changes. Run `python tools/benchmark_ai_review.py`; preserve runner, cases and tests. |
| `atlas catalog-object` | REMOVE | Redundant object inspection/selection wrapper. Use `data dso-info` and `atlas why-object`; update common-name test and documentation. |
| `atlas why-object` | KEEP | Explicitly requested and actively used for DSO selection investigations. |
| `atlas tile` | KEEP | Geometry inspection and deterministic chart numbering. |
| `atlas coverage` | KEEP | Full-sky geometry verification. |
| `atlas report` | KEEP | Draft coverage, navigation and layout diagnostics. |
| `atlas validate` | KEEP | Manifest/checksum and publication checks. |
| `atlas build` | KEEP | All editions, details, color/SW, PDF/PNG, workers and publication mode. |
| `research observing-list-coverage` | REMOVE | Completed local NSOG/AL/curation investigation; only research adapters and research tests depend on it. Current curation fixtures and production matching are separate. |
| `research nsog-nebula-analysis` | REMOVE | One-time rating/coverage study; no production importer, selector or renderer calls it. Historical scientific conclusions remain. |
| `research observing-list-compare` | REMOVE | Companion to the retired external-list reports; no independent active caller. |

## Exclusive code and retained boundaries

- Delete `research/nsog_nebula_analysis.py` and
  `research/observing_lists/`, plus their exclusive tests. Do not delete curated
  observing lists, selection/matching infrastructure or the active label-review
  experiment tests in `tests/research/`.
- Delete `catalog/tycho_density.py`, `catalog/faint_density.py` and
  `catalog/pocket_selection.py`, plus exclusive report tests. Preserve all
  magnitude conversion, UCAC4 calibration, catalogue queries and selection code.
- Remove the unused legacy `import_iau_stick_figures` parser/importer. Its
  `_positions` helper is still used by Stellarium: preserve it unchanged in the
  Stellarium module before deleting `catalog/iau_stick_figures.py`.
- Keep `catalog/openngc_outlines.py`: although it has no static caller, it
  regenerates a source product used by chart builds. Lack of imports alone is
  insufficient evidence of dead code.
- Keep `research/nebula_curation.py`: its tests still validate the checked-in
  editorial curation documents and prevent proprietary research-field leakage.
- Keep the AI reviewer, action validation, bounded loop, replay and credentials
  configuration. They have explicit design contracts and tests; their optional
  status does not establish abandonment.
- No dependency can be removed safely: the retained importers, renderer, contour
  generators and AI provider still use the declared runtime packages.

Catalogue CLI adapters have one dedicated module, `cli_data.py`. The main
`cli.py` owns argument dispatch and chart/atlas commands. Shared rendering inputs
are defined once, preserving command-specific defaults and options. This split
accompanies actual code deletion; it is not counted as a source reduction.

## Validation and measurements

Baseline logs, command/default inventory, source line counts, selection report
and rendered Pocket proofs were captured before changing implementation files.

| Measure | Before | After | Reduction |
| --- | ---: | ---: | ---: |
| CLI command paths | 42 | 32 | 10 |
| `cli.py` Python lines | 2,434 | 981 | 1,453 |
| Combined CLI adapters (`cli.py`, `cli_data.py`) | 2,434 | 1,900 | 534 |
| All Python under `src/` | 42,177 | 37,821 | 4,356 |
| Python under `src/` and `tests/` | 63,464 | 58,577 | 4,887 |
| All project Python, including `tools/` and `scripts/` | 66,889 | 62,084 | 4,805 |

Counts include blank lines and docstrings, using tracked Python files plus the
three new implementation/test/tool files. Generated files, environments and
unrelated untracked inputs are excluded. Thirteen source modules and three
exclusive test modules are deleted. The new data adapter contains 919 lines;
the standalone benchmark contains 82. No runtime dependencies were added or
removed. There are now four `chart`, 22 `data` and six `atlas` commands.

- Baseline `make check`: lint passed; **1,436 tests passed, one failed** in
  268.64 seconds. The failure was an obsolete expectation of only PD01/PD02,
  although committed Pocket configuration already includes PD03/PD04. Update
  that assertion to the four configured detail codes; no atlas definition is
  changed.
- Post-cleanup `make check`: **lint passed; all 1,406 tests passed** in
  271.87 seconds. Thirty-five tests exclusive to removed features were deleted;
  four offline CLI integration tests were added. The existing detail-code
  assertion was corrected as described above.
- All 32 remaining leaf commands preserve their options, types, defaults,
  required flags and choices, compared against the baseline parser inventory.
  All 36 help pages (root, three groups, 32 leaves) succeed in subprocesses.
- All 31 retained command handlers other than `dso-info` are identical as Python
  syntax trees. `dso-info` loses only the branch for the removed atlas wrapper;
  its supported data-command output is unchanged. The HIP-position resolver
  moved out of the retired IAU importer is also syntax-tree-identical.
- Four offline CLI integration tests cover repeatable OpenNGC import and
  manifests, Tycho/Hipparcos merging and real store-backed Stellarium import,
  WDS overlay import, and missing-input errors. The focused existing CLI/name/
  constellation suite also passed (26 tests).
- The complete current `selection-report` JSON is byte-identical. Selected
  counts stay Pocket **1,133**, Standard **3,093**, Deep/Eyepiece **11,904**.
- An Eyepiece Deep single-chart render with the real optional UCAC4 store
  succeeds: 1,778 stars and 21 DSOs on `eyepieceDeep-105`.
- The moved benchmark tool completes one optimized Virgo case with the offline
  mock reviewer, valid schema and no runner errors. Provider, replay and action
  behavior remain covered by the retained AI tests.

| Pocket proof | Chart/detail pages | PDF pages including furniture/index | Hard issues before → after | Changed raster pages |
| --- | ---: | ---: | ---: | ---: |
| Color Variant A: P15/P20/P23, PD01/PD02/PD03 | 6 | 19 | 7 → 7 | 0 |
| Black/white: P15, PD02 | 2 | 12 | 0 → 0 | 0 |

All eight chart preview PNGs are byte-identical. All 31 combined-PDF pages
rasterized with Poppler at 72 dpi are pixel-identical, including frontmatter,
overviews, directory and index. All per-chart manifest records are identical,
including layout hashes, selections, suppressions, issues and navigation.
Only the expected `code` input fingerprint changes; all other input
fingerprints match. Both proof atlases pass ordinary `atlas validate`.
Publication validation correctly rejects the incomplete proof atlas rather
than treating this as a publication build.

Artifacts:

- `build/cli-cleanup/baseline/`: original logs, parser inventory and proofs.
- `build/cli-cleanup/after/color/pocket/atlas.pdf`
- `build/cli-cleanup/after/bw/pocket/atlas.pdf`
- `build/cli-cleanup/after/eyepiece/eyepieceDeep/charts/eyepieceDeep-105/chart.pdf`
- `build/cli-cleanup/comparison.json`, `help-checks.json`, `line-counts.json`
- `build/cli-cleanup/make-check-after.log`, `import-check.log`,
  `benchmark-check.log`, `publication-check.log`

These are representative partial builds, not complete new atlases. Live
catalogue downloads and paid AI calls were not repeated. Existing fetcher,
catalogue-quality and AI-provider tests remain offline; the scientific
implementations of all supported catalogue imports are unchanged.

## Remaining complexity and uncertain removal candidates

- `cli_data.py` is the largest remaining CLI responsibility: several source
  formats, provenance manifests and two complementary current reports. Keeping
  these explicit is clearer than introducing a generic importer framework.
- The chart render/review/validate handlers still share parts of the layout
  workflow. Further unification would reach into build behavior and was not
  needed for this cleanup.
- `catalog/selection_analysis.py` remains large (1,123 lines), but supports
  active curation audits, `why-object`, metadata diagnostics and regression
  tests. Do not remove it solely because it is diagnostic code.
- The optional AI loop, OpenNGC outline converter, curation-document validator
  and star-store reindex operation could be revisited only after their supported
  workflows are explicitly retired. There is insufficient evidence that these
  are unused; they remain available.

Historical research documents retain their results, but obsolete executable
examples and adapter-extension instructions are removed or replaced with
current diagnostics. `AGENTS.md` and the architecture map name the two CLI
entry points and the separate benchmark tool. No new CLI framework, catalogue
policy, chart geometry or rendering behavior is introduced.
