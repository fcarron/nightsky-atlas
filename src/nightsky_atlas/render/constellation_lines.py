"""Page-space preparation of constellation stick-figure lines.

The scene builder projects only the two endpoint stars of a constellation line.
A stick figure is a symbolic connection, not a physical great circle, so the
printed line is a straight segment in the chart plane (``AGENTS.md`` section
12).  This module turns those two-point segments into the actual page strokes,
shortening each end by the radius of the star symbol it meets plus a small gap so
the line stops at the symbol edge instead of running under it to the centre.

An endpoint with no plotted star nearby - a segment clipped at the chart frame,
or a line star below the magnitude limit - is left untrimmed; there is no symbol
for it to avoid.  The decision is made on page distance, so it is consistent
across editions and projections.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from nightsky_atlas.atlas.config import StyleConfig
from nightsky_atlas.chart.page import PagePoint, PageTransform
from nightsky_atlas.render.symbols import StarSizeModel
from nightsky_atlas.scene.models import ChartScene

__all__ = ["ConstellationStroke", "resolve_constellation_lines"]


@dataclass(frozen=True, slots=True)
class ConstellationStroke:
    """A straight constellation line stroke in page millimetres, already trimmed."""

    source_id: str
    start: PagePoint
    end: PagePoint


def _star_grid(
    scene: ChartScene,
    transform: PageTransform,
    size_model: StarSizeModel,
    cell_mm: float,
) -> dict[tuple[int, int], list[tuple[PagePoint, float]]]:
    """Bucket plotted stars by page cell for fast endpoint matching."""
    grid: dict[tuple[int, int], list[tuple[PagePoint, float]]] = {}
    for scene_star in scene.stars:
        point = transform.to_page(scene_star.chart_point)
        key = (int(math.floor(point.x_mm / cell_mm)), int(math.floor(point.y_mm / cell_mm)))
        grid.setdefault(key, []).append(
            (point, size_model.radius_mm(scene_star.star.magnitude))
        )
    return grid


def _endpoint_gap_mm(
    point: PagePoint,
    grid: dict[tuple[int, int], list[tuple[PagePoint, float]]],
    tolerance_mm: float,
    extra_mm: float,
    cell_mm: float,
) -> float | None:
    """Return the trim for a segment endpoint, or ``None`` when no star is near."""
    base_x = int(math.floor(point.x_mm / cell_mm))
    base_y = int(math.floor(point.y_mm / cell_mm))
    nearest: tuple[float, float] | None = None
    for offset_x in (-1, 0, 1):
        for offset_y in (-1, 0, 1):
            for star, radius_mm in grid.get((base_x + offset_x, base_y + offset_y), ()):
                distance = math.hypot(star.x_mm - point.x_mm, star.y_mm - point.y_mm)
                if distance <= tolerance_mm and (nearest is None or distance < nearest[0]):
                    nearest = (distance, radius_mm)
    if nearest is None:
        return None
    return nearest[1] + extra_mm


def resolve_constellation_lines(
    scene: ChartScene,
    transform: PageTransform,
    style: StyleConfig,
) -> tuple[ConstellationStroke, ...]:
    """Return straight, star-trimmed page strokes for the scene's stick figures."""
    config = style.constellation.lines
    if not config.enabled or not scene.constellation_lines:
        return ()

    size_model = StarSizeModel.from_style(style.star)
    tolerance = config.star_match_tolerance_mm
    grid = _star_grid(scene, transform, size_model, tolerance)

    strokes: list[ConstellationStroke] = []
    for segment in scene.constellation_lines:
        start = transform.to_page(segment.points[0])
        end = transform.to_page(segment.points[-1])
        length = math.hypot(end.x_mm - start.x_mm, end.y_mm - start.y_mm)
        if length <= 0.0:
            continue
        unit_x = (end.x_mm - start.x_mm) / length
        unit_y = (end.y_mm - start.y_mm) / length
        start_gap = _endpoint_gap_mm(
            start, grid, tolerance, config.star_gap_extra_mm, tolerance
        )
        end_gap = _endpoint_gap_mm(
            end, grid, tolerance, config.star_gap_extra_mm, tolerance
        )
        start_trim = start_gap if start_gap is not None else 0.0
        end_trim = end_gap if end_gap is not None else 0.0
        if length - start_trim - end_trim <= 0.0:
            continue
        strokes.append(
            ConstellationStroke(
                source_id=segment.source_id,
                start=PagePoint(
                    x_mm=start.x_mm + unit_x * start_trim,
                    y_mm=start.y_mm + unit_y * start_trim,
                ),
                end=PagePoint(
                    x_mm=end.x_mm - unit_x * end_trim,
                    y_mm=end.y_mm - unit_y * end_trim,
                ),
            )
        )
    return tuple(strokes)
