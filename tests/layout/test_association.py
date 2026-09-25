"""Rendered DSO source geometry used by label placement."""

from __future__ import annotations

import pytest

from nightsky_atlas.catalog.models import DsoType
from nightsky_atlas.chart.page import PagePoint, PageRect
from nightsky_atlas.layout.association import SourceGeometry, source_edge_distance


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
