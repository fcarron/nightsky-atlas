# d3-celestial Milky Way outline data

`mw.json` is vendored from `ofrohn/d3-celestial` at commit
`7e720a3de062059d4c5400a379146a601d9010e0`.

- Upstream file: <https://github.com/ofrohn/d3-celestial/blob/7e720a3de062059d4c5400a379146a601d9010e0/data/mw.json>
- Raw file: <https://raw.githubusercontent.com/ofrohn/d3-celestial/7e720a3de062059d4c5400a379146a601d9010e0/data/mw.json>
- Upstream project and maintainer: d3-celestial, Olaf Frohn
- Original outline source cited by d3-celestial: José R. Vieira, *Milky Way
  Outline Catalog*
- License for the GeoJSON as distributed with d3-celestial: BSD-3-Clause;
  see the adjacent `LICENSE` file. This notice does not assert that Vieira
  released the original catalogue under that license.
- SHA-256: `aee221a7a0e879418e685de00c3e68fbdfac5667c0a8aab74929ef9cf4aab4fb`

NightSky Atlas reads the five GeoJSON features `ol1` through `ol5`, converts
GeoJSON longitude back to equatorial right ascension, projects the coordinates
with the chart's stereographic projection, and clips contour paths to the chart
field. It does not alter the source geometry. Black-and-white styles draw
contour lines; experimental colour styles also fill the contour levels.
