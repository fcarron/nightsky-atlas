"""Tests for the decomposed soft-cost function."""

from __future__ import annotations

import pytest

from nightsky_atlas.atlas.config import DsoLabelPlacementStyle, SourceAssociationStyle
from nightsky_atlas.catalog.models import DsoType
from nightsky_atlas.chart.page import PagePoint, PageRect
from nightsky_atlas.layout.association import SourceGeometry
from nightsky_atlas.layout.models import CompassPosition, LabelCandidate
from nightsky_atlas.layout.scoring import (
    CostWeights,
    StarCircle,
    SymbolCircle,
    rescore_candidate_interactions,
    score_candidate,
    star_rect_edge_distance_mm,
)

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
        "label_source_facing_edge_distance_mm": "label_source_facing_edge_distance",
        "label_source_corridor": "label_source_corridor",
        "label_competing_source_ambiguity": "label_competing_source_ambiguity",
        "label_competing_owner": "label_competing_owner",
        "label_glyph_proximity": "label_glyph_proximity",
        "label_foreign_object_proximity": "label_foreign_object_proximity",
        "label_ownership_margin_cost": "label_ownership_margin",
    }
    expected = sum(
        value * getattr(weights, weight_for[name]) for name, value in breakdown.components().items()
    )
    assert breakdown.total(weights) == pytest.approx(expected)


def _galaxy_source(source_id: str, x: float, y: float, radius: float) -> SourceGeometry:
    return SourceGeometry(
        id=source_id,
        source_type=DsoType.GALAXY,
        center=PagePoint(x, y),
        radius_x_mm=radius,
        radius_y_mm=radius,
    )


def test_cached_static_score_matches_full_score_with_different_placed_labels() -> None:
    candidate = make_candidate(CompassPosition.E, 102.0, 99.0)
    owner = _galaxy_source("NGC-owner", 100.0, 100.0, 1.0)
    foreign = _galaxy_source("NGC-foreign", 112.0, 100.0, 0.5)
    placement = DsoLabelPlacementStyle()
    common = {
        "target_anchor": owner.center,
        "target_source_id": owner.id,
        "source_symbols": (owner, foreign),
        "source_association": SourceAssociationStyle(),
        "dso_placement": placement,
        "is_dso_label": True,
    }
    static = score(candidate, **common)
    for placed in (
        (PageRect(109.0, 99.0, 8.0, 2.5),),
        (PageRect(103.0, 99.0, 8.0, 2.5), PageRect(115.0, 104.0, 8.0, 2.5)),
    ):
        full = score(candidate, placed_bounds=placed, **common)
        cached = rescore_candidate_interactions(
            static,
            candidate,
            placed,
            crowding_radius_mm=6.0,
            dso_placement=placement,
            is_dso_label=True,
        )
        assert cached == full
        assert cached.total(CostWeights()) == full.total(CostWeights())


def test_ownership_margin_can_outweigh_a_slightly_closer_candidate() -> None:
    owner = _galaxy_source("NGC-owner", 100.0, 100.0, 1.0)
    foreign = _galaxy_source("NGC-foreign", 109.0, 100.0, 1.0)
    close = make_candidate(CompassPosition.E, 102.0, 99.0)
    clear = make_candidate(CompassPosition.N, 98.0, 96.0)
    close_score = score(
        close,
        target_anchor=owner.center,
        target_source_id=owner.id,
        source_symbols=(owner, foreign),
        source_association=SourceAssociationStyle(),
        dso_placement=DsoLabelPlacementStyle(),
        is_dso_label=True,
    )
    clear_score = score(
        clear,
        target_anchor=owner.center,
        target_source_id=owner.id,
        source_symbols=(owner, foreign),
        source_association=SourceAssociationStyle(),
        dso_placement=DsoLabelPlacementStyle(),
        is_dso_label=True,
    )
    assert close_score.ownership_margin_mm < clear_score.ownership_margin_mm
    assert close_score.label_ownership_margin_cost > clear_score.label_ownership_margin_cost
    assert clear_score.total(CostWeights()) < close_score.total(CostWeights())


def test_overlapping_galaxies_use_the_documented_ownership_exception() -> None:
    owner = _galaxy_source("NGC-owner", 100.0, 100.0, 2.0)
    interacting = _galaxy_source("NGC-interacting", 102.0, 100.0, 2.0)
    candidate = make_candidate(CompassPosition.E, 105.0, 99.0)
    breakdown = score(
        candidate,
        target_source_id=owner.id,
        source_symbols=(owner, interacting),
        source_association=SourceAssociationStyle(),
        dso_placement=DsoLabelPlacementStyle(),
        is_dso_label=True,
    )
    assert breakdown.ownership_margin_mm < 0.0
    assert not breakdown.foreign_source_closer_than_owner
    assert breakdown.label_ownership_margin_cost < (
        max(0.0, DsoLabelPlacementStyle().ownership_margin_preferred_mm
            - breakdown.ownership_margin_mm) ** 2
    )


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


