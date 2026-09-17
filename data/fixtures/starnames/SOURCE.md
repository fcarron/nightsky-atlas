# Star names and designations

`starnames.json` maps a Hipparcos number to common names and designations used
for star labels.

- **Source:** d3-celestial (Olaf Frohn), `data/starnames.json`, `master`,
  fetched 2026-09-16.
- **License:** **BSD-3-Clause** (see `LICENSE` in this directory).
- **Transformation:** imported from the raw d3-celestial file, keeping only
  `name`, `bayer`, `flam`, `var` and constellation (`c`); thin spaces and
  direction marks were stripped. Keys are decimal Hipparcos numbers as strings.
- **Committed:** yes (~207 kB); the build must be reproducible offline.

Example entry:

```json
"102098": {"name": "Deneb", "bayer": "\u03b1", "flam": "50", "c": "Cyg"}
```
