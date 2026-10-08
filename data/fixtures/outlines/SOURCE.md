# Schematic nebula outlines

`nebulae.json` holds coarsely hand-authored RA/Dec outlines for extended
deep-sky objects whose shape is not captured by an ellipse (major/minor axis).

- **Origin:** authored for NightSky Atlas on 2026-09-16. The vertices are a
  deliberately coarse, schematic tracing of each object's bright extent, not a
  survey-derived boundary.
- **License:** [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
  This covers only the project-authored schematic artwork, not third-party
  catalogue data or coordinates.
- **Coordinates:** `[ra_deg, dec_deg]` J2000/ICRS, RA increasing eastward. Rings
  are implicitly closed; the first vertex is not repeated.
- **Stable IDs:** each outline is addressed as `outline:dso:<dso_id>`, matching
  the normalized deep-sky object ID (e.g. `outline:dso:NGC7000`).

Coverage is intentionally small and Cygnus-centred while the outline pipeline is
validated. New outlines are added only when the object is large enough that an
ellipse would mislead.

| `dso_id` | Common name |
| --- | --- |
| `NGC7000` | North America Nebula |
| `IC5070` | Pelican Nebula |
| `NGC6960` | Western Veil |
| `NGC6992` | Eastern Veil |
| `NGC6979` | Pickering's Triangle |
