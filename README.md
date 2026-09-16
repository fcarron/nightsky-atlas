# NightSky Atlas

NightSky Atlas generates publication-quality printable star atlases for visual
deep-sky observing, especially Dobsonian star-hopping.

The primary output is vector PDF. Secondary outputs include SVG, PNG previews,
annotated review PNGs and a machine-readable layout JSON document.

See `AGENTS.md` for the authoritative product, architecture and engineering
contract.

## Development

```bash
make setup   # create .venv and install the package with dev tools
make test    # run the test suite
make lint    # run Ruff
make check   # lint + test (standard pre-commit verification)
```

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

### Real star catalogue (Tycho-2)

```bash
.venv/bin/nightsky data fetch-stars     # download raw parts into data/raw/
.venv/bin/nightsky data import-stars    # build data/processed/stars/tycho2.sqlite
.venv/bin/nightsky chart render --chart test-cygnus \
    --star-store data/processed/stars/tycho2.sqlite --magnitude-limit 9.0
```

Raw and processed catalogue data are build inputs and are not committed. See
`docs/PERFORMANCE.md` for benchmark numbers and licensing notes.

## Status

Early development. See the development plan in `AGENTS.md`.
