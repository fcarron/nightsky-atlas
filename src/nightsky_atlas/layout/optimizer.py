"""Deterministic label optimizer.

Strategy (``AGENTS.md`` section 15.3): priority-ordered greedy placement
followed by a deterministic local repair pass.  No stochastic search is used,
so the result is reproducible.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import Any

from nightsky_atlas.atlas.config import StyleConfig
from nightsky_atlas.catalog.models import DsoType
from nightsky_atlas.chart.page import PagePoint, PageRect, PageTransform
from nightsky_atlas.layout.association import (
    SourceGeometry,
    dso_source_geometries,
    source_edge_distance,
    source_geometries_overlap,
    source_intersects_rect,
)
from nightsky_atlas.layout.candidates import direction_preference_rank
from nightsky_atlas.layout.geometry import (
    circle_intersects_rect,
    rects_overlap,
)
from nightsky_atlas.layout.labels import constellation_label_anchors
from nightsky_atlas.layout.leader_lines import (
    leader_line_for,
    prepare_leader_routing_context,
    resolve_leader_lines,
)
from nightsky_atlas.layout.models import Label, LabelCandidate
from nightsky_atlas.layout.scoring import (
    CostBreakdown,
    CostWeights,
    StarCircle,
    SymbolCircle,
    candidate_star_edge_distance_mm,
    foreign_star_hard_min_mm,
    rescore_candidate_interactions,
    score_candidate,
    star_source_bounds,
)
from nightsky_atlas.layout.spatial import RectIndex
from nightsky_atlas.layout.targeted_leaders import add_targeted_dso_leaders
from nightsky_atlas.layout.text_geometry import (
    candidate_ink_bounds,
    label_collision_bounds,
)
from nightsky_atlas.render.constellation_lines import resolve_constellation_lines
from nightsky_atlas.render.double_stars import (
    printed_star_obstacles,
    related_member_star_ids,
    source_member_star_ids,
)
from nightsky_atlas.render.symbols import dso_symbol_extent
from nightsky_atlas.scene.models import ChartScene

__all__ = ["OptimizationResult", "layout_cost", "layout_hash", "optimize_labels"]

_IMPORTANT_STAR_MAGNITUDE = 6.0
_CROWDING_RADIUS_MM = 6.0
_EDGE_MARGIN_MM = 8.0
_MAX_REPAIR_PASSES = 4
_GRID_CELL_MM = 8.0
_SOURCE_INDEX_CACHE: dict[
    int, tuple[tuple[SourceGeometry, ...], RectIndex[SourceGeometry]]
] = {}


@dataclass(frozen=True, slots=True)
class OptimizationResult:
    """The optimized layout and its before/after diagnostics."""

    labels: tuple[Label, ...]
    cost_before: float
    cost_after: float
    placed_count: int
    hidden_count: int
    component_totals_before: dict[str, float]
    component_totals_after: dict[str, float]
    label_diagnostics: dict[str, dict[str, Any]]
    metrics: dict[str, Any]


class _CandidateScoreCache:
    def __init__(
        self,
        anchors: dict[str, PagePoint],
        printable: PageRect,
        symbols_index: RectIndex[SymbolCircle],
        sources: tuple[SourceGeometry, ...],
        stars_index: RectIndex[StarCircle],
        stars: tuple[StarCircle, ...],
        style: StyleConfig,
        weights: CostWeights,
        constellation_lines: tuple[tuple[PagePoint, PagePoint], ...],
        furniture: tuple[PageRect, ...] = (),
    ) -> None:
        self.anchors = anchors
        self.printable = printable
        self.symbols_index = symbols_index
        self.sources = sources
        self.source_by_id = {source.id: source for source in sources}
        self.stars_index = stars_index
        self.stars = stars
        self.style = style
        self.weights = weights
        self.constellation_lines = constellation_lines
        self.furniture = furniture
        self._static: dict[tuple[str, str], CostBreakdown] = {}
        self._geometry: dict[
            tuple[str, str], tuple[tuple[SymbolCircle, ...], tuple[StarCircle, ...]]
        ] = {}
        self._validity: dict[tuple[str, str], tuple[bool, PageRect]] = {}

    def geometry(
        self,
        label: Label,
        candidate: LabelCandidate,
    ) -> tuple[tuple[SymbolCircle, ...], tuple[StarCircle, ...]]:
        key = (label.id, candidate.id)
        geometry = self._geometry.get(key)
        if geometry is None:
            geometry = (
                tuple(self.symbols_index.query(candidate.bounds)),
                _nearby_stars(
                    label, candidate.bounds, self.stars_index, self.stars, self.style
                ),
            )
            self._geometry[key] = geometry
        return geometry

    def valid(
        self,
        label: Label,
        candidate: LabelCandidate,
        placed_bounds: tuple[PageRect, ...],
    ) -> bool:
        key = (label.id, candidate.id)
        validity = self._validity.get(key)
        if validity is None:
            symbols, stars = self.geometry(label, candidate)
            validity = (
                _is_valid(
                    label,
                    candidate,
                    (),
                    self.printable,
                    symbols,
                    stars,
                    self.style,
                    self.furniture,
                    self.sources,
                    self.source_by_id,
                ),
                _collision_bounds(label, candidate, self.style),
            )
            self._validity[key] = validity
        static_valid, collision_bounds = validity
        return static_valid and not any(
            rects_overlap(collision_bounds, other) for other in placed_bounds
        )

    def cost(
        self,
        label: Label,
        candidate: LabelCandidate,
        placed_bounds: tuple[PageRect, ...],
        *,
        nearby_symbols: tuple[SymbolCircle, ...] | None = None,
        nearby_stars: tuple[StarCircle, ...] | None = None,
    ) -> float:
        return self.breakdown(
            label,
            candidate,
            placed_bounds,
            nearby_symbols=nearby_symbols,
            nearby_stars=nearby_stars,
        ).total(self.weights)

    def breakdown(
        self,
        label: Label,
        candidate: LabelCandidate,
        placed_bounds: tuple[PageRect, ...],
        *,
        nearby_symbols: tuple[SymbolCircle, ...] | None = None,
        nearby_stars: tuple[StarCircle, ...] | None = None,
    ) -> CostBreakdown:
        key = (label.id, candidate.id)
        static = self._static.get(key)
        if static is None:
            if nearby_symbols is None or nearby_stars is None:
                symbols, stars = self.geometry(label, candidate)
            else:
                symbols, stars = nearby_symbols, nearby_stars
                self._geometry.setdefault(key, (symbols, stars))
            static = score_candidate(
                candidate,
                target_anchor=_anchor_for(label, self.anchors, candidate),
                placed_bounds=(),
                symbols=symbols,
                stars=stars,
                associated_star_ids=_associated_star_ids(label, stars),
                related_star_ids=_related_star_ids(label, stars),
                star_clearance=self.style.label.star_clearance,
                target_source_id=_association_source_id(label),
                source_association=self.style.label.source_association,
                dso_placement=self.style.label.dso_placement,
                is_dso_label=label.id.startswith("label:dso:"),
                source_symbols=_nearby_sources(label, candidate.bounds, self.sources, self.style),
                association_scale=_association_scale(label, self.style),
                printable=self.printable,
                crowding_radius_mm=_CROWDING_RADIUS_MM,
                weights=self.weights,
                edge_margin_mm=_EDGE_MARGIN_MM,
                constellation_lines=self.constellation_lines,
            )
            self._static[key] = static
        return rescore_candidate_interactions(
            static,
            candidate,
            placed_bounds,
            crowding_radius_mm=_CROWDING_RADIUS_MM,
            dso_placement=self.style.label.dso_placement,
            is_dso_label=label.id.startswith("label:dso:"),
        )


def _symbol_circles(
    scene: ChartScene, transform: PageTransform, style: StyleConfig
) -> tuple[SymbolCircle, ...]:
    symbols: list[SymbolCircle] = []
    for scene_dso in scene.deep_sky_objects:
        if not scene_dso.symbol_visible:
            continue
        extent = dso_symbol_extent(scene_dso.dso, mm_per_deg=transform.mm_per_deg, style=style)
        symbols.append(
            SymbolCircle(
                center=transform.to_page(scene_dso.chart_point),
                radius_mm=extent.collision_radius_mm,
                id=scene_dso.dso.id,
            )
        )
    return tuple(symbols)


def _star_circles(
    scene: ChartScene, transform: PageTransform, style: StyleConfig
) -> tuple[StarCircle, ...]:
    """Return every actual printed stellar disk for label-clearance geometry."""
    return tuple(
        StarCircle(
            id=star.id,
            star_ids=star.star_ids,
            center=star.page_point,
            radius_mm=star.radius_mm,
            system_ids=star.system_ids,
            marker_length_mm=star.marker_length_mm,
            marker_line_width_mm=star.marker_line_width_mm,
        )
        for star in printed_star_obstacles(scene, transform, style)
    )


def _target_anchors(
    labels: tuple[Label, ...], scene: ChartScene, transform: PageTransform, style: StyleConfig
) -> dict[str, PagePoint]:
    anchors: dict[str, PagePoint] = {}
    for scene_star in scene.stars:
        anchors[scene_star.star.id] = transform.to_page(scene_star.chart_point)
    system_points: dict[str, list[PagePoint]] = {}
    for obstacle in printed_star_obstacles(scene, transform, style):
        for star_id in obstacle.star_ids:
            anchors[star_id] = obstacle.page_point
        for system_id in obstacle.system_ids:
            system_points.setdefault(system_id, []).append(obstacle.page_point)
    for system_id, points in system_points.items():
        anchors[system_id] = PagePoint(
            sum(point.x_mm for point in points) / len(points),
            sum(point.y_mm for point in points) / len(points),
        )
    for scene_dso in scene.deep_sky_objects:
        anchors[scene_dso.dso.id] = transform.to_page(scene_dso.chart_point)
    anchors.update(constellation_label_anchors(scene, transform, style))
    return anchors


def _printable(transform: PageTransform) -> PageRect:
    return PageRect(
        left_mm=transform.page.margin_mm,
        top_mm=transform.page.margin_mm,
        width_mm=transform.page.printable_width_mm,
        height_mm=transform.page.printable_height_mm,
    )


def _anchor_for(
    label: Label, anchors: dict[str, PagePoint], candidate: LabelCandidate
) -> PagePoint:
    anchor = anchors.get(label.target_id)
    if anchor is not None:
        return anchor
    return candidate.bounds.center


def _symbol_bounds(symbol: SymbolCircle) -> PageRect:
    return PageRect(
        left_mm=symbol.center.x_mm - symbol.radius_mm,
        top_mm=symbol.center.y_mm - symbol.radius_mm,
        width_mm=2.0 * symbol.radius_mm,
        height_mm=2.0 * symbol.radius_mm,
    )


def _collision_bounds(
    label: Label, candidate: LabelCandidate, style: StyleConfig
) -> PageRect:
    return label_collision_bounds(
        label,
        candidate,
        ink_clearance_mm=style.label.dso_placement.label_label_ink_clearance_mm,
    )


def _labels_overlap(
    first: Label,
    first_candidate: LabelCandidate,
    second: Label,
    second_candidate: LabelCandidate,
    style: StyleConfig,
) -> bool:
    first_bounds = _collision_bounds(first, first_candidate, style)
    second_bounds = _collision_bounds(second, second_candidate, style)
    return rects_overlap(first_bounds, second_bounds)


def _build_symbol_index(symbols: tuple[SymbolCircle, ...]) -> RectIndex[SymbolCircle]:
    index: RectIndex[SymbolCircle] = RectIndex(_GRID_CELL_MM)
    for position, symbol in enumerate(symbols):
        index.set(f"symbol:{position}", _symbol_bounds(symbol), symbol)
    return index


def _nearby_sources(
    label: Label,
    bounds: PageRect,
    sources: tuple[SourceGeometry, ...],
    style: StyleConfig,
) -> tuple[SourceGeometry, ...]:
    """Limit DSO association scoring to the local source neighborhood."""
    owner_id = _association_source_id(label)
    placement = style.label.dso_placement
    association = style.label.source_association
    margin = max(placement.candidate_edge_gaps_mm) + association.corridor_margin_mm + 1.0
    margin_sq = margin**2
    source_index = _source_spatial_index(sources)
    nearby = []
    for source in source_index.query(bounds, margin_mm=margin):
        radius = source.collision_radius_mm
        dx = max(
            bounds.left_mm - (source.center.x_mm + radius),
            0.0,
            source.center.x_mm - radius - bounds.right_mm,
        )
        dy = max(
            bounds.top_mm - (source.center.y_mm + radius),
            0.0,
            source.center.y_mm - radius - bounds.bottom_mm,
        )
        if source.id == owner_id or dx * dx + dy * dy <= margin_sq:
            nearby.append(source)
    return tuple(nearby)


def _source_spatial_index(
    sources: tuple[SourceGeometry, ...],
) -> RectIndex[SourceGeometry]:
    key = id(sources)
    cached = _SOURCE_INDEX_CACHE.get(key)
    if cached is not None and cached[0] is sources:
        return cached[1]
    index: RectIndex[SourceGeometry] = RectIndex(_GRID_CELL_MM)
    for source in sources:
        radius = source.collision_radius_mm
        index.set(
            source.id,
            PageRect(
                source.center.x_mm - radius,
                source.center.y_mm - radius,
                2.0 * radius,
                2.0 * radius,
            ),
            source,
        )
    if len(_SOURCE_INDEX_CACHE) >= 4:
        _SOURCE_INDEX_CACHE.pop(next(iter(_SOURCE_INDEX_CACHE)))
    _SOURCE_INDEX_CACHE[key] = (sources, index)
    return index


def _ownership_result(
    label: Label,
    bounds: PageRect,
    sources: tuple[SourceGeometry, ...],
    style: StyleConfig,
    *,
    all_sources: bool = False,
) -> tuple[float, float | None, SourceGeometry | None, bool]:
    considered = sources if all_sources else _nearby_sources(label, bounds, sources, style)
    owner = next((source for source in considered if source.id == label.target_id), None)
    if owner is None:
        return 0.0, None, None, False
    owner_gap = source_edge_distance(owner, bounds)
    competitors = tuple(
        source for source in considered if source.id != label.target_id
    )
    nearest = min(
        competitors,
        key=lambda source: (source_edge_distance(source, bounds), source.id),
        default=None,
    )
    if nearest is None:
        return owner_gap, None, None, False
    foreign_gap = source_edge_distance(nearest, bounds)
    margin = foreign_gap - owner_gap
    isolated_galaxy = (
        owner.source_type == DsoType.GALAXY
        and nearest.source_type == DsoType.GALAXY
    )
    overlap_exception = isolated_galaxy and source_geometries_overlap(owner, nearest)
    near_hard_violation = (
        isolated_galaxy
        and margin < style.label.dso_placement.ownership_margin_hard_limit_mm
        and not overlap_exception
    )
    return owner_gap, margin, nearest, near_hard_violation


def _build_star_index(stars: tuple[StarCircle, ...]) -> RectIndex[StarCircle]:
    index: RectIndex[StarCircle] = RectIndex(_GRID_CELL_MM)
    for star in stars:
        index.set(star.id, star_source_bounds(star), star)
    return index


def _associated_star_ids(label: Label, stars: tuple[StarCircle, ...]) -> frozenset[str]:
    """Return the physical printed members owned by a label's source."""
    return source_member_star_ids(label.target_id, stars)


