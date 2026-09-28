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
from nightsky_atlas.render.detail_markers import build_detail_marker

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("edition", "code", "stellar_limit", "scale_bar"),
    (("pocket", "P", 7.5, 10.0), ("standard", "S", 9.0, 5.0), ("deep", "D", 10.0, 2.0)),
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
    assert presentation_from_edition(chart, atlas.resolved_edition()).chart_code == f"{code}001"


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


def test_pocket_symmetric_navigation_tiling() -> None:
    pocket = load_atlas_config(ROOT / "atlas" / "pocket.yaml")
    spec = TilingSpec.from_config(pocket.tiling)
    assert spec.declination_centers == (-67.0, -33.0, 0.0, 33.0, 67.0)
    assert resolve_ring_counts(spec) == (5, 12, 12, 12, 5)
    charts = chart_definitions(pocket)
    assert len(charts) == 48
    assert coverage_report(charts, step_deg=0.5).covers_all
    assert neighbour_overlap_report(charts, step_deg=1.0).is_complete


def test_pocket_constellation_boundaries_are_distinct_from_grid_and_figures() -> None:
    pocket = load_style_config(ROOT / "styles" / "pocket.yaml")
    standard = load_style_config(ROOT / "styles" / "standard.yaml")
    boundary = pocket.constellation.boundaries
    assert boundary.enabled
    assert boundary.line_width_mm == pytest.approx(0.12)
    assert boundary.gray == pytest.approx(0.68)
    assert boundary.gray < pocket.grid.gray
    assert boundary.gray > pocket.constellation.lines.gray
    assert pocket.constellation.lines == standard.constellation.lines
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
        "SD084",
        "SD031",
        "SD063",
        "SD013",
        "SD035",
    }
    assert {detail.name for detail in details} >= {
        "Virgo Cluster",
        "Sagittarius clusters · M22 / M28",
        "Cygnus nebula field",
        "Orion Nebula · M42",
        "Perseus Double Cluster",
        "Pleiades · M45",
    }
    assert all(detail.mm_per_degree == 20.0 for detail in details)
    assert all(detail.star_profile == "deep" for detail in details)
    assert deep.stellar_limit_magnitude == 10.0


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
