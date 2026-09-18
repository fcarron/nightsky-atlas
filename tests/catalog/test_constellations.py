"""Tests for the vendored constellation geometry loader."""

from __future__ import annotations

from pathlib import Path

from nightsky_atlas.catalog.constellations import (
    CONSTELLATION_NAMES,
    constellation_name,
    load_constellations,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "data" / "fixtures" / "constellations"


def test_fixture_loads_lines_and_boundaries() -> None:
    catalogue = load_constellations(FIXTURE_DIR)
    assert catalogue.line_count > 0
    assert catalogue.boundary_count > 0
    assert catalogue.boundary_count < catalogue.line_count * 40


def test_boundaries_are_deduplicated() -> None:
    catalogue = load_constellations(FIXTURE_DIR)
    keys = set()
    for segment in catalogue.boundaries:
        start = (round(segment.ra1_deg, 3), round(segment.dec1_deg, 3))
        end = (round(segment.ra2_deg, 3), round(segment.dec2_deg, 3))
        key = (start, end) if start <= end else (end, start)
        assert key not in keys
        keys.add(key)


def test_segments_have_finite_in_range_coordinates() -> None:
    catalogue = load_constellations(FIXTURE_DIR)
    for segment in (*catalogue.lines, *catalogue.boundaries):
        assert -90.0 <= segment.dec1_deg <= 90.0
        assert -90.0 <= segment.dec2_deg <= 90.0
        assert segment.provenance.catalogue == "d3-celestial"


def test_missing_directory_yields_empty_catalogue(tmp_path: Path) -> None:
    catalogue = load_constellations(tmp_path)
    assert catalogue.line_count == 0
    assert catalogue.boundary_count == 0


def test_segments_carry_constellation_id() -> None:
    catalogue = load_constellations(FIXTURE_DIR)
    ids = {segment.constellation_id for segment in (*catalogue.lines, *catalogue.boundaries)}
    assert "And" in ids
    assert "Ori" in ids
    assert "" not in ids


def test_constellation_name_registry() -> None:
    assert constellation_name("And") == "Andromeda"
    assert constellation_name("UMa") == "Ursa Major"
    assert constellation_name("Ser") == "Serpens"
    assert constellation_name("ZZZ") == "ZZZ"
    assert len(set(CONSTELLATION_NAMES.values())) == len(CONSTELLATION_NAMES)