def _related_star_ids(label: Label, stars: tuple[StarCircle, ...]) -> frozenset[str]:
    """Return all printed components semantically related to a star label."""
    return related_member_star_ids(label.target_id, stars)


def _resolved_weights(style: StyleConfig, weights: CostWeights | None) -> CostWeights:
    if weights is not None:
        return weights
    clearance = style.label.star_clearance
    return CostWeights(
        label_foreign_star_clearance=clearance.foreign.weight,
        label_associated_star_clearance=clearance.associated.clearance_weight,
        label_association_distance=clearance.associated.distance_weight,
        label_source_distance=style.label.source_association.distance_weight,
        label_source_facing_edge_distance=0.0,
        label_source_corridor=style.label.source_association.corridor_weight,
        label_competing_source_ambiguity=style.label.source_association.ambiguity_weight,
        label_competing_owner=style.label.source_association.competing_owner_weight,
        label_glyph_proximity=style.label.source_association.glyph_weight,
        label_foreign_object_proximity=(
            style.label.source_association.foreign_object_weight
        ),
        label_ownership_margin=style.label.dso_placement.ownership_margin_weight,
    )


def _star_query_margin_mm(style: StyleConfig) -> float:
    foreign = style.label.star_clearance.foreign
    return max(
        foreign.soft_clear_mm + style.star.max_diameter_mm / 2.0 * foreign.radius_clearance_factor,
        style.label.star_clearance.associated.preferred_max_mm,
    )


def _nearby_stars(
    label: Label,
    bounds: PageRect,
    index: RectIndex[StarCircle],
    stars: tuple[StarCircle, ...],
    style: StyleConfig,
) -> tuple[StarCircle, ...]:
    queried = tuple(index.query(bounds, margin_mm=_star_query_margin_mm(style)))
    if not label.id.startswith("label:star:"):
        return tuple(sorted(queried, key=lambda star: star.id))
    known_ids = {star.id for star in queried}
    associated = tuple(
        star for star in stars if label.target_id in star.star_ids and star.id not in known_ids
    )
    related_ids = _related_star_ids(label, stars)
    related = tuple(
        star
        for star in stars
        if related_ids & star.star_ids and star.id not in known_ids
    )
    by_id = {star.id: star for star in (*queried, *associated, *related)}
    return tuple(sorted(by_id.values(), key=lambda star: star.id))


def _is_valid(
    label: Label,
    candidate: LabelCandidate,
    placed_bounds: tuple[PageRect, ...],
    printable: PageRect,
    symbols: tuple[SymbolCircle, ...],
    stars: tuple[StarCircle, ...],
    style: StyleConfig,
    furniture: tuple[PageRect, ...] = (),
    source_geometries: tuple[SourceGeometry, ...] | None = None,
    source_by_id: dict[str, SourceGeometry] | None = None,
) -> bool:
    bounds = candidate.bounds
    collision_bounds = _collision_bounds(label, candidate, style)
    if (
        bounds.left_mm < printable.left_mm
        or bounds.top_mm < printable.top_mm
        or bounds.right_mm > printable.right_mm
        or bounds.bottom_mm > printable.bottom_mm
    ):
        return False
    if any(rects_overlap(collision_bounds, other) for other in placed_bounds):
        return False
    if any(rects_overlap(bounds, obstacle) for obstacle in furniture):
        return False
    source_bounds = (
        candidate_ink_bounds(candidate) if label.id.startswith("label:dso:") else bounds
    )
    if source_geometries is None:
        if any(
            circle_intersects_rect(symbol.center, symbol.radius_mm, source_bounds)
            for symbol in symbols
        ):
            return False
    else:
        if source_by_id is None:
            source_by_id = {source.id: source for source in source_geometries}
        source_conflict = any(
            source_intersects_rect(source_by_id[symbol.id], source_bounds)
            for symbol in symbols
            if symbol.id in source_by_id
        )
        if source_conflict:
            return False
    if label.id.startswith("label:dso:") and source_geometries is not None:
        _, _, _, wrong_owner = _ownership_result(
            label, candidate_ink_bounds(candidate), source_geometries, style
        )
        if wrong_owner:
            return False
    related = _related_star_ids(label, stars)
    for star in stars:
        hard_min = style.label.star_clearance.associated.hard_min_mm if (
            related & star.star_ids
        ) else foreign_star_hard_min_mm(star.radius_mm, style.label.star_clearance)
        if candidate_star_edge_distance_mm(
            star,
            candidate,
            visible_text=label.id.startswith(("label:star:", "label:dso:")),
        ) < hard_min:
            return False
    return True


def _preference_rank(candidate: LabelCandidate) -> float:
    return direction_preference_rank(candidate.position)


def _association_scale(label: Label, style: StyleConfig) -> float:
    compact_text = "".join(label.text.split())
    if label.id.startswith("label:star:") and len(compact_text) <= 3:
        return style.label.source_association.compact_label_factor
    if label.id.startswith("label:dso:") and len(compact_text) <= 4:
        return style.label.dso_placement.compact_label_factor
    return 1.0


def _association_source_id(label: Label) -> str | None:
    if label.id.startswith(("label:star:", "label:dso:")):
        return label.target_id
    return None


def _dso_conflict_components(
    labels: tuple[Label, ...], style: StyleConfig
) -> tuple[tuple[str, ...], ...]:
    """Connect DSO labels whose legal candidate regions can compete for space."""
    dso_labels = tuple(sorted(
        (label for label in labels if label.id.startswith("label:dso:")),
        key=lambda label: label.id,
    ))
    adjacency = {label.id: set() for label in dso_labels}
    index: RectIndex[tuple[str, PageRect]] = RectIndex(_GRID_CELL_MM)
    sequence = 0
    for label in dso_labels:
        for candidate in label.candidates:
            bounds = _collision_bounds(label, candidate, style)
            for other_id, other_bounds in index.query(bounds):
                if other_id != label.id and rects_overlap(bounds, other_bounds):
                    adjacency[label.id].add(other_id)
                    adjacency[other_id].add(label.id)
            index.set(
                f"candidate:{sequence}",
                bounds,
                (label.id, bounds),
            )
            sequence += 1
    components: list[tuple[str, ...]] = []
    remaining = set(adjacency)
    while remaining:
        root = min(remaining)
        pending = [root]
        members: set[str] = set()
        while pending:
            current = pending.pop()
            if current in members:
                continue
            members.add(current)
            pending.extend(sorted(adjacency[current] - members, reverse=True))
        remaining.difference_update(members)
        components.append(tuple(sorted(members)))
    return tuple(sorted(components, key=lambda component: (component[0], len(component))))


