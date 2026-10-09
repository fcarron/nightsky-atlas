# Standard edition cartography

Standard uses the symmetric, aligned 11-ring tiling described below. The
geometry was first evaluated on the `experiment/standard-11-rings-aligned`
branch and then adopted with a 12-degree RA phase.

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
| Charts (tiled) | 129 (baseline: 118) |

This sits between Sky Atlas 2000.0 (26 charts, ~10 mm/deg, mag 8.5) and
Uranometria 2000.0 (~220 charts, mag ~9.75) in chart count: Tirion-like scale
and readability, but a deeper limit and many more pages.

## Tiling (11 aligned rings)

This branch tests eleven evenly spaced declination rings, no RA staggering,
and one stereographic chart centred on each pole. Ring centres are
`-75, -60, -45, -30, -15, 0, +15, +30, +45, +60, +75` degrees. Counts are
mirror-symmetric, with a shared 12-degree RA phase:

| Ring pair / ring | Charts per ring | RA step |
| --- | ---: | ---: |
| ±75° | 5 | 72.000° |
| ±60° | 10 | 36.000° |
| ±45° | 11 | 32.727° |
| ±30° | 15 | 24.000° |
| ±15° | 15 | 24.000° |
| 0° | 15 | 24.000° |
| Each pole | 1 | — |

This gives **129 main charts**: 57 non-equatorial charts in each hemisphere,
plus the 15 equatorial charts shared by both overview maps (72 cells per map).
The 11-chart rings at ±45° are the smallest
tested counts that close coverage; 10 leave gaps around RA 18°/198° near
Dec ±39.6°. Four charts at ±75° leave gaps near Dec ±69.9°. The 5/10/15 grids
remain nested; the 11-chart rings are the sole additional RA raster. Same-count
rings are exactly aligned north/south. The 12° phase puts RA 12h at the centre
of chart S065; RA 0h lies between equatorial chart centres.

At 0.25° global sampling, the selected geometry has no uncovered samples.
Area-weighted coverage multiplicity is 1.528; 56.57% of the sky is covered
once, 36.26% twice, 5.02% three times and 2.16% four times. Its sampled
minimum reserve—the largest signed distance in projected chart coordinates to
any chart edge at each sky point—is 0.61° (about 6.1 mm at this edition's
scale), near RA 192°, Dec ±38.1° with the selected 12° phase. A finer local
scan below corroborates this sampled result; neither raster is a mathematical
proof for every real-valued sky coordinate.

At ring-centre parallels, the smallest measured east-west overlap is 2.88°
(28.8 mm) at the equator. The smallest north-south overlap on central meridians
is 3.46° (34.6 mm); the polar-cap transition is also 3.46°. These are local
axis measurements, not the global reserve above.

Baseline comparison: the previous 118-chart arrangement has a sampled minimum
reserve of 0.11°, 67.85% singly covered sky, minimum ring-centre east-west
overlap 1.42°, central-meridian north-south overlap 2.46°, and only 0.46° at
the polar-cap transition. The 129-chart tiling is more navigable at the
tightest seams but uses 11 additional main charts. The 127-chart simple
5/10/15 proposal has gaps around Dec ±39.6° because 10 charts at ±45° are
insufficient. Moving the outer rings to ±74°, ±76° or ±77° does not improve the
balanced 75° choice: 74° reduces polar overlap to 2.46°, 76° increases
outer-ring overlap, and 77° reduces the ±60/±77 central-meridian overlap to
1.46°.

A fine scan of 3,586,082 points around all ring transitions, the pole
transitions and RA wrap found no gaps; the smallest sampled projected edge
reserve was 0.602° in the aligned 0°-phase scan. The selected 12° phase is a
global rotation of that tiling, so the geometric overlap measures are
unchanged. Both hemisphere overviews extend 9.25° past the equator, showing the
complete equatorial chart row on each map. The normal neighbour audit checked
598 directed references with no missing overlaps. A full 12°-phase build is at
`build/standard-11-rings-ra12/standard/atlas.pdf` (129 main charts plus 9
details). Its manifest reports 78 hard layout issues; the 0°-phase comparison
build reported 73. These are draft builds, not publication validations.

Chart IDs remain north-to-south: `standard-001` is the north polar cap, then
the +75° through 0° rings run in increasing RA; the southern rings follow and
`standard-129` is the south polar cap. Declared N/S/E/W neighbours are derived
from actual projected chart edges and must pass the neighbour-overlap test.

## Build

