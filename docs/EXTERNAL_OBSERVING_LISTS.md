# External observing-list coverage audits

The `nightsky research observing-list-coverage` command compares a locally
supplied observing list with the normalized DSO catalogue and the current
Pocket, Standard, Deep and Reference selectors. It is a research audit only:
external-list membership is evidence for review and never becomes an atlas
selection rule automatically.

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

## Run an audit

```bash
nightsky research observing-list-coverage \
  --source astroplanner \
  --input local/research/nsog/ \
  --list-name "NSOG local AstroPlanner export" \
  --json build/nsog-coverage.json \
  --csv build/nsog-coverage.csv
```

For the normalized CSV format used by an AL list:

```bash
nightsky research observing-list-coverage \
  --source astronomical-league \
  --input /path/to/local-list.csv \
  --list-name "Planetary Nebulae Program" \
  --json build/al-pn-coverage.json
```

To compare reports by stable NightSkyAtlas physical-object ID:

```bash
nightsky research observing-list-compare \
  build/nsog-coverage.json build/al-pn-coverage.json \
  --minimum-lists 2 --json build/list-consensus.json
```

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

## Add a source adapter

Implement a parser in `research/observing_lists/sources/` that yields
`ExternalObservingListEntry` values. Keep only fields needed for identity,
matching and local diagnostics. Register the parser in
`research/observing_lists/coverage.py`; matching, production selector lookup,
deduplication and reporting remain source-neutral. Use synthetic fixtures only.

## Local research status

No local NSOG/AstroPlanner source file was present at implementation time. The
tool can be run against a user-provided export with the command above; it does
not download third-party lists.
