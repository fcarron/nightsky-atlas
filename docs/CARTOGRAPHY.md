# Standard edition cartography

Frozen at M14.1 (2026-09-16).

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
| Charts (tiled) | 135 |

This sits between Sky Atlas 2000.0 (26 charts, ~10 mm/deg, mag 8.5) and
Uranometria 2000.0 (~220 charts, mag ~9.75) in chart count: Tirion-like scale
and readability, but a deeper limit and many more pages.

## Tiling

Declination-band tiling with 3 degree overlap. Bands step by
`height - overlap` from pole to pole; within a band, charts are spaced in right
ascension using the band edge nearest the equator (where a chart covers the
least RA), so coverage is guaranteed and adjacent charts overlap. Near-pole
bands naturally widen in RA and close the polar caps.

- Coverage validated at 1 degree sampling: 0 gaps, maximum overlap 6 charts.
- Charts are numbered `standard-NNN` (deterministic band-then-RA order).
- N/S/E/W neighbour references are derived from band adjacency and RA order.

## Build

```bash
nightsky atlas tile                        # 135 chart definitions + neighbours
nightsky atlas coverage --step 1           # gaps=0, max_overlap=6
nightsky atlas build --png-dpi 100         # per-page PDF/PNG + atlas.pdf + manifest
```

`build/<atlas>/manifest.json` records page geometry, limits, per-page layout
hashes and diagnostics, data-source manifests, AI model and the git commit.

## Open items

- 14 residual hard violations on 6 dense pages (Milky Way / Virgo-Coma fields);
  the two reference MVP charts validate cleanly.
- Polar pages use the same chart field and stereographic projection, not a
  dedicated polar projection; coverage is complete but local distortion near
  the pole is larger. Fields reaching the pole use the polar grid (meridians at
  the coarser `grid.polar_ra_step_deg`); the meridian fan is still dense at the
  pole itself. Revisit if field tests show it matters.
