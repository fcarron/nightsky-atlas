"""Deterministic label optimizer.

Strategy (``AGENTS.md`` section 15.3): priority-ordered greedy placement
followed by a deterministic local repair pass.  No stochastic search is used,
so the result is reproducible.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, replace

from nightsky_atlas.atlas.config import StyleConfig
from nightsky_atlas.chart.page import PagePoint, PageRect, PageTransform
from nightsky_atlas.layout.association import SourceGeometry, dso_source_geometries
from nightsky_atlas.layout.candidates import CANDIDATE_PREFERENCE
from nightsky_atlas.layout.geometry import (
    circle_intersects_rect,
    rects_overlap,
)
from nightsky_atlas.layout.labels import constellation_label_anchors
from nightsky_atlas.layout.leader_lines import leader_line_for, resolve_leader_lines
from nightsky_atlas.layout.models import Label, LabelCandidate
from nightsky_atlas.layout.scoring import (
    CostBreakdown,
    CostWeights,
    StarCircle,
    SymbolCircle,
    candidate_star_edge_distance_mm,
    foreign_star_hard_min_mm,
    score_candidate,
    star_source_bounds,
)
from nightsky_atlas.layout.spatial import RectIndex
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
    label_diagnostics: dict[str, dict[str, float | str | bool | None]]


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


def _build_symbol_index(symbols: tuple[SymbolCircle, ...]) -> RectIndex[SymbolCircle]:
    index: RectIndex[SymbolCircle] = RectIndex(_GRID_CELL_MM)
    for position, symbol in enumerate(symbols):
        index.set(f"symbol:{position}", _symbol_bounds(symbol), symbol)
    return index


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
) -> bool:
    bounds = candidate.bounds
    if (
        bounds.left_mm < printable.left_mm
        or bounds.top_mm < printable.top_mm
        or bounds.right_mm > printable.right_mm
        or bounds.bottom_mm > printable.bottom_mm
    ):
        return False
    if any(rects_overlap(bounds, other) for other in placed_bounds):
        return False
    if any(rects_overlap(bounds, obstacle) for obstacle in furniture):
        return False
    if any(circle_intersects_rect(symbol.center, symbol.radius_mm, bounds) for symbol in symbols):
        return False
    related = _related_star_ids(label, stars)
    for star in stars:
        hard_min = style.label.star_clearance.associated.hard_min_mm if (
            related & star.star_ids
        ) else foreign_star_hard_min_mm(star.radius_mm, style.label.star_clearance)
        if candidate_star_edge_distance_mm(
            star, candidate, visible_text=label.id.startswith("label:star:")
        ) < hard_min:
            return False
    return True


def _preference_rank(candidate: LabelCandidate) -> int:
    return CANDIDATE_PREFERENCE.index(candidate.position)


def _association_scale(label: Label, style: StyleConfig) -> float:
    compact = label.id.startswith("label:star:") and len("".join(label.text.split())) <= 3
    return style.label.source_association.compact_label_factor if compact else 1.0


def _association_source_id(label: Label) -> str | None:
    if label.id.startswith(("label:star:", "label:dso:")):
        return label.target_id
    return None


def optimize_labels(
    labels: tuple[Label, ...],
    scene: ChartScene,
    transform: PageTransform,
    style: StyleConfig,
    *,
    weights: CostWeights | None = None,
    furniture: Iterable[PageRect] = (),
) -> OptimizationResult:
    """Optimize label placement deterministically.

    ``furniture`` holds the mandatory page-furniture rectangles that no label
    may overlap, so the optimizer never places a label onto the title,
    navigation, scale bar or legend (``AGENTS.md`` sections 15.1 and 16).
    """
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

    placements: dict[str, str | None] = {}
    placed_index: RectIndex[PageRect] = RectIndex(_GRID_CELL_MM)
    for label in ordered:
        if not label.locked:
            continue
        candidate_id = label.selected_candidate_id
        candidate = label.candidate(candidate_id) if candidate_id is not None else None
        if candidate is not None:
            placements[label.id] = candidate.id
            placed_index.set(label.id, candidate.bounds, candidate.bounds)
        else:
            placements[label.id] = None

    for label in ordered:
        if label.id in placements:
            continue
        best: tuple[tuple[float, float, int, int], LabelCandidate] | None = None
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
            )
            breakdown = score_candidate(
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
                source_symbols=sources,
                association_scale=_association_scale(label, style),
                printable=printable,
                crowding_radius_mm=_CROWDING_RADIUS_MM,
                weights=weights,
                edge_margin_mm=_EDGE_MARGIN_MM,
                constellation_lines=constellation_lines,
            )
            key = (
                0.0 if valid else 1.0,
                breakdown.total(weights),
                candidate.variant_rank,
                _preference_rank(candidate),
            )
            if best is None or key < best[0]:
                best = (key, candidate)
        if best is None:
            placements[label.id] = None
            continue
        valid = best[0][0] == 0.0
        if not valid and not label.mandatory:
            placements[label.id] = None
            continue
        placements[label.id] = best[1].id
        placed_index.set(label.id, best[1].bounds, best[1].bounds)

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
    )
    cost_after, totals_after = _evaluate(
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

    optimized = tuple(
        label.with_placement(placements.get(label.id), hidden=placements.get(label.id) is None)
        for label in labels
    )
    auto_labels = list(optimized)
    for index, label in enumerate(auto_labels):
        candidate = label.effective_candidate()
        if label.hidden or label.locked or candidate is None:
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
    optimized = tuple(auto_labels)
    placed_count = sum(1 for value in placements.values() if value is not None)
    label_diagnostics = _label_diagnostics(
        optimized,
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
    return OptimizationResult(
        labels=optimized,
        cost_before=cost_before,
        cost_after=cost_after,
        placed_count=placed_count,
        hidden_count=len(ordered) - placed_count,
        component_totals_before=totals_before,
        component_totals_after=totals_after,
        label_diagnostics=label_diagnostics,
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
) -> CostBreakdown:
    nearby_bounds = tuple(
        placed_index.query(candidate.bounds, margin_mm=_CROWDING_RADIUS_MM, exclude=label.id)
    )
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
        source_symbols=sources,
        association_scale=_association_scale(label, style),
        printable=printable,
        crowding_radius_mm=_CROWDING_RADIUS_MM,
        weights=weights,
        edge_margin_mm=_EDGE_MARGIN_MM,
        constellation_lines=constellation_lines,
    )


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
) -> dict[str, dict[str, float | str | bool | None]]:
    diagnostics: dict[str, dict[str, float | str | bool | None]] = {}
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
        diagnostic: dict[str, float | str | bool | None] = {
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
        "source_envelope_component_count": float(len(owned)),
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
) -> dict[str, str | None]:
    for _ in range(_MAX_REPAIR_PASSES):
        changed = False
        for label in ordered:
            if label.locked:
                continue
            current_id = placements.get(label.id)
            if current_id is None:
                continue
            current = label.candidate(current_id)
            if current is None:
                continue
            anchor = _anchor_for(label, anchors, current)
            best_id = current_id
            nearby_bounds = tuple(
                placed_index.query(current.bounds, margin_mm=_CROWDING_RADIUS_MM, exclude=label.id)
            )
            nearby_symbols = tuple(symbols_index.query(current.bounds))
            nearby_stars = _nearby_stars(label, current.bounds, stars_index, stars, style)
            best_cost = score_candidate(
                current,
                target_anchor=anchor,
                placed_bounds=nearby_bounds,
                symbols=nearby_symbols,
                stars=nearby_stars,
                associated_star_ids=_associated_star_ids(label, nearby_stars),
                related_star_ids=_related_star_ids(label, nearby_stars),
                star_clearance=style.label.star_clearance,
                target_source_id=_association_source_id(label),
                source_association=style.label.source_association,
                source_symbols=sources,
                association_scale=_association_scale(label, style),
                printable=printable,
                crowding_radius_mm=_CROWDING_RADIUS_MM,
                weights=weights,
                edge_margin_mm=_EDGE_MARGIN_MM,
                constellation_lines=constellation_lines,
            ).total(weights)
            for candidate in label.candidates:
                if candidate.id == current_id:
                    continue
                cand_bounds = tuple(
                    placed_index.query(
                        candidate.bounds,
                        margin_mm=_CROWDING_RADIUS_MM,
                        exclude=label.id,
                    )
                )
                cand_symbols = tuple(symbols_index.query(candidate.bounds))
                cand_stars = _nearby_stars(label, candidate.bounds, stars_index, stars, style)
                if not _is_valid(
                    label,
                    candidate,
                    cand_bounds,
                    printable,
                    cand_symbols,
                    cand_stars,
                    style,
                    furniture,
                ):
                    continue
                cost = score_candidate(
                    candidate,
                    target_anchor=anchor,
                    placed_bounds=cand_bounds,
                    symbols=cand_symbols,
                    stars=cand_stars,
                    associated_star_ids=_associated_star_ids(label, cand_stars),
                    related_star_ids=_related_star_ids(label, cand_stars),
                    star_clearance=style.label.star_clearance,
                    target_source_id=_association_source_id(label),
                    source_association=style.label.source_association,
                    source_symbols=sources,
                    association_scale=_association_scale(label, style),
                    printable=printable,
                    crowding_radius_mm=_CROWDING_RADIUS_MM,
                    weights=weights,
                    edge_margin_mm=_EDGE_MARGIN_MM,
                    constellation_lines=constellation_lines,
                ).total(weights)
                if cost < best_cost - 1e-9:
                    best_cost = cost
                    best_id = candidate.id
            if best_id != current_id:
                placements[label.id] = best_id
                new_candidate = label.candidate(best_id)
                if new_candidate is not None:
                    placed_index.set(label.id, new_candidate.bounds, new_candidate.bounds)
                changed = True
        if not changed:
            break
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
            placed_index.set(label_id, placed_candidate.bounds, placed_candidate.bounds)
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
            source_symbols=sources,
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
