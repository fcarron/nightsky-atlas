"""Tests for compass candidate generation."""

from __future__ import annotations

import pytest

from nightsky_atlas.chart.page import PagePoint, PageRect
from nightsky_atlas.layout.candidates import compass_candidates
from nightsky_atlas.layout.geometry import circle_rect_edge_distance_mm
from nightsky_atlas.layout.models import CompassPosition
from nightsky_atlas.render.text import TextMetrics

METRICS = TextMetrics(width_mm=4.0, height_mm=2.0)
ANCHOR = PagePoint(x_mm=100.0, y_mm=100.0)


def make_candidates():
    return compass_candidates(
        label_id="label:dso:X",
        metrics=METRICS,
        anchor=ANCHOR,
        exclusion_radius_mm=2.0,
        padding_mm=0.5,
    )


def test_generates_all_eight_positions() -> None:
    candidates = make_candidates()
    assert len(candidates) == 8
    assert {candidate.position for candidate in candidates} == {
        CompassPosition.N,
        CompassPosition.NE,
        CompassPosition.E,
        CompassPosition.SE,
        CompassPosition.S,
        CompassPosition.SW,
        CompassPosition.W,
        CompassPosition.NW,
    }


def test_candidate_ids_are_stable() -> None:
    candidates = make_candidates()
    assert candidates[0].id == "label:dso:X:N"
    assert all(candidate.id.startswith("label:dso:X:") for candidate in candidates)


def test_north_candidate_is_above_anchor() -> None:
    north = next(item for item in make_candidates() if item.position == CompassPosition.N)
    assert north.bounds.center.y_mm < ANCHOR.y_mm
    assert north.bounds.center.x_mm == pytest.approx(ANCHOR.x_mm)


def test_east_candidate_is_left_of_anchor() -> None:
    east = next(item for item in make_candidates() if item.position == CompassPosition.E)
    assert east.bounds.center.x_mm < ANCHOR.x_mm
    assert east.bounds.center.y_mm == pytest.approx(ANCHOR.y_mm)


def test_candidate_clears_exclusion_zone() -> None:
    for candidate in make_candidates():
        center = candidate.bounds.center
        distance = ((center.x_mm - ANCHOR.x_mm) ** 2 + (center.y_mm - ANCHOR.y_mm) ** 2) ** 0.5
        assert distance >= 2.0 + 0.5


def test_bounds_match_metrics() -> None:
    for candidate in make_candidates():
        assert candidate.bounds.width_mm == pytest.approx(METRICS.width_mm)
        assert candidate.bounds.height_mm == pytest.approx(METRICS.height_mm)


def test_exact_edge_gap_refines_diagonal_candidates() -> None:
    candidates = compass_candidates(
        label_id="label:star:X",
        metrics=METRICS,
        anchor=ANCHOR,
        exclusion_radius_mm=2.0,
        padding_mm=0.5,
        exact_edge_gap_mm=0.5,
    )
    for candidate in candidates:
        assert circle_rect_edge_distance_mm(ANCHOR, 2.0, candidate.bounds) == pytest.approx(
            0.5, abs=0.01
        )


def test_exact_edge_gap_preserves_additional_candidate_rings() -> None:
    candidates = compass_candidates(
        label_id="label:star:X",
        metrics=METRICS,
        anchor=ANCHOR,
        exclusion_radius_mm=2.0,
        exact_edge_gap_mm=0.45,
        ring_count=2,
        ring_gap_mm=1.25,
    )
    for candidate in candidates:
        assert circle_rect_edge_distance_mm(
            ANCHOR, 2.0, candidate.bounds
        ) == pytest.approx(0.45 + candidate.ring * 1.25, abs=0.01)


def test_candidate_translates_glyph_geometry_to_page_coordinates() -> None:
    metrics = TextMetrics(
        width_mm=4.0,
        height_mm=2.0,
        ink_rects_mm=(PageRect(0.5, 0.25, 1.0, 1.0),),
        whitespace_rects_mm=(PageRect(1.5, 0.0, 0.5, 2.0),),
    )
    candidate = compass_candidates(
        label_id="label:star:X",
        metrics=metrics,
        anchor=ANCHOR,
        exclusion_radius_mm=2.0,
    )[0]
    assert candidate.glyph_bounds[0].left_mm == pytest.approx(
        candidate.bounds.left_mm + 0.5
    )
    assert candidate.whitespace_bounds[0].top_mm == pytest.approx(candidate.bounds.top_mm)


def test_dense_candidate_sampling_uses_all_requested_gaps_and_directions() -> None:
    from nightsky_atlas.layout.candidates import CANDIDATE_DIRECTIONS_16

    gaps = (0.35, 0.55, 0.8)
    candidates = compass_candidates(
        label_id="label:dso:NGC1",
        metrics=METRICS,
        anchor=ANCHOR,
        exclusion_radius_mm=2.0,
        exact_edge_gap_mm=gaps[0],
        exact_edge_gaps_mm=gaps,
        positions=CANDIDATE_DIRECTIONS_16,
    )
    assert len(candidates) == len(gaps) * 16
    for ring, gap in enumerate(gaps):
        assert {item.position for item in candidates if item.ring == ring} == set(
            CANDIDATE_DIRECTIONS_16
        )
        assert all(
            circle_rect_edge_distance_mm(ANCHOR, 2.0, item.bounds)
            == pytest.approx(gap, abs=0.01)
            for item in candidates
            if item.ring == ring
        )


def test_exact_edge_callback_can_use_visible_glyph_not_logical_line_box() -> None:
    """Short glyphs should not inherit unused Pango descent as star clearance."""
    metrics = TextMetrics(
        width_mm=2.0,
        height_mm=3.0,
        # A τ-like short glyph with 0.75 mm unused descent in its line box.
        ink_rects_mm=(PageRect(0.3, 0.5, 1.4, 1.75),),
    )

    def glyph_circle_gap(bounds: PageRect, glyphs: tuple[PageRect, ...]) -> float:
        return min(
            circle_rect_edge_distance_mm(ANCHOR, 1.0, rect)
            for rect in (glyphs or (bounds,))
        )

    candidate = next(
        item
        for item in compass_candidates(
            label_id="label:star:tau",
            metrics=metrics,
            anchor=ANCHOR,
            exclusion_radius_mm=1.0,
            exact_edge_gap_mm=0.45,
            exact_edge_distance=glyph_circle_gap,
        )
        if item.position == CompassPosition.N
    )
    assert glyph_circle_gap(candidate.bounds, candidate.glyph_bounds) == pytest.approx(
        0.45, abs=0.01
    )
    assert circle_rect_edge_distance_mm(ANCHOR, 1.0, candidate.bounds) < 0.0
