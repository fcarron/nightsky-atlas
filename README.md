# NightSky Atlas

NightSky Atlas generates publication-quality printable star atlases for visual
deep-sky observing, especially Dobsonian star-hopping.

The primary output is vector PDF. Secondary outputs include SVG, PNG previews,
annotated review PNGs and a machine-readable layout JSON document.

See `AGENTS.md` for the condensed engineering contract, and `docs/` for the
product, architecture, plan, cartography, AI-review and data-source details.

## Development

```bash
make setup   # create .venv and install the package with dev tools
make test    # run the test suite
make lint    # run Ruff
make check   # lint + test (standard pre-commit verification)
```

The Standard style uses the Lato font family. Install Lato Regular and Bold on
the build machine so Pango measures and renders the intended typeface.

Run the command-line interface:

```bash
.venv/bin/python -m nightsky_atlas --help
```

Render the first development chart (Virgo) to a PDF and PNG preview:

```bash
.venv/bin/nightsky chart render \
    --chart test-virgo \
    --atlas atlas/standard.yaml \
    --style styles/standard.yaml \
    --stars data/fixtures/stars/test_virgo.csv \
    --outdir build
```

Artifacts are written to `build/standard/charts/test-virgo/chart.pdf` and
`preview.png`. Render a star magnitude diagnostic page with:

```bash
.venv/bin/nightsky chart magnitude-scale --outdir build
```

For a 100%-print A4 comparison of the Pocket, Standard and Deep star-symbol
curves, use:

```bash
.venv/bin/nightsky chart magnitude-scale --edition-comparison --outdir build
```

All chart and atlas commands accept `--edition pocket`, `--edition standard`,
or `--edition deep` to select matching atlas and style presets. Explicit
`--atlas` and `--style` paths remain available for custom definitions. Optional
layers can be omitted explicitly, for example `--no-constellations` or
`--no-outlines`.

### Real star catalogue (Tycho-2)

```bash
.venv/bin/nightsky data fetch-stars       # download raw Tycho-2 parts into data/raw/
.venv/bin/nightsky data fetch-hipparcos   # download the bright-star supplement
.venv/bin/nightsky data import-stars      # build data/processed/stars/tycho2.sqlite
.venv/bin/nightsky chart render --chart test-cygnus \
    --star-store data/processed/stars/tycho2.sqlite --magnitude-limit 9.0
```

The store merges Tycho-2 with the Hipparcos main catalogue because Tycho-2 omits
the brightest stars (Deneb, Vega, Altair, Sirius, ...). See
`docs/DATA_SOURCES.md` for provenance and licensing.

Standard follows the field-readability philosophy of *Sky Atlas 2000.0*
without copying its label selection. Star labels are observer-oriented, not
exhaustive: curated familiar names, Bayer designations, selective Flamsteed
numbers, then relevant variable/special designations. Important names may
appear as `Deneb α`; Bayer labels are normally Greek letters alone and
Flamsteed labels numbers alone. Constellation suffixes are omitted on the map
in normal cases, and a star normally shows Bayer *or* Flamsteed, not both.
Shorter or unambiguous longer variants remain available to the deterministic
layout. Obscure official names and HIP/HD/TYC IDs are not normally printed.
Full designations, aliases and catalogue identities remain separate from the
edition-configurable display text; imported cross-ID provenance is tracked in
`docs/DATA_SOURCES.md`. To count eligible labels before chart placement, run:

```bash
.venv/bin/nightsky data star-label-report --edition standard
```

### Double/multiple stars (WDS overlay)

```bash
.venv/bin/nightsky data fetch-wds        # download the raw WDS into data/raw/
.venv/bin/nightsky data import-wds       # build data/processed/double_stars/wds.json
```

Tycho-2 remains the source of truth for single-star positions and magnitudes.
The Washington Double Star Catalog is a separate overlay for visual double and
multiple systems; systems are linked to stars per chart, and only safe matches
influence the printed chart. A pair that cannot be separated on the page is
drawn as one symbol with a horizontal marker; a separable pair is drawn as two
real positions. See `docs/ARCHITECTURE.md` and `docs/DATA_SOURCES.md`.

Raw and processed catalogue data are build inputs and are not committed. See
`docs/PERFORMANCE.md` for benchmark numbers and licensing notes.

### Full atlas with overview pages

```bash
.venv/bin/nightsky atlas build --star-store data/processed/stars/tycho2.sqlite
```

Atlas builds use two chart workers by default. Use `--jobs 4` with several GiB
of free memory, or `--jobs 1` for a serial build. Chart pages are
assembled into the atlas PDF in chart order regardless of worker count.

Add `--publication` for a strict release build. It requires the complete chart
set, full-sky coverage, nonempty processed star and DSO catalogues, and matching
source manifests with a `processed_sha256` checksum. Re-import older processed
catalogues once to create checksummed manifests. The build records fingerprints
of code, configuration and geometry inputs, then publishes from a staging
directory only after validation. An earlier publication is retained as
`build/.standard-previous` (or a numbered variant). Development subsets remain
available without this flag.

After building, verify the files and recorded inputs without rendering again:

```bash
.venv/bin/nightsky atlas validate --edition standard --publication
```

The combined `build/standard/atlas.pdf` opens with front matter and two
whole-sky overview pages (northern and southern hemispheres) showing the
constellation background, the bright stars and one trapezoidal cell per chart
with its printed chart code. Use `--no-overviews` to omit them. An optional
per-chart locator inset is enabled with `locator.enabled: true` in the style.
See `docs/CARTOGRAPHY.md`.

## Status

Early development. See the development plan in `docs/DEVELOPMENT_PLAN.md` and the
current snapshot in `docs/STATE.md`.

## License and data attribution

The atlas generator is licensed under the [MIT License](LICENSE). Original
NightSky Atlas cartographic design is CC BY 4.0 where identified. Official PDFs
are free for non-commercial sharing, subject to third-party rights. The MIT
licence does not automatically apply to generated atlases. Source-specific
terms are documented in [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) and
[THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).
Constellation stick figures follow the Sky & Telescope tradition via
Stellarium's Western (Sky & Telescope) sky culture. They are conventional
figures, separate from official IAU boundaries. Their HIP-referenced primary
and supplementary strokes retain bold/normal/thin hierarchy, with physical
widths configurable by style. The figure data is CC BY-SA 2.0; the IAU boundary
polygons are BSD-3-Clause. See [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md)
for attribution and terms that generated atlases must retain.

See [CONTRIBUTING.md](CONTRIBUTING.md) for local checks and contribution rules.
