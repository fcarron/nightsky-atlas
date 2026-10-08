"""Tests for the Cairo renderer.

These tests intentionally avoid fragile byte comparisons of the whole PDF
(``AGENTS.md`` section 24.2).  They check that valid artifacts are produced and
that raster dimensions follow from physical page size and resolution.
"""

from __future__ import annotations

import struct
from pathlib import Path

import cairo
import pytest

from nightsky_atlas.atlas.config import load_style_config
from nightsky_atlas.catalog.constellations import ConstellationSegment
from nightsky_atlas.catalog.galaxy_visibility import GalaxyContourClass
from nightsky_atlas.catalog.models import DeepSkyObject, DsoType, Provenance, Star
from nightsky_atlas.catalog.outlines import NebulaOutline
from nightsky_atlas.catalog.sample import load_sample_stars
from nightsky_atlas.catalog.selection import DsoMetadata
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.chart.page import PagePoint, PageTransform
from nightsky_atlas.layout.models import Label
from nightsky_atlas.projection.base import ChartPoint
from nightsky_atlas.render.cairo import (
    _bold_symbol_ids,
    _draw_outlines,
    _dso_contour,
    _dso_line_width_mm,
    _dso_overlaps_bright_star,
    _foreground_close_stars,
    _foreground_double_star_marks,
    _foreground_star_double_marks,
    _foreground_stars_over_dsos,
    draw_chart_page,
    render_chart,
    render_edition_magnitude_scale,
    render_magnitude_scale,
)
from nightsky_atlas.render.double_stars import DoubleStarMark
from nightsky_atlas.render.symbols import DsoShape, StarSizeModel, dso_symbol_extent
from nightsky_atlas.scene.builder import build_scene, build_star_scene
from nightsky_atlas.scene.models import ChartScene, SceneDso, SceneStar
from nightsky_atlas.units import mm_to_pt

REPO_ROOT = Path(__file__).resolve().parents[2]
STYLE = load_style_config(REPO_ROOT / "styles" / "standard.yaml")
PAGE = PageGeometry(width_mm=297.0, height_mm=210.0, margin_mm=12.0)
CHART = ChartDefinition(
    id="test-virgo",
    center_ra_deg=187.5,
    center_dec_deg=12.0,
    width_deg=20.0,
    height_deg=14.0,
)


def build_artifacts():
    stars = load_sample_stars(REPO_ROOT / "data" / "fixtures" / "stars" / "test_virgo.csv")
    scene = build_star_scene(CHART, stars)
    return scene, PageTransform(chart=CHART, page=PAGE)


def png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def test_render_chart_writes_pdf_and_png(tmp_path: Path) -> None:
    scene, transform = build_artifacts()
    pdf_path = tmp_path / "chart.pdf"
    png_path = tmp_path / "preview.png"

    render_chart(scene, transform, STYLE, pdf_path=pdf_path, png_path=png_path, png_dpi=72.0)

    pdf_bytes = pdf_path.read_bytes()
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 1000

    expected = (
        round(mm_to_pt(PAGE.width_mm) * 72.0 / 72.0),
        round(mm_to_pt(PAGE.height_mm) * 72.0 / 72.0),
    )
    assert png_dimensions(png_path) == expected


def test_render_chart_pdf_only(tmp_path: Path) -> None:
    scene, transform = build_artifacts()
    pdf_path = tmp_path / "chart.pdf"
    render_chart(scene, transform, STYLE, pdf_path=pdf_path)
    assert pdf_path.exists()
    assert not (tmp_path / "preview.png").exists()


def test_render_chart_requires_an_output() -> None:
    scene, transform = build_artifacts()
    with pytest.raises(ValueError):
        render_chart(scene, transform, STYLE)


def test_render_chart_with_constellation_lines(tmp_path: Path) -> None:
    stars = load_sample_stars(REPO_ROOT / "data" / "fixtures" / "stars" / "test_virgo.csv")
    segment = ConstellationSegment(
        id="constellation-line:test",
        ra1_deg=187.5,
        dec1_deg=12.0,
        ra2_deg=183.0,
        dec2_deg=8.0,
        provenance=Provenance(catalogue="TEST", source_id="line"),
    )
    scene = build_scene(CHART, stars, constellation_lines=[segment])
    assert scene.constellation_lines
    pdf_path = tmp_path / "chart.pdf"
    png_path = tmp_path / "preview.png"
    render_chart(
        scene,
        PageTransform(chart=CHART, page=PAGE),
        STYLE,
        pdf_path=pdf_path,
        png_path=png_path,
    )
    assert pdf_path.read_bytes().startswith(b"%PDF")
    assert png_path.exists()


