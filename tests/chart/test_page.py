"""Tests for the page transform and chart clipping."""

from __future__ import annotations

import pytest

from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.chart.page import PagePoint, PageTransform
from nightsky_atlas.projection import ChartPoint

PAGE = PageGeometry(width_mm=297.0, height_mm=210.0, margin_mm=12.0)
CHART = ChartDefinition(
    id="test-virgo",
    center_ra_deg=187.5,
    center_dec_deg=12.0,
    width_deg=20.0,
    height_deg=14.0,
)


def make_transform() -> PageTransform:
    return PageTransform(chart=CHART, page=PAGE)


def test_mm_per_deg_fits_height_limited_field() -> None:
    assert make_transform().mm_per_deg == pytest.approx(186.0 / 14.0)


def test_chart_centre_maps_to_page_centre() -> None:
    transform = make_transform()
    assert transform.to_page(ChartPoint(0.0, 0.0)) == PagePoint(148.5, 105.0)


def test_north_is_up_and_east_is_left() -> None:
    transform = make_transform()
    center = transform.to_page(ChartPoint(0.0, 0.0))
    north = transform.to_page(ChartPoint(0.0, 1.0))
    east = transform.to_page(ChartPoint(1.0, 0.0))

    assert north.y_mm < center.y_mm
    assert north.x_mm == pytest.approx(center.x_mm)
    assert east.x_mm < center.x_mm
    assert east.y_mm == pytest.approx(center.y_mm)


def test_north_edge_lands_on_printable_margin() -> None:
    transform = make_transform()
    top = transform.to_page(ChartPoint(0.0, CHART.height_deg / 2.0))
    assert top.y_mm == pytest.approx(PAGE.margin_mm)


def test_chart_corners_are_on_page() -> None:
    transform = make_transform()
    corners = [
        ChartPoint(CHART.width_deg / 2.0, CHART.height_deg / 2.0),
        ChartPoint(-CHART.width_deg / 2.0, CHART.height_deg / 2.0),
        ChartPoint(CHART.width_deg / 2.0, -CHART.height_deg / 2.0),
        ChartPoint(-CHART.width_deg / 2.0, -CHART.height_deg / 2.0),
    ]
    for corner in corners:
        assert transform.chart_contains(corner)
        assert transform.page_contains(transform.to_page(corner))


def test_chart_contains_boundaries_and_outside() -> None:
    transform = make_transform()
    assert transform.chart_contains(ChartPoint(0.0, 0.0))
    assert transform.chart_contains(ChartPoint(10.0, 7.0))
    assert not transform.chart_contains(ChartPoint(10.5, 0.0))
    assert not transform.chart_contains(ChartPoint(0.0, 7.5))


def test_page_contains_boundaries_and_outside() -> None:
    transform = make_transform()
    assert transform.page_contains(PagePoint(PAGE.margin_mm, PAGE.margin_mm))
    assert transform.page_contains(PagePoint(148.5, 105.0))
    assert not transform.page_contains(PagePoint(PAGE.margin_mm - 1.0, 105.0))
    assert not transform.page_contains(PagePoint(148.5, PAGE.height_mm - PAGE.margin_mm + 1.0))


def test_rotation_is_explicitly_rejected() -> None:
    rotated = ChartDefinition(
        id="rotated",
        center_ra_deg=0.0,
        center_dec_deg=0.0,
        width_deg=10.0,
        height_deg=10.0,
        rotation_deg=5.0,
    )
    with pytest.raises(NotImplementedError):
        PageTransform(chart=rotated, page=PAGE)


def test_chart_rect_matches_scaled_field() -> None:
    transform = make_transform()
    rect = transform.chart_rect
    assert rect.width_mm == pytest.approx(CHART.width_deg * transform.mm_per_deg)
    assert rect.height_mm == pytest.approx(CHART.height_deg * transform.mm_per_deg)
    assert rect.center.x_mm == pytest.approx(148.5)
    assert rect.center.y_mm == pytest.approx(105.0)


def test_chart_rect_is_inside_printable_area() -> None:
    rect = make_transform().chart_rect
    assert rect.left_mm >= PAGE.margin_mm - 1e-9
    assert rect.top_mm >= PAGE.margin_mm - 1e-9
    assert rect.right_mm <= PAGE.width_mm - PAGE.margin_mm + 1e-9
    assert rect.bottom_mm <= PAGE.height_mm - PAGE.margin_mm + 1e-9
