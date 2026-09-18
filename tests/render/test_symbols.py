"""Tests for star and deep-sky symbol sizing."""

from __future__ import annotations

from itertools import pairwise
from math import pi
from pathlib import Path

import pytest

from nightsky_atlas.atlas.config import load_style_config
from nightsky_atlas.catalog.models import DeepSkyObject, DsoType, Provenance
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.chart.page import PageRect, PageTransform
from nightsky_atlas.layout.collision import IssueType, find_hard_violations
from nightsky_atlas.layout.labels import _exclusion_radius_mm
from nightsky_atlas.layout.models import CompassPosition, Label, LabelCandidate
from nightsky_atlas.layout.optimizer import _symbol_circles
from nightsky_atlas.render.symbols import (
    CIRCLE_CROSS_REACH_FACTOR,
    SPOKED_CIRCLE_INNER_FACTOR,
    SPOKED_CIRCLE_OUTER_FACTOR,
    DsoShape,
    StarSizeModel,
    dso_shape,
    dso_symbol_extent,
    galaxy_ellipse,
)
from nightsky_atlas.scene.builder import build_scene

REPO_ROOT = Path(__file__).resolve().parents[2]
STYLE_PATH = REPO_ROOT / "styles" / "standard.yaml"
STYLE = load_style_config(STYLE_PATH)
CHART = ChartDefinition(
    id="test", center_ra_deg=187.5, center_dec_deg=12.0, width_deg=20.0, height_deg=14.0
)
PAGE = PageGeometry(width_mm=297.0, height_mm=210.0, margin_mm=12.0)
TRANSFORM = PageTransform(chart=CHART, page=PAGE)


def make_model(**overrides: float) -> StarSizeModel:
    values = {
        "min_diameter_mm": 0.2,
        "max_diameter_mm": 1.6,
        "bright_magnitude": 0.0,
        "faint_magnitude": 10.0,
    }
    values.update(overrides)
    return StarSizeModel(**values)


def test_from_style_matches_configuration() -> None:
    style = load_style_config(STYLE_PATH).star
    model = StarSizeModel.from_style(style)
    assert model.max_diameter_mm == pytest.approx(style.max_diameter_mm)
    assert model.min_diameter_mm == pytest.approx(style.min_diameter_mm)
    assert model.faint_magnitude == pytest.approx(style.faint_magnitude)


@pytest.mark.parametrize(
    ("edition", "magnitude_limit", "mag_six_diameter_mm"),
    (("pocket", 7.5, 0.65), ("standard", 9.0, 1.10), ("deep", 10.0, 0.85)),
)
def test_edition_star_curves_are_calibrated(
    edition: str, magnitude_limit: float, mag_six_diameter_mm: float
) -> None:
    style = load_style_config(REPO_ROOT / "styles" / f"{edition}.yaml")
    model = StarSizeModel.from_style(style.star)

    assert style.star.faint_magnitude == pytest.approx(magnitude_limit)
    assert model.diameter_mm(6.0) == pytest.approx(mag_six_diameter_mm)
    assert model.diameter_mm(style.star.diameter_curve[0][0] - 1.0) == pytest.approx(
        style.star.diameter_curve[0][1]
    )
    assert model.diameter_mm(style.star.faint_magnitude + 1.0) == pytest.approx(
        style.star.diameter_curve[-1][1]
    )

    magnitudes = [value / 10.0 for value in range(-10, int((magnitude_limit + 2.0) * 10))]
    diameters = [model.diameter_mm(magnitude) for magnitude in magnitudes]
    assert all(later <= earlier + 1e-12 for earlier, later in pairwise(diameters))


def test_star_diameter_is_a_physical_circle() -> None:
    model = StarSizeModel.from_style(STYLE.star)
    diameter = model.diameter_mm(6.0)
    assert model.radius_mm(6.0) * 2.0 == pytest.approx(diameter)


def test_bright_and_faint_are_clamped() -> None:
    model = make_model()
    assert model.diameter_mm(-1.0) == pytest.approx(1.6)
    assert model.diameter_mm(0.0) == pytest.approx(1.6)
    assert model.diameter_mm(10.0) == pytest.approx(0.2)
    assert model.diameter_mm(15.0) == pytest.approx(0.2)


def test_midpoint_is_linear() -> None:
    model = make_model()
    assert model.diameter_mm(5.0) == pytest.approx((1.6 + 0.2) / 2.0)


def test_monotonic_non_increasing_with_faintness() -> None:
    model = make_model()
    magnitudes = [value / 10.0 for value in range(-20, 140)]
    diameters = [model.diameter_mm(magnitude) for magnitude in magnitudes]
    for earlier, later in pairwise(diameters):
        assert later <= earlier + 1e-12


