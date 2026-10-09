# Standard edition cartography

Frozen at M14.1 (2026-09-16); tiling revised for Standard v0.1 (full-sky draft),
again for v0.2 (north-to-south order, calmer coordinate labels), and again for
v0.3 (mirror-symmetric ring counts for regular navigation).

## Page and field

| Parameter | Value |
| --- | --- |
| Page | A4 landscape, 297 x 210 mm |
| Margin | 12 mm (printable 273 x 186 mm) |
| Field of view | 27 x 18.5 degrees |
| Scale | 10 mm per degree |
| Projection | stereographic, north up / east left |
| Stellar limit | magnitude 9.0 |
| DSO selection | per-type visibility, catalogue/curation rules and edition inheritance |
| Charts (tiled) | 118 |

This sits between Sky Atlas 2000.0 (26 charts, ~10 mm/deg, mag 8.5) and
Uranometria 2000.0 (~220 charts, mag ~9.75) in chart count: Tirion-like scale
and readability, but a deeper limit and many more pages.

## Tiling (Standard v0.3)

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
- `standard-118` = south polar cap.

### Resolved ring counts

The requested start counts (`14/13/11/8/5` per hemisphere) do **not** cover the
sky.  The chart field is a rectangle in the tangent plane, so its declination
extent shrinks away from the central meridian; a `cos(dec)` estimate is far too
optimistic near the poles, where the outermost ring must interlock with the
polar cap.  A coverage sweep fixed the minimum counts that leave no gap at
0.25 deg sampling.  The counts are **mirror-symmetric** north/south: every
`+dec` ring has the same number of charts as its `-dec` counterpart, so the two
hemispheres pair chart-for-chart and navigation is regular:

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
| -72 | 10 | 36.00 deg |
| +90 | 1 | - |
| -90 | 1 | - |

Total **118 charts**, 59 per hemisphere.  `auto_adjust_counts` is off: the
conservative per-ring resolver would demand 10 charts in the outer rings too
(120 charts), while the assembled tiling with the stagger covers at the counts
above, which are already the equal north/south minimum.

- Coverage validated numerically (`nightsky atlas coverage --step 0.5`): 0 gaps,
  overlap 1..4, 259,200 samples.
- Every declared N/S/E/W neighbour pair shares covered sky
  (`neighbour_overlap_report`): 629 pairs, 0 missing.
- The two polar caps link to surrounding charts along all four page edges;
  other single-chart rings have no same-ring east/west neighbour. The remaining
  multi-chart rings are complete circles.

## Build

```bash
nightsky atlas tile                        # 118 chart definitions + neighbours
nightsky atlas coverage --step 0.5         # gaps=0, overlap 1..4
nightsky atlas build --png-dpi 100         # per-page PDF/PNG + atlas.pdf + manifest
nightsky atlas report                      # draft stats + region review list
```

`build/<atlas>/manifest.json` records page geometry, limits, tiling (including
resolved ring counts), per-page layout hashes, neighbours and diagnostics,
data-source manifests, and the git commit.  `build/<atlas>/draft-report.json`
holds the north-to-south chart order, per-ring RA step, coverage, density
outliers, neighbour-reference problems and the region review list.

## Coordinate grid, edge labels and ticks

The chart grid uses edition-specific angular intervals. Right ascension is
given below in time; 1 h = 15°.

| Edition | RA grid | Dec grid | RA labels | Dec labels | Outer RA ticks | Outer Dec ticks | Polar RA grid/ticks |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Pocket | 1 h | 10° | 1 h | 10° | 15 min | 5° | 2 h |
| Standard | 30 min | 5° | 1 h | 10° | 10 min | 2.5° | 30 min |
| Deep | 15 min | 2° | 30 min | 4° | 5 min | 1° | 15 min |

At the equator, RA grid lines print about 75 mm apart in every edition; their
spacing changes with declination and the stereographic projection. Short ticks
project the coordinate subdivisions onto the outside of the rectangular chart
frame, like an axis on a graph. Ticks coinciding with a full grid line are
slightly longer (1.2 mm instead of 0.8 mm). Ticks closer than 4 mm along an
edge are thinned, with full-grid values retained first. On polar fields, ticks
follow the polar meridian interval rather than adding a dense set of minor RA
marks. Declination ticks use 5° in Pocket, 2.5° in Standard and 1° in Deep;
these intervals keep the side marks at a similar printed spacing to the RA
ticks above and below the frame.

