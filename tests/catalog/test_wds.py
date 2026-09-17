"""Tests for the Washington Double Star Catalog importer."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from nightsky_atlas.catalog.models import Provenance, Star
from nightsky_atlas.catalog.systems import MatchStatus, match_star_system
from nightsky_atlas.catalog.wds import (
    FILENAME,
    iter_wds_systems,
    parse_wds_record,
    raw_path,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "data" / "fixtures" / "double_stars" / "wds_subset.dat"


def fixture_systems() -> dict[str, object]:
    return {system.source_id: system for system in iter_wds_systems(FIXTURE)}


def test_raw_path_names_the_expected_file(tmp_path: Path) -> None:
    assert raw_path(tmp_path) == tmp_path / FILENAME
    assert FILENAME.endswith(".gz")


def test_iterates_every_fixture_record() -> None:
    assert len(list(iter_wds_systems(FIXTURE))) == 9


def test_parses_albireo_pair() -> None:
    system = fixture_systems()["STFA43:AB"]
    assert system.id == "system:wds:STFA43:AB"
    assert system.source == "WDS"
    assert system.separation_arcsec == pytest.approx(34.7)
    assert system.position_angle_deg == pytest.approx(54.0)
    assert system.component_magnitudes == pytest.approx((3.19, 4.68))
    assert system.combined_magnitude == pytest.approx(2.935, abs=0.01)
    assert system.is_multiple is False
    assert system.match_status is MatchStatus.UNMATCHED
    assert system.ra_deg == pytest.approx(292.6804, abs=1e-3)
    assert system.dec_deg == pytest.approx(27.9597, abs=1e-3)


def test_negative_sentinels_become_none() -> None:
    system = fixture_systems()["RBR12:Ba,Bb"]
    assert system.separation_arcsec is None
    assert system.position_angle_deg is None
    # Ba,Bb is a sub-pair of the same primary component, not a triple system.
    assert system.is_multiple is False


def test_multiple_system_keeps_component_designation() -> None:
    system = fixture_systems()["STFA37:AB,CD"]
    assert system.is_multiple is True
    assert system.id == "system:wds:STFA37:AB,CD"
    assert system.separation_arcsec == pytest.approx(209.4)


def test_parse_returns_none_for_unusable_records() -> None:
    assert parse_wds_record("") is None
    assert parse_wds_record("not a wds record") is None


def test_albireo_links_to_primary_and_companion() -> None:
    """The Albireo fixture record matches a Tycho-like primary and companion."""
    system = fixture_systems()["STFA43:AB"]
    assert system.ra_deg is not None and system.dec_deg is not None
    separation = system.separation_arcsec or 0.0
    angle = math.radians(system.position_angle_deg or 0.0)
    dec_deg = system.dec_deg + separation / 3600.0 * math.cos(angle)
    cos_dec = math.cos(math.radians(system.dec_deg))
    ra_deg = system.ra_deg + separation / 3600.0 * math.sin(angle) / cos_dec
    primary = Star(
        id="TYC 2133-2964-1",
        ra_deg=system.ra_deg,
        dec_deg=system.dec_deg,
        magnitude=3.07,
        provenance=Provenance(catalogue="TYC2", source_id="2133-2964-1"),
    )
    companion = Star(
        id="TYC 2133-2963-1",
        ra_deg=ra_deg,
        dec_deg=dec_deg,
        magnitude=4.67,
        provenance=Provenance(catalogue="TYC2", source_id="2133-2963-1"),
    )
    matched = match_star_system(system, [primary, companion])
    assert matched.match_status is MatchStatus.POSITIONAL
    assert matched.primary_star_id == "TYC 2133-2964-1"
    assert matched.component_star_ids == ("TYC 2133-2963-1",)
    assert matched.is_safe_match is True
