# Alpha readiness audit — 2026-10-16

Scope: local `refactor/label-optimizer`, baseline `7b790a1`, plus the small
installation/documentation/test corrections described below. No scientific,
selection, optimizer, style or chart-rendering code was changed.

## Follow-up: non-layout corrections

At the user's request, layout findings are deferred. The following targeted
corrections follow the original audit; the evidence tables below describe the
initial audit rather than a claim that those corrections were already present.

- WDS importer documentation and generated metadata no longer assert an
  unverified public-domain grant. Source URL and the USNO acknowledgement are
  recorded. Only the existing local manifest was updated; the stored WDS object
  JSON retains SHA-256 `5fce088db380434410455bbf08264d411c624c15643820aa9bf9e956b81a488c`.
- `docs/ATLAS_DISTRIBUTION.md` supplies a download companion with attribution,
  source/licence/data links, transformations and accepted caveats. It includes
  the fuller AAVSO/APASS acknowledgement. No new source permission is asserted.
- `tools/prepare_alpha_download.py` uses existing ordinary validation and input
  fingerprinting to prepare a local PDF package, notices, exact Gaia data,
  configuration copies, input/catalogue hashes and packaging environment.
  It records layout issues, rejects stale inputs and does not upload anything
  or alter strict publication validation. Raw catalogues/private paths are
  excluded from the package inventory.
- A pinned OpenNGC snapshot reproduces all 238 outline component records
  exactly; the existing converter's extra `source_url` explains the different
  whole-file checksum. The archive, checksum and invocation are documented in
  `docs/DATA_SOURCES.md`. Production contours remain untouched.
- The Milky Way source record now describes both contour strokes and the
  existing experimental colour fills, without changing their style.

Follow-up verification: `make check` passes **1,458 tests** (374.73 s).
The full colour-A Pocket rebuild preserves **43 byte-identical chart PNGs**,
identical chart layout/diagnostic records and identical extracted combined-PDF
text. All **15 hard issues and one warning** remain. This is not a claim of a
new pixel comparison of every editorial PDF page.

Verified local archive: `build/downloads/pocket-alpha-2026-10-16.zip`, with
30 checksummed files and SHA-256
`dcd08e7a94f456beb985f14381f8511eb0b95db12dfc7f72929e6362bd3a7a9f`.
ZIP integrity and every packaged checksum were checked. It contains no raw
catalogues, SQLite stores or private absolute paths in the inventory. Its
environment record describes packaging time, not inferred historical build
dependencies. The exact code fingerprint accompanies the commit ID because
these working-tree changes are not yet committed. No upload was performed.
New PDF: `build/alpha-cleanup/verified-pocket/pocket/atlas.pdf`.
Verification: `build/alpha-cleanup/verification.json` and `make-check.log`.
The remaining source-rights caveats and layout findings remain open; publication
still requires the actual download to retain these notices/data.

## Decision

**The source project is technically suitable for an explicitly experimental
public alpha. No further architectural refactoring is required first.**
A public atlas download still needs its actual distribution package checked:
attach the applicable notices and corresponding Gaia contour data, and disclose
the remaining layout defects. The PDFs tested here are drafts, not
`--publication` output or field-approved release candidates. Existing accepted
licence uncertainties remain uncertainties; this audit provides no legal clearance.

## Prioritized findings

Effort estimates are engineering estimates, excluding third-party response time.