def test_foreign_star_outside_corridor_only_gets_normal_proximity_cost() -> None:
    candidate = make_candidate(CompassPosition.E, 151.0, 99.0)
    target = StarCircle("owner", frozenset({"owner"}), PagePoint(150.0, 100.0), 0.5)
    nearby_above = StarCircle(
        "above",
        frozenset({"above"}),
        PagePoint(152.0, 98.6),
        0.2,
    )
    breakdown = score(
        candidate,
        stars=(target, nearby_above),
        associated_star_ids=frozenset({"owner"}),
        target_source_id="owner",
    )
    assert breakdown.label_source_corridor == 0.0
    assert breakdown.label_foreign_star_clearance > 0.0


def test_source_facing_distance_uses_star_disk_edge() -> None:
    candidate = make_candidate(CompassPosition.W, 151.0, 99.0)
    owner = StarCircle("owner", frozenset({"owner"}), PagePoint(150.0, 100.0), 0.5)
    breakdown = score(
        candidate,
        stars=(owner,),
        associated_star_ids=frozenset({"owner"}),
        target_source_id="owner",
    )
    assert breakdown.label_source_facing_edge_distance_mm == pytest.approx(0.5)


def test_compact_label_scale_strengthens_source_distance_cost() -> None:
    candidate = make_candidate(CompassPosition.W, 153.0, 99.0)
    owner = StarCircle("owner", frozenset({"owner"}), PagePoint(150.0, 100.0), 0.5)
    common = {
        "stars": (owner,),
        "associated_star_ids": frozenset({"owner"}),
        "target_source_id": "owner",
    }
    long_label = score(candidate, association_scale=1.0, **common)
    compact_label = score(candidate, association_scale=1.35, **common)
    assert compact_label.label_source_distance_mm == pytest.approx(
        long_label.label_source_distance_mm * 1.35
    )
    assert compact_label.total(CostWeights()) > long_label.total(CostWeights())


def test_compact_label_prefers_close_source_despite_faint_star_soft_cost() -> None:
    close = make_candidate(CompassPosition.W, 151.0, 99.0)
    far = make_candidate(CompassPosition.W, 154.0, 99.0)
    owner = StarCircle("owner", frozenset({"owner"}), PagePoint(150.0, 100.0), 0.5)
    faint = StarCircle("faint", frozenset({"faint"}), PagePoint(152.0, 98.7), 0.1)
    common = {
        "stars": (owner, faint),
        "associated_star_ids": frozenset({"owner"}),
        "target_source_id": "owner",
        "association_scale": 1.35,
    }
    assert score(close, **common).total(CostWeights()) < score(far, **common).total(
        CostWeights()
    )


def test_competing_owner_can_justify_another_nearby_candidate() -> None:
    blocked = make_candidate(CompassPosition.W, 151.0, 99.0)
    clear = make_candidate(CompassPosition.N, 146.0, 96.0)
    owner = StarCircle("owner", frozenset({"owner"}), PagePoint(150.0, 100.0), 0.5)
    competitor = StarCircle(
        "competitor",
        frozenset({"competitor"}),
        PagePoint(150.75, 100.0),
        0.1,
    )
    common = {
        "stars": (owner, competitor),
        "associated_star_ids": frozenset({"owner"}),
        "target_source_id": "owner",
        "association_scale": 1.35,
    }
    blocked_score = score(blocked, **common)
    clear_score = score(clear, **common)
    assert blocked_score.label_competing_owner > clear_score.label_competing_owner
    assert clear_score.total(CostWeights()) < blocked_score.total(CostWeights())


def test_dso_owner_and_foreign_object_use_source_geometry() -> None:
    candidate = make_candidate(CompassPosition.E, 151.0, 99.0)
    owner = source("NGC1", 150.0, 100.0, 0.5)
    other = source("NGC2", 151.0, 100.0, 0.2)
    clear = score(candidate, target_source_id="NGC1", source_symbols=(owner,))
    ambiguous = score(
        candidate,
        target_source_id="NGC1",
        source_symbols=(owner, other),
    )
    assert ambiguous.label_foreign_object_proximity > clear.label_foreign_object_proximity
    assert ambiguous.label_competing_source_ambiguity > clear.label_competing_source_ambiguity


