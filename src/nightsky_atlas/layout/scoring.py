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
from nightsky_atlas.layout.association import (
    SourceGeometry,
    source_contains_point,
    source_edge_distance,
    source_extent_edge_distance,
    source_facing_point,
)
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
    "candidate_star_edge_distance_mm",
    "foreign_star_hard_min_mm",
    "score_candidate",
    "star_rect_edge_distance_mm",
    "star_source_bounds",
    "star_source_facing_point",
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
    label_source_facing_edge_distance: float = 0.0
    label_source_corridor: float = 18.0
    label_competing_source_ambiguity: float = 20.0
    label_competing_owner: float = 26.0
    label_glyph_proximity: float = 24.0
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
    system_ids: frozenset[str] = frozenset()
    marker_length_mm: float = 0.0
    marker_line_width_mm: float = 0.0


def _star_radius_mm(star: StarCircle) -> float:
    radius = getattr(star, "radius_mm", None)
    return radius if radius is not None else star.collision_radius_mm


def star_source_bounds(star: StarCircle) -> PageRect:
    """Return the conservative bounds of one actual printed star mark."""
    half_width = max(
        _star_radius_mm(star),
        star.marker_length_mm / 2.0 + star.marker_line_width_mm / 2.0,
    )
    half_height = max(_star_radius_mm(star), star.marker_line_width_mm / 2.0)
    return PageRect(
        star.center.x_mm - half_width,
        star.center.y_mm - half_height,
        2.0 * half_width,
        2.0 * half_height,
    )


def _marker_rect_edge_distance_mm(star: StarCircle, rect: PageRect) -> float:
    """Return the edge gap from a collapsed-double marker stroke to ``rect``."""
    if star.marker_length_mm <= 0.0:
        return float("inf")
    half_length = star.marker_length_mm / 2.0
    left = star.center.x_mm - half_length
    right = star.center.x_mm + half_length
    dx = max(left - rect.right_mm, rect.left_mm - right, 0.0)
    dy = max(star.center.y_mm - rect.bottom_mm, rect.top_mm - star.center.y_mm, 0.0)
    return (dx * dx + dy * dy) ** 0.5 - star.marker_line_width_mm / 2.0


def star_rect_edge_distance_mm(star: StarCircle, rect: PageRect) -> float:
    """Return the gap from the actual star/double-star mark to ``rect``.

    Collapsed doubles are the union of their combined-magnitude disk and the
    short horizontal marker.  All other stars remain simple rendered disks.
    """
    return min(
        circle_rect_edge_distance_mm(star.center, _star_radius_mm(star), rect),
        _marker_rect_edge_distance_mm(star, rect),
    )


def candidate_star_edge_distance_mm(
    star: StarCircle, candidate: LabelCandidate, *, visible_text: bool = False
) -> float:
    """Return a star-to-label gap using painted ink for stellar labels.

    Pango logical line boxes contain ascent/descent space with no painted ink.
    Measuring a star-label gap to that space makes short labels visibly farther
    away than their configured physical clearance.
    """
    rects = (
        candidate.glyph_bounds
        if visible_text and candidate.glyph_bounds
        else (candidate.bounds,)
    )
    return min(star_rect_edge_distance_mm(star, rect) for rect in rects)


def star_source_facing_point(star: StarCircle, rect: PageRect) -> PagePoint:
    """Return the nearest visible point of a star/double-star mark to ``rect``."""
    circle_distance = circle_rect_edge_distance_mm(star.center, _star_radius_mm(star), rect)
    marker_distance = _marker_rect_edge_distance_mm(star, rect)
    if marker_distance >= circle_distance:
        return _circle_facing_point(star.center, _star_radius_mm(star), rect)
    near = clamp_point_to_rect(star.center, rect)
    marker_x = min(
        max(near.x_mm, star.center.x_mm - star.marker_length_mm / 2.0),
        star.center.x_mm + star.marker_length_mm / 2.0,
    )
    dx = near.x_mm - marker_x
    dy = near.y_mm - star.center.y_mm
    length = (dx * dx + dy * dy) ** 0.5
    if length <= 0.0:
        return PagePoint(marker_x, star.center.y_mm)
    offset = star.marker_line_width_mm / 2.0
    return PagePoint(marker_x + dx / length * offset, star.center.y_mm + dy / length * offset)


