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
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.chart.page import PagePoint, PageRect, PageTransform
from nightsky_atlas.chart.presentation import (
    PRODUCT_NAME,
    ChartPresentation,
    presentation_for,
)
from nightsky_atlas.layout.geometry import expand_rect
from nightsky_atlas.layout.models import Label
from nightsky_atlas.render.constellation_lines import resolve_constellation_lines
from nightsky_atlas.render.double_stars import DoubleStarMark, resolve_double_stars
from nightsky_atlas.render.ecliptic import build_ecliptic
from nightsky_atlas.render.furniture import build_furniture_plan, draw_furniture
from nightsky_atlas.render.grid import GridLine, build_grid, build_grid_labels
from nightsky_atlas.render.overview import LocatorInset, draw_locator_inset
from nightsky_atlas.render.symbols import (
    CIRCLE_CROSS_REACH_FACTOR,
    SPOKED_CIRCLE_INNER_FACTOR,
    SPOKED_CIRCLE_OUTER_FACTOR,
    DsoShape,
    StarSizeModel,
    SymbolExtent,
    dso_symbol_extent,
)
from nightsky_atlas.render.text import draw_centered_text, draw_text
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
    line_knockouts: bool = False


def render_chart(
    scene: ChartScene,
    transform: PageTransform,
    style: StyleConfig,
    *,
    labels: Iterable[Label] = (),
    debug: DebugOptions | None = None,
    presentation: ChartPresentation | None = None,
    locator: LocatorInset | None = None,
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
        draw_chart_page(
            cr,
            scene,
            transform,
            style,
            labels=labels,
            debug=debug,
            presentation=presentation,
            locator=locator,
        )

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
    presentation: ChartPresentation | None = None,
    locator: LocatorInset | None = None,
) -> None:
    """Draw one chart page into an existing context, in point units.

    Used both for standalone page rendering and for multi-page atlas PDFs.
    """
    size_model = StarSizeModel.from_style(style.star)
    label_list = tuple(labels)
    bold_symbol_ids = _bold_symbol_ids(label_list)
    if presentation is None:
        presentation = presentation_for(scene.definition)
    plan = build_furniture_plan(transform, scene.definition, style, presentation)
    _draw_background(cr, transform.page)
    grid_lines = _draw_grid(cr, transform, scene.definition, style)
    _draw_ecliptic(cr, transform, scene.definition, style)
    _draw_constellations(cr, transform, scene, style, label_list)
    _draw_chart_border(cr, transform, style)
    _draw_outlines(cr, transform, scene, style)
    _draw_stars(cr, transform, scene, size_model, style)
    _draw_dsos(cr, transform, scene, style, bold_symbol_ids)
    _draw_grid_labels(cr, grid_lines, transform, style, scene.definition, obstacles=plan.obstacles)
    _draw_labels(cr, label_list, style)
    if locator is not None:
        draw_locator_inset(cr, locator, transform, style)
    if debug is not None:
        _draw_debug(cr, transform, scene, label_list, style, debug)
    draw_furniture(cr, plan, style)


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
            f"{PRODUCT_NAME} \N{EM DASH} star magnitude scale",
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
        surface = cairo.PDFSurface(str(path), mm_to_pt(page.width_mm), mm_to_pt(page.height_mm))
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
    style: StyleConfig,
) -> None:
    """Draw stars, collapsing unseparable double/multiple systems to one marker.

    The close/separate decision is made in
    :func:`~nightsky_atlas.render.double_stars.resolve_double_stars` from the
    printed separation, not here; the renderer only draws what it is told.
    """
    marks = resolve_double_stars(scene, transform, style)
    suppressed: set[str] = set()
    for mark in marks:
        suppressed |= mark.suppress_star_ids

    rect = transform.chart_rect
    cr.save()
    cr.rectangle(
        mm_to_pt(rect.left_mm),
        mm_to_pt(rect.top_mm),
        mm_to_pt(rect.width_mm),
        mm_to_pt(rect.height_mm),
    )
    cr.clip()
    cr.set_source_rgb(0.0, 0.0, 0.0)
    for scene_star in scene.stars:
        if scene_star.star.id in suppressed:
            continue
        point = transform.to_page(scene_star.chart_point)
        radius = mm_to_pt(size_model.radius_mm(scene_star.star.magnitude))
        cr.arc(mm_to_pt(point.x_mm), mm_to_pt(point.y_mm), radius, 0.0, 2.0 * math.pi)
        cr.fill()

    for mark in marks:
        _draw_double_star_mark(cr, mark, size_model)

    for point, radius_mm in _foreground_close_stars(scene, transform, size_model, suppressed):
        cr.set_source_rgb(1.0, 1.0, 1.0)
        cr.arc(
            mm_to_pt(point.x_mm),
            mm_to_pt(point.y_mm),
            mm_to_pt(radius_mm + style.star.close_overlap_halo_mm),
            0.0,
            2.0 * math.pi,
        )
        cr.fill()
        cr.set_source_rgb(0.0, 0.0, 0.0)
        cr.arc(mm_to_pt(point.x_mm), mm_to_pt(point.y_mm), mm_to_pt(radius_mm), 0.0, 2.0 * math.pi)
        cr.fill()
    cr.restore()