| Priority | Component / evidence | Impact and recommended action | Effort / status |
| --- | --- | --- | --- |
| BLOCKER, fixed | `tests/atlas/test_editions.py`, `tests/catalog/test_pocket_dso_quality.py` | A clean source checkout failed four tests because local catalogues were assumed. Add explicit missing-file guards to the existing integration cases; also prevent one DSO test passing vacuously with an empty scene. All five affected cases still run and pass with local data. | Fixed; clean `make check` passes. |
| BLOCKER, local package prepared | `render/front_matter.py` credits; `THIRD_PARTY_LICENSES.md`; Gaia `SOURCE.md` | Standalone PDF credits lack licence/data-access URLs. The follow-up package supplies associated notices, retained BSD/OFL/CC notices, adaptation information and exact ODbL contour data. Preserve the package or prominent companion links when publishing, including terms relevant to the object index. | Prepared and checksum-verified locally; public hosting is not part of this task. |
| SHOULD FIX, fixed | `cli_data.py:901`, `catalog/wds.py` module documentation | Generated WDS manifests assert public-domain status, while current source documentation explicitly does not rely on an established grant. Align these metadata statements with the verified evidence before shipping manifests. Do not change data or infer new restrictions. | Fixed in follow-up; regression test covers metadata and repeat import. |
| SHOULD FIX | Pocket P11, P23, P28, P34, PD03, PD04; `build/alpha-audit/layout-issues.json` | Fifteen hard findings remain. Triage real text/outline collisions separately from labels legitimately inside extended objects. Review P11's M84/M86 association at the page edge first. Use existing overrides where appropriate; do not weaken the validator globally. | About half a day for triage; fixes depend on findings. Not every hard finding prevents an explicitly disclosed alpha. |
| SHOULD FIX, fixed | `catalog/openngc_outlines.py`, README data preparation | Current local builds auto-load imported OpenNGC outlines. README fetch/import steps do not reproduce this additional processed layer. Document the exact upstream revision and invocation of the existing importer, so a new user can reproduce the reviewed charts. The layer **is** included in build input fingerprints. | Documented and verified in follow-up; no new importer/CLI needed. |
| SHOULD FIX, inventory provided | Catalogue downloads, `pyproject.toml`, release manifests | Moving upstream downloads and unpinned dependencies do not recreate a historical release automatically. The package now records input/catalogue/provenance hashes, versions, configuration copies and native/Python packaging dependencies. Retain matching source and raw snapshots separately; the inventory does not recover missing historic files. | Implemented; exact old snapshot retention remains an operational responsibility. |
| LATER | `layout/optimizer.py`, `render/cairo.py`, `atlas/config.py` | Large modules and a 564-line hard-conflict repair remain, but encode tested behavior. Profile and isolate a demonstrated local concern before further refactoring. No alpha-critical dependency cycle or safely removable scientific subsystem was identified. | Several days if later justified. |
| LATER | `catalog/selection_analysis.py`, historical tools/docs | Report warns about 418 Deep objects absent from legacy Reference; Pocket ⊆ Standard ⊆ Deep = Eyepiece still holds. Clarify the legacy diagnostic expectation, and archive completed research utilities only after checking consumers. Do not alter selections to satisfy Reference. | 1–2 hours for diagnostic clarification. |
| LATER | Packaging and observing epoch | Installation is a repository workflow; atlas/style fixtures are not a self-contained wheel deployment. Positions are for J2000, not propagated to the observing date. Documented scope, not a newly discovered astronomy defect. | Separate future tasks. |

## Architecture and agent workflow

The current data flow is findable without reading a single monolithic pipeline:

| Responsibility | Entry points | Matching tests |
| --- | --- | --- |
| Import, identity, units and provenance | `catalog/`; `cli_data.py` | `tests/catalog/` |
| Edition configuration and tiling | `atlas/config.py`, `atlas/tiling.py` | `tests/atlas/` |
| Select and project chart contents | `build/chart.py`, `scene/builder.py` | `tests/scene/`, `tests/build/test_chart.py` |
| Labels, candidates, scores, repair and diagnostics | `layout/labels.py`, `candidates.py`, `scoring.py`, `optimizer.py`, `diagnostics.py` | `tests/layout/` |
| Vector graphics and exact text metrics | `render/cairo.py`, `symbols.py`, `text.py` | `tests/render/` |
| Main/detail orchestration, PDF assembly, publication | `build/atlas.py`, `details.py`, `document.py`, `preflight.py` | `tests/build/` |

The source contains 117 Python modules / 38,222 lines. `build/atlas.py` is
1,859 lines; its coordinator is 259 lines. The optimizer is 1,602 lines.
Static analysis found no cycles among explicitly resolved absolute module
imports; this is not proof against every possible runtime import cycle.
Shared text/symbol geometry couples layout and rendering deliberately: do not
duplicate those calculations to make the dependency graph look cleaner.
No network-client imports were found in build/scene/layout/render.

All 35 command/group help entries were checked. Production dispatch and data
commands remain separate; specialist tools stay outside the CLI. Existing
optional AI, UCAC4 and eyepiece code has consumers and is not presumed dead.
Strict configuration rejects unknown keys. No new configuration was added.
`AGENTS.md` now has one short rule covering reuse, boundaries, research tools,
justified configuration/exceptions, retirement of experiments and regressions.

## Installation and reproducibility evidence