def _joint_component_search(
    component: tuple[str, ...],
    labels_by_id: dict[str, Label],
    placements: dict[str, str | None],
    anchors: dict[str, PagePoint],
    printable: PageRect,
    symbols_index: RectIndex[SymbolCircle],
    sources: tuple[SourceGeometry, ...],
    stars_index: RectIndex[StarCircle],
    stars: tuple[StarCircle, ...],
    style: StyleConfig,
    weights: CostWeights,
    furniture: tuple[PageRect, ...],
    constellation_lines: tuple[tuple[PagePoint, PagePoint], ...],
    cost_cache: _CandidateScoreCache,
) -> tuple[dict[str, str] | None, int]:
    """Bounded deterministic beam search for one small DSO conflict component."""
    component_set = set(component)
    ordered = tuple(sorted(
        (labels_by_id[label_id] for label_id in component),
        key=lambda label: (-label.priority, label.id),
    ))
    fixed_bounds = tuple(
        _collision_bounds(
            labels_by_id[label_id],
            labels_by_id[label_id].candidate(candidate_id),
            style,
        )
        for label_id, candidate_id in placements.items()
        if label_id not in component_set
        and candidate_id is not None
        and label_id in labels_by_id
        and labels_by_id[label_id].candidate(candidate_id) is not None
    )
    fixed_index: RectIndex[PageRect] = RectIndex(_GRID_CELL_MM)
    for index, bounds in enumerate(fixed_bounds):
        fixed_index.set(str(index), bounds, bounds)
    beam: list[tuple[int, float, tuple[str, ...]]] = [(0, 0.0, ())]
    visited = 0
    config = style.label.dso_placement
    for label in ordered:
        expanded: list[tuple[int, float, tuple[str, ...]]] = []
        for hard_count, total_cost, assignment in beam:
            assigned_bounds = tuple(
                _collision_bounds(
                    previous,
                    previous.candidate(candidate_id),
                    style,
                )
                for previous, candidate_id in zip(ordered, assignment, strict=False)
            )
            for candidate in label.candidates:
                visited += 1
                if visited > config.joint_node_budget:
                    return None, visited
                occupied = (
                    *fixed_index.query(candidate.bounds, margin_mm=_CROWDING_RADIUS_MM),
                    *assigned_bounds,
                )
                valid = cost_cache.valid(label, candidate, occupied)
                cost = cost_cache.cost(label, candidate, occupied)
                penalty = 0.0 if valid else 1_000_000.0
                expanded.append((
                    hard_count + (0 if valid else 1),
                    total_cost + cost + penalty,
                    (*assignment, candidate.id),
                ))
        expanded.sort(key=lambda state: (state[0], state[1], state[2]))
        beam = expanded[: config.joint_beam_width]
        if not beam:
            return None, visited
    best = beam[0]
    return (
        {
            label.id: candidate_id
            for label, candidate_id in zip(ordered, best[2], strict=True)
        },
        visited,
    )


def _joint_dso_optimize(
    labels: tuple[Label, ...],
    placements: dict[str, str | None],
    anchors: dict[str, PagePoint],
    printable: PageRect,
    placed_index: RectIndex[PageRect],
    symbols_index: RectIndex[SymbolCircle],
    sources: tuple[SourceGeometry, ...],
    stars_index: RectIndex[StarCircle],
    stars: tuple[StarCircle, ...],
    style: StyleConfig,
    weights: CostWeights,
    furniture: tuple[PageRect, ...],
    constellation_lines: tuple[tuple[PagePoint, PagePoint], ...],
    cost_cache: _CandidateScoreCache,
) -> tuple[dict[str, str | None], dict[str, Any]]:
    """Optimize independent small DSO conflict components jointly.

    Components too large for the configured bounded search retain the
    deterministic greedy/local-repair solution; that local repair is the
    bounded fallback and does not alter the selected label set.
    """
    labels_by_id = {label.id: label for label in labels}
    components = _dso_conflict_components(labels, style)
    stats: dict[str, Any] = {
        "component_count": len(components),
        "component_sizes": [len(component) for component in components],
        "components": [list(component) for component in components],
        "max_component_size": max(map(len, components), default=0),
        "joint_components_searched": 0,
        "components_using_local_fallback": 0,
        "fallback_components": [],
        "component_search_budget_hits": 0,
        "search_budget_hit_components": [],
        "joint_search_nodes": 0,
    }
    for component in components:
        if len(component) < 2:
            continue
        if len(component) > style.label.dso_placement.joint_max_component_labels:
            stats["components_using_local_fallback"] += 1
            stats["fallback_components"].append({
                "component_index": len(stats["fallback_components"]),
                "size": len(component),
                "label_ids": list(component),
                "reason": "component_too_large",
            })
            continue
        result, visited = _joint_component_search(
            component,
            labels_by_id,
            placements,
            anchors,
            printable,
            symbols_index,
            sources,
            stars_index,
            stars,
            style,
            weights,
            furniture,
            constellation_lines,
            cost_cache,
        )
        stats["joint_search_nodes"] += visited
        if result is None:
            stats["component_search_budget_hits"] += 1
            stats["components_using_local_fallback"] += 1
            stats["search_budget_hit_components"].append(list(component))
            stats["fallback_components"].append({
                "component_index": len(stats["fallback_components"]),
                "size": len(component),
                "label_ids": list(component),
                "reason": "search_budget_reached",
            })
            continue
        stats["joint_components_searched"] += 1
        for label_id, candidate_id in result.items():
            placements[label_id] = candidate_id
            label = labels_by_id[label_id]
            candidate = label.candidate(candidate_id)
            if candidate is not None:
                bounds = _collision_bounds(label, candidate, style)
                placed_index.set(label_id, bounds, bounds)
    return placements, stats


