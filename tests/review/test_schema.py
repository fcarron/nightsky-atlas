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


def test_unknown_element_rejected() -> None:
    payload = valid_payload()
    payload["issues"][0]["element_id"] = "label:dso:UNKNOWN"
    with pytest.raises(ReviewValidationError):
        validate_review(payload, known_element_ids=KNOWN)


def test_unknown_issue_type_rejected() -> None:
    payload = valid_payload()
    payload["issues"][0]["issue_type"] = "looks_weird"
    with pytest.raises(ReviewValidationError):
        validate_review(payload, known_element_ids=KNOWN)


def test_unknown_action_rejected() -> None:
    payload = valid_payload()
    payload["issues"][0]["action"]["type"] = "delete_object"
    with pytest.raises(ReviewValidationError):
        validate_review(payload, known_element_ids=KNOWN)


def test_severity_out_of_range_rejected() -> None:
    payload = valid_payload()
    payload["issues"][0]["severity"] = 11
    with pytest.raises(ReviewValidationError):
        validate_review(payload, known_element_ids=KNOWN)


def test_extra_key_rejected() -> None:
    payload = valid_payload()
    payload["notes"] = "free text"
    with pytest.raises(ReviewValidationError):
        validate_review(payload, known_element_ids=KNOWN)


def test_select_candidate_requires_candidate() -> None:
    payload = valid_payload()
    payload["issues"][0]["action"] = {"type": "select_candidate"}
    with pytest.raises(ReviewValidationError):
        validate_review(payload, known_element_ids=KNOWN)


def test_invalid_candidate_rejected() -> None:
    payload = valid_payload()
    payload["issues"][0]["action"]["candidate"] = "UP"
    with pytest.raises(ReviewValidationError):
        validate_review(payload, known_element_ids=KNOWN)


def test_display_name_variant_requires_value() -> None:
    payload = {
        "page_score": 8.0,
        "issues": [
            {
                "element_id": "label:dso:NGC4486",
                "issue_type": "ambiguous_association",
                "severity": 5,
                "action": {"type": "select_display_name_variant"},
            }
        ],
    }
    with pytest.raises(ReviewValidationError):
        validate_review(payload, known_element_ids=KNOWN)


def test_fine_adjust_requires_a_nonzero_bounded_intent() -> None:
    payload = valid_payload()
    payload["issues"][0]["action"] = {
        "type": "fine_adjust_label",
        "offset_x_mm": 0.0,
        "offset_y_mm": 0.0,
    }
    with pytest.raises(ReviewValidationError):
        validate_review(payload, known_element_ids=KNOWN)


def test_visibility_action_requires_label_element() -> None:
    payload = {
        "page_score": 8.0,
        "issues": [
            {
                "element_id": "dso:NGC4486",
                "issue_type": "unreadable_label",
                "severity": 5,
                "action": {"type": "hide_optional_label"},
            }
        ],
    }
    with pytest.raises(ReviewValidationError):
        validate_review(payload, known_element_ids=KNOWN)
