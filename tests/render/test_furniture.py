"""Tests for footer furniture, navigation and the magnitude legend."""

from __future__ import annotations

from itertools import pairwise
from pathlib import Path

import pytest

from nightsky_atlas.atlas.config import LocatorStyle, load_style_config
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.chart.page import PageTransform
from nightsky_atlas.chart.presentation import presentation_for
from nightsky_atlas.render.furniture import build_furniture_plan
from nightsky_atlas.render.overview import locator_rect
from nightsky_atlas.render.symbols import StarSizeModel, star_reference_magnitudes
from nightsky_atlas.render.text import TextMeasurer

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
    title_height = TextMeasurer(
        STYLE.label.font_family, plan.title.font_size_pt
    ).measure_markup_mm(plan.title.markup).height_mm
    assert plan.title.y_mm + title_height <= PAGE.height_mm - 2.0


def test_navigation_sits_outside_the_chart_frame_with_short_codes() -> None:
    plan, transform = build_plan((("N", "standard-082"), ("S", "standard-054")))
    rect = transform.chart_rect
    by_direction = {text.text.split(":")[0]: text for text in plan.navigation}
    assert by_direction["N"].text == "N: S082"
    assert by_direction["S"].text == "S: S054"
    assert by_direction["N"].target_chart_code == "S082"
    assert by_direction["S"].target_chart_code == "S054"
    assert by_direction["N"].y_mm < rect.top_mm
    assert by_direction["S"].y_mm > rect.bottom_mm


def test_east_west_navigation_follows_east_left_orientation() -> None:
    plan, transform = build_plan((("E", "standard-067"), ("W", "standard-069")))
    rect = transform.chart_rect
    by_direction = {text.text.split(":")[0]: text for text in plan.navigation}
    assert by_direction["E"].x_mm < rect.left_mm
    assert by_direction["W"].x_mm > rect.right_mm


def test_east_west_navigation_stays_clear_of_paper_edge_and_frame() -> None:
    plan, transform = build_plan((("E", "standard-067"), ("W", "standard-069")))
    rect = transform.chart_rect
    inset = STYLE.furniture.navigation.side_inset_mm
    for text in plan.navigation:
        assert text.rotation_rad != 0.0
        metrics = TextMeasurer(
            STYLE.label.font_family, text.font_size_pt
        ).measure_markup_mm(text.markup if text.markup else text.text)
        half_width = metrics.height_mm / 2.0
        assert text.x_mm - half_width >= inset - 1e-9
        assert text.x_mm + half_width <= PAGE.width_mm - inset + 1e-9
        assert (
            text.x_mm + half_width <= rect.left_mm
            or text.x_mm - half_width >= rect.right_mm
        )


def test_navigation_is_larger_than_coordinate_labels() -> None:
    plan, _ = build_plan((("N", "standard-082"),))
    assert plan.navigation
    for text in plan.navigation:
        assert text.font_size_pt > STYLE.grid.label_font_size_pt


def test_navigation_is_mid_grey_and_subordinate_to_sky_labels() -> None:
    nav = STYLE.furniture.navigation
    assert nav.gray >= STYLE.grid.label_gray
    assert nav.gray <= STYLE.furniture.title_gray + 0.5
    assert nav.font_size_pt <= STYLE.label.dso_labels.normal_size_pt * 1.3


def test_title_chart_code_is_bold_and_prefix_regular() -> None:
    plan, _ = build_plan()
    assert plan.title is not None
    assert plan.title.markup is not None
    assert "<b>S068</b>" in plan.title.markup
    assert plan.title.markup.startswith("NightSky Atlas")
    assert plan.title.font_size_pt == pytest.approx(8.5)


def test_navigation_rectangles_are_label_obstacles() -> None:
    plan, _ = build_plan((("N", "standard-082"),))
    nav = plan.navigation[0]
    assert any(
        obstacle.left_mm <= nav.x_mm <= obstacle.right_mm
        and obstacle.top_mm <= nav.y_mm <= obstacle.bottom_mm
        for obstacle in plan.obstacles
    )


