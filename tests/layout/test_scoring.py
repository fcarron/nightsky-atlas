"""Tests for the decomposed soft-cost function."""

from __future__ import annotations

import pytest

from nightsky_atlas.chart.page import PagePoint, PageRect
from nightsky_atlas.layout.models import CompassPosition, LabelCandidate
from nightsky_atlas.layout.scoring import CostWeights, StarCircle, SymbolCircle, score_candidate

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
    breakdown = score(make_candidate(CompassPosition.N, 142.0, 99.0), placed_bounds=(other,))
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
    breakdown = score(make_candidate(CompassPosition.N, 142.0, 90.0), placed_bounds=others)
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
        "constellation_line_overlap": "constellation_line_overlap",
        "label_foreign_star_clearance": "label_foreign_star_clearance",
        "label_associated_star_clearance": "label_associated_star_clearance",
        "label_association_distance_mm": "label_association_distance",
        "label_source_distance_mm": "label_source_distance",
        "label_source_corridor": "label_source_corridor",
        "label_competing_source_ambiguity": "label_competing_source_ambiguity",
        "label_foreign_object_proximity": "label_foreign_object_proximity",
    }
    expected = sum(
        value * getattr(weights, weight_for[name]) for name, value in breakdown.components().items()
    )
    assert breakdown.total(weights) == pytest.approx(expected)


def _star_at_clearance(
    candidate: LabelCandidate, clearance_mm: float, radius_mm: float = 0.5
) -> StarCircle:
    return StarCircle(
        id="star:foreign",
        star_ids=frozenset({"star:foreign"}),
        center=PagePoint(
            candidate.bounds.left_mm - radius_mm - clearance_mm,
            candidate.bounds.center.y_mm,
        ),
        radius_mm=radius_mm,
    )


@pytest.mark.parametrize(
    ("clearance_mm", "expect_penalty"),
    ((0.5, True), (0.8, True), (1.01, False)),
)
def test_foreign_star_clearance_penalty_is_graded(
    clearance_mm: float, expect_penalty: bool
) -> None:
    candidate = make_candidate(CompassPosition.N, 140.0, 95.0)
    breakdown = score(candidate, stars=(_star_at_clearance(candidate, clearance_mm),))
    assert (breakdown.label_foreign_star_clearance > 0.0) is expect_penalty


def test_edge_distance_uses_rendered_star_radius() -> None:
    candidate = make_candidate(CompassPosition.N, 140.0, 95.0)
    center = PagePoint(candidate.bounds.left_mm - 1.0, candidate.bounds.center.y_mm)
    small = StarCircle("small", frozenset({"small"}), center, 0.2)
    large = StarCircle("large", frozenset({"large"}), center, 0.8)
    small_cost = score(candidate, stars=(small,)).label_foreign_star_clearance
    large_cost = score(candidate, stars=(large,)).label_foreign_star_clearance
    assert large_cost > small_cost


def test_equally_close_bright_foreign_star_costs_more_than_faint_star() -> None:
    candidate = make_candidate(CompassPosition.N, 140.0, 95.0)
    faint = _star_at_clearance(candidate, 0.05, radius_mm=0.2)
    bright = _star_at_clearance(candidate, 0.05, radius_mm=1.2)
    faint_cost = score(candidate, stars=(faint,)).label_foreign_star_clearance
    bright_cost = score(candidate, stars=(bright,)).label_foreign_star_clearance
    assert bright_cost > faint_cost * 5.0


def test_associated_star_uses_smaller_clearance_and_far_distance_penalty() -> None:
    candidate = make_candidate(CompassPosition.N, 140.0, 95.0)
    star = _star_at_clearance(candidate, 0.5)
    associated = score(
        candidate,
        stars=(star,),
        associated_star_ids=frozenset({"star:foreign"}),
    )
    foreign = score(candidate, stars=(star,))
    far = _star_at_clearance(candidate, 6.0)
    far_associated = score(
        candidate,
        stars=(far,),
        associated_star_ids=frozenset({"star:foreign"}),
    )
    assert associated.label_associated_star_clearance < foreign.label_foreign_star_clearance
    assert far_associated.label_association_distance_mm > 0.0


def test_foreign_star_in_source_corridor_is_penalized() -> None:
    candidate = make_candidate(CompassPosition.E, 151.0, 99.0)
    target = StarCircle("owner", frozenset({"owner"}), PagePoint(150.0, 100.0), 0.5)
    competing = StarCircle("other", frozenset({"other"}), PagePoint(150.6, 100.0), 0.2)
    clear = score(
        candidate,
        stars=(target,),
        associated_star_ids=frozenset({"owner"}),
        target_source_id="owner",
    )
    blocked = score(
        candidate,
        stars=(target, competing),
        associated_star_ids=frozenset({"owner"}),
        target_source_id="owner",
    )
    assert blocked.label_source_corridor > clear.label_source_corridor
    assert blocked.label_competing_source_ambiguity > 0.0


def test_dso_owner_and_foreign_object_use_source_geometry() -> None:
    candidate = make_candidate(CompassPosition.E, 151.0, 99.0)
    owner = SymbolCircle(PagePoint(150.0, 100.0), 0.5, "NGC1")
    other = SymbolCircle(PagePoint(151.0, 100.0), 0.2, "NGC2")
    clear = score(candidate, symbols=(owner,), target_source_id="NGC1")
    ambiguous = score(candidate, symbols=(owner, other), target_source_id="NGC1")
    assert ambiguous.label_foreign_object_proximity > clear.label_foreign_object_proximity
    assert ambiguous.label_competing_source_ambiguity > clear.label_competing_source_ambiguity


def test_contour_backed_dso_uses_source_facing_contour_edge() -> None:
    candidate = make_candidate(CompassPosition.W, 160.0, 99.0)
    circle = SymbolCircle(PagePoint(150.0, 100.0), 4.0, "NGC1")
    contour = SymbolCircle(
        PagePoint(150.0, 100.0),
        4.0,
        "NGC1",
        ((PagePoint(159.0, 98.0), PagePoint(159.0, 102.0)),),
    )
    circle_cost = score(
        candidate,
        target_source_id="NGC1",
        source_symbols=(circle,),
    )
    contour_cost = score(
        candidate,
        target_source_id="NGC1",
        source_symbols=(contour,),
    )
    assert circle_cost.label_source_distance_mm > 0.0
    assert contour_cost.label_source_distance_mm == 0.0
