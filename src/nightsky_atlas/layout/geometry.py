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
]


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


def circle_intersects_rect(
    center: PagePoint, radius_mm: float, rect: PageRect
) -> bool:
    """Return whether a circle intersects a rectangle."""
    closest = clamp_point_to_rect(center, rect)
    return math.hypot(closest.x_mm - center.x_mm, closest.y_mm - center.y_mm) <= radius_mm