@pytest.mark.parametrize(
    "overrides",
    [
        {"min_diameter_mm": 0.0},
        {"max_diameter_mm": 0.1, "min_diameter_mm": 0.2},
        {"bright_magnitude": 10.0, "faint_magnitude": 10.0},
        {"bright_magnitude": 12.0, "faint_magnitude": 3.0},
    ],
)
def test_invalid_model_rejected(overrides: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        make_model(**overrides)


def make_galaxy(
    *,
    position_angle_deg: float | None = 0.0,
    major_axis_arcmin: float | None = 2.0,
    minor_axis_arcmin: float | None = 1.0,
) -> DeepSkyObject:
    return DeepSkyObject(
        id="NGC0001",
        ra_deg=10.0,
        dec_deg=10.0,
        object_type=DsoType.GALAXY,
        provenance=Provenance(catalogue="TEST", source_id="NGC0001"),
        major_axis_arcmin=major_axis_arcmin,
        minor_axis_arcmin=minor_axis_arcmin,
        position_angle_deg=position_angle_deg,
    )


def test_galaxy_ellipse_true_scale() -> None:
    geometry = galaxy_ellipse(make_galaxy(), mm_per_deg=60.0, min_axis_mm=0.7)
    assert geometry is not None
    assert geometry.major_mm == pytest.approx(2.0)
    assert geometry.minor_mm == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("position_angle_deg", "expected_direction"),
    [(0.0, (0.0, -1.0)), (90.0, (-1.0, 0.0)), (180.0, (0.0, 1.0))],
)
def test_galaxy_position_angle_page_direction(
    position_angle_deg: float, expected_direction: tuple[float, float]
) -> None:
    geometry = galaxy_ellipse(
        make_galaxy(position_angle_deg=position_angle_deg), mm_per_deg=60.0, min_axis_mm=0.7
    )
    assert geometry is not None
    assert geometry.major_axis_direction[0] == pytest.approx(expected_direction[0], abs=1e-9)
    assert geometry.major_axis_direction[1] == pytest.approx(expected_direction[1], abs=1e-9)


def test_galaxy_minimum_printable_size_preserves_ratio() -> None:
    geometry = galaxy_ellipse(
        make_galaxy(major_axis_arcmin=0.01, minor_axis_arcmin=0.005),
        mm_per_deg=60.0,
        min_axis_mm=0.7,
    )
    assert geometry is not None
    assert geometry.major_mm == pytest.approx(0.7)
    assert geometry.minor_mm == pytest.approx(0.35)


def test_galaxy_maximum_size_caps_both_axes() -> None:
    geometry = galaxy_ellipse(
        make_galaxy(major_axis_arcmin=200.0, minor_axis_arcmin=100.0),
        mm_per_deg=60.0,
        min_axis_mm=0.7,
        max_axis_mm=12.0,
    )
    assert geometry is not None
    assert geometry.major_mm == pytest.approx(12.0)
    assert geometry.minor_mm == pytest.approx(6.0)


def test_galaxy_without_axes_has_no_ellipse() -> None:
    geometry = galaxy_ellipse(make_galaxy(major_axis_arcmin=None), mm_per_deg=60.0, min_axis_mm=0.7)
    assert geometry is None


def test_decorative_symbol_reach_stays_within_extent() -> None:
    # The drawn symbol must never exceed the SymbolExtent that label exclusion
    # and collision detection consume (AGENTS.md section 12).
    assert CIRCLE_CROSS_REACH_FACTOR <= 1.0
    assert SPOKED_CIRCLE_INNER_FACTOR == 1.0
    assert SPOKED_CIRCLE_OUTER_FACTOR > 1.0


@pytest.mark.parametrize(
    ("object_type", "expected"),
    [
        (DsoType.OPEN_CLUSTER, DsoShape.DASHED_CIRCLE),
        (DsoType.GLOBULAR_CLUSTER, DsoShape.CIRCLE_CROSS),
        (DsoType.PLANETARY_NEBULA, DsoShape.SPOKED_CIRCLE),
        (DsoType.BRIGHT_NEBULA, DsoShape.DASHED_SQUARE),
        (DsoType.GALAXY_CLUSTER, DsoShape.SQUARE),
    ],
)
def test_dso_shape_mapping(object_type: DsoType, expected: DsoShape) -> None:
    assert dso_shape(object_type) == expected


def test_galaxy_rotation_is_axis_angle() -> None:
    geometry = galaxy_ellipse(make_galaxy(position_angle_deg=0.0), mm_per_deg=60.0, min_axis_mm=0.7)
    assert geometry is not None
    assert geometry.rotation_rad == pytest.approx(-pi / 2.0)


