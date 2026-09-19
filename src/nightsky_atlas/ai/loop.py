"""Bounded AI optimization loop.

The loop improves a usable deterministic layout; it can never make a broken
page valid on its own.  Every iteration is recorded for audit and replay, and
termination is guaranteed (``AGENTS.md`` section 19).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nightsky_atlas.ai.actions import apply_review_actions
from nightsky_atlas.ai.base import ChartReviewer
from nightsky_atlas.atlas.config import StyleConfig
from nightsky_atlas.chart.page import PageTransform
from nightsky_atlas.chart.presentation import presentation_for
from nightsky_atlas.layout.models import Label
from nightsky_atlas.layout.optimizer import layout_cost, layout_hash
from nightsky_atlas.layout.validation import validate_layout
from nightsky_atlas.render.furniture import furniture_obstacles
from nightsky_atlas.render.review import render_review_png
from nightsky_atlas.review.build import build_review_request
from nightsky_atlas.review.models import ReviewRequest
from nightsky_atlas.review.schema import ReviewValidationError
from nightsky_atlas.scene.models import ChartScene

__all__ = [
    "AILoopResult",
    "IterationRecord",
    "optimize_with_ai",
    "write_history",
]

RequestFactory = Callable[[tuple[Label, ...], int], ReviewRequest]


@dataclass(frozen=True, slots=True)
class IterationRecord:
    """One AI review iteration, with before/after metrics."""

    iteration: int
    layout_hash_before: str
    layout_hash_after: str
    page_score: float
    issue_count: int
    applied: tuple[str, ...]
    rejected: tuple[tuple[str, str], ...]
    cost_before: float
    cost_after: float
    usage_model: str | None
    usage_cost_usd: float | None
    cumulative_cost_usd: float
    error: str | None = None
    proposed_actions: tuple[dict[str, str], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable mapping of this iteration."""
        return {
            "iteration": self.iteration,
            "layout_hash_before": self.layout_hash_before,
            "layout_hash_after": self.layout_hash_after,
            "page_score": self.page_score,
            "issue_count": self.issue_count,
            "applied": list(self.applied),
            "rejected": [list(item) for item in self.rejected],
            "cost_before": self.cost_before,
            "cost_after": self.cost_after,
            "usage_model": self.usage_model,
            "usage_cost_usd": self.usage_cost_usd,
            "cumulative_cost_usd": self.cumulative_cost_usd,
            "error": self.error,
            "proposed_actions": list(self.proposed_actions),
        }


