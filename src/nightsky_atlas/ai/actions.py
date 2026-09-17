"""Apply whitelisted AI review actions to a copied layout.

Actions are applied one at a time; after each, the deterministic validator
runs and any action that introduces hard violations is rejected
(``AGENTS.md`` sections 18.4 and 18.5).
"""

from __future__ import annotations

from dataclasses import dataclass

from nightsky_atlas.atlas.config import StyleConfig
from nightsky_atlas.chart.page import PageTransform
from nightsky_atlas.chart.presentation import presentation_for
from nightsky_atlas.layout.models import Label
from nightsky_atlas.layout.validation import validate_layout
from nightsky_atlas.render.furniture import furniture_obstacles
from nightsky_atlas.review.schema import ReviewAction, ReviewActionType, ReviewResult
from nightsky_atlas.scene.models import ChartScene

__all__ = ["ApplyResult", "apply_review_actions"]


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
    if action.type == ReviewActionType.SHOW_OPTIONAL_LABEL:
        candidate = label.effective_candidate()
        if candidate is None:
            return None
        return label.with_placement(candidate.id, hidden=False)
    if action.type == ReviewActionType.HIDE_OPTIONAL_LABEL:
        if label.mandatory:
            return None
        return label.with_placement(None, hidden=True)
    return None


def apply_review_actions(
    labels: tuple[Label, ...],
    result: ReviewResult,
    scene: ChartScene,
    transform: PageTransform,
    style: StyleConfig,
    *,
    min_severity: int = 1,
) -> ApplyResult:
    """Apply a review's actions, rejecting those that break hard constraints.

    Issues with a severity below ``min_severity`` are ignored, which suppresses
    low-confidence noise from the reviewer.
    """
    current = labels
    applied: list[str] = []
    rejected: list[tuple[str, str]] = []
    furniture = furniture_obstacles(
        transform, scene.definition, style, presentation_for(scene.definition)
    )
    baseline = {
        issue.id
        for issue in validate_layout(
            current, scene, transform, style, furniture=furniture
        ).issues
    }

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
        if updated is None:
            rejected.append(
                (issue.element_id, f"action not applicable: {action.type.value}")
            )
            continue
        candidate_labels = tuple(
            updated if item.id == label.id else item for item in current
        )
        candidate_issues = {
            item.id
            for item in validate_layout(
                candidate_labels, scene, transform, style, furniture=furniture
            ).issues
        }
        if not candidate_issues <= baseline:
            rejected.append((issue.element_id, "action introduces hard violations"))
            continue
        current = candidate_labels
        baseline = candidate_issues
        applied.append(issue.element_id)

    return ApplyResult(labels=current, applied=tuple(applied), rejected=tuple(rejected))