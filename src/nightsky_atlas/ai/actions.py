"""Apply whitelisted AI review actions to a copied layout.

Actions are applied one at a time; after each, the deterministic validator
runs and any action that introduces hard violations is rejected
(``AGENTS.md`` sections 18.4 and 18.5).  When a reviewer asks to move a label
to a candidate that is unavailable or that collides, the action engine falls
back to a deterministic repair: it searches the label's own candidates and
applies the cheapest hard-clean placement.  The reviewer supplies the *intent*;
the deterministic engine owns the actual placement.
"""

from __future__ import annotations

from dataclasses import dataclass

from nightsky_atlas.atlas.config import StyleConfig
from nightsky_atlas.chart.page import PageRect, PageTransform
from nightsky_atlas.chart.presentation import presentation_for
from nightsky_atlas.layout.models import Label
from nightsky_atlas.layout.optimizer import layout_cost
from nightsky_atlas.layout.validation import validate_layout
from nightsky_atlas.render.furniture import furniture_obstacles
from nightsky_atlas.review.schema import ReviewAction, ReviewActionType, ReviewResult
from nightsky_atlas.scene.models import ChartScene

__all__ = ["ApplyResult", "apply_review_actions"]

_COST_EPSILON = 1e-9
DEFAULT_SOFT_COST_EPSILON = 0.25


@dataclass(frozen=True, slots=True)
class ApplyResult:
    """Outcome of applying a review's actions."""

    labels: tuple[Label, ...]
    applied: tuple[str, ...]
    rejected: tuple[tuple[str, str], ...]


def _apply_one(label: Label, action: ReviewAction) -> Label | None:
    if action.type == ReviewActionType.SELECT_CANDIDATE:
        candidate_id = f"{label.id}:{action.candidate}"
        if label.candidate(candidate_id) is None:
            return None
        return label.with_placement(candidate_id)
    if action.type == ReviewActionType.MOVE_LABEL:
        candidates = [
            item for item in label.candidates if item.position == action.preferred_direction
        ]
        if not candidates:
            return None
        ring_by_distance = {"near": 0, "medium": 1, "far": 2}
        wanted_ring = ring_by_distance.get(action.distance or "near", 0)
        candidate = min(
            candidates, key=lambda item: (abs(item.ring - wanted_ring), item.ring, item.id)
        )
        return label.with_placement(candidate.id)
    if action.type == ReviewActionType.FINE_ADJUST_LABEL:
        # Intent is deliberately mapped to the nearest existing legal candidate;
        # no reviewer-supplied page coordinate ever enters the layout document.
        current = label.effective_candidate()
        if current is None:
            return None
        wanted_x = current.bounds.center.x_mm + (action.offset_x_mm or 0.0)
        wanted_y = current.bounds.center.y_mm + (action.offset_y_mm or 0.0)
        candidate = min(
            label.candidates,
            key=lambda item: (
                (item.bounds.center.x_mm - wanted_x) ** 2
                + (item.bounds.center.y_mm - wanted_y) ** 2,
                item.id,
            ),
        )
        return label.with_placement(candidate.id)
    if action.type == ReviewActionType.SHOW_OPTIONAL_LABEL:
        candidate = label.effective_candidate()
        if candidate is None:
            return None
        return label.with_placement(candidate.id, hidden=False)
    if action.type == ReviewActionType.HIDE_OPTIONAL_LABEL:
        if label.mandatory:
            return None
        return label.with_placement(None, hidden=True)
    if action.type == ReviewActionType.REQUEST_LINE_KNOCKOUT:
        # Knockouts are derived from every final visible label by the renderer.
        # Returning the same placement records the review intent without letting
        # AI edit line geometry.
        candidate = label.effective_candidate()
        return label.with_placement(candidate.id, hidden=label.hidden) if candidate else None
    return None


def _replace(labels: tuple[Label, ...], label_id: str, updated: Label) -> tuple[Label, ...]:
    return tuple(updated if item.id == label_id else item for item in labels)


def _hard_issues(
    labels: tuple[Label, ...],
    scene: ChartScene,
    transform: PageTransform,
    style: StyleConfig,
    furniture: tuple[PageRect, ...],
) -> set[str]:
    return {
        issue.id
        for issue in validate_layout(labels, scene, transform, style, furniture=furniture).issues
    }


