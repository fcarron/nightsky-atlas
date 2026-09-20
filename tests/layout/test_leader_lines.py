"""Deterministic leader lines for distant deep-sky labels."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from nightsky_atlas.ai.actions import apply_review_actions
from nightsky_atlas.ai.recorded import RecordedReviewer, write_recorded_reviews
from nightsky_atlas.atlas.config import load_style_config
from nightsky_atlas.catalog.models import DeepSkyObject, DsoType, Provenance, Star
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.chart.page import PagePoint, PageRect, PageTransform
from nightsky_atlas.layout.geometry import segments_intersect
from nightsky_atlas.layout.leader_lines import leader_line_for, resolve_leader_lines
from nightsky_atlas.layout.models import CompassPosition, Label, LabelCandidate
from nightsky_atlas.layout.optimizer import layout_hash, optimize_labels
from nightsky_atlas.layout.validation import validate_layout
from nightsky_atlas.render.cairo import render_chart
from nightsky_atlas.review.models import ReviewRequest
from nightsky_atlas.review.schema import ReviewResult
from nightsky_atlas.scene.builder import build_scene

ROOT = Path(__file__).resolve().parents[2]
STYLE = load_style_config(ROOT / "styles" / "standard.yaml")
CHART = ChartDefinition(
    id="test", center_ra_deg=187.5, center_dec_deg=12.0, width_deg=20.0, height_deg=14.0
)
TRANSFORM = PageTransform(CHART, PageGeometry(297.0, 210.0, 12.0))
DSO = DeepSkyObject(
    id="NGC4486",
    ra_deg=187.5,
    dec_deg=12.0,
    object_type=DsoType.GALAXY,
    provenance=Provenance(catalogue="TEST", source_id="NGC4486"),
    magnitude=8.0,
)
SCENE = build_scene(CHART, [], [DSO])
STAR = Star(
    id="HIP 1",
    ra_deg=187.5,
    dec_deg=12.0,
    magnitude=2.0,
    provenance=Provenance(catalogue="TEST", source_id="HIP 1"),
)
STAR_SCENE = build_scene(CHART, [STAR], [])


def test_segment_crossing_ignores_disjoint_collinear_segments() -> None:
    a = PagePoint(0.0, 0.0)
    b = PagePoint(1.0, 0.0)
    assert not segments_intersect(a, b, PagePoint(2.0, 0.0), PagePoint(3.0, 0.0))
    assert segments_intersect(a, b, PagePoint(0.5, -1.0), PagePoint(0.5, 1.0))


def make_label(*, ring: int = 2) -> Label:
    candidate = LabelCandidate(
        id="label:dso:NGC4486:E:2",
        position=CompassPosition.E,
        anchor=PagePoint(160.0, 104.0),
        bounds=PageRect(160.0, 104.0, 8.0, 2.5),
        ring=ring,
    )
    return Label(
        id="label:dso:NGC4486",
        target_id="NGC4486",
        text="M87",
        priority=100,
        mandatory=True,
        candidates=(candidate,),
        selected_candidate_id=candidate.id,
    )


def test_leader_line_stops_at_symbol_and_before_text() -> None:
    label = make_label()
    line = leader_line_for(label, (label,), SCENE, TRANSFORM, STYLE)
    assert line is not None
    assert line.start.x_mm > TRANSFORM.center_page.x_mm
    assert line.end.x_mm == 159.6
    assert line.start.y_mm == line.end.y_mm
    assert line.end.x_mm < label.effective_candidate().bounds.left_mm


def test_optimizer_adds_line_only_to_distant_dso_label() -> None:
    far = optimize_labels((make_label(),), SCENE, TRANSFORM, STYLE).labels[0]
    assert far.leader_line
    assert resolve_leader_lines((far,), SCENE, TRANSFORM, STYLE)
    assert validate_layout((far,), SCENE, TRANSFORM, STYLE).is_valid
    near = optimize_labels((make_label(ring=0),), SCENE, TRANSFORM, STYLE).labels[0]
    assert not near.leader_line


def test_optimizer_never_adds_line_for_distant_proper_star_name() -> None:
    candidate = LabelCandidate(
        id="label:star:HIP 1:name:E:2",
        position=CompassPosition.E,
        anchor=PagePoint(160.0, 104.0),
        bounds=PageRect(160.0, 104.0, 8.0, 2.5),
        ring=2,
    )
    label = Label(
        id="label:star:HIP 1:name",
        target_id="HIP 1",
        text="Test name",
        priority=95,
        mandatory=True,
        candidates=(candidate,),
        selected_candidate_id=candidate.id,
    )
    optimized = optimize_labels((label,), STAR_SCENE, TRANSFORM, STYLE).labels[0]
    assert not optimized.leader_line
    assert not resolve_leader_lines((optimized,), STAR_SCENE, TRANSFORM, STYLE)


def test_near_clean_candidate_is_preferred_over_distant_callout() -> None:
    far = make_label()
    near = LabelCandidate(
        id="label:dso:NGC4486:E",
        position=CompassPosition.E,
        anchor=PagePoint(151.0, 104.0),
        bounds=PageRect(151.0, 104.0, 8.0, 2.5),
        ring=0,
    )
    label = replace(far, candidates=(near, *far.candidates), selected_candidate_id=None)
    result = optimize_labels((label,), SCENE, TRANSFORM, STYLE).labels[0]
    assert result.selected_candidate_id == near.id
    assert not result.leader_line


def test_crossing_another_label_rejects_leader_line() -> None:
    label = make_label()
    obstacle = replace(
        label,
        id="label:other",
        target_id="NGC4486",
        candidates=(
            LabelCandidate(
                id="label:other:N",
                position=CompassPosition.N,
                anchor=PagePoint(154.0, 104.0),
                bounds=PageRect(154.0, 104.0, 3.0, 2.5),
            ),
        ),
        selected_candidate_id="label:other:N",
    )
    assert leader_line_for(label, (label, obstacle), SCENE, TRANSFORM, STYLE) is None
    invalid = replace(label, leader_line=True)
    assert not validate_layout((invalid, obstacle), SCENE, TRANSFORM, STYLE).is_valid


def test_ai_enable_and_replay_state(tmp_path: Path) -> None:
    label = make_label(ring=1)
    review = ReviewResult.model_validate(
        {
            "page_score": 5.0,
            "issues": [
                {
                    "element_id": label.id,
                    "issue_type": "leader_line_needed",
                    "severity": 5,
                    "action": {"type": "enable_leader_line"},
                }
            ],
        }
    )
    recorded_path = write_recorded_reviews(tmp_path / "review.json", [review])
    request = ReviewRequest("test", "1", "1", (), ("enable_leader_line",))
    replayed = RecordedReviewer.from_file(recorded_path).review(request)
    first = apply_review_actions((label,), review, SCENE, TRANSFORM, STYLE)
    second = apply_review_actions((label,), replayed, SCENE, TRANSFORM, STYLE)
    assert first.applied == (label.id,)
    assert first.labels == second.labels
    assert first.labels[0].leader_line
    assert Label.from_dict(first.labels[0].to_dict()) == first.labels[0]
    assert layout_hash(first.labels) != layout_hash((label,))
    assert resolve_leader_lines(first.labels, SCENE, TRANSFORM, STYLE)
    render_chart(
        SCENE,
        TRANSFORM,
        STYLE,
        labels=first.labels,
        pdf_path=tmp_path / "chart.pdf",
        png_path=tmp_path / "preview.png",
    )
    assert (tmp_path / "chart.pdf").read_bytes().startswith(b"%PDF")
    assert (tmp_path / "preview.png").read_bytes().startswith(b"\x89PNG")

    remove = ReviewResult.model_validate(
        {
            "page_score": 5.0,
            "issues": [
                {
                    "element_id": label.id,
                    "issue_type": "leader_line_needed",
                    "severity": 5,
                    "action": {"type": "remove_leader_line"},
                }
            ],
        }
    )
    removed = apply_review_actions(first.labels, remove, SCENE, TRANSFORM, STYLE)
    assert removed.applied == (label.id,)
    assert not removed.labels[0].leader_line
