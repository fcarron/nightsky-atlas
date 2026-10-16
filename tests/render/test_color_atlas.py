from __future__ import annotations

import math
import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, call

import cairo
import pytest

from nightsky_atlas.atlas.config import StyleConfig, load_style_config
from nightsky_atlas.catalog.galaxy_visibility import GalaxyContourClass
from nightsky_atlas.catalog.milky_way import MilkyWayContour, load_milky_way_contours
from nightsky_atlas.catalog.models import DsoType
from nightsky_atlas.catalog.selection import DsoMetadata
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.chart.page import PageTransform
from nightsky_atlas.projection.base import ChartPoint
from nightsky_atlas.projection.stereographic import StereographicProjection
from nightsky_atlas.render.cairo import (
    _draw_dso_shape,
    _draw_milky_way_contours,
    _dso_color,
    _dso_fill_and_outline_alpha,
    _dso_fill_color,
)
from nightsky_atlas.render.symbols import DsoShape, SymbolExtent
from nightsky_atlas.scene.builder import build_scene
from nightsky_atlas.scene.models import ChartScene, SceneMilkyWayPolygon
from nightsky_atlas.units import mm_to_pt

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("edition", "base_levels", "color_levels", "expected_fills"),
    (
        (
            "pocket",
            (1,),
            (1, 2, 3, 4, 5),
            {
                1: "#E8F1F8",
                2: "#E3EEF7",
                3: "#D6E6F3",
                4: "#CFE2F1",
                5: "#C4D9EC",
            },
        ),
        ("standard", (1, 3), (1, 3), {1: "#E8F1F8", 3: "#D6E6F3"}),
        ("deep", (1, 3, 5), (1, 3), {1: "#E8F1F8", 3: "#D6E6F3"}),
    ),
)
def test_color_styles_inherit_edition_and_select_fill_levels(
    edition: str,
    base_levels: tuple[int, ...],
    color_levels: tuple[int, ...],
    expected_fills: dict[int, str],
) -> None:
    base = load_style_config(REPO_ROOT / "styles" / f"{edition}.yaml")
    assert base.milky_way.levels == base_levels
    style = load_style_config(REPO_ROOT / "styles" / "color" / f"{edition}.yaml")
    assert style.id == base.id
    assert style.star == base.star
    assert style.dso == base.dso
    assert style.milky_way.levels == color_levels
    assert style.color_atlas is not None
    assert style.color_atlas.milky_way_fills == expected_fills
    assert style.color_atlas.dso.galaxies == "#B97A63"
    assert style.color_atlas.constellation_names == "#92969E"
    assert style.color_atlas.open_cluster_fill.large_fill_alpha == 0.18
    assert style.color_atlas.galaxy_fill.full_fill_until_mm == 2.5
    assert style.color_atlas.galaxy_fill.large_fill_from_mm == 7.0
    assert style.color_atlas.galaxy_fill.large_fill_alpha == 0.18
    assert style.color_atlas.schematic_nebula_fill.full_fill_until_mm == 3.0
    assert style.color_atlas.schematic_nebula_fill.large_fill_from_mm == 16.0
    assert style.color_atlas.schematic_nebula_fill.large_fill_alpha == 0.08


@pytest.mark.parametrize("edition", ("pocket", "standard", "deep"))
def test_existing_edition_styles_remain_uncolored(edition: str) -> None:
    style = load_style_config(REPO_ROOT / "styles" / f"{edition}.yaml")
    assert style.color_atlas is None


def test_open_cluster_color_style_reduces_large_symbol_fill_only() -> None:
    style = load_style_config(REPO_ROOT / "styles/color/pocket.yaml")
    assert style.color_atlas is not None
    cluster = Mock(dso=Mock(object_type=DsoType.OPEN_CLUSTER))
    small = SymbolExtent(DsoShape.DASHED_CIRCLE, 4.0, 4.0)
    medium = SymbolExtent(DsoShape.DASHED_CIRCLE, 10.0, 10.0)
    large = SymbolExtent(DsoShape.DASHED_CIRCLE, 20.0, 20.0)

    assert _dso_fill_and_outline_alpha(style, cluster, small) == (1.0, 1.0)
    assert _dso_fill_and_outline_alpha(style, cluster, medium) == (
        0.48,
        style.color_atlas.open_cluster_fill.medium_outline_alpha,
    )
    assert _dso_fill_and_outline_alpha(style, cluster, large) == (
        0.18,
        style.color_atlas.open_cluster_fill.large_outline_alpha,
    )