def test_render_magnitude_scale(tmp_path: Path) -> None:
    pdf_path = tmp_path / "scale.pdf"
    png_path = tmp_path / "scale.png"
    render_magnitude_scale(
        PAGE,
        STYLE,
        magnitudes=[0, 2, 4, 6, 8, 10],
        pdf_path=pdf_path,
        png_path=png_path,
        png_dpi=72.0,
    )
    assert pdf_path.read_bytes().startswith(b"%PDF")
    assert png_path.exists()


def test_render_magnitude_scale_requires_magnitudes(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        render_magnitude_scale(PAGE, STYLE, magnitudes=[], pdf_path=tmp_path / "x.pdf")


def test_render_edition_magnitude_scale(tmp_path: Path) -> None:
    styles = {
        edition: load_style_config(REPO_ROOT / "styles" / f"{edition}.yaml")
        for edition in ("pocket", "standard", "deep")
    }
    pdf_path = tmp_path / "edition-scale.pdf"
    png_path = tmp_path / "edition-scale.png"
    render_edition_magnitude_scale(
        PAGE,
        styles,
        pdf_path=pdf_path,
        png_path=png_path,
        png_dpi=72.0,
    )
    assert pdf_path.read_bytes().startswith(b"%PDF")
    assert png_path.exists()


def make_label(label_id: str, target_id: str, weight: str) -> Label:
    return Label(
        id=label_id,
        target_id=target_id,
        text="X",
        priority=100,
        mandatory=True,
        candidates=(),
        font_weight=weight,
    )


def test_bold_symbol_ids_follow_bold_labels() -> None:
    labels = (
        make_label("label:dso:NGC4486", "NGC4486", "bold"),
        make_label("label:dso:NGC4565", "NGC4565", "normal"),
        make_label("label:star:HIP1", "HIP 1", "bold"),
    )
    assert _bold_symbol_ids(labels) == frozenset({"NGC4486", "HIP 1"})


def test_dso_line_width_uses_bold_width_for_emphasized_objects() -> None:
    assert _dso_line_width_mm(STYLE, bold=True) == pytest.approx(STYLE.dso.bold_line_width_mm)
    assert _dso_line_width_mm(STYLE, bold=False) == pytest.approx(STYLE.dso.line_width_mm)
    assert STYLE.dso.bold_line_width_mm > STYLE.dso.line_width_mm


def _pixel_rgb(surface: cairo.ImageSurface, x_pt: float, y_pt: float) -> tuple[int, int, int]:
    surface.flush()
    stride = surface.get_stride()
    data = surface.get_data()
    offset = round(y_pt) * stride + round(x_pt) * 4
    return data[offset], data[offset + 1], data[offset + 2]


def test_stars_are_clipped_to_the_chart_frame() -> None:
    transform = PageTransform(chart=CHART, page=PAGE)
    star = Star(
        id="edge",
        ra_deg=187.5,
        dec_deg=12.0,
        magnitude=0.0,
        provenance=Provenance(catalogue="TEST", source_id="edge"),
    )
    scene = ChartScene(
        definition=CHART,
        stars=(SceneStar(star, ChartPoint(-CHART.width_deg / 2.0, 0.0)),),
    )
    surface = cairo.ImageSurface(
        cairo.FORMAT_ARGB32,
        round(mm_to_pt(PAGE.width_mm)),
        round(mm_to_pt(PAGE.height_mm)),
    )
    draw_chart_page(cairo.Context(surface), scene, transform, STYLE)

    rect = transform.chart_rect
    y_pt = mm_to_pt(transform.center_page.y_mm)
    inside = _pixel_rgb(surface, mm_to_pt(rect.right_mm) - mm_to_pt(0.3), y_pt)
    outside = _pixel_rgb(surface, mm_to_pt(rect.right_mm) + mm_to_pt(0.6), y_pt)
    assert sum(inside) < 200
    assert sum(outside) > 700


def test_weaker_star_overlapping_bright_star_gets_foreground_halo() -> None:
    transform = PageTransform(chart=CHART, page=PAGE)
    bright = Star("bright", 187.5, 12.0, 0.0, Provenance("TEST", "bright"))
    faint = Star("faint", 187.5, 12.0, 8.0, Provenance("TEST", "faint"))
    scene = ChartScene(
        definition=CHART,
        stars=(
            SceneStar(bright, ChartPoint(0.0, 0.0)),
            SceneStar(faint, ChartPoint(0.05, 0.0)),
        ),
    )
    foreground = _foreground_close_stars(
        scene, transform, StarSizeModel.from_style(STYLE.star), set()
    )
    assert len(foreground) == 1


def test_compact_dso_overlapping_bright_star_keeps_its_knockout() -> None:
    transform = PageTransform(chart=CHART, page=PAGE)
    star = Star("bright", 187.5, 12.0, 2.0, Provenance("TEST", "bright"))
    dso = DeepSkyObject(
        id="NGC0404",
        ra_deg=187.55,
        dec_deg=12.0,
        object_type=DsoType.GALAXY,
        provenance=Provenance("TEST", "NGC0404"),
        major_axis_arcmin=3.4,
        minor_axis_arcmin=3.37,
    )
    scene = build_scene(CHART, (star,), (dso,))
    extent = dso_symbol_extent(dso, mm_per_deg=transform.mm_per_deg, style=STYLE)
    assert _dso_overlaps_bright_star(
        scene.deep_sky_objects[0],
        scene,
        transform,
        StarSizeModel.from_style(STYLE.star),
        extent,
        STYLE,
    )
    surface = cairo.ImageSurface(
        cairo.FORMAT_ARGB32,
        round(mm_to_pt(PAGE.width_mm)),
        round(mm_to_pt(PAGE.height_mm)),
    )
    draw_chart_page(cairo.Context(surface), scene, transform, STYLE)

    dso_point = transform.to_page(scene.deep_sky_objects[0].chart_point)
    assert sum(_pixel_rgb(surface, mm_to_pt(dso_point.x_mm), mm_to_pt(dso_point.y_mm))) > 700


def test_star_overlapping_large_nebula_symbol_is_redrawn_in_foreground() -> None:
    transform = PageTransform(chart=CHART, page=PAGE)
    star = Star("star", 187.5, 12.0, 5.0, Provenance("TEST", "star"))
    nebula = DeepSkyObject(
        id="IC0434",
        ra_deg=187.5,
        dec_deg=12.0,
        object_type=DsoType.BRIGHT_NEBULA,
        provenance=Provenance("TEST", "IC0434"),
        major_axis_arcmin=90.0,
        minor_axis_arcmin=90.0,
    )
    scene = build_scene(CHART, (star,), (nebula,))
    extent = dso_symbol_extent(nebula, mm_per_deg=transform.mm_per_deg, style=STYLE)
    assert not _dso_overlaps_bright_star(
        scene.deep_sky_objects[0],
        scene,
        transform,
        StarSizeModel.from_style(STYLE.star),
        extent,
        STYLE,
    )
    foreground = _foreground_stars_over_dsos(
        scene, transform, StarSizeModel.from_style(STYLE.star), STYLE, set()
    )
    assert foreground == (
        (
            transform.to_page(scene.stars[0].chart_point),
            StarSizeModel.from_style(STYLE.star).radius_mm(5.0),
        ),
    )


def test_bright_nebula_contour_preserves_contour_and_solid_square_fallback(monkeypatch) -> None:
    nebula = DeepSkyObject(
        id="NGC7000",
        ra_deg=187.5,
        dec_deg=12.0,
        object_type=DsoType.BRIGHT_NEBULA,
        provenance=Provenance("TEST", "NGC7000"),
        cross_ids=("C 020",),
    )
    outline = NebulaOutline(
        id="outline:C020",
        dso_id="C020",
        points=((186.5, 11.0), (188.5, 11.0), (188.5, 13.0)),
        provenance=Provenance("TEST", "outline:C020"),
    )
    outlined_scene = build_scene(CHART, (), (nebula,), nebula_outlines=(outline,))
    fallback_scene = build_scene(CHART, (), (nebula,))
    drawn_shapes = []
    monkeypatch.setattr(
        "nightsky_atlas.render.cairo.draw_dso_symbol",
        lambda _cr, _x, _y, extent, _dash: drawn_shapes.append(extent.shape),
    )
    transform = PageTransform(chart=CHART, page=PAGE)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 800, 600)

    draw_chart_page(cairo.Context(surface), outlined_scene, transform, STYLE)
    assert drawn_shapes == []
    draw_chart_page(cairo.Context(surface), fallback_scene, transform, STYLE)
    assert drawn_shapes == [DsoShape.SQUARE]