def _repair_candidate(
    label: Label,
    current: tuple[Label, ...],
    scene: ChartScene,
    transform: PageTransform,
    style: StyleConfig,
    furniture: tuple[PageRect, ...],
    baseline: set[str],
    current_cost: float,
) -> tuple[tuple[Label, ...], set[str], float] | None:
    """Move a label to its cheapest hard-clean candidate.

    The label's current placement is skipped, so a repair always changes
    something.  Returns ``None`` when no candidate is both hard-clean and
    cheaper than the current layout.
    """
    current_candidate = None if label.hidden else label.effective_candidate()
    current_id = current_candidate.id if current_candidate is not None else None
    best_cost = current_cost
    best: tuple[tuple[Label, ...], set[str], float] | None = None
    for candidate in label.candidates:
        if candidate.id == current_id:
            continue
        candidate_labels = _replace(current, label.id, label.with_placement(candidate.id))
        issues = _hard_issues(candidate_labels, scene, transform, style, furniture)
        if not issues <= baseline:
            continue
        cost = layout_cost(candidate_labels, scene, transform, style)[0]
        if cost < best_cost - _COST_EPSILON:
            best = (candidate_labels, issues, cost)
            best_cost = cost
    return best


def apply_review_actions(
    labels: tuple[Label, ...],
    result: ReviewResult,
    scene: ChartScene,
    transform: PageTransform,
    style: StyleConfig,
    *,
    min_severity: int = 1,
    require_cost_non_increase: bool = False,
    soft_cost_epsilon: float = DEFAULT_SOFT_COST_EPSILON,
) -> ApplyResult:
    """Apply a review's actions, rejecting those that break hard constraints.

    Issues with a severity below ``min_severity`` are ignored, which suppresses
    low-confidence noise from the reviewer.  A ``select_candidate`` that is
    unavailable or colliding is repaired deterministically when the label has a
    cheaper hard-clean candidate.  With ``require_cost_non_increase`` the
    deterministic optimizer's acceptance gate also applies: a direct move that
    would raise the soft cost is treated like a collision and repaired or
    rejected, so an AI pass can never degrade the layout.
    """
    current = labels
    applied: list[str] = []
    rejected: list[tuple[str, str]] = []
    furniture = furniture_obstacles(
        transform, scene.definition, style, presentation_for(scene.definition)
    )
    baseline = _hard_issues(current, scene, transform, style, furniture)
    current_cost = layout_cost(current, scene, transform, style)[0]

    for issue in result.issues:
        action = issue.action
        if action is None or issue.severity < min_severity:
            continue
        label = next((item for item in current if item.id == issue.element_id), None)
        if label is None:
            rejected.append((issue.element_id, "referenced element is not a label"))
            continue
        if label.locked:
            rejected.append((issue.element_id, "label is locked by an override"))
            continue

        updated = _apply_one(label, action)
        if updated is not None:
            candidate_labels = _replace(current, label.id, updated)
            issues = _hard_issues(candidate_labels, scene, transform, style, furniture)
            if issues <= baseline:
                cost = layout_cost(candidate_labels, scene, transform, style)[0]
                if not require_cost_non_increase or cost <= current_cost + soft_cost_epsilon:
                    current, baseline, current_cost = candidate_labels, issues, cost
                    applied.append(issue.element_id)
                    continue

        if action.type in (
            ReviewActionType.SELECT_CANDIDATE,
            ReviewActionType.MOVE_LABEL,
            ReviewActionType.FINE_ADJUST_LABEL,
        ):
            repaired = _repair_candidate(
                label, current, scene, transform, style, furniture, baseline, current_cost
            )
            if repaired is not None:
                current, baseline, current_cost = repaired
                applied.append(issue.element_id)
                continue

        if updated is None:
            rejected.append((issue.element_id, f"action not applicable: {action.type.value}"))
        elif require_cost_non_increase:
            rejected.append((issue.element_id, "action increases soft cost"))
        else:
            rejected.append((issue.element_id, "action introduces hard violations"))

    return ApplyResult(labels=current, applied=tuple(applied), rejected=tuple(rejected))