@pytest.mark.parametrize(
    ("edition", "expected_magnitudes"),
    [
        ("pocket", (*range(8), 7.5)),
        ("standard", tuple(range(10))),
        ("deep", tuple(range(11))),
    ],
)
def test_legend_dots_use_real_star_size_model(
    edition: str, expected_magnitudes: tuple[float, ...]
) -> None:
    style = load_style_config(REPO_ROOT / "styles" / f"{edition}.yaml")
    transform = make_transform()
    plan = build_furniture_plan(
        transform, transform.chart, style, presentation_for(transform.chart)
    )
    assert plan.legend is not None
    model = StarSizeModel.from_style(style.star)
    assert star_reference_magnitudes(style.star) == expected_magnitudes
    assert tuple(number.text for number in plan.legend.numbers) == tuple(
        f"{magnitude:g}" for magnitude in expected_magnitudes
    )
    assert [dot.diameter_mm for dot in plan.legend.dots] == pytest.approx(
        [model.diameter_mm(magnitude) for magnitude in expected_magnitudes]
    )
    assert all(
        number.x_mm == pytest.approx(dot.x_mm)
        and number.y_mm < dot.y_mm - dot.diameter_mm / 2.0
        for dot, number in zip(plan.legend.dots, plan.legend.numbers, strict=True)
    )
    assert all(
        right.x_mm - right.diameter_mm / 2.0
        - (left.x_mm + left.diameter_mm / 2.0)
        == pytest.approx(style.furniture.magnitude_legend.spacing_mm)
        for left, right in pairwise(plan.legend.dots)
    )
    measurer = TextMeasurer(style.label.font_family, style.furniture.magnitude_legend.font_size_pt)
    assert all(
        number.x_mm + measurer.measure_mm(number.text).width_mm / 2.0
        < right.x_mm - right.diameter_mm / 2.0
        for number, right in zip(plan.legend.numbers[:-1], plan.legend.dots[1:], strict=True)
    )
    assert all(
        dot.y_mm - dot.diameter_mm / 2.0 > transform.chart_rect.bottom_mm
        for dot in plan.legend.dots
    )
    assert all(
        number.y_mm + measurer.measure_mm(number.text).height_mm
        <= PAGE.height_mm - 2.0
        for number in plan.legend.numbers
    )
    assert all(dot.y_mm + dot.diameter_mm / 2.0 <= PAGE.height_mm - 2.0 for dot in plan.legend.dots)
    assert plan.scale_bar is not None
    assert (
        plan.legend.numbers[-1].x_mm
        + measurer.measure_mm(plan.legend.numbers[-1].text).width_mm
        < plan.scale_bar.left_mm
    )


def test_scale_bar_length_follows_mm_per_degree() -> None:
    plan, transform = build_plan()
    assert plan.scale_bar is not None
    expected = STYLE.furniture.scale_bar.length_deg * transform.mm_per_deg
    assert (plan.scale_bar.right_mm - plan.scale_bar.left_mm) == pytest.approx(expected)
    assert plan.scale_bar.label.endswith("\N{DEGREE SIGN}")
    assert "deg" not in plan.scale_bar.label
    label_height = TextMeasurer(
        STYLE.label.font_family, plan.scale_bar.font_size_pt
    ).measure_mm(plan.scale_bar.label).height_mm
    assert plan.scale_bar.label_y_mm + label_height < plan.scale_bar.line_y_mm
    assert plan.scale_bar.line_y_mm + STYLE.furniture.scale_bar.tick_mm / 2.0 < PAGE.height_mm - 2.0


def test_footer_sits_below_the_chart_frame() -> None:
    plan, transform = build_plan((("S", "standard-054"),))
    rect = transform.chart_rect
    assert plan.scale_bar is not None
    assert plan.scale_bar.line_y_mm > rect.bottom_mm
    assert plan.legend is not None
    assert plan.legend.dots[0].y_mm > rect.bottom_mm


def test_locator_rect_is_a_label_obstacle_when_enabled() -> None:
    style = STYLE.model_copy(update={"locator": LocatorStyle(enabled=True)})
    transform = make_transform()
    plan = build_furniture_plan(
        transform, transform.chart, style, presentation_for(transform.chart)
    )
    rect = locator_rect(transform, style)
    assert rect is not None
    assert rect in plan.obstacles
