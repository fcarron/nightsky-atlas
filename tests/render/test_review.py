"""Tests for the annotated review image renderer."""

from __future__ import annotations

import struct
from pathlib import Path

from nightsky_atlas.atlas.config import load_style_config
from nightsky_atlas.catalog.models import DeepSkyObject, DsoType, Provenance
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.chart.page import PageTransform
from nightsky_atlas.layout.labels import build_dso_labels
from nightsky_atlas.render.review import render_review_png
from nightsky_atlas.scene.builder import build_scene

REPO_ROOT = Path(__file__).resolve().parents[2]
STYLE = load_style_config(REPO_ROOT / "styles" / "standard.yaml")

CHART = ChartDefinition(
    id="test", center_ra_deg=187.5, center_dec_deg=12.0, width_deg=20.0, height_deg=14.0
)
PAGE = PageGeometry(width_mm=297.0, height_mm=210.0, margin_mm=12.0)
TRANSFORM = PageTransform(chart=CHART, page=PAGE)


def test_render_review_png(tmp_path: Path) -> None:
    dso = DeepSkyObject(
        id="NGC4486",
        ra_deg=187.5,
        dec_deg=12.0,
        object_type=DsoType.GALAXY,
        provenance=Provenance(catalogue="TEST", source_id="NGC4486"),
        magnitude=8.0,
    )
    scene = build_scene(CHART, [], [dso])
    labels = build_dso_labels(scene, TRANSFORM, STYLE)
    path = tmp_path / "review.png"
    render_review_png(scene, TRANSFORM, STYLE, labels, path, png_dpi=72.0)

    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", data[16:24])
    assert width > 0 and height > 0