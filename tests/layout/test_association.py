"""Rendered DSO source geometry used by label placement."""

from __future__ import annotations

import math

import pytest

from nightsky_atlas.catalog.models import DsoType
from nightsky_atlas.chart.page import PagePoint, PageRect
from nightsky_atlas.layout.association import (
    SourceGeometry,
    _segment_rect_distance,
    nearest_source_geometry,
    source_edge_distance,
    source_intersects_rect,
    source_outline_edge_distance,
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
    assert source_outline_edge_distance(source, label) == 0.0


def test_text_inside_ellipse_footprint_clears_its_rendered_outline() -> None:
    source = SourceGeometry(
        id="ESO056-115",
        source_type=DsoType.GALAXY,
        center=PagePoint(100.0, 100.0),
        radius_x_mm=30.0,
        radius_y_mm=18.0,
        rotation_rad=0.4,
    )
    label = PageRect(98.0, 99.0, 4.0, 2.0)

    assert source_edge_distance(source, label) == 0.0
    assert source_outline_edge_distance(source, label) > 0.0


def test_text_inside_square_footprint_clears_its_rendered_outline() -> None:
    source = SourceGeometry(
        id="cluster",
        source_type=DsoType.OPEN_CLUSTER,
        center=PagePoint(100.0, 100.0),
        radius_x_mm=15.0,
        radius_y_mm=12.0,
        shape=DsoShape.SQUARE,
    )
    label = PageRect(98.0, 99.0, 4.0, 2.0)

    assert source_edge_distance(source, label) == 0.0
    assert source_outline_edge_distance(source, label) > 0.0


@pytest.mark.parametrize("radius", [1.0, 5.0, 50.0])
@pytest.mark.parametrize(
    ("rect", "outline_gap"),
    [
        ((1.5, -0.25, 0.5, 0.5), 0.5),
        ((-0.25, -0.25, 0.5, 0.5), 1.0 - math.sqrt(0.125)),
        ((0.75, -0.1, 0.5, 0.2), 0.0),
        ((1.0, 0.0, 0.5, 0.5), 0.0),
        ((-2.0, -2.0, 4.0, 4.0), 0.0),
        ((1.2, 1.6, 0.0, 0.0), 1.0),
    ],
)
def test_circle_outline_clearance_inside_outside_and_tangent(
    radius: float, rect: tuple[float, float, float, float], outline_gap: float
) -> None:
    source = SourceGeometry(
        id="cluster",
        source_type=DsoType.OPEN_CLUSTER,
        center=PagePoint(100.0, 100.0),
        radius_x_mm=radius,
        radius_y_mm=radius,
        rotation_rad=0.7,
    )
    x, y, width, height = rect
    bounds = PageRect(100.0 + x * radius, 100.0 + y * radius, width * radius, height * radius)
    assert source_outline_edge_distance(source, bounds) == pytest.approx(
        outline_gap * radius, abs=1e-12
    )


def test_nearest_source_pruning_matches_exhaustive_geometry() -> None:
    sources = (
        SourceGeometry("circle", DsoType.OPEN_CLUSTER, PagePoint(3.0, 4.0), 2.0, 2.0),
        SourceGeometry("ellipse", DsoType.GALAXY, PagePoint(12.0, 7.0), 5.0, 0.5, 0.7),
        SourceGeometry(
            "square", DsoType.BRIGHT_NEBULA, PagePoint(-5.0, 3.0), 3.0, 1.0,
            shape=DsoShape.SQUARE,
        ),
        SourceGeometry(
            "contour", DsoType.BRIGHT_NEBULA, PagePoint(0.0, 0.0), 0.1, 0.1,
            outline_paths=((PagePoint(20.0, -5.0), PagePoint(20.0, 15.0)),),
        ),
    )
    for x in range(-10, 25, 3):
        for y in range(-10, 20, 3):
            rect = PageRect(x + 0.13, y + 0.21, 0.7, 0.4)
            expected = min(
                sources, key=lambda source: (source_edge_distance(source, rect), source.id)
            )
            assert nearest_source_geometry(sources, rect) is expected, (x, y)
    assert nearest_source_geometry(sources, PageRect(20.1, 0.0, 0.2, 0.2)).id == "contour"


def test_nearest_source_preserves_stable_ties_and_empty_inputs() -> None:
    first = SourceGeometry("A", DsoType.GALAXY, PagePoint(0.0, 0.0), 1.0, 1.0)
    second = SourceGeometry("Z", DsoType.GALAXY, PagePoint(0.0, 0.0), 1.0, 1.0)
    rect = PageRect(3.0, 0.0, 1.0, 1.0)
    assert nearest_source_geometry((second, first), rect) is first
    assert nearest_source_geometry((), rect) is None


def test_contour_segment_pruning_matches_exhaustive_distance() -> None:
    paths = tuple(
        tuple(
            PagePoint(
                offset + (4.0 + math.sin(index * 0.7)) * math.cos(index * math.pi / 32),
                2.0 * math.sin(index * math.pi / 32),
            )
            for index in range(65)
        )
        for offset in (0.0, 20.0)
    )
    source = SourceGeometry(
        "nebulosity", DsoType.BRIGHT_NEBULA, PagePoint(0.0, 0.0), 0.1, 0.1,
        outline_paths=paths,
    )
    for x in range(-8, 29, 3):
        for y in range(-5, 6, 2):
            rect = PageRect(x + 0.11, y + 0.23, 0.8, 0.6)
            expected = min(
                _segment_rect_distance(start, end, rect)
                for path in paths
                for start, end in zip(path, path[1:], strict=False)
            )
            assert source_edge_distance(source, rect) == expected
            assert source_outline_edge_distance(source, rect) == expected


def test_empty_contour_distance_remains_an_error() -> None:
    source = SourceGeometry(
        "invalid", DsoType.BRIGHT_NEBULA, PagePoint(0.0, 0.0), 1.0, 1.0,
        outline_paths=((PagePoint(0.0, 0.0),),),
    )
    with pytest.raises(ValueError):
        source_edge_distance(source, PageRect(1.0, 1.0, 1.0, 1.0))


@pytest.mark.parametrize(
    ("angle", "intersects"),
    ((0.12, False), (0.06, True)),
)
def test_open_cluster_dash_geometry_matches_rendered_strokes(
    angle: float, intersects: bool
) -> None:
    source = SourceGeometry(
        id="Mel022",
        source_type=DsoType.OPEN_CLUSTER,
        center=PagePoint(100.0, 100.0),
        radius_x_mm=5.0,
        radius_y_mm=5.0,
        shape=DsoShape.DASHED_CIRCLE,
        dash_length_mm=0.4,
        dash_gap_mm=0.4,
        outline_width_mm=0.15,
    )
    x = 100.0 + 5.0 * math.cos(angle)
    y = 100.0 + 5.0 * math.sin(angle)
    label = PageRect(x - 0.1, y - 0.1, 0.2, 0.2)

    distance = source_outline_edge_distance(source, label)
    assert (distance == 0.0) is intersects


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
