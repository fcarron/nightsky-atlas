"""Tests for overview and locator rendering."""

from __future__ import annotations

from pathlib import Path

import cairo
import pytest

from nightsky_atlas.atlas.config import LocatorStyle, load_atlas_config, load_style_config
from nightsky_atlas.atlas.overview import NORTH, build_overview, hemisphere_for
from nightsky_atlas.atlas.tiling import chart_definitions
from nightsky_atlas.catalog.constellations import load_constellations
from nightsky_atlas.catalog.models import Provenance, Star
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.chart.page import PageTransform
from nightsky_atlas.projection.base import ChartPoint
from nightsky_atlas.render.overview import (
    LocatorInset,
    OverviewTransform,
    draw_locator_inset,
    draw_overview_page,
    locator_rect,
)
from nightsky_atlas.units import mm_to_pt

REPO_ROOT = Path(__file__).resolve().parents[2]
ATLAS_PATH = REPO_ROOT / "atlas" / "standard.yaml"
STYLE_PATH = REPO_ROOT / "styles" / "standard.yaml"
CONSTELLATIONS = REPO_ROOT / "data" / "fixtures" / "constellations"

PAGE = PageGeometry(width_mm=297.0, height_mm=210.0, margin_mm=12.0)


@pytest.fixture(scope="module")
def overview():
    atlas = load_atlas_config(ATLAS_PATH)
    charts = chart_definitions(atlas)
    constellations = load_constellations(CONSTELLATIONS)
    return build_overview(
        charts,
        hemisphere=NORTH,
        constellations=constellations,
        edition=atlas.resolved_edition(),
    )


def make_surface() -> tuple[cairo.ImageSurface, cairo.Context[cairo.Surface]]:
    surface = cairo.ImageSurface(
        cairo.FORMAT_ARGB32, int(mm_to_pt(PAGE.width_mm)), int(mm_to_pt(PAGE.height_mm))
    )
    return surface, cairo.Context(surface)


def make_transform() -> PageTransform:
    return PageTransform(
        chart=ChartDefinition(
            id="standard-053",
            center_ra_deg=187.5,
            center_dec_deg=12.0,
            width_deg=27.0,
            height_deg=18.5,
        ),
        page=PAGE,
    )


def test_overview_transform_flips_east_left_north_up() -> None:
    transform = OverviewTransform(center_x_mm=100.0, center_y_mm=100.0, scale_mm_per_deg=1.0)
    east = transform.to_page(ChartPoint(10.0, 0.0))
    north = transform.to_page(ChartPoint(0.0, 10.0))
    assert east.x_mm < 100.0
    assert east.y_mm == pytest.approx(100.0)
    assert north.y_mm < 100.0
    assert north.x_mm == pytest.approx(100.0)


def test_draw_overview_page_writes_png(tmp_path: Path, overview) -> None:
    surface, cr = make_surface()
    draw_overview_page(cr, overview, PAGE, load_style_config(STYLE_PATH))
    path = tmp_path / "overview.png"
    surface.write_to_png(str(path))
    assert path.stat().st_size > 0


def test_draw_overview_page_with_bright_star(tmp_path: Path) -> None:
    atlas = load_atlas_config(ATLAS_PATH)
    charts = chart_definitions(atlas)
    constellations = load_constellations(CONSTELLATIONS)
    star = Star(
        id="test-star",
        ra_deg=180.0,
        dec_deg=45.0,
        magnitude=1.0,
        provenance=Provenance(catalogue="test", source_id="test-star"),
    )
    overview = build_overview(
        charts,
        hemisphere=NORTH,
        constellations=constellations,
        edition=atlas.resolved_edition(),
        bright_stars=[star],
    )
    assert len(overview.stars) == 1
    surface, cr = make_surface()
    draw_overview_page(cr, overview, PAGE, load_style_config(STYLE_PATH))
    path = tmp_path / "overview-star.png"
    surface.write_to_png(str(path))
    assert path.stat().st_size > 0


def test_locator_rect_disabled_by_default() -> None:
    style = load_style_config(STYLE_PATH)
    assert locator_rect(make_transform(), style) is None


def test_locator_rect_sits_inside_chart_frame_when_enabled() -> None:
    style = load_style_config(STYLE_PATH).model_copy(
        update={"locator": LocatorStyle(enabled=True)}
    )
    transform = make_transform()
    rect = locator_rect(transform, style)
    assert rect is not None
    frame = transform.chart_rect
    assert frame.left_mm <= rect.left_mm
    assert rect.right_mm <= frame.right_mm
    assert frame.top_mm <= rect.top_mm
    assert rect.bottom_mm <= frame.bottom_mm


def test_locator_rect_corner_mapping() -> None:
    base = load_style_config(STYLE_PATH)
    transform = make_transform()
    frame = transform.chart_rect
    bottom_left = locator_rect(
        transform, base.model_copy(update={"locator": LocatorStyle(enabled=True)})
    )
    top_right = locator_rect(
        transform,
        base.model_copy(
            update={"locator": LocatorStyle(enabled=True, corner="top_right")}
        ),
    )
    assert bottom_left is not None and top_right is not None
    assert bottom_left.top_mm > frame.top_mm
    assert top_right.top_mm == pytest.approx(frame.top_mm + base.locator.inset_margin_mm)
    assert top_right.left_mm > bottom_left.left_mm


def test_draw_locator_inset_is_a_noop_when_disabled(overview) -> None:
    surface, cr = make_surface()
    cr.set_source_rgb(1.0, 1.0, 1.0)
    cr.paint()
    inset = LocatorInset(overview=overview, current_chart_id="standard-053")
    draw_locator_inset(cr, inset, make_transform(), load_style_config(STYLE_PATH))
    surface.flush()


def test_draw_locator_inset_writes_png(tmp_path: Path, overview) -> None:
    style = load_style_config(STYLE_PATH).model_copy(
        update={"locator": LocatorStyle(enabled=True)}
    )
    transform = make_transform()
    definition = transform.chart
    inset = LocatorInset(
        overview=overview,
        current_chart_id=definition.id,
        neighbour_ids=frozenset(neighbour for _, neighbour in definition.neighbours),
    )
    surface, cr = make_surface()
    cr.set_source_rgb(1.0, 1.0, 1.0)
    cr.paint()
    draw_locator_inset(cr, inset, transform, style)
    path = tmp_path / "locator.png"
    surface.write_to_png(str(path))
    assert path.stat().st_size > 0


def test_locator_uses_hemisphere_of_chart(overview) -> None:
    assert hemisphere_for(12.0) == overview.hemisphere