def _foreground_close_stars(
    scene: ChartScene,
    transform: PageTransform,
    size_model: StarSizeModel,
    suppressed: set[str],
) -> tuple[tuple[PagePoint, float], ...]:
    """Return weaker stars whose mark would otherwise merge into a brighter one."""
    placed = tuple(
        (
            scene_star,
            transform.to_page(scene_star.chart_point),
            size_model.radius_mm(scene_star.star.magnitude),
        )
        for scene_star in scene.stars
        if scene_star.star.id not in suppressed
    )
    foreground = []
    for scene_star, point, radius in placed:
        if any(
            other.star.magnitude < scene_star.star.magnitude
            and math.hypot(point.x_mm - other_point.x_mm, point.y_mm - other_point.y_mm)
            < radius + other_radius
            for other, other_point, other_radius in placed
        ):
            foreground.append((point, radius))
    return tuple(foreground)


def _draw_double_star_mark(
    cr: cairo.Context[cairo.Surface],
    mark: DoubleStarMark,
    size_model: StarSizeModel,
) -> None:
    """Draw one collapsed double star: symbol plus a short horizontal marker."""
    x = mm_to_pt(mark.page_point.x_mm)
    y = mm_to_pt(mark.page_point.y_mm)
    radius = mm_to_pt(size_model.radius_mm(mark.magnitude))
    cr.arc(x, y, radius, 0.0, 2.0 * math.pi)
    cr.fill()
    half_length = mm_to_pt(mark.marker_length_mm) / 2.0
    cr.set_line_width(mm_to_pt(mark.marker_line_width_mm))
    cr.move_to(x - half_length, y)
    cr.line_to(x + half_length, y)
    cr.stroke()


def _bold_symbol_ids(labels: Iterable[Label]) -> frozenset[str]:
    """Return target IDs whose label is bold, so their symbols are bold too."""
    return frozenset(label.target_id for label in labels if label.font_weight == "bold")


def _dso_line_width_mm(style: StyleConfig, *, bold: bool) -> float:
    """Return the deep-sky symbol stroke width for a bold or ordinary object."""
    return style.dso.bold_line_width_mm if bold else style.dso.line_width_mm


def _draw_dsos(
    cr: cairo.Context[cairo.Surface],
    transform: PageTransform,
    scene: ChartScene,
    style: StyleConfig,
    bold_symbol_ids: frozenset[str] = frozenset(),
) -> None:
    cr.set_source_rgb(0.0, 0.0, 0.0)
    rect = transform.chart_rect
    cr.save()
    cr.rectangle(
        mm_to_pt(rect.left_mm),
        mm_to_pt(rect.top_mm),
        mm_to_pt(rect.width_mm),
        mm_to_pt(rect.height_mm),
    )
    cr.clip()
    for scene_dso in scene.deep_sky_objects:
        dso = scene_dso.dso
        bold = dso.id in bold_symbol_ids
        cr.set_line_width(mm_to_pt(_dso_line_width_mm(style, bold=bold)))
        point = transform.to_page(scene_dso.chart_point)
        extent = dso_symbol_extent(dso, mm_per_deg=transform.mm_per_deg, style=style)
        _draw_dso_symbol(cr, mm_to_pt(point.x_mm), mm_to_pt(point.y_mm), extent, style.dso.dash_mm)
    cr.restore()


def _draw_dso_symbol(
    cr: cairo.Context[cairo.Surface],
    x: float,
    y: float,
    extent: SymbolExtent,
    dash_mm: float,
) -> None:
    """Draw one deep-sky symbol from its central extent description."""
    if extent.is_elliptical:
        _draw_ellipse(cr, x, y, extent)
    else:
        _draw_dso_shape(cr, x, y, mm_to_pt(extent.width_mm), extent.shape, dash_mm)


def _draw_ellipse(
    cr: cairo.Context[cairo.Surface], x: float, y: float, extent: SymbolExtent
) -> None:
    major_pt = mm_to_pt(extent.width_mm)
    minor_pt = mm_to_pt(extent.height_mm)
    cr.save()
    cr.translate(x, y)
    cr.rotate(extent.rotation_rad)
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
    outer_radius = size_pt / 2.0
    radius = (
        outer_radius / SPOKED_CIRCLE_OUTER_FACTOR
        if shape == DsoShape.SPOKED_CIRCLE
        else outer_radius
    )
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
        reach = radius * CIRCLE_CROSS_REACH_FACTOR
        cr.move_to(cx - reach, cy)
        cr.line_to(cx + reach, cy)
        cr.move_to(cx, cy - reach)
        cr.line_to(cx, cy + reach)
        cr.stroke()
    if shape == DsoShape.SPOKED_CIRCLE:
        inner = radius * SPOKED_CIRCLE_INNER_FACTOR
        outer = radius * SPOKED_CIRCLE_OUTER_FACTOR
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            cr.move_to(cx + dx * inner, cy + dy * inner)
            cr.line_to(cx + dx * outer, cy + dy * outer)
        cr.stroke()
    cr.restore()


