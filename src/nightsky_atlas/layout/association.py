"""Shared rendered source geometry for deterministic label ownership."""

from __future__ import annotations

import math
from dataclasses import dataclass

from nightsky_atlas.atlas.config import StyleConfig
from nightsky_atlas.catalog.models import DsoType
from nightsky_atlas.chart.page import PagePoint, PageRect, PageTransform
from nightsky_atlas.layout.geometry import clamp_point_to_rect, segment_intersects_rect
from nightsky_atlas.render.symbols import dso_symbol_extent
from nightsky_atlas.scene.models import ChartScene

__all__ = [
    "SourceGeometry",
    "dso_source_geometries",
    "source_contains_point",
    "source_edge_distance",
    "source_extent_edge_distance",
    "source_facing_point",
]


@dataclass(frozen=True, slots=True)
class SourceGeometry:
    """The physical geometry a reader associates with one DSO label."""

    id: str
    source_type: DsoType
    center: PagePoint
    radius_x_mm: float
    radius_y_mm: float
    rotation_rad: float = 0.0
    outline_paths: tuple[tuple[PagePoint, ...], ...] = ()
    ignore_interior_stars: bool = False

    @property
    def collision_radius_mm(self) -> float:
        return max(self.radius_x_mm, self.radius_y_mm)


def dso_source_geometries(
    scene: ChartScene, transform: PageTransform, style: StyleConfig
) -> tuple[SourceGeometry, ...]:
    """Build the same ellipse/symbol/contour geometry used by the chart."""
    outlines_by_dso: dict[str, list[tuple[PagePoint, ...]]] = {}
    for outline in scene.nebula_outlines:
        outlines_by_dso.setdefault(outline.dso_id, []).append(
            tuple(transform.to_page(point) for point in outline.points)
        )
    geometries: list[SourceGeometry] = []
    for scene_dso in scene.deep_sky_objects:
        extent = dso_symbol_extent(
            scene_dso.dso,
            mm_per_deg=transform.mm_per_deg,
            style=style,
        )
        geometries.append(
            SourceGeometry(
                id=scene_dso.dso.id,
                source_type=scene_dso.dso.object_type,
                center=transform.to_page(scene_dso.chart_point),
                radius_x_mm=extent.radius_x_mm,
                radius_y_mm=extent.radius_y_mm,
                rotation_rad=extent.rotation_rad,
                outline_paths=tuple(outlines_by_dso.get(scene_dso.dso.id, ())),
                ignore_interior_stars=scene_dso.dso.object_type == DsoType.OPEN_CLUSTER,
            )
        )
    return tuple(geometries)


def source_edge_distance(source: SourceGeometry, rect: PageRect) -> float:
    """Measure from the rendered source boundary to its facing label edge."""
    if source.outline_paths:
        return min(
            _segment_rect_distance(start, end, rect)
            for path in source.outline_paths
            for start, end in zip(path, path[1:], strict=False)
        )
    return source_extent_edge_distance(source, rect)


def source_extent_edge_distance(source: SourceGeometry, rect: PageRect) -> float:
    """Fast ellipse/symbol distance, intentionally ignoring detailed contours."""
    return _point_rect_distance(_ellipse_facing_point(source, rect), rect)


def source_facing_point(source: SourceGeometry, rect: PageRect) -> PagePoint:
    """Return the point on the source boundary facing the label rectangle."""
    target = rect.center
    if source.outline_paths:
        return min(
            (
                _closest_point_on_segment(target, start, end)
                for path in source.outline_paths
                for start, end in zip(path, path[1:], strict=False)
            ),
            key=lambda point: _point_distance(point, target),
        )
    return _ellipse_facing_point(source, rect)


def _ellipse_facing_point(source: SourceGeometry, rect: PageRect) -> PagePoint:
    target = rect.center
    dx = target.x_mm - source.center.x_mm
    dy = target.y_mm - source.center.y_mm
    cos_angle = math.cos(source.rotation_rad)
    sin_angle = math.sin(source.rotation_rad)
    local_x = dx * cos_angle + dy * sin_angle
    local_y = -dx * sin_angle + dy * cos_angle
    denominator = math.sqrt(
        (local_x / source.radius_x_mm) ** 2 + (local_y / source.radius_y_mm) ** 2
    )
    if denominator <= 0.0:
        return source.center
    scale = 1.0 / denominator
    boundary_x = local_x * scale
    boundary_y = local_y * scale
    return PagePoint(
        source.center.x_mm + boundary_x * cos_angle - boundary_y * sin_angle,
        source.center.y_mm + boundary_x * sin_angle + boundary_y * cos_angle,
    )


def source_contains_point(source: SourceGeometry, point: PagePoint) -> bool:
    """Return whether a point belongs to the rendered source footprint."""
    dx = point.x_mm - source.center.x_mm
    dy = point.y_mm - source.center.y_mm
    cos_angle = math.cos(source.rotation_rad)
    sin_angle = math.sin(source.rotation_rad)
    local_x = dx * cos_angle + dy * sin_angle
    local_y = -dx * sin_angle + dy * cos_angle
    return (
        (local_x / source.radius_x_mm) ** 2 + (local_y / source.radius_y_mm) ** 2
        <= 1.0
    )


def _point_distance(first: PagePoint, second: PagePoint) -> float:
    return math.hypot(first.x_mm - second.x_mm, first.y_mm - second.y_mm)


def _point_rect_distance(point: PagePoint, rect: PageRect) -> float:
    return _point_distance(point, clamp_point_to_rect(point, rect))


def _segment_rect_distance(start: PagePoint, end: PagePoint, rect: PageRect) -> float:
    if segment_intersects_rect(start, end, rect):
        return 0.0
    corners = (
        PagePoint(rect.left_mm, rect.top_mm),
        PagePoint(rect.right_mm, rect.top_mm),
        PagePoint(rect.right_mm, rect.bottom_mm),
        PagePoint(rect.left_mm, rect.bottom_mm),
    )
    return min(
        _point_rect_distance(start, rect),
        _point_rect_distance(end, rect),
        *(_point_segment_distance(corner, start, end) for corner in corners),
    )


def _closest_point_on_segment(point: PagePoint, start: PagePoint, end: PagePoint) -> PagePoint:
    dx = end.x_mm - start.x_mm
    dy = end.y_mm - start.y_mm
    length_sq = dx * dx + dy * dy
    if length_sq <= 0.0:
        return start
    along = max(
        0.0,
        min(1.0, ((point.x_mm - start.x_mm) * dx + (point.y_mm - start.y_mm) * dy) / length_sq),
    )
    return PagePoint(start.x_mm + along * dx, start.y_mm + along * dy)


def _point_segment_distance(point: PagePoint, start: PagePoint, end: PagePoint) -> float:
    return _point_distance(point, _closest_point_on_segment(point, start, end))