def test_galaxy_fill_fades_smoothly_with_rendered_symbol_size() -> None:
    style = load_style_config(REPO_ROOT / "styles/color/standard.yaml")
    galaxy = Mock(dso=Mock(object_type=DsoType.GALAXY))

    def alpha(diameter_mm: float) -> tuple[float, float]:
        extent = SymbolExtent(DsoShape.CIRCLE, diameter_mm, diameter_mm / 2.0)
        return _dso_fill_and_outline_alpha(style, galaxy, extent)

    assert alpha(2.0) == (1.0, 1.0)
    assert alpha(2.5) == (1.0, 1.0)
    assert alpha(4.75) == pytest.approx((0.59, 1.0))
    assert alpha(7.0) == pytest.approx((0.18, 1.0))
    assert alpha(12.0) == pytest.approx((0.18, 1.0))
    assert alpha(3.5)[0] > alpha(4.75)[0] > alpha(6.0)[0]


@pytest.mark.parametrize(
    "object_type",
    (DsoType.BRIGHT_NEBULA, DsoType.DARK_NEBULA, DsoType.SUPERNOVA_REMNANT),
)
def test_schematic_nebula_fills_fade_smoothly_without_fading_outlines(
    object_type: DsoType,
) -> None:
    style = load_style_config(REPO_ROOT / "styles/color/standard.yaml")
    scene_dso = Mock(dso=Mock(object_type=object_type))

    def alpha(size_mm: float, shape: DsoShape) -> tuple[float, float]:
        extent = SymbolExtent(shape, size_mm, size_mm)
        return _dso_fill_and_outline_alpha(style, scene_dso, extent)

    assert alpha(2.0, DsoShape.SQUARE) == (1.0, 1.0)
    assert alpha(3.0, DsoShape.DASHED_SQUARE) == (1.0, 1.0)
    assert alpha(9.5, DsoShape.SQUARE) == pytest.approx((0.54, 1.0))
    assert alpha(16.0, DsoShape.DASHED_SQUARE) == pytest.approx((0.08, 1.0))
    assert alpha(24.0, DsoShape.SQUARE) == pytest.approx((0.08, 1.0))
    assert alpha(5.0, DsoShape.SQUARE)[0] > alpha(9.5, DsoShape.SQUARE)[0]
    assert alpha(9.5, DsoShape.SQUARE)[0] > alpha(14.0, DsoShape.SQUARE)[0]


def test_schematic_nebula_fill_rule_does_not_affect_non_square_or_other_symbols() -> None:
    style = load_style_config(REPO_ROOT / "styles/color/standard.yaml")
    nebula = Mock(dso=Mock(object_type=DsoType.BRIGHT_NEBULA))
    galaxy = Mock(dso=Mock(object_type=DsoType.GALAXY))
    extent = SymbolExtent(DsoShape.CIRCLE, 20.0, 20.0)

    assert _dso_fill_and_outline_alpha(style, nebula, extent) == (1.0, 1.0)
    assert _dso_fill_and_outline_alpha(style, galaxy, extent) == pytest.approx((0.18, 1.0))


@pytest.mark.parametrize(
    "object_type",
    (DsoType.BRIGHT_NEBULA, DsoType.DARK_NEBULA, DsoType.SUPERNOVA_REMNANT),
)
def test_monochrome_schematic_nebula_symbols_are_not_attenuated(
    object_type: DsoType,
) -> None:
    style = load_style_config(REPO_ROOT / "styles/standard.yaml")
    scene_dso = Mock(dso=Mock(object_type=object_type))
    extent = SymbolExtent(DsoShape.DASHED_SQUARE, 30.0, 30.0)

    assert _dso_fill_and_outline_alpha(style, scene_dso, extent) == (1.0, 1.0)


def test_monochrome_galaxy_fill_is_not_size_attenuated() -> None:
    style = load_style_config(REPO_ROOT / "styles/standard.yaml")
    galaxy = Mock(dso=Mock(object_type=DsoType.GALAXY))
    extent = SymbolExtent(DsoShape.CIRCLE, 60.0, 30.0)
    assert _dso_fill_and_outline_alpha(style, galaxy, extent) == (1.0, 1.0)


