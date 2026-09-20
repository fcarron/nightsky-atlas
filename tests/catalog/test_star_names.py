"""Tests for the star-name lookup."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nightsky_atlas.catalog.star_names import StarName, hip_number, load_star_names

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "data" / "fixtures" / "starnames"


def test_committed_fixture_loads() -> None:
    names = load_star_names(FIXTURE_DIR)
    assert len(names) > 4000
    deneb = names[102098]
    assert deneb.name == "Deneb"
    assert deneb.bayer == "α"
    assert deneb.flamsteed == "50"
    assert deneb.constellation == "Cyg"
    assert deneb.display_text() == "Deneb"


def test_display_text_precedence() -> None:
    assert StarName(1, name="Thing", bayer="α", constellation="Cyg").display_text() == "Thing"
    assert StarName(1, bayer="α", constellation="Cyg").display_text() == "α Cyg"
    assert StarName(1, flamsteed="50", constellation="Cyg").display_text() == "50 Cyg"
    assert StarName(1, variable="V", constellation="Cyg").display_text() == "V Cyg"
    assert StarName(1).display_text() is None


def test_hip_number_parses_forms() -> None:
    assert hip_number("HIP 102098") == 102098
    assert hip_number("HIP\u2009102098") == 102098
    assert hip_number(None) is None
    assert hip_number("TYC 1-1-1") is None


def test_missing_directory_is_empty() -> None:
    assert load_star_names(FIXTURE_DIR / "nope") == {}


def test_malformed_fixture_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "starnames.json").write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="root"):
        load_star_names(tmp_path)


def test_non_numeric_key_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "starnames.json").write_text(
        json.dumps({"not-a-number": {"name": "X"}}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="non-numeric"):
        load_star_names(tmp_path)


def test_curated_duplicate_preferred_name_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "starnames.json").write_text(
        json.dumps({"1": {}, "2": {}}), encoding="utf-8"
    )
    (tmp_path / "curated.yaml").write_text(
        "source: test\n"
        "proper_names:\n"
        "  core: [{hip: 1, name: Same}, {hip: 2, name: Same}]\n"
        "  standard: []\n"
        "  extended: []\n"
        "variables: []\n"
        "preferred_designations: []\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate curated name"):
        load_star_names(tmp_path)
