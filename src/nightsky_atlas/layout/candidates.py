"""Compass label candidate generation.

Each label gets up to eight candidate placements around its anchor object's
exclusion zone, following the standard compass positions in ``AGENTS.md``
section 14.2.  Page orientation is north up and east left, so the east vector
points to decreasing page x.
"""

from __future__ import annotations

import math

from nightsky_atlas.chart.page import PagePoint, PageRect
from nightsky_atlas.layout.models import CompassPosition, LabelCandidate
from nightsky_atlas.render.text import TextMetrics

__all__ = [
    "CANDIDATE_PREFERENCE",
    "COMPASS_VECTORS",
    "compass_candidates",
]

_SQRT_HALF = math.sqrt(0.5)

COMPASS_VECTORS: dict[CompassPosition, tuple[float, float]] = {
    CompassPosition.N: (0.0, -1.0),
    CompassPosition.NE: (-_SQRT_HALF, -_SQRT_HALF),
    CompassPosition.E: (-1.0, 0.0),
    CompassPosition.SE: (-_SQRT_HALF, _SQRT_HALF),
    CompassPosition.S: (0.0, 1.0),
    CompassPosition.SW: (_SQRT_HALF, _SQRT_HALF),
    CompassPosition.W: (1.0, 0.0),
    CompassPosition.NW: (_SQRT_HALF, -_SQRT_HALF),
}

CANDIDATE_PREFERENCE: tuple[CompassPosition, ...] = (
    CompassPosition.N,
    CompassPosition.NE,
    CompassPosition.E,
    CompassPosition.SE,
    CompassPosition.S,
    CompassPosition.SW,
    CompassPosition.W,
    CompassPosition.NW,
)


def compass_candidates(
    *,
    label_id: str,
    metrics: TextMetrics,
    anchor: PagePoint,
    exclusion_radius_mm: float,
    padding_mm: float = 0.6,
    ring_count: int = 1,
    ring_gap_mm: float = 2.5,
) -> tuple[LabelCandidate, ...]:
    """Generate compass candidates around an anchor point.

    ``anchor`` is the anchor object's page position; ``exclusion_radius_mm`` is
    the radius of its symbol.  A candidate's text box is placed so that its near
    edge clears the exclusion zone by ``padding_mm``.  Additional concentric
    rings are generated at ``ring_gap_mm`` spacing to give the optimizer more
    room in crowded fields; ring 0 keeps the plain ``position`` ID used by the
    compass action schema.
    """
    if ring_count < 1:
        raise ValueError("ring_count must be at least 1")

    candidates: list[LabelCandidate] = []
    for ring in range(ring_count):
        for position in CANDIDATE_PREFERENCE:
            dx, dy = COMPASS_VECTORS[position]
            half_extent = (
                abs(dx) * metrics.width_mm / 2.0 + abs(dy) * metrics.height_mm / 2.0
            )
            distance = (
                exclusion_radius_mm + padding_mm + half_extent + ring * ring_gap_mm
            )
            center_x = anchor.x_mm + dx * distance
            center_y = anchor.y_mm + dy * distance
            left = center_x - metrics.width_mm / 2.0
            top = center_y - metrics.height_mm / 2.0
            bounds = PageRect(
                left_mm=left,
                top_mm=top,
                width_mm=metrics.width_mm,
                height_mm=metrics.height_mm,
            )
            candidate_id = (
                f"{label_id}:{position.value}"
                if ring == 0
                else f"{label_id}:{position.value}:{ring}"
            )
            candidates.append(
                LabelCandidate(
                    id=candidate_id,
                    position=position,
                    anchor=PagePoint(x_mm=left, y_mm=top),
                    bounds=bounds,
                    ring=ring,
                )
            )
    return tuple(candidates)