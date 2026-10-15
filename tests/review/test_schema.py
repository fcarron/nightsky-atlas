"""Tests for review response schema validation."""

from __future__ import annotations

import pytest

from nightsky_atlas.review.schema import ReviewValidationError, validate_review

KNOWN = {"label:dso:NGC4486", "dso:NGC4486", "star:TYC 1-8-1"}


def valid_payload() -> dict:
    return {
        "page_score": 8.5,
        "issues": [
            {
                "element_id": "label:dso:NGC4486",
                "issue_type": "ambiguous_association",
                "severity": 7,
                "action": {"type": "select_candidate", "candidate": "SW"},
            }
        ],
    }


def test_valid_payload() -> None:
    result = validate_review(valid_payload(), known_element_ids=KNOWN)
    assert result.page_score == pytest.approx(8.5)
    assert len(result.issues) == 1


def test_empty_issues_is_valid() -> None:
    result = validate_review({"page_score": 9.0, "issues": []}, known_element_ids=KNOWN)
    assert result.issues == []


@pytest.mark.parametrize(
    "changes",
    [
        pytest.param({"element_id": "label:dso:UNKNOWN"}, id="unknown-element"),
        pytest.param({"issue_type": "looks_weird"}, id="unknown-issue-type"),
        pytest.param({"action": {"type": "delete_object", "candidate": "SW"}}, id="unknown-action"),
        pytest.param({"severity": 11}, id="severity-out-of-range"),
        pytest.param({"action": {"type": "select_candidate"}}, id="missing-candidate"),
        pytest.param(
            {"action": {"type": "select_candidate", "candidate": "UP"}}, id="invalid-candidate"
        ),
        pytest.param(
            {"severity": 5, "action": {"type": "select_display_name_variant"}},
            id="missing-display-variant",
        ),
        pytest.param(
            {"action": {"type": "fine_adjust_label", "offset_x_mm": 0.0, "offset_y_mm": 0.0}},
            id="zero-fine-adjustment",
        ),
        pytest.param(
            {
                "element_id": "dso:NGC4486",
                "issue_type": "unreadable_label",
                "severity": 5,
                "action": {"type": "hide_optional_label"},
            },
            id="visibility-on-non-label",
        ),
    ],
)
def test_invalid_review_issue_rejected(changes: dict) -> None:
    payload = valid_payload()
    payload["issues"][0].update(changes)
    with pytest.raises(ReviewValidationError):
        validate_review(payload, known_element_ids=KNOWN)


def test_extra_key_rejected() -> None:
    payload = valid_payload()
    payload["notes"] = "free text"
    with pytest.raises(ReviewValidationError):
        validate_review(payload, known_element_ids=KNOWN)
