"""Tests for compass candidate generation."""

from __future__ import annotations

import pytest

from nightsky_atlas.chart.page import PagePoint
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
    assert {candidate.position for candidate in candidates} == set(CompassPosition)


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