Actual host: Ubuntu **24.04.5 LTS**, Python **3.12.3**, Pango **1.52.1**,
Cairo **1.18.0**. A fresh virtual environment and a catalogue-free export of
tracked `HEAD` files were tested. This was **not a fresh OS/container test**:
Docker was unavailable in this WSL distribution. The host lacked the README's
`python3-gi-cairo` prerequisite; the Ubuntu 3.48.2-1 package was downloaded and
its Cairo bridge staged only inside the audit environment. System packages
and the working development environment were not changed.

Pip editable installation succeeded with freshly resolved dependencies:
NumPy 2.5.4, SciPy 1.18.1, Pycairo 1.29.2, Pydantic 2.14.1, HTTPX 0.28.1,
PyYAML 6.0.1, pytest 9.1.1 and Ruff 0.17.1. Versions and installation logs
are under `build/alpha-audit/`. This does not establish compatibility with all
future versions or with native Windows/macOS.
Pip also reported conflicts for the host's inherited `nala` utility; these
are unrelated system-site packages, not NightSkyAtlas dependencies. The host
therefore should not be described as a pristine dependency environment.

Small safe corrections:

- README/CI explicitly install compiler and Python headers for Pycairo builds.
- Their Pango smoke check now creates a layout with a Cairo context; imports
  alone miss a broken/missing GI Cairo bridge.
- The fixture quickstart uses `--optimize`: **7 stars, 2 labels**, vector PDF
  and PNG, no catalogue downloads. Zero DSOs is expected in this tiny fixture.
- README explains alpha limitations, nonzero build exit status, edition counts,
  colour opt-in and the combined catalogue. Full Pocket requires UCAC4 for
  PD02; the ordinary main-chart presets do not require this faint-star store.

Live OpenNGC fetch/import succeeded into isolated audit paths: **13,372
records**. UCC 260615 download and published checksum verification succeeded;
reimport against the local combined catalogue produced a **byte-identical**
JSON file (SHA-256 `6642681aedbb9313b7a93ff77cb71856ea41f06c8abb61506bf812ea898b1dd3`).
The 37,611 normalized records include 36,817 physical DSOs. No production
catalogue was overwritten. Tycho-2/Hipparcos, UCAC4 and every historical
VizieR table were **not** freshly downloaded; their existing local stores,
fixtures, checksums and integration tests were used.

## Scientific and cartographic checks

- Tycho-2 uses mean ICRS J2000 positions, with its documented special component
  propagation; Hipparcos is propagated from J1991.25 to J2000. UCAC4 uses J2000
  ICRS. No claim of current-date proper-motion correction is made.
- Catalogue/alias tests cover stable identity, deduplication and source-specific
  units. UCC `r_50` remains a half-membership radius, not a visual diameter.
- Existing projection, hemisphere, ring/neighbour, size, text-metric,
  mandatory-label, detail-coverage and Crumey visibility tests were run.
  Visibility is an observing heuristic, not a detection guarantee.
- Full Pocket coverage: **1,036,800 samples at 0.25°**, zero uncovered samples;
  **178 neighbour pairs**, zero reported non-overlapping neighbours. Sampling
  is not a mathematical proof of continuous coverage.
- Actual selected unique DSOs: **Pocket 1,133; Standard 3,093; Deep 11,904**.
  No selections, coordinates, outlines, geometries or font sizes changed.
- Pocket PDF: A4 landscape, 841.89 × 595.276 PDF points; embedded font subsets,
  no raster images reported by `pdfimages`. Physical scale must still be
  preserved by printing at 100%, without fit-to-page.

| Build / check | Result | Time / evidence |
| --- | --- | --- |
| Baseline `make check`, development environment with catalogues | Ruff passes; **1,453 passed** | 387.87 s pytest; `make-check.log` |
| Clean export before guards | **4 failed, 1,432 passed, 17 skipped** | 272.01 s; failures were missing local data |
| Clean export after guards, fresh dependencies | Ruff passes; **1,431 passed, 22 skipped** | 273.52 s; `clean-fixed-make-check.log` |
| Five affected integration cases with real catalogues | **5 passed** | 28.35 s; `integration-with-data.log` |
| Post-change full suite, fresh dependencies and real data | Ruff passes; **1,453 passed** | 369.54 s; `fresh-full-data-check.log` |
| Complete Pocket colour A, 4 workers | **39 main + 4 detail; 74 PDF pages; 15 hard, 1 warning** | 299.4 s build; about 906 s accumulated CPU |
| Standard B&W proof, 4 workers | **4 main + 4 detail; 6 hard** | 154.5 s |
| Deep colour A proof, 4 workers | **4 main + 2 detail; 1 hard** | 192.8 s |
| Ordinary output validation | Passes for all three audit builds | Manifest/checksum validation |
| Pocket publication validation | Correctly rejects ordinary build and hard issues | `publication-pocket.log` |

