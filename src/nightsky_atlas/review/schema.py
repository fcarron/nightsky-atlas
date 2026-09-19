"""Strict schema for AI review responses.

A malformed review must never alter a layout (``AGENTS.md`` section 18.3), so
the whole response is validated before use.  Unknown element references,
unknown issue or action types, out-of-range severities and invalid candidates
all fail validation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from nightsky_atlas.layout.models import CompassPosition

__all__ = [
    "PERMITTED_ACTIONS",
    "ReviewAction",
    "ReviewActionType",
    "ReviewIssue",
    "ReviewIssueType",
    "ReviewResult",
    "ReviewValidationError",
    "validate_review",
]


class ReviewValidationError(ValueError):
    """Raised when a review response fails schema validation."""


class ReviewActionType(StrEnum):
    """Whitelisted actions a reviewer may request."""

    SELECT_CANDIDATE = "select_candidate"
    MOVE_LABEL = "move_label"
    FINE_ADJUST_LABEL = "fine_adjust_label"
    SHOW_OPTIONAL_LABEL = "show_optional_label"
    HIDE_OPTIONAL_LABEL = "hide_optional_label"
    USE_LEADER_LINE = "use_leader_line"
    REMOVE_LEADER_LINE = "remove_leader_line"
    SELECT_DISPLAY_NAME_VARIANT = "select_display_name_variant"
    ENABLE_LEADER_LINE = "enable_leader_line"
    REQUEST_LINE_KNOCKOUT = "request_line_knockout"


PERMITTED_ACTIONS: tuple[str, ...] = tuple(action.value for action in ReviewActionType)


class ReviewIssueType(StrEnum):
    """Issue categories a reviewer may report."""

    AMBIGUOUS_ASSOCIATION = "ambiguous_association"
    OVERLAPPING_LABELS = "overlapping_labels"
    UNREADABLE_LABEL = "unreadable_label"
    WRONG_POSITION = "wrong_position"
    MISSING_LABEL = "missing_label"
    OTHER = "other"
    CONSTELLATION_LINE_OVERLAP = "constellation_line_overlap"
    LABEL_TOO_CLOSE_TO_SYMBOL = "label_too_close_to_symbol"
    LABEL_CLUSTER_TOO_DENSE = "label_cluster_too_dense"
    POOR_VISUAL_BALANCE = "poor_visual_balance"
    LEADER_LINE_NEEDED = "leader_line_needed"
    DISPLAY_NAME_TOO_LONG = "display_name_too_long"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReviewAction(_StrictModel):
    """A single requested change to presentation state."""

    type: ReviewActionType
    candidate: str | None = None
    display_name_variant: str | None = None
    preferred_direction: CompassPosition | None = None
    distance: str | None = None
    max_offset_mm: float | None = Field(default=None, ge=0.0, le=3.0)
    offset_x_mm: float | None = Field(default=None, ge=-3.0, le=3.0)
    offset_y_mm: float | None = Field(default=None, ge=-3.0, le=3.0)


class ReviewIssue(_StrictModel):
    """One reported problem with an element."""

    element_id: str
    issue_type: ReviewIssueType
    severity: int = Field(ge=1, le=10)
    action: ReviewAction | None = None


class ReviewResult(_StrictModel):
    """A complete, schema-valid review response."""

    page_score: float = Field(ge=0.0, le=10.0)
    issues: list[ReviewIssue] = Field(default_factory=list)


def _validate_action(action: ReviewAction, label_ids: set[str], element_id: str) -> None:
    if action.type == ReviewActionType.SELECT_CANDIDATE:
        if action.candidate is None:
            raise ReviewValidationError(f"{element_id}: select_candidate requires a candidate")
        if action.candidate not in {position.value for position in CompassPosition}:
            raise ReviewValidationError(f"{element_id}: invalid candidate {action.candidate!r}")
    if action.type == ReviewActionType.MOVE_LABEL:
        if action.preferred_direction is None:
            raise ReviewValidationError(f"{element_id}: move_label requires preferred_direction")
        if action.distance is not None and action.distance not in {"near", "medium", "far"}:
            raise ReviewValidationError(f"{element_id}: invalid distance")
    if action.type == ReviewActionType.FINE_ADJUST_LABEL:
        if action.offset_x_mm is None or action.offset_y_mm is None:
            raise ReviewValidationError(f"{element_id}: fine_adjust_label requires both offsets")
        if action.offset_x_mm == 0.0 and action.offset_y_mm == 0.0:
            raise ReviewValidationError(f"{element_id}: fine_adjust_label requires an offset")
    if action.type == ReviewActionType.SELECT_DISPLAY_NAME_VARIANT:
        if action.display_name_variant is None:
            raise ReviewValidationError(
                f"{element_id}: select_display_name_variant requires a variant"
            )
    if (
        action.type
        in (
            ReviewActionType.SHOW_OPTIONAL_LABEL,
            ReviewActionType.HIDE_OPTIONAL_LABEL,
        )
        and element_id not in label_ids
    ):
        raise ReviewValidationError(
            f"{element_id}: label visibility actions require a label element"
        )


def validate_review(payload: dict[str, Any], *, known_element_ids: set[str]) -> ReviewResult:
    """Validate a raw review response against known elements.

    Raises :class:`ReviewValidationError` if the response is malformed or
    references an unknown element.
    """
    try:
        result = ReviewResult.model_validate(payload)
    except ValidationError as exc:
        raise ReviewValidationError(str(exc)) from exc

    label_ids = {element_id for element_id in known_element_ids if element_id.startswith("label:")}
    for issue in result.issues:
        if issue.element_id not in known_element_ids:
            raise ReviewValidationError(f"unknown element reference {issue.element_id!r}")
        if issue.action is not None:
            _validate_action(issue.action, label_ids, issue.element_id)
    return result
