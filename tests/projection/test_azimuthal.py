"""Tests for the azimuthal equidistant overview projection."""

from __future__ import annotations

import math

import pytest

from nightsky_atlas.astronomy.angles import angular_separation_deg
from nightsky_atlas.projection import (
    AzimuthalEquidistantProjection,
    ChartPoint,
    Projection,
)


def north_pole() -> AzimuthalEquidistantProjection:
    return AzimuthalEquidistantProjection(center_ra_deg=180.0, center_dec_deg=90.0)


def test_centre_maps_to_origin() -> None:
    point = north_pole().project(180.0, 90.0)
    assert point.xi_deg == pytest.approx(0.0, abs=1e-12)
    assert point.eta_deg == pytest.approx(0.0, abs=1e-12)


def test_radial_distance_equals_angular_distance() -> None:
    projection = north_pole()
    for ra, dec in ((0.0, 60.0), (90.0, 30.0), (250.0, 10.0)):
        point = projection.project(ra, dec)
        radius = math.hypot(point.xi_deg, point.eta_deg)
        expected = angular_separation_deg(180.0, 90.0, ra, dec)
        assert radius == pytest.approx(expected, rel=1e-9)


def test_equator_maps_to_radius_ninety() -> None:
    projection = north_pole()
    for ra in (0.0, 45.0, 123.0, 300.0):
        point = projection.project(ra, 0.0)
        assert math.hypot(point.xi_deg, point.eta_deg) == pytest.approx(90.0, abs=1e-9)


def test_angular_distance_matches_projected_radius() -> None:
    projection = north_pole()
    for ra, dec in ((10.0, 80.0), (200.0, -20.0)):
        point = projection.project(ra, dec)
        assert projection.angular_distance_deg(ra, dec) == pytest.approx(
            math.hypot(point.xi_deg, point.eta_deg), abs=1e-9
        )


def test_hemisphere_is_inside_radius_ninety() -> None:
    projection = north_pole()
    inside = projection.project(123.0, 15.0)
    outside = projection.project(123.0, -15.0)
    assert math.hypot(inside.xi_deg, inside.eta_deg) < 90.0
    assert math.hypot(outside.xi_deg, outside.eta_deg) > 90.0


def test_satisfies_projection_protocol() -> None:
    projection = north_pole()
    assert isinstance(projection, Projection)
    assert projection.name == "azimuthal_equidistant"


def test_rejects_invalid_centre() -> None:
    with pytest.raises(ValueError):
        AzimuthalEquidistantProjection(0.0, 91.0)
    with pytest.raises(ValueError):
        AzimuthalEquidistantProjection(float("nan"), 0.0)


def test_returns_chart_point() -> None:
    assert isinstance(north_pole().project(0.0, 45.0), ChartPoint)