@dataclass(frozen=True, slots=True)
class AILoopResult:
    """Final layout plus the full iteration history and stop reason."""

    labels: tuple[Label, ...]
    iterations: tuple[IterationRecord, ...]
    stopped_reason: str
    final_cost: float
    total_cost_usd: float

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable mapping of the loop result."""
        return {
            "stopped_reason": self.stopped_reason,
            "final_cost": self.final_cost,
            "total_cost_usd": self.total_cost_usd,
            "iterations": [record.to_dict() for record in self.iterations],
        }


def _significant_issues(result: object, threshold: int) -> bool:
    return any(issue.severity >= threshold for issue in result.issues)  # type: ignore[attr-defined]


def optimize_with_ai(
    labels: tuple[Label, ...],
    scene: ChartScene,
    transform: PageTransform,
    style: StyleConfig,
    reviewer: ChartReviewer,
    *,
    max_iterations: int = 4,
    max_cost_usd: float = 0.05,
    min_target_score: float = 9.0,
    significant_severity: int = 6,
    min_action_severity: int = 6,
    request_factory: RequestFactory | None = None,
    page_id: str = "chart",
    images: tuple[str, ...] = (),
) -> AILoopResult:
    """Run a bounded AI review loop over an already-usable layout."""
    if request_factory is None:
        request_factory = _default_request_factory(scene, transform, style, page_id, images)

    current = labels
    current_cost, _ = layout_cost(current, scene, transform, style)
    current_hash = layout_hash(current)
    seen_hashes = {current_hash}
    history: list[IterationRecord] = []
    total_cost_usd = 0.0
    stopped_reason = "max_iterations"

    for iteration in range(max_iterations):
        request = request_factory(current, iteration)
        try:
            review = reviewer.review(request)
        except (ReviewValidationError, ValueError) as exc:
            history.append(
                IterationRecord(
                    iteration=iteration,
                    layout_hash_before=current_hash,
                    layout_hash_after=current_hash,
                    page_score=0.0,
                    issue_count=0,
                    applied=(),
                    rejected=(),
                    cost_before=current_cost,
                    cost_after=current_cost,
                    usage_model=None,
                    usage_cost_usd=None,
                    cumulative_cost_usd=total_cost_usd,
                    error=str(exc),
                )
            )
            stopped_reason = "invalid_review"
            break

        usage = getattr(reviewer, "last_usage", None)
        usage_cost = getattr(usage, "cost_usd", None)
        if usage_cost:
            total_cost_usd += usage_cost

        outcome = apply_review_actions(
            current,
            review,
            scene,
            transform,
            style,
            min_severity=min_action_severity,
            require_cost_non_increase=True,
        )
        new_labels = outcome.labels
        new_cost, _ = layout_cost(new_labels, scene, transform, style)
        new_hash = layout_hash(new_labels)

        history.append(
            IterationRecord(
                iteration=iteration,
                layout_hash_before=current_hash,
                layout_hash_after=new_hash,
                page_score=review.page_score,
                issue_count=len(review.issues),
                applied=outcome.applied,
                rejected=outcome.rejected,
                cost_before=current_cost,
                cost_after=new_cost,
                usage_model=getattr(usage, "model", None),
                usage_cost_usd=usage_cost,
                cumulative_cost_usd=total_cost_usd,
                proposed_actions=tuple(
                    {
                        "element_id": issue.element_id,
                        "reason_code": issue.issue_type.value,
                        "action": issue.action.type.value if issue.action else "none",
                    }
                    for issue in review.issues
                ),
            )
        )

        current, current_cost, current_hash = new_labels, new_cost, new_hash

        if not _significant_issues(review, significant_severity):
            stopped_reason = "no_significant_issues"
            break
        if review.page_score >= min_target_score:
            stopped_reason = "target_score_reached"
            break
        if not outcome.applied:
            stopped_reason = "no_accepted_changes"
            break
        if new_hash == history[-1].layout_hash_before:
            stopped_reason = "no_change"
            break
        if new_hash in seen_hashes:
            stopped_reason = "repeated_layout"
            break
        if total_cost_usd >= max_cost_usd:
            stopped_reason = "cost_budget_reached"
            break
        seen_hashes.add(new_hash)

    return AILoopResult(
        labels=current,
        iterations=tuple(history),
        stopped_reason=stopped_reason,
        final_cost=current_cost,
        total_cost_usd=total_cost_usd,
    )


def _default_request_factory(
    scene: ChartScene,
    transform: PageTransform,
    style: StyleConfig,
    page_id: str,
    images: tuple[str, ...],
) -> RequestFactory:
    if len(images) > 1:
        raise ValueError(
            "default AI review supports one full-page image; use a request factory for crops"
        )

    def factory(labels: tuple[Label, ...], iteration: int) -> ReviewRequest:
        current_images = images
        if images:
            original = Path(images[0])
            rendered = original.with_name(f"{original.stem}-iteration-{iteration}.png")
            render_review_png(scene, transform, style, labels, rendered)
            current_images = (str(rendered),)
        validation = validate_layout(
            labels,
            scene,
            transform,
            style,
            furniture=furniture_obstacles(
                transform, scene.definition, style, presentation_for(scene.definition)
            ),
        )
        diagnostics = {
            "hard_issue_count": float(len(validation.issues)),
            "iteration": float(iteration),
        }
        return build_review_request(
            page_id=page_id,
            scene=scene,
            labels=labels,
            transform=transform,
            diagnostics=diagnostics,
            images=current_images,
        )

    return factory


def write_history(path: str | Path, result: AILoopResult) -> Path:
    """Persist an AI optimization history as JSON for audit and replay."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return target
