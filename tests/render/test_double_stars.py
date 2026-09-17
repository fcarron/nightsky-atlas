"""Tests for the page-space double-star resolution."""

from __future__ import annotations

from pathlib import Path

from nightsky_atlas.atlas.config import StyleConfig, load_style_config
from nightsky_atlas.catalog.models import Provenance, Star
from nightsky_atlas.catalog.systems import MatchStatus, StarSystem
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.chart.page import PageTransform
from nightsky_atlas.projection.base import ChartPoint
from nightsky_atlas.render.double_stars import resolve_double_stars
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
