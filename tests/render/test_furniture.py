"""Tests for footer furniture, navigation and the magnitude legend."""

from __future__ import annotations

from pathlib import Path

import pytest

from nightsky_atlas.atlas.config import load_style_config
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.chart.page import PageTransform
from nightsky_atlas.chart.presentation import presentation_for
from nightsky_atlas.render.furniture import build_furniture_plan
from nightsky_atlas.render.symbols import StarSizeModel

REPO_ROOT = Path(__file__).resolve().parents[2]
STYLE = load_style_config(REPO_ROOT / "styles" / "standard.yaml")
PAGE = PageGeometry(width_mm=297.0, height_mm=210.0, margin_mm=12.0)


def make_transform(neighbours: tuple[tuple[str, str], ...] = ()) -> PageTransform:
    definition = ChartDefinition(
        id="standard-068",
        center_ra_deg=187.5,
        center_dec_deg=12.0,
        width_deg=27.0,
        height_deg=18.5,
        neighbours=neighbours,
    )
    return PageTransform(chart=definition, page=PAGE)


def build_plan(neighbours: tuple[tuple[str, str], ...] = ()):
    transform = make_transform(neighbours)
    presentation = presentation_for(transform.chart)
    return build_furniture_plan(transform, transform.chart, STYLE, presentation), transform


def test_title_uses_short_code_and_footer_position() -> None:
    plan, _ = build_plan()
    assert plan.title is not None
    assert plan.title.text == "NightSky Atlas \N{EM DASH} Standard \N{MIDDLE DOT} S068"
    assert plan.title.align == "right"
    assert plan.title.x_mm == pytest.approx(PAGE.width_mm - PAGE.margin_mm)
    assert plan.title.y_mm > PAGE.height_mm / 2.0


def test_navigation_sits_outside_the_chart_frame_with_short_codes() -> None:
    plan, transform = build_plan((("N", "standard-082"), ("S", "standard-054")))
    rect = transform.chart_rect
    by_direction = {text.text.split(":")[0]: text for text in plan.navigation}
    assert by_direction["N"].text == "N: S082"
    assert by_direction["S"].text == "S: S054"
    assert by_direction["N"].y_mm < rect.top_mm
    assert by_direction["S"].y_mm > rect.bottom_mm


def test_east_west_navigation_follows_east_left_orientation() -> None:
    plan, transform = build_plan((("E", "standard-067"), ("W", "standard-069")))
    rect = transform.chart_rect
    by_direction = {text.text.split(":")[0]: text for text in plan.navigation}
    assert by_direction["E"].x_mm < rect.left_mm
    assert by_direction["W"].x_mm > rect.right_mm


def test_navigation_is_smaller_than_coordinate_labels() -> None:
    plan, _ = build_plan((("N", "standard-082"),))
    assert plan.navigation
    for text in plan.navigation:
        assert text.font_size_pt < STYLE.grid.label_font_size_pt


def test_navigation_rectangles_are_label_obstacles() -> None:
    plan, _ = build_plan((("N", "standard-082"),))
    nav = plan.navigation[0]
    assert any(
        obstacle.left_mm <= nav.x_mm <= obstacle.right_mm
        and obstacle.top_mm <= nav.y_mm <= obstacle.bottom_mm
        for obstacle in plan.obstacles
    )


def test_legend_dots_use_real_star_size_model() -> None:
    plan, _ = build_plan()
    assert plan.legend is not None
    model = StarSizeModel.from_style(STYLE.star)
    magnitudes = STYLE.furniture.magnitude_legend.magnitudes
    assert [dot.diameter_mm for dot in plan.legend.dots] == pytest.approx(
        [model.diameter_mm(magnitude) for magnitude in magnitudes]
    )


def test_scale_bar_length_follows_mm_per_degree() -> None:
    plan, transform = build_plan()
    assert plan.scale_bar is not None
    expected = STYLE.furniture.scale_bar.length_deg * transform.mm_per_deg
    assert (plan.scale_bar.right_mm - plan.scale_bar.left_mm) == pytest.approx(expected)
    assert plan.scale_bar.label.endswith("\N{DEGREE SIGN}")
    assert "deg" not in plan.scale_bar.label


def test_footer_sits_below_the_chart_frame() -> None:
    plan, transform = build_plan((("S", "standard-054"),))
    rect = transform.chart_rect
    assert plan.scale_bar is not None
    assert plan.scale_bar.line_y_mm > rect.bottom_mm
    assert plan.legend is not None
    assert plan.legend.dots[0].y_mm > rect.bottom_mm
