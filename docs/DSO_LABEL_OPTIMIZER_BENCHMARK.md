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

## Second-pass review before text-ink geometry

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

## Text-ink clearance audit

The renderer and candidate builder already use Pango glyph-cluster ink extents;
the issue was that DSO label-to-label collision checks still used the full
logical line box. At Standard's 6.5 pt DejaVu Sans size, `4387`, `4438`, `4458`,
and `4478` measure 5.644 × 3.175 mm logically but their ink envelope is
5.644 × 2.117 mm. `M87` is 5.997 × 3.175 mm logically and 5.997 × 2.469 mm in
ink; `M100` is 7.761 × 3.175 mm logically and 7.761 × 2.469 mm in ink;
`I3476` is 6.350 × 3.175 mm logically and 6.350 × 2.117 mm in ink. The numeric
labels' glyph envelope begins 0.706 mm below the logical top. There was no
additional label-to-label padding in the old hard geometry.

The clearance experiment uses each DSO label's actual measured ink envelope
with the configured total edge gap (half added to each label). Page clipping
and page furniture still use the full logical box. Star labels retain their
logical collision box. Source association, source-facing edge distance and DSO
leader endpoints use the visible ink envelope. Missing ink metrics safely fall
back to the logical box.

All four S053 runs had the same 226 selected labels / 214 DSO labels and used
the same Standard content. The `logical` row is a fresh control with no added
ink clearance; because source-facing geometry is now measured to glyph ink, it
is not byte-for-byte the pre-audit implementation quoted above. Candidate
rectangle conflicts count distinct overlapping candidate pairs between
different DSO labels; component-edge count is the number of connected
label-pairs in that graph.

| S053 geometry | Hard label–label | Hard label–DSO | Total hard | Leaders | Ownership ambiguity | Nearest DSO ≠ owner | Source gap median / p90 / p95 / max (mm) | Conflict components / largest | Candidate pairs / graph edges | Mean valid candidates | Runtime |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: |
| Logical-box control | 8 | 7 | 15 | 11 | 85 | 21 | 0.350 / 1.500 / 2.000 / 6.001 | 12 / 198 | 1,661,944 / 2,084 | 37.51 | 157.1 s |
| Ink + 0.20 mm | 3 | 13 | 16 | 13 | 72 | 21 | 0.350 / 1.101 / 1.507 / 6.000 | 13 / 198 | 1,257,106 / 1,968 | 40.55 | 146.6 s |
| Ink + 0.15 mm | 4 | 13 | 17 | 12 | 73 | 21 | 0.350 / 1.101 / 1.507 / 6.000 | 13 / 198 | 1,220,396 / 1,957 | 40.87 | 119.4 s |
| Ink + 0.10 mm | 4 | 5 | 9 | 14 | 72 | 21 | 0.350 / 1.500 / 1.700 / 6.000 | 13 / 198 | 1,184,787 / 1,939 | 41.06 | 114.1 s |

No run hid labels, hit the joint-search node budget, or changed source
selection. The 0.10 mm run has the lowest raw hard-conflict count, but at 300
dpi its tightest text pairs are not robustly separated at print scale; it also
has a worse p90/p95 distance tail. The 0.15 mm run does not improve the 0.20 mm
conflict/ownership results. Adopt **0.20 mm** as the conservative cartographic
clearance: it cuts logical-box candidate-pair conflicts by about 24%, reduces
label–label hard issues from 8 to 3, improves p90/p95 source distance, and
keeps approximately 2.4 pixels between ink envelopes at 300 dpi. It does not
break the 198-label Virgo component, and total hard conflicts are 1 above the
fresh logical-box control because the changed assignments expose more
label–symbol conflicts. This is not a claim that the Virgo core is solved.

Foreign DSO symbols have no generic hard exclusion halo: actual overlap is the
hard failure, while the existing foreign-object cost falls quadratically to
zero over 0.8 mm. Source ellipse/contour distances carry no extra ellipse
padding. The 0.8 mm term is a soft score, not reserved whitespace. The current
source model measures symbol paths from their geometry centerline and does not
inflate by half the rendered stroke width (at most 0.15 mm); this slight
under-clearance is small and was left unchanged to keep this task limited to
label text geometry. Foreign-star weighting is unchanged. Only resolved
constellation stick figures contribute a soft line-overlap cost (0.4 mm margin);
grid, ecliptic and IAU boundaries do not reject candidates. Stick-line knockout
remains available.

The S053 PDF and 300 dpi preview variants are under
`build/dso-ink-clearance/standard/charts/standard-053/{logical,ink_020,ink_015,ink_010}/`.
The selected 0.20 mm control renders are under the corresponding S084 and S001
directories. At print scale, the M84/M86 core remains intrinsically crowded;
labels are measurably more tightly packed without changing typography. The
selected configuration preserves the sparse and medium controls:

| Chart | Labels | Hard conflicts | Leaders | Runtime |
| --- | ---: | ---: | ---: | ---: |
| S084 medium | 48 | 0 | 1 | 6.6 s |
| S001 sparse | 22 | 0 | 0 | 5.5 s |

Conclusion: the logical line box reserved about 1.06 mm of unused vertical
space for ordinary numeric DSO labels, so text geometry was a real but limited
contributor. The large Virgo component remains connected and the glyph widths
are nearly the same as logical advances. The dominant remaining limitation is
genuine local object/label density, with some unavoidable label-to-galaxy
overlaps in the M84/M86 region; this refinement alone cannot eliminate it.