Standard/Deep proofs are samples, **not new complete-edition validations**.
They cover Cygnus, Virgo, M13, Orion and NGC7331/Stephan's Quintet with details.
All build commands and per-chart issues are retained in the audit manifests,
`proofs.json`, logs and `layout-issues.json`. A build's exit 1 for layout issues
must not be confused with an exception or a missing final PDF.

Pocket's 15 hard findings comprise 13 label/DSO and two label/label findings:
P11 3, P23 6, P28 3, P34 1, PD03 1, PD04 1. P15 has a reported mandatory-label
fallback warning. Visually inspected full-page previews and P11/P23 PDF crops
confirm genuine crowding near M84/M86 and M42/M43. Some star labels within
Cr70/M42 and a cluster label within the Rosette need semantic triage rather
than automatic deletion. P34's edge pair is also crowded. These findings are
not all proven false positives or all proven equally harmful. No algorithm or
threshold was changed in this audit.

## Data rights and distribution

Keep four layers distinct: **generator code** (MIT); **raw astronomical
sources** (source-specific); **derived datasets** (their applicable terms);
**PDF drawings and index** (mixed-source output). The index reuses structured
facts and cannot simply be declared irrelevant to database rights. Free or
non-commercial distribution does not itself satisfy attribution/share-alike
conditions. Existing project decisions accept the caveats below for the beta;
that is not an affirmative permission grant for raw-database redistribution.

| Used source / material | Evidence and terms | Attribution / audit status |
| --- | --- | --- |
| Tycho-2; Hipparcos | ESA/catalogue authors, CC BY-NC 3.0 IGO | ESA, Høg et al., ESA 1997 and teams credited; documented. Non-commercial restriction retained. |
| UCAC4 / APASS, Pocket PD02 | USNO/Zacharias et al.; valid APASS V plus documented calibrated fallback; no explicit comprehensive redistribution grant established | Credited; accepted with caveat. Expand APASS acknowledgement in release companion to include AAVSO and requested funders. Do not bundle the stellar database. |
| OpenNGC objects and imported outlines | Mattia Verga & contributors, CC BY-SA 4.0; normalization/corrections are adaptations | Credited and changes documented; retain share-alike for adapted material/database. Do not offer the whole PDF as unrestricted MIT or assume all PDF contents exempt. |
| Sharpless, Lynds LBN, van den Bergh, Barnard | VizieR VII/20, VII/21, VII/220A, VII/9; original scientific authors | Citations retained; source-specific terms, no blanket raw-table redistribution licence asserted. Accepted with caveat. |
| Lyngå / Collinder / Melotte / Stock | VII/92A | Citations retained; accepted source-rights caveat. |
| Harris/Palomar; Hickson; Arp; RC3 | VII/202, VII/213, VII/74A, VII/155, including crossmatched enrichment | Original authors credited; accepted source-rights caveat. Attribution contribution is not a claim that every source independently selects targets. |
| UCC 260615 | Versioned Zenodo/README, Perren et al. 2023; data licence unspecified | Credited; accepted with caveat. Software GPL is not a catalogue licence. No redistribution grant inferred. |
| WDS | USNO/Mason et al.; requested acknowledgement | PDF acknowledgement retained; accepted reuse-terms caveat; metadata contradiction corrected in the follow-up. |
| Gaia/CDS density and G flux, LMC/SMC | ODbL 1.0; ESA/Gaia/DPAC, CDS/CNRS, hips2fits; product version 1.4, 2022-06-15 / 2022-06-16 | Both sources and transformations recorded. Derived GeoJSON already separately ODbL. Release must provide notice and data access. |
| Milky Way d3-celestial GeoJSON | Olaf Frohn, BSD-3-Clause; original José R. Vieira catalogue | Both credited and BSD notice retained. Original Vieira grant not separately verified; accepted caveat, no source replacement required. |
| Stellarium Western (Sky & Telescope) figures | Krizak, Piskor and Stellarium Team; pinned source, CC BY-SA 2.0 | Attribution and adaptation record retained; derived figure data retain their licence. |
| Boundaries and star names | Olaf Frohn/d3-celestial BSD-3-Clause; IAU spelling-check snapshot says CC Attribution, version unspecified | Notices retained; IAU snapshot caveat documented. |
| Observing-list membership | Herschel 400 Wikipedia-derived CC BY-SA 4.0; other lists supply designations | Source notices retained; do not treat every membership source as MIT. |
| Project-authored outlines/design; bundled fonts | Marked project artwork CC BY 4.0; Lato and Source Sans 3 SIL OFL 1.1 | Notices and font licences present; font embedding verified. |