def _repair_dso_hard_conflicts(
    labels: tuple[Label, ...],
    placements: dict[str, str | None],
    anchors: dict[str, PagePoint],
    printable: PageRect,
    symbols_index: RectIndex[SymbolCircle],
    sources: tuple[SourceGeometry, ...],
    stars_index: RectIndex[StarCircle],
    stars: tuple[StarCircle, ...],
    style: StyleConfig,
    weights: CostWeights,
    furniture: tuple[PageRect, ...],
    constellation_lines: tuple[tuple[PagePoint, PagePoint], ...],
    cost_cache: _CandidateScoreCache | None = None,
) -> tuple[dict[str, str | None], dict[str, Any]]:
    """Resolve remaining local hard conflicts without suppressing any label."""
    labels_by_id = {label.id: label for label in labels}
    if cost_cache is None:
        cost_cache = _CandidateScoreCache(
            anchors,
            printable,
            symbols_index,
            sources,
            stars_index,
            stars,
            style,
            weights,
            constellation_lines,
            furniture,
        )
    stats: dict[str, Any] = {
        "single_conflict_moves": 0,
        "pair_conflict_moves": 0,
        "unresolved_label_pairs": [],
        "neighborhood_searches": 0,
        "neighborhood_moves": 0,
        "neighborhood_search_budget_hits": 0,
        "neighborhood_search_nodes": 0,
        "neighborhood_search_limit_reached": False,
        "neighborhood_sizes": [],
    }
    empty_index: RectIndex[PageRect] = RectIndex(_GRID_CELL_MM)
    static_rejections: dict[tuple[str, str], str | None] = {}

    def static_rejection(label: Label, candidate: LabelCandidate) -> str | None:
        key = (label.id, candidate.id)
        if key not in static_rejections:
            static_rejections[key] = _candidate_rejection_reason(
                label,
                candidate,
                empty_index,
                symbols_index,
                stars_index,
                stars,
                printable,
                style,
                furniture=furniture,
                source_geometries=sources,
            )
        return static_rejections[key]

    def current_labels() -> tuple[Label, ...]:
        return tuple(
            label.with_placement(
                placements.get(label.id), hidden=placements.get(label.id) is None
            )
            for label in labels
        )

    def source_conflicts(label: Label, candidate: LabelCandidate) -> bool:
        source_bounds = (
            candidate_ink_bounds(candidate)
            if label.id.startswith("label:dso:")
            else candidate.bounds
        )
        nearby_ids = {symbol.id for symbol in symbols_index.query(source_bounds)}
        return any(
            source.id in nearby_ids
            and circle_intersects_rect(
                source.center, source.collision_radius_mm, source_bounds
            )
            and source_edge_distance(source, source_bounds) <= 0.0
            for source in sources
        )

    def legal_candidates(
        label: Label,
        placed_index: RectIndex[PageRect],
    ) -> list[tuple[float, str, LabelCandidate]]:
        placed_index.discard(label.id)
        choices = []
        for candidate in label.candidates:
            if static_rejection(label, candidate) is not None:
                continue
            collision_bounds = _collision_bounds(label, candidate, style)
            if any(
                rects_overlap(collision_bounds, other)
                for other in placed_index.query(
                    collision_bounds,
                    margin_mm=style.label.dso_placement.label_label_ink_clearance_mm or 0.0,
                    exclude=label.id,
                )
            ):
                continue
            nearby_bounds = tuple(
                placed_index.query(
                    candidate.bounds,
                    margin_mm=_CROWDING_RADIUS_MM,
                    exclude=label.id,
                )
            )
            choices.append(
                (cost_cache.cost(label, candidate, nearby_bounds), candidate.id, candidate)
            )
        return sorted(choices, key=lambda item: (item[0], item[1]))

    def hard_conflict_count(candidate_labels: tuple[Label, ...]) -> int:
        placed = tuple(
            (label, label.effective_candidate())
            for label in candidate_labels
            if not label.hidden and label.effective_candidate() is not None
        )
        label_pairs = {
            tuple(sorted((first.id, second.id)))
            for index, (first, first_candidate) in enumerate(placed)
            for second, second_candidate in placed[index + 1 :]
            if first_candidate is not None
            and second_candidate is not None
            and _labels_overlap(first, first_candidate, second, second_candidate, style)
        }
        page_issues = sum(
            1
            for _, candidate in placed
            if candidate is not None
            and (
                candidate.bounds.left_mm < printable.left_mm
                or candidate.bounds.top_mm < printable.top_mm
                or candidate.bounds.right_mm > printable.right_mm
                or candidate.bounds.bottom_mm > printable.bottom_mm
            )
        )
        dso_pairs = set()
        for label, candidate in placed:
            if candidate is None:
                continue
            visible_bounds = (
                candidate_ink_bounds(candidate)
                if label.id.startswith("label:dso:")
                else candidate.bounds
            )
            nearby_ids = {symbol.id for symbol in symbols_index.query(visible_bounds)}
            for source in sources:
                if (
                    source.id in nearby_ids
                    and circle_intersects_rect(
                        source.center, source.collision_radius_mm, visible_bounds
                    )
                    and source_edge_distance(source, visible_bounds) <= 0.0
                ):
                    dso_pairs.add((label.id, source.id))
        return len(label_pairs) + len(dso_pairs) + page_issues

    def seed_conflicts(candidate_labels: tuple[Label, ...]) -> list[tuple[str, ...]]:
        placed = tuple(
            (label, label.effective_candidate())
            for label in candidate_labels
            if not label.hidden and label.effective_candidate() is not None
        )
        seeds: set[tuple[str, ...]] = set()
        for index, (first, first_candidate) in enumerate(placed):
            if first_candidate is None or not first.id.startswith("label:dso:"):
                continue
            if (
                source_conflicts(first, first_candidate)
                or first_candidate.bounds.left_mm < printable.left_mm
                or first_candidate.bounds.top_mm < printable.top_mm
                or first_candidate.bounds.right_mm > printable.right_mm
                or first_candidate.bounds.bottom_mm > printable.bottom_mm
            ):
                seeds.add((first.id,))
            for second, second_candidate in placed[index + 1 :]:
                if (
                    second_candidate is not None
                    and second.id.startswith("label:dso:")
                    and _labels_overlap(first, first_candidate, second, second_candidate, style)
                ):
                    seeds.add(tuple(sorted((first.id, second.id))))
        return sorted(seeds)

    def expand_neighborhood(seed: tuple[str, ...]) -> tuple[str, ...]:
        neighborhood = set(seed)
        limit = style.label.dso_placement.hard_repair_neighborhood_labels
        while len(neighborhood) < limit:
            current = current_labels()
            outside = tuple(label for label in current if label.id not in neighborhood)
            outside_index: RectIndex[Label] = RectIndex(_GRID_CELL_MM)
            for other in outside:
                other_candidate = other.effective_candidate()
                if other_candidate is not None and not other.locked:
                    outside_index.set(
                        other.id,
                        _collision_bounds(other, other_candidate, style),
                        other,
                    )
            options: list[tuple[int, str, str, tuple[str, ...]]] = []
            for label_id in sorted(neighborhood):
                label = labels_by_id[label_id]
                for candidate in label.candidates:
                    if static_rejection(label, candidate) is not None:
                        continue
                    blockers = tuple(sorted(
                        other.id
                        for other in outside_index.query(
                            _collision_bounds(label, candidate, style)
                        )
                        if other.effective_candidate() is not None
                        and _labels_overlap(
                            label,
                            candidate,
                            other,
                            other.effective_candidate(),
                            style,
                        )
                    ))
                    options.append((len(blockers), label_id, candidate.id, blockers))
            if not options:
                break
            _, _, _, blockers = min(options, key=lambda item: item[:3])
            if not blockers:
                break
            frequencies: dict[str, int] = {}
            for _, _, _, blocked in options:
                for blocked_id in blocked:
                    frequencies[blocked_id] = frequencies.get(blocked_id, 0) + 1
            slots = limit - len(neighborhood)
            ordered_blockers = sorted(
                blockers,
                key=lambda blocked_id: (
                    -frequencies.get(blocked_id, 0),
                    labels_by_id[blocked_id].priority,
                    blocked_id,
                ),
            )
            additions = ordered_blockers[:slots]
            if not additions:
                break
            neighborhood.update(additions)
        return tuple(sorted(neighborhood))

    # First give each DSO label with a symbol overlap a chance to move while
    # holding its current neighbours fixed.
    for label in sorted(
        (item for item in labels if item.id.startswith("label:dso:")),
        key=lambda item: (-item.priority, item.id),
    ):
        if label.locked:
            continue
        current = label.candidate(placements.get(label.id) or "")
        if current is None:
            continue
        current_outside = (
            current.bounds.left_mm < printable.left_mm
            or current.bounds.top_mm < printable.top_mm
            or current.bounds.right_mm > printable.right_mm
            or current.bounds.bottom_mm > printable.bottom_mm
        )
        if not source_conflicts(label, current) and not current_outside:
            continue
        index = _build_placed_index(current_labels(), style)
        choices = legal_candidates(label, index)
        if choices:
            placements[label.id] = choices[0][1]
            stats["single_conflict_moves"] += 1

    # A label-label collision can have no individually free candidate because
    # its partner occupies all nearby slots. Search those pairs jointly against
    # the otherwise fixed layout, with deterministic finite candidate sets.
    for _ in range(2):
        changed = False
        selected = current_labels()
        selected_by_id = {label.id: label for label in selected}
        overlaps = []
        for index, first in enumerate(selected):
            first_candidate = first.effective_candidate()
            if first_candidate is None:
                continue
            for second in selected[index + 1 :]:
                if not (first.id.startswith("label:dso:") and second.id.startswith("label:dso:")):
                    continue
                second_candidate = second.effective_candidate()
                if second_candidate is not None and _labels_overlap(
                    first, first_candidate, second, second_candidate, style
                ):
                    overlaps.append((first.id, second.id))
        for first_id, second_id in overlaps:
            selected = current_labels()
            selected_by_id = {label.id: label for label in selected}
            first = selected_by_id[first_id]
            second = selected_by_id[second_id]
            first_current = first.effective_candidate()
            second_current = second.effective_candidate()
            if (
                first_current is None
                or second_current is None
                or not _labels_overlap(first, first_current, second, second_current, style)
            ):
                continue
            if first.locked or second.locked:
                continue
            fixed_index = RectIndex[PageRect](_GRID_CELL_MM)
            for other in selected:
                if other.id in (first_id, second_id):
                    continue
                candidate = other.effective_candidate()
                if candidate is not None:
                    bounds = _collision_bounds(other, candidate, style)
                    fixed_index.set(other.id, bounds, bounds)
            first_choices = legal_candidates(first, fixed_index)
            second_choices = legal_candidates(second, fixed_index)
            best: tuple[float, str, str] | None = None
            for first_cost, first_candidate_id, first_candidate in first_choices:
                for second_cost, second_candidate_id, second_candidate in second_choices:
                    if _labels_overlap(
                        first, first_candidate, second, second_candidate, style
                    ):
                        continue
                    key = (first_cost + second_cost, first_candidate_id, second_candidate_id)
                    if best is None or key < best:
                        best = key
            if best is None:
                stats["unresolved_label_pairs"].append([first_id, second_id])
                continue
            if placements.get(first_id) != best[1] or placements.get(second_id) != best[2]:
                placements[first_id] = best[1]
                placements[second_id] = best[2]
                stats["pair_conflict_moves"] += 1
                changed = True
        if not changed:
            break

    # For dense local jams, expand only the labels blocking the best static
    # alternatives, then reuse the same bounded beam search used for ordinary
    # small conflict components. This avoids searching the whole Virgo core.
    for _ in range(2):
        changed = False
        pass_labels = current_labels()
        seeds = seed_conflicts(pass_labels)
        current_hard_count = hard_conflict_count(pass_labels)

        def seed_rank(
            seed: tuple[str, ...], candidate_labels: tuple[Label, ...]
        ) -> tuple[int, int, tuple[str, ...]]:
            seed_ids = set(seed)
            conflict_count = sum(
                source_conflicts(label, candidate)
                for label in candidate_labels
                if label.id in seed_ids
                and (candidate := label.effective_candidate()) is not None
            )
            for index, first in enumerate(candidate_labels):
                first_candidate = first.effective_candidate()
                if first_candidate is None or first.id not in seed_ids:
                    continue
                conflict_count += sum(
                    second_candidate is not None
                    and _labels_overlap(
                        first, first_candidate, second, second_candidate, style
                    )
                    for second in candidate_labels[index + 1 :]
                    if (second_candidate := second.effective_candidate()) is not None
                )
            priority = max(
                (labels_by_id[label_id].priority for label_id in seed_ids), default=0
            )
            return (-conflict_count, -priority, seed)

        for seed in sorted(seeds, key=lambda item: seed_rank(item, pass_labels)):
            if (
                stats["neighborhood_searches"]
                >= style.label.dso_placement.hard_repair_search_limit
            ):
                stats["neighborhood_search_limit_reached"] = True
                break
            if current_hard_count == 0:
                break
            neighborhood = expand_neighborhood(seed)
            if len(neighborhood) > style.label.dso_placement.hard_repair_neighborhood_labels:
                continue
            stats["neighborhood_searches"] += 1
            stats["neighborhood_sizes"].append(len(neighborhood))
            solution, visited = _joint_component_search(
                neighborhood,
                labels_by_id,
                placements,
                anchors,
                printable,
                symbols_index,
                sources,
                stars_index,
                stars,
                style,
                weights,
                furniture,
                constellation_lines,
                cost_cache,
            )
            stats["neighborhood_search_nodes"] += visited
            if solution is None:
                stats["neighborhood_search_budget_hits"] += 1
                continue
            proposed = dict(placements)
            proposed.update(solution)
            new_count = hard_conflict_count(
                tuple(
                    label.with_placement(
                        proposed.get(label.id), hidden=proposed.get(label.id) is None
                    )
                    for label in labels
                )
            )
            if new_count < current_hard_count:
                placements.update(solution)
                current_hard_count = new_count
                stats["neighborhood_moves"] += 1
                changed = True
        if not changed:
            break
    final_labels = current_labels()
    unresolved = []
    unresolved_dso = []
    unresolved_page = []
    for index, first in enumerate(final_labels):
        first_candidate = first.effective_candidate()
        if first_candidate is None or not first.id.startswith("label:dso:"):
            continue
        if (
            first_candidate.bounds.left_mm < printable.left_mm
            or first_candidate.bounds.top_mm < printable.top_mm
            or first_candidate.bounds.right_mm > printable.right_mm
            or first_candidate.bounds.bottom_mm > printable.bottom_mm
        ):
            unresolved_page.append(first.id)
        visible_bounds = candidate_ink_bounds(first_candidate)
        nearby_ids = {symbol.id for symbol in symbols_index.query(visible_bounds)}
        for source in sources:
            if (
                source.id in nearby_ids
                and circle_intersects_rect(
                    source.center, source.collision_radius_mm, visible_bounds
                )
                and source_edge_distance(source, visible_bounds) <= 0.0
            ):
                unresolved_dso.append([first.id, source.id])
        for second in final_labels[index + 1 :]:
            if not second.id.startswith("label:dso:"):
                continue
            second_candidate = second.effective_candidate()
            if second_candidate is not None and _labels_overlap(
                first, first_candidate, second, second_candidate, style
            ):
                unresolved.append([first.id, second.id])
    stats["unresolved_label_pairs"] = unresolved
    stats["unresolved_label_dso_pairs"] = unresolved_dso
    stats["unresolved_page_labels"] = unresolved_page
    return placements, stats


