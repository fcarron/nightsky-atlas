"""Tests for the OpenRouter reviewer using a mock transport (no network)."""

from __future__ import annotations

import json

import httpx
import pytest

from nightsky_atlas.ai.openrouter import OpenRouterError, OpenRouterReviewer
from nightsky_atlas.review.models import ReviewElement, ReviewRequest


def make_request() -> ReviewRequest:
    return ReviewRequest(
        page_id="standard:test",
        prompt_version="1",
        schema_version="1",
        images=(),
        permitted_actions=("select_candidate",),
        elements=(ReviewElement(id="label:dso:NGC4486", kind="label", text="M87"),),
    )


def completion(content: str) -> dict:
    return {
        "model": "test/model",
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 7, "cost": 0.0004},
    }


def client_with(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_successful_review_captures_usage() -> None:
    body = completion(json.dumps({"page_score": 9.0, "issues": []}))
    reviewer = OpenRouterReviewer(
        model="test/model",
        api_key="k",
        client=client_with(lambda request: httpx.Response(200, json=body)),
    )
    result = reviewer.review(make_request())
    assert result.page_score == 9.0
    assert reviewer.last_usage is not None
    assert reviewer.last_usage.prompt_tokens == 11
    assert reviewer.last_usage.completion_tokens == 7
    assert reviewer.last_usage.cost_usd == pytest.approx(0.0004)


def test_retries_transient_then_succeeds() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(500, text="server error")
        return httpx.Response(200, json=completion(json.dumps({"page_score": 8.0, "issues": []})))

    reviewer = OpenRouterReviewer(
        model="m", api_key="k", client=client_with(handler), max_retries=1, retry_backoff_s=0.0
    )
    assert reviewer.review(make_request()).page_score == 8.0
    assert calls["count"] == 2


def test_client_error_is_not_retried() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(401, text="unauthorized")

    reviewer = OpenRouterReviewer(
        model="m", api_key="k", client=client_with(handler), max_retries=3, retry_backoff_s=0.0
    )
    with pytest.raises(OpenRouterError):
        reviewer.review(make_request())
    assert calls["count"] == 1


def test_non_json_content_raises() -> None:
    body = completion("this is prose, not JSON")
    reviewer = OpenRouterReviewer(
        model="m", api_key="k", client=client_with(lambda request: httpx.Response(200, json=body))
    )
    with pytest.raises(OpenRouterError):
        reviewer.review(make_request())


def test_unknown_element_reference_is_dropped() -> None:
    payload = {
        "page_score": 8.0,
        "issues": [
            {
                "element_id": "label:dso:UNKNOWN",
                "issue_type": "other",
                "severity": 5,
            }
        ],
    }
    body = completion(json.dumps(payload))
    reviewer = OpenRouterReviewer(
        model="m", api_key="k", client=client_with(lambda request: httpx.Response(200, json=body))
    )
    result = reviewer.review(make_request())
    assert result.issues == []
    assert reviewer.last_dropped_elements == ("label:dso:UNKNOWN",)


def test_missing_api_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(OpenRouterError):
        OpenRouterReviewer(model="m")


def test_prompt_lists_element_candidates() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=completion(json.dumps({"page_score": 9.0, "issues": []})))

    request = ReviewRequest(
        page_id="standard:test",
        prompt_version="1",
        schema_version="1",
        images=(),
        permitted_actions=("select_candidate",),
        elements=(
            ReviewElement(
                id="label:dso:NGC4486",
                kind="label",
                text="M87",
                candidates=("N", "S"),
            ),
        ),
    )
    reviewer = OpenRouterReviewer(
        model="m", api_key="k", client=client_with(handler)
    )
    reviewer.review(request)
    prompt = captured["body"]["messages"][1]["content"][0]["text"]
    assert "candidates=[N,S]" in prompt