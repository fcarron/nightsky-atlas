"""Tests for the deterministic label optimizer."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from nightsky_atlas.atlas.config import load_style_config
from nightsky_atlas.catalog.models import Provenance, Star
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.chart.page import PagePoint, PageRect, PageTransform
from nightsky_atlas.layout.models import CompassPosition, Label, LabelCandidate
from nightsky_atlas.layout.optimizer import _association_scale, optimize_labels
from nightsky_atlas.render.symbols import StarSizeModel
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


def test_optimizer_avoids_furniture() -> None:
    label = make_label(
        "label:a",
        (
            make_candidate("label:a", CompassPosition.N, 100.0, 100.0),
            make_candidate("label:a", CompassPosition.S, 100.0, 130.0),
        ),
    )
    furniture = (PageRect(left_mm=98.0, top_mm=99.0, width_mm=12.0, height_mm=5.0),)
    result = optimize_labels((label,), EMPTY_SCENE, TRANSFORM, STYLE, furniture=furniture)
    assert result.labels[0].selected_candidate_id == "label:a:S"


def test_optional_label_outside_page_is_hidden() -> None:
    label = make_label(
        "label:out",
        (make_candidate("label:out", CompassPosition.N, -50.0, -50.0),),
        mandatory=False,
    )
    result = optimize_labels((label,), EMPTY_SCENE, TRANSFORM, STYLE)
    assert result.labels[0].hidden is True
    assert result.hidden_count == 1


def test_optimizer_never_changes_canonical_label_text() -> None:
    first = LabelCandidate(
        id="label:star:1:E",
        position=CompassPosition.E,
        anchor=PagePoint(100.0, 100.0),
        bounds=PageRect(100.0, 100.0, 14.0, 2.5),
        display_text="obsolete fallback",
        variant_rank=1,
    )
    second = LabelCandidate(
        id="label:star:1:W",
        position=CompassPosition.W,
        anchor=PagePoint(90.0, 100.0),
        bounds=PageRect(90.0, 100.0, 14.0, 2.5),
    )
    label = make_label("label:star:1", (first, second))
    label = replace(label, text="Deneb α")
    placed = optimize_labels((label,), EMPTY_SCENE, TRANSFORM, STYLE).labels[0]
    assert placed.text == "Deneb α"
    assert Label.from_dict(placed.to_dict()) == placed


def test_optimizer_preserves_canonical_dso_text() -> None:
    candidate = LabelCandidate(
        id="label:dso:NGC7000:E",
        position=CompassPosition.E,
        anchor=PagePoint(100.0, 100.0),
        bounds=PageRect(100.0, 100.0, 8.0, 2.5),
        display_text="NGC 7000",
    )
    label = replace(
        make_label("label:dso:NGC7000", (candidate,)),
        target_id="NGC7000",
        text="7000",
    )
    placed = optimize_labels((label,), EMPTY_SCENE, TRANSFORM, STYLE).labels[0]
    assert placed.text == "7000"
    assert not placed.hidden


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


def test_per_label_ownership_diagnostics_are_exposed() -> None:
    label = make_label(
        "label:dso:X",
        (make_candidate("label:dso:X", CompassPosition.E, 100.0, 100.0),),
    )
    result = optimize_labels((label,), EMPTY_SCENE, TRANSFORM, STYLE)
    diagnostic = result.label_diagnostics[label.id]
    assert "source_facing_edge_distance_mm" in diagnostic
    assert "glyph_proximity_cost" in diagnostic
    assert diagnostic["leader_line_used"] is False


def test_only_compact_star_labels_get_stronger_distance_scale() -> None:
    short_star = replace(
        make_label(
            "label:star:short",
            (make_candidate("label:star:short", CompassPosition.N, 100.0, 100.0),),
        ),
        text="47",
    )
    named_star = replace(short_star, id="label:star:named", text="Deneb α")
    short_dso = replace(short_star, id="label:dso:short", text="57")
    assert _association_scale(short_star, STYLE) > 1.0
    assert _association_scale(named_star, STYLE) == 1.0
    assert _association_scale(short_dso, STYLE) == 1.0


def test_optimizer_prefers_candidate_with_cleaner_foreign_star_clearance() -> None:
    star = Star("foreign", 187.5, 12.0, 0.0, Provenance("TEST", "foreign"))
    scene = build_scene(CHART, (star,), ())
    center = TRANSFORM.center_page
    radius = StarSizeModel.from_style(STYLE.star).radius_mm(0.0)
    near = LabelCandidate(
        id="label:dso:near",
        position=CompassPosition.N,
        anchor=center,
        bounds=PageRect(center.x_mm + radius + 0.5, center.y_mm - 1.25, 8.0, 2.5),
    )
    clean = LabelCandidate(
        id="label:dso:clean",
        position=CompassPosition.S,
        anchor=center,
        bounds=PageRect(center.x_mm + 8.0, center.y_mm + 6.0, 8.0, 2.5),
    )
    label = Label(
        id="label:dso",
        target_id="dso:missing",
        text="7000",
        priority=50,
        mandatory=True,
        candidates=(near, clean),
    )

    result = optimize_labels((label,), scene, TRANSFORM, STYLE)

    assert result.labels[0].selected_candidate_id == clean.id
    assert result.component_totals_after["label_foreign_star_clearance"] == 0.0