def test_magellanic_cloud_color_style_uses_milky_way_family() -> None:
    style = load_style_config(REPO_ROOT / "styles/color/pocket.yaml")
    assert style.color_atlas is not None
    assert style.color_atlas.magellanic_cloud_fills == {
        1: "#E8F1F8",
        2: "#D6E6F3",
        3: "#C4D9EC",
    }
    assert style.color_atlas.magellanic_cloud_fill_alpha == {
        1: 0.78,
        2: 0.78,
        3: 0.78,
    }
    assert style.color_atlas.magellanic_cloud_outline == "#D6E3ED"


@pytest.mark.parametrize("edition", ("pocket", "standard", "deep"))
def test_color_styles_cover_each_edition(edition: str) -> None:
    style = load_style_config(REPO_ROOT / f"styles/color/{edition}.yaml")
    assert style.color_atlas is not None
    assert style.color_atlas.open_cluster_fill is not None
    assert set(style.color_atlas.magellanic_cloud_fills) == {1, 2, 3}
    assert set(style.color_atlas.magellanic_cloud_fill_alpha) == {1, 2, 3}


@pytest.mark.parametrize(
    ("object_type", "subtype", "palette_key"),
    (
        (DsoType.GALAXY, None, "galaxies"),
        (DsoType.OPEN_CLUSTER, None, "clusters"),
        (DsoType.GLOBULAR_CLUSTER, None, "clusters"),
        (DsoType.PLANETARY_NEBULA, None, "planetary_nebulae"),
        (DsoType.BRIGHT_NEBULA, None, "bright_nebulae"),
        (DsoType.BRIGHT_NEBULA, "reflection nebula", "reflection_nebulae"),
        (DsoType.DARK_NEBULA, None, "dark_nebulae"),
        (DsoType.SUPERNOVA_REMNANT, None, "supernova_remnants"),
        (DsoType.GALAXY_CLUSTER, None, "other"),
    ),
)
def test_dso_classes_use_the_configured_color_palette(
    object_type: DsoType, subtype: str | None, palette_key: str
) -> None:
    style = load_style_config(
        REPO_ROOT / "styles/color/standard.yaml"
    )
    dso = Mock(object_type=object_type, semantic_subtype=subtype)
    color = _dso_color(style, Mock(dso=dso))
    assert style.color_atlas is not None
    assert color == getattr(style.color_atlas.dso, palette_key)


@pytest.mark.parametrize(
    ("visibility_class", "blend_level"),
    (
        (GalaxyContourClass.BOLD, 0),
        (GalaxyContourClass.NORMAL, 1),
        (GalaxyContourClass.FINE, 2),
        (GalaxyContourClass.DOTTED, 3),
    ),
)
def test_galaxy_fill_intensity_follows_existing_contour_class(
    visibility_class: GalaxyContourClass, blend_level: int
) -> None:
    style = load_style_config(REPO_ROOT / "styles/color/pocket.yaml")
    dso = Mock(object_type=DsoType.GALAXY, semantic_subtype=None)
    metadata = DsoMetadata("NGC 1", galaxy_contour_class=visibility_class)
    scene_dso = Mock(dso=dso, metadata=metadata)

    base = _dso_color(style, scene_dso)
    fill = _dso_fill_color(style, scene_dso)
    assert style.color_atlas is not None
    expected = _blend_hex_to_white(base, style.color_atlas.dso_fill_white_blend[blend_level])
    assert fill == expected


@pytest.mark.parametrize(
    ("score", "blend_level"),
    ((90.0, 0), (60.0, 1), (40.0, 2), (10.0, 3)),
)
def test_other_dso_fill_intensity_uses_existing_visual_score(
    score: float, blend_level: int
) -> None:
    style = load_style_config(REPO_ROOT / "styles/color/pocket.yaml")
    dso = Mock(object_type=DsoType.BRIGHT_NEBULA, semantic_subtype=None)
    scene_dso = Mock(dso=dso, metadata=DsoMetadata("NGC 1", visual_score=score))

    base = _dso_color(style, scene_dso)
    fill = _dso_fill_color(style, scene_dso)
    assert style.color_atlas is not None
    expected = _blend_hex_to_white(base, style.color_atlas.dso_fill_white_blend[blend_level])
    assert fill == expected


