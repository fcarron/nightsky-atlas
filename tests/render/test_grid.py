"""Tests for coordinate grid generation."""

from __future__ import annotations

from pathlib import Path

import pytest

from nightsky_atlas.atlas.config import load_style_config
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.chart.page import PageTransform
from nightsky_atlas.render.grid import build_grid

REPO_ROOT = Path(__file__).resolve().parents[2]
STYLE = load_style_config(REPO_ROOT / "styles" / "standard.yaml")

CHART = ChartDefinition(
    id="test", center_ra_deg=187.5, center_dec_deg=12.0, width_deg=20.0, height_deg=14.0
)
PAGE = PageGeometry(width_mm=297.0, height_mm=210.0, margin_mm=12.0)
TRANSFORM = PageTransform(chart=CHART, page=PAGE)


def test_grid_has_meridians_and_parallels() -> None:
    lines = build_grid(CHART, TRANSFORM, STYLE)
    kinds = {line.kind for line in lines}
    assert kinds == {"ra", "dec"}
    assert len(lines) > 4


def test_grid_values_follow_step() -> None:
    for line in build_grid(CHART, TRANSFORM, STYLE):
        step = STYLE.grid.ra_step_deg if line.kind == "ra" else STYLE.grid.dec_step_deg
        assert line.value_deg % step == pytest.approx(0.0, abs=1e-9)


def test_grid_points_are_finite() -> None:
    for line in build_grid(CHART, TRANSFORM, STYLE):
        assert len(line.points) >= 2
        for point in line.points:
            assert point.x_mm == point.x_mm  # not NaN
            assert point.y_mm == point.y_mm


def test_disabled_grid_is_empty() -> None:
    style = STYLE.model_copy(update={"grid": STYLE.grid.model_copy(update={"enabled": False})})
    assert build_grid(CHART, TRANSFORM, style) == ()