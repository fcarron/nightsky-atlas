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
from nightsky_atlas.catalog.models import Provenance, Star
from nightsky_atlas.catalog.sample import load_sample_stars
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.chart.page import PageTransform
from nightsky_atlas.layout.models import Label
from nightsky_atlas.projection.base import ChartPoint
from nightsky_atlas.render.cairo import (
    _bold_symbol_ids,
    _dso_line_width_mm,
    _foreground_close_stars,
    draw_chart_page,
    render_chart,
    render_magnitude_scale,
)
from nightsky_atlas.render.symbols import StarSizeModel
from nightsky_atlas.scene.builder import build_scene, build_star_scene
from nightsky_atlas.scene.models import ChartScene, SceneStar
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
