from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from nightsky_atlas.catalog import stellarium_figures
from nightsky_atlas.catalog.dso_store import load_dso_catalog
from nightsky_atlas.catalog.manifest import file_sha256
from nightsky_atlas.catalog.store import QueryBox, StarStore
from nightsky_atlas.catalog.systems import load_system_catalog
from nightsky_atlas.catalog.tycho import raw_part_paths
from nightsky_atlas.cli import main

FIXTURES = Path(__file__).resolve().parents[1] / "data/fixtures"


def test_openngc_import_cli_preserves_data_and_manifest_on_repeat(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    source = (FIXTURES / "openngc/sample.csv").read_bytes()
    (raw / "NGC.csv").write_bytes(source)
    (raw / "addendum.csv").write_bytes(source.splitlines(keepends=True)[0])
    output, manifest = tmp_path / "catalogue.json", tmp_path / "manifest.json"
    command = [
        "data", "import-openngc", "--raw", str(raw),
        "--out", str(output), "--manifest", str(manifest),
    ]
    assert main(command) == 0
    first = output.read_bytes(), manifest.read_bytes()
    assert main(command) == 0
    assert (output.read_bytes(), manifest.read_bytes()) == first
    objects = {obj.id: obj for obj in load_dso_catalog(output)}
    assert objects["NGC0224"].ra_deg == pytest.approx(10.68479167)
    assert objects["NGC0224"].major_axis_arcmin == 177.83
    assert json.loads(manifest.read_text())["processed_sha256"] == file_sha256(output)


def test_star_import_cli_merges_bright_stars_and_supports_figure_import(
    tmp_path: Path, monkeypatch
) -> None:
    raw = tmp_path / "tycho"
    raw.mkdir()
    source = (FIXTURES / "tycho2/sample.dat").read_bytes()
    for index, part in enumerate(raw_part_paths(raw)):
        part.write_bytes(gzip.compress(source if index == 0 else b"", mtime=0))
    bright = tmp_path / "hipparcos"
    bright.mkdir()
    (bright / "hip_main.dat").write_bytes((FIXTURES / "hipparcos/sample.dat").read_bytes())
    store, manifest = tmp_path / "stars.sqlite", tmp_path / "stars.manifest.json"
    assert main([
        "data", "import-stars", "--raw", str(raw), "--bright-raw", str(bright),
        "--out", str(store), "--manifest", str(manifest),
    ]) == 0
    with StarStore.open(store) as catalogue:
        stars = {star.id: star for star in catalogue.query_box(QueryBox(0, 360, -90, 90))}
    assert len(stars) == 12
    assert stars["HIP 32349"].magnitude == -1.44
    assert stars["TYC 1-8-1"].magnitude == pytest.approx(12.146)
    assert json.loads(manifest.read_text())["processed_sha256"] == file_sha256(store)

    source = tmp_path / "index.json"
    source.write_text(json.dumps({
        "id": "western_SnT",
        "constellations": [{
            "id": "CON western_SnT CMa", "iau": "CMa", "lines": [[32349, 65474]],
        }],
    }))
    monkeypatch.setattr(stellarium_figures, "verify_source", lambda _: None)
    destination = tmp_path / "figures"
    assert main([
        "data", "import-stellarium-figures", "--source", str(source),
        "--store", str(store), "--hipparcos-raw", str(bright / "hip_main.dat"),
        "--dest", str(destination),
    ]) == 0
    geometry = json.loads((destination / "constellations.lines.json").read_text())
    coordinates = geometry["features"][0]["geometry"]["coordinates"][0]
    assert coordinates == [
        [stars["HIP 32349"].ra_deg, stars["HIP 32349"].dec_deg],
        [stars["HIP 65474"].ra_deg, stars["HIP 65474"].dec_deg],
    ]


def test_wds_import_cli_preserves_semantic_overlay(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "wds.dat.gz").write_bytes(gzip.compress(
        (FIXTURES / "double_stars/wds_subset.dat").read_bytes(), mtime=0,
    ))
    output, manifest = tmp_path / "wds.json", tmp_path / "wds.manifest.json"
    assert main([
        "data", "import-wds", "--raw", str(raw), "--out", str(output),
        "--manifest", str(manifest),
    ]) == 0
    systems = load_system_catalog(output)
    assert len(systems) == 9
    assert any(system.source_id == "STF2383:CD" for system in systems)
    assert json.loads(manifest.read_text())["processed_sha256"] == file_sha256(output)


def test_import_cli_reports_missing_input_without_writing_output(tmp_path: Path, capsys) -> None:
    output = tmp_path / "catalogue.json"
    assert main([
        "data", "import-openngc", "--raw", str(tmp_path / "missing"), "--out", str(output),
    ]) == 1
    assert "fetch-openngc" in capsys.readouterr().err
    assert not output.exists()
