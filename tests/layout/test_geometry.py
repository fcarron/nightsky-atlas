"""Tests for geometric primitives."""

from __future__ import annotations

import pytest

from nightsky_atlas.chart.page import PagePoint, PageRect
from nightsky_atlas.layout.geometry import (
    circle_intersects_rect,
    clamp_point_to_rect,
    expand_rect,
    point_in_rect,
    rect_distance_mm,
    rect_overlap_area_mm2,
    rects_overlap,
    segment_intersects_rect,
    split_segment_at_rect,
)

A = PageRect(left_mm=10.0, top_mm=10.0, width_mm=10.0, height_mm=10.0)


def test_point_in_rect() -> None:
    assert point_in_rect(PagePoint(15.0, 15.0), A)
    assert not point_in_rect(PagePoint(5.0, 15.0), A)


def test_rects_overlap() -> None:
    overlapping = PageRect(15.0, 15.0, 10.0, 10.0)
    touching = PageRect(20.0, 10.0, 5.0, 5.0)
    separate = PageRect(30.0, 30.0, 5.0, 5.0)
    assert rects_overlap(A, overlapping)
    assert rects_overlap(A, touching)
    assert not rects_overlap(A, separate)


def test_overlap_area() -> None:
    overlapping = PageRect(15.0, 15.0, 10.0, 10.0)
    assert rect_overlap_area_mm2(A, overlapping) == pytest.approx(25.0)
    assert rect_overlap_area_mm2(A, PageRect(30.0, 30.0, 5.0, 5.0)) == 0.0


def test_rect_distance() -> None:
    assert rect_distance_mm(A, PageRect(15.0, 15.0, 5.0, 5.0)) == 0.0
    assert rect_distance_mm(A, PageRect(20.0, 10.0, 5.0, 5.0)) == 0.0
    assert rect_distance_mm(A, PageRect(13.0, 30.0, 5.0, 5.0)) == pytest.approx(10.0)


def test_clamp_point() -> None:
    assert clamp_point_to_rect(PagePoint(0.0, 0.0), A) == PagePoint(10.0, 10.0)
    assert clamp_point_to_rect(PagePoint(15.0, 15.0), A) == PagePoint(15.0, 15.0)


def test_circle_intersects_rect() -> None:
    assert circle_intersects_rect(PagePoint(15.0, 15.0), 1.0, A)
    assert circle_intersects_rect(PagePoint(8.0, 15.0), 3.0, A)
    assert not circle_intersects_rect(PagePoint(0.0, 0.0), 3.0, A)


def test_segment_knockout_uses_expanded_label_bounds() -> None:
    bounds = expand_rect(PageRect(4.0, 4.0, 2.0, 2.0), 0.5)
    start, end = PagePoint(0.0, 5.0), PagePoint(10.0, 5.0)
    assert segment_intersects_rect(start, end, bounds)
    parts = split_segment_at_rect(start, end, bounds)
    assert [(part[0].x_mm, part[1].x_mm) for part in parts] == [(0.0, 3.5), (6.5, 10.0)]
