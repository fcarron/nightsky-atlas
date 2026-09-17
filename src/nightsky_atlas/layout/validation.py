"""Layout validation.

A page cannot be considered publishable because it rendered successfully: this
module turns hard collision checks into a verdict (``AGENTS.md`` section 23).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from nightsky_atlas.atlas.config import StyleConfig
from nightsky_atlas.chart.page import PageRect, PageTransform
from nightsky_atlas.layout.collision import IssueType, LayoutIssue, find_hard_violations
from nightsky_atlas.layout.models import Label
from nightsky_atlas.scene.models import ChartScene

__all__ = ["ValidationResult", "validate_layout"]


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """The hard-violation verdict for a layout."""

    issues: tuple[LayoutIssue, ...]

    @property
    def is_valid(self) -> bool:
        """Whether the layout has no unresolved hard violations."""
        return not self.issues

    def count_by_type(self) -> dict[str, int]:
        """Return issue counts keyed by issue type value."""
        counts: Counter[str] = Counter(issue.issue_type.value for issue in self.issues)
        return dict(sorted(counts.items()))


def validate_layout(
    labels: tuple[Label, ...],
    scene: ChartScene,
    transform: PageTransform,
    style: StyleConfig,
    *,
    furniture: Iterable[PageRect] = (),
) -> ValidationResult:
    """Validate a label layout against hard constraints."""
    issues = find_hard_violations(
        labels, scene, transform, style, furniture=furniture
    )
    return ValidationResult(issues=issues)


def issue_types(result: ValidationResult) -> set[IssueType]:
    """Return the set of issue types present in a result."""
    return {issue.issue_type for issue in result.issues}