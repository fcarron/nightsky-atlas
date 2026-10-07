from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from nightsky_atlas.atlas.config import StyleConfig, TargetedDsoLeaderStyle
from nightsky_atlas.chart.page import PageRect, PageTransform
from nightsky_atlas.layout.leader_lines import (
    leader_line_for,
    prepare_leader_routing_context,
    resolve_leader_lines,
)
from nightsky_atlas.layout.models import Label
from nightsky_atlas.layout.text_geometry import candidate_ink_bounds
from nightsky_atlas.layout.validation import validate_layout
from nightsky_atlas.scene.models import ChartScene


@dataclass(frozen=True, slots=True)
class TargetedLeaderResult:
    labels: tuple[Label, ...]
    decisions: tuple[dict[str, Any], ...]
    counts: dict[str, int]


def is_wide_dso_label(label: Label, config: TargetedDsoLeaderStyle) -> bool:
    candidate = label.effective_candidate()
    if not label.id.startswith("label:dso:") or candidate is None:
        return False
    ink = candidate_ink_bounds(candidate)
    return (
        ink.width_mm >= config.min_ink_width_mm
        and ink.width_mm >= config.min_ink_aspect_ratio * max(ink.height_mm, 0.001)
    )


def add_targeted_dso_leaders(
    labels: tuple[Label, ...],
    diagnostics: Mapping[str, Mapping[str, Any]],
    scene: ChartScene,
    transform: PageTransform,
    style: StyleConfig,
    *,
    furniture: Sequence[PageRect] = (),
) -> TargetedLeaderResult:
    config = style.label.leader_lines.targeted_dso
    if not style.label.leader_lines.enabled or not config.enabled:
        return TargetedLeaderResult(labels, (), {})
    output = labels
    decisions: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    context = None
    baseline_issues: set[str] = set()
    for label in sorted(labels, key=lambda item: (-item.priority, item.id)):
        if label.hidden or label.locked or label.leader_line:
            continue
        if not is_wide_dso_label(label, config):
            continue
        diagnostic = diagnostics.get(label.id)
        decision: dict[str, Any] = {"label_id": label.id, "text": label.text}
        decisions.append(decision)

        def reject(reason: str, decision: dict[str, Any] = decision) -> None:
            decision["result"] = reason
            counts[reason] += 1

        if diagnostic is None:
            reject("missing_diagnostics")
            continue
        ambiguous = (
            diagnostic.get("competing_owner_cost", 0.0) >= config.min_competing_owner_cost
            or diagnostic.get("association_corridor_cost", 0.0) > 0.0
            or diagnostic.get("ownership_margin_weak", False)
        )
        if not ambiguous:
            reject("clear_association")
            continue
        if context is None:
            context = prepare_leader_routing_context(scene, transform, style)
            baseline_issues = {
                issue.id
                for issue in validate_layout(
                    labels, scene, transform, style, furniture=furniture
                ).issues
            }
        updated = replace(label, leader_line=True, leader_line_reason="targeted_long_label")
        proposed = tuple(updated if item.id == label.id else item for item in output)
        route = leader_line_for(updated, proposed, scene, transform, style, context=context)
        if route is None:
            reject("no_safe_route_at_current_position")
            continue
        length = math.hypot(route.end.x_mm - route.start.x_mm, route.end.y_mm - route.start.y_mm)
        decision["length_mm"] = length
        if length > config.max_length_mm:
            reject("line_too_long")
            continue
        before = resolve_leader_lines(output, scene, transform, style, context=context)
        after = resolve_leader_lines(proposed, scene, transform, style, context=context)
        if (
            len(after) != sum(item.leader_line for item in proposed)
            or tuple(item for item in after if item.label_id != label.id) != before
        ):
            reject("crossing_or_existing_route_changed")
            continue
        issues = {
            issue.id
            for issue in validate_layout(
                proposed, scene, transform, style, furniture=furniture
            ).issues
        }
        if issues - baseline_issues:
            reject("new_hard_issue")
            continue
        output = proposed
        decision["result"] = "added"
        counts["added"] += 1
    return TargetedLeaderResult(output, tuple(decisions), dict(sorted(counts.items())))