@dataclass(frozen=True, slots=True)
class _ClosestForeignStar:
    id: str
    radius_mm: float
    distance_mm: float


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
    label_source_facing_edge_distance_mm: float = 0.0
    label_source_corridor: float = 0.0
    label_competing_source_ambiguity: float = 0.0
    label_competing_owner: float = 0.0
    label_glyph_proximity: float = 0.0
    label_foreign_object_proximity: float = 0.0
    competing_owner_id: str | None = None
    closest_foreign_star_id: str | None = None
    closest_foreign_star_radius_mm: float | None = None
    closest_foreign_star_distance_mm: float | None = None

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
            + self.label_source_facing_edge_distance_mm
            * weights.label_source_facing_edge_distance
            + self.label_source_corridor * weights.label_source_corridor
            + self.label_competing_source_ambiguity
            * weights.label_competing_source_ambiguity
            + self.label_competing_owner * weights.label_competing_owner
            + self.label_glyph_proximity * weights.label_glyph_proximity
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
            "label_source_facing_edge_distance_mm": (
                self.label_source_facing_edge_distance_mm
            ),
            "label_source_corridor": self.label_source_corridor,
            "label_competing_source_ambiguity": self.label_competing_source_ambiguity,
            "label_competing_owner": self.label_competing_owner,
            "label_glyph_proximity": self.label_glyph_proximity,
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
    related_star_ids: frozenset[str] | None = None,
    star_clearance: StarLabelClearanceStyle | None = None,
    target_source_id: str | None = None,
    source_association: SourceAssociationStyle | None = None,
    source_symbols: tuple[SourceGeometry, ...] | None = None,
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
    related_ids = associated_star_ids if related_star_ids is None else related_star_ids
    foreign_penalty = 0.0
    associated_penalty = 0.0
    association_distance = 0.0
    visible_star_text = bool(associated_star_ids)
    for star in stars:
        distance = candidate_star_edge_distance_mm(
            star, candidate, visible_text=visible_star_text
        )
        if associated_star_ids & star.star_ids:
            associated_penalty += _clearance_penalty(
                distance,
                clearance.associated.hard_min_mm,
                clearance.associated.soft_clear_mm,
            )
            association_distance += max(0.0, distance - clearance.associated.preferred_max_mm)
        elif not related_ids & star.star_ids:
            foreign_penalty += _foreign_star_proximity_penalty(
                distance, star.radius_mm, clearance.foreign
            )
    if target_source_id is None:
        glyph_proximity = 0.0
        closest_foreign = None
        source_distance = 0.0
        source_facing_distance = 0.0
        source_corridor = 0.0
        competing_ambiguity = 0.0
        competing_owner = 0.0
        foreign_object_proximity = 0.0
        competing_owner_id = None
    else:
        association = source_association or SourceAssociationStyle()
        association_sources = () if source_symbols is None else source_symbols
        owner_sources = tuple(
            source for source in association_sources if source.id == target_source_id
        )
        glyph_proximity, closest_foreign = _glyph_proximity_cost(
            candidate,
            stars,
            associated_star_ids,
            related_ids,
            owner_sources,
            association,
        )
        (
            source_distance,
            source_facing_distance,
            source_corridor,
            competing_ambiguity,
            competing_owner,
            foreign_object_proximity,
            competing_owner_id,
        ) = _source_association_costs(
            candidate,
            target_anchor,
            target_source_id,
            stars,
            association_sources,
            associated_star_ids,
            related_ids,
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
        label_source_distance_mm=source_distance * association_scale,
        label_source_facing_edge_distance_mm=source_facing_distance,
        label_source_corridor=source_corridor * association_scale,
        label_competing_source_ambiguity=competing_ambiguity * association_scale,
        label_competing_owner=competing_owner * association_scale,
        label_glyph_proximity=glyph_proximity * association_scale,
        label_foreign_object_proximity=foreign_object_proximity,
        competing_owner_id=competing_owner_id,
        closest_foreign_star_id=(closest_foreign.id if closest_foreign else None),
        closest_foreign_star_radius_mm=(
            closest_foreign.radius_mm if closest_foreign else None
        ),
        closest_foreign_star_distance_mm=(
            closest_foreign.distance_mm if closest_foreign else None
        ),
    )


