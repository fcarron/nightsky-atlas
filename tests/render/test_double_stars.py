"""Tests for the page-space double-star resolution."""

from __future__ import annotations

from dataclasses import replace
from math import hypot
from pathlib import Path

import pytest

from nightsky_atlas.atlas.config import StyleConfig, load_style_config
from nightsky_atlas.catalog.models import Provenance, Star
from nightsky_atlas.catalog.systems import (
    MatchStatus,
    StarSystem,
    combined_magnitude,
    match_star_systems,
)
from nightsky_atlas.catalog.tycho import iter_tycho2_stars
from nightsky_atlas.catalog.wds import iter_wds_systems
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.chart.page import PageRect, PageTransform
from nightsky_atlas.layout.collision import IssueType, find_hard_violations
from nightsky_atlas.layout.models import CompassPosition, Label, LabelCandidate
from nightsky_atlas.layout.optimizer import _star_circles, _target_anchors, optimize_labels
from nightsky_atlas.projection.base import ChartPoint
from nightsky_atlas.projection.stereographic import StereographicProjection
from nightsky_atlas.render.cairo import (
    _foreground_close_stars,
    _foreground_star_double_marks,
    _marked_double_star_members,
)
from nightsky_atlas.render.double_stars import (
    MapResolution,
    classify_map_resolution,
    printed_star_obstacles,
    related_member_star_ids,
    resolve_double_stars,
    source_member_star_ids,
)
from nightsky_atlas.render.symbols import StarSizeModel
from nightsky_atlas.scene.models import ChartScene, SceneStar, SceneStarSystem

REPO_ROOT = Path(__file__).resolve().parents[2]
STYLE = load_style_config(REPO_ROOT / "styles" / "standard.yaml")
PAGE = PageGeometry(width_mm=297.0, height_mm=210.0, margin_mm=12.0)
CHART = ChartDefinition(
    id="test-doubles",
    center_ra_deg=10.0,
    center_dec_deg=0.0,
    width_deg=20.0,
    height_deg=14.0,
)
TRANSFORM = PageTransform(chart=CHART, page=PAGE)


def make_star(star_id: str, magnitude: float) -> Star:
    return Star(
        id=star_id,
        ra_deg=10.0,
        dec_deg=0.0,
        magnitude=magnitude,
        provenance=Provenance(catalogue="TEST", source_id=star_id),
    )


def make_scene(
    *,
    component_eta_deg: float,
    status: MatchStatus = MatchStatus.POSITIONAL,
    component_star_id: str | None = "B",
    secondary_system: StarSystem | None = None,
    style: StyleConfig = STYLE,
    primary_magnitude: float = 6.0,
    component_magnitudes: tuple[float, ...] = (6.0, 8.0),
    combined_magnitude: float | None = 5.71,
) -> ChartScene:
    primary = make_star("A", primary_magnitude)
    stars = [SceneStar(primary, ChartPoint(0.0, 0.0))]
    component_ids: tuple[str, ...] = ()
    if component_star_id is not None:
        component = make_star(component_star_id, 8.0)
        stars.append(SceneStar(component, ChartPoint(component_eta_deg, 0.0)))
        component_ids = (component_star_id,)
    system = StarSystem(
        id="system:wds:CLOSE",
        source="wds",
        source_id="CLOSE",
        ra_deg=10.0,
        dec_deg=0.0,
        primary_star_id="A",
        component_star_ids=component_ids,
        component_magnitudes=component_magnitudes,
        combined_magnitude=combined_magnitude,
        separation_arcsec=2.0,
        position_angle_deg=90.0,
        match_status=status,
    )
    systems = [SceneStarSystem(system, ChartPoint(0.0, 0.0))]
    if component_star_id is not None:
        systems[0] = SceneStarSystem(
            system,
            ChartPoint(0.0, 0.0),
            component_points=(ChartPoint(component_eta_deg, 0.0),),
        )
    if secondary_system is not None:
        systems.append(SceneStarSystem(secondary_system, ChartPoint(0.0, 0.0)))
    return ChartScene(
        definition=CHART,
        stars=tuple(stars),
        star_systems=tuple(systems),
    )


