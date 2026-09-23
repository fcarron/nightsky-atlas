"""Decomposed soft-cost function for label placement.

Every component is measured separately so diagnostics can explain *why* a
candidate was chosen (``AGENTS.md`` section 15.2).  No opaque single score.
"""

from __future__ import annotations

from dataclasses import dataclass

from nightsky_atlas.atlas.config import (
    ForeignStarClearanceStyle,
    SourceAssociationStyle,
    StarLabelClearanceStyle,
)
from nightsky_atlas.chart.page import PagePoint, PageRect
from nightsky_atlas.layout.candidates import CANDIDATE_PREFERENCE
from nightsky_atlas.layout.geometry import (
    circle_intersects_rect,
    circle_rect_edge_distance_mm,
    clamp_point_to_rect,
    expand_rect,
    rect_overlap_area_mm2,
    rects_overlap,
    segment_intersects_rect,
)
from nightsky_atlas.layout.models import LabelCandidate

__all__ = [
    "CostBreakdown",
    "CostWeights",
    "StarCircle",
    "SymbolCircle",
    "foreign_star_hard_min_mm",
    "score_candidate",
]


@dataclass(frozen=True, slots=True)
class CostWeights:
    """Relative weights for each independently measured cost component."""

    label_label_overlap: float = 100.0
    label_symbol_overlap: float = 40.0
    anchor_distance: float = 1.0
    edge_proximity: float = 2.0
    preference_rank: float = 0.5
    crowding: float = 1.0
    constellation_line_overlap: float = 35.0
    label_foreign_star_clearance: float = 18.0
    label_associated_star_clearance: float = 8.0
    label_association_distance: float = 0.5
    label_source_distance: float = 12.0
    label_source_corridor: float = 18.0
    label_competing_source_ambiguity: float = 20.0
    label_foreign_object_proximity: float = 8.0


@dataclass(frozen=True, slots=True)
class SymbolCircle:
    """A DSO source extent, optionally refined by rendered contour paths."""

    center: PagePoint
    radius_mm: float
    id: str = ""
    outline_paths: tuple[tuple[PagePoint, ...], ...] = ()


@dataclass(frozen=True, slots=True)
class StarCircle:
    """One actually printed stellar mark, including collapsed double systems."""

    id: str
    star_ids: frozenset[str]
    center: PagePoint
    radius_mm: float


@dataclass(frozen=True, slots=True)
class CostBreakdown:
    """Independently measurable cost components for one candidate."""

    label_label_overlap_mm2: float = 0.0
    label_symbol_overlap_mm2: float = 0.0
    anchor_distance_mm: float = 0.0
    edge_proximity_mm: float = 0.0
    preference_rank: float = 0.0
    crowding: float = 0.0
    constellation_line_overlap: float = 0.0
    label_foreign_star_clearance: float = 0.0
    label_associated_star_clearance: float = 0.0
    label_association_distance_mm: float = 0.0
    label_source_distance_mm: float = 0.0
    label_source_corridor: float = 0.0
    label_competing_source_ambiguity: float = 0.0
    label_foreign_object_proximity: float = 0.0

    def total(self, weights: CostWeights) -> float:
        """Return the weighted total cost."""
        return (
            self.label_label_overlap_mm2 * weights.label_label_overlap
            + self.label_symbol_overlap_mm2 * weights.label_symbol_overlap
            + self.anchor_distance_mm * weights.anchor_distance
            + self.edge_proximity_mm * weights.edge_proximity
            + self.preference_rank * weights.preference_rank
            + self.crowding * weights.crowding
            + self.constellation_line_overlap * weights.constellation_line_overlap
            + self.label_foreign_star_clearance * weights.label_foreign_star_clearance
            + self.label_associated_star_clearance * weights.label_associated_star_clearance
            + self.label_association_distance_mm * weights.label_association_distance
            + self.label_source_distance_mm * weights.label_source_distance
            + self.label_source_corridor * weights.label_source_corridor
            + self.label_competing_source_ambiguity
            * weights.label_competing_source_ambiguity
            + self.label_foreign_object_proximity * weights.label_foreign_object_proximity
        )

    def components(self) -> dict[str, float]:
        """Return each component keyed by field name."""
        return {
            "label_label_overlap_mm2": self.label_label_overlap_mm2,
            "label_symbol_overlap_mm2": self.label_symbol_overlap_mm2,
            "anchor_distance_mm": self.anchor_distance_mm,
            "edge_proximity_mm": self.edge_proximity_mm,
            "preference_rank": self.preference_rank,
            "crowding": self.crowding,
            "constellation_line_overlap": self.constellation_line_overlap,
            "label_foreign_star_clearance": self.label_foreign_star_clearance,
            "label_associated_star_clearance": self.label_associated_star_clearance,
            "label_association_distance_mm": self.label_association_distance_mm,
            "label_source_distance_mm": self.label_source_distance_mm,
            "label_source_corridor": self.label_source_corridor,
            "label_competing_source_ambiguity": self.label_competing_source_ambiguity,
            "label_foreign_object_proximity": self.label_foreign_object_proximity,
        }


