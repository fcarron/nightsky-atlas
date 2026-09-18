# Standard edition cartography

Frozen at M14.1 (2026-09-16); tiling revised for Standard v0.1 (full-sky draft)
and again for v0.2 (north-to-south order, calmer coordinate labels).

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
| Charts (tiled) | 116 |

This sits between Sky Atlas 2000.0 (26 charts, ~10 mm/deg, mag 8.5) and
Uranometria 2000.0 (~220 charts, mag ~9.75) in chart count: Tirion-like scale
and readability, but a deeper limit and many more pages.

## Tiling (Standard v0.2)

Explicit declination rings with staggered right ascension and stereographic
polar caps:

- ring centres every 16 deg: -72, -56, -40, -24, -8, +8, +24, +40, +56, +72;
- one stereographic chart centred on each pole;
- alternate rings offset by half a chart spacing (less four-corner clustering);
- nominal vertical overlap 2 deg (`height - step = 2.5 deg` in practice).

Charts are numbered **north to south, the reading order of the atlas**:

- `standard-001` = north polar cap;
- then the `+72, +56, ..., -72` rings in that order, each ring running in
  increasing right ascension (0h -> 24h) so the RA-wrap neighbour is always
  between the last and first chart of a ring;
- `standard-116` = south polar cap.

### Resolved ring counts

The requested start counts (`14/13/11/8/5` per hemisphere) do **not** cover the
sky.  The chart field is a rectangle in the tangent plane, so its declination
extent shrinks away from the central meridian; a `cos(dec)` estimate is far too
optimistic near the poles, where the outermost ring must interlock with the
polar cap.  A coverage sweep fixed the minimum counts that leave no gap at
0.25 deg sampling:

| Ring | Count | RA step |
| --- | --- | --- |
| +72 | 10 | 36.00 deg |
| +56 | 9 | 40.00 deg |
| +40 | 12 | 30.00 deg |
| +24 | 13 | 27.69 deg |
| +8 | 14 | 25.71 deg |
| -8 | 14 | 25.71 deg |
| -24 | 13 | 27.69 deg |
| -40 | 12 | 30.00 deg |
| -56 | 9 | 40.00 deg |
| -72 | 8 | 45.00 deg |
| +90 | 1 | - |
| -90 | 1 | - |

Total **116 charts**.  The `+72`/`-72` counts differ (10 vs 8) because the
stagger phase alternates around the ring stack, so the two poles meet their cap
with opposite phase.  `auto_adjust_counts` is off: the conservative per-ring
resolver would demand 10 charts in both outermost rings (120 charts), while the
assembled tiling covers with 10/8.

- Coverage validated numerically (`nightsky atlas coverage --step 0.5`): 0 gaps,
  overlap 1..4, 259,200 samples.
- Every declared N/S/E/W neighbour pair shares covered sky
  (`neighbour_overlap_report`): 458 pairs, 0 missing.
- The two polar caps have no east/west neighbour; the remaining rings are
  complete circles.

## Build

```bash
nightsky atlas tile                        # 116 chart definitions + neighbours
nightsky atlas coverage --step 0.5         # gaps=0, overlap 1..4
nightsky atlas build --png-dpi 100         # per-page PDF/PNG + atlas.pdf + manifest
nightsky atlas report                      # draft stats + region review list
```

`build/<atlas>/manifest.json` records page geometry, limits, tiling (including
resolved ring counts), per-page layout hashes, neighbours and diagnostics,
data-source manifests, and the git commit.  `build/<atlas>/draft-report.json`
holds the north-to-south chart order, per-ring RA step, coverage, density
outliers, neighbour-reference problems and the region review list.

## Coordinate labels (v0.2)

Grid **lines** stay fine (`ra_step_deg`/`dec_step_deg` 2 deg).  Coordinate
**labels** are a separate, sparser layer:

- a label every second grid line by default (`label_ra_step_deg` /
  `label_dec_step_deg` 4 deg), so grid-line density and label density are
  deliberately decoupled;
- `label_min_spacing_mm` (13 mm) additionally drops any label that would print
  closer than that to a neighbour on the same page edge, which is what tames
  the converging meridian fan on charts near the poles;