def test_close_pair_uses_combined_magnitude_for_one_printed_star() -> None:
    scene = make_scene(component_eta_deg=0.01)
    marks = resolve_double_stars(scene, TRANSFORM, STYLE)
    assert len(marks) == 1
    assert marks[0].star_id == "A"
    assert marks[0].magnitude == pytest.approx(combined_magnitude((6.0, 8.0)))
    assert marks[0].suppress_star_ids == {"A", "B"}
    assert marks[0].pair_ids == ("system:wds:CLOSE",)


def test_close_pair_components_do_not_overpaint_their_own_marker() -> None:
    scene = make_scene(component_eta_deg=0.01)
    size_model = StarSizeModel.from_style(STYLE.star)
    marks = resolve_double_stars(scene, TRANSFORM, STYLE)
    members = _marked_double_star_members(scene, marks)

    assert members == {"A", "B"}
    assert _foreground_star_double_marks(
        scene, TRANSFORM, size_model, set(), marks, marked_members=members,
    ) == ((), ())
    assert _foreground_close_stars(
        scene, TRANSFORM, size_model, set(), excluded_foreground_ids=members,
    ) == ()


def test_mark_extends_existing_star_obstacle_in_optimizer_and_hard_gate() -> None:
    scene = make_scene(component_eta_deg=0.01, primary_magnitude=6.2)
    obstacles = printed_star_obstacles(scene, TRANSFORM, STYLE)
    assert {item.id for item in obstacles} == {"A"}
    obstacle = next(item for item in obstacles if item.id == "A")
    assert obstacle.star_ids == {"A", "B"}
    assert obstacle.marker_length_mm > 0.0
    model = StarSizeModel.from_style(STYLE.star)
    original_radius = model.radius_mm(6.2)
    assert obstacle.magnitude == pytest.approx(combined_magnitude((6.2, 8.0)))
    assert obstacle.disk_radius_mm == pytest.approx(model.radius_mm(obstacle.magnitude))
    assert obstacle.collision_radius_mm >= original_radius
    circles = _star_circles(scene, TRANSFORM, STYLE)
    assert len(circles) == 1
    assert circles[0].radius_mm == obstacle.disk_radius_mm
    assert _target_anchors((), scene, TRANSFORM, STYLE)["B"] == obstacle.page_point

    x = obstacle.page_point.x_mm + (original_radius + obstacle.collision_radius_mm) / 2.0
    bounds = PageRect(x, obstacle.page_point.y_mm - 0.05, 0.1, 0.1)
    candidate = LabelCandidate(
        id="label:near:N", position=CompassPosition.N,
        anchor=obstacle.page_point, bounds=bounds,
    )
    label = Label(
        id="label:near", target_id="A", text="X", priority=50,
        mandatory=True, candidates=(candidate,),
    )
    issues = find_hard_violations((label,), scene, TRANSFORM, STYLE)
    assert IssueType.LABEL_STAR in {issue.issue_type for issue in issues}


def test_wide_pair_is_left_separate() -> None:
    scene = make_scene(component_eta_deg=0.5)
    assert resolve_double_stars(scene, TRANSFORM, STYLE) == ()


def test_resolved_pair_keeps_shared_system_identity_for_layout() -> None:
    scene = make_scene(component_eta_deg=0.5)
    obstacles = printed_star_obstacles(scene, TRANSFORM, STYLE)
    assert {obstacle.id for obstacle in obstacles} == {"A", "B"}
    assert all(obstacle.system_ids == {"system:wds:CLOSE"} for obstacle in obstacles)
    assert source_member_star_ids("system:wds:CLOSE", obstacles) == {"A", "B"}
    assert related_member_star_ids("A", obstacles) == {"A", "B"}


