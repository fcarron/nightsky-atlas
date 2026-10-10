from __future__ import annotations

from pathlib import Path

import cairo

from nightsky_atlas.atlas.config import load_atlas_config, load_style_config
from nightsky_atlas.catalog.models import Provenance, Star
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.chart.page import PageTransform
from nightsky_atlas.projection.base import ChartPoint
from nightsky_atlas.render import cairo as chart_renderer
from nightsky_atlas.render import front_matter
from nightsky_atlas.render.symbols import StarSizeModel
from nightsky_atlas.render.variable_stars import resolve_variable_star_marks
from nightsky_atlas.scene.models import ChartScene, SceneStar

ROOT = Path(__file__).resolve().parents[2]
STYLE = load_style_config(ROOT / "styles" / "standard.yaml")
ATLAS = load_atlas_config(ROOT / "atlas" / "standard.yaml")
PAGE = PageGeometry(297.0, 210.0, 12.0)
CHART = ChartDefinition("variables", 0.0, 0.0, 20.0, 14.0)


def _scene() -> ChartScene:
    star = Star(
        "hip-10826",
        0.0,
        0.0,
        4.0,
        Provenance("TEST", "Mira"),
        hip_id="HIP 10826",
    )
    return ChartScene(CHART, stars=(SceneStar(star, ChartPoint(0.0, 0.0)),))


def test_only_explicit_variable_star_selection_gets_mark() -> None:
    scene = _scene()
    transform = PageTransform(CHART, PAGE)
    marks = resolve_variable_star_marks(
        scene,
        transform,
        StarSizeModel.from_style(STYLE.star),
        frozenset({10826, 14576}),
        STYLE,
    )

    assert len(marks) == 1
    assert marks[0].star_id == "hip-10826"
    assert marks[0].stellar_diameter_mm == StarSizeModel.from_style(STYLE.star).diameter_mm(4.0)


def test_variable_marker_renderer_uses_curated_hip_selection(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        chart_renderer,
        "draw_variable_star_ring",
        lambda cr, x, y, diameter, style: calls.append((x, y, diameter)),
    )
    surface = cairo.RecordingSurface(cairo.CONTENT_COLOR_ALPHA, None)
    chart_renderer.draw_chart_page(
        cairo.Context(surface),
        _scene(),
        PageTransform(CHART, PAGE),
        STYLE,
        variable_star_hips=frozenset({10826}),
    )

    assert len(calls) == 1


def test_field_guide_explains_and_uses_the_production_variable_ring(monkeypatch) -> None:
    labels = []
    rings = []
    monkeypatch.setattr(
        front_matter,
        "_text",
        lambda cr, text, *args, **kwargs: labels.append(text),
    )
    monkeypatch.setattr(
        front_matter,
        "draw_variable_star_ring",
        lambda cr, x, y, diameter, style: rings.append((x, y, diameter)),
    )
    surface = cairo.RecordingSurface(cairo.CONTENT_COLOR_ALPHA, None)
    front_matter.draw_field_guide(
        cairo.Context(surface),
        ATLAS,
        STYLE,
        chart_count=len(ATLAS.charts),
        mm_per_degree=10.0,
    )

    assert len(rings) == 1
    assert (
        "Selected variable stars are ringed; selection is incomplete and current brightness "
        "is not shown."
    ) in labels
