"""Compass label candidate generation.

Each label gets up to eight candidate placements around its anchor object's
exclusion zone, following the standard compass positions in ``AGENTS.md``
section 14.2.  Page orientation is north up and east left, so the east vector
points to decreasing page x.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from nightsky_atlas.chart.page import PagePoint, PageRect
from nightsky_atlas.layout.geometry import circle_rect_edge_distance_mm
from nightsky_atlas.layout.models import CompassPosition, LabelCandidate
from nightsky_atlas.render.text import TextMetrics

__all__ = [
    "CANDIDATE_DIRECTIONS_16",
    "CANDIDATE_PREFERENCE",
    "COMPASS_VECTORS",
    "compass_candidates",
    "direction_preference_rank",
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
    CompassPosition.NNE: (-math.sin(math.pi / 8.0), -math.cos(math.pi / 8.0)),
    CompassPosition.ENE: (-math.cos(math.pi / 8.0), -math.sin(math.pi / 8.0)),
    CompassPosition.ESE: (-math.cos(math.pi / 8.0), math.sin(math.pi / 8.0)),
    CompassPosition.SSE: (-math.sin(math.pi / 8.0), math.cos(math.pi / 8.0)),
    CompassPosition.SSW: (math.sin(math.pi / 8.0), math.cos(math.pi / 8.0)),
    CompassPosition.WSW: (math.cos(math.pi / 8.0), math.sin(math.pi / 8.0)),
    CompassPosition.WNW: (math.cos(math.pi / 8.0), -math.sin(math.pi / 8.0)),
    CompassPosition.NNW: (math.sin(math.pi / 8.0), -math.cos(math.pi / 8.0)),
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

CANDIDATE_DIRECTIONS_16: tuple[CompassPosition, ...] = (
    CompassPosition.N,
    CompassPosition.NNE,
    CompassPosition.NE,
    CompassPosition.ENE,
    CompassPosition.E,
    CompassPosition.ESE,
    CompassPosition.SE,
    CompassPosition.SSE,
    CompassPosition.S,
    CompassPosition.SSW,
    CompassPosition.SW,
    CompassPosition.WSW,
    CompassPosition.W,
    CompassPosition.WNW,
    CompassPosition.NW,
    CompassPosition.NNW,
)


def direction_preference_rank(position: CompassPosition) -> float:
    """Return a stable atlas direction preference rank for 8/16-way candidates."""
    if position in CANDIDATE_PREFERENCE:
        return float(CANDIDATE_PREFERENCE.index(position))
    # Intermediate directions inherit the preference rank of the following
    # compass direction, with a small penalty so the traditional eight remain
    # the first choice when geometry is otherwise equal.
    clockwise = CANDIDATE_DIRECTIONS_16
    index = clockwise.index(position)
    following = clockwise[(index + 1) % len(clockwise)]
    while following not in CANDIDATE_PREFERENCE:
        index = (index + 1) % len(clockwise)
        following = clockwise[(index + 1) % len(clockwise)]
    return CANDIDATE_PREFERENCE.index(following) + 0.25


CandidateEdgeDistance = Callable[[PageRect, tuple[PageRect, ...]], float]


def compass_candidates(
    *,
    label_id: str,
    metrics: TextMetrics,
    anchor: PagePoint,
    exclusion_radius_mm: float,
    padding_mm: float = 0.6,
    exact_edge_gap_mm: float | None = None,
    exact_edge_distance: CandidateEdgeDistance | None = None,
    approximate_edge_distance: CandidateEdgeDistance | None = None,
    exact_edge_gaps_mm: tuple[float, ...] | None = None,
    positions: tuple[CompassPosition, ...] | None = None,
    positions_by_ring: tuple[tuple[CompassPosition, ...], ...] | None = None,
    allowed_rect: PageRect | None = None,
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
    if exact_edge_gaps_mm is not None and not exact_edge_gaps_mm:
        raise ValueError("exact_edge_gaps_mm must not be empty")
    if exact_edge_gaps_mm is not None and ring_count != 1:
        raise ValueError("exact_edge_gaps_mm cannot be combined with multiple rings")
    if positions_by_ring is not None and exact_edge_gaps_mm is None:
        raise ValueError("positions_by_ring requires exact_edge_gaps_mm")

    candidates: list[LabelCandidate] = []
    candidate_positions = positions or CANDIDATE_PREFERENCE
    gap_count = len(exact_edge_gaps_mm) if exact_edge_gaps_mm is not None else ring_count
    if positions_by_ring is not None and len(positions_by_ring) != gap_count:
        raise ValueError("positions_by_ring must match the number of exact edge gaps")
    for ring in range(gap_count):
        ring_positions = (
            positions_by_ring[ring]
            if positions_by_ring is not None
            else candidate_positions
        )
        for position in ring_positions:
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
            if exact_edge_gap_mm is not None:
                target_edge_gap_mm = (
                    exact_edge_gaps_mm[ring]
                    if exact_edge_gaps_mm is not None
                    else exact_edge_gap_mm + ring * ring_gap_mm
                )
                for _ in range(3):
                    glyph_bounds = _translated_rects(
                        metrics.ink_rects_mm, bounds.left_mm, bounds.top_mm
                    )
                    distance_fn = (
                        approximate_edge_distance
                        if approximate_edge_distance is not None and _ < 1
                        else exact_edge_distance
                    )
                    gap = (
                        distance_fn(bounds, glyph_bounds)
                        if distance_fn is not None
                        else circle_rect_edge_distance_mm(anchor, exclusion_radius_mm, bounds)
                    )
                    adjustment = gap - target_edge_gap_mm
                    if abs(adjustment) < 0.001:
                        break
                    radial_x = bounds.center.x_mm - anchor.x_mm
                    radial_y = bounds.center.y_mm - anchor.y_mm
                    radial_length = math.hypot(radial_x, radial_y)
                    if radial_length == 0.0:
                        break
                    bounds = PageRect(
                        left_mm=bounds.left_mm - radial_x / radial_length * adjustment,
                        top_mm=bounds.top_mm - radial_y / radial_length * adjustment,
                        width_mm=bounds.width_mm,
                        height_mm=bounds.height_mm,
                    )
            if allowed_rect is not None and not (
                bounds.left_mm >= allowed_rect.left_mm - 1e-9
                and bounds.top_mm >= allowed_rect.top_mm - 1e-9
                and bounds.right_mm <= allowed_rect.right_mm + 1e-9
                and bounds.bottom_mm <= allowed_rect.bottom_mm + 1e-9
            ):
                continue
            candidate_id = (
                f"{label_id}:{position.value}"
                if ring == 0
                else f"{label_id}:{position.value}:{ring}"
            )
            candidates.append(
                LabelCandidate(
                    id=candidate_id,
                    position=position,
                    anchor=PagePoint(x_mm=bounds.left_mm, y_mm=bounds.top_mm),
                    bounds=bounds,
                    ring=ring,
                    glyph_bounds=_translated_rects(
                        metrics.ink_rects_mm, bounds.left_mm, bounds.top_mm
                    ),
                    whitespace_bounds=_translated_rects(
                        metrics.whitespace_rects_mm, bounds.left_mm, bounds.top_mm
                    ),
                )
            )
    return tuple(candidates)


def _translated_rects(
    rects: tuple[PageRect, ...], left_mm: float, top_mm: float
) -> tuple[PageRect, ...]:
    return tuple(
        PageRect(
            left_mm=left_mm + rect.left_mm,
            top_mm=top_mm + rect.top_mm,
            width_mm=rect.width_mm,
            height_mm=rect.height_mm,
        )
        for rect in rects
    )
