# Performance notes

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
