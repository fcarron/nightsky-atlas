"""Coordinate grid path generation.

Grid lines are generated in chart-plane degrees and mapped to page millimetres.
They are clipped by the renderer to the chart field; labels take priority over
them (``AGENTS.md`` section 5.2 / 14.4).

Coordinate edge labels are *furniture*: they are placed just inside the chart
frame, never collision-routed against sky labels, and drawn beneath them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from nightsky_atlas.atlas.config import StyleConfig
from nightsky_atlas.chart.models import ChartDefinition
from nightsky_atlas.chart.page import PagePoint, PageRect, PageTransform
from nightsky_atlas.projection.base import ProjectionError
from nightsky_atlas.projection.stereographic import StereographicProjection
from nightsky_atlas.render.text import TextMeasurer
from nightsky_atlas.scene.builder import default_projection

__all__ = [
    "GridLabel",
    "GridLine",
    "build_grid",
    "build_grid_labels",
    "format_dec_deg",
    "format_ra_deg",
]

_SAMPLES = 65
_EDGE_MARGIN_DEG = 1.0
_MULTIPLE_TOL = 1e-6


@dataclass(frozen=True, slots=True)
class GridLine:
    """One grid polyline: a meridian (``ra``) or parallel (``dec``)."""

    kind: str
    value_deg: float
    points: tuple[PagePoint, ...]


@dataclass(frozen=True, slots=True)
class GridLabel:
    """A coordinate label placed just inside the chart frame."""

    id: str
    kind: str
    value_deg: float
    text: str
    bounds: PageRect


def format_ra_deg(ra_deg: float) -> str:
    """Format right ascension as ``HHhMMm`` on the 0-24 hour clock."""
    total_minutes = int(round((ra_deg % 360.0) * 4.0)) % (24 * 60)
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours:02d}h{minutes:02d}m"


def format_dec_deg(dec_deg: float) -> str:
    """Format declination as a signed degree value, e.g. ``+12°``."""
    value = round(dec_deg, 3)
    sign = "+" if value >= 0.0 else "-"
    magnitude = abs(value)
    if abs(magnitude - round(magnitude)) < _MULTIPLE_TOL:
        body = f"{magnitude:.0f}"
    else:
        body = f"{magnitude:.1f}"
    return f"{sign}{body}\N{DEGREE SIGN}"


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
        sample_dec_min = dec_min - _EDGE_MARGIN_DEG
        sample_dec_max = dec_max + _EDGE_MARGIN_DEG
        while ra <= ra_limit:
            points = [
                point
                for index in range(_SAMPLES)
                if (
                    point := _project(
                        projector,
                        transform,
                        ra,
                        sample_dec_min
                        + (sample_dec_max - sample_dec_min) * index / (_SAMPLES - 1),
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


def _is_multiple(value: float, step: float) -> bool:
    ratio = value / step
    return abs(ratio - round(ratio)) < _MULTIPLE_TOL


def _clamp(value: float, low: float, high: float) -> float:
    if high < low:
        return low
    return min(max(value, low), high)


def _scan_crossings(
    points: tuple[PagePoint, ...], edge_value: float, axis: str
) -> list[float]:
    """Return perpendicular coordinates where a polyline crosses an edge.

    ``axis == "x"`` scans a vertical edge and returns page ``y`` positions;
    ``axis == "y"`` scans a horizontal edge and returns page ``x`` positions.
    Duplicate crossings at shared vertices are collapsed.
    """
    results: list[float] = []
    for first, second in zip(points, points[1:], strict=False):
        value_a = first.x_mm if axis == "x" else first.y_mm
        value_b = second.x_mm if axis == "x" else second.y_mm
        if value_a == value_b or (value_a - edge_value) * (value_b - edge_value) > 0.0:
            continue
        fraction = (edge_value - value_a) / (value_b - value_a)
        if not 0.0 <= fraction <= 1.0:
            continue
        if axis == "x":
            results.append(first.y_mm + fraction * (second.y_mm - first.y_mm))
        else:
            results.append(first.x_mm + fraction * (second.x_mm - first.x_mm))

    unique: list[float] = []
    seen: set[float] = set()
    for value in results:
        key = round(value, 4)
        if key not in seen:
            seen.add(key)
            unique.append(value)
    return unique


def build_grid_labels(
    definition: ChartDefinition,
    transform: PageTransform,
    style: StyleConfig,
    *,
    lines: tuple[GridLine, ...] | None = None,
) -> tuple[GridLabel, ...]:
    """Build RA/Dec edge labels just inside the chart frame.

    RA labels sit against the top and bottom edges; Dec labels against the left
    and right edges.  The set of labelled lines is controlled by
    ``grid.label_ra_step_deg`` / ``grid.label_dec_step_deg``.  These are
    furniture, not sky labels, so they are not collision-routed.
    """
    grid = style.grid
    if not grid.enabled or not grid.labels_enabled:
        return ()
    if lines is None:
        lines = build_grid(definition, transform, style)

    rect = transform.chart_rect
    measurer = TextMeasurer(style.label.font_family, grid.label_font_size_pt)
    ra_step = grid.label_ra_step_deg or grid.ra_step_deg
    dec_step = grid.label_dec_step_deg or grid.dec_step_deg
    pad = grid.label_padding_mm

    labels: list[GridLabel] = []
    seen_ids: set[str] = set()

    def add(edge: str, kind: str, value_deg: float, text: str, left: float, top: float) -> None:
        label_id = f"grid:{kind}:{value_deg:g}:{edge}"
        if label_id in seen_ids:
            return
        seen_ids.add(label_id)
        metrics = measurer.measure_mm(text)
        labels.append(
            GridLabel(
                id=label_id,
                kind=kind,
                value_deg=value_deg,
                text=text,
                bounds=PageRect(
                    left_mm=left,
                    top_mm=top,
                    width_mm=metrics.width_mm,
                    height_mm=metrics.height_mm,
                ),
            )
        )

    for line in lines:
        if line.kind == "ra":
            if not _is_multiple(line.value_deg, ra_step):
                continue
            text = format_ra_deg(line.value_deg)
            metrics = measurer.measure_mm(text)
            for edge, top in (
                ("top", rect.top_mm + pad),
                ("bottom", rect.bottom_mm - pad - metrics.height_mm),
            ):
                crossings = _scan_crossings(
                    line.points, rect.top_mm if edge == "top" else rect.bottom_mm, "y"
                )
                for x in crossings:
                    if not rect.left_mm <= x <= rect.right_mm:
                        continue
                    left = _clamp(
                        x - metrics.width_mm / 2.0,
                        rect.left_mm + pad,
                        rect.right_mm - pad - metrics.width_mm,
                    )
                    add(edge, "ra", line.value_deg, text, left, top)
        else:
            if not _is_multiple(line.value_deg, dec_step):
                continue
            text = format_dec_deg(line.value_deg)
            metrics = measurer.measure_mm(text)
            for edge, left in (
                ("left", rect.left_mm + pad),
                ("right", rect.right_mm - pad - metrics.width_mm),
            ):
                crossings = _scan_crossings(
                    line.points, rect.left_mm if edge == "left" else rect.right_mm, "x"
                )
                for y in crossings:
                    if not rect.top_mm <= y <= rect.bottom_mm:
                        continue
                    top = _clamp(
                        y - metrics.height_mm / 2.0,
                        rect.top_mm + pad,
                        rect.bottom_mm - pad - metrics.height_mm,
                    )
                    add(edge, "dec", line.value_deg, text, left, top)

    return tuple(labels)
