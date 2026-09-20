"""Tests for scene construction."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from nightsky_atlas.catalog.constellations import ConstellationSegment
from nightsky_atlas.catalog.models import DeepSkyObject, DsoType, Provenance, Star
from nightsky_atlas.catalog.outlines import NebulaOutline
from nightsky_atlas.catalog.sample import load_sample_stars
from nightsky_atlas.catalog.selection import SelectionPolicy
from nightsky_atlas.catalog.systems import MatchStatus, StarSystem
from nightsky_atlas.chart.models import ChartDefinition
from nightsky_atlas.projection import ChartPoint, StereographicProjection
from nightsky_atlas.scene.builder import build_scene, build_star_scene

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "data" / "fixtures" / "stars" / "test_virgo.csv"

DEFINITION = ChartDefinition(
    id="test-virgo",
    center_ra_deg=187.5,
    center_dec_deg=12.0,
    width_deg=20.0,
    height_deg=14.0,
)

INSIDE_IDS = {f"star-00{index}" for index in range(1, 9)}
OUTSIDE_IDS = {"star-009", "star-010", "star-011", "star-012"}


def build_fixture_scene():
    return build_star_scene(DEFINITION, load_sample_stars(FIXTURE))


def test_known_fixture_star_count() -> None:
    assert build_fixture_scene().star_count == 8


def test_off_chart_stars_excluded() -> None:
    placed = {scene_star.star.id for scene_star in build_fixture_scene().stars}
    assert placed == INSIDE_IDS
    assert placed.isdisjoint(OUTSIDE_IDS)


def test_center_star_projects_to_chart_origin() -> None:
    scene = build_fixture_scene()
    center = next(item for item in scene.stars if item.star.id == "star-001")
    assert center.chart_point.xi_deg == pytest.approx(0.0, abs=1e-9)
    assert center.chart_point.eta_deg == pytest.approx(0.0, abs=1e-9)


def test_projected_positions_match_direction() -> None:
    scene = build_fixture_scene()
    by_id = {item.star.id: item.chart_point for item in scene.stars}
    assert by_id["star-003"].xi_deg > 0.0
    assert by_id["star-003"].eta_deg > 0.0
    assert by_id["star-002"].xi_deg < 0.0
    assert by_id["star-002"].eta_deg < 0.0


def test_all_projected_points_in_field() -> None:
    for scene_star in build_fixture_scene().stars:
        assert DEFINITION.contains(scene_star.chart_point)


def test_empty_input_gives_empty_scene() -> None:
    scene = build_star_scene(DEFINITION, [])
    assert scene.star_count == 0
    assert scene.definition == DEFINITION


def test_point_at_field_corner_is_inside() -> None:
    assert DEFINITION.contains(ChartPoint(10.0, 7.0))
    assert not DEFINITION.contains(ChartPoint(10.1, 7.0))


def make_dso(
    object_id: str, ra_deg: float, dec_deg: float, magnitude: float | None
) -> DeepSkyObject:
    return DeepSkyObject(
        id=object_id,
        ra_deg=ra_deg,
        dec_deg=dec_deg,
        object_type=DsoType.GALAXY,
        provenance=Provenance(catalogue="TEST", source_id=object_id),
        magnitude=magnitude,
    )


def test_build_scene_includes_only_in_field_dsos() -> None:
    dsos = [
        make_dso("d-in", 187.5, 12.0, 8.0),
        make_dso("d-out", 100.0, 40.0, 8.0),
    ]
    scene = build_scene(DEFINITION, (), dsos)
    assert scene.dso_count == 1
    assert scene.deep_sky_objects[0].dso.id == "d-in"


def test_dso_magnitude_limit_keeps_unknown_magnitudes() -> None:
    dsos = [
        make_dso("bright", 187.5, 12.0, 8.0),
        make_dso("faint", 187.6, 12.0, 14.0),
        make_dso("unknown", 187.7, 12.0, None),
    ]
    scene = build_scene(DEFINITION, (), dsos, dso_magnitude_limit=12.0)
    assert {item.dso.id for item in scene.deep_sky_objects} == {"bright", "unknown"}


def make_segment(
    ra1_deg: float, dec1_deg: float, ra2_deg: float, dec2_deg: float
) -> ConstellationSegment:
    return ConstellationSegment(
        id=f"seg:{ra1_deg}:{dec1_deg}:{ra2_deg}:{dec2_deg}",
        ra1_deg=ra1_deg,
        dec1_deg=dec1_deg,
        ra2_deg=ra2_deg,
        dec2_deg=dec2_deg,
        provenance=Provenance(catalogue="TEST", source_id="seg"),
    )


def test_constellation_segment_inside_field_is_clipped() -> None:
    segment = ConstellationSegment(
        id="seg:Vir",
        ra1_deg=170.0,
        dec1_deg=12.0,
        ra2_deg=205.0,
        dec2_deg=12.0,
        provenance=Provenance(catalogue="TEST", source_id="seg"),
        constellation_id="Vir",
    )
    scene = build_scene(DEFINITION, [], [], constellation_lines=[segment])
    assert len(scene.constellation_lines) == 1
    assert scene.constellation_lines[0].constellation_id == "Vir"
    for point in scene.constellation_lines[0].points:
        assert DEFINITION.contains(point)


def test_constellation_segment_far_away_is_excluded() -> None:
    segment = make_segment(0.0, -50.0, 20.0, -50.0)
    scene = build_scene(DEFINITION, [], [], constellation_lines=[segment])
    assert scene.constellation_lines == ()


def test_constellation_boundaries_tracked_separately() -> None:
    boundary = make_segment(175.0, 12.0, 200.0, 12.0)
    line = make_segment(178.0, 10.0, 190.0, 10.0)
    scene = build_scene(
        DEFINITION, [], [], constellation_lines=[line], constellation_boundaries=[boundary]
    )
    assert len(scene.constellation_boundaries) == 1
    assert len(scene.constellation_lines) == 1


REGION_CASES = [
    ("equator", 30.0, 0.0, 20.0, 0.0, 40.0, 0.0),
    ("mid", 187.5, 45.0, 178.0, 42.0, 198.0, 47.0),
    ("north-pole", 90.0, 82.0, 70.0, 85.0, 110.0, 85.0),
    ("south-pole", 90.0, -82.0, 70.0, -85.0, 110.0, -85.0),
    ("long", 90.0, 0.0, 40.0, -20.0, 140.0, 20.0),
]


@pytest.mark.parametrize("label,center_ra,center_dec,ra1,dec1,ra2,dec2", REGION_CASES)
def test_constellation_line_is_a_straight_two_point_segment(
    label: str,
    center_ra: float,
    center_dec: float,
    ra1: float,
    dec1: float,
    ra2: float,
    dec2: float,
) -> None:
    definition = ChartDefinition(
        id=label,
        center_ra_deg=center_ra,
        center_dec_deg=center_dec,
        width_deg=27.0,
        height_deg=18.5,
    )
    segment = make_segment(ra1, dec1, ra2, dec2)
    scene = build_scene(definition, [], [], constellation_lines=[segment])
    assert scene.constellation_lines
    for line in scene.constellation_lines:
        assert len(line.points) == 2
        for point in line.points:
            assert definition.contains(point)


def test_constellation_line_projects_only_endpoints() -> None:
    definition = ChartDefinition(
        id="eq", center_ra_deg=30.0, center_dec_deg=0.0, width_deg=27.0, height_deg=18.5
    )
    segment = make_segment(20.0, 0.0, 40.0, 0.0)
    scene = build_scene(definition, [], [], constellation_lines=[segment])
    line = scene.constellation_lines[0]
    projector = StereographicProjection(30.0, 0.0)
    start = projector.project(20.0, 0.0)
    end = projector.project(40.0, 0.0)
    assert line.points[0].xi_deg == pytest.approx(start.xi_deg)
    assert line.points[0].eta_deg == pytest.approx(start.eta_deg)
    assert line.points[1].xi_deg == pytest.approx(end.xi_deg)
    assert line.points[1].eta_deg == pytest.approx(end.eta_deg)


def test_polar_constellation_line_does_not_follow_the_curved_parallel() -> None:
    definition = ChartDefinition(
        id="np", center_ra_deg=90.0, center_dec_deg=82.0, width_deg=27.0, height_deg=18.5
    )
    segment = make_segment(60.0, 85.0, 120.0, 85.0)
    scene = build_scene(definition, [], [], constellation_lines=[segment])
    line = scene.constellation_lines[0]
    assert len(line.points) == 2
    projector = StereographicProjection(90.0, 82.0)
    parallel_mid = projector.project(90.0, 85.0)
    chord_mid_eta = (line.points[0].eta_deg + line.points[1].eta_deg) / 2.0
    assert abs(parallel_mid.eta_deg - chord_mid_eta) > 0.5


def test_constellation_boundary_is_still_densified_and_curved() -> None:
    definition = ChartDefinition(
        id="eq", center_ra_deg=30.0, center_dec_deg=0.0, width_deg=27.0, height_deg=18.5
    )
    boundary = make_segment(10.0, 0.0, 50.0, 0.0)
    scene = build_scene(definition, [], [], constellation_boundaries=[boundary])
    assert scene.constellation_boundaries
    assert all(len(run.points) > 2 for run in scene.constellation_boundaries)


def make_outline(dso_id: str, points: tuple[tuple[float, float], ...]) -> NebulaOutline:
    return NebulaOutline(
        id=f"outline:dso:{dso_id}",
        dso_id=dso_id,
        points=points,
        provenance=Provenance(catalogue="TEST", source_id=dso_id),
    )


def test_outline_inside_field_is_closed() -> None:
    outline = make_outline(
        "NGC7000",
        ((186.5, 11.0), (188.5, 11.0), (188.5, 13.0), (186.5, 13.0)),
    )
    scene = build_scene(
        DEFINITION, [], [make_dso("NGC7000", 187.5, 12.0, 8.0)], nebula_outlines=[outline]
    )
    assert scene.outline_count == 1
    ring = scene.nebula_outlines[0]
    assert ring.dso_id == "NGC7000"
    assert ring.points[0] == ring.points[-1]
    for point in ring.points:
        assert DEFINITION.contains(point)


def test_outline_far_away_is_excluded() -> None:
    outline = make_outline(
        "FAR",
        ((0.0, -50.0), (2.0, -50.0), (2.0, -48.0)),
    )
    scene = build_scene(
        DEFINITION, [], [make_dso("FAR", 187.5, 12.0, 8.0)], nebula_outlines=[outline]
    )
    assert scene.nebula_outlines == ()


def test_outline_partly_outside_field_is_clipped() -> None:
    outline = make_outline(
        "BIG",
        ((186.5, 10.0), (188.5, 10.0), (188.5, 20.0), (186.5, 20.0)),
    )
    scene = build_scene(
        DEFINITION, [], [make_dso("BIG", 187.5, 12.0, 8.0)], nebula_outlines=[outline]
    )
    assert scene.outline_count >= 1
    for run in scene.nebula_outlines:
        for point in run.points:
            assert DEFINITION.contains(point)


def test_outline_follows_dso_visibility() -> None:
    outline = make_outline(
        "NGC7000", ((186.5, 11.0), (188.5, 11.0), (188.5, 13.0))
    )
    dso = make_dso("NGC7000", 187.5, 12.0, 12.0)
    hidden = build_scene(
        DEFINITION, [], [dso], dso_magnitude_limit=10.0, nebula_outlines=[outline]
    )
    visible = build_scene(
        DEFINITION, [], [dso], dso_magnitude_limit=13.0, nebula_outlines=[outline]
    )
    assert hidden.deep_sky_objects == ()
    assert hidden.nebula_outlines == ()
    assert visible.dso_count == 1
    assert visible.outline_count == 1


def test_selected_outline_can_cross_chart_without_dso_center_inside() -> None:
    outline = make_outline(
        "EDGE", ((186.5, 11.0), (188.5, 11.0), (188.5, 13.0))
    )
    dso = make_dso("EDGE", 210.0, 12.0, 8.0)
    scene = build_scene(DEFINITION, [], [dso], nebula_outlines=[outline])
    assert scene.dso_count == 0
    assert scene.outline_count == 1


def test_outline_alias_suppresses_only_its_nebula_fallback_symbol() -> None:
    nebula = DeepSkyObject(
        id="NGC7000",
        ra_deg=187.5,
        dec_deg=12.0,
        object_type=DsoType.BRIGHT_NEBULA,
        provenance=Provenance(catalogue="TEST", source_id="NGC7000"),
        cross_ids=("C 020",),
    )
    galaxy = DeepSkyObject(
        id="NGC7001",
        ra_deg=188.0,
        dec_deg=12.0,
        object_type=DsoType.GALAXY,
        provenance=Provenance(catalogue="TEST", source_id="NGC7001"),
    )
    outlines = (
        make_outline("C020", ((186.5, 11.0), (188.5, 11.0), (188.5, 13.0))),
        make_outline("NGC7001", ((187.5, 11.0), (188.5, 11.0), (188.5, 13.0))),
    )
    scene = build_scene(DEFINITION, (), (nebula, galaxy), nebula_outlines=outlines)

    by_id = {item.dso.id: item for item in scene.deep_sky_objects}
    assert by_id["NGC7000"].symbol_visible is False
    assert by_id["NGC7001"].symbol_visible is True
    assert {outline.dso_id for outline in scene.nebula_outlines} == {"NGC7000", "NGC7001"}


def test_supernova_remnant_outline_is_solid_and_suppresses_fallback_symbol() -> None:
    remnant = DeepSkyObject(
        id="NGC6960",
        ra_deg=187.5,
        dec_deg=12.0,
        object_type=DsoType.SUPERNOVA_REMNANT,
        provenance=Provenance(catalogue="TEST", source_id="NGC6960"),
    )
    outlines = (
        make_outline("NGC6960", ((186.5, 11.0), (188.5, 11.0), (188.5, 13.0))),
        make_outline("NGC6960", ((186.5, 12.5), (188.5, 12.5), (188.5, 13.5))),
    )
    scene = build_scene(DEFINITION, (), (remnant,), nebula_outlines=outlines)

    assert scene.deep_sky_objects[0].symbol_visible is False
    assert len(scene.nebula_outlines) == 2
    assert all(not outline.dashed for outline in scene.nebula_outlines)


@pytest.mark.parametrize("object_type", (DsoType.BRIGHT_NEBULA, DsoType.SUPERNOVA_REMNANT))
def test_bright_nebula_and_supernova_remnant_outlines_are_solid(object_type: DsoType) -> None:
    dso = DeepSkyObject(
        id="NGC7000",
        ra_deg=187.5,
        dec_deg=12.0,
        object_type=object_type,
        provenance=Provenance(catalogue="TEST", source_id="NGC7000"),
    )
    scene = build_scene(
        DEFINITION,
        (),
        (dso,),
        nebula_outlines=(
            make_outline("NGC7000", ((186.5, 11.0), (188.5, 11.0), (188.5, 13.0))),
        ),
    )

    assert scene.nebula_outlines[0].dashed is False


def test_dark_nebula_outline_is_dashed() -> None:
    dso = DeepSkyObject(
        id="B168",
        ra_deg=187.5,
        dec_deg=12.0,
        object_type=DsoType.DARK_NEBULA,
        provenance=Provenance(catalogue="TEST", source_id="B168"),
    )
    scene = build_scene(
        DEFINITION,
        (),
        (dso,),
        nebula_outlines=(
            make_outline("B168", ((186.5, 11.0), (188.5, 11.0), (188.5, 13.0))),
        ),
    )

    assert scene.nebula_outlines[0].dashed is True


FORCED_POLICY = SelectionPolicy(forced_lists=frozenset({"herschel400"}))
OBSERVING_INDEX = {"NGC869": frozenset({"herschel400"})}


def test_forced_observing_list_bypasses_magnitude_limit() -> None:
    dso = make_dso("NGC0869", 187.5, 12.0, 15.0)
    scene = build_scene(
        DEFINITION,
        (),
        [dso],
        dso_magnitude_limit=12.0,
        observing_index=OBSERVING_INDEX,
        selection_policy=FORCED_POLICY,
    )
    assert scene.dso_count == 1
    metadata = scene.deep_sky_objects[0].metadata
    assert metadata is not None
    assert metadata.forced is True
    assert metadata.list_memberships == {"herschel400"}


def test_non_member_faint_dso_is_still_excluded() -> None:
    dsos = [
        make_dso("NGC0869", 187.5, 12.0, 15.0),
        make_dso("NGC9999", 187.6, 12.0, 15.0),
    ]
    scene = build_scene(
        DEFINITION,
        (),
        dsos,
        dso_magnitude_limit=12.0,
        observing_index=OBSERVING_INDEX,
        selection_policy=FORCED_POLICY,
    )
    assert {item.dso.id for item in scene.deep_sky_objects} == {"NGC0869"}
    assert scene.deep_sky_objects[0].metadata is not None


def test_scene_without_policy_has_no_metadata() -> None:
    scene = build_scene(DEFINITION, (), [make_dso("d-in", 187.5, 12.0, 8.0)])
    assert scene.deep_sky_objects[0].metadata is None


def test_policy_keeps_surface_bright_object_beyond_magnitude_limit() -> None:
    galaxy = make_dso("NGC9998", 187.5, 12.0, 13.8)
    galaxy = replace(
        galaxy,
        major_axis_arcmin=1.5,
        minor_axis_arcmin=1.5,
    )
    policy = SelectionPolicy()
    scene = build_scene(
        DEFINITION,
        (),
        [galaxy],
        dso_magnitude_limit=12.0,
        selection_policy=policy,
    )
    assert scene.dso_count == 1
    metadata = scene.deep_sky_objects[0].metadata
    assert metadata is not None
    assert metadata.visible is True


def test_policy_excludes_star_typed_objects() -> None:
    star_entry = replace(make_dso("STAR1", 187.5, 12.0, 6.0), object_type=DsoType.STAR)
    scene = build_scene(
        DEFINITION,
        (),
        [star_entry],
        selection_policy=SelectionPolicy(),
    )
    assert scene.dso_count == 0


def make_star(star_id: str, ra_deg: float, dec_deg: float, magnitude: float) -> Star:
    return Star(
        id=star_id,
        ra_deg=ra_deg,
        dec_deg=dec_deg,
        magnitude=magnitude,
        provenance=Provenance(catalogue="TEST", source_id=star_id),
    )


def make_system(primary_star_id: str | None, *, status: MatchStatus) -> StarSystem:
    return StarSystem(
        id="system:wds:TEST",
        source="wds",
        source_id="TEST",
        ra_deg=187.5,
        dec_deg=12.0,
        primary_star_id=primary_star_id,
        component_star_ids=("star-002",) if primary_star_id else (),
        match_status=status,
    )


def test_safe_star_system_is_projected_into_the_scene() -> None:
    stars = load_sample_stars(FIXTURE)
    scene = build_scene(
        DEFINITION,
        stars,
        star_systems=[make_system("star-001", status=MatchStatus.POSITIONAL)],
    )
    assert scene.star_system_count == 1
    scene_system = scene.star_systems[0]
    assert scene_system.system.primary_star_id == "star-001"
    assert len(scene_system.component_points) == 1


def test_unsafe_star_system_is_not_added_to_the_scene() -> None:
    stars = load_sample_stars(FIXTURE)
    scene = build_scene(
        DEFINITION,
        stars,
        star_systems=[make_system("star-001", status=MatchStatus.AMBIGUOUS)],
    )
    assert scene.star_system_count == 0


def test_star_system_outside_the_chart_is_excluded() -> None:
    outside = StarSystem(
        id="system:wds:OUT",
        source="wds",
        source_id="OUT",
        ra_deg=100.0,
        dec_deg=-40.0,
        primary_star_id="star-001",
        match_status=MatchStatus.POSITIONAL,
    )
    scene = build_scene(DEFINITION, [], star_systems=[outside])
    assert scene.star_system_count == 0
