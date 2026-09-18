# Constellation geometry sources

The two fixture files have distinct provenance and licenses.

## IAU/MacRobert stick figures

- **File:** `constellations.lines.json`
- **Source:** Dominic Ford's
  [`dcf21/constellation-stick-figures`](https://github.com/dcf21/constellation-stick-figures),
  `constellation_lines_iau.dat`, commit
  `75d29c207bbd752023c447ddd1f9f4ff0eb47538`.
- **Copyright / attribution:** Alan MacRobert et al.; imported via Dominic
  Ford's data conversion.
- **License:** [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
- **Transformation:** Hipparcos identifiers were resolved to J2000 RA/Dec and
  written as GeoJSON `MultiLineString` features. Segment connectivity is
  unchanged.

## IAU constellation boundaries

- **File:** `constellations.bounds.json`
- **Source:** [d3-celestial](https://github.com/ofrohn/d3-celestial) by Olaf
  Frohn, `master`, fetched 2026-09-16.
- **License:** BSD-3-Clause; see the adjacent `LICENSE` file.
- **Transformation:** none on import. Boundary polygons are converted to a
  deduplicated segment set at load time.

These committed fixtures make an offline build reproducible. Further catalogue
licensing and attribution requirements are recorded in
`docs/DATA_SOURCES.md`.
