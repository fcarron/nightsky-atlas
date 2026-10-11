"""Shared rendered source geometry for deterministic label ownership."""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

from nightsky_atlas.atlas.config import StyleConfig
from nightsky_atlas.catalog.models import DsoType
from nightsky_atlas.chart.page import PagePoint, PageRect, PageTransform
from nightsky_atlas.layout.geometry import (
    clamp_point_to_rect,
    segment_intersects_rect,
    segments_intersect,
)
from nightsky_atlas.render.symbols import DsoShape, dso_symbol_extent
from nightsky_atlas.scene.models import ChartScene

__all__ = [
    "SourceGeometry",
    "dso_source_geometries",
    "source_contains_point",
    "source_edge_distance",
    "source_outline_edge_distance",
    "source_extent_edge_distance",
    "source_facing_point",
    "source_geometries_overlap",
    "source_intersects_rect",
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
    shape: DsoShape = DsoShape.CIRCLE
    dash_length_mm: float = 0.0
    dash_gap_mm: float = 0.0
    outline_width_mm: float = 0.0

    @property
    def collision_radius_mm(self) -> float:
        if self.shape in {DsoShape.SQUARE, DsoShape.DASHED_SQUARE}:
            return math.hypot(self.radius_x_mm, self.radius_y_mm)
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
        if not scene_dso.symbol_visible:
            continue
        extent = dso_symbol_extent(
            scene_dso.dso,
            mm_per_deg=transform.mm_per_deg,
            style=style,
        )
        is_dashed_circle = extent.shape == DsoShape.DASHED_CIRCLE
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
                shape=extent.shape,
                dash_length_mm=style.dso.dash_mm if is_dashed_circle else 0.0,
                dash_gap_mm=style.dso.dash_mm if is_dashed_circle else 0.0,
                outline_width_mm=style.dso.line_width_mm,
            )
        )
    return tuple(geometries)


@lru_cache(maxsize=32768)
def source_edge_distance(source: SourceGeometry, rect: PageRect) -> float:
    """Measure from the rendered source boundary to its facing label edge."""
    if source.outline_paths:
        return min(
            _segment_rect_distance(start, end, rect)
            for path in source.outline_paths
            for start, end in zip(path, path[1:], strict=False)
        )
    if source.shape in {DsoShape.SQUARE, DsoShape.DASHED_SQUARE}:
        return _axis_aligned_rect_edge_distance(source, rect)
    return _ellipse_rect_edge_distance(source, rect)


@lru_cache(maxsize=32768)
def source_outline_edge_distance(source: SourceGeometry, rect: PageRect) -> float:
    """Measure clearance to the drawn outline, ignoring footprint containment."""
    if source.outline_paths:
        return min(
            _segment_rect_distance(start, end, rect)
            for path in source.outline_paths
            for start, end in zip(path, path[1:], strict=False)
        )
    if source.shape in {DsoShape.SQUARE, DsoShape.DASHED_SQUARE}:
        return _axis_aligned_rect_outline_distance(source, rect)
    if source.shape == DsoShape.DASHED_CIRCLE and source.dash_length_mm > 0.0:
        return _dashed_circle_rect_distance(source, rect)
    return _ellipse_rect_outline_distance(source, rect)


def _dashed_circle_rect_distance(source: SourceGeometry, rect: PageRect) -> float:
    """Measure against the actual short dash segments of an open-cluster mark."""
    radius = (source.radius_x_mm + source.radius_y_mm) / 2.0
    circumference = 2.0 * math.pi * radius
    period = source.dash_length_mm + source.dash_gap_mm
    if circumference <= 0.0 or period <= 0.0:
        return _ellipse_rect_outline_distance(source, rect)
    distance = math.inf
    dash_start = 0.0
    while dash_start < circumference:
        dash_end = min(circumference, dash_start + source.dash_length_mm)
        count = max(1, math.ceil((dash_end - dash_start) / 0.05))
        previous = _circle_point(source.center, radius, dash_start / radius)
        for index in range(1, count + 1):
            arc = dash_start + (dash_end - dash_start) * index / count
            current = _circle_point(source.center, radius, arc / radius)
            distance = min(distance, _segment_rect_distance(previous, current, rect))
            previous = current
        dash_start += period
    return max(0.0, distance - source.outline_width_mm / 2.0)


def _circle_point(center: PagePoint, radius: float, angle: float) -> PagePoint:
    return PagePoint(
        center.x_mm + radius * math.cos(angle),
        center.y_mm + radius * math.sin(angle),
    )


