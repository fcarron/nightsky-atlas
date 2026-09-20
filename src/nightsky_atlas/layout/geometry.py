"""Geometric primitives for collision detection.

Axis-aligned rectangles are the label and page primitive.  Symbol circles are
used for star and deep-sky exclusion zones; ellipses are approximated by their
bounding circle, which is conservative for collision purposes
(``AGENTS.md`` section 24.1).
"""

from __future__ import annotations

import math

from nightsky_atlas.chart.page import PagePoint, PageRect

__all__ = [
    "circle_intersects_rect",
    "clamp_point_to_rect",
    "point_in_rect",
    "rect_distance_mm",
    "rect_overlap_area_mm2",
    "rects_overlap",
    "expand_rect",
    "segment_intersects_rect",
    "segments_intersect",
    "split_segment_at_rect",
]


def segments_intersect(
    first_start: PagePoint,
    first_end: PagePoint,
    second_start: PagePoint,
    second_end: PagePoint,
) -> bool:
    """Whether two finite segments cross or touch."""
    if (
        max(first_start.x_mm, first_end.x_mm) < min(second_start.x_mm, second_end.x_mm)
        or max(second_start.x_mm, second_end.x_mm) < min(first_start.x_mm, first_end.x_mm)
        or max(first_start.y_mm, first_end.y_mm) < min(second_start.y_mm, second_end.y_mm)
        or max(second_start.y_mm, second_end.y_mm) < min(first_start.y_mm, first_end.y_mm)
    ):
        return False

    def cross(a: PagePoint, b: PagePoint, c: PagePoint) -> float:
        return (b.x_mm - a.x_mm) * (c.y_mm - a.y_mm) - (
            b.y_mm - a.y_mm
        ) * (c.x_mm - a.x_mm)

    first_side_a = cross(first_start, first_end, second_start)
    first_side_b = cross(first_start, first_end, second_end)
    second_side_a = cross(second_start, second_end, first_start)
    second_side_b = cross(second_start, second_end, first_end)
    return first_side_a * first_side_b <= 0.0 and second_side_a * second_side_b <= 0.0


def expand_rect(rect: PageRect, margin_mm: float) -> PageRect:
    """Return a rectangle expanded uniformly in page millimetres."""
    return PageRect(
        rect.left_mm - margin_mm,
        rect.top_mm - margin_mm,
        rect.width_mm + 2 * margin_mm,
        rect.height_mm + 2 * margin_mm,
    )


def _clip_parameter(p: float, q: float, interval: list[float]) -> bool:
    if p == 0.0:
        return q >= 0.0
    value = q / p
    if p < 0.0:
        if value > interval[1]:
            return False
        interval[0] = max(interval[0], value)
    else:
        if value < interval[0]:
            return False
        interval[1] = min(interval[1], value)
    return True


def _segment_rect_interval(
    start: PagePoint, end: PagePoint, rect: PageRect
) -> tuple[float, float] | None:
    """Return the closed parameter interval where a segment is inside ``rect``."""
    dx, dy = end.x_mm - start.x_mm, end.y_mm - start.y_mm
    interval = [0.0, 1.0]
    for p, q in (
        (-dx, start.x_mm - rect.left_mm),
        (dx, rect.right_mm - start.x_mm),
        (-dy, start.y_mm - rect.top_mm),
        (dy, rect.bottom_mm - start.y_mm),
    ):
        if not _clip_parameter(p, q, interval):
            return None
    return (interval[0], interval[1]) if interval[0] <= interval[1] else None


def segment_intersects_rect(start: PagePoint, end: PagePoint, rect: PageRect) -> bool:
    """Return whether a closed page-space segment enters a rectangle."""
    return _segment_rect_interval(start, end, rect) is not None


def split_segment_at_rect(
    start: PagePoint, end: PagePoint, rect: PageRect
) -> tuple[tuple[PagePoint, PagePoint], ...]:
    """Return visible portions of a segment after knocking out its rect intersection."""
    interval = _segment_rect_interval(start, end, rect)
    if interval is None:
        return ((start, end),)
    dx, dy = end.x_mm - start.x_mm, end.y_mm - start.y_mm

    def point(t: float) -> PagePoint:
        return PagePoint(start.x_mm + dx * t, start.y_mm + dy * t)

    first, last = interval
    parts: list[tuple[PagePoint, PagePoint]] = []
    if first > 0.0:
        parts.append((start, point(first)))
    if last < 1.0:
        parts.append((point(last), end))
    return tuple(parts)


def point_in_rect(point: PagePoint, rect: PageRect, *, tolerance_mm: float = 0.0) -> bool:
    """Return whether a point lies inside a rectangle."""
    return (
        rect.left_mm - tolerance_mm <= point.x_mm <= rect.right_mm + tolerance_mm
        and rect.top_mm - tolerance_mm <= point.y_mm <= rect.bottom_mm + tolerance_mm
    )


def rects_overlap(a: PageRect, b: PageRect, *, tolerance_mm: float = 0.0) -> bool:
    """Return whether two rectangles overlap (touching counts with tolerance)."""
    return not (
        a.right_mm < b.left_mm - tolerance_mm
        or b.right_mm < a.left_mm - tolerance_mm
        or a.bottom_mm < b.top_mm - tolerance_mm
        or b.bottom_mm < a.top_mm - tolerance_mm
    )


def rect_overlap_area_mm2(a: PageRect, b: PageRect) -> float:
    """Return the overlapping area of two rectangles in square millimetres."""
    width = min(a.right_mm, b.right_mm) - max(a.left_mm, b.left_mm)
    height = min(a.bottom_mm, b.bottom_mm) - max(a.top_mm, b.top_mm)
    if width <= 0.0 or height <= 0.0:
        return 0.0
    return width * height


def clamp_point_to_rect(point: PagePoint, rect: PageRect) -> PagePoint:
    """Return the point on ``rect`` closest to ``point``."""
    return PagePoint(
        x_mm=min(max(point.x_mm, rect.left_mm), rect.right_mm),
        y_mm=min(max(point.y_mm, rect.top_mm), rect.bottom_mm),
    )


def rect_distance_mm(a: PageRect, b: PageRect) -> float:
    """Return the shortest distance between two rectangles (0 if overlapping)."""
    dx = max(0.0, max(a.left_mm - b.right_mm, b.left_mm - a.right_mm))
    dy = max(0.0, max(a.top_mm - b.bottom_mm, b.top_mm - a.bottom_mm))
    return math.hypot(dx, dy)


def circle_intersects_rect(center: PagePoint, radius_mm: float, rect: PageRect) -> bool:
    """Return whether a circle intersects a rectangle."""
    closest = clamp_point_to_rect(center, rect)
    return math.hypot(closest.x_mm - center.x_mm, closest.y_mm - center.y_mm) <= radius_mm
