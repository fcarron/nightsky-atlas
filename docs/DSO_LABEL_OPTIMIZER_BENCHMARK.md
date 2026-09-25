# DSO label optimizer review set

Use these production Standard charts to review DSO placement without changing
catalogue selection:

- `standard-053` — Virgo Cluster stress field (primary benchmark)
- `standard-084` — medium-density control field
- `standard-001` — sparse control field

Regenerate a chart with the production Tycho-2 store, deterministic optimizer,
PDF/preview and serialized placement diagnostics:

```sh
.venv/bin/python -m nightsky_atlas chart render \
  --edition standard --chart standard-053 \
  --star-store data/processed/stars/tycho2.sqlite \
  --optimize --write-layout --outdir build/dso-label-benchmark
```

Replace the chart ID for either control field. The serialized `chart.json`
contains per-label DSO association diagnostics and chart-level placement
metrics. Add `--placement-diagnostics` to include the best rejected candidate
alternatives and their rejection reasons. The benchmark reports candidate
conflicts and unresolved geometric issues; it does not hide or cull selected
objects or labels.

## Second-pass review

Production Standard renders reviewed on 2026-09-25 (all 226 labels remain
present on S053):

| Chart | Labels | Hard label–DSO | Hard label–label | DSO leaders | Runtime |
| --- | ---: | ---: | ---: | ---: | ---: |
| S053 Virgo | 226 | 17 | 10 | 19 | 182 s |
| S084 control | 48 | 0 | 0 | 1 | 10.8 s |
| S001 control | 22 | 0 | 0 | 0 | 4.9 s |

S053 source-edge gap: median 0.35 mm, p90 1.50 mm, p95 1.50 mm, maximum
6.00 mm. Nearest-DSO-not-owner fell from 44 to 36; 23 of these remain
unconnected. There are 89 unresolved ownership ambiguities (108 raw geometric
ambiguities, including placements whose validated leader explicitly identifies
the owner). The leader lengths have median 0.90 mm and p90 1.38 mm.

The 198-label Virgo conflict component uses deterministic fallback; the
45-neighborhood repair limit was reached, with no per-search node-budget hits.
Most remaining direct candidates are blocked by other label boxes, so the
existing 16-direction sampling is not the dominant limitation. S053 still has
27 hard conflicts, one more than the previous 26 (17 label–DSO and 10
label–label, versus 13+13). Treat this as an unresolved density/placement
problem, not a successful hard-conflict reduction. The full chart remains
visibly congested in the Virgo core; no labels or objects were removed.