def _source_association_costs(
    candidate: LabelCandidate,
    target_anchor: PagePoint,
    target_source_id: str | None,
    stars: tuple[StarCircle, ...],
    symbols: tuple[SourceGeometry, ...],
    associated_star_ids: frozenset[str],
    related_star_ids: frozenset[str],
    config: SourceAssociationStyle,
) -> tuple[float, float, float, float, float, float, str | None]:
    """Score the visual corridor and ownership of a source-to-label pairing."""
    bounds = candidate.bounds
    own_stars = tuple(star for star in stars if associated_star_ids & star.star_ids)
    own_symbols = tuple(symbol for symbol in symbols if symbol.id == target_source_id)
    owner_options = [
        (
            candidate_star_edge_distance_mm(source, candidate, visible_text=True),
            star_source_facing_point(
                source,
                min(
                    candidate.glyph_bounds or (bounds,),
                    key=lambda rect: star_rect_edge_distance_mm(source, rect),
                ),
            ),
        )
        for source in own_stars
    ] + [
        (source_edge_distance(source, bounds), source_facing_point(source, bounds))
        for source in own_symbols
    ]
    owner_gap, corridor_start = min(
        owner_options,
        key=lambda item: item[0],
        default=(_point_rect_distance(target_anchor, bounds), target_anchor),
    )
    source_distance = max(
        0.0,
        config.preferred_min_gap_mm - owner_gap,
        owner_gap - config.preferred_max_gap_mm,
    )
    corridor_end = clamp_point_to_rect(corridor_start, bounds)
    corridor = 0.0
    ambiguity = 0.0
    competing_owner = 0.0
    competing_owner_id: str | None = None
    strongest_competitor = 0.0
    foreign_object_proximity = 0.0
    ambiguity_limit = max(0.0, owner_gap) + config.ambiguity_margin_mm

    for star in stars:
        if related_star_ids & star.star_ids:
            continue
        if any(
            source.ignore_interior_stars and source_contains_point(source, star.center)
            for source in own_symbols
        ):
            continue
        importance = _star_importance(star.radius_mm)
        if _point_segment_distance(star.center, corridor_start, corridor_end) < (
            star.radius_mm + config.corridor_margin_mm
        ):
            corridor += importance
        gap = star_rect_edge_distance_mm(star, bounds)
        if gap < ambiguity_limit:
            ambiguity += importance * (ambiguity_limit - gap) / max(
                config.ambiguity_margin_mm, 1e-9
            )
        if gap < owner_gap:
            strength = importance * (owner_gap - gap + config.ambiguity_margin_mm) / max(
                config.ambiguity_margin_mm, 1e-9
            )
            competing_owner += strength
            if strength > strongest_competitor:
                strongest_competitor = strength
                competing_owner_id = star.id

    for symbol in symbols:
        if symbol.id == target_source_id:
            continue
        if _point_segment_distance(symbol.center, corridor_start, corridor_end) < (
            symbol.collision_radius_mm + config.corridor_margin_mm
        ):
            corridor += 1.0
        gap = source_extent_edge_distance(symbol, bounds)
        if gap < ambiguity_limit:
            ambiguity += (ambiguity_limit - gap) / max(config.ambiguity_margin_mm, 1e-9)
        if gap < owner_gap:
            strength = (owner_gap - gap + config.ambiguity_margin_mm) / max(
                config.ambiguity_margin_mm, 1e-9
            )
            competing_owner += strength
            if strength > strongest_competitor:
                strongest_competitor = strength
                competing_owner_id = symbol.id
        if gap < config.foreign_object_clear_mm:
            fraction = (config.foreign_object_clear_mm - gap) / config.foreign_object_clear_mm
            foreign_object_proximity += fraction * fraction
    return (
        source_distance,
        max(0.0, owner_gap),
        corridor,
        ambiguity,
        competing_owner,
        foreign_object_proximity,
        competing_owner_id,
    )