Crossmatched sources overlap: Pocket has 1,110 OpenNGC-linked, 282 UCC-linked
and 553 RC3-linked targets, for example, **not** that many additional objects.
Lynds LDN VII/7A, Terzan and Abell are not selected in this Pocket dataset but
remain relevant to Standard/Deep. Data preparation/import is not selection.

Primary checks: [ESA catalogue page](https://www.cosmos.esa.int/web/hipparcos/catalogues)
(direct access restricted; official indexed notice),
[CC BY-NC 3.0 IGO](https://creativecommons.org/licenses/by-nc/3.0/igo/legalcode),
[OpenNGC upstream](https://github.com/mattiaverga/OpenNGC),
[OpenNGC licence](https://raw.githubusercontent.com/mattiaverga/OpenNGC/master/LICENSES/CC-BY-SA-4.0.txt),
[UCC versioned record](https://zenodo.org/records/20705026),
[UCC README](https://zenodo.org/records/20705026/files/README.txt?download=1),
[WDS](https://crf.usno.navy.mil/wds),
[UCAC4 product documentation](https://irsa.ipac.caltech.edu/data/USNO/UCAC4/ucac4.html),
[AAVSO data-use guidance](https://aavso.org/data-usage-guidelines-2026-07/),
[Gaia density product](https://alasky.cds.unistra.fr/MocServer/query?ID=CDS%2FP%2FDM%2FI%2F355%2Fgaiadr3&fmt=html&get=record),
[Gaia flux product](https://alasky.cds.unistra.fr/MocServer/query?ID=CDS%2FP%2FDM%2Fflux-G%2FI%2F355%2Fgaiadr3&fmt=html&get=record),
[ODbL §§4.3–4.6](https://opendatacommons.org/licenses/odbl/1-0/),
[pinned d3 BSD notice](https://raw.githubusercontent.com/ofrohn/d3-celestial/7e720a3de062059d4c5400a379146a601d9010e0/LICENSE),
[pinned Stellarium attribution](https://raw.githubusercontent.com/Stellarium/stellarium-skycultures/014fbb5e59233d133c22f9811af96b67d05a95c9/western_SnT/description.md),
[OFL](https://openfontlicense.org/open-font-license-official-text/).
Existing `docs/DATA_SOURCES.md`, `THIRD_PARTY_LICENSES.md` and adjacent source
records remain authoritative for source mappings and previously accepted
caveats. WDS's linked acknowledgement subpage timed out; the VizieR general
licence page was inaccessible. This was no new exhaustive permissions study
of every historical publication. No newly established source prohibition was
found; missing explicit terms are not proof of either permission or conflict.

This audit recommends the release actions above; it does not change existing
source licences or replace the project's accepted non-commercial-beta policy.

## Public repository hygiene and artifacts

A scan of 481 tracked files found no high-confidence credential patterns,
private keys, tracked `.env`, bytecode, Zone.Identifier or files at least 1 MiB.
No tracked personal absolute `/home/fred/` or Windows user paths were found.
This was not a full Git-history/entropy security audit. Existing unrelated
untracked CSVs, `opencode.json` and the Windows metadata file were preserved.
Publish a reviewed Git export, not a zip of a worktree containing ignored raw
catalogues, builds or local credentials.

Artifacts are local/ignored, relative to the repository root:

- `build/alpha-audit/full-pocket/pocket/atlas.pdf`
- `build/alpha-audit/proof-standard/standard/atlas.pdf`
- `build/alpha-audit/proof-deep/deep/atlas.pdf`
- `build/alpha-audit/clean-fixture-optimized/standard/charts/test-virgo/`
- `build/alpha-audit/p11-virgo-crop.png`, `p23-orion-crop.png`
- `build/alpha-audit/layout-issues.json`, `selection.json`, `static.json`, logs.

Initial audit files: `AGENTS.md`, `README.md`, `.github/workflows/ci.yml`, the two
integration test modules above, `docs/STATE.md` and this report. The requested
follow-up also changes WDS metadata generation, its CLI regression test,
outline-import regression coverage, the Milky Way source record and adds the
distribution companion/tool/tests. No commit, push, PR or source swap was
performed. Licensing statements now follow the explicit follow-up request.
