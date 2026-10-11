# Color Atlas Style Experiment

This is an optional rendering study. The production Pocket, Standard and Deep
styles remain monochrome. The experimental styles inherit their edition's
geometry, star and DSO selection, symbols, labels and layout rules, then add the
palette and Milky Way fills described here.

## Palette and implementation

The styles use the requested white paper, near-black stars and labels, muted
green constellation figures, neutral grey grid and boundaries, and restrained
class colors for deep-sky symbols. The palette combines the clear field
orientation of Pocket Sky Atlas with the gentle Milky Way wash of Sky Atlas
2000.0 Deluxe and the class differentiation of Interstellarum. It is an
original NightSkyAtlas treatment, not a reproduction of those atlases.

Milky Way fills use the existing d3-celestial contour data, the chart's
stereographic projection and the source's five discrete levels. Each level is
a flat color; there is no gradient, interpolation or generated sky geometry.
The renderer keeps rings grouped by their source GeoJSON polygon and checks the
spherical polygon side before clipping it to a chart. This avoids treating a
large contour's projected complement as its interior. Level 1 establishes the
filled region against a white exterior; each stronger level is clipped to all
weaker levels, so a contour cannot color sky outside the Milky Way. A chart
fully inside a contour still receives that fill when no contour edge crosses
it. A scene without Milky Way source data remains unchanged. Existing contour
lines remain softly stroked on top. No Milky Way geometry or catalogue data was
added or changed. Fill levels remain configured by the optional style and must
also be enabled in the contour selection.

DSO symbol interiors use their configured class colors while the symbol edges
remain black. In color styles, selected bright-nebula and supernova-remnant
contour polygons are lightly filled with their class colors, then their
existing contours are drawn over the fill. The fill follows only the supplied
schematic outline data; unoutlined regions are unchanged. Existing symbol
shapes, line styles and sizes are unchanged.

| Variant | Standard / Deep | Pocket preview |
| --- | --- | --- |
| A | 1 + 3: `#E8F1F8`, `#D6E6F3` | 1–5: `#E8F1F8`, `#E3EEF7`, `#D6E6F3`, `#CFE2F1`, `#C4D9EC` |
| B | 1 + 3: `#E3EEF7`, `#CFE2F1` | 1–5: `#E8F1F8`, `#E3EEF7`, `#CFE2F1`, `#B8D7EA`, `#9FC9E2` |
| C | 1 + 3 + 5: `#E8F1F8`, `#D6E6F3`, `#C4D9EC` | 1–5: `#E8F1F8`, `#E3EEF7`, `#CFE2F1`, `#B8D7EA`, `#9FC9E2` |

Each edition has three optional style files under
`styles/experiments/color/`. Pocket uses a slightly stronger Milky Way stroke;
Deep uses the gentlest stroke. The color system and fill tones remain shared.
The experimental contour widths are 0.07 mm for Pocket and Standard, and
0.06 mm for Deep.

## Revised Pocket preview

The latest review focuses on Pocket's five discrete contour levels. Standard
and Deep retain their original level selections for comparison.

| Region | Chart | Preview directory |
| --- | --- | --- |
| Cygnus | P009 | `build/color-atlas/revised/pocket-{a,b,c}/pocket-009/` |
| Sagittarius / Scutum | P027 | `build/color-atlas/revised/pocket-{a,b,c}/pocket-027/` |
| Orion / Monoceros | P023 | `build/color-atlas/revised/pocket-{a,b,c}/pocket-023/` |
| Virgo Cluster | P021 | `build/color-atlas/revised/pocket-{a,b,c}/pocket-021/` |
| Southern Milky Way | P037 | `build/color-atlas/revised/pocket-{a,b,c}/pocket-037/` |

Each directory contains a vector `chart.pdf` and a 180-dpi `preview.png` under
`pocket/charts/<chart-id>/`. The previews use the production Pocket star and DSO
data and the normal deterministic label optimizer.

## Contour-fill regression previews

The latest local check uses Pocket variant B and real catalogue data:

- Cygnus P008, including Deneb inside and a white exterior sample:
  `build/color-atlas/p008-finalcheck/pocket/charts/pocket-008/preview.png`
- Adjacent Cygnus P009, including Sadr inside and Vega outside:
  `build/color-atlas/p009-nested/pocket/charts/pocket-009/preview.png`

These previews check the source contour topology and nested fill clipping. The
full atlas should still be reviewed at print size; some local fields do not
intersect all five brightness contours, so not every chart contains every fill
color.

## Earlier rendered comparison

The earlier local proof set contains five regions for each edition and each variant:

| Region | Pocket | Standard | Deep |
| --- | --- | --- | --- |
| Cygnus | P009 | S019 | D096 |
| Sagittarius / Scutum | P027 | S092 | D329 |
| Orion / Monoceros | P023 | S070 | D254 |
| Virgo Cluster | P021 | S066 | D216 |
| Southern Milky Way | P037 | S120 | D455 |

Each proof has a vector `chart.pdf` and a 100-dpi `preview.png` under
`build/color-atlas/proofs/<edition>-<variant>/<edition>/charts/<chart-id>/`.
The Standard Cygnus field was also rendered at 300 dpi for print-scale review:
`build/color-atlas/print-scale/standard-{a,b,c}/standard/charts/standard-019/`.
All proofs use the processed Tycho-2 star store and the normal label optimizer.

## Visual assessment

- **A** is the calmest treatment. The broad Milky Way shape is visible, though
  the palest outer band may fade on some printers.
- **B** improves orientation at normal print size. Its two very light tones
  remain behind stars, DSO marks and labels. It is the preferred balance for
  Pocket and Standard; Deep can retain a gentler edition-specific outline.
- **C** adds a useful inner brightness distinction in some fields, but it is
  subtle at atlas scale and can add visual texture in dense Deep charts. The
  extra band is not a clear overall improvement over B.

This is a chart-sample study, not a complete colored-atlas publication review.
Printer, paper and grayscale reproduction can change the apparent contrast;
the final print specification remains open.