def _blend_hex_to_white(color: str, factor: float) -> str:
    rgb = _rgb_bytes(color)
    return "#" + "".join(f"{round(channel + (255 - channel) * factor):02X}" for channel in rgb)


def test_closed_milky_way_contours_create_closed_chart_clips() -> None:
    chart = ChartDefinition("wrap-fill", 0.0, 0.0, 4.0, 4.0)
    contour = MilkyWayContour(
        "milky-way:1:wrap-fill",
        1,
        ((358.0, -2.0), (2.0, -2.0), (2.0, 2.0), (358.0, 2.0), (358.0, -2.0)),
    )
    scene = build_scene(
        chart,
        milky_way_contours=(contour,),
        milky_way_levels=(1,),
        milky_way_fill_enabled=True,
    )
    assert scene.milky_way_polygons
    for polygon in scene.milky_way_polygons:
        assert len(polygon.points) >= 4
        assert polygon.points[0] == polygon.points[-1]
        assert all(abs(point.xi_deg) <= 2.0 + 1e-8 for point in polygon.points)
        assert all(abs(point.eta_deg) <= 2.0 + 1e-8 for point in polygon.points)


def test_milky_way_geojson_rings_keep_their_source_polygon_group() -> None:
    chart = ChartDefinition("fill-hole", 0.0, 0.0, 6.0, 6.0)
    outer = MilkyWayContour(
        "outer", 1, ((357.0, -4.0), (3.0, -4.0), (3.0, 4.0), (357.0, 4.0), (357.0, -4.0)),
        polygon_id="region", is_hole=False,
    )
    hole = MilkyWayContour(
        "hole", 1, ((359.0, -1.0), (1.0, -1.0), (1.0, 1.0), (359.0, 1.0), (359.0, -1.0)),
        polygon_id="region", is_hole=True,
    )

    scene = build_scene(
        chart,
        milky_way_contours=(outer, hole),
        milky_way_levels=(1,),
        milky_way_fill_enabled=True,
    )

    assert len(scene.milky_way_polygons) >= 2
    assert {polygon.polygon_id for polygon in scene.milky_way_polygons} == {"region"}
    assert all(polygon.level == 1 for polygon in scene.milky_way_polygons)
    assert all(polygon.points[0] == polygon.points[-1] for polygon in scene.milky_way_polygons)


def test_milky_way_fill_can_render_without_an_outline_path() -> None:
    style = load_style_config(REPO_ROOT / "styles/color/standard.yaml")
    chart = ChartDefinition("fill-only", 0.0, 0.0, 4.0, 4.0)
    scene = ChartScene(
        definition=chart,
        milky_way_polygons=(
            SceneMilkyWayPolygon(
                1,
                (
                    ChartPoint(-1.0, -1.0),
                    ChartPoint(1.0, -1.0),
                    ChartPoint(1.0, 1.0),
                    ChartPoint(-1.0, 1.0),
                ),
            ),
            SceneMilkyWayPolygon(
                1,
                (
                    ChartPoint(-0.5, -0.5),
                    ChartPoint(1.5, -0.5),
                    ChartPoint(1.5, 1.5),
                    ChartPoint(-0.5, 1.5),
                ),
            ),
        ),
    )
    context = Mock()
    transform = PageTransform(chart, PageGeometry(297.0, 210.0, 10.0))
    _draw_milky_way_contours(context, transform, scene, style)
    assert context.fill.call_count == 1
    assert context.set_fill_rule.called
    assert context.clip.called
    context.set_source_rgb.assert_any_call(232 / 255, 241 / 255, 248 / 255)


def test_milky_way_brightness_bands_are_clipped_to_the_previous_contour() -> None:
    style = load_style_config(REPO_ROOT / "styles/color/standard.yaml")
    chart = ChartDefinition("nested-fill", 0.0, 0.0, 4.0, 4.0)
    outer = (
        ChartPoint(-1.5, -1.5),
        ChartPoint(1.5, -1.5),
        ChartPoint(1.5, 1.5),
        ChartPoint(-1.5, 1.5),
    )
    inner = (
        ChartPoint(-2.0, -0.5),
        ChartPoint(0.5, -0.5),
        ChartPoint(0.5, 0.5),
        ChartPoint(-2.0, 0.5),
    )
    scene = ChartScene(
        definition=chart,
        milky_way_polygons=(
            SceneMilkyWayPolygon(1, outer),
            SceneMilkyWayPolygon(3, inner),
        ),
    )
    context = Mock()

    _draw_milky_way_contours(
        context, PageTransform(chart, PageGeometry(297.0, 210.0, 10.0)), scene, style
    )

    assert context.clip.call_count == 2
    assert context.fill.call_count == 2
    assert context.set_fill_rule.call_count >= 2
    assert context.set_source_rgb.call_args_list[:2] == [
        call(232 / 255, 241 / 255, 248 / 255),
        call(214 / 255, 230 / 255, 243 / 255),
    ]