def _draw_labels(
    cr: cairo.Context[cairo.Surface],
    labels: Iterable[Label],
    style: StyleConfig,
) -> None:
    for label in labels:
        if label.hidden:
            continue
        candidate = label.effective_candidate()
        if candidate is None:
            continue
        cr.set_source_rgb(0.0, 0.0, 0.0)
        draw_text(
            cr,
            label.text,
            mm_to_pt(candidate.bounds.left_mm),
            mm_to_pt(candidate.bounds.top_mm),
            style.label.font_family,
            label.font_size_pt if label.font_size_pt is not None else style.label.font_size_pt,
            label.font_weight,
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
            extent = dso_symbol_extent(scene_dso.dso, mm_per_deg=transform.mm_per_deg, style=style)
            cr.arc(
                mm_to_pt(point.x_mm),
                mm_to_pt(point.y_mm),
                mm_to_pt(extent.collision_radius_mm),
                0.0,
                2.0 * math.pi,
            )
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
            candidate = label.effective_candidate()
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

    if debug.line_knockouts:
        cr.set_source_rgb(0.9, 0.45, 0.0)
        for label in label_list:
            if label.hidden or (candidate := label.effective_candidate()) is None:
                continue
            bounds = expand_rect(candidate.bounds, 0.4)
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
            candidate = label.effective_candidate()
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
    labels: tuple[Label, ...] = (),
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
        _draw_constellation_lines(
            cr,
            transform,
            scene,
            style,
            gray=config.lines.gray,
            line_width_mm=config.lines.line_width_mm,
            knockout_bounds=tuple(
                candidate.bounds
                for label in labels
                if not label.hidden
                if (candidate := label.effective_candidate()) is not None
            ),
        )


def _draw_constellation_lines(
    cr: cairo.Context[cairo.Surface],
    transform: PageTransform,
    scene: ChartScene,
    style: StyleConfig,
    *,
    gray: float,
    line_width_mm: float,
    knockout_bounds: tuple[PageRect, ...] = (),
) -> None:
    """Draw straight stick-figure lines, trimmed clear of their star symbols."""
    strokes = resolve_constellation_lines(scene, transform, style, knockout_bounds=knockout_bounds)
    if not strokes:
        return
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
    for stroke in strokes:
        cr.move_to(mm_to_pt(stroke.start.x_mm), mm_to_pt(stroke.start.y_mm))
        cr.line_to(mm_to_pt(stroke.end.x_mm), mm_to_pt(stroke.end.y_mm))
        cr.stroke()
    cr.restore()


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


def _draw_ecliptic(
    cr: cairo.Context[cairo.Surface],
    transform: PageTransform,
    definition: ChartDefinition,
    style: StyleConfig,
) -> None:
    if not style.ecliptic.enabled:
        return
    paths = build_ecliptic(definition, transform)
    if not paths:
        return
    rect = transform.chart_rect
    cr.save()
    cr.rectangle(
        mm_to_pt(rect.left_mm),
        mm_to_pt(rect.top_mm),
        mm_to_pt(rect.width_mm),
        mm_to_pt(rect.height_mm),
    )
    cr.clip()
    gray = min(max(style.ecliptic.gray, 0.0), 1.0)
    cr.set_source_rgb(gray, gray, gray)
    cr.set_line_width(mm_to_pt(style.ecliptic.line_width_mm))
    cr.set_dash([mm_to_pt(style.ecliptic.dash_mm), mm_to_pt(style.ecliptic.gap_mm)])
    for path in paths:
        for index, point in enumerate(path):
            if index == 0:
                cr.move_to(mm_to_pt(point.x_mm), mm_to_pt(point.y_mm))
            else:
                cr.line_to(mm_to_pt(point.x_mm), mm_to_pt(point.y_mm))
        cr.stroke()
    cr.restore()


def _draw_grid_labels(
    cr: cairo.Context[cairo.Surface],
    lines: tuple[GridLine, ...],
    transform: PageTransform,
    style: StyleConfig,
    definition: ChartDefinition,
    *,
    obstacles: tuple[PageRect, ...] = (),
) -> None:
    if not lines:
        return
    labels = build_grid_labels(transform.chart, transform, style, lines=lines, avoid=obstacles)
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