def test_double_star_label_diagnostics_distinguish_resolved_and_unresolved_sources() -> None:
    resolved_scene = make_scene(component_eta_deg=0.5)
    resolved_primary = next(
        obstacle
        for obstacle in printed_star_obstacles(resolved_scene, TRANSFORM, STYLE)
        if obstacle.id == "A"
    )
    resolved_candidate = LabelCandidate(
        id="label:star:A:W",
        position=CompassPosition.W,
        anchor=resolved_primary.page_point,
        bounds=PageRect(
            resolved_primary.page_point.x_mm + 2.0,
            resolved_primary.page_point.y_mm - 1.0,
            2.0,
            2.0,
        ),
    )
    resolved_label = Label(
        id="label:star:A",
        target_id="A",
        text="A",
        priority=50,
        mandatory=True,
        candidates=(resolved_candidate,),
    )
    resolved = optimize_labels((resolved_label,), resolved_scene, TRANSFORM, STYLE)
    resolved_diagnostic = resolved.label_diagnostics[resolved_label.id]
    assert resolved_diagnostic["star_source_type"] == "resolved_double_component"
    assert resolved_diagnostic["same_system_components_excluded"] is True

    unresolved_scene = make_scene(component_eta_deg=0.01)
    unresolved_primary = printed_star_obstacles(unresolved_scene, TRANSFORM, STYLE)[0]
    unresolved_candidate = LabelCandidate(
        id="label:star:A:N",
        position=CompassPosition.N,
        anchor=unresolved_primary.page_point,
        bounds=PageRect(
            unresolved_primary.page_point.x_mm + 2.0,
            unresolved_primary.page_point.y_mm - 1.0,
            2.0,
            2.0,
        ),
    )
    unresolved_label = Label(
        id="label:star:A",
        target_id="A",
        text="A",
        priority=50,
        mandatory=True,
        candidates=(unresolved_candidate,),
    )
    unresolved = optimize_labels((unresolved_label,), unresolved_scene, TRANSFORM, STYLE)
    unresolved_diagnostic = unresolved.label_diagnostics[unresolved_label.id]
    assert unresolved_diagnostic["star_source_type"] == "unresolved_double"
    assert unresolved_diagnostic["source_envelope_component_count"] == 1.0


def test_unsafe_match_never_marks() -> None:
    scene = make_scene(component_eta_deg=0.01, status=MatchStatus.AMBIGUOUS)
    assert resolve_double_stars(scene, TRANSFORM, STYLE) == ()


def test_disabled_style_never_marks() -> None:
    style = STYLE.model_copy(
        update={"double_stars": STYLE.double_stars.model_copy(update={"enabled": False})}
    )
    scene = make_scene(component_eta_deg=0.01)
    assert resolve_double_stars(scene, TRANSFORM, style) == ()


def test_map_resolution_uses_glyph_radii_and_configured_clearances() -> None:
    assert classify_map_resolution(1.15, 0.5, 0.5, STYLE) is MapResolution.UNRESOLVED
    assert classify_map_resolution(1.8, 0.5, 0.5, STYLE) is MapResolution.MARGINAL
    assert classify_map_resolution(2.0, 0.5, 0.5, STYLE) is MapResolution.RESOLVED


def test_unlinked_companion_uses_catalogue_separation_without_inventing_star() -> None:
    # No component star in the catalogue: the WDS separation (2 arcsec) maps to
    # a tiny page distance, so the primary still carries a marker.
    scene = make_scene(component_eta_deg=0.01, component_star_id=None)
    marks = resolve_double_stars(scene, TRANSFORM, STYLE)
    assert len(marks) == 1
    assert marks[0].star_id == "A"
    assert marks[0].magnitude == pytest.approx(combined_magnitude((6.0, 8.0)))


def test_unrendered_component_does_not_replace_primary_marker_anchor() -> None:
    primary = SceneStar(make_star("A", 6.0), ChartPoint(0.0, 0.0))
    system = StarSystem(
        id="system:wds:UNRENDERED",
        source="wds",
        source_id="UNRENDERED",
        ra_deg=10.0,
        dec_deg=0.0,
        primary_star_id="A",
        component_star_ids=("B",),
        component_magnitudes=(6.0, 7.0),
        combined_magnitude=5.53,
        separation_arcsec=2.0,
        match_status=MatchStatus.POSITIONAL,
    )
    scene = ChartScene(
        definition=CHART,
        stars=(primary,),
        star_systems=(SceneStarSystem(system, ChartPoint(0.0, 0.0)),),
    )

    marks = resolve_double_stars(scene, TRANSFORM, STYLE)

    assert len(marks) == 1
    assert marks[0].star_id == "A"
    assert marks[0].magnitude == pytest.approx(combined_magnitude((6.0, 7.0)))


