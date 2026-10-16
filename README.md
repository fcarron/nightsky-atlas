# NightSky Atlas

## What is NightSky Atlas?

NightSky Atlas creates printable star charts and atlases
for visual deep-sky observing and Dobsonian star-hopping. Its main output is a
vector PDF; chart previews are also written as PNG files. Charts combine stars,
deep-sky objects, constellation geometry, coordinate grids and navigation.
The main editions are Pocket (5 mm/°), Standard (10 mm/°) and Deep (20 mm/°).
Eyepiece (40 mm/°) and Eyepiece Deep (80 mm/°) are experimental.

## Alpha status

The atlas generation pipeline works locally and offline once the catalogues
are prepared. This is an alpha: known label collisions remain on some pages,
and printed telescope-field review is still pending. An ordinary build can
write a complete PDF and still exit with status 1 because it found hard layout
issues; inspect its manifest and draft report. `--publication` is a stricter
zero-hard-issue check, not legal clearance or field-use approval.

No tagged public atlas download is linked here yet. The fixture quickstart
below generates an installation example; full-catalogue charts require the
separate data preparation steps. Run commands from the repository root.

## Requirements: Ubuntu 24.04 and WSL

The supported setup described here is Ubuntu 24.04, including Ubuntu running
under WSL. Ubuntu 24.04 provides Python 3.12 as `/usr/bin/python3`. Native
Windows and macOS have not been tested.

Rendering uses Cairo and Pango through PyGObject. Install their Ubuntu packages
before making the virtual environment. The compiler and Python headers are
needed when pip builds Pycairo from source. The `--system-site-packages` option is
needed so that the environment can import Ubuntu's `gi` bindings; a default
isolated virtual environment cannot see them.

## Install

Clone the repository and enter its directory:

```bash
git clone https://github.com/fcarron/nightsky-atlas.git
cd nightsky-atlas
```

Install the system libraries and Python bindings:

```bash
sudo apt update
sudo apt install -y \
    build-essential python3-dev python3-venv python3-gi python3-gi-cairo gir1.2-pango-1.0 \
    libcairo2-dev libfontconfig1 pkg-config
```

Create a Python 3.12 virtual environment that can use those system bindings,
then install NightSky Atlas and its development tools:

```bash
/usr/bin/python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e ".[dev]"
```

Confirm that the CLI and Pango bindings are available:

```bash
.venv/bin/nightsky --help
.venv/bin/python - <<'PYTHON'
import cairo
import gi
gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import PangoCairo
cr = cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, 10, 10))
PangoCairo.create_layout(cr)
print("PangoCairo OK")
PYTHON
```

No API key is needed to install or create charts. The Lato and Source Sans 3
fonts used by the renderer are bundled with the repository.

## Quickstart: create a test chart

The repository includes a small Virgo star fixture, so this first render does
not download astronomical catalogues:

```bash
.venv/bin/nightsky chart render \
    --chart test-virgo \
    --atlas atlas/standard.yaml \
    --style styles/standard.yaml \
    --stars data/fixtures/stars/test_virgo.csv \
    --optimize \
    --outdir build
```

The command writes both files here:

```text
build/standard/charts/test-virgo/chart.pdf
build/standard/charts/test-virgo/preview.png
```

The PDF is vector output. The PNG is a 150 dpi preview by default. This fixture
is deliberately small and is for checking the installation and renderer; it is
not a sample of the full catalogue or a complete atlas.

## Prepare astronomical catalogues

Raw downloads and processed catalogues are kept under `data/raw/` and
`data/processed/`; they are generated locally and are not committed. The first
real atlas needs a stellar store and a deep-sky catalogue. The following
commands are the CLI's fetch and import steps:

```bash
# Tycho-2: 20 compressed parts, about 159 MB total
.venv/bin/nightsky data fetch-stars

# Hipparcos main catalogue: about 53 MB; supplies bright stars missing in Tycho-2
.venv/bin/nightsky data fetch-hipparcos

# Merge Tycho-2 and Hipparcos into the indexed SQLite star store
.venv/bin/nightsky data import-stars

# OpenNGC deep-sky objects
.venv/bin/nightsky data fetch-openngc
.venv/bin/nightsky data import-openngc
```

