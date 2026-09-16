"""Tests for the deterministic label optimizer."""

from __future__ import annotations

from pathlib import Path

from nightsky_atlas.atlas.config import load_style_config
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.chart.page import PagePoint, PageRect, PageTransform
from nightsky_atlas.layout.models import CompassPosition, Label, LabelCandidate
from nightsky_atlas.layout.optimizer import optimize_labels
from nightsky_atlas.scene.builder import build_scene

REPO_ROOT = Path(__file__).resolve().parents[2]
STYLE = load_style_config(REPO_ROOT / "styles" / "standard.yaml")

CHART = ChartDefinition(
    id="test", center_ra_deg=187.5, center_dec_deg=12.0, width_deg=20.0, height_deg=14.0
)
PAGE = PageGeometry(width_mm=297.0, height_mm=210.0, margin_mm=12.0)
TRANSFORM = PageTransform(chart=CHART, page=PAGE)
EMPTY_SCENE = build_scene(CHART, [], [])


def make_candidate(
    label_id: str, position: CompassPosition, left: float, top: float
) -> LabelCandidate:
    return LabelCandidate(
        id=f"{label_id}:{position.value}",
        position=position,
        anchor=PagePoint(left, top),
        bounds=PageRect(left, top, 8.0, 2.5),
    )


def make_label(
    label_id: str,
    candidates: tuple[LabelCandidate, ...],
    *,
    priority: int = 50,
    mandatory: bool = True,
) -> Label:
    return Label(
        id=label_id,
        target_id="X",
        text="X",
        priority=priority,
        mandatory=mandatory,
        candidates=candidates,
    )


def test_greedy_avoids_overlap_between_mandatory_labels() -> None:
    first = make_label(
        "label:a",
        (
            make_candidate("label:a", CompassPosition.N, 100.0, 100.0),
            make_candidate("label:a", CompassPosition.S, 100.0, 110.0),
        ),
    )
    second = make_label(
        "label:b",
        (
            make_candidate("label:b", CompassPosition.N, 102.0, 101.0),
            make_candidate("label:b", CompassPosition.SE, 120.0, 120.0),
        ),
    )
    result = optimize_labels((first, second), EMPTY_SCENE, TRANSFORM, STYLE)
    by_id = {label.id: label for label in result.labels}
    assert by_id["label:a"].selected_candidate_id is not None
    assert by_id["label:b"].selected_candidate_id is not None
    bounds_a = by_id["label:a"].selected_candidate().bounds
    bounds_b = by_id["label:b"].selected_candidate().bounds
    assert not (bounds_a.left_mm < bounds_b.right_mm and bounds_b.left_mm < bounds_a.right_mm)


def test_optional_label_outside_page_is_hidden() -> None:
    label = make_label(
        "label:out",
        (make_candidate("label:out", CompassPosition.N, -50.0, -50.0),),
        mandatory=False,
    )
    result = optimize_labels((label,), EMPTY_SCENE, TRANSFORM, STYLE)
    assert result.labels[0].hidden is True
    assert result.hidden_count == 1


def test_mandatory_label_outside_page_is_placed() -> None:
    label = make_label(
        "label:out",
        (make_candidate("label:out", CompassPosition.N, -50.0, -50.0),),
        mandatory=True,
    )
    result = optimize_labels((label,), EMPTY_SCENE, TRANSFORM, STYLE)
    assert result.labels[0].hidden is False
    assert result.placed_count == 1


def test_optimizer_resolves_overlap_and_lowers_cost() -> None:
    first = make_label(
        "label:a",
        (
            make_candidate("label:a", CompassPosition.N, 100.0, 100.0),
            make_candidate("label:a", CompassPosition.E, 200.0, 100.0),
        ),
    )
    second = make_label(
        "label:b",
        (
            make_candidate("label:b", CompassPosition.N, 100.0, 100.0),
            make_candidate("label:b", CompassPosition.W, 200.0, 140.0),
        ),
    )
    result = optimize_labels((first, second), EMPTY_SCENE, TRANSFORM, STYLE)
    assert result.cost_after < result.cost_before
    by_id = {label.id: label for label in result.labels}
    bounds_a = by_id["label:a"].selected_candidate().bounds
    bounds_b = by_id["label:b"].selected_candidate().bounds
    assert not (bounds_a.left_mm < bounds_b.right_mm and bounds_b.left_mm < bounds_a.right_mm)


def test_optimization_is_deterministic() -> None:
    labels = tuple(
        make_label(
            f"label:{index}",
            (make_candidate(f"label:{index}", CompassPosition.N, 100.0 + index, 100.0),),
        )
        for index in range(3)
    )
    first = optimize_labels(labels, EMPTY_SCENE, TRANSFORM, STYLE)
    second = optimize_labels(labels, EMPTY_SCENE, TRANSFORM, STYLE)
    assert [label.selected_candidate_id for label in first.labels] == [
        label.selected_candidate_id for label in second.labels
    ]
    assert first.cost_after == second.cost_after


def test_component_totals_are_exposed() -> None:
    label = make_label(
        "label:a",
        (make_candidate("label:a", CompassPosition.N, 100.0, 100.0),),
    )
    result = optimize_labels((label,), EMPTY_SCENE, TRANSFORM, STYLE)
    assert "anchor_distance_mm" in result.component_totals_after
    assert "preference_rank" in result.component_totals_after