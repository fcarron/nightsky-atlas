"""Tests for page-space trimming of straight constellation stick-figure lines."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from nightsky_atlas.atlas.config import load_style_config
from nightsky_atlas.catalog.constellations import ConstellationSegment
from nightsky_atlas.catalog.models import Provenance, Star
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.chart.page import PageTransform
from nightsky_atlas.render.constellation_lines import resolve_constellation_lines
from nightsky_atlas.render.symbols import StarSizeModel
from nightsky_atlas.scene.builder import build_scene

REPO_ROOT = Path(__file__).resolve().parents[2]
STYLE = load_style_config(REPO_ROOT / "styles" / "standard.yaml")
PAGE = PageGeometry(width_mm=297.0, height_mm=210.0, margin_mm=12.0)
DEFINITION = ChartDefinition(
    id="test-lines",
    center_ra_deg=0.0,
    center_dec_deg=0.0,
    width_deg=20.0,
    height_deg=14.0,
)
TRANSFORM = PageTransform(chart=DEFINITION, page=PAGE)


def make_star(star_id: str, ra_deg: float, dec_deg: float, magnitude: float) -> Star:
    return Star(
        id=star_id,
        ra_deg=ra_deg,
        dec_deg=dec_deg,
        magnitude=magnitude,
        provenance=Provenance(catalogue="TEST", source_id=star_id),
    )


def make_segment(
    ra1_deg: float, dec1_deg: float, ra2_deg: float, dec2_deg: float
) -> ConstellationSegment:
    return ConstellationSegment(
        id=f"seg:{ra1_deg}:{dec1_deg}:{ra2_deg}:{dec2_deg}",
        ra1_deg=ra1_deg,
        dec1_deg=dec1_deg,
        ra2_deg=ra2_deg,
        dec2_deg=dec2_deg,
        provenance=Provenance(catalogue="TEST", source_id="seg"),
    )


def resolve(*, stars, lines):
    scene = build_scene(
        DEFINITION, stars, [], constellation_lines=lines
    )
    return resolve_constellation_lines(scene, TRANSFORM, STYLE)


def test_line_endpoints_are_trimmed_by_star_radius_plus_gap() -> None:
    stars = [make_star("s1", 0.5, 0.5, 3.0), make_star("s2", 2.0, 0.5, 6.0)]
    line = make_segment(0.5, 0.5, 2.0, 0.5)
    strokes = resolve(stars=stars, lines=[line])
    assert len(strokes) == 1
    stroke = strokes[0]

    size_model = StarSizeModel.from_style(STYLE.star)
    extra = STYLE.constellation.lines.star_gap_extra_mm
    scene = build_scene(DEFINITION, stars, [], constellation_lines=[line])
    first = TRANSFORM.to_page(scene.stars[0].chart_point)
    second = TRANSFORM.to_page(scene.stars[1].chart_point)
    first_gap = size_model.radius_mm(3.0) + extra
    second_gap = size_model.radius_mm(6.0) + extra

    assert math.hypot(
        stroke.start.x_mm - first.x_mm, stroke.start.y_mm - first.y_mm
    ) == pytest.approx(first_gap)
    assert math.hypot(
        stroke.end.x_mm - second.x_mm, stroke.end.y_mm - second.y_mm
    ) == pytest.approx(second_gap)


def test_line_does_not_start_inside_a_star_symbol() -> None:
    stars = [make_star("s1", 0.5, 0.5, 0.0), make_star("s2", 2.0, 0.5, 6.0)]
    line = make_segment(0.5, 0.5, 2.0, 0.5)
    strokes = resolve(stars=stars, lines=[line])
    size_model = StarSizeModel.from_style(STYLE.star)
    scene = build_scene(DEFINITION, stars, [], constellation_lines=[line])
    first = TRANSFORM.to_page(scene.stars[0].chart_point)
    radius = size_model.radius_mm(0.0)
    distance = math.hypot(strokes[0].start.x_mm - first.x_mm, strokes[0].start.y_mm - first.y_mm)
    assert distance >= radius


def test_unmatched_endpoint_is_left_untrimmed() -> None:
    stars = [make_star("s1", 0.5, 0.5, 3.0)]
    line = make_segment(0.5, 0.5, 1.2, 0.5)
    strokes = resolve(stars=stars, lines=[line])
    assert len(strokes) == 1
    scene = build_scene(DEFINITION, stars, [], constellation_lines=[line])
    end = scene.constellation_lines[0].points[-1]
    end_page = TRANSFORM.to_page(end)
    assert strokes[0].end.x_mm == pytest.approx(end_page.x_mm)
    assert strokes[0].end.y_mm == pytest.approx(end_page.y_mm)


def test_very_short_segment_between_stars_is_dropped() -> None:
    stars = [make_star("s1", 0.0, 0.0, 0.0), make_star("s2", 0.05, 0.0, 0.0)]
    line = make_segment(0.0, 0.0, 0.05, 0.0)
    strokes = resolve(stars=stars, lines=[line])
    assert strokes == ()


def test_disabled_lines_produce_no_strokes() -> None:
    stars = [make_star("s1", 0.5, 0.5, 3.0), make_star("s2", 2.0, 0.5, 6.0)]
    line = make_segment(0.5, 0.5, 2.0, 0.5)
    style = STYLE.model_copy(
        update={
            "constellation": STYLE.constellation.model_copy(
                update={
                    "lines": STYLE.constellation.lines.model_copy(
                        update={"enabled": False}
                    )
                }
            )
        }
    )
    scene = build_scene(DEFINITION, stars, [], constellation_lines=[line])
    assert resolve_constellation_lines(scene, TRANSFORM, style) == ()