@pytest.mark.parametrize(
    ("object_type", "expected_shape"),
    (
        (DsoType.BRIGHT_NEBULA, DsoShape.SQUARE),
        (DsoType.DARK_NEBULA, DsoShape.DASHED_SQUARE),
        (DsoType.GALAXY_CLUSTER, DsoShape.DASHED_CIRCLE),
    ),
)
def test_dso_fallback_renderer_uses_requested_symbol(
    monkeypatch, object_type: DsoType, expected_shape: DsoShape
) -> None:
    dso = DeepSkyObject(
        id="TEST-DSO",
        ra_deg=187.5,
        dec_deg=12.0,
        object_type=object_type,
        provenance=Provenance("TEST", "TEST-DSO"),
    )
    scene = build_scene(CHART, (), (dso,))
    drawn_shapes = []
    monkeypatch.setattr(
        "nightsky_atlas.render.cairo.draw_dso_symbol",
        lambda _cr, _x, _y, extent, _dash: drawn_shapes.append(extent.shape),
    )
    transform = PageTransform(chart=CHART, page=PAGE)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 800, 600)

    draw_chart_page(cairo.Context(surface), scene, transform, STYLE)

    assert drawn_shapes == [expected_shape]


def test_supernova_remnant_contours_are_solid(monkeypatch) -> None:
    remnant = DeepSkyObject(
        id="NGC6960",
        ra_deg=187.5,
        dec_deg=12.0,
        object_type=DsoType.SUPERNOVA_REMNANT,
        provenance=Provenance("TEST", "NGC6960"),
    )
    outline = NebulaOutline(
        id="outline:NGC6960",
        dso_id="NGC6960",
        points=((186.5, 11.0), (188.5, 11.0), (188.5, 13.0)),
        provenance=Provenance("TEST", "outline:NGC6960"),
    )
    scene = build_scene(CHART, (), (remnant,), nebula_outlines=(outline,))
    calls = []
    monkeypatch.setattr(
        "nightsky_atlas.render.cairo._draw_segments",
        lambda _cr, _transform, segments, **kwargs: calls.append(
            (tuple(segments), kwargs["dash_mm"])
        ),
    )
    transform = PageTransform(chart=CHART, page=PAGE)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 800, 600)

    _draw_outlines(cairo.Context(surface), transform, scene, STYLE)

    assert len(calls) == 1
    assert calls[0][1] is None
    assert all(not outline.dashed for outline in calls[0][0])


