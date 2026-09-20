# Star names and designations

`starnames.json` maps a Hipparcos number to common names and designations used
for star labels.

`curated.yaml` is the NightSky editorial selection for printed proper names
(99 core, 86 standard, 17 extended),
variable-star designations and a few customary Flamsteed preferences. It is
keyed by HIP number and does not alter the source catalogue. Its 202 canonical
proper-name spellings and HIP identifications were checked against the IAU
Catalog of Star Names (2022-04-04 snapshot, IAU-produced data, Creative
Commons Attribution; the snapshot does not specify a version):
<https://iauarchive.eso.org/public/themes/naming_stars/>. The tier assignments
are original NightSky editorial choices, not copied from another atlas.
Retain this attribution when redistributing the curated selection. The
underlying d3-celestial cross-identifications remain BSD-3-Clause below.
The machine-readable snapshot used for the HIP/name comparison is archived at
<https://github.com/mirandadam/iau-starnames/blob/master/catalog_data/IAU-CSN.txt>;
its header identifies the IAU as producer and requests citation of the IAU page.
It is not vendored. Variable-star and Flamsteed preferences in `curated.yaml`
were selected manually from the d3-celestial fields below.

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
