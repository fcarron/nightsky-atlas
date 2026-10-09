"""Edition presets share physical print styling while changing sky scale."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from nightsky_atlas.atlas.config import load_atlas_config, load_style_config
from nightsky_atlas.atlas.tiling import (
    TilingSpec,
    chart_definitions,
    coverage_report,
    neighbour_overlap_report,
    resolve_ring_counts,
)
from nightsky_atlas.build.atlas import _style_with_star_profile
from nightsky_atlas.chart.page import PageTransform
from nightsky_atlas.chart.presentation import presentation_from_edition
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
        expected = [index * 360.0 / count for index in range(count)]
        assert by_dec[dec] == pytest.approx(expected)
    assert by_dec[-62.0] == pytest.approx(by_dec[62.0])
    assert by_dec[-33.0] == pytest.approx(by_dec[33.0])
    detail = pocket.detail_charts[0]
    assert detail.code == "PD021A"
    assert detail.parent_chart_id == "pocket-021"


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


def test_deep_tiling_mirrors_standard_ring_design() -> None:
    standard = load_atlas_config(ROOT / "atlas" / "standard.yaml")
    deep = load_atlas_config(ROOT / "atlas" / "deep.yaml")
    assert deep.tiling.polar_caps is True
    assert deep.tiling.stagger_ra_centers is True
    assert deep.tiling.auto_adjust_counts is False
    assert deep.tiling.declination_centers
    assert deep.tiling.target_overlap.vertical_deg == pytest.approx(
        standard.tiling.target_overlap.vertical_deg / 2.0
    )
    assert deep.tiling.target_overlap.horizontal_min_deg == pytest.approx(
        standard.tiling.target_overlap.horizontal_min_deg / 2.0
    )
    spec = TilingSpec.from_config(deep.tiling)
    assert spec.is_ring_mode


def test_standard_detail_maps_are_supplemental_and_doubled_scale() -> None:
    standard = load_atlas_config(ROOT / "atlas" / "standard.yaml")
    deep = load_atlas_config(ROOT / "atlas" / "deep.yaml")
    details = standard.detail_charts
    assert len(chart_definitions(standard)) == 118
    assert {detail.code for detail in details} == {
        "SD053",
        "SD053A",
        "SD053B",
        "SD089",
        "SD084",
        "SD031",
        "SD063",
        "SD013",
        "SD035",
    }
    assert {
        detail.code for detail in details if detail.fallback_parent_galaxy_labels
    } == {"SD053A", "SD053B", "SD089"}
    assert {detail.name for detail in details} >= {
        "Virgo Cluster",
        "Sagittarius clusters · M22 / M28",
        "Cygnus nebula field",
        "Orion Nebula · M42",
        "Perseus Double Cluster",
        "Pleiades · M45",
    }
    assert {
        detail.code: detail.mm_per_degree
        for detail in details
        if detail.code in {"SD053A", "SD053B", "SD089"}
    } == {"SD053A": 60.0, "SD053B": 60.0, "SD089": 60.0}
    assert all(
        detail.mm_per_degree == 20.0
        for detail in details
        if detail.code not in {"SD053A", "SD053B", "SD089"}
    )
    assert all(detail.star_profile == "deep" for detail in details)
    assert deep.stellar_limit_magnitude == 10.5


def test_detail_deep_star_profile_preserves_standard_dso_styling() -> None:
    standard_style = load_style_config(ROOT / "styles" / "standard.yaml")
    deep_style = load_style_config(ROOT / "styles" / "deep.yaml")
    detail_style = _style_with_star_profile(standard_style, deep_style)
    assert detail_style.star == deep_style.star
    assert detail_style.double_stars == deep_style.double_stars
    assert detail_style.label.star_labels == deep_style.label.star_labels
    assert detail_style.dso == standard_style.dso
    assert detail_style.label.dso_labels == standard_style.label.dso_labels


def test_standard_detail_markers_project_into_their_parent_charts() -> None:
    standard = load_atlas_config(ROOT / "atlas" / "standard.yaml")
    charts = {chart.id: chart for chart in chart_definitions(standard)}
    for detail in standard.detail_charts:
        parent = charts[detail.parent_chart_id]
        transform = PageTransform(
            chart=parent,
            page=standard.page.to_geometry(),
            scale_mm_per_degree=standard.mm_per_degree,
        )
        marker = build_detail_marker(detail, parent, transform)
        assert marker.chart_code == detail.code
        assert marker.label == detail.name
        assert len(marker.boundary) == 48
        assert all(
            math.isfinite(point.x_mm) and math.isfinite(point.y_mm)
            for point in marker.boundary
        )
        frame = transform.chart_rect
        xs = [point.x_mm for point in marker.boundary]
        ys = [point.y_mm for point in marker.boundary]
        assert max(xs) >= frame.left_mm and min(xs) <= frame.right_mm
        assert max(ys) >= frame.top_mm and min(ys) <= frame.bottom_mm


@pytest.mark.parametrize("edition", ("pocket", "standard", "deep"))
def test_each_edition_tiling_covers_the_sky(edition: str) -> None:
    atlas = load_atlas_config(ROOT / "atlas" / f"{edition}.yaml")
    assert coverage_report(chart_definitions(atlas), step_deg=2.0).covers_all