def test_only_dark_nebula_contours_are_dashed(monkeypatch) -> None:
    bright = DeepSkyObject(
        id="NGC7000",
        ra_deg=187.5,
        dec_deg=12.0,
        object_type=DsoType.BRIGHT_NEBULA,
        provenance=Provenance("TEST", "NGC7000"),
    )
    dark = DeepSkyObject(
        id="B168",
        ra_deg=188.0,
        dec_deg=12.0,
        object_type=DsoType.DARK_NEBULA,
        provenance=Provenance("TEST", "B168"),
    )
    scene = build_scene(
        CHART,
        (),
        (bright, dark),
        nebula_outlines=(
            NebulaOutline(
                id="outline:NGC7000",
                dso_id="NGC7000",
                points=((186.5, 11.0), (188.5, 11.0), (188.5, 13.0)),
                provenance=Provenance("TEST", "outline:NGC7000"),
            ),
            NebulaOutline(
                id="outline:B168",
                dso_id="B168",
                points=((187.0, 11.0), (189.0, 11.0), (189.0, 13.0)),
                provenance=Provenance("TEST", "outline:B168"),
            ),
        ),
    )
    calls = []
    monkeypatch.setattr(
        "nightsky_atlas.render.cairo._draw_segments",
        lambda _cr, _transform, segments, **kwargs: calls.append(
            (tuple(segments), kwargs["dash_mm"])
        ),
    )
    transform = PageTransform(chart=CHART, page=PAGE)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 800, 600)

    _draw_outlines(cairo.Context(surface), transform, scene, STYLE)

    solid_ids = {
        outline.dso_id for outlines, dash in calls if dash is None for outline in outlines
    }
    dashed_ids = {
        outline.dso_id for outlines, dash in calls if dash is not None for outline in outlines
    }
    assert solid_ids == {"NGC7000"}
    assert dashed_ids == {"B168"}


def test_equal_brightness_overlapping_stars_get_one_deterministic_halo() -> None:
    transform = PageTransform(chart=CHART, page=PAGE)
    first = Star("A", 187.5, 12.0, 6.0, Provenance("TEST", "A"))
    second = Star("B", 187.5, 12.0, 6.0, Provenance("TEST", "B"))
    scene = ChartScene(
        definition=CHART,
        stars=(
            SceneStar(first, ChartPoint(0.0, 0.0)),
            SceneStar(second, ChartPoint(0.05, 0.0)),
        ),
    )

    foreground = _foreground_close_stars(
        scene, transform, StarSizeModel.from_style(STYLE.star), set()
    )

    assert len(foreground) == 1
    assert foreground[0][0] == transform.to_page(ChartPoint(0.05, 0.0))


