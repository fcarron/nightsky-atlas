from __future__ import annotations

import math

from nightsky_atlas.catalog.milky_way import MilkyWayContour
from nightsky_atlas.chart.models import ChartDefinition
from nightsky_atlas.scene.builder import build_scene


def test_ra_zero_wrap_projects_as_a_short_continuous_contour() -> None:
    chart = ChartDefinition("wrap", 0.0, 0.0, 4.0, 4.0)
    contour = MilkyWayContour(
        "milky-way:1:wrap",
        1,
        ((359.5, 0.0), (0.0, 0.0), (0.5, 0.0)),
    )
    scene = build_scene(chart, milky_way_contours=(contour,), milky_way_levels=(1,))
    assert scene.milky_way_contours
    points = [point for path in scene.milky_way_contours for point in path.points]
    assert max(point.xi_deg for point in points) - min(point.xi_deg for point in points) < 1.1
    assert all(abs(point.xi_deg) <= 2.0 + 1e-9 for point in points)


def test_milky_way_paths_are_clipped_to_chart_field() -> None:
    chart = ChartDefinition("clip", 180.0, 0.0, 4.0, 4.0)
    contour = MilkyWayContour(
        "milky-way:3:clip",
        3,
        ((176.0, 0.0), (179.0, 0.0), (180.0, 0.0), (181.0, 0.0), (184.0, 0.0)),
    )
    scene = build_scene(chart, milky_way_contours=(contour,), milky_way_levels=(3,))
    points = [point for path in scene.milky_way_contours for point in path.points]
    assert points
    assert all(abs(point.xi_deg) <= 2.0 + 1e-9 for point in points)
    assert any(abs(abs(point.xi_deg) - 2.0) < 1e-8 for point in points)


def test_only_configured_milky_way_levels_are_projected() -> None:
    chart = ChartDefinition("level", 0.0, 0.0, 4.0, 4.0)
    contours = (
        MilkyWayContour("milky-way:1:inside", 1, ((358.0, 0), (0, 0), (2, 0))),
        MilkyWayContour("milky-way:3:inside", 3, ((358.0, 1), (0, 1), (2, 1))),
    )
    scene = build_scene(chart, milky_way_contours=contours, milky_way_levels=(3,))
    assert scene.milky_way_contours
    assert {path.level for path in scene.milky_way_contours} == {3}


def test_empty_level_set_disables_projected_contours() -> None:
    chart = ChartDefinition("off", 0.0, 0.0, 4.0, 4.0)
    contour = MilkyWayContour("milky-way:1:off", 1, ((358.0, 0), (0, 0), (2, 0)))
    scene = build_scene(chart, milky_way_contours=(contour,), milky_way_levels=())
    assert scene.milky_way_contours == ()


def test_projected_paths_remain_finite_near_polar_chart() -> None:
    chart = ChartDefinition("polar", 0.0, 88.0, 8.0, 6.0)
    contour = MilkyWayContour(
        "milky-way:1:polar",
        1,
        ((350.0, 85.0), (0.0, 85.0), (10.0, 85.0)),
    )
    scene = build_scene(chart, milky_way_contours=(contour,), milky_way_levels=(1,))
    assert all(
        math.isfinite(point.xi_deg)
        and math.isfinite(point.eta_deg)
        for path in scene.milky_way_contours
        for point in path.points
    )