def _edge_proximity_mm(bounds: PageRect, printable: PageRect, margin_mm: float) -> float:
    penalty = 0.0
    for distance in (
        bounds.left_mm - printable.left_mm,
        printable.right_mm - bounds.right_mm,
        bounds.top_mm - printable.top_mm,
        printable.bottom_mm - bounds.bottom_mm,
    ):
        if distance < margin_mm:
            penalty += margin_mm - distance
    return penalty


def score_candidate(
    candidate: LabelCandidate,
    *,
    target_anchor: PagePoint,
    placed_bounds: tuple[PageRect, ...],
    symbols: tuple[SymbolCircle, ...],
    stars: tuple[StarCircle, ...] = (),
    associated_star_ids: frozenset[str] = frozenset(),
    star_clearance: StarLabelClearanceStyle | None = None,
    target_source_id: str | None = None,
    source_association: SourceAssociationStyle | None = None,
    source_symbols: tuple[SymbolCircle, ...] | None = None,
    association_scale: float = 1.0,
    printable: PageRect,
    crowding_radius_mm: float,
    weights: CostWeights,
    edge_margin_mm: float = 8.0,
    constellation_lines: tuple[tuple[PagePoint, PagePoint], ...] = (),
    line_safety_margin_mm: float = 0.4,
) -> CostBreakdown:
    """Measure all cost components for one candidate."""
    bounds = candidate.bounds
    center = bounds.center

    label_overlap = sum(
        rect_overlap_area_mm2(bounds, other)
        for other in placed_bounds
        if rects_overlap(bounds, other)
    )
    symbol_overlap = sum(
        rect_overlap_area_mm2(bounds, _symbol_rect(symbol))
        for symbol in symbols
        if circle_intersects_rect(symbol.center, symbol.radius_mm, bounds)
    )
    anchor_distance = (
        (center.x_mm - target_anchor.x_mm) ** 2 + (center.y_mm - target_anchor.y_mm) ** 2
    ) ** 0.5
    crowding = float(
        sum(1 for other in placed_bounds if _rect_distance(center, other) <= crowding_radius_mm)
    )
    line_overlap = float(
        sum(
            segment_intersects_rect(start, end, expand_rect(bounds, line_safety_margin_mm))
            for start, end in constellation_lines
        )
    )
    clearance = star_clearance or StarLabelClearanceStyle()
    foreign_penalty = 0.0
    associated_penalty = 0.0
    association_distance = 0.0
    for star in stars:
        distance = circle_rect_edge_distance_mm(star.center, star.radius_mm, bounds)
        if associated_star_ids & star.star_ids:
            associated_penalty += _clearance_penalty(
                distance,
                clearance.associated.hard_min_mm,
                clearance.associated.soft_clear_mm,
            )
            association_distance += max(0.0, distance - clearance.associated.preferred_max_mm)
        else:
            foreign_penalty += _foreign_star_proximity_penalty(
                distance, star.radius_mm, clearance.foreign
            )
    if target_source_id is None:
        source_distance = 0.0
        source_corridor = 0.0
        competing_ambiguity = 0.0
        foreign_object_proximity = 0.0
    else:
        association = source_association or SourceAssociationStyle()
        (
            source_distance,
            source_corridor,
            competing_ambiguity,
            foreign_object_proximity,
        ) = _source_association_costs(
            bounds,
            target_anchor,
            target_source_id,
            stars,
            symbols if source_symbols is None else source_symbols,
            associated_star_ids,
            association,
        )

    return CostBreakdown(
        label_label_overlap_mm2=label_overlap,
        label_symbol_overlap_mm2=symbol_overlap,
        anchor_distance_mm=anchor_distance,
        edge_proximity_mm=_edge_proximity_mm(bounds, printable, edge_margin_mm),
        preference_rank=float(CANDIDATE_PREFERENCE.index(candidate.position)),
        crowding=crowding,
        constellation_line_overlap=line_overlap,
        label_foreign_star_clearance=foreign_penalty,
        label_associated_star_clearance=associated_penalty,
        label_association_distance_mm=association_distance,
        label_source_distance_mm=source_distance,
        label_source_corridor=source_corridor * association_scale,
        label_competing_source_ambiguity=competing_ambiguity * association_scale,
        label_foreign_object_proximity=foreign_object_proximity,
    )


