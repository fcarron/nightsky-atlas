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
the declination rings proceed from north to south, and `standard-129` is the
south polar cap. Within each ring, the RA anchor is numbered first and
subsequent charts proceed westward (decreasing RA), matching the printed
north-up, east-left chart orientation. Thus a chart's west neighbour is
normally the next number, wrapping at the RA seam. Declared N/S/E/W neighbours
are derived from actual projected chart edges and must pass the neighbour-
overlap test.

The numbering change only permutes chart IDs within each ring; centres, fields,
ring counts, offsets and projected footprints are unchanged. For a ring of
`n` charts, the anchor remains first, followed by the other centres in
decreasing RA. This convention is shared by Pocket, Standard and Deep. Example
physical-chart mappings from the former ordering are Pocket `P03 → P06`,
Standard `S026 → S019`, and Deep `D116 → D093`. Detail charts keep their stable
PD/SD/DD codes; their parent IDs refer to the same physical main-chart fields
under the new numbering.

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
(`PD01`, `SD01`… or `DD01`…), its region, scale and field. Main-chart
relationships are derived from the actual projected sky footprints: a detail
chart can be referenced from several overlapping main charts, while it is
printed only once. Its clipped footprint and linked code appear on each main
chart with meaningful overlap. The detail-chart directory and PDF links list
all related main-chart codes. Codes do not derive from parent chart numbers.

An optimized main-chart DSO label can be suppressed only when its object lies
inside a related detail chart and that same DSO label is successfully placed
there without a hard layout issue. The symbol remains visible on the main
chart. A detail chart elsewhere in the atlas is not sufficient evidence.

The parent edition remains the source of DSO selection: Pocket details use
Pocket selection, Standard details use Standard selection, and Deep details use
Deep selection. A star profile can be denser without changing the DSO policy.
The selected star profile supplies star limits, symbol sizes and star-label
style; the base edition continues to supply DSO styling and selection. An
optional UCAC4 supplement may be enabled for detail charts without adding it to
the parent charts.

| Edition and detail | Code | Scale | Stars to | Related main charts |
| --- | --- | ---: | ---: | --- |
| Pocket — Virgo core | PD01 | 20 mm/° | 9.0 | P21, P20, P12, P11 |
| Standard — Virgo Cluster | SD01 | 20 mm/° | 10.5 | S051, S050, S066, S065 |
| Standard — Virgo core | SD02 | 80 mm/° | 13.5 | S051 |
| Standard — South Virgo | SD03 | 40 mm/° | 12.25 | S066, S051 |
| Standard — Fornax core | SD04 | 40 mm/° | 12.25 | S101, S113, S102 |
| Standard — Sagittarius clusters | SD05 | 20 mm/° | 10.5 | S092, S077, S091, S076 |
| Standard — Cygnus nebula field | SD06 | 20 mm/° | 10.5 | S019, S031, S030 |
| Standard — Orion Nebula | SD07 | 20 mm/° | 10.5 | S070, S085 |
| Standard — Double Cluster | SD08 | 20 mm/° | 10.5 | S016, S007, S027, S017 |
| Standard — Pleiades | SD09 | 20 mm/° | 10.5 | S041, S056, S042, S057 |
| Deep — NGC 7331 / Stephan's Quintet | DD01 | 40 mm/° | 12.25 | D093, D094, D118, D119 |
| Deep — Pleiades | DD02 | 40 mm/° | 12.25 | D167, D168, D138 |
| Deep — Coma core | DD03 | 80 mm/° | 13.5 | D128, D129, D156 |
| Deep — Markarian chain | DD04 | 80 mm/° | 13.5 | D186, D187 |
| Deep — Orion Nebula | DD05 | 80 mm/° | 13.5 | D285, D255 |
| Deep — Fornax core | DD06 | 40 mm/° | 12.25 | D398, D373, D399, D374 |
| Deep — 30 Doradus | DD07 | 80 mm/° | 13.5 | D473, D474, D485, D484 |
| Deep — LMC bar | DD08 | 80 mm/° | 13.5 | D474, D473 |
| Deep — NGC 346 / SMC | DD09 | 40 mm/° | 12.25 | D477, D486, D476, D462 |

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