The default paths are:

```text
data/raw/tycho2/                         Tycho-2 download parts
data/raw/hipparcos/                      Hipparcos main catalogue
data/processed/stars/tycho2.sqlite      merged star store (about 364 MB)
data/processed/stars/tycho2.manifest.json
data/raw/openngc/                        OpenNGC CSV source files
data/processed/dso/openngc.json          normalized deep-sky catalogue
data/processed/dso/openngc.manifest.json
```

The repository already contains the small constellation, star-name, observing
list and schematic nebula-outline fixtures used by the renderer. They do not
need to be fetched separately.

Reviewed full-catalogue charts also use an optional imported OpenNGC outline
layer. Its pinned download, checksum and existing converter invocation are in
[DATA_SOURCES.md](docs/DATA_SOURCES.md#imported-openngc-nebula-outlines).

### Optional catalogues

The Washington Double Star Catalog (WDS) adds a double/multiple-star overlay.
Charts can be built without it. The current CLI commands and default paths are:

```bash
.venv/bin/nightsky data fetch-wds
.venv/bin/nightsky data import-wds
```

The raw WDS download is about 6.5 MB; the processed overlay is about 57 MB.
When `data/processed/double_stars/wds.json` exists, atlas builds use it by
default. Use `--no-double-stars` to omit it.

UCAC4 is a separate faint-star supplement. No main chart needs it, but the
configured Pocket Pleiades detail PD02 explicitly requests it at 40 mm/° and
magnitude 11.25. A complete Pocket build therefore needs the supplement even
without global `--faint-star-store` options. Standard and Deep do not request it
by default. The complete source is about 8.5 GiB before its local SQLite store:

```bash
.venv/bin/nightsky data fetch-ucac4
.venv/bin/nightsky data import-ucac4-faint
```

Selected VizieR deep-sky catalogues can extend OpenNGC coverage. They are not
needed for the initial Standard atlas. To fetch the configured sources and
merge them with OpenNGC, run:

```bash
.venv/bin/nightsky data fetch-vizier-dsos
.venv/bin/nightsky data import-vizier-dsos
```

The merged catalogue is written to `data/processed/dso/catalogue.json` and is
used automatically when present, unless `--dsos` explicitly selects another file.
UCC 260615 can enrich that catalogue after the VizieR import:

```bash
.venv/bin/nightsky data fetch-ucc
.venv/bin/nightsky data import-ucc
```

Import makes records available; it does not select every imported object. VizieR sources have
source-specific terms, so review them before redistribution. See
[docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) for provenance and licensing.

## Generate a full atlas

Build the complete Standard chart set with the star and OpenNGC catalogues:

```bash
.venv/bin/nightsky atlas build --edition standard \
    --star-store data/processed/stars/tycho2.sqlite \
    --dsos data/processed/dso/openngc.json
```

Standard contains 129 main charts plus eight detail charts. The default build uses two
workers and also creates per-chart PNG previews. Use `--jobs 1` to build
serially, `--jobs 4` if several GiB of memory are available, or `--no-png` to
skip preview images. A full build can take substantially longer than the
single-chart quickstart.

For a strict release build, add `--publication`. It checks complete sky
coverage, nonempty processed star and DSO catalogues, and source manifests with
matching checksums. If a processed catalogue predates checksummed manifests,
import it again before this check:

```bash
.venv/bin/nightsky atlas build --edition standard \
    --star-store data/processed/stars/tycho2.sqlite \
    --dsos data/processed/dso/openngc.json \
    --publication
.venv/bin/nightsky atlas validate --edition standard --publication
```

To build Pocket or Deep instead, change `--edition standard` to `pocket` or
`deep`. Pocket has 39 main charts and four details; Deep has 492 main charts
and ten details. Prepare UCAC4 for Pocket PD02 as described above. Explicit configuration paths are also accepted with `--atlas` and
`--style`; for example, the experimental Eyepiece configuration is
`atlas/eyepiece.yaml` with `styles/eyepiece.yaml`.

Colour is opt-in; `--edition` uses the classic black-and-white preset. The
canonical colour styles are `styles/color/pocket.yaml`,
`styles/color/standard.yaml` and `styles/color/deep.yaml`. For example:

```bash
.venv/bin/nightsky atlas build --edition pocket \
  --style styles/color/pocket.yaml
```

## Find and print the PDFs

The combined atlas is written to:

```text
build/standard/atlas.pdf
```

Individual chart PDFs and previews are under
`build/standard/charts/<chart-id>/`. Open the combined PDF in a PDF viewer and
print at **100% / actual size** so the edition's printed scale is preserved.
Disable “fit to page” or equivalent scaling in the print dialog. The atlas
pages are A4 landscape.

## Prepare an alpha download

Keep the PDF with its source notices and corresponding Gaia contour data.
From the repository root, prepare a local package from a completed build:

```bash
.venv/bin/python tools/prepare_alpha_download.py \
    --atlas-dir build/pocket \
    --outdir build/downloads/pocket-alpha
.venv/bin/python -m zipfile -c build/downloads/pocket-alpha.zip \
    build/downloads/pocket-alpha
```

The tool verifies ordinary output checksums, unchanged build inputs and
catalogue metadata. It retains recorded layout issues, includes notices,
the exact Gaia GeoJSON, configuration files and an input/environment inventory.
It refuses to overwrite an existing package. This does not satisfy the
zero-hard-issue `--publication` check or grant legal/field approval.
No upload happens. For separate PDF hosting, link the notices and contour
download beside it. See [alpha download notices](docs/ATLAS_DISTRIBUTION.md).

## Editions

Pocket is the compact 5 mm/° edition, Standard is 10 mm/°, and Deep is 20 mm/°.
Pocket emphasizes wide-field orientation, binoculars and small telescopes;
Standard is a general-purpose observing atlas; Deep provides smaller fields
and fainter targets. Their chart scale and object selection differ. Use `--edition pocket`,
`--edition standard` or `--edition deep` with `nightsky atlas build`.
Eyepiece (40 mm/°) and Eyepiece Deep (80 mm/°) are experimental and currently
require explicit atlas and style files. A 100%-print comparison sheet for the
three main editions can be rendered with:

```bash
.venv/bin/nightsky chart magnitude-scale --edition-comparison --outdir build
```

## Development and tests

The same Ubuntu system packages and `--system-site-packages` virtual
environment described above are needed for development. Run the checks with:

```bash
make test
make test-fast
make lint
make check
```

`make test-fast` omits fine-resolution all-sky audits (`slow`) and checks
against locally imported full catalogues (`integration`). `make check` always
runs the complete suite, including `tests/build/` and publication checks.
Tests do not download catalogues; most use committed small fixtures.
Integration cases requiring imported catalogues are skipped with a reason when
those files are absent, and run during `make check` when the files are available.
On Ubuntu, install the system packages above before running `make setup`; the
target creates the virtual environment with access to Ubuntu's `gi` bindings.

## License and data sources

The generator is licensed under the [MIT License](LICENSE). Generated atlases
also include third-party fonts, constellation geometry and catalogue data with
their own terms; the MIT license does not automatically cover generated PDFs.
Tycho-2 and Hipparcos are CC BY-NC 3.0 IGO, OpenNGC is CC BY-SA 4.0, and the
Gaia-derived Magellanic contour data are ODbL 1.0. The WDS is USNO-maintained;
its current source page requests acknowledgement but does not state a separate
reuse licence. There is no blanket licence for a generated PDF; the intended
beta use is free and non-commercial, subject to source terms. Review
[docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) and
[THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md) before sharing or
redistributing outputs.