def _render_milky_way_pixels(
    scene: ChartScene,
    style: StyleConfig,
    geometry: PageGeometry | None = None,
) -> tuple[cairo.ImageSurface, PageTransform]:
    geometry = geometry or PageGeometry(60.0, 60.0, 10.0)
    transform = PageTransform(scene.definition, geometry)
    width = math.ceil(mm_to_pt(geometry.width_mm))
    height = math.ceil(mm_to_pt(geometry.height_mm))
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    context = cairo.Context(surface)
    background = style.color_atlas.background if style.color_atlas is not None else "#FFFFFF"
    context.set_source_rgb(*_rgb_tuple(background))
    context.paint()
    _draw_milky_way_contours(context, transform, scene, style)
    surface.flush()
    return surface, transform


def _rgb_tuple(color: str) -> tuple[float, float, float]:
    value = color.lstrip("#")
    return tuple(int(value[index : index + 2], 16) / 255 for index in (0, 2, 4))


def _rgb_bytes(color: str) -> tuple[int, int, int]:
    value = color.lstrip("#")
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))


def _pixel_rgb(surface: cairo.ImageSurface, x_pt: float, y_pt: float) -> tuple[int, int, int]:
    x = round(x_pt)
    y = round(y_pt)
    offset = y * surface.get_stride() + x * 4
    argb = int.from_bytes(surface.get_data()[offset : offset + 4], sys.byteorder)
    return (argb >> 16 & 255, argb >> 8 & 255, argb & 255)


def _chart_pixel(
    surface: cairo.ImageSurface, transform: PageTransform, point: ChartPoint
) -> tuple[int, int, int]:
    page = transform.to_page(point)
    return _pixel_rgb(surface, mm_to_pt(page.x_mm), mm_to_pt(page.y_mm))


def _count_rgb(surface: cairo.ImageSurface, target: tuple[int, int, int]) -> int:
    data = surface.get_data()
    stride = surface.get_stride()
    count = 0
    for y in range(surface.get_height()):
        for x in range(surface.get_width()):
            offset = y * stride + x * 4
            argb = int.from_bytes(data[offset : offset + 4], sys.byteorder)
            if (argb >> 16 & 255, argb >> 8 & 255, argb & 255) == target:
                count += 1
    return count


def test_color_fills_show_nested_levels_and_keep_exterior_white() -> None:
    style = load_style_config(REPO_ROOT / "styles/color/pocket.yaml")
    chart = ChartDefinition("raster-levels", 0.0, 0.0, 4.0, 4.0)

    def square(radius: float) -> tuple[ChartPoint, ...]:
        return (
            ChartPoint(-radius, -radius),
            ChartPoint(radius, -radius),
            ChartPoint(radius, radius),
            ChartPoint(-radius, radius),
        )

    hole = (
        ChartPoint(-1.3, -1.3),
        ChartPoint(-1.0, -1.3),
        ChartPoint(-1.0, -1.0),
        ChartPoint(-1.3, -1.0),
    )

    scene = ChartScene(
        definition=chart,
        milky_way_polygons=(
            SceneMilkyWayPolygon(1, square(1.5), polygon_id="level-1"),
            SceneMilkyWayPolygon(1, hole, polygon_id="level-1"),
            SceneMilkyWayPolygon(2, square(1.2), polygon_id="level-2"),
            SceneMilkyWayPolygon(3, square(0.9), polygon_id="level-3"),
            SceneMilkyWayPolygon(4, square(0.6), polygon_id="level-4"),
            SceneMilkyWayPolygon(5, square(0.3), polygon_id="level-5"),
        ),
    )

    surface, transform = _render_milky_way_pixels(
        replace(scene, milky_way_contours=()), style
    )
    assert style.color_atlas is not None
    colors = style.color_atlas.milky_way_fills
    assert _chart_pixel(surface, transform, ChartPoint(1.7, 1.7)) == (255, 255, 255)
    assert _chart_pixel(surface, transform, ChartPoint(-1.15, -1.15)) == (255, 255, 255)
    assert _chart_pixel(surface, transform, ChartPoint(1.4, 0.0)) == _rgb_bytes(
        colors[1]
    )
    for point, level in (
        (ChartPoint(1.3, 0.0), 1),
        (ChartPoint(1.1, 0.0), 2),
        (ChartPoint(0.8, 0.0), 3),
        (ChartPoint(0.5, 0.0), 4),
        (ChartPoint(0.0, 0.0), 5),
    ):
        assert _chart_pixel(surface, transform, point) == _rgb_bytes(colors[level])