```bash
nightsky atlas tile                        # 129 chart definitions + neighbours
nightsky atlas coverage --step 0.25       # gaps=0, overlap 1..4
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
| Standard | Standard | S | S001 … S129 |
| Deep | Deep | D | D001 … D492 |

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

## Detail charts

Detail charts use only three physical map scales: 20, 40 or 80 mm/°. Their
fields are 13 × 8.5°, 6.5 × 4.25° and 3.25 × 2.125°, respectively. This leaves
space for a heading and a footer on A4 landscape while preserving true map
scale. The page identifies each chart with a stable edition-specific code
(`PD01`, `SD01`… or `DD01`…), its region, scale, field and primary parent chart.
The detail-chart directory and PDF links provide the same code and parent
reference. Codes do not derive from parent chart numbers.

The parent edition remains the source of DSO selection: Pocket details use
Pocket selection, Standard details use Standard selection, and Deep details use
Deep selection. A star profile can be denser without changing the DSO policy.
The selected star profile supplies star limits, symbol sizes and star-label
style; the base edition continues to supply DSO styling and selection. An
optional UCAC4 supplement may be enabled for detail charts without adding it to
the parent charts.

| Edition and detail | Code | Scale | Stars to | Primary parent |
| --- | --- | ---: | ---: | --- |
| Pocket — Virgo core | PD01 | 20 mm/° | 9.0 | P20 |
| Standard — Virgo Cluster | SD01 | 20 mm/° | 10.5 | S050 |
| Standard — Virgo core | SD02 | 80 mm/° | 13.5 | S050 |
| Standard — South Virgo | SD03 | 40 mm/° | 12.25 | S065 |
| Standard — Fornax core | SD04 | 40 mm/° | 12.25 | S090 |
| Standard — Sagittarius clusters | SD05 | 20 mm/° | 10.5 | S099 |
| Standard — Cygnus nebula field | SD06 | 20 mm/° | 10.5 | S026 |
| Standard — Orion Nebula | SD07 | 20 mm/° | 10.5 | S061 |
| Standard — Double Cluster | SD08 | 20 mm/° | 10.5 | S008 |
| Standard — Pleiades | SD09 | 20 mm/° | 10.5 | S030 |
| Deep — NGC 7331 / Stephan's Quintet | DD01 | 40 mm/° | 12.25 | D116 |
| Deep — Pleiades | DD02 | 40 mm/° | 12.25 | D147 |
| Deep — Coma core | DD03 | 80 mm/° | 13.5 | D131 |
| Deep — Markarian chain | DD04 | 80 mm/° | 13.5 | D188 |
| Deep — Orion Nebula | DD05 | 80 mm/° | 13.5 | D269 |
| Deep — Fornax core | DD06 | 40 mm/° | 12.25 | D381 |
| Deep — 30 Doradus | DD07 | 80 mm/° | 13.5 | D466 |
| Deep — LMC bar | DD08 | 80 mm/° | 13.5 | D465 |
| Deep — NGC 346 / SMC | DD09 | 40 mm/° | 12.25 | D477 |

Star profiles are existing edition presets: Standard detail stars use the
Standard profile, Deep detail stars use Deep, and the denser detail fields use
Eyepiece or Eyepiece Deep profiles. These profiles do not replace the parent's
DSO selection policy. Parent-chart galaxy-label fallback remains a presentation
rule: it may transfer only labels for selected objects that are present on both
the detail field and its parent, and it never removes Messier or Herschel 400
labels.

Old public codes map to the stable codes as follows:

| Old code | New code | Old code | New code |
| --- | --- | --- | --- |
| PD021A | PD01 | DD105 | DD01 |
| SD053 | SD01 | DD111 | DD02 |
| SD053A | SD02 | DD121 | DD03 |
| SD053B | SD03 | DD174 | DD04 |
| SD089 | SD04 | DD223 | DD05 |
| SD084 | SD05 | DD328 | DD06 |
| SD031 | SD06 | DD405A | DD07 |
| SD063 | SD07 | DD405B | DD08 |
| SD013 | SD08 | DD415 | DD09 |
| SD035 | SD09 |  |  |

### Deep 23-ring tiling experiment

The experimental Deep configuration uses 23 symmetric declination rings from
−82.5° to +82.5° at 7.5° intervals, plus two polar charts. RA staggering is
disabled and every ring begins at 0°. Its symmetric ring counts, north to
south, are `5 / 10 / 15 / 15 / 20 / 25 / 25 / 25 / 30 / 30 / 30 / 30 / 30 /
30 / 30 / 25 / 25 / 25 / 20 / 15 / 15 / 10 / 5`, for 492 main charts. The
equatorial ring has 30 charts at 12° intervals (00h00m, 00h48m, …, 23h12m).
The grids at ±15°, ±30°, ±45°, ±60° and ±75° align with the experimental
Standard grid.

A vectorized audit of the actual stereographic rectangles sampled the full
sky on a 0.25° RA/Dec grid with cos(Dec) area weighting. It found no uncovered
samples among 1,036,800 tested directions. Estimated area fractions are 63.16%
single coverage, 31.63% double, 2.79% triple and 2.43% four-or-more coverage;
the mean multiplicity is 1.445. A projected edge-distance scan found the
smallest sampled safety margin to be 0.216° (about 4.32 mm at 20 mm/°), near
RA 16h48m, Dec −56.9°. The smallest horizontal overlap at ring centres is
1.024° (20.48 mm) on the ±30° rings. Exact stereographic edge intersections
sampled along the RA direction found a minimum adjacent-ring overlap of about
0.78° (15.5 mm) at the polar-cap/±82.5° transition near RA 12h00m; a finer
local check measures approximately 0.79°. These
figures are numerical checks, not a proof for every continuous sky position;
the polar and ring-transition margins are weaker than the 30 mm nominal target.

The previous 430-chart layout also had no holes on the same 0.25° sample and
had estimated coverage fractions of 76.58% single, 20.73% double, 2.55% triple
and 0.14% four-or-more, with mean multiplicity 1.262. Its smallest sampled
safety margin was about 0.080° (1.61 mm). The 492-chart experiment therefore
trades 62 pages for more overlap and a regular equatorial/aligned grid. The
current repository state is an experiment; review it before adopting it as the
Deep release tiling.

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
- The 129-chart count is geometry-driven. A later optional pass may nudge
  individual chart centres by +-1-2 deg to move important regions away from page
  edges, but the draft deliberately uses a clean geometric grid only.
