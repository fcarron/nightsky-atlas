"""Layout models, candidate generation and validation."""

from __future__ import annotations

from nightsky_atlas.layout.candidates import compass_candidates
from nightsky_atlas.layout.collision import (
    IssueType,
    LayoutIssue,
    find_hard_violations,
    placed_candidates,
)
from nightsky_atlas.layout.labels import build_dso_labels
from nightsky_atlas.layout.models import CompassPosition, Label, LabelCandidate
from nightsky_atlas.layout.optimizer import OptimizationResult, optimize_labels
from nightsky_atlas.layout.scoring import CostBreakdown, CostWeights
from nightsky_atlas.layout.validation import ValidationResult, validate_layout

__all__ = [
    "CompassPosition",
    "CostBreakdown",
    "CostWeights",
    "IssueType",
    "Label",
    "LabelCandidate",
    "LayoutIssue",
    "OptimizationResult",
    "ValidationResult",
    "build_dso_labels",
    "compass_candidates",
    "find_hard_violations",
    "optimize_labels",
    "placed_candidates",
    "validate_layout",
]