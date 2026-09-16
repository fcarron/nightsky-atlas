"""Tests for the decomposed soft-cost function."""

from __future__ import annotations

import pytest

from nightsky_atlas.chart.page import PagePoint, PageRect
from nightsky_atlas.layout.models import CompassPosition, LabelCandidate
from nightsky_atlas.layout.scoring import CostWeights, SymbolCircle, score_candidate

PRINTABLE = PageRect(left_mm=12.0, top_mm=12.0, width_mm=273.0, height_mm=186.0)


def make_candidate(position: CompassPosition, left: float, top: float) -> LabelCandidate:
    return LabelCandidate(
        id=f"label:x:{position.value}",
        position=position,
        anchor=PagePoint(left, top),
        bounds=PageRect(left, top, 8.0, 2.5),
    )


def score(candidate: LabelCandidate, **kwargs: object):
    defaults = {
        "target_anchor": PagePoint(150.0, 100.0),
        "placed_bounds": (),
        "symbols": (),
        "printable": PRINTABLE,
        "crowding_radius_mm": 6.0,
        "weights": CostWeights(),
    }
    defaults.update(kwargs)
    return score_candidate(candidate, **defaults)  # type: ignore[arg-type]


def test_preference_rank_component() -> None:
    north = score(make_candidate(CompassPosition.N, 146.0, 90.0)).preference_rank
    south = score(make_candidate(CompassPosition.S, 146.0, 110.0)).preference_rank
    assert north < south


def test_edge_proximity_penalty() -> None:
    near_edge = score(make_candidate(CompassPosition.N, 13.0, 100.0)).edge_proximity_mm
    central = score(make_candidate(CompassPosition.N, 140.0, 100.0)).edge_proximity_mm
    assert near_edge > 0.0
    assert central == 0.0


def test_label_label_overlap_component() -> None:
    other = PageRect(140.0, 98.0, 8.0, 2.5)
    breakdown = score(
        make_candidate(CompassPosition.N, 142.0, 99.0), placed_bounds=(other,)
    )
    assert breakdown.label_label_overlap_mm2 > 0.0


def test_symbol_overlap_component() -> None:
    symbol = SymbolCircle(center=PagePoint(146.0, 91.0), radius_mm=2.0)
    breakdown = score(make_candidate(CompassPosition.N, 142.0, 90.0), symbols=(symbol,))
    assert breakdown.label_symbol_overlap_mm2 > 0.0


def test_crowding_component() -> None:
    others = (
        PageRect(140.0, 90.0, 8.0, 2.5),
        PageRect(141.0, 92.0, 8.0, 2.5),
    )
    breakdown = score(
        make_candidate(CompassPosition.N, 142.0, 90.0), placed_bounds=others
    )
    assert breakdown.crowding >= 1.0


def test_total_is_weighted_sum() -> None:
    breakdown = score(make_candidate(CompassPosition.N, 140.0, 95.0))
    weights = CostWeights()
    weight_for = {
        "label_label_overlap_mm2": "label_label_overlap",
        "label_symbol_overlap_mm2": "label_symbol_overlap",
        "anchor_distance_mm": "anchor_distance",
        "edge_proximity_mm": "edge_proximity",
        "preference_rank": "preference_rank",
        "crowding": "crowding",
    }
    expected = sum(
        value * getattr(weights, weight_for[name])
        for name, value in breakdown.components().items()
    )
    assert breakdown.total(weights) == pytest.approx(expected)