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
from nightsky_atlas.layout.candidates import CANDIDATE_PREFERENCE
from nightsky_atlas.layout.geometry import circle_intersects_rect, rects_overlap
from nightsky_atlas.layout.labels import constellation_label_anchors
from nightsky_atlas.layout.leader_lines import leader_line_for, resolve_leader_lines
from nightsky_atlas.layout.models import Label, LabelCandidate
from nightsky_atlas.layout.scoring import CostWeights, SymbolCircle, score_candidate
from nightsky_atlas.layout.spatial import RectIndex
from nightsky_atlas.render.constellation_lines import resolve_constellation_lines
from nightsky_atlas.render.double_stars import printed_star_obstacles
from nightsky_atlas.render.symbols import dso_symbol_extent
from nightsky_atlas.scene.models import ChartScene

__all__ = ["OptimizationResult", "layout_cost", "layout_hash", "optimize_labels"]

_IMPORTANT_STAR_MAGNITUDE = 6.0
_CROWDING_RADIUS_MM = 6.0
_EDGE_MARGIN_MM = 8.0
_MAX_REPAIR_PASSES = 4
_GRID_CELL_MM = 8.0
_VARIANT_RANK_COST = 12.0


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


def _symbol_circles(
    scene: ChartScene, transform: PageTransform, style: StyleConfig
) -> tuple[SymbolCircle, ...]:
    symbols: list[SymbolCircle] = []
    for star in printed_star_obstacles(scene, transform, style):
        if star.magnitude <= _IMPORTANT_STAR_MAGNITUDE:
            symbols.append(
                SymbolCircle(
                    center=star.page_point,
                    radius_mm=star.collision_radius_mm,
                )
            )
    for scene_dso in scene.deep_sky_objects:
        if not scene_dso.symbol_visible:
            continue
        extent = dso_symbol_extent(scene_dso.dso, mm_per_deg=transform.mm_per_deg, style=style)
        symbols.append(
            SymbolCircle(
                center=transform.to_page(scene_dso.chart_point),
                radius_mm=extent.collision_radius_mm,
            )
        )
    return tuple(symbols)


def _target_anchors(
    labels: tuple[Label, ...], scene: ChartScene, transform: PageTransform, style: StyleConfig
) -> dict[str, PagePoint]:
    anchors: dict[str, PagePoint] = {}
    for scene_star in scene.stars:
        anchors[scene_star.star.id] = transform.to_page(scene_star.chart_point)
    for obstacle in printed_star_obstacles(scene, transform, style):
        for star_id in obstacle.star_ids:
            anchors[star_id] = obstacle.page_point
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


def _is_valid(
    bounds: PageRect,
    placed_bounds: tuple[PageRect, ...],
    printable: PageRect,
    symbols: tuple[SymbolCircle, ...],
    furniture: tuple[PageRect, ...] = (),
) -> bool:
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
    return not any(
        circle_intersects_rect(symbol.center, symbol.radius_mm, bounds) for symbol in symbols
    )


def _preference_rank(candidate: LabelCandidate) -> int:
    return CANDIDATE_PREFERENCE.index(candidate.position)


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
    weights = weights or CostWeights()
    furniture_rects = tuple(furniture)
    printable = _printable(transform)
    symbols = _symbol_circles(scene, transform, style)
    constellation_lines = tuple(
        (stroke.start, stroke.end)
        for stroke in resolve_constellation_lines(scene, transform, style)
    )
    symbols_index = _build_symbol_index(symbols)
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
        ordered, before, anchors, printable, symbols, weights, constellation_lines
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
            valid = _is_valid(
                candidate.bounds,
                nearby_bounds,
                printable,
                nearby_symbols,
                furniture_rects,
            )
            breakdown = score_candidate(
                candidate,
                target_anchor=_anchor_for(label, anchors, candidate),
                placed_bounds=nearby_bounds,
                symbols=nearby_symbols,
                printable=printable,
                crowding_radius_mm=_CROWDING_RADIUS_MM,
                weights=weights,
                edge_margin_mm=_EDGE_MARGIN_MM,
                constellation_lines=constellation_lines,
            )
            key = (
                0.0 if valid else 1.0,
                breakdown.total(weights) + candidate.variant_rank * _VARIANT_RANK_COST,
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
        weights,
        furniture_rects,
        constellation_lines,
    )
    cost_after, totals_after = _evaluate(
        ordered, placements, anchors, printable, symbols, weights, constellation_lines
    )

    optimized = tuple(
        label.with_placement(placements.get(label.id), hidden=placements.get(label.id) is None)
        for label in labels
    )
    auto_labels = list(optimized)
    for index, label in enumerate(auto_labels):
        candidate = label.effective_candidate()
        if (
            label.hidden
            or candidate is None
            or candidate.ring < style.label.leader_lines.auto_min_ring
            or leader_line_for(label, tuple(auto_labels), scene, transform, style) is None
        ):
            continue
        proposed = list(auto_labels)
        proposed[index] = replace(label, leader_line=True)
        enabled_count = sum(item.leader_line for item in proposed)
        if len(resolve_leader_lines(tuple(proposed), scene, transform, style)) == enabled_count:
            auto_labels = proposed
    optimized = tuple(auto_labels)
    placed_count = sum(1 for value in placements.values() if value is not None)
    return OptimizationResult(
        labels=optimized,
        cost_before=cost_before,
        cost_after=cost_after,
        placed_count=placed_count,
        hidden_count=len(ordered) - placed_count,
        component_totals_before=totals_before,
        component_totals_after=totals_after,
    )


def _local_repair(
    ordered: tuple[Label, ...],
    placements: dict[str, str | None],
    anchors: dict[str, PagePoint],
    printable: PageRect,
    placed_index: RectIndex[PageRect],
    symbols_index: RectIndex[SymbolCircle],
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
            best_cost = score_candidate(
                current,
                target_anchor=anchor,
                placed_bounds=nearby_bounds,
                symbols=nearby_symbols,
                printable=printable,
                crowding_radius_mm=_CROWDING_RADIUS_MM,
                weights=weights,
                edge_margin_mm=_EDGE_MARGIN_MM,
                constellation_lines=constellation_lines,
            ).total(weights) + current.variant_rank * _VARIANT_RANK_COST
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
                if not _is_valid(candidate.bounds, cand_bounds, printable, cand_symbols, furniture):
                    continue
                cost = score_candidate(
                    candidate,
                    target_anchor=anchor,
                    placed_bounds=cand_bounds,
                    symbols=cand_symbols,
                    printable=printable,
                    crowding_radius_mm=_CROWDING_RADIUS_MM,
                    weights=weights,
                    edge_margin_mm=_EDGE_MARGIN_MM,
                    constellation_lines=constellation_lines,
                ).total(weights) + candidate.variant_rank * _VARIANT_RANK_COST
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
    symbols_index = _build_symbol_index(symbols)
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
        nearby_symbols = tuple(symbols_index.query(candidate.bounds))
        breakdown = score_candidate(
            candidate,
            target_anchor=_anchor_for(label, anchors, candidate),
            placed_bounds=nearby_bounds,
            symbols=nearby_symbols,
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
    weights = weights or CostWeights()
    printable = _printable(transform)
    symbols = _symbol_circles(scene, transform, style)
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
    return _evaluate(ordered, placements, anchors, printable, symbols, weights, constellation_lines)
