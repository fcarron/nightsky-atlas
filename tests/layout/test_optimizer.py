"""Tests for the deterministic label optimizer."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import nightsky_atlas.layout.optimizer as optimizer_module
from nightsky_atlas.atlas.config import load_style_config
from nightsky_atlas.catalog.models import DsoType, Provenance, Star
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.chart.page import PagePoint, PageRect, PageTransform
from nightsky_atlas.layout.association import SourceGeometry
from nightsky_atlas.layout.geometry import rects_overlap
from nightsky_atlas.layout.models import CompassPosition, Label, LabelCandidate
from nightsky_atlas.layout.optimizer import (
    _association_scale,
    _build_star_index,
    _build_symbol_index,
    _CandidateScoreCache,
    _dso_conflict_components,
    _dso_placement_metrics,
    _is_valid,
    _repair_dso_hard_conflicts,
    optimize_labels,
)
from nightsky_atlas.layout.scoring import CostWeights, SymbolCircle
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


def test_candidate_cache_reuses_static_score_for_changed_neighbors(monkeypatch) -> None:
    candidate = make_candidate("label:dso:X", CompassPosition.E, 100.0, 100.0)
    label = make_label("label:dso:X", (candidate,))
    calls = 0
    original = optimizer_module.score_candidate

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(optimizer_module, "score_candidate", counted)
    cache = _CandidateScoreCache(
        {"X": PagePoint(98.0, 101.0)},
        PageRect(12.0, 12.0, 273.0, 186.0),
        _build_symbol_index(()),
        (),
        _build_star_index(()),
        (),
        STYLE,
        CostWeights(),
        (),
    )
    clear_cost = cache.cost(label, candidate, ())
    occupied_cost = cache.cost(
        label, candidate, (PageRect(101.0, 100.0, 2.0, 2.5),)
    )

    assert calls == 1
    assert occupied_cost > clear_cost


def test_candidate_cache_reuses_static_validity_for_changed_neighbors(monkeypatch) -> None:
    candidate = make_candidate("label:dso:X", CompassPosition.E, 100.0, 100.0)
    label = make_label("label:dso:X", (candidate,))
    calls = 0
    original = optimizer_module._is_valid

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(optimizer_module, "_is_valid", counted)
    cache = _CandidateScoreCache(
        {"X": PagePoint(98.0, 101.0)},
        PageRect(12.0, 12.0, 273.0, 186.0),
        _build_symbol_index(()),
        (),
        _build_star_index(()),
        (),
        STYLE,
        CostWeights(),
        (),
    )

    assert cache.valid(label, candidate, ())
    assert not cache.valid(label, candidate, (PageRect(101.0, 100.0, 2.0, 2.5),))
    assert cache.valid(label, candidate, ())
    assert calls == 1


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


def test_local_repair_diagnostics_are_deterministic() -> None:
    label = make_label(
        "label:dso:X",
        (
            make_candidate("label:dso:X", CompassPosition.N, 100.0, 100.0),
            make_candidate("label:dso:X", CompassPosition.S, 100.0, 110.0),
        ),
    )
    first = optimize_labels((label,), EMPTY_SCENE, TRANSFORM, STYLE)
    second = optimize_labels((label,), EMPTY_SCENE, TRANSFORM, STYLE)
    passes = first.metrics["local_repair"]["passes"]

    assert first.metrics["local_repair"] == second.metrics["local_repair"]
    assert len(passes) >= 1
    assert passes[0]["evaluated_labels"] == 1


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


def test_valid_leader_resolves_ownership_ambiguity_but_keeps_raw_diagnostic() -> None:
    candidate = make_candidate(
        "label:dso:NGC1", CompassPosition.E, 100.0, 100.0
    )
    label = replace(
        make_label("label:dso:NGC1", (candidate,)),
        target_id="NGC1",
        leader_line=True,
    )
    metrics = _dso_placement_metrics(
        (label,),
        {
            label.id: {
                "label_id": label.id,
                "source_facing_edge_distance_mm": 1.0,
                "ownership_margin_mm": -0.2,
                "competing_source_ambiguity_cost": 1.0,
                "competing_owner_cost": 0.0,
                "leader_line_used": True,
                "leader_line_length_mm": 1.0,
            }
        },
        {},
        1.0,
        weak_margin_mm=0.75,
    )

    assert metrics["raw_ownership_ambiguity_count"] == 1
    assert metrics["ownership_ambiguity_count"] == 0
    assert metrics["negative_ownership_margin_count"] == 1
    assert metrics["weak_ownership_margin_count"] == 1


def test_mandatory_label_outside_page_is_placed() -> None:
    label = make_label(
        "label:out",
        (make_candidate("label:out", CompassPosition.N, -50.0, -50.0),),
        mandatory=True,
    )
    result = optimize_labels((label,), EMPTY_SCENE, TRANSFORM, STYLE)
    assert result.labels[0].hidden is False
    assert result.placed_count == 1


def test_optional_selected_dso_label_is_not_suppressed_by_placement() -> None:
    label = replace(
        make_label(
            "label:dso:NGC1",
            (make_candidate("label:dso:NGC1", CompassPosition.N, -50.0, -50.0),),
            mandatory=False,
        ),
        target_id="NGC1",
    )
    result = optimize_labels((label,), EMPTY_SCENE, TRANSFORM, STYLE)
    assert result.labels[0].hidden is False
    assert result.placed_count == 1


def test_galaxy_label_validity_uses_ellipse_not_bounding_circle() -> None:
    center = PagePoint(150.0, 100.0)
    source = SourceGeometry(
        id="NGC1",
        source_type=DsoType.GALAXY,
        center=center,
        radius_x_mm=5.0,
        radius_y_mm=1.0,
    )
    label = make_label(
        "label:dso:NGC1",
        (make_candidate("label:dso:NGC1", CompassPosition.N, 146.0, 96.0),),
    )
    candidate = label.candidates[0]
    assert _is_valid(
        label,
        candidate,
        (),
        PageRect(12.0, 12.0, 273.0, 186.0),
        (SymbolCircle(center, 5.0, "NGC1"),),
        (),
        STYLE,
        source_geometries=(source,),
    )


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


def test_dso_conflict_component_is_optimized_jointly_without_culling() -> None:
    first = replace(
        make_label(
            "label:dso:A",
            (
                make_candidate("label:dso:A", CompassPosition.N, 100.0, 100.0),
                make_candidate("label:dso:A", CompassPosition.E, 120.0, 100.0),
            ),
        ),
        target_id="A",
    )
    second = replace(
        make_label(
            "label:dso:B",
            (
                make_candidate("label:dso:B", CompassPosition.N, 100.0, 100.0),
                make_candidate("label:dso:B", CompassPosition.W, 130.0, 100.0),
            ),
        ),
        target_id="B",
    )
    result = optimize_labels((first, second), EMPTY_SCENE, TRANSFORM, STYLE)
    assert result.placed_count == 2
    assert result.metrics["local_conflict_components"]["joint_components_searched"] == 1
    selected = [label.effective_candidate().bounds for label in result.labels]
    assert not (
        selected[0].left_mm < selected[1].right_mm
        and selected[1].left_mm < selected[0].right_mm
        and selected[0].top_mm < selected[1].bottom_mm
        and selected[1].top_mm < selected[0].bottom_mm
    )


def test_joint_dso_optimizer_preserves_locked_override() -> None:
    first_candidates = (
        make_candidate("label:dso:A", CompassPosition.N, 100.0, 100.0),
        make_candidate("label:dso:A", CompassPosition.E, 120.0, 100.0),
    )
    first = replace(
        make_label("label:dso:A", first_candidates),
        target_id="A",
        selected_candidate_id=first_candidates[1].id,
        locked=True,
    )
    second = replace(
        make_label(
            "label:dso:B",
            (
                make_candidate("label:dso:B", CompassPosition.N, 100.0, 100.0),
                make_candidate("label:dso:B", CompassPosition.W, 108.0, 100.0),
            ),
        ),
        target_id="B",
    )

    components = _dso_conflict_components((first, second), STYLE)
    result = optimize_labels((first, second), EMPTY_SCENE, TRANSFORM, STYLE)
    by_id = {label.id: label for label in result.labels}

    assert all(first.id not in component for component in components)
    assert any(second.id in component for component in components)
    assert by_id[first.id].locked is True
    assert by_id[first.id].selected_candidate_id == first_candidates[1].id


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
    result = optimize_labels(
        (label,), EMPTY_SCENE, TRANSFORM, STYLE, detailed_diagnostics=True
    )
    diagnostic = result.label_diagnostics[label.id]
    assert "source_facing_edge_distance_mm" in diagnostic
    assert "glyph_proximity_cost" in diagnostic
    assert "candidate_total_cost" in diagnostic
    assert "nearest_competing_dso_id" in diagnostic
    assert "best_alternatives" in diagnostic
    assert diagnostic["leader_line_used"] is False
    assert result.metrics["dso_label_count"] == 1
    assert "optimizer_runtime_s" in result.metrics


def test_pair_conflict_repair_reassigns_labels_jointly() -> None:
    first_current = make_candidate("label:dso:NGC1", CompassPosition.E, 100.0, 100.0)
    first_alt = make_candidate("label:dso:NGC1", CompassPosition.N, 100.0, 90.0)
    second_current = make_candidate("label:dso:NGC2", CompassPosition.W, 102.0, 100.0)
    second_alt = make_candidate("label:dso:NGC2", CompassPosition.E, 110.0, 100.0)
    first = replace(
        make_label("label:dso:NGC1", (first_current, first_alt)), target_id="NGC1"
    )
    second = replace(
        make_label("label:dso:NGC2", (second_current, second_alt)), target_id="NGC2"
    )
    labels = (first, second)
    placements, stats = _repair_dso_hard_conflicts(
        labels,
        {first.id: first_current.id, second.id: second_current.id},
        {"NGC1": PagePoint(104.0, 101.25), "NGC2": PagePoint(113.0, 101.25)},
        PageRect(12.0, 12.0, 273.0, 186.0),
        _build_symbol_index(()),
        (),
        _build_star_index(()),
        (),
        STYLE,
        CostWeights(),
        (),
        (),
    )
    assert placements[second.id] == second_alt.id
    assert stats["pair_conflict_moves"] == 1
    assert not rects_overlap(
        first.candidate(placements[first.id]).bounds,
        second.candidate(placements[second.id]).bounds,
    )


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
    assert _association_scale(short_dso, STYLE) == STYLE.label.dso_placement.compact_label_factor


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
