"""Tests for visual double/multiple star systems and their matching."""

from __future__ import annotations

from pathlib import Path

import pytest

from nightsky_atlas.catalog.models import Provenance, Star
from nightsky_atlas.catalog.systems import (
    MatchStatus,
    StarSystem,
    VisualPriority,
    combined_magnitude,
    load_system_catalog,
    match_star_system,
    match_star_systems,
    write_system_catalog,
)


def make_star(
    star_id: str,
    ra_deg: float,
    dec_deg: float,
    magnitude: float = 6.0,
) -> Star:
    return Star(
        id=star_id,
        ra_deg=ra_deg,
        dec_deg=dec_deg,
        magnitude=magnitude,
        provenance=Provenance(catalogue="TEST", source_id=star_id),
    )


def make_system(
    *,
    ra_deg: float | None = 10.0,
    dec_deg: float | None = 0.0,
    separation_arcsec: float | None = None,
    position_angle_deg: float | None = None,
    component_magnitudes: tuple[float, ...] = (),
    is_multiple: bool = False,
) -> StarSystem:
    return StarSystem(
        id="system:wds:TEST",
        source="wds",
        source_id="TEST",
        ra_deg=ra_deg,
        dec_deg=dec_deg,
        is_multiple=is_multiple,
        separation_arcsec=separation_arcsec,
        position_angle_deg=position_angle_deg,
        component_magnitudes=component_magnitudes,
        combined_magnitude=combined_magnitude(component_magnitudes),
    )


def test_combined_magnitude_of_two_components() -> None:
    assert combined_magnitude((6.0, 7.0)) == pytest.approx(5.635, abs=0.01)


def test_combined_magnitude_ignores_missing_and_handles_none() -> None:
    assert combined_magnitude((6.0, None)) == pytest.approx(6.0)
    assert combined_magnitude(()) is None
    assert combined_magnitude((None, None)) is None


def test_system_validation_rejects_bad_values() -> None:
    with pytest.raises(ValueError):
        StarSystem(id="  ", source="wds", source_id="X")
    with pytest.raises(ValueError):
        StarSystem(
            id="system:wds:X",
            source="wds",
            source_id="X",
            ra_deg=10.0,
            dec_deg=0.0,
            position_angle_deg=361.0,
        )
    with pytest.raises(ValueError):
        StarSystem(
            id="system:wds:X",
            source="wds",
            source_id="X",
            ra_deg=10.0,
            dec_deg=0.0,
            separation_arcsec=-1.0,
        )


def test_system_round_trip() -> None:
    system = StarSystem(
        id="system:wds:STF1744:AB",
        source="wds",
        source_id="STF1744:AB",
        ra_deg=200.98,
        dec_deg=54.93,
        primary_star_id="HIP 65378",
        component_star_ids=("TYC 1-1-1",),
        is_multiple=True,
        separation_arcsec=14.4,
        position_angle_deg=153.0,
        component_magnitudes=(2.23, 3.88),
        combined_magnitude=2.015,
        visual_priority=VisualPriority.NOTABLE,
        match_status=MatchStatus.POSITIONAL,
    )
    restored = StarSystem.from_dict(system.to_dict())
    assert restored == system


def test_exact_match_is_preserved() -> None:
    system = StarSystem(
        id="system:wds:X",
        source="wds",
        source_id="X",
        primary_star_id="s1",
        match_status=MatchStatus.EXACT,
    )
    matched = match_star_system(system, [])
    assert matched is system
    assert matched.is_safe_match is True


def test_positional_match_links_the_nearest_star() -> None:
    star = make_star("s1", 10.0, 0.0)
    matched = match_star_system(make_system(), [star])
    assert matched.match_status is MatchStatus.POSITIONAL
    assert matched.primary_star_id == "s1"
    assert matched.is_safe_match is True


def test_positions_outside_tolerance_are_unmatched() -> None:
    # ~36 arcsec away, well beyond the 2 arcsec primary tolerance.
    star = make_star("far", 10.01, 0.0)
    matched = match_star_system(make_system(), [star])
    assert matched.match_status is MatchStatus.UNMATCHED
    assert matched.primary_star_id is None
    assert matched.is_safe_match is False


def test_several_candidates_are_ambiguous_and_never_safe() -> None:
    stars = [make_star("a", 10.0, 0.0), make_star("b", 10.0002, 0.0)]
    matched = match_star_system(make_system(), stars)
    assert matched.match_status is MatchStatus.AMBIGUOUS
    assert matched.is_safe_match is False


def test_companion_is_linked_from_separation_and_position_angle() -> None:
    primary = make_star("a", 10.0, 0.0, magnitude=6.0)
    # 60 arcsec due east of the primary at the equator.
    companion = make_star("b", 10.0 + 60.0 / 3600.0, 0.0, magnitude=8.0)
    system = make_system(separation_arcsec=60.0, position_angle_deg=90.0)
    matched = match_star_system(system, [primary, companion])
    assert matched.match_status is MatchStatus.POSITIONAL
    assert matched.primary_star_id == "a"
    assert matched.component_star_ids == ("b",)
    assert matched.linked_star_ids() == ("a", "b")


def test_match_star_systems_reuses_one_grid() -> None:
    stars = [make_star("a", 10.0, 0.0)]
    systems = [make_system(), make_system(ra_deg=250.0, dec_deg=-40.0)]
    matched = match_star_systems(systems, stars)
    assert [system.match_status for system in matched] == [
        MatchStatus.POSITIONAL,
        MatchStatus.UNMATCHED,
    ]


def test_system_catalog_round_trip(tmp_path: Path) -> None:
    systems = [make_system(separation_arcsec=1.0, component_magnitudes=(6.0, 7.0))]
    path = tmp_path / "systems.json"
    assert write_system_catalog(path, systems) == 1
    assert load_system_catalog(path) == systems


def test_missing_system_catalog_is_empty(tmp_path: Path) -> None:
    assert load_system_catalog(tmp_path / "absent.json") == []
