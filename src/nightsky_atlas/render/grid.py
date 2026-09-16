"""Coordinate grid path generation.

Grid lines are generated in chart-plane degrees and mapped to page millimetres.
They are clipped by the renderer to the chart field; labels take priority over
them (``AGENTS.md`` section 5.2 / 14.4).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from nightsky_atlas.atlas.config import StyleConfig
from nightsky_atlas.chart.models import ChartDefinition
from nightsky_atlas.chart.page import PagePoint, PageTransform
from nightsky_atlas.projection.base import ProjectionError
from nightsky_atlas.projection.stereographic import StereographicProjection
from nightsky_atlas.scene.builder import default_projection

__all__ = ["GridLine", "build_grid"]

_SAMPLES = 65


@dataclass(frozen=True, slots=True)
class GridLine:
    """One grid polyline: a meridian (``ra``) or parallel (``dec``)."""

    kind: str
    value_deg: float
    points: tuple[PagePoint, ...]


def _ra_half_width_deg(definition: ChartDefinition) -> float:
    half_height = definition.height_deg / 2.0
    dec_min = definition.center_dec_deg - half_height
    dec_max = definition.center_dec_deg + half_height
    worst = min(89.9, max(abs(dec_min), abs(dec_max)))
    cos_dec = math.cos(math.radians(worst))
    return (definition.width_deg / 2.0) / max(cos_dec, 1e-4)


def _project(
    projector: StereographicProjection,
    transform: PageTransform,
    ra_deg: float,
    dec_deg: float,
) -> PagePoint | None:
    try:
        chart_point = projector.project(ra_deg, dec_deg)
    except ProjectionError:
        return None
    return transform.to_page(chart_point)


def _first_multiple(start: float, step: float) -> float:
    return math.ceil(start / step - 1e-9) * step


def build_grid(
    definition: ChartDefinition,
    transform: PageTransform,
    style: StyleConfig,
) -> tuple[GridLine, ...]:
    """Build RA and Dec grid polylines for a chart."""
    grid = style.grid
    if not grid.enabled:
        return ()

    projector = default_projection(definition)
    half_height = definition.height_deg / 2.0
    dec_min = definition.center_dec_deg - half_height
    dec_max = definition.center_dec_deg + half_height
    ra_half = _ra_half_width_deg(definition)
    lines: list[GridLine] = []

    if ra_half < 180.0:
        ra = _first_multiple(definition.center_ra_deg - ra_half, grid.ra_step_deg)
        ra_limit = definition.center_ra_deg + ra_half + 1e-9
        while ra <= ra_limit:
            points = [
                point
                for index in range(_SAMPLES)
                if (
                    point := _project(
                        projector,
                        transform,
                        ra,
                        dec_min + (dec_max - dec_min) * index / (_SAMPLES - 1),
                    )
                )
                is not None
            ]
            if len(points) >= 2:
                lines.append(GridLine(kind="ra", value_deg=ra, points=tuple(points)))
            ra += grid.ra_step_deg

    dec = _first_multiple(dec_min, grid.dec_step_deg)
    dec_limit = dec_max + 1e-9
    while dec <= dec_limit:
        points = [
            point
            for index in range(_SAMPLES)
            if (
                point := _project(
                    projector,
                    transform,
                    definition.center_ra_deg - ra_half + 2.0 * ra_half * index / (_SAMPLES - 1),
                    dec,
                )
            )
            is not None
        ]
        if len(points) >= 2:
            lines.append(GridLine(kind="dec", value_deg=dec, points=tuple(points)))
        dec += grid.dec_step_deg

    return tuple(lines)