def _source_association_costs(
    bounds: PageRect,
    target_anchor: PagePoint,
    target_source_id: str | None,
    stars: tuple[StarCircle, ...],
    symbols: tuple[SymbolCircle, ...],
    associated_star_ids: frozenset[str],
    config: SourceAssociationStyle,
) -> tuple[float, float, float, float]:
    """Score the visual corridor and ownership of a source-to-label pairing."""
    own_stars = tuple(star for star in stars if associated_star_ids & star.star_ids)
    own_symbols = tuple(symbol for symbol in symbols if symbol.id == target_source_id)
    owner_gaps = [
        circle_rect_edge_distance_mm(source.center, source.radius_mm, bounds)
        for source in own_stars
    ] + [_source_rect_edge_distance(source, bounds) for source in own_symbols]
    owner_gap = min(owner_gaps, default=_point_rect_distance(target_anchor, bounds))
    source_distance = max(
        0.0,
        config.preferred_min_gap_mm - owner_gap,
        owner_gap - config.preferred_max_gap_mm,
    )
    if own_symbols:
        owner = min(own_symbols, key=lambda source: _source_rect_edge_distance(source, bounds))
        corridor_start = _source_facing_point(owner, bounds)
    else:
        corridor_start = target_anchor
    corridor_end = clamp_point_to_rect(corridor_start, bounds)
    own_extent = max((source.radius_mm for source in own_symbols), default=0.0)
    corridor = 0.0
    ambiguity = 0.0
    foreign_object_proximity = 0.0
    ambiguity_limit = max(0.0, owner_gap) + config.ambiguity_margin_mm

    for star in stars:
        if associated_star_ids & star.star_ids:
            continue
        if own_symbols and _point_distance(star.center, target_anchor) <= own_extent:
            continue
        importance = min(2.0, max(0.15, star.radius_mm / 0.6))
        if _point_segment_distance(star.center, corridor_start, corridor_end) < (
            star.radius_mm + config.corridor_margin_mm
        ):
            corridor += importance
        gap = circle_rect_edge_distance_mm(star.center, star.radius_mm, bounds)
        if gap < ambiguity_limit:
            ambiguity += importance * (ambiguity_limit - gap) / max(
                config.ambiguity_margin_mm, 1e-9
            )

    for symbol in symbols:
        if symbol.id == target_source_id:
            continue
        if _point_segment_distance(symbol.center, corridor_start, corridor_end) < (
            symbol.radius_mm + config.corridor_margin_mm
        ):
            corridor += 1.0
        gap = _source_rect_edge_distance(symbol, bounds)
        if gap < ambiguity_limit:
            ambiguity += (ambiguity_limit - gap) / max(config.ambiguity_margin_mm, 1e-9)
        if gap < config.foreign_object_clear_mm:
            fraction = (config.foreign_object_clear_mm - gap) / config.foreign_object_clear_mm
            foreign_object_proximity += fraction * fraction
    return source_distance, corridor, ambiguity, foreign_object_proximity


