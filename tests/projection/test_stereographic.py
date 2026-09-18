"""Tests for the stereographic projection."""

from __future__ import annotations

import math

import pytest

from nightsky_atlas.astronomy.angles import angular_separation_deg
from nightsky_atlas.projection import (
    ChartPoint,
    Projection,
    ProjectionError,
    StereographicProjection,
)

CENTER_RA_DEG = 187.5
CENTER_DEC_DEG = 12.0


def make_projection() -> StereographicProjection:
    return StereographicProjection(CENTER_RA_DEG, CENTER_DEC_DEG)


def radial_deg(ra_deg: float, dec_deg: float) -> float:
    separation = angular_separation_deg(CENTER_RA_DEG, CENTER_DEC_DEG, ra_deg, dec_deg)
    return math.degrees(2.0 * math.tan(math.radians(separation) / 2.0))


def test_chart_centre_maps_to_origin() -> None:
    point = make_projection().project(CENTER_RA_DEG, CENTER_DEC_DEG)
    assert point.xi_deg == pytest.approx(0.0, abs=1e-12)
    assert point.eta_deg == pytest.approx(0.0, abs=1e-12)


def test_east_offset_is_positive_xi() -> None:
    point = make_projection().project(CENTER_RA_DEG + 1.0, CENTER_DEC_DEG)
    assert point.xi_deg > 0.0
    assert math.hypot(point.xi_deg, point.eta_deg) == pytest.approx(
        radial_deg(CENTER_RA_DEG + 1.0, CENTER_DEC_DEG), rel=1e-9
    )


def test_west_offset_is_negative_xi() -> None:
    point = make_projection().project(CENTER_RA_DEG - 1.0, CENTER_DEC_DEG)
    assert point.xi_deg < 0.0
    assert math.hypot(point.xi_deg, point.eta_deg) == pytest.approx(
        radial_deg(CENTER_RA_DEG - 1.0, CENTER_DEC_DEG), rel=1e-9
    )


def test_north_offset_is_positive_eta() -> None:
    point = make_projection().project(CENTER_RA_DEG, CENTER_DEC_DEG + 1.0)
    assert point.xi_deg == pytest.approx(0.0, abs=1e-12)
    assert point.eta_deg == pytest.approx(1.0, abs=1e-3)


def test_south_offset_is_negative_eta() -> None:
    point = make_projection().project(CENTER_RA_DEG, CENTER_DEC_DEG - 1.0)
    assert point.eta_deg == pytest.approx(-1.0, abs=1e-3)


def test_offset_symmetry() -> None:
    projection = make_projection()
    east = projection.project(CENTER_RA_DEG + 3.0, CENTER_DEC_DEG)
    west = projection.project(CENTER_RA_DEG - 3.0, CENTER_DEC_DEG)
    north = projection.project(CENTER_RA_DEG, CENTER_DEC_DEG + 3.0)
    south = projection.project(CENTER_RA_DEG, CENTER_DEC_DEG - 3.0)

    assert east.xi_deg == pytest.approx(-west.xi_deg)
    assert east.eta_deg == pytest.approx(west.eta_deg)
    assert north.eta_deg == pytest.approx(-south.eta_deg)
    assert north.xi_deg == pytest.approx(south.xi_deg)


def test_radial_distance_matches_two_tan_half_c() -> None:
    for offset_deg in (0.5, 1.0, 5.0, 10.0):
        point = make_projection().project(CENTER_RA_DEG, CENTER_DEC_DEG + offset_deg)
        expected = math.degrees(2.0 * math.tan(math.radians(offset_deg) / 2.0))
        assert point.eta_deg == pytest.approx(expected, rel=1e-12)


def test_finite_over_supported_chart_fov() -> None:
    projection = make_projection()
    for delta_ra in (-15.0, -10.0, 0.0, 10.0, 15.0):
        for delta_dec in (-7.0, 0.0, 7.0):
            point = projection.project(CENTER_RA_DEG + delta_ra, CENTER_DEC_DEG + delta_dec)
            assert math.isfinite(point.xi_deg)
            assert math.isfinite(point.eta_deg)


def test_antipode_raises() -> None:
    projection = StereographicProjection(0.0, 0.0)
    with pytest.raises(ProjectionError):
        projection.project(180.0, 0.0)


def test_satisfies_projection_protocol() -> None:
    projection = make_projection()
    assert isinstance(projection, Projection)
    assert projection.name == "stereographic"


def test_rejects_invalid_centre() -> None:
    with pytest.raises(ValueError):
        StereographicProjection(0.0, 91.0)
    with pytest.raises(ValueError):
        StereographicProjection(float("nan"), 0.0)


def test_chart_point_is_hashable() -> None:
    assert ChartPoint(1.0, 2.0) == ChartPoint(1.0, 2.0)
    assert len({ChartPoint(1.0, 2.0), ChartPoint(1.0, 2.0)}) == 1


def test_inverse_round_trips_within_field() -> None:
    projection = make_projection()
    for delta_ra in (-15.0, -5.0, 0.0, 5.0, 15.0):
        for delta_dec in (-8.0, 0.0, 8.0):
            ra = (CENTER_RA_DEG + delta_ra) % 360.0
            dec = CENTER_DEC_DEG + delta_dec
            point = projection.project(ra, dec)
            ra_back, dec_back = projection.inverse(point.xi_deg, point.eta_deg)
            assert ra_back == pytest.approx(ra, abs=1e-9)
            assert dec_back == pytest.approx(dec, abs=1e-9)


def test_inverse_of_centre_is_centre() -> None:
    projection = make_projection()
    assert projection.inverse(0.0, 0.0) == pytest.approx(
        (CENTER_RA_DEG, CENTER_DEC_DEG)
    )


def test_inverse_rejects_non_finite() -> None:
    with pytest.raises(ProjectionError):
        make_projection().inverse(float("inf"), 0.0)
