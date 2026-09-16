"""Tests for star symbol sizing."""

from __future__ import annotations

from itertools import pairwise
from math import pi
from pathlib import Path

import pytest

from nightsky_atlas.atlas.config import load_style_config
from nightsky_atlas.catalog.models import DeepSkyObject, DsoType, Provenance
from nightsky_atlas.render.symbols import (
    DsoShape,
    StarSizeModel,
    dso_shape,
    galaxy_ellipse,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
STYLE = REPO_ROOT / "styles" / "standard.yaml"


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
    style = load_style_config(STYLE).star
    model = StarSizeModel.from_style(style)
    assert model.max_diameter_mm == pytest.approx(style.max_diameter_mm)
    assert model.min_diameter_mm == pytest.approx(style.min_diameter_mm)
    assert model.faint_magnitude == pytest.approx(style.faint_magnitude)


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
    geometry = galaxy_ellipse(
        make_galaxy(major_axis_arcmin=None), mm_per_deg=60.0, min_axis_mm=0.7
    )
    assert geometry is None


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
