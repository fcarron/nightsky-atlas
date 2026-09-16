"""Tests for the reviewer interface and mock reviewer."""

from __future__ import annotations

from nightsky_atlas.ai.base import ChartReviewer, MockReviewer
from nightsky_atlas.review.models import ReviewRequest
from nightsky_atlas.review.schema import ReviewResult


def make_request() -> ReviewRequest:
    return ReviewRequest(
        page_id="standard:test",
        prompt_version="1",
        schema_version="1",
        images=(),
        permitted_actions=("select_candidate",),
    )


def test_mock_reviewer_returns_queued_results() -> None:
    first = ReviewResult(page_score=5.0, issues=[])
    second = ReviewResult(page_score=9.0, issues=[])
    reviewer = MockReviewer(results=[first, second])
    assert reviewer.review(make_request()) is first
    assert reviewer.review(make_request()) is second


def test_mock_reviewer_records_requests() -> None:
    reviewer = MockReviewer()
    reviewer.review(make_request())
    assert len(reviewer.requests) == 1


def test_mock_reviewer_default_is_perfect() -> None:
    result = MockReviewer().review(make_request())
    assert result.page_score == 10.0
    assert result.issues == []


def test_single_result_constructor() -> None:
    result = ReviewResult(page_score=7.0, issues=[])
    reviewer = MockReviewer(result)
    assert reviewer.review(make_request()) is result
    assert reviewer.review(make_request()).page_score == 10.0


def test_satisfies_protocol() -> None:
    assert isinstance(MockReviewer(), ChartReviewer)