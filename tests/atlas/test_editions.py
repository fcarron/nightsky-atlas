"""Edition presets share physical print styling while changing sky scale."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from nightsky_atlas.atlas.config import (
    AtlasConfig,
    DetailChartConfig,
    load_atlas_config,
    load_style_config,
)
from nightsky_atlas.atlas.detail_geometry import (
    detail_chart_contains_position,
    detail_chart_overlaps_main_chart,
    detail_chart_parent_ids,
)
from nightsky_atlas.atlas.tiling import (
    TilingSpec,
    chart_definitions,
    coverage_report,
    neighbour_overlap_report,
    resolve_ring_counts,
)
from nightsky_atlas.build.atlas import (
    _detail_scene,
    _detail_style,
    _exclude_star_labels,
    _profile_config_path,
    _style_with_star_profile,
)
from nightsky_atlas.build.chart import build_chart_context, load_chart_inputs
from nightsky_atlas.catalog.star_names import hip_number, load_star_names
from nightsky_atlas.chart.models import ChartDefinition
from nightsky_atlas.chart.page import PageTransform
from nightsky_atlas.chart.presentation import presentation_from_edition
from nightsky_atlas.layout.labels import build_labels
from nightsky_atlas.layout.optimizer import optimize_labels
from nightsky_atlas.layout.selection import select_labels
from nightsky_atlas.projection.base import ProjectionError
from nightsky_atlas.projection.stereographic import StereographicProjection
from nightsky_atlas.render.detail_markers import build_detail_marker
from nightsky_atlas.render.symbols import StarSizeModel

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("edition", "code", "stellar_limit", "scale_bar"),
    (
        ("pocket", "P", 7.5, 10.0),
        ("standard", "S", 9.0, 5.0),
        ("deep", "D", 10.5, 2.0),
    ),
)
def test_edition_presets_load_with_expected_scale_and_codes(
    edition: str, code: str, stellar_limit: float, scale_bar: float
) -> None:
    atlas = load_atlas_config(ROOT / "atlas" / f"{edition}.yaml")
    style = load_style_config(ROOT / "styles" / f"{edition}.yaml")
    chart = chart_definitions(atlas)[0]
    assert atlas.resolved_edition().code == code
    assert atlas.stellar_limit_magnitude == stellar_limit
    assert style.furniture.scale_bar.length_deg == scale_bar
    assert style.furniture.scale_bar.enabled is False
    expected_code = f"{code}01" if edition == "pocket" else f"{code}001"
    assert presentation_from_edition(chart, atlas.resolved_edition()).chart_code == expected_code


def test_star_label_exclusions_are_pocket_only_stable_hip_ids() -> None:
    pocket = load_atlas_config(ROOT / "atlas" / "pocket.yaml")
    assert pocket.exclude_star_labels == (17702, 17847)
    for edition in ("standard", "deep"):
        assert load_atlas_config(ROOT / "atlas" / f"{edition}.yaml").exclude_star_labels == ()


def test_pocket_p15_excludes_two_names_but_keeps_star_symbols() -> None:
    atlas_path = ROOT / "atlas" / "pocket.yaml"
    style_path = ROOT / "styles" / "pocket.yaml"
    atlas = load_atlas_config(atlas_path)
    definition = next(chart for chart in chart_definitions(atlas) if chart.id == "pocket-015")
    context = build_chart_context(
        atlas_path=atlas_path,
        style_path=style_path,
        definition=definition,
        star_store=ROOT / "data" / "processed" / "stars" / "tycho2.sqlite",
    )
    names = load_star_names()
    labels = build_labels(context.scene, context.transform, context.style, names)
    excluded_label_ids = {
        label.id
        for label in labels
        if label.target_id
        in {
            item.star.id
            for item in context.scene.stars
            if hip_number(item.star.hip_id) in {17702, 17847}
        }
    }
    assert len(excluded_label_ids) == 2

    remaining, records = _exclude_star_labels(labels, context.scene, atlas.exclude_star_labels)
    assert not {label.text for label in remaining} & {"Alcyone", "Atlas"}
    assert {record["hip_id"] for record in records} == {"HIP 17702", "HIP 17847"}
    assert {record["label_id"] for record in records} == excluded_label_ids
    assert {
        item.star.hip_id for item in context.scene.stars
    } >= {"HIP 17702", "HIP 17847"}


def test_deep_magnitude_10_5_uses_a_smaller_printable_faint_star() -> None:
    style = load_style_config(ROOT / "styles" / "deep.yaml")
    sizes = StarSizeModel.from_style(style.star)
    assert style.star.faint_magnitude == 10.5
    assert sizes.diameter_mm(10.0) == pytest.approx(0.35)
    assert sizes.diameter_mm(10.5) == pytest.approx(0.25)


def test_physical_print_style_is_shared_across_editions() -> None:
    standard = load_style_config(ROOT / "styles" / "standard.yaml")
    for edition in ("pocket", "deep"):
        style = load_style_config(ROOT / "styles" / f"{edition}.yaml")
        assert style.label.font_size_pt == standard.label.font_size_pt
        assert style.label.dso_labels.normal_size_pt == standard.label.dso_labels.normal_size_pt
        assert style.grid.line_width_mm == standard.grid.line_width_mm
        assert style.grid.label_padding_mm == standard.grid.label_padding_mm
        assert style.constellation.lines.line_width_mm == standard.constellation.lines.line_width_mm
        assert style.furniture.navigation.font_size_pt == standard.furniture.navigation.font_size_pt


def test_pocket_overlap_is_mm_derived() -> None:
    pocket = load_atlas_config(ROOT / "atlas" / "pocket.yaml")
    spec = TilingSpec.from_config(pocket.tiling)
    assert spec.overlap_deg == pytest.approx(10.0 / pocket.tiling.mm_per_degree)


def test_pocket_labels_named_stars_through_magnitude_5_5() -> None:
    style = load_style_config(ROOT / "styles" / "pocket.yaml")
    assert style.star.label_magnitude_limit == pytest.approx(5.5)
    assert style.label.star_labels.bayer.max_magnitude == pytest.approx(5.5)


def test_pocket_symmetric_navigation_tiling() -> None:
    pocket = load_atlas_config(ROOT / "atlas" / "pocket.yaml")
    spec = TilingSpec.from_config(pocket.tiling)
    assert spec.declination_centers == (-62.0, -33.0, 0.0, 33.0, 62.0)
    assert spec.coverage_step_deg == 0.25
    assert resolve_ring_counts(spec) == (5, 9, 9, 9, 5)
    charts = chart_definitions(pocket)
    assert len(charts) == 39
    assert coverage_report(charts, step_deg=0.25).covers_all
    assert neighbour_overlap_report(charts, step_deg=0.5).is_complete
    by_dec: dict[float, list[float]] = {}
    for chart in charts:
        by_dec.setdefault(chart.center_dec_deg, []).append(chart.center_ra_deg)
    for dec in (-62.0, -33.0, 0.0, 33.0, 62.0):
        count = 5 if abs(dec) == 62.0 else 9
        expected = [(12.0 - index * 360.0 / count) % 360.0 for index in range(count)]
        assert by_dec[dec] == pytest.approx(expected)
    assert by_dec[-62.0] == pytest.approx(by_dec[62.0])
    assert by_dec[-33.0] == pytest.approx(by_dec[33.0])
    detail = pocket.detail_charts[0]
    assert detail.code == "PD01"
    parent_ids = detail_chart_parent_ids((detail,), charts)[detail.id]
    assert {"pocket-020", "pocket-021"} <= set(parent_ids)


def test_pocket_39_tiling_covers_transition_lines_and_chart_corners() -> None:
    charts = chart_definitions(load_atlas_config(ROOT / "atlas" / "pocket.yaml"))

    def covering_count(ra_deg: float, dec_deg: float) -> int:
        covered = 0
        for chart in charts:
            try:
                point = StereographicProjection(chart.center_ra_deg, chart.center_dec_deg).project(
                    ra_deg, dec_deg
                )
            except ProjectionError:
                continue
            covered += (
                abs(point.xi_deg) <= chart.width_deg / 2.0 + 1e-8
                and abs(point.eta_deg) <= chart.height_deg / 2.0 + 1e-8
            )
        return covered

    critical_decs = (
        -50.005,
        -50.0,
        -49.995,
        -72.16,
        -72.15,
        -72.14,
        -16.505,
        -16.5,
        -16.495,
        16.495,
        16.5,
        16.505,
        72.14,
        72.15,
        72.16,
        49.995,
        50.0,
        50.005,
    )
    for dec in critical_decs:
        for ra in range(0, 360, 2):
            assert covering_count(float(ra), dec) >= 1, (ra, dec)
        for ra in (0.0, 0.001, 359.999, 140.2, 219.8):
            assert covering_count(ra, dec) >= 1, (ra, dec)

    for chart in charts:
        projection = StereographicProjection(chart.center_ra_deg, chart.center_dec_deg)
        for xi in (-chart.width_deg / 2, chart.width_deg / 2):
            for eta in (-chart.height_deg / 2, chart.height_deg / 2):
                ra, dec = projection.inverse(xi, eta)
                assert covering_count(ra, dec) >= 1, (chart.id, xi, eta, ra, dec)


def test_pocket_constellation_boundaries_are_distinct_from_grid_and_figures() -> None:
    pocket = load_style_config(ROOT / "styles" / "pocket.yaml")
    standard = load_style_config(ROOT / "styles" / "standard.yaml")
    boundary = pocket.constellation.boundaries
    assert boundary.enabled
    assert boundary.line_width_mm == pytest.approx(0.12)
    assert boundary.gray == pytest.approx(0.68)
    assert boundary.gray < pocket.grid.gray
    assert boundary.gray > pocket.constellation.lines.gray
    assert pocket.constellation.lines.gray == pytest.approx(0.64)
    assert pocket.constellation.lines.bold_width_mm == pytest.approx(0.18)
    assert pocket.constellation.lines.normal_width_mm == pytest.approx(0.12)
    assert pocket.constellation.lines.thin_width_mm == pytest.approx(0.08)
    assert pocket.grid.gray == standard.grid.gray
    assert pocket.grid.line_width_mm == standard.grid.line_width_mm


def test_deep_tiling_uses_aligned_rings_with_polar_caps() -> None:
    standard = load_atlas_config(ROOT / "atlas" / "standard.yaml")
    deep = load_atlas_config(ROOT / "atlas" / "deep.yaml")
    assert deep.tiling.polar_caps is True
    assert deep.tiling.stagger_ra_centers is False
    assert deep.tiling.auto_adjust_counts is False
    assert deep.tiling.declination_centers
    assert standard.tiling.target_overlap.vertical_deg == pytest.approx(3.0)
    assert standard.tiling.target_overlap.horizontal_min_deg == pytest.approx(3.0)
    assert deep.tiling.target_overlap.vertical_deg == pytest.approx(1.5)
    assert deep.tiling.target_overlap.horizontal_min_deg == pytest.approx(1.0)
    spec = TilingSpec.from_config(deep.tiling)
    assert spec.is_ring_mode


def test_detail_charts_use_stable_codes_supported_scales_and_edition_stars() -> None:
    standard = load_atlas_config(ROOT / "atlas" / "standard.yaml")
    pocket = load_atlas_config(ROOT / "atlas" / "pocket.yaml")
    deep = load_atlas_config(ROOT / "atlas" / "deep.yaml")
    details = standard.detail_charts
    assert len(chart_definitions(standard)) == 129
    assert [detail.code for detail in pocket.detail_charts] == ["PD01", "PD02"]
    assert [detail.code for detail in details] == [f"SD{i:02d}" for i in range(1, 10)]
    assert [detail.code for detail in deep.detail_charts] == [f"DD{i:02d}" for i in range(1, 10)]
    assert all(
        not hasattr(detail, "fallback_parent_galaxy_labels")
        and not hasattr(detail, "parent_chart_id")
        for detail in (*pocket.detail_charts, *details, *deep.detail_charts)
    )
    assert {detail.name for detail in details} >= {
        "Virgo Cluster",
        "Sagittarius clusters · M22 / M28",
        "Cygnus nebula field",
        "Orion Nebula · M42",
        "Perseus Double Cluster",
        "Pleiades · M45",
    }
    assert [detail.mm_per_degree for detail in details] == [20, 80, 40, 40, 20, 20, 20, 20, 20]
    assert [detail.star_profile for detail in details] == [
        "deep",
        "eyepiece_deep",
        "eyepiece",
        "eyepiece",
        "deep",
        "deep",
        "deep",
        "deep",
        "deep",
    ]
    assert [detail.mm_per_degree for detail in deep.detail_charts] == [
        40,
        40,
        80,
        80,
        80,
        40,
        80,
        80,
        40,
    ]
    assert [detail.star_profile for detail in deep.detail_charts] == [
        "eyepiece",
        "eyepiece",
        "eyepiece_deep",
        "eyepiece_deep",
        "eyepiece_deep",
        "eyepiece",
        "eyepiece_deep",
        "eyepiece_deep",
        "eyepiece",
    ]
    assert pocket.detail_charts[0].mm_per_degree == 20.0
    assert pocket.detail_charts[0].star_profile == "deep"
    assert pocket.detail_charts[1].name == "Pleiades · M45"
    assert pocket.detail_charts[1].mm_per_degree == 40.0
    assert pocket.detail_charts[1].star_profile == "eyepiece"
    assert pocket.detail_charts[1].stars.magnitude_limit == pytest.approx(11.25)
    assert pocket.detail_charts[1].stars.include_ucac4 is True
    assert pocket.detail_charts[1].stars.named_labels == (
        17489,
        17499,
        17531,
        17573,
        17608,
        17702,
        17847,
        17851,
    )
    assert pocket.detail_charts[1].show_constellation_names is False
    assert pocket.detail_charts[1].objects["Mel022"].show_symbol is False
    assert pocket.detail_charts[1].objects["Mel022"].show_label is True
    for detail in (*pocket.detail_charts, *details, *deep.detail_charts):
        assert detail.mm_per_degree in {20.0, 40.0, 80.0}
        assert detail.width_deg * detail.mm_per_degree <= 260.0
        assert detail.height_deg * detail.mm_per_degree <= 170.0
    assert deep.stellar_limit_magnitude == 10.5

    for atlas in (pocket, standard, deep):
        charts = tuple(chart_definitions(atlas))
        relations = detail_chart_parent_ids(atlas.detail_charts, charts)
        assert all(relations[detail.id] for detail in atlas.detail_charts)
        assert all(
            chart_id in {chart.id for chart in charts}
            for parent_ids in relations.values()
            for chart_id in parent_ids
        )


def test_detail_chart_rejects_intermediate_scales() -> None:
    with pytest.raises(ValueError, match="scale must be 10, 20, 40 or 80"):
        DetailChartConfig(
            id="detail-test",
            code="SD99",
            name="Test field",
            center_ra_deg=0.0,
            center_dec_deg=0.0,
            width_deg=4.0,
            height_deg=3.0,
            mm_per_degree=60.0,
        )


def test_pocket_detail_scale_requires_matching_stellar_profile() -> None:
    pocket = load_atlas_config(ROOT / "atlas" / "pocket.yaml")
    raw = pocket.model_dump()
    detail = raw["detail_charts"][0]

    detail["mm_per_degree"] = 10.0
    detail["width_deg"] = 26.0
    detail["height_deg"] = 17.0
    detail["star_profile"] = "standard"
    AtlasConfig.model_validate(raw)

    detail["mm_per_degree"] = 20.0
    detail["width_deg"] = 13.0
    detail["height_deg"] = 8.5
    detail["star_profile"] = "deep"
    AtlasConfig.model_validate(raw)

    detail["mm_per_degree"] = 40.0
    detail["width_deg"] = 6.5
    detail["height_deg"] = 4.25
    detail["star_profile"] = "eyepiece"
    AtlasConfig.model_validate(raw)

    detail["star_profile"] = "deep"
    with pytest.raises(ValueError, match="must use the 'eyepiece' star profile"):
        AtlasConfig.model_validate(raw)

    detail["mm_per_degree"] = 10.0
    detail["width_deg"] = 26.0
    detail["height_deg"] = 17.0
    detail["star_profile"] = "deep"
    with pytest.raises(ValueError, match="must use the 'standard' star profile"):
        AtlasConfig.model_validate(raw)


def test_detail_overrides_inherit_style_and_control_pleiades_layers() -> None:
    atlas_path = ROOT / "atlas" / "pocket.yaml"
    style_path = ROOT / "styles" / "pocket.yaml"
    atlas = load_atlas_config(atlas_path)
    detail = atlas.detail_charts[1]
    parent_style = load_style_config(style_path)
    eyepiece_style = load_style_config(ROOT / "styles" / "eyepiece.yaml")
    detail_style = _detail_style(
        detail, _style_with_star_profile(parent_style, eyepiece_style)
    )
    assert detail_style.star.faint_magnitude == eyepiece_style.star.faint_magnitude
    assert detail_style.dso == parent_style.dso
    assert detail_style.constellation.names.enabled is False
    assert detail_style.constellation.lines.enabled == parent_style.constellation.lines.enabled
    assert (
        detail_style.constellation.boundaries.enabled
        == parent_style.constellation.boundaries.enabled
    )
    independent_layers = _detail_style(
        detail.model_copy(
            update={
                "show_constellation_figures": False,
                "show_constellation_boundaries": True,
            }
        ),
        _style_with_star_profile(parent_style, eyepiece_style),
    )
    assert independent_layers.constellation.lines.enabled is False
    assert independent_layers.constellation.boundaries.enabled is True

    context = build_chart_context(
        atlas_path=atlas_path,
        style_path=style_path,
        definition=detail.to_definition(atlas_id=atlas.id),
        star_store=ROOT / "data" / "processed" / "stars" / "tycho2.sqlite",
        faint_star_store=ROOT / "data" / "processed" / "stars" / "faint_stars.sqlite",
        faint_star_limit=11.25,
        magnitude_limit=11.25,
        scale_mm_per_degree=detail.mm_per_degree,
        allow_faint_star_supplement=True,
    )
    scene = _detail_scene(detail, context.scene)
    assert context.transform.mm_per_deg == pytest.approx(40.0)
    assert all(item.star.magnitude <= 11.25 for item in scene.stars)
    assert any(item.star.id.startswith("UCAC4-") for item in scene.stars)
    primary = [item.star for item in scene.stars if not item.star.id.startswith("UCAC4-")]
    ucac4 = [item.star for item in scene.stars if item.star.id.startswith("UCAC4-")]
    for faint_star in ucac4:
        for primary_star in primary:
            mean_dec = math.radians((faint_star.dec_deg + primary_star.dec_deg) / 2.0)
            delta_ra = (faint_star.ra_deg - primary_star.ra_deg) * math.cos(mean_dec)
            delta_dec = faint_star.dec_deg - primary_star.dec_deg
            assert math.hypot(delta_ra, delta_dec) * 3600.0 >= 3.0
    by_id = {item.dso.id: item for item in scene.deep_sky_objects}
    assert by_id["Mel022"].symbol_visible is False
    assert by_id["Mel022"].label_visible is True

    labels = build_labels(
        scene,
        context.transform,
        detail_style,
        load_star_names(),
        required_star_hips=detail.stars.named_labels,
    )
    labels = select_labels(labels, scene, context.transform, detail_style)
    labels = optimize_labels(labels, scene, context.transform, detail_style).labels
    pleiades_names = {
        "Alcyone",
        "Atlas",
        "Electra",
        "Maia",
        "Merope",
        "Taygeta",
        "Pleione",
        "Celaeno",
    }
    forced = [label for label in labels if label.text in pleiades_names]
    assert {label.text for label in forced} == pleiades_names
    assert all(label.mandatory for label in forced)
    assert all(not label.hidden and label.effective_candidate() is not None for label in forced)
    assert any(label.id == "label:dso:Mel022" for label in labels)
    assert not any(label.id == "label:constellation:TAU" for label in labels)


def test_detail_profile_uses_shared_star_profile_with_experimental_style() -> None:
    profile = _profile_config_path(
        ROOT / "styles" / "experiments" / "color" / "pocket-c.yaml", "eyepiece"
    )
    assert profile == ROOT / "styles" / "eyepiece.yaml"


def test_standard_tiling_has_eleven_aligned_symmetric_rings() -> None:
    standard = load_atlas_config(ROOT / "atlas" / "standard.yaml")
    spec = TilingSpec.from_config(standard.tiling)
    assert spec.declination_centers == (
        -75.0,
        -60.0,
        -45.0,
        -30.0,
        -15.0,
        0.0,
        15.0,
        30.0,
        45.0,
        60.0,
        75.0,
    )
    assert spec.stagger_ra_centers is False
    assert spec.ra_offset_deg == pytest.approx(12.0)
    assert spec.auto_adjust_counts is False
    assert resolve_ring_counts(spec) == (5, 10, 11, 15, 15, 15, 15, 15, 11, 10, 5)
    charts = chart_definitions(standard)
    assert len(charts) == 129
    by_dec: dict[float, list[float]] = {}
    for chart in charts:
        by_dec.setdefault(chart.center_dec_deg, []).append(chart.center_ra_deg)
    for dec, count in zip(spec.declination_centers, spec.chart_counts, strict=True):
        assert by_dec[dec] == pytest.approx(
            [(12.0 - i * 360.0 / count) % 360.0 for i in range(count)]
        )
    for dec in (15.0, 30.0, 45.0, 60.0, 75.0):
        assert by_dec[-dec] == pytest.approx(by_dec[dec])
    assert coverage_report(charts, step_deg=0.5).covers_all
    assert neighbour_overlap_report(charts, step_deg=1.0).is_complete


def test_deep_experimental_tiling_has_23_aligned_symmetric_rings() -> None:
    deep = load_atlas_config(ROOT / "atlas" / "deep.yaml")
    spec = TilingSpec.from_config(deep.tiling)
    expected_centers = (
        -83.0,
        -75.0,
        -67.5,
        -60.0,
        -53.0,
        -45.0,
        -37.5,
        -30.0,
        -22.5,
        -15.0,
        -7.5,
        0.0,
        7.5,
        15.0,
        22.5,
        30.0,
        37.5,
        45.0,
        53.0,
        60.0,
        67.5,
        75.0,
        83.0,
    )
    expected_counts = (
        5,
        10,
        15,
        15,
        20,
        25,
        25,
        25,
        30,
        30,
        30,
        30,
        30,
        30,
        30,
        25,
        25,
        25,
        20,
        15,
        15,
        10,
        5,
    )
    assert spec.declination_centers == expected_centers
    assert spec.chart_counts == expected_counts
    assert spec.declination_centers[11] == 0.0
    assert spec.polar_caps is True
    assert spec.stagger_ra_centers is False
    assert spec.ra_offset_deg == pytest.approx(0.0)
    assert spec.auto_adjust_counts is False
    assert expected_centers == tuple(-dec for dec in reversed(expected_centers))
    assert expected_counts == tuple(reversed(expected_counts))

    charts = chart_definitions(deep)
    assert len(charts) == 492
    assert charts[0].id == "deep-001"
    assert charts[0].center_dec_deg == 90.0
    assert charts[-1].center_dec_deg == -90.0
    by_dec: dict[float, list[float]] = {}
    for chart in charts:
        by_dec.setdefault(chart.center_dec_deg, []).append(chart.center_ra_deg)
    for dec, count in zip(expected_centers, expected_counts, strict=True):
        assert by_dec[dec] == pytest.approx(
            [(-index * 360.0 / count) % 360.0 for index in range(count)]
        )
    for dec in expected_centers[11:]:
        assert by_dec[-dec] == pytest.approx(by_dec[dec])

    standard = load_atlas_config(ROOT / "atlas" / "standard.yaml")
    standard_by_dec: dict[float, list[float]] = {}
    for chart in chart_definitions(standard):
        if abs(chart.center_dec_deg) < 89.0:
            standard_by_dec.setdefault(chart.center_dec_deg, []).append(chart.center_ra_deg)
    assert set(standard_by_dec[0.0]) <= set(by_dec[0.0])

    assert coverage_report(charts, step_deg=0.25).covers_all
    assert neighbour_overlap_report(charts, step_deg=0.25).is_complete
    deep_relations = detail_chart_parent_ids(deep.detail_charts, charts)
    assert all(deep_relations[detail.id] for detail in deep.detail_charts)


def test_detail_star_profiles_preserve_parent_dso_styling_and_limit() -> None:
    standard_style = load_style_config(ROOT / "styles" / "standard.yaml")
    for profile_name in ("deep", "eyepiece", "eyepiece_deep"):
        profile_style = load_style_config(ROOT / "styles" / f"{profile_name}.yaml")
        profile_atlas = load_atlas_config(ROOT / "atlas" / f"{profile_name}.yaml")
        detail_style = _style_with_star_profile(standard_style, profile_style)
        assert profile_atlas.stellar_limit_magnitude == profile_style.star.faint_magnitude
        assert detail_style.star == profile_style.star
        assert detail_style.double_stars == profile_style.double_stars
        assert detail_style.label.star_labels == profile_style.label.star_labels
        assert detail_style.dso == standard_style.dso
        assert detail_style.label.dso_labels == standard_style.label.dso_labels


def test_standard_detail_star_depth_does_not_change_dso_selection() -> None:
    atlas_path = ROOT / "atlas" / "standard.yaml"
    style_path = ROOT / "styles" / "standard.yaml"
    atlas = load_atlas_config(atlas_path)
    style = load_style_config(style_path)
    inputs = load_chart_inputs(
        atlas_path=atlas_path,
        style_path=style_path,
        atlas=atlas,
        style=style,
    )
    detail = next(detail for detail in atlas.detail_charts if detail.code == "SD02")
    definition = detail.to_definition(atlas_id=atlas.id)

    selected_ids = []
    for stellar_limit in (10.5, 13.5):
        context = build_chart_context(
            atlas_path=atlas_path,
            style_path=style_path,
            definition=definition,
            magnitude_limit=stellar_limit,
            scale_mm_per_degree=detail.mm_per_degree,
            inputs=inputs,
        )
        selected_ids.append(tuple(item.dso.id for item in context.scene.deep_sky_objects))
        assert context.selection_policy == inputs.selection_policy

    assert selected_ids[0] == selected_ids[1]


def test_standard_detail_markers_project_into_their_parent_charts() -> None:
    standard = load_atlas_config(ROOT / "atlas" / "standard.yaml")
    chart_list = tuple(chart_definitions(standard))
    charts = {chart.id: chart for chart in chart_list}
    relations = detail_chart_parent_ids(standard.detail_charts, chart_list)
    for detail in standard.detail_charts:
        assert relations[detail.id]
        for chart_id in relations[detail.id]:
            parent = charts[chart_id]
            transform = PageTransform(
                chart=parent,
                page=standard.page.to_geometry(),
                scale_mm_per_degree=standard.mm_per_degree,
            )
            marker = build_detail_marker(detail, parent, transform)
            assert marker is not None
            assert marker.chart_code == detail.code
            assert marker.label == detail.name
            assert len(marker.boundary) == 128
            assert all(
                math.isfinite(point.x_mm) and math.isfinite(point.y_mm) for point in marker.boundary
            )
            frame = transform.chart_rect
            assert all(
                frame.left_mm - 1e-9 <= point.x_mm <= frame.right_mm + 1e-9
                and frame.top_mm - 1e-9 <= point.y_mm <= frame.bottom_mm + 1e-9
                for point in marker.visible_boundary
            )


def test_pocket_detail_chart_has_all_geometric_main_chart_relations() -> None:
    pocket = load_atlas_config(ROOT / "atlas" / "pocket.yaml")
    charts = tuple(chart_definitions(pocket))
    detail = pocket.detail_charts[0]

    parent_ids = detail_chart_parent_ids((detail,), charts)[detail.id]

    assert "pocket-020" in parent_ids
    assert "pocket-021" in parent_ids
    for chart_id in parent_ids:
        chart = next(item for item in charts if item.id == chart_id)
        overlap = detail_chart_overlaps_main_chart(detail, chart)
        assert overlap is not None
        assert overlap.area_deg2 > 0.01
        transform = PageTransform(chart, pocket.page.to_geometry(), pocket.mm_per_degree)
        marker = build_detail_marker(detail, chart, transform)
        assert marker is not None
        assert marker.chart_code == detail.code
        assert all(
            transform.chart_rect.left_mm <= point.x_mm <= transform.chart_rect.right_mm
            and transform.chart_rect.top_mm <= point.y_mm <= transform.chart_rect.bottom_mm
            for point in marker.visible_boundary
        )


def test_detail_chart_geometry_handles_ra_wrap_and_rejects_edge_only_contact() -> None:
    detail = DetailChartConfig(
        id="detail-wrap",
        code="PD99",
        name="Wrap field",
        center_ra_deg=359.8,
        center_dec_deg=0.0,
        width_deg=4.0,
        height_deg=2.0,
        mm_per_degree=20.0,
    )
    wrap_chart = ChartDefinition(
        id="wrap-main",
        center_ra_deg=0.0,
        center_dec_deg=0.0,
        width_deg=10.0,
        height_deg=6.0,
    )
    opposite_chart = ChartDefinition(
        id="opposite",
        center_ra_deg=180.0,
        center_dec_deg=0.0,
        width_deg=10.0,
        height_deg=6.0,
    )
    touching_chart = ChartDefinition(
        id="touching",
        center_ra_deg=364.8,
        center_dec_deg=0.0,
        width_deg=6.0,
        height_deg=2.0,
    )

    assert detail_chart_contains_position(detail, 0.1, 0.0)
    assert not detail_chart_contains_position(detail, 2.5, 0.0)
    assert detail_chart_overlaps_main_chart(detail, wrap_chart) is not None
    assert detail_chart_overlaps_main_chart(detail, opposite_chart) is None
    assert detail_chart_overlaps_main_chart(detail, touching_chart) is None


@pytest.mark.parametrize("edition", ("pocket", "standard", "deep"))
def test_each_edition_tiling_covers_the_sky(edition: str) -> None:
    atlas = load_atlas_config(ROOT / "atlas" / f"{edition}.yaml")
    assert coverage_report(chart_definitions(atlas), step_deg=2.0).covers_all
