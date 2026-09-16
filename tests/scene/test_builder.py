"""Tests for scene construction."""

from __future__ import annotations

from pathlib import Path

import pytest

from nightsky_atlas.catalog.models import DeepSkyObject, DsoType, Provenance
from nightsky_atlas.catalog.sample import load_sample_stars
from nightsky_atlas.chart.models import ChartDefinition
from nightsky_atlas.projection import ChartPoint
from nightsky_atlas.scene.builder import build_scene, build_star_scene

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "data" / "fixtures" / "stars" / "test_virgo.csv"

DEFINITION = ChartDefinition(
    id="test-virgo",
    center_ra_deg=187.5,
    center_dec_deg=12.0,
    width_deg=20.0,
    height_deg=14.0,
)

INSIDE_IDS = {f"star-00{index}" for index in range(1, 9)}
OUTSIDE_IDS = {"star-009", "star-010", "star-011", "star-012"}


def build_fixture_scene():
    return build_star_scene(DEFINITION, load_sample_stars(FIXTURE))


def test_known_fixture_star_count() -> None:
    assert build_fixture_scene().star_count == 8


def test_off_chart_stars_excluded() -> None:
    placed = {scene_star.star.id for scene_star in build_fixture_scene().stars}
    assert placed == INSIDE_IDS
    assert placed.isdisjoint(OUTSIDE_IDS)


def test_center_star_projects_to_chart_origin() -> None:
    scene = build_fixture_scene()
    center = next(item for item in scene.stars if item.star.id == "star-001")
    assert center.chart_point.xi_deg == pytest.approx(0.0, abs=1e-9)
    assert center.chart_point.eta_deg == pytest.approx(0.0, abs=1e-9)


def test_projected_positions_match_direction() -> None:
    scene = build_fixture_scene()
    by_id = {item.star.id: item.chart_point for item in scene.stars}
    assert by_id["star-003"].xi_deg > 0.0
    assert by_id["star-003"].eta_deg > 0.0
    assert by_id["star-002"].xi_deg < 0.0
    assert by_id["star-002"].eta_deg < 0.0


def test_all_projected_points_in_field() -> None:
    for scene_star in build_fixture_scene().stars:
        assert DEFINITION.contains(scene_star.chart_point)


def test_empty_input_gives_empty_scene() -> None:
    scene = build_star_scene(DEFINITION, [])
    assert scene.star_count == 0
    assert scene.definition == DEFINITION


def test_point_at_field_corner_is_inside() -> None:
    assert DEFINITION.contains(ChartPoint(10.0, 7.0))
    assert not DEFINITION.contains(ChartPoint(10.1, 7.0))


def make_dso(
    object_id: str, ra_deg: float, dec_deg: float, magnitude: float | None
) -> DeepSkyObject:
    return DeepSkyObject(
        id=object_id,
        ra_deg=ra_deg,
        dec_deg=dec_deg,
        object_type=DsoType.GALAXY,
        provenance=Provenance(catalogue="TEST", source_id=object_id),
        magnitude=magnitude,
    )


def test_build_scene_includes_only_in_field_dsos() -> None:
    dsos = [
        make_dso("d-in", 187.5, 12.0, 8.0),
        make_dso("d-out", 100.0, 40.0, 8.0),
    ]
    scene = build_scene(DEFINITION, (), dsos)
    assert scene.dso_count == 1
    assert scene.deep_sky_objects[0].dso.id == "d-in"


def test_dso_magnitude_limit_keeps_unknown_magnitudes() -> None:
    dsos = [
        make_dso("bright", 187.5, 12.0, 8.0),
        make_dso("faint", 187.6, 12.0, 14.0),
        make_dso("unknown", 187.7, 12.0, None),
    ]
    scene = build_scene(DEFINITION, (), dsos, dso_magnitude_limit=12.0)
    assert {item.dso.id for item in scene.deep_sky_objects} == {"bright", "unknown"}
