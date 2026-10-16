"""Read-only label association diagnostics and placement metrics."""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Any

from nightsky_atlas.atlas.config import StyleConfig
from nightsky_atlas.chart.page import PagePoint, PageRect, PageTransform
from nightsky_atlas.layout.association import (
    SourceGeometry,
    source_edge_distance,
    source_geometries_overlap,
    source_outline_edge_distance,
)
from nightsky_atlas.layout.leader_lines import (
    leader_line_for,
    resolve_leader_lines,
)
from nightsky_atlas.layout.models import Label
from nightsky_atlas.layout.placement import (
    _associated_star_ids,
    _association_source_id,
    _candidate_breakdown,
    _candidate_rejection_reason,
    _labels_overlap,
    _nearby_stars,
    _ownership_result,
    _related_star_ids,
    _weighted_ownership_cost,
)
from nightsky_atlas.layout.scoring import (
    CostWeights,
    StarCircle,
    SymbolCircle,
)
from nightsky_atlas.layout.spatial import RectIndex
from nightsky_atlas.layout.text_geometry import (
    candidate_ink_bounds,
)
from nightsky_atlas.scene.models import ChartScene


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
                _weighted_ownership_cost(breakdown, weights)
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
                    and source_outline_edge_distance(other_source, visible_bounds) <= 0.0
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