def test_real_pocket_p009_has_white_exterior_and_filled_level_one_at_sadr() -> None:
    style = load_style_config(REPO_ROOT / "styles/color/pocket.yaml")
    chart = ChartDefinition("pocket-009-mask-regression", 292.0, 33.0, 54.0, 36.0)
    contours = load_milky_way_contours(REPO_ROOT / "data/third_party/d3-celestial/mw.json")
    scene = build_scene(
        chart,
        milky_way_contours=contours,
        milky_way_levels=(1, 2, 3, 4, 5),
        milky_way_fill_enabled=True,
    )
    projection = StereographicProjection(chart.center_ra_deg, chart.center_dec_deg)
    sadr = projection.project(305.557, 40.256)
    vega = projection.project(279.2347, 38.7837)
    surface, transform = _render_milky_way_pixels(
        replace(scene, milky_way_contours=()), style
    )
    assert style.color_atlas is not None
    sadr_pixel = _chart_pixel(surface, transform, sadr)
    level1_rgb = _rgb_bytes(style.color_atlas.milky_way_fills[1])
    assert all(
        abs(actual - expected) <= 1
        for actual, expected in zip(sadr_pixel, level1_rgb, strict=True)
    )
    assert _chart_pixel(surface, transform, vega) == _rgb_bytes(style.color_atlas.background)


def test_real_pocket_p007_keeps_m31_in_the_level_one_source_hole() -> None:
    style = load_style_config(REPO_ROOT / "styles/color/pocket.yaml")
    chart = ChartDefinition("pocket-007-m31-mask-regression", 12.0, 33.0, 54.0, 36.0)
    scene = build_scene(
        chart,
        milky_way_contours=load_milky_way_contours(
            REPO_ROOT / "data/third_party/d3-celestial/mw.json"
        ),
        milky_way_levels=(1, 2, 3, 4, 5),
        milky_way_fill_enabled=True,
    )
    projection = StereographicProjection(chart.center_ra_deg, chart.center_dec_deg)
    m31 = projection.project(10.6847, 41.269)
    surface, transform = _render_milky_way_pixels(
        replace(scene, milky_way_contours=()), style
    )

    assert style.color_atlas is not None
    assert _chart_pixel(surface, transform, m31) == _rgb_bytes(
        style.color_atlas.background
    )


def test_real_pocket_p008_shows_cygnus_milky_way_and_white_exterior() -> None:
    style = load_style_config(REPO_ROOT / "styles/color/pocket.yaml")
    chart = ChartDefinition("pocket-008-cygnus-regression", 332.0, 33.0, 54.0, 36.0)
    contours = load_milky_way_contours(REPO_ROOT / "data/third_party/d3-celestial/mw.json")
    scene = build_scene(
        chart,
        milky_way_contours=contours,
        milky_way_levels=(1, 2, 3, 4, 5),
        milky_way_fill_enabled=True,
    )
    surface, transform = _render_milky_way_pixels(
        replace(scene, milky_way_contours=()), style
    )
    assert style.color_atlas is not None
    projection = StereographicProjection(chart.center_ra_deg, chart.center_dec_deg)
    deneb = projection.project(310.36, 45.28)
    outside = projection.project(320.0, 25.0)
    assert _chart_pixel(surface, transform, deneb) in {
        _rgb_bytes(style.color_atlas.milky_way_fills[level])
        for level in (1, 2, 3, 4, 5)
    }
    assert _chart_pixel(surface, transform, outside) == _rgb_bytes(
        style.color_atlas.background
    )
    assert all(
        _count_rgb(surface, _rgb_bytes(style.color_atlas.milky_way_fills[level])) > 0
        for level in (1, 2, 3)
    )


