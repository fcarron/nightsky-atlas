# External observing-list coverage audits

This is the historical methodology for the completed local NSOG/AL coverage
study. Its research commands and exclusive adapters were retired in the CLI
cleanup (see `CLI_CLEANUP_AUDIT.md`). The sections below describe that snapshot,
not a supported current command. Curated memberships and production catalogue
matching remain available; use `data selection-report` and `atlas why-object`
for current edition diagnostics.

## Keep source files local

The parser code and synthetic tests are public project material. Third-party
list content is separate. Do not commit NSOG membership, AstroPlanner NSOG
planfiles, ratings, descriptions, notes or extracted complete membership lists.
NSOG files belong outside tracked data, for example under
`local/research/nsog/` (gitignored). Files supplied for an audit are read in
place; they are not copied into the repository. Reports retain only row
locators, designations, optional coordinates/type/constellation/size, match
results and production selection reasons. Other input columns, including notes
and ratings, are discarded.

Astronomical League lists use the same local-input rule. A publicly downloadable
file is not automatically licensed for redistribution. Do not vendor a full
list unless redistribution permission for that exact list has been documented.

## Input formats

`--source astroplanner` accepts AstroPlanner APTF plan text files (versions 2
and 3, including the NSOG constellation DSO plans), object-list exports saved
as UTF-8 CSV or TSV, plus text files with one designation per line. The native
AstroPlanner database is not parsed. APTF parsing reads object designation, RA,
Dec and a coarse type hint; it discards notes, descriptions, ratings and other
columns.
`--source astronomical-league` accepts UTF-8 CSV/TSV or one-designation-per-line
text. The CSV/TSV header needs a designation, object, name, target or ID column.
Optional recognized columns include catalogue, RA, Dec, type, constellation
and size. RA/Dec can be decimal degrees or sexagesimal strings. Angular sizes
with arcsecond units are converted to arcminutes. The adapter does not scrape
websites.

Directories are searched recursively for `.csv`, `.tsv` and `.txt` files.
When several files are provided, they are treated as one audit/list. Set
`--list-name` to provide a useful aggregate name.

## Archived reports

The study wrote local coverage JSON/CSV and physical-object consensus reports.
Those saved artifacts describe their original catalogue and policy snapshot;
keep proprietary source inputs and per-entry reports local.

## Matching and report metrics

Matching proceeds in this order: canonical designation, known normalized alias
or catalogue cross-ID, catalogue-specific separator normalization, optional
coordinate search and unresolved/manual review. Arbitrary fuzzy text matching
is not used. Coordinate tolerance defaults to 2 arcminutes and is adjustable.
Object-type hints filter coordinate candidates. More than one candidate is
reported as ambiguous and is never silently selected. A local YAML override can
resolve a hard case:

```yaml
overrides:
  - source: AstroPlanner
    raw_designation: XYZ
    canonical_object: NGC1234
    reason: verified against the local source chart
```

Use `--overrides local/research/overrides/nsog.yaml` to apply it. The target
must be a canonical ID in the normalized catalogue. Overrides contain no list
membership snapshot and are gitignored by default.

- **Match coverage** is the percent of unique normalized external designations
  that resolve unambiguously to a catalogue object.
- **Database coverage** compares unique matched physical targets to an estimated
  unique external target count. Unmatched distinct designations count as
  separate possible targets, so aliases that resolve to one physical object do
  not inflate the denominator. Unresolved aliases can make this estimate high.
- **Edition coverage** is selected physical targets divided by unique matched
  physical targets. This denominator is explicit because unresolved external
  designations have no NightSkyAtlas identity yet.
- Exact, alias, catalogue-normalized, coordinate and manual-override matches
  are counted separately. The detail report includes every input row, while
  target and edition counts deduplicate by physical object ID.
- Unmatched entries distinguish parse failures, unknown designations,
  ambiguous candidates and entries with coordinates but no nearby database
  object. The latter are possible database omissions, not externally verified
  objects.
- Type and source-catalogue sections count unique matched physical targets.
  Nebula analysis reports which external nebula targets have non-LDN/LBN source
  representation and which are represented by LDN/LBN alone. External-list
  membership does not itself prove that an object is visually important.

The JSON schema is versioned (`schema_version: 1`). It does not preserve source
descriptions, ratings, observing notes or arbitrary metadata columns. Treat
reports as local research artifacts when they contain proprietary designations
or membership. The optional comparison command computes union, intersection,
per-object list membership and a thresholded consensus set.

## Local research status

The adapters and their synthetic tests have been removed after the study.
The original snapshot remains in Git at `3fe896a`; this does not grant rights
to redistribute local third-party list inputs or derived membership reports.