def _glyph_proximity_cost(
    candidate: LabelCandidate,
    stars: tuple[StarCircle, ...],
    associated_star_ids: frozenset[str],
    related_star_ids: frozenset[str],
    owner_sources: tuple[SourceGeometry, ...],
    config: SourceAssociationStyle,
) -> tuple[float, _ClosestForeignStar | None]:
    if not candidate.glyph_bounds and not candidate.whitespace_bounds:
        return 0.0, None
    glyph_left = min(
        (rect.left_mm for rect in candidate.glyph_bounds),
        default=candidate.bounds.left_mm,
    )
    glyph_right = max(
        (rect.right_mm for rect in candidate.glyph_bounds), default=candidate.bounds.right_mm
    )
    glyph_top = min(
        (rect.top_mm for rect in candidate.glyph_bounds),
        default=candidate.bounds.top_mm,
    )
    glyph_bottom = max(
        (rect.bottom_mm for rect in candidate.glyph_bounds), default=candidate.bounds.bottom_mm
    )
    total = 0.0
    closest: _ClosestForeignStar | None = None
    for star in stars:
        if related_star_ids & star.star_ids:
            continue
        if any(
            source.ignore_interior_stars and source_contains_point(source, star.center)
            for source in owner_sources
        ):
            continue
        glyph_distance = min(
            (
                star_rect_edge_distance_mm(star, rect)
                for rect in candidate.glyph_bounds
            ),
            default=float("inf"),
        )
        whitespace_distance = min(
            (
                star_rect_edge_distance_mm(star, rect)
                for rect in candidate.whitespace_bounds
            ),
            default=float("inf"),
        )
        nearest = min(glyph_distance, whitespace_distance)
        if closest is None or nearest < closest.distance_mm:
            closest = _ClosestForeignStar(star.id, star.radius_mm, nearest)
        if nearest >= config.glyph_clear_mm:
            continue
        fraction = (config.glyph_clear_mm - nearest) / config.glyph_clear_mm
        factor = config.whitespace_factor if whitespace_distance <= glyph_distance else 1.0
        if glyph_top <= star.center.y_mm <= glyph_bottom and (
            star.center.x_mm < glyph_left or star.center.x_mm > glyph_right
        ):
            factor *= config.glyph_inline_factor
        total += _star_importance(star.radius_mm) * factor * fraction * fraction
    return total, closest


def _star_importance(radius_mm: float) -> float:
    return min(2.0, max(0.15, radius_mm / 0.6))


def _circle_facing_point(center: PagePoint, radius_mm: float, rect: PageRect) -> PagePoint:
    near = clamp_point_to_rect(center, rect)
    dx = near.x_mm - center.x_mm
    dy = near.y_mm - center.y_mm
    length = (dx * dx + dy * dy) ** 0.5
    if length <= 0.0:
        return center
    return PagePoint(
        center.x_mm + dx / length * radius_mm,
        center.y_mm + dy / length * radius_mm,
    )


def _point_distance(first: PagePoint, second: PagePoint) -> float:
    return ((first.x_mm - second.x_mm) ** 2 + (first.y_mm - second.y_mm) ** 2) ** 0.5


def _point_rect_distance(point: PagePoint, rect: PageRect) -> float:
    return _point_distance(point, clamp_point_to_rect(point, rect))


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
