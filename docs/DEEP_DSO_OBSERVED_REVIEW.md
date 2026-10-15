# DeepskyLog-observed targets in Deep

The user-provided `dso_not_in_deep.csv` was matched against the normalized
catalogue snapshot at `data/processed/dso/catalogue.json`. Matching uses the
primary designation first, then normalized catalogue IDs and retained aliases
including the input's `database_names`. Letter-suffixed NGC/IC components were
not mapped to an unsuffixed host when no exact component record exists. No
positional-only matches or catalogue imports were made.

The input contains **2,413 rows**. Three rows already mapped to objects selected
in Deep. Of the remaining rows, 1,424 matched supported DSO records; these
resolve to **1,421 unique new catalogue IDs** because three IDs occur more than
once in the input. Those stable IDs are curated in
`data/fixtures/observing_lists/deepskylog_deep_observed_v1.json` and forced only
in Deep (and its inherited Eyepiece policy). To preserve the existing dark-nebula
curation gate, the 135 accepted dark nebula IDs are also listed in Deep's
`dark_nebula.curated_designations`; no global selection rule changed.

## Matching results

| Result | Input rows | Interpretation |
| --- | ---: | --- |
| Already selected in Deep | 3 | Unique existing catalogue objects; unchanged |
| Added to Deep | 1,424 | 1,421 unique IDs, selected once each |
| Not found | 914 | No exact ID or retained alias in the current normalized catalogue |
| Ambiguous | 52 | 41 component designations without exact records; 11 catalogue-type or identity conflicts |
| Excluded | 20 | 12 stars, 6 double stars, 2 UCC clusters marked `bad_oc=y` |

The complete row-by-row audit, including source observer/observation counts,
status and reason, is `docs/DEEP_DSO_OBSERVED_CANDIDATES.csv`. “Not found” does
not assert that an object is nonexistent; it means the current local catalogue
does not provide a safe identity match. The ambiguous rows are not selected.

## Edition counts

| Edition | Before | After | Change |
| --- | ---: | ---: | ---: |
| Pocket | 1,133 | 1,133 | 0 |
| Standard | 3,093 | 3,093 | 0 |
| Deep | 10,483 | 11,904 | +1,421 |
| Reference analysis preset | 14,866 | 15,561 | +695 |

Counts come from `nightsky data selection-report` against the same local
catalogue and edition configuration. Deep's existing hierarchy means these
objects are also available in the experimental Eyepiece policy; Pocket and
Standard remain unchanged. The non-release Reference analysis preset also
inherits part of Deep's change through its existing hierarchy.

## Selection by normalized type

| Type | Added IDs |
| --- | ---: |
| Galaxies | 973 |
| Open clusters | 260 |
| Dark nebulae | 135 |
| Globular clusters | 39 |
| Bright nebulae | 12 |
| Planetary nebulae | 1 |
| Galaxy group/cluster | 1 |
| **Total** | **1,421** |

The CSV's classification is treated as a matching hint. The normalized
catalogue's DSO type controls symbol type; incompatible classifications are
held as ambiguous. UCC `r_50` is not used as visual extent or diameter.

## Validation artifacts

Two crowded pages were rendered both before and after with the same current
Deep tiling and chart settings. The baseline build used the committed policy
without the new list. The per-chart counters were:

| Main chart | New objects projected into field | DSOs before → after | Labels before → after | Hard issues before → after |
| --- | ---: | ---: | ---: | ---: |
| deep-128 (Coma core area) | 32 | 137 → 169 | 120 → 135 | 5 → 101 |
| deep-157 (Coma / Leo) | 31 | 155 → 185 | 169 → 199 | 5 → 27 |

The visual proof confirms additional crowding, especially around the Coma core
on deep-128. This is a real readability cost of retaining the new selected
labels and should be reviewed before treating the expanded Deep PDF as
publication-ready. No optimizer thresholds or label rules were changed. The
two after pages are successful rendered previews; a full Deep atlas build was
not run.

Before/after previews and chart PDFs:

- `build/deep-observed-expansion-baseline/deep/charts/deep-128/`
- `build/deep-observed-expansion-review/deep/charts/deep-128/`
- `build/deep-observed-expansion-baseline-157/deep/charts/deep-157/`
- `build/deep-observed-expansion-review/deep/charts/deep-157/`

The full selection report is reproducible with:

```bash
nightsky data selection-report --json /tmp/deep-selection.json --csv /tmp/deep-selection.csv
```

The original source CSV is user-provided workspace input and is not tracked in
Git; the CSV audit retains the requested object-level outcomes.