def source_intersects_rect(source: SourceGeometry, rect: PageRect) -> bool:
    if source.outline_paths:
        return any(
            segment_intersects_rect(start, end, rect)
            for path in source.outline_paths
            for start, end in zip(path, path[1:], strict=False)
        )
    if source.shape in {DsoShape.SQUARE, DsoShape.DASHED_SQUARE}:
        return _rectangles_overlap(_source_rect(source), rect)
    if (
        source.center.x_mm + source.collision_radius_mm < rect.left_mm
        or source.center.x_mm - source.collision_radius_mm > rect.right_mm
        or source.center.y_mm + source.collision_radius_mm < rect.top_mm
        or source.center.y_mm - source.collision_radius_mm > rect.bottom_mm
    ):
        return False
    cos_angle = math.cos(source.rotation_rad)
    sin_angle = math.sin(source.rotation_rad)

    def local(point: PagePoint) -> tuple[float, float]:
        dx = point.x_mm - source.center.x_mm
        dy = point.y_mm - source.center.y_mm
        return (
            (dx * cos_angle + dy * sin_angle) / source.radius_x_mm,
            (-dx * sin_angle + dy * cos_angle) / source.radius_y_mm,
        )

    corners = (
        PagePoint(rect.left_mm, rect.top_mm),
        PagePoint(rect.right_mm, rect.top_mm),
        PagePoint(rect.right_mm, rect.bottom_mm),
        PagePoint(rect.left_mm, rect.bottom_mm),
    )
    if (
        rect.left_mm <= source.center.x_mm <= rect.right_mm
        and rect.top_mm <= source.center.y_mm <= rect.bottom_mm
    ):
        return True
    if any(sum(value * value for value in local(corner)) <= 1.0 for corner in corners):
        return True
    for start, end in zip(corners, (*corners[1:], corners[0]), strict=False):
        x1, y1 = local(start)
        x2, y2 = local(end)
        dx, dy = x2 - x1, y2 - y1
        length_sq = dx * dx + dy * dy
        fraction = (
            0.0
            if length_sq == 0.0
            else max(0.0, min(1.0, -(x1 * dx + y1 * dy) / length_sq))
        )
        if (x1 + fraction * dx) ** 2 + (y1 + fraction * dy) ** 2 <= 1.0:
            return True
    return False


def source_extent_edge_distance(source: SourceGeometry, rect: PageRect) -> float:
    """Fast radial ellipse estimate used for broad source-ambiguity scoring."""
    if source.shape in {DsoShape.SQUARE, DsoShape.DASHED_SQUARE}:
        return _axis_aligned_rect_edge_distance(source, rect)
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
    if source.shape in {DsoShape.SQUARE, DsoShape.DASHED_SQUARE}:
        bounds = _source_rect(source)
        return clamp_point_to_rect(target, bounds)
    return _ellipse_facing_point(source, rect)


def _source_rect(source: SourceGeometry) -> PageRect:
    return PageRect(
        left_mm=source.center.x_mm - source.radius_x_mm,
        top_mm=source.center.y_mm - source.radius_y_mm,
        width_mm=2.0 * source.radius_x_mm,
        height_mm=2.0 * source.radius_y_mm,
    )


def _axis_aligned_rect_edge_distance(source: SourceGeometry, rect: PageRect) -> float:
    bounds = _source_rect(source)
    if _rectangles_overlap(bounds, rect):
        return 0.0
    dx = max(bounds.left_mm - rect.right_mm, rect.left_mm - bounds.right_mm, 0.0)
    dy = max(bounds.top_mm - rect.bottom_mm, rect.top_mm - bounds.bottom_mm, 0.0)
    return math.hypot(dx, dy)


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


def _ellipse_rect_edge_distance(source: SourceGeometry, rect: PageRect) -> float:
    """Measure true edge clearance between a rotated ellipse and rectangle.

    Intersection is tested in the ellipse's normalized unit-circle frame.
    For disjoint shapes, a sampled boundary search followed by golden-section
    refinement gives a stable sub-0.01 mm distance without adding a geometry
    dependency.
    """
    if source_intersects_rect(source, rect):
        return 0.0
    return _ellipse_rect_boundary_distance(source, rect)


def _ellipse_rect_outline_distance(source: SourceGeometry, rect: PageRect) -> float:
    return _ellipse_rect_boundary_distance(source, rect)