Coordinate labels remain separate from lines and ticks. RA values sit above and
below the frame; declination values sit at its sides. Labels closer than 13 mm
along an edge are thinned, favouring round values, and labels are omitted where
they would overlap page furniture. Polar RA labels appear only every 2 h.

## Visible notation and page furniture

Internal ids stay long (`standard-068`) but the printed atlas uses a short,
consistent notation built centrally in `chart/presentation.py`:

| Edition | Name | Code | Visible chart code |
| --- | --- | --- | --- |
| Pocket | Pocket | P | P01 … P39 |
| Standard | Standard | S | S001 … S118 |
| Deep | Deep | D | D001 … D430 |

The edition name and code come from the atlas `edition:` block and fall back to
this registry when omitted. The footer title uses compact visible-constellation
context, for example `NightSky Atlas · Cyg · S068`; navigation references neighbouring charts as
`N: S082`, never with the internal id.

Furniture sits outside the chart frame and is deliberately quiet
(`styles/standard.yaml` → `furniture:`):

- **Navigation** is larger than the coordinate labels, mid-grey, and placed
  further out than the RA/Dec labels (east left, west right, per the printed
  orientation).  Coordinate labels treat navigation rectangles as obstacles.
- **Scale bar** is omitted from chart pages in all editions; the edge ticks
  and coordinate grid provide the chart reference.
- **Magnitude legend** is a compact `mag 2 4 6 8` reference whose dots use the
  real `StarSizeModel`, so the printed sizes match the chart exactly.
- **Footer** uses the same one-line atlas, constellation and chart identifier
  across editions. The magnitude legend remains at left where configured.

## Pocket and Standard detail charts and galaxy labels

Standard detail charts are framed on their parent page and tagged with their
printed detail code. A detail chart may opt into `fallback_parent_galaxy_labels`:
for that field, an ordinary galaxy number is omitted from the parent only when
the same stable DSO ID has a placed detail label and that label has no hard
layout violation. The galaxy symbol remains on both pages. Messier and Herschel
400 labels are never transferred. It is enabled for Standard Virgo core
(`SD053A`), southern Virgo (`SD053B`) and Fornax (`SD089`). Pocket now retains
just Virgo core (`PD021A`, parent `P21`), at
10 mm/° with stars to mag 9.0 and the parent's DSO selection; the other former
Pocket detail fields use ordinary labels on the main maps. Pocket uses the
compact detail code as its frame tag; the detail page carries the region name.

Deep has nine close-ups: NGC 7331 with Stephan's Quintet (`DD105`), the
Pleiades (`DD111`), the Coma core (`DD121`), the Markarian chain (`DD174`),
M42 (`DD223`), the Fornax core (`DD328`), 30 Doradus (`DD405A`), the LMC bar
(`DD405B`) and NGC 346 in the SMC (`DD415`). Their dedicated star profile plots
stars to magnitude 11.5, while Deep main charts plot stars to magnitude 10.5.
Deep's bold, normal and fine galaxy classes use a 0.75-arcmin minimum major
axis at 20 mm/degree. This is the same 0.25-mm angular threshold on paper as
Pocket's 3 arcmin at 5 mm/degree and Standard's 1.5 arcmin at 10 mm/degree.
Deep's dotted class retains its separate 0.5-arcmin and 400-mm visibility-score
requirements. The plotted galaxy ellipse still has its cartographic minimum
size; the selection threshold does not set the printed symbol diameter.
DD105 at 40 mm/degree uses a separate star-diameter curve, extending the
Standard-to-Deep size progression by one magnitude; its stellar limit remains
11.5. The other Deep detail charts retain their existing star sizes.
Galaxy-label fallback is enabled only for the four galaxy fields. In addition
to the stable-ID and hard-clean
detail-label requirements above, a Deep parent galaxy must be at least
magnitude 12.5 and have three other plotted galaxies within the style's
15-mm label-density radius. Brighter galaxies, Messier and H400 objects keep
their main-chart labels. Chart pages do not include scale bars; angular scale
is stated in the edition introduction and chart field information.

