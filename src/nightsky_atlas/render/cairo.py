"""Cairo page renderer.

The renderer is intentionally boring: it accepts a scene, a page transform and
a style, and draws exactly what they specify (``AGENTS.md`` section 16).  It
does not query catalogues, invent labels or make content decisions.

User space is PostScript points so that text sizes are exact; millimetre
geometry is converted with :func:`nightsky_atlas.units.mm_to_pt`.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

import cairo

from nightsky_atlas.atlas.config import StyleConfig
from nightsky_atlas.catalog.models import DsoType
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.chart.page import PageTransform
from nightsky_atlas.layout.models import Label
from nightsky_atlas.render.grid import GridLine, build_grid, build_grid_labels
from nightsky_atlas.render.symbols import (
    DsoShape,
    EllipseGeometry,
    StarSizeModel,
    dso_shape,
    galaxy_ellipse,
)
from nightsky_atlas.render.text import TextMeasurer, draw_centered_text, draw_text
from nightsky_atlas.scene.models import ChartScene, SceneOutline, SceneSegment
from nightsky_atlas.units import mm_to_pt

__all__ = ["DebugOptions", "draw_chart_page", "render_chart", "render_magnitude_scale"]

_DEFAULT_PNG_DPI = 300.0
_POINTS_PER_INCH = 72.0


@dataclass(frozen=True, slots=True)
class DebugOptions:
    """Opt-in diagnostic overlays; never part of a publication PDF."""

    label_boxes: bool = False
    exclusion_zones: bool = False
    element_ids: bool = False
    candidate_points: bool = False


def render_chart(
    scene: ChartScene,
    transform: PageTransform,
    style: StyleConfig,
    *,
    labels: Iterable[Label] = (),
    debug: DebugOptions | None = None,
    pdf_path: str | Path | None = None,
    png_path: str | Path | None = None,
    png_dpi: float = _DEFAULT_PNG_DPI,
) -> None:
    """Render a chart to a vector PDF and/or a PNG preview.

    Labels are supplied by the caller; the renderer never invents or moves
    them.  When a label has no explicit selection the fixed candidate
    preference order is used (first candidate).
    """

    def draw(cr: cairo.Context[cairo.Surface]) -> None:
        draw_chart_page(cr, scene, transform, style, labels=labels, debug=debug)

    _render_outputs(
        transform.page,
        draw,
        pdf_path=pdf_path,
        png_path=png_path,
        png_dpi=png_dpi,
    )


def draw_chart_page(
    cr: cairo.Context[cairo.Surface],
    scene: ChartScene,
    transform: PageTransform,
    style: StyleConfig,
    *,
    labels: Iterable[Label] = (),
    debug: DebugOptions | None = None,
) -> None:
    """Draw one chart page into an existing context, in point units.

    Used both for standalone page rendering and for multi-page atlas PDFs.
    """
    size_model = StarSizeModel.from_style(style.star)
    _draw_background(cr, transform.page)
    grid_lines = _draw_grid(cr, transform, scene.definition, style)
    _draw_constellations(cr, transform, scene, style)
    _draw_chart_border(cr, transform, style)
    _draw_outlines(cr, transform, scene, style)
    _draw_stars(cr, transform, scene, size_model)
    _draw_dsos(cr, transform, scene, style)
    _draw_grid_labels(cr, grid_lines, transform, style)
    _draw_labels(cr, labels, style)
    if debug is not None:
        _draw_debug(cr, transform, scene, labels, style, debug)
    _draw_title(cr, scene, transform.page, style)
    _draw_scale_bar(cr, transform, scene.definition, style)
    _draw_neighbours(cr, scene.definition, transform.page, style)


def render_magnitude_scale(
    page: PageGeometry,
    style: StyleConfig,
    *,
    magnitudes: Iterable[float] | None = None,
    pdf_path: str | Path | None = None,
    png_path: str | Path | None = None,
    png_dpi: float = _DEFAULT_PNG_DPI,
) -> None:
    """Render a diagnostic page showing star size against magnitude."""
    size_model = StarSizeModel.from_style(style.star)
    if magnitudes is None:
        low = math.floor(style.star.bright_magnitude)
        high = math.ceil(style.star.faint_magnitude)
        magnitude_values = tuple(float(value) for value in range(low, high + 1))
    else:
        magnitude_values = tuple(float(value) for value in magnitudes)
    if not magnitude_values:
        raise ValueError("at least one magnitude is required")

    def draw(cr: cairo.Context[cairo.Surface]) -> None:
        cr.set_source_rgb(1.0, 1.0, 1.0)
        cr.paint()

        left = mm_to_pt(page.margin_mm)
        right = mm_to_pt(page.width_mm - page.margin_mm)
        top = mm_to_pt(page.margin_mm)
        bottom = mm_to_pt(page.height_mm - page.margin_mm)

        cr.set_source_rgb(0.0, 0.0, 0.0)
        cr.set_line_width(mm_to_pt(0.2))
        cr.rectangle(left, top, right - left, bottom - top)
        cr.stroke()

        _draw_centered_text(
            cr,
            "NightSky Atlas - star magnitude scale",
            (left + right) / 2.0,
            mm_to_pt(page.margin_mm / 2.0),
            style.label.font_family,
            style.label.font_size_pt,
        )

        cell_width = (right - left) / len(magnitude_values)
        baseline_y = (top + bottom) / 2.0
        for index, magnitude in enumerate(magnitude_values):
            center_x = left + cell_width * (index + 0.5)
            radius = max(mm_to_pt(size_model.radius_mm(magnitude)), mm_to_pt(0.05))
            cr.set_source_rgb(0.0, 0.0, 0.0)
            cr.arc(center_x, baseline_y, radius, 0.0, 2.0 * math.pi)
            cr.fill()
            _draw_centered_text(
                cr,
                f"m={magnitude:g}",
                center_x,
                baseline_y + mm_to_pt(8.0),
                style.label.font_family,
                style.label.font_size_pt,
            )
            _draw_centered_text(
                cr,
                f"{size_model.diameter_mm(magnitude):.2f} mm",
                center_x,
                baseline_y + mm_to_pt(11.0),
                style.label.font_family,
                style.label.font_size_pt,
            )

    _render_outputs(page, draw, pdf_path=pdf_path, png_path=png_path, png_dpi=png_dpi)


def _render_outputs(
    page: PageGeometry,
    draw: Callable[[cairo.Context[cairo.Surface]], None],
    *,
    pdf_path: str | Path | None,
    png_path: str | Path | None,
    png_dpi: float,
) -> None:
    if pdf_path is None and png_path is None:
        raise ValueError("at least one of pdf_path or png_path is required")

    if pdf_path is not None:
        path = Path(pdf_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        surface = cairo.PDFSurface(
            str(path), mm_to_pt(page.width_mm), mm_to_pt(page.height_mm)
        )
        context = cairo.Context(surface)
        draw(context)
        surface.finish()

    if png_path is not None:
        path = Path(png_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        scale = png_dpi / _POINTS_PER_INCH
        width_px = round(mm_to_pt(page.width_mm) * scale)
        height_px = round(mm_to_pt(page.height_mm) * scale)
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width_px, height_px)
        context = cairo.Context(surface)
        context.scale(scale, scale)
        draw(context)
        surface.write_to_png(str(path))


def _draw_background(cr: cairo.Context[cairo.Surface], page: PageGeometry) -> None:
    cr.set_source_rgb(1.0, 1.0, 1.0)
    cr.paint()


def _draw_chart_border(
    cr: cairo.Context[cairo.Surface], transform: PageTransform, style: StyleConfig
) -> None:
    rect = transform.chart_rect
    cr.set_source_rgb(0.0, 0.0, 0.0)
    cr.set_line_width(mm_to_pt(style.furniture.chart_border_width_mm))
    cr.rectangle(
        mm_to_pt(rect.left_mm),
        mm_to_pt(rect.top_mm),
        mm_to_pt(rect.width_mm),
        mm_to_pt(rect.height_mm),
    )
    cr.stroke()


def _draw_stars(
    cr: cairo.Context[cairo.Surface],
    transform: PageTransform,
    scene: ChartScene,
    size_model: StarSizeModel,
) -> None:
    cr.set_source_rgb(0.0, 0.0, 0.0)
    for scene_star in scene.stars:
        point = transform.to_page(scene_star.chart_point)
        radius = mm_to_pt(size_model.radius_mm(scene_star.star.magnitude))
        cr.arc(mm_to_pt(point.x_mm), mm_to_pt(point.y_mm), radius, 0.0, 2.0 * math.pi)
        cr.fill()


def _draw_dsos(
    cr: cairo.Context[cairo.Surface],
    transform: PageTransform,
    scene: ChartScene,
    style: StyleConfig,
) -> None:
    cr.set_source_rgb(0.0, 0.0, 0.0)
    cr.set_line_width(mm_to_pt(style.dso.line_width_mm))
    for scene_dso in scene.deep_sky_objects:
        dso = scene_dso.dso
        point = transform.to_page(scene_dso.chart_point)
        x = mm_to_pt(point.x_mm)
        y = mm_to_pt(point.y_mm)
        if dso.object_type == DsoType.GALAXY:
            geometry = galaxy_ellipse(
                dso,
                mm_per_deg=transform.mm_per_deg,
                min_axis_mm=style.dso.min_axis_mm,
                max_axis_mm=style.dso.max_axis_mm,
            )
            if geometry is not None:
                _draw_ellipse(cr, x, y, geometry)
                continue
        _draw_dso_shape(
            cr, x, y, mm_to_pt(style.dso.size_mm), dso_shape(dso.object_type), style.dso.dash_mm
        )


def _draw_ellipse(
    cr: cairo.Context[cairo.Surface], x: float, y: float, geometry: EllipseGeometry
) -> None:
    major_pt = mm_to_pt(geometry.major_mm)
    minor_pt = mm_to_pt(geometry.minor_mm)
    cr.save()
    cr.translate(x, y)
    cr.rotate(geometry.rotation_rad)
    cr.scale(major_pt / 2.0, minor_pt / 2.0)
    cr.arc(0.0, 0.0, 1.0, 0.0, 2.0 * math.pi)
    cr.restore()
    cr.stroke()


def _draw_dso_shape(
    cr: cairo.Context[cairo.Surface],
    cx: float,
    cy: float,
    size_pt: float,
    shape: DsoShape,
    dash_mm: float,
) -> None:
    radius = size_pt / 2.0
    cr.save()
    if shape in (DsoShape.DASHED_CIRCLE, DsoShape.DASHED_SQUARE):
        cr.set_dash([mm_to_pt(dash_mm), mm_to_pt(dash_mm)], 0.0)
    if shape in (
        DsoShape.CIRCLE,
        DsoShape.DASHED_CIRCLE,
        DsoShape.CIRCLE_CROSS,
        DsoShape.SPOKED_CIRCLE,
    ):
        cr.arc(cx, cy, radius, 0.0, 2.0 * math.pi)
        cr.stroke()
    if shape in (DsoShape.SQUARE, DsoShape.DASHED_SQUARE):
        cr.rectangle(cx - radius, cy - radius, 2.0 * radius, 2.0 * radius)
        cr.stroke()
    if shape == DsoShape.DOT:
        cr.arc(cx, cy, radius, 0.0, 2.0 * math.pi)
        cr.fill()
    if shape == DsoShape.CIRCLE_CROSS:
        reach = radius * 1.4
        cr.move_to(cx - reach, cy)
        cr.line_to(cx + reach, cy)
        cr.move_to(cx, cy - reach)
        cr.line_to(cx, cy + reach)
        cr.stroke()
    if shape == DsoShape.SPOKED_CIRCLE:
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            cr.move_to(cx + dx * radius, cy + dy * radius)
            cr.line_to(cx + dx * radius * 1.5, cy + dy * radius * 1.5)
        cr.stroke()
    cr.restore()


def _draw_labels(
    cr: cairo.Context[cairo.Surface],
    labels: Iterable[Label],
    style: StyleConfig,
) -> None:
    for label in sorted(labels, key=lambda item: (item.priority, item.id)):
        if label.hidden:
            continue
        candidate = label.selected_candidate()
        if candidate is None and label.candidates:
            candidate = label.candidates[0]
        if candidate is None:
            continue
        cr.set_source_rgb(0.0, 0.0, 0.0)
        draw_text(
            cr,
            label.text,
            mm_to_pt(candidate.bounds.left_mm),
            mm_to_pt(candidate.bounds.top_mm),
            style.label.font_family,
            style.label.font_size_pt,
        )


def _draw_debug(
    cr: cairo.Context[cairo.Surface],
    transform: PageTransform,
    scene: ChartScene,
    labels: Iterable[Label],
    style: StyleConfig,
    debug: DebugOptions,
) -> None:
    cr.set_line_width(mm_to_pt(0.1))

    if debug.exclusion_zones:
        cr.set_source_rgb(0.15, 0.35, 0.9)
        for scene_dso in scene.deep_sky_objects:
            point = transform.to_page(scene_dso.chart_point)
            radius = style.dso.size_mm / 2.0
            geometry = galaxy_ellipse(
                scene_dso.dso,
                mm_per_deg=transform.mm_per_deg,
                min_axis_mm=style.dso.min_axis_mm,
                max_axis_mm=style.dso.max_axis_mm,
            )
            if geometry is not None:
                radius = geometry.major_mm / 2.0
            cr.arc(mm_to_pt(point.x_mm), mm_to_pt(point.y_mm), mm_to_pt(radius), 0.0, 2.0 * math.pi)
            cr.stroke()

    label_list = tuple(labels)

    if debug.candidate_points:
        cr.set_source_rgb(0.1, 0.6, 0.1)
        for label in label_list:
            for candidate in label.candidates:
                center = candidate.bounds.center
                cr.arc(
                    mm_to_pt(center.x_mm),
                    mm_to_pt(center.y_mm),
                    mm_to_pt(0.2),
                    0.0,
                    2.0 * math.pi,
                )
                cr.fill()

    if debug.label_boxes:
        cr.set_source_rgb(0.9, 0.1, 0.1)
        for label in label_list:
            if label.hidden:
                continue
            candidate = label.selected_candidate()
            if candidate is None and label.candidates:
                candidate = label.candidates[0]
            if candidate is None:
                continue
            bounds = candidate.bounds
            cr.rectangle(
                mm_to_pt(bounds.left_mm),
                mm_to_pt(bounds.top_mm),
                mm_to_pt(bounds.width_mm),
                mm_to_pt(bounds.height_mm),
            )
            cr.stroke()

    if debug.element_ids:
        cr.set_source_rgb(0.8, 0.0, 0.0)
        for label in label_list:
            if label.hidden:
                continue
            candidate = label.selected_candidate()
            if candidate is None and label.candidates:
                candidate = label.candidates[0]
            if candidate is None:
                continue
            draw_text(
                cr,
                label.id,
                mm_to_pt(candidate.bounds.left_mm),
                mm_to_pt(candidate.bounds.top_mm) - mm_to_pt(2.5),
                style.label.font_family,
                4.0,
            )


def _draw_constellations(
    cr: cairo.Context[cairo.Surface],
    transform: PageTransform,
    scene: ChartScene,
    style: StyleConfig,
) -> None:
    config = style.constellation
    if config.boundaries.enabled and scene.constellation_boundaries:
        _draw_segments(
            cr,
            transform,
            scene.constellation_boundaries,
            gray=config.boundaries.gray,
            line_width_mm=config.boundaries.line_width_mm,
            dash_mm=(config.boundaries.dash_mm, config.boundaries.gap_mm),
        )
    if config.lines.enabled and scene.constellation_lines:
        _draw_segments(
            cr,
            transform,
            scene.constellation_lines,
            gray=config.lines.gray,
            line_width_mm=config.lines.line_width_mm,
            dash_mm=None,
        )


def _draw_outlines(
    cr: cairo.Context[cairo.Surface],
    transform: PageTransform,
    scene: ChartScene,
    style: StyleConfig,
) -> None:
    if not scene.nebula_outlines:
        return
    _draw_segments(
        cr,
        transform,
        scene.nebula_outlines,
        gray=style.dso.outline_gray,
        line_width_mm=style.dso.outline_line_width_mm,
        dash_mm=(style.dso.outline_dash_mm, style.dso.outline_dash_mm),
    )


def _draw_segments(
    cr: cairo.Context[cairo.Surface],
    transform: PageTransform,
    segments: Iterable[SceneSegment | SceneOutline],
    *,
    gray: float,
    line_width_mm: float,
    dash_mm: tuple[float, float] | None,
) -> None:
    rect = transform.chart_rect
    tone = min(max(gray, 0.0), 1.0)
    cr.save()
    cr.rectangle(
        mm_to_pt(rect.left_mm),
        mm_to_pt(rect.top_mm),
        mm_to_pt(rect.width_mm),
        mm_to_pt(rect.height_mm),
    )
    cr.clip()
    cr.set_source_rgb(tone, tone, tone)
    cr.set_line_width(mm_to_pt(line_width_mm))
    if dash_mm is not None:
        cr.set_dash([mm_to_pt(dash_mm[0]), mm_to_pt(dash_mm[1])], 0.0)
    for segment in segments:
        for index, chart_point in enumerate(segment.points):
            point = transform.to_page(chart_point)
            if index == 0:
                cr.move_to(mm_to_pt(point.x_mm), mm_to_pt(point.y_mm))
            else:
                cr.line_to(mm_to_pt(point.x_mm), mm_to_pt(point.y_mm))
        cr.stroke()
    cr.restore()


def _draw_grid(
    cr: cairo.Context[cairo.Surface],
    transform: PageTransform,
    definition: ChartDefinition,
    style: StyleConfig,
) -> tuple[GridLine, ...]:
    if not style.grid.enabled:
        return ()
    lines = build_grid(definition, transform, style)
    if not lines:
        return ()
    rect = transform.chart_rect
    cr.save()
    cr.rectangle(
        mm_to_pt(rect.left_mm),
        mm_to_pt(rect.top_mm),
        mm_to_pt(rect.width_mm),
        mm_to_pt(rect.height_mm),
    )
    cr.clip()
    gray = min(max(style.grid.gray, 0.0), 1.0)
    cr.set_source_rgb(gray, gray, gray)
    cr.set_line_width(mm_to_pt(style.grid.line_width_mm))
    for line in lines:
        for index, point in enumerate(line.points):
            if index == 0:
                cr.move_to(mm_to_pt(point.x_mm), mm_to_pt(point.y_mm))
            else:
                cr.line_to(mm_to_pt(point.x_mm), mm_to_pt(point.y_mm))
        cr.stroke()
    cr.restore()
    return lines


def _draw_grid_labels(
    cr: cairo.Context[cairo.Surface],
    lines: tuple[GridLine, ...],
    transform: PageTransform,
    style: StyleConfig,
) -> None:
    if not lines:
        return
    labels = build_grid_labels(transform.chart, transform, style, lines=lines)
    if not labels:
        return
    gray = min(max(style.grid.label_gray, 0.0), 1.0)
    cr.set_source_rgb(gray, gray, gray)
    for label in labels:
        draw_text(
            cr,
            label.text,
            mm_to_pt(label.bounds.left_mm),
            mm_to_pt(label.bounds.top_mm),
            style.label.font_family,
            style.grid.label_font_size_pt,
        )


def _draw_scale_bar(
    cr: cairo.Context[cairo.Surface],
    transform: PageTransform,
    definition: ChartDefinition,
    style: StyleConfig,
) -> None:
    length_mm = style.furniture.scale_bar_length_deg * transform.mm_per_deg
    if length_mm <= 0.0:
        return
    page = transform.page
    bar_left = mm_to_pt(page.width_mm / 2.0) - mm_to_pt(length_mm) / 2.0
    bar_right = bar_left + mm_to_pt(length_mm)
    bar_y = mm_to_pt(page.height_mm - page.margin_mm / 2.0)
    tick = mm_to_pt(1.2)
    cr.set_source_rgb(0.0, 0.0, 0.0)
    cr.set_line_width(mm_to_pt(style.furniture.scale_bar_thickness_mm))
    cr.move_to(bar_left, bar_y)
    cr.line_to(bar_right, bar_y)
    cr.move_to(bar_left, bar_y - tick / 2.0)
    cr.line_to(bar_left, bar_y + tick / 2.0)
    cr.move_to(bar_right, bar_y - tick / 2.0)
    cr.line_to(bar_right, bar_y + tick / 2.0)
    cr.stroke()
    draw_text(
        cr,
        f"{style.furniture.scale_bar_length_deg:g} deg",
        bar_left,
        bar_y - mm_to_pt(4.0),
        style.label.font_family,
        style.furniture.scale_font_size_pt,
    )


def _draw_neighbours(
    cr: cairo.Context[cairo.Surface],
    definition: ChartDefinition,
    page: PageGeometry,
    style: StyleConfig,
) -> None:
    neighbours = definition.neighbours
    if not neighbours:
        return
    size = style.furniture.scale_font_size_pt
    family = style.label.font_family
    measurer = TextMeasurer(family, size)
    margin = page.margin_mm
    inset = 2.0
    for direction, label in neighbours:
        text = f"{direction}: {label}"
        if direction == "N":
            draw_centered_text(
                cr, text, mm_to_pt(page.width_mm / 2.0), mm_to_pt(margin + inset), family, size
            )
        elif direction == "S":
            draw_centered_text(
                cr,
                text,
                mm_to_pt(page.width_mm / 2.0),
                mm_to_pt(page.height_mm - margin - inset),
                family,
                size,
            )
        elif direction == "E":
            draw_text(
                cr,
                text,
                mm_to_pt(margin + inset),
                mm_to_pt(page.height_mm / 2.0),
                family,
                size,
            )
        elif direction == "W":
            width_mm = measurer.measure_mm(text).width_mm
            draw_text(
                cr,
                text,
                mm_to_pt(page.width_mm - margin - inset - width_mm),
                mm_to_pt(page.height_mm / 2.0),
                family,
                size,
            )


def _draw_title(
    cr: cairo.Context[cairo.Surface],
    scene: ChartScene,
    page: PageGeometry,
    style: StyleConfig,
) -> None:
    title = f"NightSky Atlas - {scene.definition.atlas_id} - {scene.definition.id}"
    _draw_centered_text(
        cr,
        title,
        mm_to_pt(page.width_mm / 2.0),
        mm_to_pt(page.margin_mm / 2.0),
        style.label.font_family,
        style.furniture.title_font_size_pt,
    )


def _draw_centered_text(
    cr: cairo.Context[cairo.Surface],
    text: str,
    center_x_pt: float,
    center_y_pt: float,
    font_family: str,
    font_size_pt: float,
) -> None:
    cr.set_source_rgb(0.0, 0.0, 0.0)
    draw_centered_text(cr, text, center_x_pt, center_y_pt, font_family, font_size_pt)