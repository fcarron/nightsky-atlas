"""Tests for layout models."""

from __future__ import annotations

from nightsky_atlas.chart.page import PagePoint, PageRect
from nightsky_atlas.layout.models import CompassPosition, Label, LabelCandidate


def make_candidate(candidate_id: str, position: CompassPosition) -> LabelCandidate:
    return LabelCandidate(
        id=candidate_id,
        position=position,
        anchor=PagePoint(10.0, 20.0),
        bounds=PageRect(10.0, 20.0, 5.0, 2.0),
    )


def make_label() -> Label:
    candidates = (
        make_candidate("label:dso:M87:N", CompassPosition.N),
        make_candidate("label:dso:M87:SW", CompassPosition.SW),
    )
    return Label(
        id="label:dso:M87",
        target_id="NGC4486",
        text="M87",
        priority=100,
        mandatory=True,
        candidates=candidates,
    )


def test_selection_defaults_to_none() -> None:
    label = make_label()
    assert label.selected_candidate() is None


def test_with_selection_returns_copy() -> None:
    label = make_label()
    selected = label.with_selection("label:dso:M87:SW")
    assert selected.selected_candidate() is not None
    assert selected.selected_candidate().position == CompassPosition.SW
    assert label.selected_candidate_id is None


def test_candidate_lookup_unknown_returns_none() -> None:
    assert make_label().candidate("missing") is None


def test_label_serialization_round_trip() -> None:
    label = make_label().with_selection("label:dso:M87:N")
    assert Label.from_dict(label.to_dict()) == label


def test_label_typography_round_trip() -> None:
    label = Label(
        id="label:dso:M87",
        target_id="NGC4486",
        text="M87",
        priority=100,
        mandatory=True,
        candidates=(),
        font_size_pt=7.475,
        font_weight="bold",
    )
    restored = Label.from_dict(label.to_dict())
    assert restored == label
    assert restored.font_size_pt == 7.475
    assert restored.font_weight == "bold"


def test_label_typography_defaults_are_style_agnostic() -> None:
    label = make_label()
    assert label.font_size_pt is None
    assert label.font_weight == "normal"


def test_candidate_serialization_round_trip() -> None:
    candidate = make_candidate("label:dso:M87:N", CompassPosition.N)
    assert LabelCandidate.from_dict(candidate.to_dict()) == candidate