def make_dso(
    object_type: DsoType,
    *,
    major_axis_arcmin: float | None = None,
    minor_axis_arcmin: float | None = None,
    position_angle_deg: float | None = 0.0,
    object_id: str = "NGC0001",
) -> DeepSkyObject:
    return DeepSkyObject(
        id=object_id,
        ra_deg=CHART.center_ra_deg,
        dec_deg=CHART.center_dec_deg,
        object_type=object_type,
        provenance=Provenance(catalogue="TEST", source_id=object_id),
        major_axis_arcmin=major_axis_arcmin,
        minor_axis_arcmin=minor_axis_arcmin,
        position_angle_deg=position_angle_deg,
    )


def extent_for(dso: DeepSkyObject, *, mm_per_deg: float = 10.0):
    return dso_symbol_extent(dso, mm_per_deg=mm_per_deg, style=STYLE)


@pytest.mark.parametrize(
    ("arcmin", "expected_mm"),
    [
        (5.0, 1.4),
        (10.0, 1.6667),
        (20.0, 3.3333),
        (36.0, 6.0),
    ],
)
def test_globular_cluster_uses_angular_diameter(arcmin: float, expected_mm: float) -> None:
    extent = extent_for(make_dso(DsoType.GLOBULAR_CLUSTER, major_axis_arcmin=arcmin))
    assert extent.uses_angular_size is True
    assert extent.shape == DsoShape.CIRCLE_CROSS
    assert extent.width_mm == pytest.approx(expected_mm, abs=1e-3)
    assert extent.height_mm == pytest.approx(expected_mm, abs=1e-3)


def test_globular_cluster_falls_back_without_size() -> None:
    extent = extent_for(make_dso(DsoType.GLOBULAR_CLUSTER))
    assert extent.uses_angular_size is False
    assert extent.width_mm == pytest.approx(STYLE.dso.globular_cluster.fallback_diameter_mm)


def test_globular_cluster_uses_minor_axis_when_major_missing() -> None:
    extent = extent_for(make_dso(DsoType.GLOBULAR_CLUSTER, minor_axis_arcmin=10.0))
    assert extent.uses_angular_size is True
    assert extent.width_mm == pytest.approx(10.0 / 60.0 * 10.0)


def test_globular_cluster_rejects_implausible_size() -> None:
    extent = extent_for(make_dso(DsoType.GLOBULAR_CLUSTER, major_axis_arcmin=5000.0))
    assert extent.uses_angular_size is False
    assert extent.width_mm == pytest.approx(STYLE.dso.globular_cluster.fallback_diameter_mm)


@pytest.mark.parametrize(
    ("arcmin", "expected_mm"),
    [
        (3.0, 1.8),
        (60.0, 10.0),
        (95.0, 15.8333),
        (110.0, 18.3333),
    ],
)
def test_open_cluster_uses_angular_diameter(arcmin: float, expected_mm: float) -> None:
    extent = extent_for(make_dso(DsoType.OPEN_CLUSTER, major_axis_arcmin=arcmin))
    assert extent.uses_angular_size is True
    assert extent.shape == DsoShape.DASHED_CIRCLE
    assert extent.width_mm == pytest.approx(expected_mm, abs=1e-3)


def test_open_cluster_maximum_size_caps_extent() -> None:
    extent = extent_for(make_dso(DsoType.OPEN_CLUSTER, major_axis_arcmin=330.0))
    assert extent.width_mm == pytest.approx(STYLE.dso.open_cluster.max_diameter_mm)


def test_planetary_nebula_uses_angular_diameter_and_includes_outer_spokes() -> None:
    extent = extent_for(make_dso(DsoType.PLANETARY_NEBULA, major_axis_arcmin=30.0))
    assert extent.uses_angular_size is True
    assert extent.width_mm == pytest.approx(30.0 / 60.0 * 10.0 * SPOKED_CIRCLE_OUTER_FACTOR)


def test_galaxy_extent_matches_true_scale() -> None:
    extent = extent_for(make_galaxy(major_axis_arcmin=2.0, minor_axis_arcmin=1.0), mm_per_deg=60.0)
    assert extent.uses_angular_size is True
    assert extent.shape == DsoShape.CIRCLE
    assert extent.is_elliptical is True
    assert extent.width_mm == pytest.approx(2.4)
    assert extent.height_mm == pytest.approx(1.2)
    assert extent.rotation_rad == pytest.approx(-pi / 2.0)


def test_galaxy_without_axes_uses_fallback_circle() -> None:
    extent = extent_for(make_galaxy(major_axis_arcmin=None))
    assert extent.uses_angular_size is False
    assert extent.is_elliptical is False
    assert extent.width_mm == pytest.approx(STYLE.dso.galaxy.fallback_diameter_mm)


