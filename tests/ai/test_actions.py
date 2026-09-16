"""Tests for AI action application."""

from __future__ import annotations

from pathlib import Path

from nightsky_atlas.ai.actions import apply_review_actions
from nightsky_atlas.atlas.config import load_style_config
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.chart.page import PagePoint, PageRect, PageTransform
from nightsky_atlas.layout.models import CompassPosition, Label, LabelCandidate
from nightsky_atlas.review.schema import ReviewResult
from nightsky_atlas.scene.builder import build_scene

REPO_ROOT = Path(__file__).resolve().parents[2]
STYLE = load_style_config(REPO_ROOT / "styles" / "standard.yaml")

CHART = ChartDefinition(
    id="test", center_ra_deg=187.5, center_dec_deg=12.0, width_deg=20.0, height_deg=14.0
)
PAGE = PageGeometry(width_mm=297.0, height_mm=210.0, margin_mm=12.0)
TRANSFORM = PageTransform(chart=CHART, page=PAGE)
SCENE = build_scene(CHART, [], [])


def make_candidate(
    label_id: str, position: CompassPosition, left: float, top: float
) -> LabelCandidate:
    return LabelCandidate(
        id=f"{label_id}:{position.value}",
        position=position,
        anchor=PagePoint(left, top),
        bounds=PageRect(left, top, 8.0, 2.5),
    )


def make_label(*, mandatory: bool = False) -> Label:
    return Label(
        id="label:x",
        target_id="X",
        text="X",
        priority=50,
        mandatory=mandatory,
        candidates=(
            make_candidate("label:x", CompassPosition.N, 100.0, 100.0),
            make_candidate("label:x", CompassPosition.S, 100.0, 110.0),
        ),
    )


def make_result(element_id: str, action: dict) -> ReviewResult:
    return ReviewResult(
        page_score=5.0,
        issues=[
            {
                "element_id": element_id,
                "issue_type": "ambiguous_association",
                "severity": 5,
                "action": action,
            }
        ],
    )


def test_select_candidate_applied() -> None:
    label = make_label()
    outcome = apply_review_actions(
        (label,),
        make_result("label:x", {"type": "select_candidate", "candidate": "S"}),
        SCENE,
        TRANSFORM,
        STYLE,
    )
    assert outcome.applied == ("label:x",)
    assert outcome.labels[0].selected_candidate_id == "label:x:S"


def test_low_severity_actions_ignored() -> None:
    result = ReviewResult(
        page_score=5.0,
        issues=[
            {
                "element_id": "label:x",
                "issue_type": "ambiguous_association",
                "severity": 3,
                "action": {"type": "select_candidate", "candidate": "S"},
            }
        ],
    )
    outcome = apply_review_actions(
        (make_label(),), result, SCENE, TRANSFORM, STYLE, min_severity=6
    )
    assert outcome.applied == ()
    assert outcome.labels[0].selected_candidate_id is None


def test_unknown_candidate_rejected() -> None:
    outcome = apply_review_actions(
        (make_label(),),
        make_result("label:x", {"type": "select_candidate", "candidate": "SW"}),
        SCENE,
        TRANSFORM,
        STYLE,
    )
    assert outcome.applied == ()
    assert outcome.rejected[0][0] == "label:x"


def test_hide_optional_label_applied() -> None:
    outcome = apply_review_actions(
        (make_label(mandatory=False),),
        make_result("label:x", {"type": "hide_optional_label"}),
        SCENE,
        TRANSFORM,
        STYLE,
    )
    assert outcome.labels[0].hidden is True


def test_hide_mandatory_label_rejected() -> None:
    outcome = apply_review_actions(
        (make_label(mandatory=True),),
        make_result("label:x", {"type": "hide_optional_label"}),
        SCENE,
        TRANSFORM,
        STYLE,
    )
    assert outcome.applied == ()
    assert outcome.labels[0].hidden is False


def test_show_optional_label_applied() -> None:
    hidden = make_label().with_placement(None, hidden=True)
    outcome = apply_review_actions(
        (hidden,),
        make_result("label:x", {"type": "show_optional_label"}),
        SCENE,
        TRANSFORM,
        STYLE,
    )
    assert outcome.labels[0].hidden is False
    assert outcome.labels[0].selected_candidate_id == "label:x:N"


def test_unsupported_action_rejected() -> None:
    outcome = apply_review_actions(
        (make_label(),),
        make_result("label:x", {"type": "use_leader_line"}),
        SCENE,
        TRANSFORM,
        STYLE,
    )
    assert outcome.applied == ()
    assert "not applicable" in outcome.rejected[0][1]


def test_unknown_element_rejected() -> None:
    outcome = apply_review_actions(
        (make_label(),),
        make_result("label:zzz", {"type": "show_optional_label"}),
        SCENE,
        TRANSFORM,
        STYLE,
    )
    assert outcome.rejected[0][1] == "referenced element is not a label"