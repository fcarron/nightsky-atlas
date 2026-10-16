"""Tests for schematic nebula outline loading."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nightsky_atlas.catalog.models import Provenance
from nightsky_atlas.catalog.outlines import (
    NebulaOutline,
    load_outlines,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "data" / "fixtures" / "outlines"


def test_committed_fixture_loads() -> None:
    outlines = load_outlines(FIXTURE_DIR)
    assert len(outlines) == 5
    ids = {outline.id for outline in outlines}
    assert "outline:dso:NGC7000" in ids
    assert "outline:dso:NGC6960" in ids
    assert all(len(outline.points) >= 3 for outline in outlines)


def test_fixture_outline_has_stable_id_and_provenance() -> None:
    by_id = {outline.id: outline for outline in load_outlines(FIXTURE_DIR)}
    north_america = by_id["outline:dso:NGC7000"]
    assert north_america.dso_id == "NGC7000"
    assert north_america.name == "North America Nebula"
    assert isinstance(north_america.provenance, Provenance)
    assert north_america.provenance.catalogue == "nightsky-atlas-authored"


def test_missing_directory_is_empty() -> None:
    assert load_outlines(FIXTURE_DIR / "does-not-exist") == ()


def test_outline_requires_three_points() -> None:
    with pytest.raises(ValueError, match="at least three"):
        NebulaOutline(
            id="outline:dso:X",
            dso_id="X",
            points=((1.0, 2.0), (3.0, 4.0)),
            provenance=Provenance(catalogue="TEST", source_id="x"),
        )


def test_outline_rejects_bad_declination() -> None:
    with pytest.raises(ValueError, match="declination"):
        NebulaOutline(
            id="outline:dso:X",
            dso_id="X",
            points=((1.0, 2.0), (3.0, 4.0), (5.0, 120.0)),
            provenance=Provenance(catalogue="TEST", source_id="x"),
        )


def test_malformed_fixture_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "nebulae.json").write_text(
        json.dumps({"outlines": [{"name": "no id", "points": [[1, 2]]}]}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="dso_id"):
        load_outlines(tmp_path)


def test_openngc_outline_import_is_repeatable_and_preserves_coordinates(tmp_path: Path) -> None:
    from nightsky_atlas.catalog.openngc_outlines import import_openngc_outlines

    source = tmp_path / "source/objects"
    source.mkdir(parents=True)
    text = "RAJ2000\tDEJ2000\tCont_Flag\n359\t-2\t\n0\t-1\t\n1\t-2\t*\n"
    (source / "NGC1499_lv2.txt").write_text(text)
    (source / "NGC1499_lv1.txt").write_text(text)
    target = tmp_path / "processed/nebulae.json"
    import_openngc_outlines(source.parent, target)
    first = target.read_bytes()
    import_openngc_outlines(source.parent, target)
    assert target.read_bytes() == first
    data = json.loads(first)
    assert data["source"]["license"] == "CC-BY-SA-4.0"
    assert data["source"]["source_url"] == "https://github.com/mattiaverga/OpenNGC"
    assert len(data["outlines"]) == 1
    assert data["outlines"][0]["id"] == "outline:openngc:NGC1499:2:0"
    assert data["outlines"][0]["points"] == [[359.0, -2.0], [0.0, -1.0], [1.0, -2.0]]
