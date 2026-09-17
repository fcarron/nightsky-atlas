"""Tests for the Cairo renderer.

These tests intentionally avoid fragile byte comparisons of the whole PDF
(``AGENTS.md`` section 24.2).  They check that valid artifacts are produced and
that raster dimensions follow from physical page size and resolution.
"""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from nightsky_atlas.atlas.config import load_style_config
from nightsky_atlas.catalog.sample import load_sample_stars
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.chart.page import PageTransform
from nightsky_atlas.layout.models import Label
from nightsky_atlas.render.cairo import (
    _bold_symbol_ids,
    _dso_line_width_mm,
    render_chart,
    render_magnitude_scale,
)
from nightsky_atlas.scene.builder import build_star_scene
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
    assert _dso_line_width_mm(STYLE, bold=True) == pytest.approx(
        STYLE.dso.bold_line_width_mm
    )
    assert _dso_line_width_mm(STYLE, bold=False) == pytest.approx(
        STYLE.dso.line_width_mm
    )
    assert STYLE.dso.bold_line_width_mm > STYLE.dso.line_width_mm