def optimize_labels(
    labels: tuple[Label, ...],
    scene: ChartScene,
    transform: PageTransform,
    style: StyleConfig,
    *,
    weights: CostWeights | None = None,
    furniture: Iterable[PageRect] = (),
    detailed_diagnostics: bool = False,
) -> OptimizationResult:
    """Optimize label placement deterministically.

    ``furniture`` holds the mandatory page-furniture rectangles that no label
    may overlap, so the optimizer never places a label onto the title,
    navigation, scale bar or legend (``AGENTS.md`` sections 15.1 and 16).
    """
    started_at = time.perf_counter()
    weights = _resolved_weights(style, weights)
    furniture_rects = tuple(furniture)
    printable = _printable(transform)
    symbols = _symbol_circles(scene, transform, style)
    sources = dso_source_geometries(scene, transform, style)
    stars = _star_circles(scene, transform, style)
    constellation_lines = tuple(
        (stroke.start, stroke.end)
        for stroke in resolve_constellation_lines(scene, transform, style)
    )
    symbols_index = _build_symbol_index(symbols)
    stars_index = _build_star_index(stars)
    anchors = _target_anchors(labels, scene, transform, style)
    ordered = tuple(sorted(labels, key=lambda label: (-label.priority, label.id)))

    # Initial layout: the placement that would be printed without optimization
    # (the explicit selection, else the preferred candidate).  Locked labels
    # start from their override so the "before" diagnostics already reflect it.
    before: dict[str, str | None] = {}
    for label in ordered:
        candidate = label.effective_candidate()
        before[label.id] = candidate.id if candidate is not None else None
    cost_before, totals_before = _evaluate(
        ordered,
        before,
        anchors,
        printable,
        symbols,
        sources,
        stars,
        style,
        weights,
        constellation_lines,
    )
    cost_cache = _CandidateScoreCache(
        anchors,
        printable,
        symbols_index,
        sources,
        stars_index,
        stars,
        style,
        weights,
        constellation_lines,
        furniture_rects,
    )

    placements: dict[str, str | None] = {}
    placed_index: RectIndex[PageRect] = RectIndex(_GRID_CELL_MM)
    for label in ordered:
        if not label.locked:
            continue
        candidate_id = label.selected_candidate_id
        candidate = label.candidate(candidate_id) if candidate_id is not None else None
        if candidate is not None:
            placements[label.id] = candidate.id
            bounds = _collision_bounds(label, candidate, style)
            placed_index.set(label.id, bounds, bounds)
        else:
            placements[label.id] = None

    for label in ordered:
        if label.id in placements:
            continue
        best: tuple[tuple[float, float, int, float], LabelCandidate] | None = None
        for candidate in label.candidates:
            nearby_bounds = tuple(
                placed_index.query(
                    candidate.bounds, margin_mm=_CROWDING_RADIUS_MM, exclude=label.id
                )
            )
            nearby_symbols = tuple(symbols_index.query(candidate.bounds))
            nearby_stars = _nearby_stars(label, candidate.bounds, stars_index, stars, style)
            valid = _is_valid(
                label,
                candidate,
                nearby_bounds,
                printable,
                nearby_symbols,
                nearby_stars,
                style,
                furniture_rects,
                sources,
            )
            if not valid and best is not None and best[0][0] == 0.0:
                continue
            cost = cost_cache.cost(
                label,
                candidate,
                nearby_bounds,
                nearby_symbols=nearby_symbols,
                nearby_stars=nearby_stars,
            )
            key = (
                0.0 if valid else 1.0,
                cost,
                candidate.variant_rank,
                _preference_rank(candidate),
            )
            if best is None or key < best[0]:
                best = (key, candidate)
        if best is None:
            placements[label.id] = None
            continue
        valid = best[0][0] == 0.0
        if not valid and not label.mandatory and not label.id.startswith("label:dso:"):
            placements[label.id] = None
            continue
        placements[label.id] = best[1].id
        bounds = _collision_bounds(label, best[1], style)
        placed_index.set(label.id, bounds, bounds)

    local_repair_stats: dict[str, Any] = {}
    placements = _local_repair(
        ordered,
        placements,
        anchors,
        printable,
        placed_index,
        symbols_index,
        symbols,
        sources,
        stars_index,
        stars,
        style,
        weights,
        furniture_rects,
        constellation_lines,
        cost_cache,
        local_repair_stats,
    )
    placements, component_stats = _joint_dso_optimize(
        ordered,
        placements,
        anchors,
        printable,
        placed_index,
        symbols_index,
        sources,
        stars_index,
        stars,
        style,
        weights,
        furniture_rects,
        constellation_lines,
        cost_cache,
    )
    placements, hard_repair_stats = _repair_dso_hard_conflicts(
        ordered,
        placements,
        anchors,
        printable,
        symbols_index,
        sources,
        stars_index,
        stars,
        style,
        weights,
        furniture_rects,
        constellation_lines,
        cost_cache,
    )
    component_stats.update(hard_repair_stats)
    optimized = tuple(
        label.with_placement(placements.get(label.id), hidden=placements.get(label.id) is None)
        for label in labels
    )
    auto_labels = list(optimized)
    for index, label in enumerate(auto_labels):
        candidate = label.effective_candidate()
        if label.hidden or label.locked or candidate is None:
            continue
        if label.id.startswith("label:dso:"):
            continue
        threshold = _leader_ambiguity_threshold(label, style)
        if threshold is None:
            continue
        selected_breakdown = _candidate_breakdown(
            label,
            candidate,
            anchors,
            printable,
            placed_index,
            symbols_index,
            sources,
            stars_index,
            stars,
            style,
            weights,
            constellation_lines,
        )
        selected_ambiguity = _ownership_ambiguity(selected_breakdown)
        if selected_ambiguity < threshold:
            continue
        direct_ambiguities = []
        for direct in label.candidates:
            if direct.ring >= style.label.leader_lines.auto_min_ring:
                continue
            nearby_bounds = tuple(
                placed_index.query(
                    direct.bounds,
                    margin_mm=_CROWDING_RADIUS_MM,
                    exclude=label.id,
                )
            )
            nearby_symbols = tuple(symbols_index.query(direct.bounds))
            nearby_stars = _nearby_stars(label, direct.bounds, stars_index, stars, style)
            if not _is_valid(
                label,
                direct,
                nearby_bounds,
                printable,
                nearby_symbols,
                nearby_stars,
                style,
                furniture_rects,
                sources,
            ):
                continue
            direct_ambiguities.append(
                _ownership_ambiguity(
                    _candidate_breakdown(
                        label,
                        direct,
                        anchors,
                        printable,
                        placed_index,
                        symbols_index,
                        sources,
                        stars_index,
                        stars,
                        style,
                        weights,
                        constellation_lines,
                    )
                )
            )
        if direct_ambiguities and min(direct_ambiguities) < threshold:
            continue
        if leader_line_for(label, tuple(auto_labels), scene, transform, style) is None:
            continue
        proposed = list(auto_labels)
        proposed[index] = replace(
            label,
            leader_line=True,
            leader_line_reason="association_ambiguity",
        )
        enabled_count = sum(item.leader_line for item in proposed)
        if len(resolve_leader_lines(tuple(proposed), scene, transform, style)) == enabled_count:
            auto_labels = proposed
    auto_labels = list(
        _consider_dso_leader_fallbacks(
            tuple(auto_labels),
            anchors,
            printable,
            symbols_index,
            sources,
            stars_index,
            stars,
            style,
            weights,
            furniture_rects,
            constellation_lines,
            scene,
            transform,
            cost_cache,
        )
    )
    optimized = tuple(auto_labels)
    final_placements: dict[str, str | None] = {}
    for label in optimized:
        candidate = None if label.hidden else label.effective_candidate()
        final_placements[label.id] = candidate.id if candidate is not None else None
    cost_after, totals_after = _evaluate(
        ordered,
        final_placements,
        anchors,
        printable,
        symbols,
        sources,
        stars,
        style,
        weights,
        constellation_lines,
    )
    placed_count = sum(1 for value in placements.values() if value is not None)
    final_placed_index = _build_placed_index(optimized, style)
    label_diagnostics = _label_diagnostics(
        optimized,
        anchors,
        printable,
        final_placed_index,
        symbols_index,
        sources,
        stars_index,
        stars,
        style,
        weights,
        constellation_lines,
        scene=scene,
        transform=transform,
        detailed_diagnostics=detailed_diagnostics,
        furniture=furniture_rects,
        component_stats=component_stats,
    )
    targeted = add_targeted_dso_leaders(
        optimized, label_diagnostics, scene, transform, style, furniture=furniture_rects
    )
    if targeted.labels != optimized:
        optimized = targeted.labels
        label_diagnostics = _label_diagnostics(
            optimized,
            anchors,
            printable,
            final_placed_index,
            symbols_index,
            sources,
            stars_index,
            stars,
            style,
            weights,
            constellation_lines,
            scene=scene,
            transform=transform,
            detailed_diagnostics=detailed_diagnostics,
            furniture=furniture_rects,
            component_stats=component_stats,
        )
    elapsed_s = time.perf_counter() - started_at
    dso_metrics = _dso_placement_metrics(
        optimized,
        label_diagnostics,
        component_stats,
        elapsed_s,
        weak_margin_mm=style.label.dso_placement.ownership_margin_preferred_mm,
    )
    dso_metrics["local_repair"] = local_repair_stats
    dso_metrics["targeted_dso_leaders"] = {
        "counts": targeted.counts,
        "decisions": list(targeted.decisions),
    }
    return OptimizationResult(
        labels=optimized,
        cost_before=cost_before,
        cost_after=cost_after,
        placed_count=placed_count,
        hidden_count=len(ordered) - placed_count,
        component_totals_before=totals_before,
        component_totals_after=totals_after,
        label_diagnostics=label_diagnostics,
        metrics=dso_metrics,
    )


def _candidate_breakdown(
    label: Label,
    candidate: LabelCandidate,
    anchors: dict[str, PagePoint],
    printable: PageRect,
    placed_index: RectIndex[PageRect],
    symbols_index: RectIndex[SymbolCircle],
    sources: tuple[SourceGeometry, ...],
    stars_index: RectIndex[StarCircle],
    stars: tuple[StarCircle, ...],
    style: StyleConfig,
    weights: CostWeights,
    constellation_lines: tuple[tuple[PagePoint, PagePoint], ...],
    cost_cache: _CandidateScoreCache | None = None,
) -> CostBreakdown:
    nearby_bounds = tuple(
        placed_index.query(candidate.bounds, margin_mm=_CROWDING_RADIUS_MM, exclude=label.id)
    )
    if cost_cache is not None:
        return cost_cache.breakdown(label, candidate, nearby_bounds)
    nearby_symbols = tuple(symbols_index.query(candidate.bounds))
    nearby_stars = _nearby_stars(label, candidate.bounds, stars_index, stars, style)
    return score_candidate(
        candidate,
        target_anchor=_anchor_for(label, anchors, candidate),
        placed_bounds=nearby_bounds,
        symbols=nearby_symbols,
        stars=nearby_stars,
        associated_star_ids=_associated_star_ids(label, nearby_stars),
        related_star_ids=_related_star_ids(label, nearby_stars),
        star_clearance=style.label.star_clearance,
        target_source_id=_association_source_id(label),
        source_association=style.label.source_association,
        dso_placement=style.label.dso_placement,
        is_dso_label=label.id.startswith("label:dso:"),
        source_symbols=_nearby_sources(label, candidate.bounds, sources, style),
        association_scale=_association_scale(label, style),
        printable=printable,
        crowding_radius_mm=_CROWDING_RADIUS_MM,
        weights=weights,
        edge_margin_mm=_EDGE_MARGIN_MM,
        constellation_lines=constellation_lines,
    )


def _build_placed_index(
    labels: tuple[Label, ...], style: StyleConfig
) -> RectIndex[PageRect]:
    index: RectIndex[PageRect] = RectIndex(_GRID_CELL_MM)
    for label in labels:
        candidate = None if label.hidden else label.effective_candidate()
        if candidate is not None:
            bounds = _collision_bounds(label, candidate, style)
            index.set(label.id, bounds, bounds)
    return index


def _weighted_ownership_cost(
    breakdown: CostBreakdown,
    weights: CostWeights,
) -> float:
    return (
        breakdown.label_source_distance_mm * weights.label_source_distance
        + breakdown.label_source_corridor * weights.label_source_corridor
        + breakdown.label_competing_source_ambiguity
        * weights.label_competing_source_ambiguity
        + breakdown.label_competing_owner * weights.label_competing_owner
        + breakdown.label_ownership_margin_cost * weights.label_ownership_margin
    )


