"""Deterministic label placement, conflict repair and leader fallback orchestration."""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import Any

from nightsky_atlas.atlas.config import StyleConfig
from nightsky_atlas.chart.page import PagePoint, PageRect, PageTransform
from nightsky_atlas.layout.association import (
    SourceGeometry,
    dso_source_geometries,
    source_outline_edge_distance,
)
from nightsky_atlas.layout.candidates import direction_preference_rank
from nightsky_atlas.layout.diagnostics import (
    _dso_placement_metrics,
    _label_diagnostics,
)
from nightsky_atlas.layout.geometry import (
    circle_intersects_rect,
    rects_overlap,
)
from nightsky_atlas.layout.leader_lines import (
    leader_line_for,
    prepare_leader_routing_context,
    resolve_leader_lines,
)
from nightsky_atlas.layout.models import Label, LabelCandidate
from nightsky_atlas.layout.placement import (
    _CROWDING_RADIUS_MM,
    _GRID_CELL_MM,
    _build_placed_index,
    _build_star_index,
    _build_symbol_index,
    _candidate_breakdown,
    _candidate_rejection_reason,
    _CandidateScoreCache,
    _collision_bounds,
    _evaluate,
    _is_valid,
    _labels_overlap,
    _nearby_stars,
    _printable,
    _resolved_weights,
    _star_circles,
    _symbol_circles,
    _target_anchors,
    _weighted_ownership_cost,
)
from nightsky_atlas.layout.scoring import (
    CostBreakdown,
    CostWeights,
    StarCircle,
    SymbolCircle,
)
from nightsky_atlas.layout.spatial import RectIndex
from nightsky_atlas.layout.targeted_leaders import add_targeted_dso_leaders
from nightsky_atlas.layout.text_geometry import (
    candidate_ink_bounds,
)
from nightsky_atlas.render.constellation_lines import resolve_constellation_lines
from nightsky_atlas.scene.models import ChartScene

__all__ = ["OptimizationResult", "layout_cost", "layout_hash", "optimize_labels"]