def test_one_marker_per_star_aggregates_hierarchical_wds_relations() -> None:
    without_companion = StarSystem(
        id="system:wds:INNER",
        source="wds",
        source_id="INNER",
        ra_deg=10.0,
        dec_deg=0.0,
        primary_star_id="A",
        separation_arcsec=1.0,
        component_magnitudes=(6.0, 7.0),
        combined_magnitude=5.32,
        match_status=MatchStatus.POSITIONAL,
    )
    scene = make_scene(component_eta_deg=0.01, secondary_system=without_companion)
    marks = resolve_double_stars(scene, TRANSFORM, STYLE)
    assert len(marks) == 1
    assert marks[0].star_id == "A"
    assert len(marks[0].pair_ids) == 2
    assert marks[0].magnitude == pytest.approx(combined_magnitude((6.0, 8.0, 7.0)))


def test_marker_length_scales_with_star_size() -> None:
    bright_scene = make_scene(
        component_eta_deg=0.01, primary_magnitude=3.0, combined_magnitude=3.0
    )
    faint_scene = make_scene(
        component_eta_deg=0.01, primary_magnitude=8.5, combined_magnitude=8.5
    )
    bright = resolve_double_stars(bright_scene, TRANSFORM, STYLE)[0]
    faint = resolve_double_stars(faint_scene, TRANSFORM, STYLE)[0]
    assert bright.marker_length_mm > faint.marker_length_mm
    assert faint.marker_length_mm >= STYLE.double_stars.min_marker_length_mm


def test_faint_unplotted_companion_is_not_marked() -> None:
    scene = make_scene(
        component_eta_deg=0.01,
        component_star_id=None,
        component_magnitudes=(8.0, 12.0),
        combined_magnitude=7.9,
    )
    assert resolve_double_stars(scene, TRANSFORM, STYLE) == ()


def test_missing_secondary_magnitude_does_not_pass_profile_selection() -> None:
    scene = make_scene(
        component_eta_deg=0.01,
        component_magnitudes=(),
        combined_magnitude=None,
    )
    assert resolve_double_stars(scene, TRANSFORM, STYLE) == ()


def make_pair_scene(specs: list[tuple[str, str, float, float]]) -> ChartScene:
    """Build a scene where several WDS records share primary ``A``."""
    stars = [SceneStar(make_star("A", 6.0), ChartPoint(0.0, 0.0))]
    systems = []
    for system_id, star_id, eta_deg, magnitude in specs:
        stars.append(SceneStar(make_star(star_id, magnitude), ChartPoint(eta_deg, 0.0)))
        system = StarSystem(
            id=f"system:wds:{system_id}",
            source="wds",
            source_id=system_id,
            ra_deg=10.0,
            dec_deg=0.0,
            primary_star_id="A",
            component_star_ids=(star_id,),
            component_magnitudes=(6.0, magnitude),
            separation_arcsec=eta_deg * 3600.0,
            combined_magnitude=None,
            match_status=MatchStatus.POSITIONAL,
        )
        systems.append(
            SceneStarSystem(
                system,
                ChartPoint(0.0, 0.0),
                component_points=(ChartPoint(eta_deg, 0.0),),
            )
        )
    return ChartScene(
        definition=CHART, stars=tuple(stars), star_systems=tuple(systems)
    )


def test_all_close_companions_of_one_primary_make_one_marker() -> None:
    scene = make_pair_scene([("CLOSE", "B", 0.01, 8.0), ("OTHER", "C", 0.02, 8.0)])
    marks = resolve_double_stars(scene, TRANSFORM, STYLE)
    assert len(marks) == 1
    assert marks[0].star_id == "A"
    assert len(marks[0].pair_ids) == 2