def _consider_dso_leader_fallbacks(
    labels: tuple[Label, ...],
    anchors: dict[str, PagePoint],
    printable: PageRect,
    symbols_index: RectIndex[SymbolCircle],
    sources: tuple[SourceGeometry, ...],
    stars_index: RectIndex[StarCircle],
    stars: tuple[StarCircle, ...],
    style: StyleConfig,
    weights: CostWeights,
    furniture: tuple[PageRect, ...],
    constellation_lines: tuple[tuple[PagePoint, PagePoint], ...],
    scene: ChartScene,
    transform: PageTransform,
    cost_cache: _CandidateScoreCache,
) -> tuple[Label, ...]:
    """Compare direct and routed placements for poorly associated DSO labels."""
    config = style.label.leader_lines
    if not config.enabled:
        return labels
    routing_context = prepare_leader_routing_context(scene, transform, style)
    output = list(labels)
    placed_index = _build_placed_index(labels, style)
    for position, label in enumerate(output):
        current = None if label.hidden else label.effective_candidate()
        if (
            not label.id.startswith("label:dso:")
            or label.locked
            or current is None
            or label.leader_line
        ):
            continue
        placed_index.discard(label.id)
        current_breakdown = _candidate_breakdown(
            label,
            current,
            anchors,
            printable,
            placed_index,
            symbols_index,
            sources,
            stars_index,
            stars,
            style,
            weights,
            constellation_lines,
            cost_cache,
        )
        own_gap = current_breakdown.label_source_facing_edge_distance_mm
        margin = current_breakdown.ownership_margin_mm
        wrong_owner = current_breakdown.foreign_source_closer_than_owner
        semantic_ambiguity = (
            current_breakdown.label_source_corridor * weights.label_source_corridor
            + current_breakdown.label_competing_source_ambiguity
            * weights.label_competing_source_ambiguity
            + current_breakdown.label_competing_owner * weights.label_competing_owner
            + current_breakdown.label_ownership_margin_cost * weights.label_ownership_margin
        )
        needs_association_help = (
            own_gap > config.dso_preferred_gap_mm
            or wrong_owner
            or (margin is not None and margin < 0.25)
            or (
                margin is not None
                and margin < style.label.dso_placement.ownership_margin_preferred_mm
                and semantic_ambiguity
                >= style.label.leader_lines.dso_ambiguity_threshold
            )
            or current_breakdown.label_source_corridor > 0.0
        )
        if not needs_association_help:
            bounds = _collision_bounds(label, current, style)
            placed_index.set(label.id, bounds, bounds)
            continue

        current_cost = current_breakdown.total(weights)
        current_rejection = _candidate_rejection_reason(
            label,
            current,
            placed_index,
            symbols_index,
            stars_index,
            stars,
            printable,
            style,
            furniture=furniture,
            source_geometries=sources,
        )
        eligible: list[tuple[float, str, LabelCandidate, CostBreakdown]] = []
        for candidate in label.candidates:
            breakdown = _candidate_breakdown(
                label,
                candidate,
                anchors,
                printable,
                placed_index,
                symbols_index,
                sources,
                stars_index,
                stars,
                style,
                weights,
                constellation_lines,
                cost_cache,
            )
            if breakdown.label_source_facing_edge_distance_mm > config.dso_candidate_max_gap_mm:
                continue
            eligible.append((breakdown.total(weights), candidate.id, candidate, breakdown))

        options: list[tuple[float, int, float, str, Label]] = []
        for direct_cost, _, candidate, breakdown in sorted(eligible)[:48]:
            rejection = _candidate_rejection_reason(
                label,
                candidate,
                placed_index,
                symbols_index,
                stars_index,
                stars,
                printable,
                style,
                furniture=furniture,
                source_geometries=sources,
            )
            if rejection is None:
                options.append((
                    direct_cost,
                    0,
                    0.0,
                    candidate.id,
                    label.with_placement(candidate.id),
                ))
            if rejection not in (None, "foreign_source_closer_than_owner"):
                continue
            line_label = replace(
                label,
                selected_candidate_id=candidate.id,
                leader_line=True,
                leader_line_reason="association_ambiguity",
            )
            proposed = list(output)
            proposed[position] = line_label
            route = leader_line_for(
                line_label,
                tuple(proposed),
                scene,
                transform,
                style,
                context=routing_context,
            )
            if route is None:
                continue
            ownership_cost = _weighted_ownership_cost(breakdown, weights)
            leader_cost = (
                direct_cost
                - ownership_cost * (1.0 - config.dso_association_residual_factor)
                + config.dso_length_weight * _route_length(route) ** 2
            )
            options.append((
                leader_cost,
                1,
                _route_length(route),
                candidate.id,
                line_label,
            ))

        for option_cost, _, _, _, replacement in sorted(options):
            if current_rejection is None and option_cost >= current_cost - 0.25:
                break
            proposed = list(output)
            proposed[position] = replacement
            enabled_count = sum(item.leader_line for item in proposed)
            if len(resolve_leader_lines(
                tuple(proposed), scene, transform, style, context=routing_context
            )) != enabled_count:
                continue
            output[position] = replacement
            break
        selected = output[position].effective_candidate()
        if selected is not None:
            bounds = _collision_bounds(label, selected, style)
            placed_index.set(label.id, bounds, bounds)
    result = tuple(output)
    enabled = sum(label.leader_line for label in result)
    resolved = resolve_leader_lines(
        result, scene, transform, style, context=routing_context
    )
    if len(resolved) != enabled:
        # A later line can intersect an earlier one; preserve only the
        # deterministic valid set instead of serializing a broken callout.
        accepted_ids = {line.label_id for line in resolved}
        result = tuple(
            label
            if not label.leader_line or label.id in accepted_ids
            else replace(label, leader_line=False, leader_line_reason=None)
            for label in result
        )
    return result


def _route_length(route: Any) -> float:
    return math.hypot(route.end.x_mm - route.start.x_mm, route.end.y_mm - route.start.y_mm)


def _ownership_ambiguity(breakdown: CostBreakdown) -> float:
    return (
        breakdown.label_source_distance_mm
        + breakdown.label_source_corridor
        + breakdown.label_competing_source_ambiguity
        + breakdown.label_competing_owner
        + breakdown.label_glyph_proximity
    )


def _leader_ambiguity_threshold(label: Label, style: StyleConfig) -> float | None:
    if label.id.startswith("label:star:"):
        return style.label.leader_lines.star_ambiguity_threshold
    if label.id.startswith("label:dso:"):
        return style.label.leader_lines.dso_ambiguity_threshold
    return None


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _dso_placement_metrics(
    labels: tuple[Label, ...],
    diagnostics: dict[str, dict[str, Any]],
    component_stats: dict[str, Any],
    runtime_s: float,
    *,
    weak_margin_mm: float,
) -> dict[str, Any]:
    dso_labels = tuple(label for label in labels if label.id.startswith("label:dso:"))
    dso_diagnostics = [diagnostics[label.id] for label in dso_labels if label.id in diagnostics]
    gaps = [
        float(item["source_facing_edge_distance_mm"])
        for item in dso_diagnostics
        if item.get("source_facing_edge_distance_mm") is not None
    ]
    direct_gaps = [
        float(item["source_facing_edge_distance_mm"])
        for item in dso_diagnostics
        if not item.get("leader_line_used")
        and item.get("source_facing_edge_distance_mm") is not None
    ]
    leader_gaps = [
        float(item["source_facing_edge_distance_mm"])
        for item in dso_diagnostics
        if item.get("leader_line_used")
        and item.get("source_facing_edge_distance_mm") is not None
    ]
    margins = [
        float(item["ownership_margin_mm"])
        for item in dso_diagnostics
        if item.get("ownership_margin_mm") is not None
    ]
    leader_lengths = [
        float(item["leader_line_length_mm"])
        for item in dso_diagnostics
        if item.get("leader_line_used") and item.get("leader_line_length_mm") is not None
    ]
    wrong_owner_nearest = sum(
        1
        for item in dso_diagnostics
        if item.get("nearest_competing_dso_edge_gap_mm") is not None
        and item["nearest_competing_dso_edge_gap_mm"]
        < item["source_facing_edge_distance_mm"]
    )
    overlap_pairs: set[tuple[str, str]] = set()
    for item in dso_diagnostics:
        label_id = str(item["label_id"])
        for other_id in item.get("label_label_conflicts", ()):
            overlap_pairs.add(tuple(sorted((label_id, str(other_id)))))
    leader_count = sum(bool(label.leader_line) for label in dso_labels)
    component_by_label = {
        label_id: {"component_index": component_index, "component_size": len(component)}
        for component_index, component in enumerate(component_stats.get("components", ()))
        for label_id in component
    }
    worst_placements = []
    for item in dso_diagnostics:
        margin = item.get("ownership_margin_mm")
        gap = item.get("source_facing_edge_distance_mm")
        severity = (
            (4.0 if item.get("foreign_source_closer_than_owner") else 0.0)
            + (max(0.0, -float(margin)) * 2.0 if margin is not None else 0.0)
            + max(0.0, float(gap or 0.0) - 0.8)
            + float(item.get("competing_source_ambiguity_cost", 0.0))
            + float(item.get("association_corridor_cost", 0.0))
        )
        worst_placements.append((severity, item))
    worst_placements.sort(
        key=lambda pair: (
            -pair[0],
            str(pair[1].get("canonical_label", "")),
            str(pair[1].get("object_id", "")),
        )
    )
    hard_dso_pairs = {
        tuple(sorted((str(item["label_id"]), str(source_id))))
        for item in dso_diagnostics
        for source_id in item.get("label_dso_conflicts", ())
    }
    return {
        "dso_label_count": len(dso_labels),
        "direct_count": len(dso_labels) - leader_count,
        "leader_count": leader_count,
        "source_edge_gap_mm": {
            "count": len(gaps),
            "median": _percentile(gaps, 0.50),
            "p90": _percentile(gaps, 0.90),
            "p95": _percentile(gaps, 0.95),
            "max": max(gaps, default=None),
        },
        "direct_source_edge_gap_mm": {
            "count": len(direct_gaps),
            "median": _percentile(direct_gaps, 0.50),
            "p90": _percentile(direct_gaps, 0.90),
            "p95": _percentile(direct_gaps, 0.95),
            "max": max(direct_gaps, default=None),
        },
        "leader_source_edge_gap_mm": {
            "count": len(leader_gaps),
            "median": _percentile(leader_gaps, 0.50),
            "p90": _percentile(leader_gaps, 0.90),
            "p95": _percentile(leader_gaps, 0.95),
            "max": max(leader_gaps, default=None),
        },
        "ownership_margin_mm": {
            "count": len(margins),
            "negative_count": sum(margin < 0.0 for margin in margins),
            "weak_count": sum(margin < weak_margin_mm for margin in margins),
            "min": min(margins, default=None),
            "p10": _percentile(margins, 0.10),
            "median": _percentile(margins, 0.50),
            "p90": _percentile(margins, 0.90),
            "max": max(margins, default=None),
            "weak_threshold_mm": weak_margin_mm,
        },
        "leader_length_mm": {
            "count": len(leader_lengths),
            "median": _percentile(leader_lengths, 0.50),
            "p90": _percentile(leader_lengths, 0.90),
            "max": max(leader_lengths, default=None),
        },
        "raw_ownership_ambiguity_count": sum(
            float(item.get("competing_source_ambiguity_cost", 0.0)) > 0.0
            or float(item.get("competing_owner_cost", 0.0)) > 0.0
            for item in dso_diagnostics
        ),
        # A validated leader explicitly connects the label to its owner, so
        # raw geometric competition is still reported above but is no longer
        # counted as unresolved ownership ambiguity.
        "ownership_ambiguity_count": sum(
            not item.get("leader_line_used")
            and (
                float(item.get("competing_source_ambiguity_cost", 0.0)) > 0.0
                or float(item.get("competing_owner_cost", 0.0)) > 0.0
            )
            for item in dso_diagnostics
        ),
        "nearest_dso_not_owner_count": wrong_owner_nearest,
        "unconnected_nearest_dso_not_owner_count": sum(
            1
            for item in dso_diagnostics
            if not item.get("leader_line_used")
            and item.get("nearest_competing_dso_edge_gap_mm") is not None
            and item["nearest_competing_dso_edge_gap_mm"]
            < item["source_facing_edge_distance_mm"]
        ),
        "foreign_source_closer_than_owner_count": sum(
            bool(item.get("foreign_source_closer_than_owner"))
            for item in dso_diagnostics
        ),
        "negative_ownership_margin_count": sum(
            margin < 0.0 for margin in margins
        ),
        "weak_ownership_margin_count": sum(
            margin < weak_margin_mm for margin in margins
        ),
        "hard_label_dso_conflict_pair_count": len(hard_dso_pairs),
        "hard_label_label_conflict_pair_count": len(overlap_pairs),
        "label_label_overlap_count": len(overlap_pairs),
        "corridor_conflict_count": sum(
            float(item.get("association_corridor_cost", 0.0)) > 0.0
            for item in dso_diagnostics
        ),
        "local_conflict_components": component_stats,
        "worst_placements": [
            {
                **item,
                "association_severity": severity,
                **component_by_label.get(str(item.get("label_id")), {}),
            }
            for severity, item in worst_placements[:20]
        ],
        "optimizer_runtime_s": runtime_s,
    }