_MAX_REPAIR_PASSES = 4


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
    anchors = _target_anchors(scene, transform, style)
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

    placements, placed_index = _greedy_place(ordered, cost_cache)

    local_repair_stats: dict[str, Any] = {}
    placements = _local_repair(
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
        local_repair_stats,
    )
    placements, component_stats = _joint_dso_optimize(
        ordered,
        placements,
        placed_index,
        style,
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
    auto_labels = _consider_star_leader_fallbacks(
        optimized, placed_index, scene, transform, cost_cache
    )
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


def _greedy_place(
    ordered: tuple[Label, ...], cost_cache: _CandidateScoreCache
) -> tuple[dict[str, str | None], RectIndex[PageRect]]:
    placements: dict[str, str | None] = {}
    placed_index: RectIndex[PageRect] = RectIndex(_GRID_CELL_MM)
    for label in ordered:
        if not label.locked:
            continue
        candidate_id = label.selected_candidate_id
        candidate = label.candidate(candidate_id) if candidate_id is not None else None
        if candidate is not None:
            placements[label.id] = candidate.id
            bounds = _collision_bounds(label, candidate, cost_cache.style)
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
            nearby_symbols = tuple(cost_cache.symbols_index.query(candidate.bounds))
            nearby_stars = _nearby_stars(
                label, candidate.bounds, cost_cache.stars_index, cost_cache.stars, cost_cache.style
            )
            valid = _is_valid(
                label,
                candidate,
                nearby_bounds,
                cost_cache.printable,
                nearby_symbols,
                nearby_stars,
                cost_cache.style,
                cost_cache.furniture,
                cost_cache.sources,
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
                direction_preference_rank(candidate.position),
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
        bounds = _collision_bounds(label, best[1], cost_cache.style)
        placed_index.set(label.id, bounds, bounds)

    return placements, placed_index


def _local_repair(
    ordered: tuple[Label, ...],
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


def _dso_conflict_components(
    labels: tuple[Label, ...], style: StyleConfig
) -> tuple[tuple[str, ...], ...]:
    """Connect DSO labels whose legal candidate regions can compete for space."""
    dso_labels = tuple(sorted(
        (label for label in labels if label.id.startswith("label:dso:") and not label.locked),
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
    style: StyleConfig,
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
    placed_index: RectIndex[PageRect],
    style: StyleConfig,
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
            style,
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
            and source_outline_edge_distance(source, source_bounds) <= 0.0
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
                    and source_outline_edge_distance(source, visible_bounds) <= 0.0
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

    def active_conflict_groups(candidate_labels: tuple[Label, ...]) -> list[tuple[str, ...]]:
        placed = tuple(
            (label, label.effective_candidate())
            for label in candidate_labels
            if not label.hidden and label.effective_candidate() is not None
        )
        adjacency: dict[str, set[str]] = {}
        label_id_by_target = {
            label.target_id: label.id
            for label in candidate_labels
            if label.id.startswith("label:dso:")
        }
        for index, (first, first_candidate) in enumerate(placed):
            if first_candidate is None or not first.id.startswith("label:dso:"):
                continue
            source_bounds = candidate_ink_bounds(first_candidate)
            nearby_ids = {symbol.id for symbol in symbols_index.query(source_bounds)}
            for source in sources:
                related_label_id = label_id_by_target.get(source.id)
                if (
                    source.id == first.target_id
                    or related_label_id is None
                    or related_label_id == first.id
                    or source.id not in nearby_ids
                    or not circle_intersects_rect(
                        source.center, source.collision_radius_mm, source_bounds
                    )
                    or source_outline_edge_distance(source, source_bounds) > 0.0
                ):
                    continue
                adjacency.setdefault(first.id, set()).add(related_label_id)
                adjacency.setdefault(related_label_id, set()).add(first.id)
            for second, second_candidate in placed[index + 1 :]:
                if (
                    second_candidate is not None
                    and second.id.startswith("label:dso:")
                    and _labels_overlap(first, first_candidate, second, second_candidate, style)
                ):
                    adjacency.setdefault(first.id, set()).add(second.id)
                    adjacency.setdefault(second.id, set()).add(first.id)
        groups: list[tuple[str, ...]] = []
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
            if len(members) >= max(
                3, style.label.dso_placement.hard_repair_neighborhood_labels - 1
            ):
                groups.append(tuple(sorted(members)))
        return sorted(groups, key=lambda group: (-len(group), group))

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
                style,
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

    groups_to_repair = active_conflict_groups(current_labels())
    for _ in range(2):
        current = current_labels()
        current_hard_count = hard_conflict_count(current)
        if current_hard_count == 0:
            break
        changed = False
        for group in groups_to_repair:
            if (
                stats["neighborhood_searches"]
                >= style.label.dso_placement.hard_repair_search_limit
            ):
                stats["neighborhood_search_limit_reached"] = True
                break
            neighborhood = expand_neighborhood(group)
            if len(neighborhood) > style.label.dso_placement.hard_repair_neighborhood_labels:
                continue
            stats["neighborhood_searches"] += 1
            stats["neighborhood_sizes"].append(len(neighborhood))
            solution, visited = _joint_component_search(
                neighborhood,
                labels_by_id,
                placements,
                style,
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
                and source_outline_edge_distance(source, visible_bounds) <= 0.0
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


def _consider_star_leader_fallbacks(
    optimized: tuple[Label, ...],
    placed_index: RectIndex[PageRect],
    scene: ChartScene,
    transform: PageTransform,
    cost_cache: _CandidateScoreCache,
) -> list[Label]:
    auto_labels = list(optimized)
    for index, label in enumerate(auto_labels):
        candidate = label.effective_candidate()
        if label.hidden or label.locked or candidate is None:
            continue
        if label.id.startswith("label:dso:"):
            continue
        threshold = _leader_ambiguity_threshold(label, cost_cache.style)
        if threshold is None:
            continue
        selected_breakdown = _candidate_breakdown(
            label,
            candidate,
            cost_cache.anchors,
            cost_cache.printable,
            placed_index,
            cost_cache.symbols_index,
            cost_cache.sources,
            cost_cache.stars_index,
            cost_cache.stars,
            cost_cache.style,
            cost_cache.weights,
            cost_cache.constellation_lines,
        )
        selected_ambiguity = _ownership_ambiguity(selected_breakdown)
        if selected_ambiguity < threshold:
            continue
        direct_ambiguities = []
        for direct in label.candidates:
            if direct.ring >= cost_cache.style.label.leader_lines.auto_min_ring:
                continue
            nearby_bounds = tuple(
                placed_index.query(
                    direct.bounds,
                    margin_mm=_CROWDING_RADIUS_MM,
                    exclude=label.id,
                )
            )
            nearby_symbols = tuple(cost_cache.symbols_index.query(direct.bounds))
            nearby_stars = _nearby_stars(
                label, direct.bounds, cost_cache.stars_index, cost_cache.stars, cost_cache.style
            )
            if not _is_valid(
                label,
                direct,
                nearby_bounds,
                cost_cache.printable,
                nearby_symbols,
                nearby_stars,
                cost_cache.style,
                cost_cache.furniture,
                cost_cache.sources,
            ):
                continue
            direct_ambiguities.append(
                _ownership_ambiguity(
                    _candidate_breakdown(
                        label,
                        direct,
                        cost_cache.anchors,
                        cost_cache.printable,
                        placed_index,
                        cost_cache.symbols_index,
                        cost_cache.sources,
                        cost_cache.stars_index,
                        cost_cache.stars,
                        cost_cache.style,
                        cost_cache.weights,
                        cost_cache.constellation_lines,
                    )
                )
            )
        if direct_ambiguities and min(direct_ambiguities) < threshold:
            continue
        if leader_line_for(label, tuple(auto_labels), scene, transform, cost_cache.style) is None:
            continue
        proposed = list(auto_labels)
        proposed[index] = replace(
            label,
            leader_line=True,
            leader_line_reason="association_ambiguity",
        )
        enabled_count = sum(item.leader_line for item in proposed)
        if len(resolve_leader_lines(
            tuple(proposed), scene, transform, cost_cache.style
        )) == enabled_count:
            auto_labels = proposed
    return auto_labels


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
    anchors = _target_anchors(scene, transform, style)
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
