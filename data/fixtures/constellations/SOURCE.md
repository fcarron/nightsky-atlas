# Constellation geometry source

- **Source:** d3-celestial — <https://github.com/ofrohn/d3-celestial>
- **Version:** `master` (files fetched 2026-09-16)
- **Files:**
  - `constellations.lines.json` — common stick-figure segments (MultiLineString)
  - `constellations.bounds.json` — constellation area polygons (Polygon); their
    shared edges form the IAU boundary network
- **License:** BSD-3-Clause. See the adjacent `LICENSE` file.
- **Coordinate fields:** GeoJSON `[ra_deg, dec_deg]`, J2000-equivalent chart
  coordinates. libration-free, RA increases eastward.
- **Transformations performed on import:** none; coordinates are read as-is.
  The boundary polygons are converted to a deduplicated segment set at load
  time (shared edges are drawn once).

These fixtures are committed because they are small (about 68 kB) and the
build must be reproducible without network access. Full licence and
attribution notes are recorded in `docs/DATA_SOURCES.md`.