def _candidate_rejection_reason(
    label: Label,
    candidate: LabelCandidate,
    placed_index: RectIndex[PageRect],
    symbols_index: RectIndex[SymbolCircle],
    stars_index: RectIndex[StarCircle],
    stars: tuple[StarCircle, ...],
    printable: PageRect,
    style: StyleConfig,
    *,
    furniture: tuple[PageRect, ...],
    source_geometries: tuple[SourceGeometry, ...],
) -> str | None:
    bounds = candidate.bounds
    collision_bounds = _collision_bounds(label, candidate, style)
    if (
        bounds.left_mm < printable.left_mm
        or bounds.top_mm < printable.top_mm
        or bounds.right_mm > printable.right_mm
        or bounds.bottom_mm > printable.bottom_mm
    ):
        return "outside_printable_area"
    if any(rects_overlap(bounds, obstacle) for obstacle in furniture):
        return "page_furniture_overlap"
    if any(
        rects_overlap(collision_bounds, other)
        for other in placed_index.query(
            collision_bounds,
            margin_mm=style.label.dso_placement.label_label_ink_clearance_mm or 0.0,
            exclude=label.id,
        )
    ):
        return "label_label_overlap"
    visible_bounds = (
        candidate_ink_bounds(candidate)
        if label.id.startswith("label:dso:")
        else bounds
    )
    nearby_symbols = tuple(symbols_index.query(visible_bounds))
    nearby_source_ids = {symbol.id for symbol in nearby_symbols}
    if any(
        source.id in nearby_source_ids and source_edge_distance(source, visible_bounds) <= 0.0
        for source in source_geometries
    ):
        return "dso_symbol_overlap"
    if label.id.startswith("label:dso:"):
        _, _, _, wrong_owner = _ownership_result(
            label, visible_bounds, source_geometries, style
        )
        if wrong_owner:
            return "foreign_source_closer_than_owner"
    for star in _nearby_stars(label, bounds, stars_index, stars, style):
        related = _related_star_ids(label, stars)
        hard_min = (
            style.label.star_clearance.associated.hard_min_mm
            if related & star.star_ids
            else foreign_star_hard_min_mm(star.radius_mm, style.label.star_clearance)
        )
        if candidate_star_edge_distance_mm(
            star,
            candidate,
            visible_text=label.id.startswith(("label:star:", "label:dso:")),
        ) < hard_min:
            return "star_clearance"
    return None


