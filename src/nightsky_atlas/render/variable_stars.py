"""Rendering primitives for the atlas's curated variable-star markers."""

from __future__ import annotations

import math
from dataclasses import dataclass

import cairo

from nightsky_atlas.atlas.config import StyleConfig
from nightsky_atlas.catalog.models import Star
from nightsky_atlas.catalog.star_names import hip_number
from nightsky_atlas.chart.page import PagePoint, PageTransform
from nightsky_atlas.render.symbols import StarSizeModel
from nightsky_atlas.scene.models import ChartScene
from nightsky_atlas.units import mm_to_pt

__all__ = ["VariableStarMark", "draw_variable_star_ring", "resolve_variable_star_marks"]


@dataclass(frozen=True, slots=True)
class VariableStarMark:
    """Page-space ring around one selected variable star."""

    star_id: str
    page_point: PagePoint
    stellar_diameter_mm: float


def resolve_variable_star_marks(
    scene: ChartScene,
    transform: PageTransform,
    size_model: StarSizeModel,
    selected_hip_numbers: frozenset[int],
    style: StyleConfig,
    *,
    suppressed_star_ids: frozenset[str] = frozenset(),
) -> tuple[VariableStarMark, ...]:
    """Return markers for selected variables present as ordinary chart stars."""
    if not style.variable_stars.enabled or not selected_hip_numbers:
        return ()
    marks = []
    for scene_star in scene.stars:
        if not isinstance(scene_star.star, Star):
            continue
        if scene_star.star.id in suppressed_star_ids:
            continue
        hip = hip_number(scene_star.star.hip_id)
        if hip not in selected_hip_numbers:
            continue
        marks.append(
            VariableStarMark(
                scene_star.star.id,
                transform.to_page(scene_star.chart_point),
                size_model.diameter_mm(scene_star.star.magnitude),
            )
        )
    return tuple(marks)


def draw_variable_star_ring(
    cr: cairo.Context[cairo.Surface],
    x_mm: float,
    y_mm: float,
    stellar_diameter_mm: float,
    style: StyleConfig,
) -> None:
    """Draw a restrained open ring outside, not over, the stellar disk."""
    marker = style.variable_stars
    if not marker.enabled:
        return
    cr.save()
    cr.set_source_rgb(marker.gray, marker.gray, marker.gray)
    cr.set_line_width(mm_to_pt(marker.line_width_mm))
    cr.new_path()
    cr.arc(
        mm_to_pt(x_mm),
        mm_to_pt(y_mm),
        mm_to_pt(stellar_diameter_mm / 2.0 + marker.ring_gap_mm),
        0.0,
        math.tau,
    )
    cr.stroke()
    cr.restore()
