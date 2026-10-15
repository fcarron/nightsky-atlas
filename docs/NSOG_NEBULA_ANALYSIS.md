# Local NSOG nebula analysis

This records the completed comparison of local AstroPlanner NSOG plans with
the normalized catalogue and edition-selection diagnostics. The one-time
research generator was retired in the CLI cleanup; these results and curation
conclusions remain historical evidence. NSOG membership is not a production
selection rule. See `CLI_CLEANUP_AUDIT.md`.

## Local inputs and outputs

Keep NSOG/AstroPlanner plan files outside tracked data, such as in
`local/research/nsog/` (that path is gitignored). The command does not download
NSOG data. It reads object designation, coarse type, constellation from the
filename, and the numeric rating only when the plan declares an `NSOG Rating`
column. Descriptions, notes, ratings from unrelated numeric columns, and other
plan text are not written to the report.

The generated local artifacts were `build/research/nsog_nebula_analysis.md`,
`build/research/nsog_nebula_analysis.json` and
`build/research/nsog_nebula_targets.csv`.

The Markdown report includes aggregate results and review queues. JSON and CSV
include per-target designations, rating aggregates, source identities and
selection diagnostics; keep them local because they encode derived NSOG list
membership. The report also summarizes the entire imported Barnard, LDN, LBN,
Sharpless and vdB populations for comparison.

## Method

- Rows are deduplicated by matched physical-object ID. Unmatched designations
  remain separate by normalized external designation.
- When duplicate NSOG rows disagree on rating, the highest numeric rating is
  used for mutually exclusive aggregate bins. All observed values and a
  conflict flag remain in the private per-target report.
- A row's last numeric field is treated as a rating only if the plan declares
  an `NSOG Rating` column. This avoids interpreting unrelated trailing numbers
  as ratings in unscored plans.
- Nebula category follows the normalized DSO type where it exists. If the
  normalized object is `other` but NSOG supplies a nebula type hint, it is
  reported as mixed/ambiguous rather than silently promoted to a nebula class.
- Catalogue contribution counts use distinct physical targets and can overlap
  across source families. Exclusive identity classes are provided separately.
- Edition decisions use the existing production selection explanation, including
  for the classical dark-nebula sanity check.
- “Project-authored schematic outline” means an existing NightSkyAtlas fixture
  path, not a survey-measured contour. Catalogue dimensions and LDN area-derived
  equivalent diameters are not asserted to be true morphology.
- An unmatched coordinate-bearing row is only a possible database gap; an
  unresolved designation without coordinates does not prove the object is
  absent. Selection gaps and weak-shape concerns are reported separately.
- Local Astronomical League dark/bright nebula fixtures are not present, so the
  optional cross-check is omitted.

This analysis describes one external observing guide's chosen sample. It does
not establish visual detectability, prove that a catalogue threshold is
appropriate, or authorize redistributing NSOG content. Review candidate policy
changes independently, with southern-sky coverage and cartographic shape
quality in view.