## Short leaders for broad DSO labels

`label.leader_lines.targeted_dso` adds a final deterministic presentation pass
after ordinary placement. Pocket, Standard and Deep inherit the enabled rule
from `styles/standard.yaml`; Eyepiece explicitly leaves it disabled pending
its own review. Missing configuration defaults to disabled.

The measured glyph envelope must be at least 8 mm wide and four times its
height. A competing-owner cost of at least 1, a nonzero association corridor
cost or an already weak ownership margin must also be present. These are
conservative v1 settings supported by a small observer review, not optimized
visibility thresholds. A long name alone does not add a line.

Only visible, unlocked DSO labels without an existing leader are considered,
in descending priority then stable-ID order. The existing candidate and all
text remain unchanged. Routes use the existing symbol/text gaps, minimum
length and collision checks, with an additional 3-mm maximum. A proposal must
preserve every existing route and introduce no new hard violation ID.
Existing hard violations are still reported; this pass does not repair them.

Added labels carry `leader_line_reason: targeted_long_label`. Optimizer metrics
include `targeted_dso_leaders` with stable-ID decisions and rejection counts;
normal label diagnostics are recomputed after accepted additions. The
source-association weight stays 20. See `docs/LEADER_LINE_EXPERIMENT.md` for the
research evidence and the atlas-wide audit.

## Overview maps and locator

The atlas opens with whole-sky **overview pages** (after the front matter):
a northern and a southern pole-centred azimuthal equidistant map. By default,
each extends 90 degrees from its pole. Pocket extends both maps 18 degrees past
the equator so the full height of its equatorial charts (for example P019) is
visible on both overview maps, using a slightly larger disk at the same map
scale. Pocket's atlas fields remain 54 x 36 degrees at 5.0 mm/degree; the
overview extension does not change field size, chart centres, chart count or
tiling. They show a simplified
constellation background (stick figures and dotted boundaries drawn as straight
chords), a light RA/Dec grid, the full name of each constellation, the bright
stars down to the ``overview.star_limit_magnitude`` and one clean **cell** per
Standard chart with its printed chart code (``S001`` …).

Charts overlap by design (star-hop overlap), so drawing every chart field
rectangle produced a tangle of near-parallel lines.  Each chart is therefore
represented by the declination-ring / right-ascension sector around its centre:
declination boundaries lie midway between adjacent ring centres (and at the pole
and equator, except for Pocket's equatorial extension) and RA boundaries midway
between adjacent chart centres within a ring. Every chart contributes exactly
one **trapezoidal** cell, adjacent cells
share a single boundary, and there is no overlap; cell sides are straight
meridians and tops/bottoms follow declination circles.  This is an index
schematic, not a reproduction of the chart fields.  The bright stars use the
same monotonic magnitude-to-size model as the charts, limited to a small,
deliberately quiet foreground.  RA hour labels ring the equator.  Appearance
lives under ``overview:`` in the style; the pages are controlled by
``atlas build --no-overviews``.

The complete chart directory is placed at the back of Pocket, Standard and
Deep, after the chart sequence and object index. The overview maps remain in
the front matter as the quick navigation aid.

An optional **locator inset** (``locator.enabled`` in the style, default off)
draws a compact version of the hemisphere overview inside a chart corner,
with the current cell in black and its immediate neighbours mid-grey (stars are
omitted at that size).  The inset rectangle is registered as a label obstacle
so no chart label is placed under it.

## Open items

- Residual hard violations on dense pages (Milky Way / Virgo-Coma fields,
  Large Magellanic Cloud); the reference MVP charts validate cleanly.  DSO and
  star label prioritisation/selection is implemented; residual dense-page
  conflicts still require review.
- Polar charts are stereographic like every other chart; local distortion at the
  pole is larger and the meridian fan can be dense, especially in Deep. Each
  edition uses `grid.polar_ra_step_deg` for its polar meridians and labels them
  at `label_polar_ra_step_deg`; the minimum-spacing rule handles crowded edges.
- The 118-chart count is geometry-driven.  A later optional pass may nudge
  individual chart centres by +-1-2 deg to move important regions away from page
  edges, but the draft deliberately uses a clean geometric grid only.
