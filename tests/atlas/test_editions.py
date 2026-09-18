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
    (("pocket", "P", 7.5, 10.0), ("standard", "S", 9.0, 5.0), ("deep", "D", 10.5, 2.0)),
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


def test_physical_print_style_is_shared_and_overlap_is_mm_derived() -> None:
    standard = load_style_config(ROOT / "styles" / "standard.yaml")
    for edition in ("pocket", "deep"):
        atlas = load_atlas_config(ROOT / "atlas" / f"{edition}.yaml")
        style = load_style_config(ROOT / "styles" / f"{edition}.yaml")
        spec = TilingSpec.from_config(atlas.tiling)
        assert style.label.font_size_pt == standard.label.font_size_pt
        assert style.dso.galaxy.min_diameter_mm == standard.dso.galaxy.min_diameter_mm
        assert spec.overlap_deg == pytest.approx(10.0 / atlas.tiling.mm_per_degree)


@pytest.mark.parametrize("edition", ("pocket", "standard", "deep"))
def test_each_edition_tiling_covers_the_sky(edition: str) -> None:
    atlas = load_atlas_config(ROOT / "atlas" / f"{edition}.yaml")
    assert coverage_report(chart_definitions(atlas), step_deg=2.0).covers_all