def test_galaxy_minimum_axis_is_preserved() -> None:
    extent = extent_for(
        make_galaxy(major_axis_arcmin=0.01, minor_axis_arcmin=0.005), mm_per_deg=60.0
    )
    assert extent.height_mm == pytest.approx(STYLE.dso.galaxy.min_minor_axis_mm)
    assert extent.width_mm == pytest.approx(STYLE.dso.galaxy.min_minor_axis_mm * 2.0)


def test_galaxy_minimum_minor_axis_preserves_ratio() -> None:
    geometry = galaxy_ellipse(
        make_galaxy(major_axis_arcmin=0.01, minor_axis_arcmin=0.005),
        mm_per_deg=60.0,
        min_axis_mm=0.7,
        min_minor_axis_mm=1.2,
    )
    assert geometry is not None
    assert geometry.minor_mm == pytest.approx(1.2)
    assert geometry.major_mm == pytest.approx(2.4)


@pytest.mark.parametrize(
    ("edition", "globular_mm", "open_cluster_mm", "diffuse_mm", "galaxy_minor_mm"),
    (
        ("pocket", 1.2, 1.6, 1.8, 1.0),
        ("standard", 1.4, 1.8, 2.0, 1.2),
        ("deep", 1.1, 1.4, 1.6, 1.0),
    ),
)
def test_edition_dso_print_minima(
    edition: str,
    globular_mm: float,
    open_cluster_mm: float,
    diffuse_mm: float,
    galaxy_minor_mm: float,
) -> None:
    style = load_style_config(REPO_ROOT / "styles" / f"{edition}.yaml")
    assert style.dso.globular_cluster.min_diameter_mm == pytest.approx(globular_mm)
    assert style.dso.planetary_nebula.min_diameter_mm == pytest.approx(globular_mm)
    assert style.dso.open_cluster.min_diameter_mm == pytest.approx(open_cluster_mm)
    assert style.dso.bright_nebula.min_diameter_mm == pytest.approx(diffuse_mm)
    assert style.dso.galaxy_cluster.min_diameter_mm == pytest.approx(diffuse_mm)
    assert style.dso.galaxy.min_minor_axis_mm == pytest.approx(galaxy_minor_mm)


def test_true_dso_angular_extent_wins_over_edition_minimum() -> None:
    style = load_style_config(REPO_ROOT / "styles" / "deep.yaml")
    dso = make_dso(DsoType.OPEN_CLUSTER, major_axis_arcmin=30.0)
    extent = dso_symbol_extent(dso, mm_per_deg=20.0, style=style)
    assert extent.uses_angular_size is True
    assert extent.width_mm == pytest.approx(10.0)


def test_extent_shared_by_label_exclusion_and_optimizer() -> None:
    dso = make_dso(DsoType.GLOBULAR_CLUSTER, major_axis_arcmin=20.0)
    scene = build_scene(CHART, (), [dso])
    extent = dso_symbol_extent(dso, mm_per_deg=TRANSFORM.mm_per_deg, style=STYLE)

    assert _exclusion_radius_mm(dso, TRANSFORM, STYLE) == pytest.approx(extent.collision_radius_mm)
    circles = _symbol_circles(scene, TRANSFORM, STYLE)
    assert len(circles) == 1
    assert circles[0].radius_mm == pytest.approx(extent.collision_radius_mm)


def test_collision_detection_uses_real_symbol_extent() -> None:
    dso = make_dso(DsoType.GLOBULAR_CLUSTER, major_axis_arcmin=30.0)
    scene = build_scene(CHART, (), [dso])
    extent = dso_symbol_extent(dso, mm_per_deg=TRANSFORM.mm_per_deg, style=STYLE)
    center = TRANSFORM.center_page
    radius = extent.collision_radius_mm

    def label_at(left_mm: float) -> Label:
        bounds = PageRect(
            left_mm=left_mm,
            top_mm=center.y_mm - 1.0,
            width_mm=8.0,
            height_mm=2.0,
        )
        candidate = LabelCandidate(
            id="label:x:N",
            position=CompassPosition.N,
            anchor=center,
            bounds=bounds,
        )
        return Label(
            id="label:x",
            target_id=dso.id,
            text="X",
            priority=50,
            mandatory=True,
            candidates=(candidate,),
        )

    outside = find_hard_violations((label_at(center.x_mm + radius + 0.5),), scene, TRANSFORM, STYLE)
    assert IssueType.LABEL_DSO not in {issue.issue_type for issue in outside}

    inside = find_hard_violations((label_at(center.x_mm + radius - 0.5),), scene, TRANSFORM, STYLE)
    assert IssueType.LABEL_DSO in {issue.issue_type for issue in inside}