def _label_diagnostics(
    labels: tuple[Label, ...],
    anchors: dict[str, PagePoint],
    printable: PageRect,
    placed_index: RectIndex[PageRect],
    symbols_index: RectIndex[SymbolCircle],
    sources: tuple[SourceGeometry, ...],
    stars_index: RectIndex[StarCircle],
    stars: tuple[StarCircle, ...],
    style: StyleConfig,
    weights: CostWeights,
    constellation_lines: tuple[tuple[PagePoint, PagePoint], ...],
    *,
    scene: ChartScene,
    transform: PageTransform,
    detailed_diagnostics: bool,
    furniture: tuple[PageRect, ...],
    component_stats: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    diagnostics: dict[str, dict[str, Any]] = {}
    sources_by_id = {source.id: source for source in sources}
    leader_lines = {
        line.label_id: line
        for line in resolve_leader_lines(labels, scene, transform, style)
    }
    placed = tuple(
        (other, other.effective_candidate())
        for other in labels
        if not other.hidden and other.effective_candidate() is not None
    )
    component_by_label = {
        label_id: {"conflict_component_index": component_index,
                   "conflict_component_size": len(component)}
        for component_index, component in enumerate(component_stats.get("components", ()))
        for label_id in component
    }
    for label in labels:
        candidate = None if label.hidden else label.effective_candidate()
        if candidate is None or _association_source_id(label) is None:
            continue
        breakdown = _candidate_breakdown(
            label,
            candidate,
            anchors,
            printable,
            placed_index,
            symbols_index,
            sources,
            stars_index,
            stars,
            style,
            weights,
            constellation_lines,
        )
        nearby_stars = _nearby_stars(label, candidate.bounds, stars_index, stars, style)
        diagnostic: dict[str, Any] = {
            "source_facing_edge_distance_mm": (
                breakdown.label_source_facing_edge_distance_mm
            ),
            "association_corridor_cost": breakdown.label_source_corridor,
            "competing_owner_cost": breakdown.label_competing_owner,
            "competing_owner_id": breakdown.competing_owner_id,
            "glyph_proximity_cost": breakdown.label_glyph_proximity,
            "closest_foreign_star_id": breakdown.closest_foreign_star_id,
            "closest_foreign_star_radius_mm": breakdown.closest_foreign_star_radius_mm,
            "closest_foreign_star_distance_mm": breakdown.closest_foreign_star_distance_mm,
            "leader_line_used": label.leader_line,
            "leader_line_reason": label.leader_line_reason,
        }
        diagnostic.update(_star_source_diagnostics(label, nearby_stars))
        if label.id.startswith("label:dso:"):
            source = sources_by_id.get(label.target_id)
            visible_bounds = candidate_ink_bounds(candidate)
            owner_gap, ownership_margin, nearest_source, wrong_owner = _ownership_result(
                label, visible_bounds, sources, style, all_sources=True
            )
            nearest_competitor = (
                source_edge_distance(nearest_source, visible_bounds), nearest_source.id
            ) if nearest_source is not None else (None, None)
            owner_overlaps_nearest = bool(
                source is not None
                and nearest_source is not None
                and source_geometries_overlap(source, nearest_source)
            )
            leader = leader_lines.get(label.id)
            line_length = (
                math.hypot(leader.end.x_mm - leader.start.x_mm, leader.end.y_mm - leader.start.y_mm)
                if leader is not None
                else 0.0
            )
            overlapping_labels = tuple(
                other.id
                for other, other_candidate in placed
                if other.id != label.id
                and other_candidate is not None
                and _labels_overlap(label, candidate, other, other_candidate, style)
            )
            nearby_symbol_ids = {symbol.id for symbol in symbols_index.query(visible_bounds)}
            weighted_association = (
                breakdown.label_source_distance_mm * weights.label_source_distance
                + breakdown.label_source_corridor * weights.label_source_corridor
                + breakdown.label_competing_source_ambiguity
                * weights.label_competing_source_ambiguity
                + breakdown.label_competing_owner * weights.label_competing_owner
                + breakdown.label_ownership_margin_cost * weights.label_ownership_margin
            )
            line_cost = style.label.leader_lines.dso_length_weight * line_length**2
            leader_adjusted_cost = (
                breakdown.total(weights)
                - weighted_association
                * (1.0 - style.label.leader_lines.dso_association_residual_factor)
                + line_cost
                if leader is not None
                else None
            )
            diagnostic.update({
                "label_id": label.id,
                "object_id": label.target_id,
                "canonical_label": label.text,
                "rendered_source_geometry_type": (
                    "contour" if source is not None and source.outline_paths
                    else "ellipse" if source is not None and source.source_type.value == "galaxy"
                    else "symbol" if source is not None
                    else "missing"
                ),
                "chosen_candidate_index": label.candidates.index(candidate),
                "candidate_direction": candidate.position.value,
                "source_label_center_distance_mm": (
                    math.hypot(
                        source.center.x_mm - visible_bounds.center.x_mm,
                        source.center.y_mm - visible_bounds.center.y_mm,
                    )
                    if source is not None
                    else None
                ),
                "nearest_competing_dso_id": nearest_competitor[1],
                "nearest_competing_dso_edge_gap_mm": nearest_competitor[0],
                "ownership_margin_mm": ownership_margin,
                "foreign_source_closer_than_owner": wrong_owner,
                "ownership_overlap_exception": owner_overlaps_nearest,
                "ownership_nearest_source_id": (
                    nearest_source.id if nearest_source is not None else None
                ),
                "ownership_owner_edge_gap_mm": owner_gap,
                "ownership_foreign_edge_gap_mm": nearest_competitor[0],
                "ownership_margin_weak": (
                    ownership_margin is not None
                    and ownership_margin < style.label.dso_placement.ownership_margin_preferred_mm
                ),
                "source_association_cost": weighted_association,
                "ownership_margin_cost": (
                    breakdown.label_ownership_margin_cost * weights.label_ownership_margin
                ),
                "competing_source_ambiguity_cost": (
                    breakdown.label_competing_source_ambiguity
                    * weights.label_competing_source_ambiguity
                ),
                "foreign_star_proximity_cost": (
                    breakdown.label_foreign_star_clearance
                    * weights.label_foreign_star_clearance
                ),
                "foreign_dso_proximity_cost": (
                    breakdown.label_foreign_object_proximity
                    * weights.label_foreign_object_proximity
                ),
                "preferred_direction_cost": breakdown.preference_rank * weights.preference_rank,
                "label_label_conflict_count": len(overlapping_labels),
                "label_label_conflicts": list(overlapping_labels),
                "label_dso_conflicts": [
                    other_source.id
                    for other_source in sources
                    if other_source.id in nearby_symbol_ids
                    and source_edge_distance(other_source, visible_bounds) <= 0.0
                ],
                "leader_line_used": leader is not None,
                "leader_line_length_mm": line_length,
                "direct_candidate_total_cost": breakdown.total(weights),
                "leader_line_cost": line_cost if leader is not None else 0.0,
                "leader_adjusted_total_cost": leader_adjusted_cost,
                "candidate_total_cost": (
                    leader_adjusted_cost
                    if leader_adjusted_cost is not None
                    else breakdown.total(weights)
                ),
            })
            diagnostic.update(component_by_label.get(label.id, {}))
            if detailed_diagnostics:
                alternatives = []
                rejection_counts: dict[str, int] = {}
                valid_candidate_count = 0
                for alternative in label.candidates:
                    if alternative.id == candidate.id:
                        continue
                    rejection = _candidate_rejection_reason(
                        label,
                        alternative,
                        placed_index,
                        symbols_index,
                        stars_index,
                        stars,
                        printable,
                        style,
                        furniture=furniture,
                        source_geometries=sources,
                    )
                    if rejection is None:
                        valid_candidate_count += 1
                    else:
                        rejection_counts[rejection] = rejection_counts.get(rejection, 0) + 1
                    alternative_breakdown = _candidate_breakdown(
                        label,
                        alternative,
                        anchors,
                        printable,
                        placed_index,
                        symbols_index,
                        sources,
                        stars_index,
                        stars,
                        style,
                        weights,
                        constellation_lines,
                    )
                    alternatives.append({
                        "candidate_id": alternative.id,
                        "direction": alternative.position.value,
                        "edge_gap_mm": alternative_breakdown.label_source_facing_edge_distance_mm,
                        "total_cost": alternative_breakdown.total(weights),
                        "rejection_reason": rejection,
                    })
                diagnostic["best_alternatives"] = sorted(
                    alternatives,
                    key=lambda item: (
                        item["rejection_reason"] is not None,
                        item["total_cost"],
                        item["candidate_id"],
                    ),
                )[:3]
                diagnostic["candidate_count"] = len(label.candidates)
                diagnostic["hard_valid_candidate_count"] = valid_candidate_count
                diagnostic["candidate_rejection_counts"] = dict(sorted(rejection_counts.items()))
                if overlapping_labels or diagnostic["label_dso_conflicts"]:
                    plausible = sorted(
                        (
                            source_edge_distance(source, candidate_ink_bounds(alternative))
                            if source is not None
                            else float("inf"),
                            alternative.id,
                            alternative,
                        )
                        for alternative in label.candidates
                    )
                    leader_resolvable = 0
                    checked = 0
                    for _, _, alternative in plausible:
                        if checked >= 16:
                            break
                        if source_edge_distance(source, candidate_ink_bounds(alternative)) > (
                            style.label.leader_lines.dso_preferred_gap_mm
                        ):
                            continue
                        rejection = _candidate_rejection_reason(
                            label,
                            alternative,
                            placed_index,
                            symbols_index,
                            stars_index,
                            stars,
                            printable,
                            style,
                            furniture=furniture,
                            source_geometries=sources,
                        )
                        if rejection not in (None, "foreign_source_closer_than_owner"):
                            continue
                        checked += 1
                        leader_label = replace(
                            label,
                            selected_candidate_id=alternative.id,
                            leader_line=True,
                            leader_line_reason="association_ambiguity",
                        )
                        proposed = tuple(
                            leader_label if other.id == label.id else other for other in labels
                        )
                        if leader_line_for(leader_label, proposed, scene, transform, style):
                            leader_resolvable += 1
                    diagnostic["leader_candidates_checked"] = checked
                    diagnostic["leader_resolvable_candidate_count"] = leader_resolvable
        diagnostics[label.id] = diagnostic
    return diagnostics


def _star_source_diagnostics(
    label: Label, stars: tuple[StarCircle, ...]
) -> dict[str, float | str | bool | None]:
    """Describe the rendered stellar source used by one star label."""
    if not label.id.startswith("label:star:"):
        return {}
    owned = _associated_star_ids(label, stars)
    related = _related_star_ids(label, stars)
    owner_marks = tuple(star for star in stars if owned & star.star_ids)
    system_ids = sorted(
        system_id
        for star in owner_marks
        for system_id in star.system_ids
        if system_id == label.target_id or label.target_id in star.star_ids
    )
    is_system_label = any(label.target_id in star.system_ids for star in stars)
    if is_system_label:
        source_type = (
            "unresolved_double"
            if len(owner_marks) == 1 and len(owner_marks[0].star_ids) > 1
            else "resolved_double_system"
        )
    elif any(len(star.star_ids) > 1 for star in owner_marks):
        source_type = "unresolved_double"
    elif len(related) > len(owned):
        source_type = (
            "resolved_double_component"
        )
    else:
        source_type = "single_star"
    return {
        "star_source_type": source_type,
        "star_source_system_id": (
            label.target_id if is_system_label else (system_ids[0] if system_ids else None)
        ),
        "source_envelope_component_count": float(len(owner_marks)),
        "same_system_components_excluded": bool(related - owned),
    }


def _local_repair(
    ordered: tuple[Label, ...],
    placements: dict[str, str | None],
    anchors: dict[str, PagePoint],
    printable: PageRect,
    placed_index: RectIndex[PageRect],
    symbols_index: RectIndex[SymbolCircle],
    symbols: tuple[SymbolCircle, ...],
    sources: tuple[SourceGeometry, ...],
    stars_index: RectIndex[StarCircle],
    stars: tuple[StarCircle, ...],
    style: StyleConfig,
    weights: CostWeights,
    furniture: tuple[PageRect, ...] = (),
    constellation_lines: tuple[tuple[PagePoint, PagePoint], ...] = (),
    cost_cache: _CandidateScoreCache | None = None,
    repair_stats: dict[str, Any] | None = None,
) -> dict[str, str | None]:
    if cost_cache is None:
        cost_cache = _CandidateScoreCache(
            anchors,
            printable,
            symbols_index,
            sources,
            stars_index,
            stars,
            style,
            weights,
            constellation_lines,
            furniture,
        )
    pass_stats: list[dict[str, Any]] = []
    for _ in range(_MAX_REPAIR_PASSES):
        changed = False
        evaluated = 0
        moves: list[dict[str, Any]] = []
        for label in ordered:
            if label.locked:
                continue
            current_id = placements.get(label.id)
            if current_id is None:
                continue
            current = label.candidate(current_id)
            if current is None:
                continue
            evaluated += 1
            best_id = current_id
            nearby_bounds = tuple(
                placed_index.query(current.bounds, margin_mm=_CROWDING_RADIUS_MM, exclude=label.id)
            )
            current_valid = cost_cache.valid(label, current, nearby_bounds)
            best_cost = cost_cache.cost(label, current, nearby_bounds)
            initial_cost = best_cost
            best_key = (0 if current_valid else 1, best_cost)
            for candidate in label.candidates:
                if candidate.id == current_id:
                    continue
                if best_key[0] == 0 and not cost_cache.valid(label, candidate, ()):
                    continue
                cand_bounds = tuple(
                    placed_index.query(
                        candidate.bounds,
                        margin_mm=_CROWDING_RADIUS_MM,
                        exclude=label.id,
                    )
                )
                candidate_valid = cost_cache.valid(label, candidate, cand_bounds)
                if not candidate_valid and best_key[0] == 0:
                    continue
                cost = cost_cache.cost(label, candidate, cand_bounds)
                candidate_key = (0 if candidate_valid else 1, cost)
                if candidate_key < (best_key[0], best_key[1] - 1e-9):
                    best_cost = cost
                    best_id = candidate.id
                    best_key = candidate_key
            if best_id != current_id:
                placements[label.id] = best_id
                new_candidate = label.candidate(best_id)
                if new_candidate is not None:
                    if repair_stats is not None:
                        old_center = current.bounds.center
                        new_center = new_candidate.bounds.center
                        moves.append({
                            "label_id": label.id,
                            "from": current_id,
                            "to": best_id,
                            "was_valid": current_valid,
                            "is_valid": best_key[0] == 0,
                            "cost_gain": (
                                initial_cost - best_cost
                                if current_valid == (best_key[0] == 0)
                                else None
                            ),
                            "movement_mm": math.hypot(
                                new_center.x_mm - old_center.x_mm,
                                new_center.y_mm - old_center.y_mm,
                            ),
                        })
                    bounds = _collision_bounds(label, new_candidate, style)
                    placed_index.set(label.id, bounds, bounds)
                changed = True
        if repair_stats is not None:
            pass_stats.append({"evaluated_labels": evaluated, "moves": moves})
        if not changed:
            break
    if repair_stats is not None:
        repair_stats["passes"] = pass_stats
    return placements


def _evaluate(
    ordered: tuple[Label, ...],
    placements: dict[str, str | None],
    anchors: dict[str, PagePoint],
    printable: PageRect,
    symbols: tuple[SymbolCircle, ...],
    sources: tuple[SourceGeometry, ...],
    stars: tuple[StarCircle, ...],
    style: StyleConfig,
    weights: CostWeights,
    constellation_lines: tuple[tuple[PagePoint, PagePoint], ...] = (),
) -> tuple[float, dict[str, float]]:
    label_by_id = {label.id: label for label in ordered}
    placed_index: RectIndex[PageRect] = RectIndex(_GRID_CELL_MM)
    for label_id, candidate_id in placements.items():
        if candidate_id is None:
            continue
        placed_label = label_by_id[label_id]
        placed_candidate = placed_label.candidate(candidate_id)
        if placed_candidate is not None:
            bounds = _collision_bounds(placed_label, placed_candidate, style)
            placed_index.set(label_id, bounds, bounds)
    stars_index = _build_star_index(stars)
    total = 0.0
    totals: dict[str, float] = {}
    for label in ordered:
        candidate_id = placements.get(label.id)
        if candidate_id is None:
            continue
        candidate = label.candidate(candidate_id)
        if candidate is None:
            continue
        nearby_bounds = tuple(
            placed_index.query(candidate.bounds, margin_mm=_CROWDING_RADIUS_MM, exclude=label.id)
        )
        nearby_stars = _nearby_stars(label, candidate.bounds, stars_index, stars, style)
        breakdown = score_candidate(
            candidate,
            target_anchor=_anchor_for(label, anchors, candidate),
            placed_bounds=nearby_bounds,
            symbols=symbols,
            stars=nearby_stars,
            associated_star_ids=_associated_star_ids(label, nearby_stars),
            related_star_ids=_related_star_ids(label, nearby_stars),
            star_clearance=style.label.star_clearance,
            target_source_id=_association_source_id(label),
            source_association=style.label.source_association,
            dso_placement=style.label.dso_placement,
            is_dso_label=label.id.startswith("label:dso:"),
            source_symbols=_nearby_sources(label, candidate.bounds, sources, style),
            association_scale=_association_scale(label, style),
            printable=printable,
            crowding_radius_mm=_CROWDING_RADIUS_MM,
            weights=weights,
            edge_margin_mm=_EDGE_MARGIN_MM,
            constellation_lines=constellation_lines,
        )
        total += breakdown.total(weights)
        for name, value in breakdown.components().items():
            totals[name] = totals.get(name, 0.0) + value
    return total, totals


def layout_hash(labels: tuple[Label, ...]) -> str:
    """Return a stable hash of placements for repeated-layout detection."""
    payload = [
        [label.id, label.selected_candidate_id, label.hidden, label.leader_line]
        for label in sorted(labels, key=lambda item: item.id)
    ]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def layout_cost(
    labels: tuple[Label, ...],
    scene: ChartScene,
    transform: PageTransform,
    style: StyleConfig,
    *,
    weights: CostWeights | None = None,
) -> tuple[float, dict[str, float]]:
    """Return the total soft cost and component totals for a layout."""
    weights = _resolved_weights(style, weights)
    printable = _printable(transform)
    symbols = _symbol_circles(scene, transform, style)
    sources = dso_source_geometries(scene, transform, style)
    stars = _star_circles(scene, transform, style)
    constellation_lines = tuple(
        (stroke.start, stroke.end)
        for stroke in resolve_constellation_lines(scene, transform, style)
    )
    anchors = _target_anchors(labels, scene, transform, style)
    ordered = tuple(sorted(labels, key=lambda label: (-label.priority, label.id)))

    placements: dict[str, str | None] = {}
    for label in labels:
        candidate = None if label.hidden else label.effective_candidate()
        placements[label.id] = candidate.id if candidate is not None else None
    return _evaluate(
        ordered,
        placements,
        anchors,
        printable,
        symbols,
        sources,
        stars,
        style,
        weights,
        constellation_lines,
    )