def test_overlapping_double_star_markers_get_one_deterministic_halo() -> None:
    size_model = StarSizeModel.from_style(STYLE.star)
    marks = (
        DoubleStarMark(
            system_id="system:wds:A",
            page_point=PagePoint(140.0, 90.0),
            magnitude=6.0,
            marker_length_mm=2.0,
            marker_line_width_mm=0.15,
            star_id="A",
        ),
        DoubleStarMark(
            system_id="system:wds:B",
            page_point=PagePoint(140.2, 90.0),
            magnitude=6.0,
            marker_length_mm=2.0,
            marker_line_width_mm=0.15,
            star_id="B",
        ),
    )

    assert _foreground_double_star_marks(marks, size_model) == (marks[1],)


def test_star_and_double_star_marker_get_one_deterministic_halo() -> None:
    transform = PageTransform(chart=CHART, page=PAGE)
    star = Star("z-star", 187.5, 12.0, 6.0, Provenance("TEST", "z-star"))
    scene = ChartScene(
        definition=CHART,
        stars=(SceneStar(star, ChartPoint(0.0, 0.0)),),
    )
    size_model = StarSizeModel.from_style(STYLE.star)
    mark = DoubleStarMark(
        system_id="system:wds:A",
        page_point=transform.to_page(ChartPoint(0.05, 0.0)),
        magnitude=6.0,
        marker_length_mm=2.0,
        marker_line_width_mm=0.15,
        star_id="double:A",
    )

    foreground_stars, foreground_marks = _foreground_star_double_marks(
        scene, transform, size_model, set(), (mark,)
    )

    expected = (transform.to_page(ChartPoint(0.0, 0.0)), size_model.radius_mm(6.0))
    assert foreground_stars == (expected,)
    assert foreground_marks == ()


def _scene_dso(
    contour_class: GalaxyContourClass | None,
    *,
    object_type: DsoType = DsoType.GALAXY,
) -> SceneDso:
    dso = DeepSkyObject(
        id="NGC0001",
        ra_deg=187.5,
        dec_deg=12.0,
        object_type=object_type,
        provenance=Provenance("TEST", "NGC0001"),
        major_axis_arcmin=2.0,
        minor_axis_arcmin=1.0,
    )
    metadata = DsoMetadata(dso_id=dso.id, galaxy_contour_class=contour_class)
    return SceneDso(dso=dso, chart_point=ChartPoint(0.0, 0.0), metadata=metadata)


def test_galaxy_contour_uses_visibility_class() -> None:
    width, dash = _dso_contour(
        _scene_dso(GalaxyContourClass.FINE), STYLE, frozenset()
    )
    assert width == pytest.approx(STYLE.dso.galaxy_contours.fine.line_width_mm)
    assert dash is None

    dotted = STYLE.dso.galaxy_contours.dotted
    width, dash = _dso_contour(
        _scene_dso(GalaxyContourClass.DOTTED), STYLE, frozenset()
    )
    assert width == pytest.approx(dotted.line_width_mm)
    assert dash == (dotted.dash_mm, dotted.gap_mm)


def test_unclassified_and_non_galaxy_fall_back_to_label_weight() -> None:
    width, dash = _dso_contour(
        _scene_dso(GalaxyContourClass.UNCLASSIFIED), STYLE, frozenset({"NGC0001"})
    )
    assert width == pytest.approx(STYLE.dso.bold_line_width_mm)
    assert dash is None

    width, _ = _dso_contour(
        _scene_dso(None, object_type=DsoType.OPEN_CLUSTER),
        STYLE,
        frozenset({"NGC0001"}),
    )
    assert width == pytest.approx(STYLE.dso.bold_line_width_mm)


def test_galaxy_without_metadata_keeps_neutral_width() -> None:
    dso = DeepSkyObject(
        id="NGC0002",
        ra_deg=187.5,
        dec_deg=12.0,
        object_type=DsoType.GALAXY,
        provenance=Provenance("TEST", "NGC0002"),
        major_axis_arcmin=2.0,
        minor_axis_arcmin=1.0,
    )
    width, dash = _dso_contour(
        SceneDso(dso=dso, chart_point=ChartPoint(0.0, 0.0)), STYLE, frozenset()
    )
    assert width == pytest.approx(STYLE.dso.line_width_mm)
    assert dash is None
