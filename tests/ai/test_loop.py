"""Tests for the bounded AI optimization loop."""

from __future__ import annotations

from pathlib import Path

from nightsky_atlas.ai.base import MockReviewer
from nightsky_atlas.ai.loop import optimize_with_ai, write_history
from nightsky_atlas.ai.openrouter import ReviewUsage
from nightsky_atlas.ai.recorded import RecordedReviewer
from nightsky_atlas.atlas.config import load_style_config
from nightsky_atlas.catalog.models import Provenance, Star
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.chart.page import PagePoint, PageRect, PageTransform
from nightsky_atlas.layout.models import CompassPosition, Label, LabelCandidate
from nightsky_atlas.layout.optimizer import layout_hash
from nightsky_atlas.review.schema import ReviewResult
from nightsky_atlas.scene.builder import build_scene

REPO_ROOT = Path(__file__).resolve().parents[2]
STYLE = load_style_config(REPO_ROOT / "styles" / "standard.yaml")

CHART = ChartDefinition(
    id="test", center_ra_deg=187.5, center_dec_deg=12.0, width_deg=20.0, height_deg=14.0
)
PAGE = PageGeometry(width_mm=297.0, height_mm=210.0, margin_mm=12.0)
TRANSFORM = PageTransform(chart=CHART, page=PAGE)


def _target_star(star_id: str) -> Star:
    return Star(
        id=star_id,
        ra_deg=CHART.center_ra_deg,
        dec_deg=CHART.center_dec_deg,
        magnitude=3.0,
        provenance=Provenance(catalogue="TEST", source_id=star_id),
    )


SCENE = build_scene(CHART, [_target_star("A"), _target_star("B")], [])


def make_candidate(
    label_id: str, position: CompassPosition, left: float, top: float
) -> LabelCandidate:
    return LabelCandidate(
        id=f"{label_id}:{position.value}",
        position=position,
        anchor=PagePoint(left, top),
        bounds=PageRect(left, top, 8.0, 2.5),
    )


def make_labels() -> tuple[Label, Label]:
    first = Label(
        id="label:a",
        target_id="A",
        text="A",
        priority=50,
        mandatory=True,
        candidates=(
            make_candidate("label:a", CompassPosition.N, 100.0, 100.0),
            make_candidate("label:a", CompassPosition.S, 100.0, 110.0),
        ),
    )
    second = Label(
        id="label:b",
        target_id="B",
        text="B",
        priority=50,
        mandatory=True,
        candidates=(make_candidate("label:b", CompassPosition.N, 102.0, 101.0),),
    )
    return first, second


def fix_a_result() -> ReviewResult:
    return ReviewResult(
        page_score=6.0,
        issues=[
            {
                "element_id": "label:a",
                "issue_type": "overlapping_labels",
                "severity": 7,
                "action": {"type": "select_candidate", "candidate": "S"},
            }
        ],
    )


def test_loop_improves_and_stops_on_no_significant_issues() -> None:
    labels = make_labels()
    reviewer = MockReviewer(results=[fix_a_result()])
    result = optimize_with_ai(labels, SCENE, TRANSFORM, STYLE, reviewer, max_iterations=4)
    assert result.stopped_reason == "no_significant_issues"
    assert len(result.iterations) == 2
    assert result.iterations[0].cost_after < result.iterations[0].cost_before
    assert result.iterations[0].applied == ("label:a",)


def test_replay_reproduces_layout() -> None:
    labels = make_labels()
    recorded = [fix_a_result(), ReviewResult(page_score=10.0, issues=[])]
    original = optimize_with_ai(
        labels, SCENE, TRANSFORM, STYLE, MockReviewer(results=list(recorded))
    )
    replay = optimize_with_ai(labels, SCENE, TRANSFORM, STYLE, RecordedReviewer(list(recorded)))
    assert layout_hash(original.labels) == layout_hash(replay.labels)
    assert original.stopped_reason == replay.stopped_reason


def test_no_accepted_changes_stops() -> None:
    unsupported = ReviewResult(
        page_score=4.0,
        issues=[
            {
                "element_id": "label:a",
                "issue_type": "other",
                "severity": 8,
                "action": {"type": "use_leader_line"},
            }
        ],
    )
    result = optimize_with_ai(
        make_labels(), SCENE, TRANSFORM, STYLE, MockReviewer(results=[unsupported])
    )
    assert result.stopped_reason == "no_accepted_changes"
    assert result.iterations[0].applied == ()


def test_cost_budget_stops() -> None:
    reviewer = MockReviewer(results=[fix_a_result()])
    reviewer.last_usage = ReviewUsage(model="m", cost_usd=0.10)
    result = optimize_with_ai(
        make_labels(),
        SCENE,
        TRANSFORM,
        STYLE,
        reviewer,
        max_iterations=4,
        max_cost_usd=0.05,
    )
    assert result.stopped_reason == "cost_budget_reached"
    assert result.total_cost_usd == 0.10


def test_max_iterations_is_bounded() -> None:
    reviewer = MockReviewer()
    result = optimize_with_ai(make_labels(), SCENE, TRANSFORM, STYLE, reviewer, max_iterations=1)
    assert len(result.iterations) <= 1


def test_history_is_written(tmp_path: Path) -> None:
    result = optimize_with_ai(
        make_labels(), SCENE, TRANSFORM, STYLE, MockReviewer(results=[fix_a_result()])
    )
    path = tmp_path / "history.json"
    write_history(path, result)
    text = path.read_text(encoding="utf-8")
    assert "stopped_reason" in text
    assert "layout_hash_before" in text


def test_review_image_is_rerendered_for_each_iteration(tmp_path: Path) -> None:
    reviewer = MockReviewer(results=[fix_a_result(), ReviewResult(page_score=10.0, issues=[])])
    result = optimize_with_ai(
        make_labels(),
        SCENE,
        TRANSFORM,
        STYLE,
        reviewer,
        images=(str(tmp_path / "review.png"),),
    )

    assert len(result.iterations) == 2
    first, second = reviewer.requests
    assert first.images != second.images
    assert Path(first.images[0]).is_file()
    assert Path(second.images[0]).is_file()
    assert Path(first.images[0]).read_bytes() != Path(second.images[0]).read_bytes()
