"""Deterministic label optimizer.

Strategy (``AGENTS.md`` section 15.3): priority-ordered greedy placement
followed by a deterministic local repair pass.  No stochastic search is used,
so the result is reproducible.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from nightsky_atlas.atlas.config import StyleConfig
from nightsky_atlas.chart.page import PagePoint, PageRect, PageTransform
from nightsky_atlas.layout.candidates import CANDIDATE_PREFERENCE
from nightsky_atlas.layout.geometry import circle_intersects_rect, rects_overlap
from nightsky_atlas.layout.models import Label, LabelCandidate
from nightsky_atlas.layout.scoring import CostWeights, SymbolCircle, score_candidate
from nightsky_atlas.render.symbols import StarSizeModel, galaxy_ellipse
from nightsky_atlas.scene.models import ChartScene

__all__ = ["OptimizationResult", "layout_cost", "layout_hash", "optimize_labels"]

_IMPORTANT_STAR_MAGNITUDE = 6.0
_CROWDING_RADIUS_MM = 6.0
_EDGE_MARGIN_MM = 8.0
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


def _symbol_circles(
    scene: ChartScene, transform: PageTransform, style: StyleConfig
) -> tuple[SymbolCircle, ...]:
    size_model = StarSizeModel.from_style(style.star)
    symbols: list[SymbolCircle] = []
    for scene_star in scene.stars:
        if scene_star.star.magnitude <= _IMPORTANT_STAR_MAGNITUDE:
            symbols.append(
                SymbolCircle(
                    center=transform.to_page(scene_star.chart_point),
                    radius_mm=size_model.radius_mm(scene_star.star.magnitude),
                )
            )
    for scene_dso in scene.deep_sky_objects:
        radius = style.dso.size_mm / 2.0
        geometry = galaxy_ellipse(
            scene_dso.dso,
            mm_per_deg=transform.mm_per_deg,
            min_axis_mm=style.dso.min_axis_mm,
            max_axis_mm=style.dso.max_axis_mm,
        )
        if geometry is not None:
            radius = geometry.major_mm / 2.0
        symbols.append(
            SymbolCircle(center=transform.to_page(scene_dso.chart_point), radius_mm=radius)
        )
    return tuple(symbols)


def _target_anchors(
    labels: tuple[Label, ...], scene: ChartScene, transform: PageTransform
) -> dict[str, PagePoint]:
    anchors: dict[str, PagePoint] = {}
    for scene_star in scene.stars:
        anchors[scene_star.star.id] = transform.to_page(scene_star.chart_point)
    for scene_dso in scene.deep_sky_objects:
        anchors[scene_dso.dso.id] = transform.to_page(scene_dso.chart_point)
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


def _is_valid(
    bounds: PageRect,
    placed_bounds: tuple[PageRect, ...],
    printable: PageRect,
    symbols: tuple[SymbolCircle, ...],
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
) -> OptimizationResult:
    """Optimize label placement deterministically."""
    weights = weights or CostWeights()
    printable = _printable(transform)
    symbols = _symbol_circles(scene, transform, style)
    anchors = _target_anchors(labels, scene, transform)
    ordered = tuple(sorted(labels, key=lambda label: (-label.priority, label.id)))

    # Initial layout: fixed preference order (first candidate), as rendered
    # without optimization.
    before = {label.id: (label.candidates[0].id if label.candidates else None) for label in ordered}
    cost_before, totals_before = _evaluate(
        ordered, before, anchors, printable, symbols, weights
    )

    placements: dict[str, str | None] = {}
    placed_bounds: list[PageRect] = []
    for label in ordered:
        best: tuple[tuple[float, float, int], LabelCandidate] | None = None
        for candidate in label.candidates:
            valid = _is_valid(candidate.bounds, tuple(placed_bounds), printable, symbols)
            breakdown = score_candidate(
                candidate,
                target_anchor=_anchor_for(label, anchors, candidate),
                placed_bounds=tuple(placed_bounds),
                symbols=symbols,
                printable=printable,
                crowding_radius_mm=_CROWDING_RADIUS_MM,
                weights=weights,
                edge_margin_mm=_EDGE_MARGIN_MM,
            )
            key = (
                0.0 if valid else 1.0,
                breakdown.total(weights),
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
        placed_bounds.append(best[1].bounds)

    placements = _local_repair(
        ordered, placements, anchors, printable, symbols, weights
    )
    cost_after, totals_after = _evaluate(
        ordered, placements, anchors, printable, symbols, weights
    )

    optimized = tuple(
        label.with_placement(
            placements.get(label.id), hidden=placements.get(label.id) is None
        )
        for label in labels
    )
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


def _others_bounds(
    label: Label,
    placements: dict[str, str | None],
    label_by_id: dict[str, Label],
) -> tuple[PageRect, ...]:
    others: list[PageRect] = []
    for other_id, other_candidate_id in placements.items():
        if other_id == label.id or other_candidate_id is None:
            continue
        other_candidate = label_by_id[other_id].candidate(other_candidate_id)
        if other_candidate is not None:
            others.append(other_candidate.bounds)
    return tuple(others)


def _local_repair(
    ordered: tuple[Label, ...],
    placements: dict[str, str | None],
    anchors: dict[str, PagePoint],
    printable: PageRect,
    symbols: tuple[SymbolCircle, ...],
    weights: CostWeights,
) -> dict[str, str | None]:
    label_by_id = {label.id: label for label in ordered}
    for _ in range(_MAX_REPAIR_PASSES):
        changed = False
        for label in ordered:
            current_id = placements.get(label.id)
            if current_id is None:
                continue
            current = label.candidate(current_id)
            if current is None:
                continue
            others = _others_bounds(label, placements, label_by_id)
            anchor = _anchor_for(label, anchors, current)
            best_id = current_id
            best_cost = score_candidate(
                current,
                target_anchor=anchor,
                placed_bounds=others,
                symbols=symbols,
                printable=printable,
                crowding_radius_mm=_CROWDING_RADIUS_MM,
                weights=weights,
                edge_margin_mm=_EDGE_MARGIN_MM,
            ).total(weights)
            for candidate in label.candidates:
                if candidate.id == current_id:
                    continue
                if not _is_valid(candidate.bounds, others, printable, symbols):
                    continue
                cost = score_candidate(
                    candidate,
                    target_anchor=anchor,
                    placed_bounds=others,
                    symbols=symbols,
                    printable=printable,
                    crowding_radius_mm=_CROWDING_RADIUS_MM,
                    weights=weights,
                    edge_margin_mm=_EDGE_MARGIN_MM,
                ).total(weights)
                if cost < best_cost - 1e-9:
                    best_cost = cost
                    best_id = candidate.id
            if best_id != current_id:
                placements[label.id] = best_id
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
) -> tuple[float, dict[str, float]]:
    label_by_id = {label.id: label for label in ordered}
    total = 0.0
    totals: dict[str, float] = {}
    for label in ordered:
        candidate_id = placements.get(label.id)
        if candidate_id is None:
            continue
        candidate = label.candidate(candidate_id)
        if candidate is None:
            continue
        others = _others_bounds(label, placements, label_by_id)
        breakdown = score_candidate(
            candidate,
            target_anchor=_anchor_for(label, anchors, candidate),
            placed_bounds=others,
            symbols=symbols,
            printable=printable,
            crowding_radius_mm=_CROWDING_RADIUS_MM,
            weights=weights,
            edge_margin_mm=_EDGE_MARGIN_MM,
        )
        total += breakdown.total(weights)
        for name, value in breakdown.components().items():
            totals[name] = totals.get(name, 0.0) + value
    return total, totals

def layout_hash(labels: tuple[Label, ...]) -> str:
    """Return a stable hash of placements for repeated-layout detection."""
    payload = [
        [label.id, label.selected_candidate_id, label.hidden]
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
    anchors = _target_anchors(labels, scene, transform)
    ordered = tuple(sorted(labels, key=lambda label: (-label.priority, label.id)))

    placements: dict[str, str | None] = {}
    for label in labels:
        if label.hidden or not label.candidates:
            placements[label.id] = None
        else:
            placements[label.id] = label.selected_candidate_id or label.candidates[0].id
    return _evaluate(ordered, placements, anchors, printable, symbols, weights)
