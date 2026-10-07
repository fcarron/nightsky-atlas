"""Tests for footer furniture, navigation and the magnitude legend."""

from __future__ import annotations

from pathlib import Path

import pytest

from nightsky_atlas.atlas.config import LocatorStyle, load_style_config
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.chart.page import PageTransform
from nightsky_atlas.chart.presentation import presentation_for
from nightsky_atlas.render.furniture import build_furniture_plan
from nightsky_atlas.render.overview import locator_rect
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
    assert plan.title.text == "NightSky Atlas \N{MIDDLE DOT} S068"
    assert plan.title.align == "right"
    assert plan.title.x_mm == pytest.approx(PAGE.width_mm - PAGE.margin_mm)
    assert plan.title.y_mm > PAGE.height_mm / 2.0
    title_height = TextMeasurer(
        STYLE.label.font_family, plan.title.font_size_pt
    ).measure_markup_mm(plan.title.markup).height_mm
    assert plan.title.y_mm + title_height <= PAGE.height_mm - 2.0


@pytest.mark.parametrize(
    ("edition", "chart_id", "expected"),
    (
        ("pocket", "pocket-035", "NightSky Atlas · Tau · P35"),
        ("standard", "standard-035", "NightSky Atlas · Tau · S035"),
        ("deep", "deep-035", "NightSky Atlas · Tau · D035"),
        ("eyepiece", "eyepiece-035", "NightSky Atlas · Tau · E035"),
    ),
)
def test_editions_share_the_standard_chart_footer(edition, chart_id, expected) -> None:
    chart = ChartDefinition(
        id=chart_id,
        center_ra_deg=187.5,
        center_dec_deg=12.0,
        width_deg=27.0,
        height_deg=18.5,
        atlas_id=edition,
    )
    transform = PageTransform(chart=chart, page=PAGE)
    style = load_style_config(REPO_ROOT / "styles" / f"{edition}.yaml")
    presentation = presentation_for(
        chart, constellation_area_fractions={"Tau": 1.0}
    )
    plan = build_furniture_plan(transform, chart, style, presentation)
    assert plan.title is not None
    assert plan.title.text == expected
    assert plan.brand is None
    assert plan.title.font_size_pt == pytest.approx(STYLE.furniture.title_font_size_pt)
    assert plan.scale_bar is None


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


def test_up_to_three_references_share_one_chart_edge() -> None:
    plan, transform = build_plan(
        (
            ("N", "standard-081"),
            ("N", "standard-082"),
            ("N", "standard-083"),
            ("N", "standard-084"),
        )
    )
    north = [text for text in plan.navigation if text.text.startswith("N:")]
    assert [text.target_chart_code for text in north] == ["S081", "S082", "S083"]
    assert [text.x_mm for text in north] == sorted(text.x_mm for text in north)
    assert len({text.x_mm for text in north}) == 3
    assert all(text.y_mm < transform.chart_rect.top_mm for text in north)


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
    assert plan.title.markup.startswith('<span size="small">NightSky Atlas</span>')
    assert plan.title.font_size_pt == pytest.approx(8.5)


def test_navigation_rectangles_are_label_obstacles() -> None:
    plan, _ = build_plan((("N", "standard-082"),))
    nav = plan.navigation[0]
    assert any(
        obstacle.left_mm <= nav.x_mm <= obstacle.right_mm
        and obstacle.top_mm <= nav.y_mm <= obstacle.bottom_mm
        for obstacle in plan.obstacles
    )


@pytest.mark.parametrize("edition", ("pocket", "standard", "deep"))
def test_normal_chart_pages_have_no_magnitude_legend(edition: str) -> None:
    style = load_style_config(REPO_ROOT / "styles" / f"{edition}.yaml")
    transform = make_transform()
    plan = build_furniture_plan(
        transform, transform.chart, style, presentation_for(transform.chart)
    )
    assert plan.legend is None


@pytest.mark.parametrize(
    "style_name",
    (
        "pocket",
        "standard",
        "deep",
        "eyepiece",
        "eyepiece_deep",
        "deep_detail",
        "deep_detail_40",
    ),
)
def test_scale_bar_is_disabled_for_all_editions_and_detail_styles(style_name: str) -> None:
    style = load_style_config(REPO_ROOT / "styles" / f"{style_name}.yaml")
    assert style.furniture.scale_bar.enabled is False


def test_standard_footer_has_no_scale_bar() -> None:
    plan, transform = build_plan((("S", "standard-054"),))
    assert plan.scale_bar is None
    assert plan.title is not None
    assert plan.title.y_mm > transform.chart_rect.bottom_mm


def test_locator_rect_is_a_label_obstacle_when_enabled() -> None:
    style = STYLE.model_copy(update={"locator": LocatorStyle(enabled=True)})
    transform = make_transform()
    plan = build_furniture_plan(
        transform, transform.chart, style, presentation_for(transform.chart)
    )
    rect = locator_rect(transform, style)
    assert rect is not None
    assert rect in plan.obstacles
