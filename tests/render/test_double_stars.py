"""Tests for the page-space double-star resolution."""

from __future__ import annotations

from pathlib import Path

from nightsky_atlas.atlas.config import StyleConfig, load_style_config
from nightsky_atlas.catalog.models import Provenance, Star
from nightsky_atlas.catalog.systems import MatchStatus, StarSystem
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.chart.page import PageRect, PageTransform
from nightsky_atlas.layout.collision import IssueType, find_hard_violations
from nightsky_atlas.layout.models import CompassPosition, Label, LabelCandidate
from nightsky_atlas.layout.optimizer import _star_circles, _target_anchors
from nightsky_atlas.projection.base import ChartPoint
from nightsky_atlas.render.double_stars import printed_star_obstacles, resolve_double_stars
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


def test_close_pair_collapses_to_one_marker() -> None:
    scene = make_scene(component_eta_deg=0.01)
    marks = resolve_double_stars(scene, TRANSFORM, STYLE)
    assert len(marks) == 1
    assert marks[0].suppress_star_ids == {"A", "B"}
    assert marks[0].magnitude == 5.71


def test_collapsed_pair_uses_printed_extent_in_optimizer_and_hard_gate() -> None:
    scene = make_scene(component_eta_deg=0.01, primary_magnitude=6.2)
    obstacle, = printed_star_obstacles(scene, TRANSFORM, STYLE)
    assert obstacle.star_ids == {"A", "B"}
    assert obstacle.magnitude < 6.0
    original_radius = StarSizeModel.from_style(STYLE.star).radius_mm(6.2)
    assert obstacle.collision_radius_mm > original_radius
    circles = _star_circles(scene, TRANSFORM, STYLE)
    assert len(circles) == 1
    assert circles[0].radius_mm == obstacle.collision_radius_mm
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


def test_unsafe_match_never_marks() -> None:
    scene = make_scene(component_eta_deg=0.01, status=MatchStatus.AMBIGUOUS)
    assert resolve_double_stars(scene, TRANSFORM, STYLE) == ()


def test_disabled_style_never_marks() -> None:
    style = STYLE.model_copy(
        update={"double_stars": STYLE.double_stars.model_copy(update={"enabled": False})}
    )
    scene = make_scene(component_eta_deg=0.01)
    assert resolve_double_stars(scene, TRANSFORM, style) == ()


def test_unlinked_companion_falls_back_to_catalogue_separation() -> None:
    # No component star in the catalogue: the WDS separation (2 arcsec) maps to
    # a tiny page distance, so the primary still carries a marker.
    scene = make_scene(component_eta_deg=0.01, component_star_id=None)
    marks = resolve_double_stars(scene, TRANSFORM, STYLE)
    assert len(marks) == 1
    assert marks[0].suppress_star_ids == {"A"}
    assert marks[0].magnitude == 5.71


def test_unrendered_component_never_becomes_a_marker_anchor() -> None:
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
    assert marks[0].suppress_star_ids == {"A"}
    assert marks[0].magnitude == 5.53


def test_one_marker_per_star_prefers_a_linked_companion() -> None:
    without_companion = StarSystem(
        id="system:wds:INNER",
        source="wds",
        source_id="INNER",
        ra_deg=10.0,
        dec_deg=0.0,
        primary_star_id="A",
        separation_arcsec=0.2,
        component_magnitudes=(6.0, 7.0),
        combined_magnitude=5.32,
        match_status=MatchStatus.POSITIONAL,
    )
    scene = make_scene(component_eta_deg=0.01, secondary_system=without_companion)
    marks = resolve_double_stars(scene, TRANSFORM, STYLE)
    assert len(marks) == 1
    assert marks[0].suppress_star_ids == {"A", "B"}


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


def test_plotted_companion_is_marked_even_without_magnitudes() -> None:
    scene = make_scene(
        component_eta_deg=0.01,
        component_magnitudes=(),
        combined_magnitude=None,
    )
    marks = resolve_double_stars(scene, TRANSFORM, STYLE)
    assert len(marks) == 1


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


def test_all_close_companions_of_one_primary_collapse_together() -> None:
    scene = make_pair_scene([("CLOSE", "B", 0.01, 8.0), ("OTHER", "C", 0.02, 8.0)])
    marks = resolve_double_stars(scene, TRANSFORM, STYLE)
    assert len(marks) == 1
    assert marks[0].suppress_star_ids == {"A", "B", "C"}


def test_wide_companion_is_left_plotted_beside_a_close_pair() -> None:
    # A-B is unseparable, A-C is separable: C must stay a real star while the
    # close pair collapses (per-pair decision, AGENTS.md section 12).
    scene = make_pair_scene([("CLOSE", "B", 0.01, 8.0), ("WIDE", "C", 0.5, 8.0)])
    marks = resolve_double_stars(scene, TRANSFORM, STYLE)
    assert len(marks) == 1
    assert marks[0].suppress_star_ids == {"A", "B"}


def test_connected_close_records_with_different_primaries_make_one_marker() -> None:
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

    assert len(marks) == 1
    assert marks[0].suppress_star_ids == {"A", "B", "C"}
    assert marks[0].page_point == TRANSFORM.to_page(ChartPoint(0.01, 0.0))