- polar charts use `label_polar_ra_step_deg` (30 deg), so the cap's RA fan is
  labelled only every two hours.

Across the 116 charts this removes about half the coordinate text versus the
every-line v0.1 draft while keeping the grid itself unchanged.

## Visible notation and page furniture

Internal ids stay long (`standard-068`) but the printed atlas uses a short,
consistent notation built centrally in `chart/presentation.py`:

| Edition | Name | Code | Visible chart code |
| --- | --- | --- | --- |
| Pocket | Pocket | P | P001 |
| Standard | Standard | S | S001 … S116 |
| Deep | Deep | D | D001 |

The edition name and code come from the atlas `edition:` block and fall back to
this registry when omitted.  The footer title is
`NightSky Atlas — Standard · S068`; navigation references neighbouring charts as
`N: S082`, never with the internal id.

Furniture sits outside the chart frame and is deliberately quiet
(`styles/standard.yaml` → `furniture:`):

- **Navigation** is smaller than the coordinate labels, mid-grey, and placed
  further out than the RA/Dec labels (east left, west right, per the printed
  orientation).  Coordinate labels treat navigation rectangles as obstacles.
- **Scale bar** is a thin (~0.13 mm) mid-grey line with end ticks and a compact
  `5°` label; the angular value is chosen per edition so the printed bar stays
  roughly 40–50 mm long (Pocket 10°, Standard 5°, Deep 2°).
- **Magnitude legend** is a compact `mag 2 4 6 8` reference whose dots use the
  real `StarSizeModel`, so the printed sizes match the chart exactly.
- **Title** is right-aligned in the footer.  The footer row is magnitude legend
  (left), scale bar (centre), title (right); nothing is stacked in the middle of
  the chart.

## Overview maps and locator

The atlas opens with two whole-sky **overview pages** (after the front matter):
a northern and a southern hemisphere disk, each a pole-centred azimuthal
equidistant projection of radius 90 degrees.  They show a simplified
constellation background (stick figures and dotted boundaries drawn as straight
chords), a light RA/Dec grid, the full name of each constellation, the bright
stars down to the ``overview.star_limit_magnitude`` and one clean **cell** per
Standard chart with its printed chart code (``S001`` …).

Charts overlap by design (star-hop overlap), so drawing every chart field
rectangle produced a tangle of near-parallel lines.  Each chart is therefore
represented by the declination-ring / right-ascension sector around its centre:
declination boundaries lie midway between adjacent ring centres (and at the pole
and equator) and RA boundaries midway between adjacent chart centres within a
ring.  Every chart contributes exactly one **trapezoidal** cell, adjacent cells
share a single boundary, and there is no overlap; cell sides are straight
meridians and tops/bottoms follow declination circles.  This is an index
schematic, not a reproduction of the chart fields.  The bright stars use the
same monotonic magnitude-to-size model as the charts, limited to a small,
deliberately quiet foreground.  RA hour labels ring the equator.  Appearance
lives under ``overview:`` in the style; the pages are controlled by
``atlas build --no-overviews``.

An optional **locator inset** (``locator.enabled`` in the style, default off)
draws a compact version of the hemisphere overview inside a chart corner,
with the current cell in black and its immediate neighbours mid-grey (stars are
omitted at that size).  The inset rectangle is registered as a label obstacle
so no chart label is placed under it.

## Open items

- Residual hard violations on dense pages (Milky Way / Virgo-Coma fields,
  Large Magellanic Cloud); the reference MVP charts validate cleanly.  DSO and
  star label prioritisation in dense fields is the next work package.
- Polar charts are stereographic like every other chart; local distortion at the
  pole is larger and the meridian fan is dense.  The polar grid uses the coarser
  `grid.polar_ra_step_deg` and labels it at `label_polar_ra_step_deg`; the
  minimum-spacing rule handles the near-pole (non-cap) rings.
- The 116-chart count is geometry-driven.  A later optional pass may nudge
  individual chart centres by +-1-2 deg to move important regions away from page
  edges, but the draft deliberately uses a clean geometric grid only.