def test_dso_long_source_distance_has_nonlinear_penalty() -> None:
    owner = source("NGC1", 150.0, 100.0, 0.5)
    placement = DsoLabelPlacementStyle()
    near = LabelCandidate(
        id="label:dso:NGC1:N:near",
        position=CompassPosition.N,
        anchor=PagePoint(146.0, 96.7),
        bounds=PageRect(146.0, 96.7, 8.0, 2.5),
    )
    long = LabelCandidate(
        id="label:dso:NGC1:N:long",
        position=CompassPosition.N,
        anchor=PagePoint(146.0, 94.0),
        bounds=PageRect(146.0, 94.0, 8.0, 2.5),
    )
    near_cost = score(
        near,
        target_source_id="NGC1",
        source_symbols=(owner,),
        dso_placement=placement,
        is_dso_label=True,
    ).label_source_distance_mm
    long_cost = score(
        long,
        target_source_id="NGC1",
        source_symbols=(owner,),
        dso_placement=placement,
        is_dso_label=True,
    ).label_source_distance_mm
    assert long_cost > near_cost * 3.0


def test_contour_backed_dso_uses_source_facing_contour_edge() -> None:
    candidate = make_candidate(CompassPosition.W, 160.0, 99.0)
    circle = source("NGC1", 150.0, 100.0, 4.0)
    contour = SourceGeometry(
        id="NGC1",
        source_type=DsoType.BRIGHT_NEBULA,
        center=PagePoint(150.0, 100.0),
        radius_x_mm=4.0,
        radius_y_mm=4.0,
        outline_paths=((PagePoint(159.0, 98.0), PagePoint(159.0, 102.0)),),
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


def source(
    source_id: str,
    x_mm: float,
    y_mm: float,
    radius_mm: float,
    *,
    source_type: DsoType = DsoType.GALAXY,
    ignore_interior_stars: bool = False,
) -> SourceGeometry:
    return SourceGeometry(
        id=source_id,
        source_type=source_type,
        center=PagePoint(x_mm, y_mm),
        radius_x_mm=radius_mm,
        radius_y_mm=radius_mm,
        ignore_interior_stars=ignore_interior_stars,
    )


def test_faint_star_after_glyph_costs_more_than_equally_close_star_above() -> None:
    candidate = LabelCandidate(
        id="label:star:owner:E",
        position=CompassPosition.E,
        anchor=PagePoint(100.0, 100.0),
        bounds=PageRect(100.0, 100.0, 10.0, 3.0),
        glyph_bounds=(PageRect(108.0, 100.8, 1.0, 1.5),),
    )
    trailing = StarCircle("trailing", frozenset({"trailing"}), PagePoint(109.3, 101.5), 0.1)
    above = StarCircle("above", frozenset({"above"}), PagePoint(108.5, 100.5), 0.1)
    trailing_cost = score(
        candidate,
        stars=(trailing,),
        target_source_id="owner",
    ).label_glyph_proximity
    above_cost = score(
        candidate,
        stars=(above,),
        target_source_id="owner",
    ).label_glyph_proximity
    assert trailing_cost > above_cost


def test_competing_source_closer_than_owner_is_reported() -> None:
    candidate = make_candidate(CompassPosition.W, 154.0, 99.0)
    owner = source("owner", 150.0, 100.0, 0.5)
    competitor = source("competitor", 153.0, 100.0, 0.4)
    breakdown = score(
        candidate,
        target_source_id="owner",
        source_symbols=(owner, competitor),
    )
    assert breakdown.label_competing_owner > 0.0
    assert breakdown.competing_owner_id == "competitor"


def test_open_cluster_member_star_is_not_a_foreign_corridor_blocker() -> None:
    candidate = make_candidate(CompassPosition.W, 154.0, 99.0)
    cluster = source(
        "cluster",
        150.0,
        100.0,
        3.0,
        source_type=DsoType.OPEN_CLUSTER,
        ignore_interior_stars=True,
    )
    member = StarCircle("member", frozenset({"member"}), PagePoint(152.0, 100.0), 0.2)
    breakdown = score(
        candidate,
        stars=(member,),
        target_source_id="cluster",
        source_symbols=(cluster,),
    )
    assert breakdown.label_source_corridor == 0.0
    assert breakdown.label_competing_source_ambiguity == 0.0


def test_own_source_stays_preferred_in_dense_faint_field() -> None:
    near = make_candidate(CompassPosition.W, 151.0, 99.0)
    far = make_candidate(CompassPosition.W, 160.0, 99.0)
    owner = StarCircle("owner", frozenset({"owner"}), PagePoint(150.0, 100.0), 0.5)
    faint = tuple(
        StarCircle(
            f"faint:{index}",
            frozenset({f"faint:{index}"}),
            PagePoint(152.0 + index * 0.35, 98.5),
            0.1,
        )
        for index in range(5)
    )
    near_cost = score(
        near,
        stars=(owner, *faint),
        associated_star_ids=frozenset({"owner"}),
        target_source_id="owner",
    ).total(CostWeights())
    far_cost = score(
        far,
        stars=(owner, *faint),
        associated_star_ids=frozenset({"owner"}),
        target_source_id="owner",
    ).total(CostWeights())
    assert near_cost < far_cost


def test_single_star_source_geometry_remains_a_rendered_disk() -> None:
    candidate = make_candidate(CompassPosition.W, 151.0, 99.0)
    star = StarCircle("owner", frozenset({"owner"}), PagePoint(150.0, 100.0), 0.5)
    assert star_rect_edge_distance_mm(star, candidate.bounds) == pytest.approx(0.5)


def test_unresolved_double_uses_outer_marker_boundary_for_label_gap() -> None:
    candidate = make_candidate(CompassPosition.W, 152.5, 99.0)
    double = StarCircle(
        "system:close",
        frozenset({"A", "B"}),
        PagePoint(150.0, 100.0),
        0.5,
        system_ids=frozenset({"system:close"}),
        marker_length_mm=4.0,
        marker_line_width_mm=0.2,
    )
    breakdown = score(
        candidate,
        stars=(double,),
        associated_star_ids=frozenset({"A", "B"}),
        related_star_ids=frozenset({"A", "B"}),
        target_source_id="A",
    )
    assert star_rect_edge_distance_mm(double, candidate.bounds) == pytest.approx(0.4)
    assert breakdown.label_source_facing_edge_distance_mm == pytest.approx(0.4)


def test_resolved_double_system_uses_nearest_component_boundary() -> None:
    candidate = make_candidate(CompassPosition.W, 155.0, 99.0)
    primary = StarCircle(
        "A", frozenset({"A"}), PagePoint(150.0, 100.0), 0.5, frozenset({"system:wide"})
    )
    companion = StarCircle(
        "B", frozenset({"B"}), PagePoint(154.0, 100.0), 0.5, frozenset({"system:wide"})
    )
    breakdown = score(
        candidate,
        stars=(primary, companion),
        associated_star_ids=frozenset({"A", "B"}),
        related_star_ids=frozenset({"A", "B"}),
        target_source_id="system:wide",
    )
    assert breakdown.label_source_facing_edge_distance_mm == pytest.approx(0.5)


def test_same_system_companion_is_excluded_from_all_foreign_star_costs() -> None:
    candidate = LabelCandidate(
        id="label:star:A:W",
        position=CompassPosition.W,
        anchor=PagePoint(152.0, 99.0),
        bounds=PageRect(152.0, 99.0, 3.0, 2.5),
        glyph_bounds=(PageRect(152.0, 99.5, 1.0, 1.0),),
    )
    primary = StarCircle(
        "A", frozenset({"A"}), PagePoint(150.0, 100.0), 0.5, frozenset({"system:wide"})
    )
    companion = StarCircle(
        "B", frozenset({"B"}), PagePoint(151.2, 100.0), 0.2, frozenset({"system:wide"})
    )
    related = score(
        candidate,
        stars=(primary, companion),
        associated_star_ids=frozenset({"A"}),
        related_star_ids=frozenset({"A", "B"}),
        target_source_id="A",
    )
    unrelated = score(
        candidate,
        stars=(primary, companion),
        associated_star_ids=frozenset({"A"}),
        target_source_id="A",
    )
    assert related.label_foreign_star_clearance == 0.0
    assert related.label_glyph_proximity == 0.0
    assert related.label_source_corridor == 0.0
    assert related.label_competing_owner == 0.0
    assert unrelated.label_glyph_proximity > 0.0
    assert unrelated.label_competing_owner > 0.0


def test_component_label_keeps_its_component_as_the_source() -> None:
    candidate = make_candidate(CompassPosition.W, 151.0, 99.0)
    primary = StarCircle(
        "A", frozenset({"A"}), PagePoint(150.0, 100.0), 0.5, frozenset({"system:wide"})
    )
    companion = StarCircle(
        "B", frozenset({"B"}), PagePoint(154.0, 100.0), 0.5, frozenset({"system:wide"})
    )
    breakdown = score(
        candidate,
        stars=(primary, companion),
        associated_star_ids=frozenset({"A"}),
        related_star_ids=frozenset({"A", "B"}),
        target_source_id="A",
    )
    assert breakdown.label_source_facing_edge_distance_mm == pytest.approx(0.5)
