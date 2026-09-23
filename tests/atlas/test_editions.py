"""Edition presets share physical print styling while changing sky scale."""

from __future__ import annotations

from pathlib import Path

import pytest

from nightsky_atlas.atlas.config import load_atlas_config, load_style_config
from nightsky_atlas.atlas.tiling import TilingSpec, chart_definitions, coverage_report
from nightsky_atlas.chart.presentation import presentation_from_edition

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


@pytest.mark.parametrize("edition", ("pocket", "standard", "deep"))
def test_each_edition_tiling_covers_the_sky(edition: str) -> None:
    atlas = load_atlas_config(ROOT / "atlas" / f"{edition}.yaml")
    assert coverage_report(chart_definitions(atlas), step_deg=2.0).covers_all
