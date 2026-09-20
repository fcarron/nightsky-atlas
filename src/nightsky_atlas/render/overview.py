"""Overview and locator map rendering.

The renderer accepts an already-projected :class:`OverviewMap` and draws
exactly what it contains (``AGENTS.md`` section 16): no catalogue access, no
projection work, no content selection.  Two entry points share the same
geometry:

- :func:`draw_overview_page` renders a full-page pole-centred hemisphere map
  for the front of the atlas, with bright stars, straight constellation lines
  and one trapezoidal cell per chart;
- :func:`draw_locator_inset` renders the compact per-chart inset, emphasizing
  the current cell and (optionally) its immediate neighbours.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import cairo

from nightsky_atlas.atlas.config import LocatorStyle, OverviewStyle, StyleConfig
from nightsky_atlas.atlas.overview import (
    OverviewCell,
    OverviewMap,
    OverviewName,
    OverviewSegment,
)
from nightsky_atlas.chart.models import PageGeometry
from nightsky_atlas.chart.page import PagePoint, PageRect, PageTransform
from nightsky_atlas.chart.presentation import PRODUCT_NAME
from nightsky_atlas.projection.azimuthal import AzimuthalEquidistantProjection
from nightsky_atlas.projection.base import ChartPoint
from nightsky_atlas.render.symbols import StarSizeModel
from nightsky_atlas.render.text import draw_centered_text
from nightsky_atlas.units import mm_to_pt

__all__ = [
    "LocatorInset",
    "OverviewTransform",
    "draw_locator_inset",
    "draw_overview_page",
    "locator_rect",
]

_TWO_PI = 2.0 * math.pi
_CENTRE_LABELS = {"north": "NCP", "south": "SCP"}
_RIM_LABEL_GAP_MM = 4.5
_RIM_LABEL_STEP_HOURS = 2


@dataclass(frozen=True, slots=True)
class OverviewTransform:
    """Map overview-plane degrees onto page millimetres (north up, east left)."""

    center_x_mm: float
    center_y_mm: float
    scale_mm_per_deg: float

    def to_page(self, point: ChartPoint) -> PagePoint:
        return PagePoint(
            x_mm=self.center_x_mm - point.xi_deg * self.scale_mm_per_deg,
            y_mm=self.center_y_mm - point.eta_deg * self.scale_mm_per_deg,
        )


@dataclass(frozen=True, slots=True)
class LocatorInset:
    """The data a per-chart locator inset needs to draw itself."""

    overview: OverviewMap
    current_chart_id: str
    neighbour_ids: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class _DiskStyle:
    """Resolved stroke/text appearance for one disk, page or locator."""

    grid_gray: float
    grid_line_width_mm: float
    show_grid: bool
    boundary_gray: float
    boundary_line_width_mm: float
    constellation_gray: float
    constellation_line_width_mm: float
    footprint_gray: float
    footprint_line_width_mm: float
    neighbour_gray: float
    neighbour_line_width_mm: float
    current_gray: float
    current_line_width_mm: float
    name_gray: float
    name_font_size_pt: float
    code_gray: float
    code_font_size_pt: float
    show_names: bool
    show_stars: bool
    star_gray: float
    star_size_model: StarSizeModel | None


def _page_disk_style(style: StyleConfig) -> _DiskStyle:
    config: OverviewStyle = style.overview
    return _DiskStyle(
        grid_gray=config.grid_gray,
        grid_line_width_mm=config.grid_line_width_mm,
        show_grid=config.show_grid,
        boundary_gray=config.boundary_gray,
        boundary_line_width_mm=config.boundary_line_width_mm,
        constellation_gray=config.constellation_gray,
        constellation_line_width_mm=config.constellation_line_width_mm,
        footprint_gray=config.footprint_gray,
        footprint_line_width_mm=config.footprint_line_width_mm,
        neighbour_gray=config.footprint_gray,
        neighbour_line_width_mm=config.footprint_line_width_mm,
        current_gray=config.footprint_gray,
        current_line_width_mm=config.footprint_line_width_mm,
        name_gray=config.name_gray,
        name_font_size_pt=config.name_font_size_pt,
        code_gray=config.code_gray,
        code_font_size_pt=config.code_font_size_pt,
        show_names=True,
        show_stars=config.show_stars,
        star_gray=config.star_gray,
        star_size_model=StarSizeModel(
            min_diameter_mm=config.star_min_diameter_mm,
            max_diameter_mm=config.star_max_diameter_mm,
            bright_magnitude=config.star_bright_magnitude,
            faint_magnitude=config.star_faint_magnitude,
        ),
    )


def _locator_disk_style(style: StyleConfig) -> _DiskStyle:
    config: LocatorStyle = style.locator
    return _DiskStyle(
        grid_gray=0.92,
        grid_line_width_mm=0.06,
        show_grid=True,
        boundary_gray=config.constellation_gray,
        boundary_line_width_mm=config.constellation_line_width_mm,
        constellation_gray=config.constellation_gray,
        constellation_line_width_mm=config.constellation_line_width_mm,
        footprint_gray=config.footprint_gray,
        footprint_line_width_mm=config.footprint_line_width_mm,
        neighbour_gray=config.neighbour_gray,
        neighbour_line_width_mm=config.neighbour_line_width_mm,
        current_gray=config.current_gray,
        current_line_width_mm=config.current_line_width_mm,
        name_gray=config.footprint_gray,
        name_font_size_pt=0.0,
        code_gray=config.current_gray,
        code_font_size_pt=0.0,
        show_names=False,
        show_stars=False,
        star_gray=0.0,
        star_size_model=None,
    )


def locator_rect(transform: PageTransform, style: StyleConfig) -> PageRect | None:
    """Return the locator inset rectangle inside the chart frame, or ``None``.

    The rectangle is reserved even before an overview exists so chart labels
    avoid it whenever the locator is enabled.
    """
    locator = style.locator
    if not locator.enabled:
        return None
    rect = transform.chart_rect
    size = locator.diameter_mm
    margin = locator.inset_margin_mm
    left = rect.left_mm + margin
    right = rect.right_mm - size - margin
    top = rect.top_mm + margin
    bottom = rect.bottom_mm - size - margin
    if locator.corner == "bottom_right":
        left, top = right, bottom
    elif locator.corner == "top_right":
        left, top = right, top
    elif locator.corner == "top_left":
        left, top = left, top
    else:  # bottom_left
        left, top = left, bottom
    return PageRect(left_mm=left, top_mm=top, width_mm=size, height_mm=size)


def draw_overview_page(
    cr: cairo.Context[cairo.Surface],
    overview: OverviewMap,
    page: PageGeometry,
    style: StyleConfig,
) -> None:
    """Draw a full-page hemisphere overview."""
    config = style.overview
    family = style.label.font_family
    cr.set_source_rgb(1.0, 1.0, 1.0)
    cr.paint()

    title_y = page.margin_mm + config.title_font_size_pt * 0.3528 + 4.0
    subtitle_y = title_y + config.subtitle_font_size_pt * 0.3528 + 2.0
    header_bottom = subtitle_y + 4.0 + _RIM_LABEL_GAP_MM
    available_radius = (page.height_mm - page.margin_mm - header_bottom) / 2.0
    radius_mm = min(config.radius_mm, available_radius)
    center_x = page.width_mm / 2.0
    center_y = header_bottom + radius_mm
    scale = radius_mm / overview.radius_deg
    transform = OverviewTransform(center_x, center_y, scale)

    cr.set_source_rgb(0.1, 0.1, 0.1)
    draw_centered_text(
        cr,
        f"{PRODUCT_NAME} \N{EM DASH} {overview.edition_name}",
        mm_to_pt(center_x),
        mm_to_pt(title_y),
        family,
        config.title_font_size_pt,
    )
    cr.set_source_rgb(0.35, 0.35, 0.35)
    draw_centered_text(
        cr,
        overview.title,
        mm_to_pt(center_x),
        mm_to_pt(subtitle_y),
        family,
        config.subtitle_font_size_pt,
    )

    disk_style = _page_disk_style(style)
    _draw_disk(cr, transform, overview, style, radius_mm, disk_style, None, frozenset())
    _draw_rim_labels(cr, transform, overview, style, radius_mm)
    _draw_centre_marker(cr, transform, overview, style)


def draw_locator_inset(
    cr: cairo.Context[cairo.Surface],
    inset: LocatorInset,
    transform: PageTransform,
    style: StyleConfig,
) -> None:
    """Draw the compact locator inset on a chart page."""
    rect = locator_rect(transform, style)
    if rect is None:
        return
    center_x = rect.left_mm + rect.width_mm / 2.0
    center_y = rect.top_mm + rect.height_mm / 2.0
    radius_mm = rect.width_mm / 2.0
    scale = radius_mm / inset.overview.radius_deg
    overview_transform = OverviewTransform(center_x, center_y, scale)

    cr.save()
    cr.set_source_rgb(1.0, 1.0, 1.0)
    cr.arc(mm_to_pt(center_x), mm_to_pt(center_y), mm_to_pt(radius_mm), 0.0, _TWO_PI)
    cr.fill()
    disk_style = _locator_disk_style(style)
    _draw_disk(
        cr,
        overview_transform,
        inset.overview,
        style,
        radius_mm,
        disk_style,
        inset.current_chart_id,
        inset.neighbour_ids if style.locator.show_neighbours else frozenset(),
    )
    cr.restore()

    locator = style.locator
    cr.set_source_rgb(locator.border_gray, locator.border_gray, locator.border_gray)
    cr.set_line_width(mm_to_pt(locator.border_line_width_mm))
    cr.arc(mm_to_pt(center_x), mm_to_pt(center_y), mm_to_pt(radius_mm), 0.0, _TWO_PI)
    cr.stroke()


def _draw_disk(
    cr: cairo.Context[cairo.Surface],
    transform: OverviewTransform,
    overview: OverviewMap,
    style: StyleConfig,
    radius_mm: float,
    disk_style: _DiskStyle,
    current_chart_id: str | None,
    neighbour_ids: frozenset[str],
) -> None:
    """Draw grid, constellation background, footprints and codes, clipped to the disk."""
    cr.save()
    cr.arc(
        mm_to_pt(transform.center_x_mm),
        mm_to_pt(transform.center_y_mm),
        mm_to_pt(radius_mm),
        0.0,
        _TWO_PI,
    )
    cr.clip()
    if disk_style.show_grid:
        _stroke_segments(
            cr,
            transform,
            overview.grid_segments,
            disk_style.grid_gray,
            disk_style.grid_line_width_mm,
        )
    _stroke_segments(
        cr,
        transform,
        overview.constellation_boundaries,
        disk_style.boundary_gray,
        disk_style.boundary_line_width_mm,
    )
    _stroke_segments(
        cr,
        transform,
        overview.constellation_lines,
        disk_style.constellation_gray,
        disk_style.constellation_line_width_mm,
        weight_ratios={
            weight: style.constellation.lines.width_mm_for(weight)
            / style.constellation.lines.normal_width_mm
            for weight in ("bold", "normal", "thin")
        },
    )
    if disk_style.show_stars:
        _draw_stars(cr, transform, overview, disk_style)
    for cell in overview.cells:
        _draw_cell(
            cr, transform, cell, disk_style, current_chart_id, neighbour_ids
        )
    if disk_style.show_names:
        _draw_names(cr, transform, overview, disk_style, style.label.font_family)
    for cell in overview.cells:
        if disk_style.show_names and cell.label_point is not None:
            page_point = transform.to_page(cell.label_point)
            cr.set_source_rgb(
                disk_style.code_gray, disk_style.code_gray, disk_style.code_gray
            )
            draw_centered_text(
                cr,
                cell.chart_code,
                mm_to_pt(page_point.x_mm),
                mm_to_pt(page_point.y_mm),
                style.label.font_family,
                disk_style.code_font_size_pt,
            )
    cr.restore()


def _draw_stars(
    cr: cairo.Context[cairo.Surface],
    transform: OverviewTransform,
    overview: OverviewMap,
    disk_style: _DiskStyle,
) -> None:
    size_model = disk_style.star_size_model
    if size_model is None:
        return
    tone = min(max(disk_style.star_gray, 0.0), 1.0)
    cr.set_source_rgb(tone, tone, tone)
    for star in overview.stars:
        page_point = transform.to_page(star.point)
        cr.arc(
            mm_to_pt(page_point.x_mm),
            mm_to_pt(page_point.y_mm),
            mm_to_pt(size_model.radius_mm(star.magnitude)),
            0.0,
            _TWO_PI,
        )
        cr.fill()


def _draw_cell(
    cr: cairo.Context[cairo.Surface],
    transform: OverviewTransform,
    cell: OverviewCell,
    disk_style: _DiskStyle,
    current_chart_id: str | None,
    neighbour_ids: frozenset[str],
) -> None:
    if cell.chart_id == current_chart_id:
        gray = disk_style.current_gray
        width = disk_style.current_line_width_mm
    elif cell.chart_id in neighbour_ids:
        gray = disk_style.neighbour_gray
        width = disk_style.neighbour_line_width_mm
    else:
        gray = disk_style.footprint_gray
        width = disk_style.footprint_line_width_mm
    _stroke_cell(cr, transform, cell, gray, width)


def _stroke_cell(
    cr: cairo.Context[cairo.Surface],
    transform: OverviewTransform,
    cell: OverviewCell,
    gray: float,
    width_mm: float,
) -> None:
    if len(cell.polygon) < 3:
        return
    tone = min(max(gray, 0.0), 1.0)
    cr.set_source_rgb(tone, tone, tone)
    cr.set_line_width(mm_to_pt(width_mm))
    _stroke_run(cr, transform, cell.polygon + (cell.polygon[0],))


def _stroke_run(
    cr: cairo.Context[cairo.Surface],
    transform: OverviewTransform,
    points: tuple[ChartPoint, ...],
) -> None:
    if len(points) < 2:
        return
    first = transform.to_page(points[0])
    cr.move_to(mm_to_pt(first.x_mm), mm_to_pt(first.y_mm))
    for point in points[1:]:
        page_point = transform.to_page(point)
        cr.line_to(mm_to_pt(page_point.x_mm), mm_to_pt(page_point.y_mm))
    cr.stroke()


def _stroke_segments(
    cr: cairo.Context[cairo.Surface],
    transform: OverviewTransform,
    segments: tuple[OverviewSegment, ...],
    gray: float,
    width_mm: float,
    *,
    weight_ratios: dict[str, float] | None = None,
) -> None:
    tone = min(max(gray, 0.0), 1.0)
    cr.set_source_rgb(tone, tone, tone)
    cr.set_line_width(mm_to_pt(width_mm))
    for segment in segments:
        if weight_ratios is not None:
            cr.set_line_width(mm_to_pt(width_mm * weight_ratios[segment.weight]))
        _stroke_run(cr, transform, segment.points)


def _draw_names(
    cr: cairo.Context[cairo.Surface],
    transform: OverviewTransform,
    overview: OverviewMap,
    disk_style: _DiskStyle,
    family: str,
) -> None:
    cr.set_source_rgb(
        disk_style.name_gray, disk_style.name_gray, disk_style.name_gray
    )
    for name in overview.constellation_names:
        _draw_name(cr, transform, name, disk_style.name_font_size_pt, family)


def _draw_name(
    cr: cairo.Context[cairo.Surface],
    transform: OverviewTransform,
    name: OverviewName,
    font_size_pt: float,
    family: str,
) -> None:
    page_point = transform.to_page(name.point)
    draw_centered_text(
        cr,
        name.text,
        mm_to_pt(page_point.x_mm),
        mm_to_pt(page_point.y_mm),
        family,
        font_size_pt,
    )


def _draw_rim_labels(
    cr: cairo.Context[cairo.Surface],
    transform: OverviewTransform,
    overview: OverviewMap,
    style: StyleConfig,
    radius_mm: float,
) -> None:
    """Right-ascension hour labels just outside the equator rim."""
    config = style.overview
    projector = AzimuthalEquidistantProjection(
        overview.center_ra_deg, overview.center_dec_deg
    )
    cr.set_source_rgb(0.35, 0.35, 0.35)
    for hour in range(0, 24, _RIM_LABEL_STEP_HOURS):
        point = transform.to_page(projector.project(hour * 15.0, 0.0))
        dx = point.x_mm - transform.center_x_mm
        dy = point.y_mm - transform.center_y_mm
        distance = math.hypot(dx, dy)
        if distance <= 0.0:
            continue
        scale = (radius_mm + _RIM_LABEL_GAP_MM) / distance
        draw_centered_text(
            cr,
            f"{hour}h",
            mm_to_pt(transform.center_x_mm + dx * scale),
            mm_to_pt(transform.center_y_mm + dy * scale),
            style.label.font_family,
            config.subtitle_font_size_pt,
        )


def _draw_centre_marker(
    cr: cairo.Context[cairo.Surface],
    transform: OverviewTransform,
    overview: OverviewMap,
    style: StyleConfig,
) -> None:
    label = _CENTRE_LABELS.get(overview.hemisphere)
    if label is None:
        return
    cr.set_source_rgb(0.35, 0.35, 0.35)
    draw_centered_text(
        cr,
        label,
        mm_to_pt(transform.center_x_mm),
        mm_to_pt(transform.center_y_mm),
        style.label.font_family,
        style.overview.subtitle_font_size_pt,
    )