The experimental Deep configuration has 23 symmetric declination rings plus
two polar charts, for 492 main charts. RA staggering is disabled, every ring
starts at 0°, and the equatorial ring has 30 charts at 12° intervals
(00h00m, 00h48m, …, 23h12m). The selected ring centres, north to south, are
`+83°, +75°, +67.5°, +60°, +53°, +45°, +37.5°, +30°, +22.5°, +15°, +7.5°,
0°, −7.5°, −15°, −22.5°, −30°, −37.5°, −45°, −53°, −60°, −67.5°, −75°,
−83°`. Ring counts remain `5 / 10 / 15 / 15 / 20 / 25 / 25 / 25 / 30 / 30 /
30 / 30 / 30 / 30 / 30 / 25 / 25 / 25 / 20 / 15 / 15 / 10 / 5`. Standard-
aligned declination rings at 0°, ±15°, ±30°, ±45°, ±60° and ±75° remain in
place.

The small shifts were compared using the same deterministic audit utility:
`.venv/bin/python tools/audit_deep_ring_shifts.py`. It projects the actual
stereographic chart rectangles. Global coverage uses 1,036,800 directions on
the 0.25° RA/Dec grid, weighted by cos(Dec); transition widths use a finer
0.125° RA / 0.0125° declination scan. The local margin column further samples
within one degree of the coarse global minimum, its antipode and reflected
declination. These are numerical samples, not a proof of continuous coverage.
Safety margin means the greatest projected edge clearance available from any
covering chart at a sampled sky point. Ring overlap is the narrowest common
declination run covered by adjacent rings at a given RA; polar overlap is
reported separately. Horizontal overlap is measured between adjacent charts
along a ring-centre parallel.

| Metric | Baseline | Candidate A | Candidate B | Candidate C | Selected |
|---|---:|---:|---:|---:|---:|
| Ring shifts from baseline | none | 82.5→83.5°, 75→75.5° | A + 52.5→53° | A + 52.5→53.25° | 82.5→83°, 52.5→53° |
| Main charts | 492 | 492 | 492 | 492 | 492 |
| Uncovered samples (0.25°) | 0 | 0 | 0 | 0 | 0 |
| Minimum global safety margin | 4.32 mm | 4.32 mm | 5.21 mm | 6.10 mm | **5.21 mm** |
| Approx. location of global minimum | RA 00h48m, Dec −56.875° | same | RA 00h48m, Dec −57.125° | RA 00h48m, Dec −57.375° | RA 00h48m, Dec −57.125° |
| Fine local safety margin | 3.64 mm | 3.64 mm | 5.16 mm | 5.92 mm | **5.16 mm** |
| Minimum horizontal overlap | 20.48 mm at ±30° | same | same | same | same |
| Minimum ring-to-ring overlap | 20.25 mm, ±75/82.5° | 12.50 mm, 67.5/75.5° | 12.50 mm, 67.5/75.5° | 10.50 mm, 45/53.25° | **15.50 mm, 45/53°** |
| Polar-cap transition overlap | 15.75 mm near RA 12h00m | 40.50 mm | 40.50 mm | 40.50 mm | **28.00 mm near RA 12h00m** |
| Area covered 1 / 2 / 3 / 4+ times | 63.16 / 31.63 / 2.79 / 2.43% | 63.00 / 31.91 / 2.70 / 2.39% | 62.90 / 32.10 / 2.64 / 2.36% | 62.84 / 32.20 / 2.61 / 2.35% | 63.01 / 31.91 / 2.68 / 2.40% |
| Mean coverage multiplicity | 1.4448 | 1.4447 | 1.4447 | 1.4447 | 1.4447 |

Candidate B improves the weakest sampled margin but shifts the ±75° ring to
±75.5°, creating a 12.5 mm narrow transition to ±67.5°. Candidate C raises
the sampled global margin further, but its 45°/53.25° transition falls to
10.5 mm and its chart-corner clearance is only 7.5 mm. The selected smaller
adjustment keeps ±75° unchanged: it matches Candidate B's global and fine
local safety margins, improves the polar transition from 15.75 to 28.0 mm,
and keeps the narrowest ring-only transition at 15.5 mm. Its weakest region is
still the 45°/53° ring junction, so the change is a measured improvement, not
a claim of uniformly generous overlap. All variants retained 2,220 neighbour
references with no missing target IDs; the tiling regression test checks that
referenced neighbours have actual geometric overlap.

For context, the preceding 430-chart layout had no holes on its 0.25° sample,
estimated coverage fractions of 76.58% single, 20.73% double, 2.55% triple and
0.14% four-or-more, and mean multiplicity 1.262. Its smallest sampled safety
margin was about 1.61 mm. The 492-chart aligned experiment uses 62 more main
charts for higher overlap and regular RA grids. Reproduce the shift comparison
with the command above; inspect the active YAML for the exact published
configuration.

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