def _point_distance(first: PagePoint, second: PagePoint) -> float:
    return ((first.x_mm - second.x_mm) ** 2 + (first.y_mm - second.y_mm) ** 2) ** 0.5


def _point_rect_distance(point: PagePoint, rect: PageRect) -> float:
    return _point_distance(point, clamp_point_to_rect(point, rect))


def _source_rect_edge_distance(source: SymbolCircle, rect: PageRect) -> float:
    if not source.outline_paths:
        return circle_rect_edge_distance_mm(source.center, source.radius_mm, rect)
    return min(
        _segment_rect_distance(start, end, rect)
        for path in source.outline_paths
        for start, end in zip(path, path[1:], strict=False)
    )


def _source_facing_point(source: SymbolCircle, rect: PageRect) -> PagePoint:
    if not source.outline_paths:
        near = clamp_point_to_rect(source.center, rect)
        dx = near.x_mm - source.center.x_mm
        dy = near.y_mm - source.center.y_mm
        length = (dx * dx + dy * dy) ** 0.5
        if length <= 0.0:
            return source.center
        return PagePoint(
            source.center.x_mm + dx / length * source.radius_mm,
            source.center.y_mm + dy / length * source.radius_mm,
        )
    target = rect.center
    return min(
        (
            _closest_point_on_segment(target, start, end)
            for path in source.outline_paths
            for start, end in zip(path, path[1:], strict=False)
        ),
        key=lambda point: _point_distance(point, target),
    )


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


def _clearance_penalty(distance_mm: float, hard_min_mm: float, soft_clear_mm: float) -> float:
    """Return a smooth 0..1 near-miss penalty above a hard clearance floor."""
    if distance_mm >= soft_clear_mm:
        return 0.0
    if distance_mm <= hard_min_mm:
        return 1.0
    fraction = (soft_clear_mm - distance_mm) / (soft_clear_mm - hard_min_mm)
    return fraction * fraction


def foreign_star_hard_min_mm(radius_mm: float, clearance: StarLabelClearanceStyle) -> float:
    """Return a hard clearance only for visually significant foreign stars."""
    if radius_mm < clearance.foreign.hard_radius_mm:
        return float("-inf")
    return clearance.foreign.hard_min_mm


def _foreign_star_proximity_penalty(
    distance_mm: float, radius_mm: float, clearance: ForeignStarClearanceStyle
) -> float:
    soft_clear = clearance.soft_clear_mm + radius_mm * clearance.radius_clearance_factor
    if distance_mm >= soft_clear:
        return 0.0
    fraction = (soft_clear - distance_mm) / soft_clear
    importance = min(
        clearance.maximum_importance,
        radius_mm / clearance.importance_reference_radius_mm,
    )
    return importance * fraction * fraction


def _symbol_rect(symbol: SymbolCircle) -> PageRect:
    return PageRect(
        left_mm=symbol.center.x_mm - symbol.radius_mm,
        top_mm=symbol.center.y_mm - symbol.radius_mm,
        width_mm=2.0 * symbol.radius_mm,
        height_mm=2.0 * symbol.radius_mm,
    )


def _rect_distance(point: PagePoint, rect: PageRect) -> float:
    dx = max(rect.left_mm - point.x_mm, 0.0, point.x_mm - rect.right_mm)
    dy = max(rect.top_mm - point.y_mm, 0.0, point.y_mm - rect.bottom_mm)
    return (dx * dx + dy * dy) ** 0.5
