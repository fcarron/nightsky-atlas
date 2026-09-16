"""Reviewer interface and a deterministic mock reviewer.

All AI optimization logic must be testable without a network (``AGENTS.md``
section 18.1).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from nightsky_atlas.review.models import ReviewRequest
from nightsky_atlas.review.schema import ReviewResult

__all__ = ["ChartReviewer", "MockReviewer"]


@runtime_checkable
class ChartReviewer(Protocol):
    """Provider-independent chart reviewer interface."""

    def review(self, request: ReviewRequest) -> ReviewResult:
        """Review a chart page and return a validated result."""
        ...


class MockReviewer:
    """A scripted reviewer for tests and offline development.

    Returns queued results in order; once exhausted it returns a perfect score
    with no issues.  Every request is recorded for assertions.
    """

    def __init__(
        self,
        result: ReviewResult | None = None,
        *,
        results: list[ReviewResult] | None = None,
    ) -> None:
        if results is not None:
            self._results = list(results)
        else:
            self._results = [result] if result is not None else []
        self.requests: list[ReviewRequest] = []

    def review(self, request: ReviewRequest) -> ReviewResult:
        self.requests.append(request)
        if self._results:
            return self._results.pop(0)
        return ReviewResult(page_score=10.0, issues=[])