def test_overlapping_pocket_charts_render_the_same_milky_way_tone() -> None:
    style = load_style_config(REPO_ROOT / "styles/color/pocket.yaml")
    contours = load_milky_way_contours(REPO_ROOT / "data/third_party/d3-celestial/mw.json")
    geometry = PageGeometry(297.0, 210.0, 13.5)
    rendered = {}
    for chart_id, ra_center in (("pocket-007", 12.0), ("pocket-008", 332.0)):
        chart = ChartDefinition(chart_id, ra_center, 33.0, 54.0, 36.0)
        scene = build_scene(
            chart,
            milky_way_contours=contours,
            milky_way_levels=(1, 2, 3, 4, 5),
            milky_way_fill_enabled=True,
        )
        rendered[chart_id] = _render_milky_way_pixels(
            replace(scene, milky_way_contours=()), style, geometry
        )

    point = (354.0, 48.0)
    pixels = []
    for chart_id, ra_center in (("pocket-007", 12.0), ("pocket-008", 332.0)):
        surface, transform = rendered[chart_id]
        chart_point = StereographicProjection(ra_center, 33.0).project(*point)
        pixels.append(_chart_pixel(surface, transform, chart_point))

    assert pixels[0] == pixels[1]
    assert style.color_atlas is not None
    assert pixels[0] == _rgb_bytes(style.color_atlas.milky_way_fills[1])


def test_real_source_fills_a_chart_fully_inside_level_one_band() -> None:
    style = load_style_config(REPO_ROOT / "styles/color/pocket.yaml")
    chart = ChartDefinition("inside-level-one-band", 305.557, 40.256, 2.0, 2.0)
    style = style.model_copy(
        update={"milky_way": style.milky_way.model_copy(update={"levels": (1,)})}
    )
    scene = build_scene(
        chart,
        milky_way_contours=load_milky_way_contours(
            REPO_ROOT / "data/third_party/d3-celestial/mw.json"
        ),
        milky_way_levels=(1,),
        milky_way_fill_enabled=True,
    )
    assert scene.milky_way_fill_available
    assert any(polygon.level == 1 for polygon in scene.milky_way_polygons)

    surface, transform = _render_milky_way_pixels(
        replace(scene, milky_way_contours=()), style
    )

    assert style.color_atlas is not None
    assert _chart_pixel(surface, transform, ChartPoint(0.0, 0.0)) == _rgb_bytes(
        style.color_atlas.milky_way_fills[1]
    )


def test_no_milky_way_source_does_not_paint_level_one_base() -> None:
    style = load_style_config(REPO_ROOT / "styles/color/pocket.yaml")
    chart = ChartDefinition("no-milky-way-data", 0.0, 0.0, 4.0, 4.0)
    scene = ChartScene(definition=chart)
    context = Mock()

    _draw_milky_way_contours(context, PageTransform(chart, PageGeometry(60, 60, 10)), scene, style)

    assert context.mock_calls == []


def test_colored_dso_symbol_uses_color_fill_and_black_outline() -> None:
    context = Mock()
    fill = (0.7, 0.36, 0.27)

    _draw_dso_shape(context, 10.0, 10.0, 5.0, DsoShape.CIRCLE, 0.5, fill_color=fill)

    calls = context.mock_calls
    fill_color_index = calls.index(call.set_source_rgb(*fill))
    fill_index = calls.index(call.fill_preserve())
    black_after_fill_index = next(
        index
        for index, recorded_call in enumerate(calls)
        if index > fill_index and recorded_call == call.set_source_rgb(0.0, 0.0, 0.0)
    )
    stroke_index = next(
        index
        for index, recorded_call in enumerate(calls)
        if index > black_after_fill_index and recorded_call == call.stroke()
    )
    assert fill_color_index < fill_index < black_after_fill_index < stroke_index


def test_color_fill_levels_must_be_enabled_as_contours() -> None:
    style = load_style_config(REPO_ROOT / "styles/color/standard.yaml")
    style_data = style.model_dump()
    style_data["milky_way"]["levels"] = [1]
    with pytest.raises(ValueError, match="fill levels must also be enabled"):
        StyleConfig.model_validate(style_data)
