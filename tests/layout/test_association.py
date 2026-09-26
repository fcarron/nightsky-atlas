"""Rendered DSO source geometry used by label placement."""

from __future__ import annotations

import pytest

from nightsky_atlas.catalog.models import DsoType
from nightsky_atlas.chart.page import PagePoint, PageRect
from nightsky_atlas.layout.association import (
    SourceGeometry,
    source_edge_distance,
    source_intersects_rect,
)
from nightsky_atlas.render.symbols import DsoShape


def test_ellipse_clearance_uses_actual_rendered_boundary() -> None:
    source = SourceGeometry(
        id="NGC1",
        source_type=DsoType.GALAXY,
        center=PagePoint(100.0, 100.0),
        radius_x_mm=4.0,
        radius_y_mm=2.0,
    )
    label = PageRect(98.0, 95.5, 4.0, 2.0)
    assert source_edge_distance(source, label) == pytest.approx(0.5, abs=0.01)


def test_ellipse_label_overlap_reports_zero_edge_gap() -> None:
    source = SourceGeometry(
        id="NGC1",
        source_type=DsoType.GALAXY,
        center=PagePoint(100.0, 100.0),
        radius_x_mm=4.0,
        radius_y_mm=2.0,
        rotation_rad=0.35,
    )
    label = PageRect(101.0, 99.0, 2.0, 1.0)
    assert source_edge_distance(source, label) == 0.0


@pytest.mark.parametrize("shape", [DsoShape.CIRCLE, DsoShape.DASHED_CIRCLE, DsoShape.SQUARE])
@pytest.mark.parametrize("rotation", [0.0, 0.35, 1.1])
def test_fast_source_intersection_matches_edge_distance(
    shape: DsoShape, rotation: float
) -> None:
    source = SourceGeometry(
        id="NGC1",
        source_type=DsoType.GALAXY,
        center=PagePoint(100.0, 100.0),
        radius_x_mm=2.0,
        radius_y_mm=1.0,
        rotation_rad=rotation,
        shape=shape,
    )
    for x in range(95, 105):
        for y in range(95, 105):
            rect = PageRect(float(x) + 0.13, float(y) + 0.21, 0.7, 0.4)
            assert source_intersects_rect(source, rect) == (
                source_edge_distance(source, rect) <= 0.0
            )


def test_contour_intersection_matches_edge_distance() -> None:
    source = SourceGeometry(
        id="NGC7000",
        source_type=DsoType.BRIGHT_NEBULA,
        center=PagePoint(100.0, 100.0),
        radius_x_mm=2.0,
        radius_y_mm=2.0,
        outline_paths=((PagePoint(98.0, 99.0), PagePoint(102.0, 101.0)),),
    )
    for rect in (PageRect(99.0, 99.0, 1.0, 1.0), PageRect(104.0, 104.0, 1.0, 1.0)):
        assert source_intersects_rect(source, rect) == (
            source_edge_distance(source, rect) <= 0.0
        )
