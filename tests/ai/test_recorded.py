"""Tests for recorded review replay."""

from __future__ import annotations

from pathlib import Path

import pytest

from nightsky_atlas.ai.recorded import (
    RecordedReviewer,
    ReviewReplayError,
    write_recorded_reviews,
)
from nightsky_atlas.review.models import ReviewRequest
from nightsky_atlas.review.schema import ReviewResult


def make_request() -> ReviewRequest:
    return ReviewRequest(
        page_id="p",
        prompt_version="1",
        schema_version="1",
        images=(),
        permitted_actions=("select_candidate",),
    )


def test_replays_results_in_order() -> None:
    first = ReviewResult(page_score=5.0, issues=[])
    second = ReviewResult(page_score=8.0, issues=[])
    reviewer = RecordedReviewer([first, second])
    assert reviewer.review(make_request()) is first
    assert reviewer.review(make_request()) is second


def test_exhaustion_raises() -> None:
    reviewer = RecordedReviewer([])
    with pytest.raises(ReviewReplayError):
        reviewer.review(make_request())


def test_file_round_trip(tmp_path: Path) -> None:
    results = [ReviewResult(page_score=7.0, issues=[])]
    path = tmp_path / "recorded.json"
    write_recorded_reviews(path, results)
    reviewer = RecordedReviewer.from_file(path)
    assert reviewer.review(make_request()).page_score == 7.0