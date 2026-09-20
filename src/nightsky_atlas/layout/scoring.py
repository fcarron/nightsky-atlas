"""Decomposed soft-cost function for label placement.

Every component is measured separately so diagnostics can explain *why* a
candidate was chosen (``AGENTS.md`` section 15.2).  No opaque single score.
"""

from __future__ import annotations

from dataclasses import dataclass

from nightsky_atlas.atlas.config import StarLabelClearanceStyle
from nightsky_atlas.chart.page import PagePoint, PageRect
from nightsky_atlas.layout.candidates import CANDIDATE_PREFERENCE
from nightsky_atlas.layout.geometry import (
    circle_intersects_rect,
    circle_rect_edge_distance_mm,
    expand_rect,
    rect_overlap_area_mm2,
    rects_overlap,
    segment_intersects_rect,
)
from nightsky_atlas.layout.models import LabelCandidate

__all__ = ["CostBreakdown", "CostWeights", "StarCircle", "SymbolCircle", "score_candidate"]


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


@dataclass(frozen=True, slots=True)
class SymbolCircle:
    """A symbol exclusion zone approximated by a circle."""

    center: PagePoint
    radius_mm: float


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
            foreign_penalty += _clearance_penalty(
                distance,
                clearance.foreign.hard_min_mm,
                clearance.foreign.soft_clear_mm,
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
    )


def _clearance_penalty(distance_mm: float, hard_min_mm: float, soft_clear_mm: float) -> float:
    """Return a smooth 0..1 near-miss penalty above a hard clearance floor."""
    if distance_mm >= soft_clear_mm:
        return 0.0
    if distance_mm <= hard_min_mm:
        return 1.0
    fraction = (soft_clear_mm - distance_mm) / (soft_clear_mm - hard_min_mm)
    return fraction * fraction


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