def test_wide_pair_is_not_marked_beside_a_close_pair() -> None:
    scene = make_pair_scene([("CLOSE", "B", 0.01, 8.0), ("WIDE", "C", 0.5, 8.0)])
    marks = resolve_double_stars(scene, TRANSFORM, STYLE)
    assert len(marks) == 1
    assert marks[0].star_id == "A"
    assert marks[0].pair_ids == ("system:wds:CLOSE",)


def test_connected_close_records_mark_each_rendered_primary_once() -> None:
    stars = (
        SceneStar(make_star("A", 6.0), ChartPoint(0.0, 0.0)),
        SceneStar(make_star("B", 5.0), ChartPoint(0.01, 0.0)),
        SceneStar(make_star("C", 7.0), ChartPoint(0.02, 0.0)),
    )
    first = StarSystem(
        id="system:wds:A-B",
        source="wds",
        source_id="A-B",
        ra_deg=10.0,
        dec_deg=0.0,
        primary_star_id="A",
        component_star_ids=("B",),
        component_magnitudes=(6.0, 5.0),
        separation_arcsec=36.0,
        match_status=MatchStatus.POSITIONAL,
    )
    second = StarSystem(
        id="system:wds:B-C",
        source="wds",
        source_id="B-C",
        ra_deg=10.0,
        dec_deg=0.0,
        primary_star_id="B",
        component_star_ids=("C",),
        component_magnitudes=(5.0, 7.0),
        separation_arcsec=36.0,
        match_status=MatchStatus.POSITIONAL,
    )
    scene = ChartScene(
        definition=CHART,
        stars=stars,
        star_systems=(
            SceneStarSystem(
                first, ChartPoint(0.0, 0.0), component_points=(ChartPoint(0.01, 0.0),)
            ),
            SceneStarSystem(
                second, ChartPoint(0.01, 0.0), component_points=(ChartPoint(0.02, 0.0),)
            ),
        ),
    )

    marks = resolve_double_stars(scene, TRANSFORM, STYLE)

    assert len(marks) == 2
    assert {mark.star_id for mark in marks} == {"A", "B"}
    assert next(mark for mark in marks if mark.star_id == "A").page_point == TRANSFORM.to_page(
        ChartPoint(0.0, 0.0)
    )


def test_epsilon_lyrae_hierarchy_changes_with_print_scale() -> None:
    deep_style = load_style_config(REPO_ROOT / "styles" / "deep.yaml")
    fixture = REPO_ROOT / "data" / "fixtures" / "double_stars" / "wds_subset.dat"
    raw_systems = {system.source_id: system for system in iter_wds_systems(fixture)}
    stars = tuple(
        SceneStar(make_star(star_id, magnitude), ChartPoint(x, 0.0))
        for star_id, magnitude, x in (
            ("eps1", 5.15, 0.0),
            ("eps1b", 6.10, 2.1 / 3600.0),
            ("eps2", 5.25, 209.4 / 3600.0),
            ("eps2b", 5.38, (209.4 + 2.4) / 3600.0),
        )
    )
    systems = (
        replace(
            raw_systems["STF2382:AB"], primary_star_id="eps1",
            component_star_ids=("eps1b",), match_status=MatchStatus.POSITIONAL,
        ),
        replace(
            raw_systems["STF2383:CD"], primary_star_id="eps2",
            component_star_ids=("eps2b",), match_status=MatchStatus.POSITIONAL,
        ),
        replace(
            raw_systems["STFA37:AB,CD"], primary_star_id="eps1",
            component_star_ids=("eps2",), match_status=MatchStatus.POSITIONAL,
        ),
    )
    scene = ChartScene(
        definition=CHART,
        stars=stars,
        star_systems=tuple(
            SceneStarSystem(system, ChartPoint(0.0, 0.0)) for system in systems
        ),
    )

    large_chart = ChartDefinition(
        id="epsilon-large-scale", center_ra_deg=10.0, center_dec_deg=0.0,
        width_deg=4.0, height_deg=3.0,
    )
    large_transform = PageTransform(large_chart, PAGE, scale_mm_per_degree=60.0)
    large_marks = resolve_double_stars(scene, large_transform, deep_style)
    by_star = {mark.star_id: mark for mark in large_marks}
    assert set(by_star) == {"eps1", "eps2"}
    assert by_star["eps1"].pair_ids == ("system:wds:STF2382:AB",)
    assert by_star["eps2"].pair_ids == ("system:wds:STF2383:CD",)

    small_transform = PageTransform(CHART, PAGE, scale_mm_per_degree=10.0)
    small_marks = resolve_double_stars(scene, small_transform, deep_style)
    eps1_mark = next(mark for mark in small_marks if mark.star_id == "eps1")
    assert "system:wds:STFA37:AB,CD" in eps1_mark.pair_ids


