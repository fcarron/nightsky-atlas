# Standard edition cartography

Frozen at M14.1 (2026-09-16); tiling revised for Standard v0.1 (full-sky draft).

## Page and field

| Parameter | Value |
| --- | --- |
| Page | A4 landscape, 297 x 210 mm |
| Margin | 12 mm (printable 273 x 186 mm) |
| Field of view | 27 x 18.5 degrees |
| Scale | ~10.05 mm per degree |
| Projection | stereographic, north up / east left |
| Stellar limit | magnitude 9.0 |
| DSO limit | magnitude 12.0 (objects with no magnitude are kept) |
| Charts (tiled) | 120 |

This sits between Sky Atlas 2000.0 (26 charts, ~10 mm/deg, mag 8.5) and
Uranometria 2000.0 (~220 charts, mag ~9.75) in chart count: Tirion-like scale
and readability, but a deeper limit and many more pages.

## Tiling (Standard v0.1)

Explicit declination rings with staggered right ascension and stereographic
polar caps:

- ring centres every 16 deg: -72, -56, -40, -24, -8, +8, +24, +40, +56, +72;
- one stereographic chart centred on each pole;
- alternate rings offset by half a chart spacing (less four-corner clustering);
- nominal vertical overlap 2 deg (`height - step = 2.5 deg` in practice).

The `chart_counts` in `atlas/standard.yaml` are start values.  Because the
field is a tangent-plane rectangle, its declination extent shrinks away from the
central meridian, so the tiler does **not** trust a `cos(dec)` estimate: it
samples each ring's declination slice, finds the narrowest right-ascension half
width and raises that ring's count until it covers the slice at every RA.  The
start values `5/8/11/13/14` resolve to `10/10/12/13/14` per hemisphere (120
charts including the caps); the outermost rings need to be denser than a naive
`cos(dec)` rule suggests to close the seams between rings and the polar caps.

- Coverage validated numerically (`nightsky atlas coverage --step 0.5`): 0 gaps,
  overlap 1..4, 259,200 samples.
- Every declared N/S/E/W neighbour pair shares covered sky
  (`neighbour_overlap_report`).
- Charts are numbered `standard-NNN` (deterministic cap/ring-then-RA order).
- The two polar caps have no east/west neighbour; the remaining rings are
  complete circles.

## Build

```bash
nightsky atlas tile                        # 120 chart definitions + neighbours
nightsky atlas coverage --step 0.5         # gaps=0, overlap 1..4
nightsky atlas build --png-dpi 100         # per-page PDF/PNG + atlas.pdf + manifest
nightsky atlas report                      # draft stats + region review list
```

`build/<atlas>/manifest.json` records page geometry, limits, tiling (including
resolved ring counts), per-page layout hashes, neighbours and diagnostics,
data-source manifests, and the git commit.  `build/<atlas>/draft-report.json`
holds coverage, density outliers, neighbour-reference problems and the region
review list.

## Open items

- Residual hard violations on dense pages (Milky Way / Virgo-Coma fields); the
  reference MVP charts validate cleanly.
- Polar charts are stereographic like every other chart; local distortion at the
  pole is larger and the meridian fan is dense.  The polar grid uses the coarser
  `grid.polar_ra_step_deg`; a minimum-spacing rule for edge labels near the pole
  is still a possible follow-up.
- The 120-chart count is geometry-driven.  A later optional pass may nudge
  individual chart centres by +-1-2 deg to move important regions away from page
  edges, but the draft deliberately uses a clean geometric grid only.