def _ellipse_rect_boundary_distance(source: SourceGeometry, rect: PageRect) -> float:
    cos_angle = math.cos(source.rotation_rad)
    sin_angle = math.sin(source.rotation_rad)

    def distance(angle: float) -> float:
        x = source.radius_x_mm * math.cos(angle)
        y = source.radius_y_mm * math.sin(angle)
        point = PagePoint(
            source.center.x_mm + x * cos_angle - y * sin_angle,
            source.center.y_mm + x * sin_angle + y * cos_angle,
        )
        return _point_rect_distance(point, rect)

    sample_count = 64
    step = 2.0 * math.pi / sample_count
    samples = [distance(index * step) for index in range(sample_count)]
    best_index = min(range(sample_count), key=samples.__getitem__)
    left = (best_index - 1) * step
    right = (best_index + 1) * step
    ratio = (math.sqrt(5.0) - 1.0) / 2.0
    first = right - ratio * (right - left)
    second = left + ratio * (right - left)
    first_value, second_value = distance(first), distance(second)
    for _ in range(32):
        if first_value <= second_value:
            right, second, second_value = second, first, first_value
            first = right - ratio * (right - left)
            first_value = distance(first)
        else:
            left, first, first_value = first, second, second_value
            second = left + ratio * (right - left)
            second_value = distance(second)
    return min(samples[best_index], first_value, second_value)


def _axis_aligned_rect_outline_distance(source: SourceGeometry, rect: PageRect) -> float:
    bounds = _source_rect(source)
    if not _rectangles_overlap(bounds, rect):
        dx = max(bounds.left_mm - rect.right_mm, rect.left_mm - bounds.right_mm, 0.0)
        dy = max(bounds.top_mm - rect.bottom_mm, rect.top_mm - bounds.bottom_mm, 0.0)
        return math.hypot(dx, dy)
    source_inside_label = (
        rect.left_mm <= bounds.left_mm
        and rect.right_mm >= bounds.right_mm
        and rect.top_mm <= bounds.top_mm
        and rect.bottom_mm >= bounds.bottom_mm
    )
    if source_inside_label:
        return 0.0
    label_inside_source = (
        bounds.left_mm <= rect.left_mm
        and bounds.right_mm >= rect.right_mm
        and bounds.top_mm <= rect.top_mm
        and bounds.bottom_mm >= rect.bottom_mm
    )
    if label_inside_source:
        return min(
            rect.left_mm - bounds.left_mm,
            bounds.right_mm - rect.right_mm,
            rect.top_mm - bounds.top_mm,
            bounds.bottom_mm - rect.bottom_mm,
        )
    return 0.0


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


@lru_cache(maxsize=8192)
def source_geometries_overlap(first: SourceGeometry, second: SourceGeometry) -> bool:
    """Return whether two rendered DSO footprints genuinely overlap.

    Galaxy exceptions use a deterministic polygonal approximation of the two
    rendered ellipses. Other symbols use their actual square/circular extents.
    This is deliberately local: overlap does not merge the physical objects.
    """
    if first.outline_paths or second.outline_paths:
        first_bounds = _source_rect(first)
        second_bounds = _source_rect(second)
        if not _rectangles_overlap(first_bounds, second_bounds):
            return False
        return (
            source_edge_distance(first, second_bounds) <= 0.0
            or source_edge_distance(second, first_bounds) <= 0.0
        )
    if first.source_type == DsoType.GALAXY and second.source_type == DsoType.GALAXY:
        if math.hypot(
            first.center.x_mm - second.center.x_mm,
            first.center.y_mm - second.center.y_mm,
        ) > first.collision_radius_mm + second.collision_radius_mm:
            return False
        if source_contains_point(first, second.center) or source_contains_point(
            second, first.center
        ):
            return True
        first_points = _ellipse_boundary(first)
        second_points = _ellipse_boundary(second)
        if any(source_contains_point(second, point) for point in first_points):
            return True
        if any(source_contains_point(first, point) for point in second_points):
            return True
        return any(
            segments_intersect(a, b, c, d)
            for a, b in zip(first_points, (*first_points[1:], first_points[0]), strict=False)
            for c, d in zip(second_points, (*second_points[1:], second_points[0]), strict=False)
        )
    first_bounds = _source_rect(first)
    second_bounds = _source_rect(second)
    return _rectangles_overlap(first_bounds, second_bounds)


def _ellipse_boundary(source: SourceGeometry, count: int = 32) -> tuple[PagePoint, ...]:
    cos_angle = math.cos(source.rotation_rad)
    sin_angle = math.sin(source.rotation_rad)
    return tuple(
        PagePoint(
            source.center.x_mm
            + source.radius_x_mm * math.cos(index * 2.0 * math.pi / count) * cos_angle
            - source.radius_y_mm * math.sin(index * 2.0 * math.pi / count) * sin_angle,
            source.center.y_mm
            + source.radius_x_mm * math.cos(index * 2.0 * math.pi / count) * sin_angle
            + source.radius_y_mm * math.sin(index * 2.0 * math.pi / count) * cos_angle,
        )
        for index in range(count)
    )


def _rectangles_overlap(first: PageRect, second: PageRect) -> bool:
    return (
        first.left_mm <= second.right_mm
        and first.right_mm >= second.left_mm
        and first.top_mm <= second.bottom_mm
        and first.bottom_mm >= second.top_mm
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