def test_real_epsilon_lyrae_has_two_pocket_double_marks_at_combined_magnitude() -> None:
    pocket_style = load_style_config(REPO_ROOT / "styles" / "pocket.yaml")
    tycho_fixture = REPO_ROOT / "data" / "fixtures" / "tycho2" / "epsilon_lyrae.dat"
    wds_fixture = REPO_ROOT / "data" / "fixtures" / "double_stars" / "wds_subset.dat"
    stars = tuple(iter_tycho2_stars([tycho_fixture]))
    systems = match_star_systems(
        (
            system for system in iter_wds_systems(wds_fixture)
            if system.source_id in {"STF2382:AB", "STF2383:CD"}
        ),
        stars,
    )
    chart = ChartDefinition(
        id="epsilon-pocket", center_ra_deg=281.09, center_dec_deg=39.64,
        width_deg=4.0, height_deg=4.0,
    )
    projection = StereographicProjection(chart.center_ra_deg, chart.center_dec_deg)
    scene = ChartScene(
        definition=chart,
        stars=tuple(
            SceneStar(star, projection.project(star.ra_deg, star.dec_deg))
            for star in stars
        ),
        star_systems=tuple(
            SceneStarSystem(system, projection.project(system.ra_deg, system.dec_deg))
            for system in systems
            if system.ra_deg is not None and system.dec_deg is not None
        ),
    )
    transform = PageTransform(chart, PAGE, scale_mm_per_degree=5.0)

    marks = resolve_double_stars(scene, transform, pocket_style)

    assert {mark.star_id for mark in marks} == {
        "TYC 3122-3438-2", "TYC 3122-3439-1",
    }
    assert {mark.pair_ids for mark in marks} == {
        ("system:wds:STF2382:AB",), ("system:wds:STF2383:CD",),
    }
    assert hypot(
        marks[0].page_point.x_mm - marks[1].page_point.x_mm,
        marks[0].page_point.y_mm - marks[1].page_point.y_mm,
    ) == pytest.approx(0.29, abs=0.02)
    size_model = StarSizeModel.from_style(pocket_style.star)
    star_by_id = {star.id: star for star in stars}
    expected_pairs = {
        "TYC 3122-3438-2": ("TYC 3122-3438-1",),
        "TYC 3122-3439-1": ("TYC 3122-3439-2",),
    }
    assert {mark.star_id: mark.suppress_star_ids for mark in marks} == {
        primary: {primary, *companions} for primary, companions in expected_pairs.items()
    }
    for mark in marks:
        expected_magnitude = combined_magnitude(
            star_by_id[star_id].magnitude
            for star_id in (mark.star_id, *expected_pairs[mark.star_id])
        )
        assert mark.magnitude == pytest.approx(expected_magnitude)
        assert size_model.diameter_mm(mark.magnitude) > size_model.diameter_mm(
            star_by_id[mark.star_id].magnitude
        )
    assert all(mark.marker_length_mm >= 1.7 for mark in marks)
    obstacles = printed_star_obstacles(scene, transform, pocket_style)
    assert len(obstacles) == 2
    obstacle_by_id = {obstacle.id: obstacle for obstacle in obstacles}
    for mark in marks:
        assert obstacle_by_id[mark.star_id].disk_radius_mm == pytest.approx(
            size_model.radius_mm(mark.magnitude)
        )
