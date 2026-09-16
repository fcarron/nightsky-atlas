"""Deterministic replay of previously recorded AI reviews.

A recorded review lets an accepted AI optimization be reproduced offline
(``AGENTS.md`` sections 18.1 and 26).
"""

from __future__ import annotations

import json
from pathlib import Path

from nightsky_atlas.review.models import ReviewRequest
from nightsky_atlas.review.schema import ReviewResult

__all__ = ["RecordedReviewer", "ReviewReplayError", "write_recorded_reviews"]


class ReviewReplayError(ValueError):
    """Raised when a replay has no recorded result to return."""


class RecordedReviewer:
    """Return previously recorded review results in order."""

    def __init__(self, results: list[ReviewResult]) -> None:
        self._results = list(results)
        self.requests: list[ReviewRequest] = []

    def review(self, request: ReviewRequest) -> ReviewResult:
        self.requests.append(request)
        if not self._results:
            raise ReviewReplayError("no more recorded review results to replay")
        return self._results.pop(0)

    @classmethod
    def from_file(cls, path: str | Path) -> RecordedReviewer:
        """Load recorded results from JSON written by :func:`write_recorded_reviews`."""
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls([ReviewResult.model_validate(item) for item in payload])


def write_recorded_reviews(path: str | Path, results: list[ReviewResult]) -> Path:
    """Write review results as JSON suitable for :class:`RecordedReviewer`."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps([result.model_dump() for result in results], indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return target