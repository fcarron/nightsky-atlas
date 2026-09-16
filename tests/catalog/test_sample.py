"""Tests for the sample star catalogue loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from nightsky_atlas.catalog.sample import StarCatalogueError, load_sample_stars

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "data" / "fixtures" / "stars" / "test_virgo.csv"

HEADER = "id,ra_deg,dec_deg,magnitude,catalogue,source_id\n"


def test_loads_committed_fixture() -> None:
    stars = load_sample_stars(FIXTURE)
    assert len(stars) == 12
    first = stars[0]
    assert first.id == "star-001"
    assert first.ra_deg == pytest.approx(187.5)
    assert first.dec_deg == pytest.approx(12.0)
    assert first.magnitude == pytest.approx(3.5)
    assert first.provenance.catalogue == "FIXTURE"
    assert first.provenance.source_id == "F-001"


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(StarCatalogueError):
        load_sample_stars(tmp_path / "nope.csv")


def test_missing_column_raises(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text("id,ra_deg,dec_deg\nstar-001,10.0,5.0\n", encoding="utf-8")
    with pytest.raises(StarCatalogueError) as excinfo:
        load_sample_stars(path)
    assert "magnitude" in str(excinfo.value)


def test_malformed_row_reports_line(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text(
        HEADER + "star-001,187.5,not-a-number,3.5,FIXTURE,F-001\n",
        encoding="utf-8",
    )
    with pytest.raises(StarCatalogueError) as excinfo:
        load_sample_stars(path)
    assert ":2" in str(excinfo.value)


def test_empty_catalogue_raises(tmp_path: Path) -> None:
    path = tmp_path / "empty.csv"
    path.write_text(HEADER, encoding="utf-8")
    with pytest.raises(StarCatalogueError):
        load_sample_stars(path)
