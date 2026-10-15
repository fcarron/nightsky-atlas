"""Cairo page renderer.

The renderer is intentionally boring: it accepts a scene, a page transform and
a style, and draws exactly what they specify (``AGENTS.md`` section 16).  It
does not query catalogues, invent labels or make content decisions.

User space is PostScript points so that text sizes are exact; millimetre
geometry is converted with :func:`nightsky_atlas.units.mm_to_pt`.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

import cairo

from nightsky_atlas.atlas.config import StyleConfig
from nightsky_atlas.catalog.galaxy_visibility import GalaxyContourClass
from nightsky_atlas.catalog.models import DsoType
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.chart.page import PagePoint, PageRect, PageTransform
from nightsky_atlas.chart.presentation import (
    PRODUCT_NAME,
    ChartPresentation,
    presentation_for,
)
from nightsky_atlas.layout.geometry import expand_rect
from nightsky_atlas.layout.leader_lines import resolve_leader_lines
from nightsky_atlas.layout.models import Label
from nightsky_atlas.layout.text_geometry import candidate_ink_bounds
from nightsky_atlas.projection.base import ChartPoint
from nightsky_atlas.render.constellation_lines import resolve_constellation_lines
from nightsky_atlas.render.detail_markers import DetailMapMarker, draw_detail_markers
from nightsky_atlas.render.double_stars import (
    DoubleStarMark,
    printed_star_obstacles,
    resolve_double_stars,
)
from nightsky_atlas.render.ecliptic import build_ecliptic
from nightsky_atlas.render.furniture import build_furniture_plan, draw_furniture
from nightsky_atlas.render.grid import GridLine, build_grid, build_grid_labels, build_grid_ticks
from nightsky_atlas.render.overview import LocatorInset, draw_locator_inset
from nightsky_atlas.render.pdf_navigation import PdfNavigation
from nightsky_atlas.render.symbols import (
    CIRCLE_CROSS_REACH_FACTOR,
    SPOKED_CIRCLE_INNER_FACTOR,
    SPOKED_CIRCLE_OUTER_FACTOR,
    SPOKED_CIRCLE_SPIKE_WIDTH_FACTOR,
    DsoShape,
    StarSizeModel,
    SymbolExtent,
    dso_symbol_extent,
    star_reference_magnitudes,
)
from nightsky_atlas.render.text import draw_centered_text, draw_text
from nightsky_atlas.render.variable_stars import (
    draw_variable_star_ring,
    resolve_variable_star_marks,
)
from nightsky_atlas.scene.models import (
    ChartScene,
    SceneDso,
    SceneMilkyWayPolygon,
    SceneOutline,
    SceneSegment,
)
from nightsky_atlas.units import mm_to_pt

__all__ = [
    "DebugOptions",
    "draw_dso_symbol",
    "draw_star_disk",
    "draw_chart_page",
    "render_chart",
    "render_magnitude_scale",
    "render_edition_magnitude_scale",
]

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
    detail_markers: tuple[DetailMapMarker, ...] = (),
    variable_star_hips: frozenset[int] = frozenset(),
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
            detail_markers=detail_markers,
            variable_star_hips=variable_star_hips,
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
    pdf_navigation: PdfNavigation | None = None,
    detail_markers: tuple[DetailMapMarker, ...] = (),
    variable_star_hips: frozenset[int] = frozenset(),
) -> None:
    """Draw one chart page into an existing context, in point units.

    Used both for standalone page rendering and for multi-page atlas PDFs.
    """
    size_model = StarSizeModel.from_style(style.star)
    label_list = tuple(labels)
    constellation_labels = tuple(
        label for label in label_list if label.id.startswith("label:constellation:")
    )
    foreground_labels = tuple(label for label in label_list if label not in constellation_labels)
    bold_symbol_ids = _bold_symbol_ids(label_list)
    if presentation is None:
        presentation = presentation_for(scene.definition, scene=scene)
    plan = build_furniture_plan(transform, scene.definition, style, presentation)
    _draw_background(
        cr,
        transform.page,
        color=style.color_atlas.background if style.color_atlas else None,
    )
    _draw_milky_way_contours(cr, transform, scene, style)
    _draw_magellanic_clouds(cr, transform, scene, style)
    _draw_nebula_outline_fills(cr, transform, scene, style)
    grid_lines = _draw_grid(cr, transform, scene.definition, style)
    draw_detail_markers(
        cr,
        detail_markers,
        transform,
        style,
        draw_labels=False,
    )
    _draw_ecliptic(cr, transform, scene.definition, style)
    _draw_constellations(cr, transform, scene, style, label_list)
    _draw_labels(cr, constellation_labels, style)
    _draw_grid_ticks(cr, transform, scene.definition, style)
    _draw_outlines(cr, transform, scene, style)
    _draw_leader_lines(cr, label_list, scene, transform, style)
    _draw_stars(cr, transform, scene, size_model, style)
    _draw_dsos(cr, transform, scene, size_model, style, bold_symbol_ids)
    _draw_filled_dso_outlines(cr, transform, scene, style, bold_symbol_ids)
    _draw_stars_over_dso_symbols(cr, transform, scene, size_model, style)
    _draw_variable_star_marks(
        cr, scene, transform, size_model, style, variable_star_hips
    )
    _draw_grid_labels(cr, grid_lines, transform, style, scene.definition, obstacles=plan.obstacles)
    _draw_labels(cr, foreground_labels, style)
    if locator is not None:
        draw_locator_inset(cr, locator, transform, style)
    if debug is not None:
        _draw_debug(cr, transform, scene, label_list, style, debug)
    draw_furniture(cr, plan, style, pdf_navigation)
    if detail_markers:
        draw_detail_markers(
            cr,
            detail_markers,
            transform,
            style,
            pdf_navigation,
            draw_frames=False,
            occupied_bounds=_detail_marker_obstacles(
                scene, transform, style, label_list
            ),
        )
    _draw_chart_border(cr, transform, style)


def _detail_marker_obstacles(
    scene: ChartScene,
    transform: PageTransform,
    style: StyleConfig,
    labels: tuple[Label, ...],
) -> tuple[PageRect, ...]:
    bounds = [
        candidate_ink_bounds(candidate)
        for label in labels
        if (candidate := label.effective_candidate()) is not None
    ]
    for star in printed_star_obstacles(scene, transform, style):
        radius = star.collision_radius_mm
        bounds.append(
            PageRect(
                star.page_point.x_mm - radius,
                star.page_point.y_mm - radius,
                2.0 * radius,
                2.0 * radius,
            )
        )
    for item in scene.deep_sky_objects:
        if not item.symbol_visible:
            continue
        extent = dso_symbol_extent(
            item.dso,
            mm_per_deg=transform.mm_per_deg,
            style=style,
        )
        radius = extent.collision_radius_mm
        center = transform.to_page(item.chart_point)
        bounds.append(
            PageRect(
                center.x_mm - radius,
                center.y_mm - radius,
                2.0 * radius,
                2.0 * radius,
            )
        )
    return tuple(bounds)


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
        magnitude_values = star_reference_magnitudes(style.star)
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


def render_edition_magnitude_scale(
    page: PageGeometry,
    edition_styles: Mapping[str, StyleConfig],
    *,
    pdf_path: str | Path | None = None,
    png_path: str | Path | None = None,
    png_dpi: float = _DEFAULT_PNG_DPI,
) -> None:
    """Render one A4 sheet comparing the physical star curves of editions.

    The circles use the same :class:`StarSizeModel` used on charts; this is a
    print calibration artifact, not a separately approximated legend.
    """
    if not edition_styles:
        raise ValueError("at least one edition style is required")

    editions = tuple(edition_styles.items())

    def draw(cr: cairo.Context[cairo.Surface]) -> None:
        cr.set_source_rgb(1.0, 1.0, 1.0)
        cr.paint()
        left = mm_to_pt(page.margin_mm)
        right = mm_to_pt(page.width_mm - page.margin_mm)
        top = mm_to_pt(page.margin_mm)
        bottom = mm_to_pt(page.height_mm - page.margin_mm)
        width = right - left

        cr.set_source_rgb(0.0, 0.0, 0.0)
        _draw_centered_text(
            cr,
            f"{PRODUCT_NAME} — edition star-symbol calibration",
            (left + right) / 2.0,
            top,
            editions[0][1].label.font_family,
            editions[0][1].label.font_size_pt,
        )

        block_height = (bottom - top - mm_to_pt(10.0)) / len(editions)
        for index, (edition, style) in enumerate(editions):
            block_top = top + mm_to_pt(8.0) + index * block_height
            model = StarSizeModel.from_style(style.star)
            magnitudes = star_reference_magnitudes(style.star)
            _draw_centered_text(
                cr,
                edition.upper(),
                (left + right) / 2.0,
                block_top,
                style.label.font_family,
                style.label.font_size_pt,
            )
            cell_width = width / len(magnitudes)
            baseline_y = block_top + block_height * 0.46
            for magnitude_index, magnitude in enumerate(magnitudes):
                center_x = left + cell_width * (magnitude_index + 0.5)
                cr.set_source_rgb(0.0, 0.0, 0.0)
                cr.arc(
                    center_x,
                    baseline_y,
                    mm_to_pt(model.radius_mm(magnitude)),
                    0.0,
                    2.0 * math.pi,
                )
                cr.fill()
                _draw_centered_text(
                    cr,
                    f"m={magnitude:g}",
                    center_x,
                    baseline_y + mm_to_pt(7.0),
                    style.label.font_family,
                    style.label.font_size_pt,
                )
                _draw_centered_text(
                    cr,
                    f"{model.diameter_mm(magnitude):.2f} mm",
                    center_x,
                    baseline_y + mm_to_pt(10.0),
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


def _draw_background(
    cr: cairo.Context[cairo.Surface], page: PageGeometry, *, color: str | None = None
) -> None:
    cr.set_source_rgb(*(_hex_rgb(color) if color else (1.0, 1.0, 1.0)))
    cr.paint()


def _hex_rgb(color: str) -> tuple[float, float, float]:
    value = color.removeprefix("#")
    return tuple(int(value[index : index + 2], 16) / 255.0 for index in (0, 2, 4))


def _dso_color(style: StyleConfig, scene_dso: SceneDso) -> str | None:
    palette = style.color_atlas
    if palette is None:
        return None
    dso = scene_dso.dso
    if dso.object_type == DsoType.GALAXY:
        return palette.dso.galaxies
    if dso.object_type in (DsoType.OPEN_CLUSTER, DsoType.GLOBULAR_CLUSTER):
        return palette.dso.clusters
    if dso.object_type == DsoType.PLANETARY_NEBULA:
        return palette.dso.planetary_nebulae
    if dso.object_type == DsoType.BRIGHT_NEBULA:
        if "reflection" in (dso.semantic_subtype or "").casefold():
            return palette.dso.reflection_nebulae
        return palette.dso.bright_nebulae
    if dso.object_type == DsoType.DARK_NEBULA:
        return palette.dso.dark_nebulae
    if dso.object_type == DsoType.SUPERNOVA_REMNANT:
        return palette.dso.supernova_remnants
    return palette.dso.other


def _dso_fill_color(style: StyleConfig, scene_dso: SceneDso) -> str | None:
    """Return a palette fill softened according to existing visibility metadata."""
    color = _dso_color(style, scene_dso)
    palette = style.color_atlas
    if color is None or palette is None:
        return color
    metadata = scene_dso.metadata
    if metadata is None:
        return color

    if scene_dso.dso.object_type == DsoType.GALAXY:
        visibility_class = metadata.galaxy_contour_class
        class_level = {
            GalaxyContourClass.BOLD: 0,
            GalaxyContourClass.NORMAL: 1,
            GalaxyContourClass.FINE: 2,
            GalaxyContourClass.DOTTED: 3,
        }.get(visibility_class)
    else:
        class_level = None

    if class_level is None:
        score = metadata.visual_score
        class_level = 0 if score >= 75 else 1 if score >= 50 else 2 if score >= 25 else 3
    blend = palette.dso_fill_white_blend[class_level]
    if blend == 0.0:
        return color
    red, green, blue = _hex_rgb(color)
    return "#" + "".join(
        f"{round((component * (1.0 - blend) + blend) * 255):02X}"
        for component in (red, green, blue)
    )


def _dso_fill_and_outline_alpha(
    style: StyleConfig, scene_dso: SceneDso, extent: SymbolExtent
) -> tuple[float, float]:
    palette = style.color_atlas
    if (
        palette is None
        or palette.open_cluster_fill is None
        or scene_dso.dso.object_type != DsoType.OPEN_CLUSTER
    ):
        return 1.0, 1.0
    rule = palette.open_cluster_fill
    diameter_mm = max(extent.width_mm, extent.height_mm)
    if diameter_mm <= rule.small_max_diameter_mm:
        return 1.0, 1.0
    if diameter_mm <= rule.medium_max_diameter_mm:
        return rule.medium_fill_alpha, rule.medium_outline_alpha
    return rule.large_fill_alpha, rule.large_outline_alpha


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
    """Draw base-catalogue stars and selected WDS overlay markers."""
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
    star_color = style.color_atlas.stars if style.color_atlas else None
    star_rgb = _hex_rgb(star_color) if star_color else (0.0, 0.0, 0.0)
    cr.set_source_rgb(*star_rgb)
    for scene_star in scene.stars:
        if scene_star.star.id in suppressed:
            continue
        point = transform.to_page(scene_star.chart_point)
        draw_star_disk(
            cr,
            point.x_mm,
            point.y_mm,
            size_model.diameter_mm(scene_star.star.magnitude),
            color=star_rgb,
        )

    for mark in marks:
        _draw_double_star_mark(cr, mark, size_model, color=star_rgb)

    for mark in _foreground_double_star_marks(marks, size_model):
        _draw_double_star_mark(
            cr,
            mark,
            size_model,
            knockout_mm=style.star.close_overlap_halo_mm,
            color=star_rgb,
        )

    marked_members = _marked_double_star_members(scene, marks)
    foreground_stars, foreground_marks = _foreground_star_double_marks(
        scene, transform, size_model, suppressed, marks, marked_members=marked_members
    )
    for mark in foreground_marks:
        _draw_double_star_mark(
            cr,
            mark,
            size_model,
            knockout_mm=style.star.close_overlap_halo_mm,
            color=star_rgb,
        )

    for point, radius_mm in _foreground_close_stars(
        scene, transform, size_model, suppressed, excluded_foreground_ids=marked_members
    ):
        _draw_star_with_halo(
            cr, point, radius_mm, style.star.close_overlap_halo_mm, color=star_rgb
        )
    for point, radius_mm in foreground_stars:
        _draw_star_with_halo(
            cr, point, radius_mm, style.star.close_overlap_halo_mm, color=star_rgb
        )
    cr.restore()


def _draw_variable_star_marks(
    cr: cairo.Context[cairo.Surface],
    scene: ChartScene,
    transform: PageTransform,
    size_model: StarSizeModel,
    style: StyleConfig,
    variable_star_hips: frozenset[int],
) -> None:
    marks = resolve_variable_star_marks(
        scene,
        transform,
        size_model,
        variable_star_hips,
        style,
    )
    rect = transform.chart_rect
    cr.save()
    cr.rectangle(
        mm_to_pt(rect.left_mm),
        mm_to_pt(rect.top_mm),
        mm_to_pt(rect.width_mm),
        mm_to_pt(rect.height_mm),
    )
    cr.clip()
    for mark in marks:
        draw_variable_star_ring(
            cr,
            mark.page_point.x_mm,
            mark.page_point.y_mm,
            mark.stellar_diameter_mm,
            style,
        )
    cr.restore()


def _draw_star_with_halo(
    cr: cairo.Context[cairo.Surface],
    point: PagePoint,
    radius_mm: float,
    halo_mm: float,
    *,
    color: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> None:
    """Draw a foreground star with a paper gap protecting its circular form."""
    cr.set_source_rgb(1.0, 1.0, 1.0)
    cr.arc(
        mm_to_pt(point.x_mm),
        mm_to_pt(point.y_mm),
        mm_to_pt(radius_mm + halo_mm),
        0.0,
        2.0 * math.pi,
    )
    cr.fill()
    cr.set_source_rgb(*color)
    cr.arc(mm_to_pt(point.x_mm), mm_to_pt(point.y_mm), mm_to_pt(radius_mm), 0.0, 2.0 * math.pi)
    cr.fill()


def _foreground_close_stars(
    scene: ChartScene,
    transform: PageTransform,
    size_model: StarSizeModel,
    suppressed: set[str],
    *,
    excluded_foreground_ids: frozenset[str] = frozenset(),
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
        if scene_star.star.id in excluded_foreground_ids:
            continue
        if any(
            (
                other.star.magnitude < scene_star.star.magnitude
                or (
                    math.isclose(other.star.magnitude, scene_star.star.magnitude)
                    and other.star.id < scene_star.star.id
                )
            )
            and math.hypot(point.x_mm - other_point.x_mm, point.y_mm - other_point.y_mm)
            < radius + other_radius
            for other, other_point, other_radius in placed
        ):
            foreground.append((point, radius))
    return tuple(foreground)


def _foreground_stars_over_dsos(
    scene: ChartScene,
    transform: PageTransform,
    size_model: StarSizeModel,
    style: StyleConfig,
    suppressed: set[str],
) -> tuple[tuple[PagePoint, float], ...]:
    """Return stars whose printed mark intersects a DSO symbol's full extent.

    DSO symbols are rendered after the regular star layer.  Repainting just
    these stars above a symbol restores a usable star-hop point without
    changing either catalogue position or the DSO's true angular scale.
    """
    dso_marks = _dso_marks_requiring_foreground(scene, transform, size_model, style)
    foreground = []
    for scene_star in scene.stars:
        if scene_star.star.id in suppressed:
            continue
        point = transform.to_page(scene_star.chart_point)
        radius_mm = size_model.radius_mm(scene_star.star.magnitude)
        if any(
            math.hypot(point.x_mm - dso_point.x_mm, point.y_mm - dso_point.y_mm)
            <= radius_mm + extent.collision_radius_mm
            for dso_point, extent in dso_marks
        ):
            foreground.append((point, radius_mm))
    return tuple(foreground)


def _dso_marks_requiring_foreground(
    scene: ChartScene,
    transform: PageTransform,
    size_model: StarSizeModel,
    style: StyleConfig,
) -> tuple[tuple[PagePoint, SymbolExtent], ...]:
    marks = []
    for item in scene.deep_sky_objects:
        if not item.symbol_visible:
            continue
        extent = dso_symbol_extent(item.dso, mm_per_deg=transform.mm_per_deg, style=style)
        color = _dso_fill_color(style, item)
        if _dso_overlaps_bright_star(item, scene, transform, size_model, extent, style) and (
            color is None or item.dso.object_type == DsoType.GALAXY
        ):
            continue
        marks.append((transform.to_page(item.chart_point), extent))
    return tuple(marks)


def _draw_stars_over_dso_symbols(
    cr: cairo.Context[cairo.Surface],
    transform: PageTransform,
    scene: ChartScene,
    size_model: StarSizeModel,
    style: StyleConfig,
) -> None:
    """Restore real star positions above DSO ink that would otherwise obscure them."""
    marks = resolve_double_stars(scene, transform, style)
    suppressed = {star_id for mark in marks for star_id in mark.suppress_star_ids}
    foreground = _foreground_stars_over_dsos(scene, transform, size_model, style, suppressed)
    dso_marks = _dso_marks_requiring_foreground(scene, transform, size_model, style)
    foreground_marks = tuple(
        mark
        for mark in marks
        if any(
            math.hypot(mark.page_point.x_mm - point.x_mm, mark.page_point.y_mm - point.y_mm)
            <= size_model.radius_mm(mark.magnitude) + extent.collision_radius_mm
            for point, extent in dso_marks
        )
    )
    if not foreground and not foreground_marks:
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
    star_color = style.color_atlas.stars if style.color_atlas else None
    star_rgb = _hex_rgb(star_color) if star_color else (0.0, 0.0, 0.0)
    for point, radius_mm in foreground:
        if _star_halo_overlaps_filled_dso(
            point,
            radius_mm + style.star.close_overlap_halo_mm,
            scene,
            transform,
            style,
        ):
            draw_star_disk(
                cr, point.x_mm, point.y_mm, radius_mm * 2.0, color=star_rgb
            )
        else:
            _draw_star_with_halo(
                cr, point, radius_mm, style.star.close_overlap_halo_mm, color=star_rgb
            )
    for mark in foreground_marks:
        knockout_mm = style.star.close_overlap_halo_mm
        if _star_halo_overlaps_filled_dso(
            mark.page_point,
            knockout_mm + (mark.marker_length_mm + mark.marker_line_width_mm) / 2.0,
            scene,
            transform,
            style,
        ):
            knockout_mm = 0.0
        _draw_double_star_mark(
            cr,
            mark,
            size_model,
            knockout_mm=knockout_mm,
            color=star_rgb,
        )
    cr.restore()


def draw_star_disk(
    cr: cairo.Context[cairo.Surface],
    x_mm: float,
    y_mm: float,
    diameter_mm: float,
    *,
    color: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> None:
    """Draw the circular stellar disk used by charts and the Field Guide."""
    cr.set_source_rgb(*color)
    cr.new_path()
    cr.arc(
        mm_to_pt(x_mm),
        mm_to_pt(y_mm),
        mm_to_pt(diameter_mm / 2.0),
        0.0,
        2.0 * math.pi,
    )
    cr.fill()


def _star_halo_overlaps_filled_dso(
    point: PagePoint,
    radius_mm: float,
    scene: ChartScene,
    transform: PageTransform,
    style: StyleConfig,
) -> bool:
    """Whether a white stellar knockout would cut into a colored DSO fill."""
    for item in scene.deep_sky_objects:
        if not item.symbol_visible or _dso_fill_color(style, item) is None:
            continue
        extent = dso_symbol_extent(item.dso, mm_per_deg=transform.mm_per_deg, style=style)
        center = transform.to_page(item.chart_point)
        dx = point.x_mm - center.x_mm
        dy = point.y_mm - center.y_mm
        if extent.is_elliptical:
            cosine = math.cos(extent.rotation_rad)
            sine = math.sin(extent.rotation_rad)
            local_x = cosine * dx + sine * dy
            local_y = -sine * dx + cosine * dy
            rx = extent.radius_x_mm + radius_mm
            ry = extent.radius_y_mm + radius_mm
            if (local_x / rx) ** 2 + (local_y / ry) ** 2 <= 1.0:
                return True
            continue

        shape = extent.shape
        if shape == DsoShape.X_MARK:
            continue
        symbol_radius = extent.radius_x_mm
        if shape == DsoShape.SPOKED_CIRCLE:
            symbol_radius /= SPOKED_CIRCLE_OUTER_FACTOR
        if shape in (DsoShape.SQUARE, DsoShape.DASHED_SQUARE):
            if abs(dx) <= symbol_radius + radius_mm and abs(dy) <= symbol_radius + radius_mm:
                return True
        elif math.hypot(dx, dy) <= symbol_radius + radius_mm:
            return True
    return False


def _foreground_double_star_marks(
    marks: tuple[DoubleStarMark, ...], size_model: StarSizeModel
) -> tuple[DoubleStarMark, ...]:
    """Return overlapping double-star markers that need a white knockout."""
    foreground = []
    for mark in marks:
        radius = size_model.radius_mm(mark.magnitude)
        if any(
            (
                other.magnitude < mark.magnitude
                or (
                    math.isclose(other.magnitude, mark.magnitude)
                    and other.system_id < mark.system_id
                )
            )
            and math.hypot(
                mark.page_point.x_mm - other.page_point.x_mm,
                mark.page_point.y_mm - other.page_point.y_mm,
            )
            < radius + size_model.radius_mm(other.magnitude)
            for other in marks
        ):
            foreground.append(mark)
    return tuple(foreground)


def _marked_double_star_members(
    scene: ChartScene, marks: tuple[DoubleStarMark, ...]
) -> frozenset[str]:
    pair_ids = {pair_id for mark in marks for pair_id in mark.pair_ids}
    members = {mark.star_id for mark in marks if mark.star_id is not None}
    for scene_system in scene.star_systems:
        if scene_system.system.id in pair_ids:
            members.update(scene_system.system.linked_star_ids())
    return frozenset(members)


def _foreground_star_double_marks(
    scene: ChartScene,
    transform: PageTransform,
    size_model: StarSizeModel,
    suppressed: set[str],
    marks: tuple[DoubleStarMark, ...],
    *,
    marked_members: frozenset[str] = frozenset(),
) -> tuple[tuple[tuple[PagePoint, float], ...], tuple[DoubleStarMark, ...]]:
    """Return the foreground layer for ordinary-star/double-marker overlaps.

    A collapsed double mark is one printed stellar symbol, so it follows the
    same brightness and stable-ID tie break as two ordinary stars.  This keeps
    adjacent marks distinct without changing their astronomical positions.
    """
    foreground_stars = []
    foreground_marks = []
    for scene_star in scene.stars:
        if scene_star.star.id in suppressed or scene_star.star.id in marked_members:
            continue
        point = transform.to_page(scene_star.chart_point)
        radius = size_model.radius_mm(scene_star.star.magnitude)
        for mark in marks:
            mark_radius = max(
                size_model.radius_mm(mark.magnitude),
                (mark.marker_length_mm + mark.marker_line_width_mm) / 2.0,
            )
            if math.hypot(point.x_mm - mark.page_point.x_mm, point.y_mm - mark.page_point.y_mm) >= (
                radius + mark_radius
            ):
                continue
            if mark.magnitude < scene_star.star.magnitude or (
                math.isclose(mark.magnitude, scene_star.star.magnitude)
                and mark.system_id < scene_star.star.id
            ):
                foreground_stars.append((point, radius))
            else:
                foreground_marks.append(mark)
    return tuple(foreground_stars), tuple(foreground_marks)


def _draw_double_star_mark(
    cr: cairo.Context[cairo.Surface],
    mark: DoubleStarMark,
    size_model: StarSizeModel,
    *,
    knockout_mm: float = 0.0,
    color: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> None:
    """Draw one collapsed double star: symbol plus a short horizontal marker."""
    cr.new_path()
    x = mm_to_pt(mark.page_point.x_mm)
    y = mm_to_pt(mark.page_point.y_mm)
    radius = mm_to_pt(size_model.radius_mm(mark.magnitude))
    half_length = mm_to_pt(mark.marker_length_mm) / 2.0
    if knockout_mm > 0.0:
        knockout_pt = mm_to_pt(knockout_mm)
        cr.set_source_rgb(1.0, 1.0, 1.0)
        cr.arc(x, y, radius + knockout_pt, 0.0, 2.0 * math.pi)
        cr.fill()
        cr.set_line_width(mm_to_pt(mark.marker_line_width_mm + 2.0 * knockout_mm))
        cr.move_to(x - half_length - knockout_pt, y)
        cr.line_to(x + half_length + knockout_pt, y)
        cr.stroke()
    cr.set_source_rgb(*color)
    cr.new_path()
    cr.arc(x, y, radius, 0.0, 2.0 * math.pi)
    cr.fill()
    cr.set_line_width(mm_to_pt(mark.marker_line_width_mm))
    cr.new_path()
    cr.move_to(x - half_length, y)
    cr.line_to(x + half_length, y)
    cr.stroke()


def _bold_symbol_ids(labels: Iterable[Label]) -> frozenset[str]:
    """Return target IDs whose label is bold, so their symbols are bold too."""
    return frozenset(label.target_id for label in labels if label.font_weight == "bold")


def _dso_line_width_mm(style: StyleConfig, *, bold: bool) -> float:
    """Return the deep-sky symbol stroke width for a bold or ordinary object."""
    return style.dso.bold_line_width_mm if bold else style.dso.line_width_mm


def _dso_contour(
    scene_dso: SceneDso,
    style: StyleConfig,
    bold_symbol_ids: frozenset[str],
) -> tuple[float, tuple[float, float] | None]:
    """Return the stroke width and optional dash pattern for one DSO symbol.

    Galaxies use the Crumey visibility contour class when it is present in the
    layout metadata: the class sets the stroke weight independently of the label
    hierarchy, so a galaxy may have a bold label but a fine contour.  Every
    other object keeps the existing bold-label stroke rule.
    """
    dso = scene_dso.dso
    if dso.object_type in (DsoType.STAR, DsoType.DOUBLE_STAR):
        return style.dso.line_width_mm, None
    metadata = scene_dso.metadata
    if dso.object_type == DsoType.GALAXY and metadata is not None:
        contour = style.dso.galaxy_contours.for_class(metadata.galaxy_contour_class)
        if contour is not None:
            dash = (
                (contour.dash_mm, contour.gap_mm or contour.dash_mm)
                if contour.dash_mm > 0.0
                else None
            )
            return contour.line_width_mm, dash
    return _dso_line_width_mm(style, bold=dso.id in bold_symbol_ids), None


def _draw_dsos(
    cr: cairo.Context[cairo.Surface],
    transform: PageTransform,
    scene: ChartScene,
    size_model: StarSizeModel,
    style: StyleConfig,
    bold_symbol_ids: frozenset[str] = frozenset(),
) -> None:
    rect = transform.chart_rect
    filled = []
    cr.save()
    cr.rectangle(
        mm_to_pt(rect.left_mm),
        mm_to_pt(rect.top_mm),
        mm_to_pt(rect.width_mm),
        mm_to_pt(rect.height_mm),
    )
    cr.clip()
    for scene_dso in scene.deep_sky_objects:
        if not scene_dso.symbol_visible:
            continue
        dso = scene_dso.dso
        color = _dso_fill_color(style, scene_dso)
        point = transform.to_page(scene_dso.chart_point)
        extent = dso_symbol_extent(dso, mm_per_deg=transform.mm_per_deg, style=style)
        if color is not None:
            fill_alpha, _ = _dso_fill_and_outline_alpha(style, scene_dso, extent)
            filled.append(
                (extent.width_mm * extent.height_mm, scene_dso, color, point, extent, fill_alpha)
            )

    for _, scene_dso, color, point, extent, fill_alpha in sorted(
        filled, key=lambda item: item[0], reverse=True
    ):
        if scene_dso.dso.object_type == DsoType.GALAXY and _dso_overlaps_bright_star(
            scene_dso, scene, transform, size_model, extent, style
        ):
            _draw_dso_knockout(
                cr,
                mm_to_pt(point.x_mm),
                mm_to_pt(point.y_mm),
                extent,
                style.dso.star_overlap_halo_mm,
            )
        cr.set_source_rgb(0.0, 0.0, 0.0)
        cr.set_line_width(mm_to_pt(_dso_contour(scene_dso, style, bold_symbol_ids)[0]))
        draw_dso_symbol(
            cr,
            mm_to_pt(point.x_mm),
            mm_to_pt(point.y_mm),
            extent,
            style.dso.dash_mm,
            fill_color=_hex_rgb(color),
            fill_alpha=fill_alpha,
            fill_only=True,
        )

    for scene_dso in scene.deep_sky_objects:
        if not scene_dso.symbol_visible:
            continue
        dso = scene_dso.dso
        color = _dso_fill_color(style, scene_dso)
        width_mm, dash = _dso_contour(scene_dso, style, bold_symbol_ids)
        extent = dso_symbol_extent(dso, mm_per_deg=transform.mm_per_deg, style=style)
        _, outline_alpha = _dso_fill_and_outline_alpha(style, scene_dso, extent)
        cr.set_source_rgba(0.0, 0.0, 0.0, outline_alpha)
        cr.set_line_width(mm_to_pt(width_mm))
        if dash is not None:
            cr.set_dash([mm_to_pt(dash[0]), mm_to_pt(dash[1])], 0.0)
        else:
            cr.set_dash([], 0.0)
        point = transform.to_page(scene_dso.chart_point)
        if color is None and _dso_overlaps_bright_star(
            scene_dso, scene, transform, size_model, extent, style
        ):
            _draw_dso_knockout(
                cr,
                mm_to_pt(point.x_mm),
                mm_to_pt(point.y_mm),
                extent,
                style.dso.star_overlap_halo_mm,
            )
            cr.set_source_rgb(0.0, 0.0, 0.0)
        draw_dso_symbol(
            cr,
            mm_to_pt(point.x_mm),
            mm_to_pt(point.y_mm),
            extent,
            style.dso.dash_mm,
            outline_only=color is not None,
        )

    cr.restore()


def _draw_filled_dso_outlines(
    cr: cairo.Context[cairo.Surface],
    transform: PageTransform,
    scene: ChartScene,
    style: StyleConfig,
    bold_symbol_ids: frozenset[str] = frozenset(),
) -> None:
    """Redraw filled DSO contours after their fills and before foreground stars."""
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
        if not scene_dso.symbol_visible or _dso_fill_color(style, scene_dso) is None:
            continue
        width_mm, dash = _dso_contour(scene_dso, style, bold_symbol_ids)
        point = transform.to_page(scene_dso.chart_point)
        extent = dso_symbol_extent(
            scene_dso.dso, mm_per_deg=transform.mm_per_deg, style=style
        )
        _, outline_alpha = _dso_fill_and_outline_alpha(style, scene_dso, extent)
        cr.set_source_rgba(0.0, 0.0, 0.0, outline_alpha)
        cr.set_line_width(mm_to_pt(width_mm))
        if dash is not None:
            cr.set_dash([mm_to_pt(dash[0]), mm_to_pt(dash[1])], 0.0)
        else:
            cr.set_dash([], 0.0)
        draw_dso_symbol(
            cr,
            mm_to_pt(point.x_mm),
            mm_to_pt(point.y_mm),
            extent,
            style.dso.dash_mm,
            outline_only=True,
        )
    cr.restore()


def _dso_overlaps_bright_star(
    scene_dso: SceneDso,
    scene: ChartScene,
    transform: PageTransform,
    size_model: StarSizeModel,
    extent: SymbolExtent,
    style: StyleConfig,
) -> bool:
    """Return whether a bright star would make a DSO mark visually disappear."""
    if max(extent.width_mm, extent.height_mm) > style.dso.star_overlap_knockout_max_diameter_mm:
        return False
    point = transform.to_page(scene_dso.chart_point)
    for scene_star in scene.stars:
        if scene_star.star.magnitude > style.dso.star_overlap_magnitude_limit:
            continue
        star_point = transform.to_page(scene_star.chart_point)
        if math.hypot(point.x_mm - star_point.x_mm, point.y_mm - star_point.y_mm) <= (
            extent.collision_radius_mm + size_model.radius_mm(scene_star.star.magnitude)
        ):
            return True
    return False


def _draw_dso_knockout(
    cr: cairo.Context[cairo.Surface],
    x: float,
    y: float,
    extent: SymbolExtent,
    halo_mm: float,
) -> None:
    """Clear enough paper behind a DSO mark for it to remain identifiable."""
    halo_pt = mm_to_pt(halo_mm)
    cr.save()
    cr.set_source_rgb(1.0, 1.0, 1.0)
    if extent.is_elliptical:
        cr.translate(x, y)
        cr.rotate(extent.rotation_rad)
        cr.scale(
            mm_to_pt(extent.width_mm) / 2.0 + halo_pt,
            mm_to_pt(extent.height_mm) / 2.0 + halo_pt,
        )
        cr.arc(0.0, 0.0, 1.0, 0.0, 2.0 * math.pi)
    else:
        cr.arc(x, y, mm_to_pt(extent.collision_radius_mm) + halo_pt, 0.0, 2.0 * math.pi)
    cr.fill()
    cr.restore()


def draw_dso_symbol(
    cr: cairo.Context[cairo.Surface],
    x: float,
    y: float,
    extent: SymbolExtent,
    dash_mm: float,
    *,
    fill_color: tuple[float, float, float] | None = None,
    fill_alpha: float = 1.0,
    fill_only: bool = False,
    outline_only: bool = False,
) -> None:
    """Draw one deep-sky symbol from its central extent description."""
    if extent.is_elliptical:
        _draw_ellipse(
            cr,
            x,
            y,
            extent,
            fill_color=fill_color,
            fill_alpha=fill_alpha,
            fill_only=fill_only,
            outline_only=outline_only,
        )
    else:
        _draw_dso_shape(
            cr,
            x,
            y,
            mm_to_pt(extent.width_mm),
            extent.shape,
            dash_mm,
            fill_color=fill_color,
            fill_alpha=fill_alpha,
            fill_only=fill_only,
            outline_only=outline_only,
        )


def _draw_ellipse(
    cr: cairo.Context[cairo.Surface],
    x: float,
    y: float,
    extent: SymbolExtent,
    *,
    fill_color: tuple[float, float, float] | None = None,
    fill_alpha: float = 1.0,
    fill_only: bool = False,
    outline_only: bool = False,
) -> None:
    major_pt = mm_to_pt(extent.width_mm)
    minor_pt = mm_to_pt(extent.height_mm)
    cr.save()
    cr.translate(x, y)
    cr.rotate(extent.rotation_rad)
    cr.scale(major_pt / 2.0, minor_pt / 2.0)
    cr.arc(0.0, 0.0, 1.0, 0.0, 2.0 * math.pi)
    cr.restore()
    if fill_color is not None and fill_only:
        cr.set_source_rgba(*fill_color, fill_alpha)
        cr.fill()
        return
    if fill_color is not None and not outline_only:
        cr.set_source_rgb(*fill_color)
        cr.fill_preserve()
        cr.set_source_rgb(0.0, 0.0, 0.0)
    cr.stroke()


def _draw_dso_shape(
    cr: cairo.Context[cairo.Surface],
    cx: float,
    cy: float,
    size_pt: float,
    shape: DsoShape,
    dash_mm: float,
    *,
    fill_color: tuple[float, float, float] | None = None,
    fill_alpha: float = 1.0,
    fill_only: bool = False,
    outline_only: bool = False,
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
        if fill_color is not None and fill_only:
            cr.set_source_rgba(*fill_color, fill_alpha)
            cr.fill()
        elif fill_color is not None and not outline_only:
            cr.set_source_rgb(*fill_color)
            cr.fill_preserve()
            cr.set_source_rgb(0.0, 0.0, 0.0)
        if not fill_only:
            cr.stroke()
    if shape in (DsoShape.SQUARE, DsoShape.DASHED_SQUARE):
        cr.rectangle(cx - radius, cy - radius, 2.0 * radius, 2.0 * radius)
        if fill_color is not None and fill_only:
            cr.set_source_rgba(*fill_color, fill_alpha)
            cr.fill()
        elif fill_color is not None and not outline_only:
            cr.set_source_rgb(*fill_color)
            cr.fill_preserve()
            cr.set_source_rgb(0.0, 0.0, 0.0)
        if not fill_only:
            cr.stroke()
    if shape == DsoShape.DOT:
        cr.arc(cx, cy, radius, 0.0, 2.0 * math.pi)
        if fill_color is not None and fill_only:
            cr.set_source_rgba(*fill_color, fill_alpha)
            cr.fill()
        elif fill_color is not None and not outline_only:
            cr.set_source_rgb(*fill_color)
            cr.fill_preserve()
            cr.set_source_rgb(0.0, 0.0, 0.0)
            cr.stroke()
        elif outline_only:
            cr.stroke()
        elif fill_color is None:
            cr.fill()
    if shape == DsoShape.X_MARK and not fill_only:
        cr.move_to(cx - radius, cy - radius)
        cr.line_to(cx + radius, cy + radius)
        cr.move_to(cx - radius, cy + radius)
        cr.line_to(cx + radius, cy - radius)
        cr.stroke()
    if shape == DsoShape.CIRCLE_CROSS and not fill_only:
        reach = radius * CIRCLE_CROSS_REACH_FACTOR
        cr.move_to(cx - reach, cy)
        cr.line_to(cx + reach, cy)
        cr.move_to(cx, cy - reach)
        cr.line_to(cx, cy + reach)
        cr.stroke()
    if shape == DsoShape.SPOKED_CIRCLE and not fill_only:
        inner = radius * SPOKED_CIRCLE_INNER_FACTOR
        outer = radius * SPOKED_CIRCLE_OUTER_FACTOR
        cr.set_line_width(cr.get_line_width() * SPOKED_CIRCLE_SPIKE_WIDTH_FACTOR)
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
        if label.id.startswith("label:constellation:"):
            color = style.color_atlas.constellation_names if style.color_atlas else None
            gray = style.constellation.names.gray
        else:
            color = style.color_atlas.labels if style.color_atlas else None
            gray = 0.0
        cr.set_source_rgb(*(_hex_rgb(color) if color else (gray, gray, gray)))
        draw_text(
            cr,
            label.text,
            mm_to_pt(candidate.bounds.left_mm),
            mm_to_pt(candidate.bounds.top_mm),
            style.label.font_family,
            label.font_size_pt if label.font_size_pt is not None else style.label.font_size_pt,
            label.font_weight,
        )


def _draw_leader_lines(
    cr: cairo.Context[cairo.Surface],
    labels: tuple[Label, ...],
    scene: ChartScene,
    transform: PageTransform,
    style: StyleConfig,
) -> None:
    lines = resolve_leader_lines(labels, scene, transform, style)
    if not lines:
        return
    line_style = style.label.leader_lines
    cr.save()
    cr.set_source_rgb(line_style.gray, line_style.gray, line_style.gray)
    cr.set_line_width(mm_to_pt(line_style.width_mm))
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    for line in lines:
        cr.move_to(mm_to_pt(line.start.x_mm), mm_to_pt(line.start.y_mm))
        cr.line_to(mm_to_pt(line.end.x_mm), mm_to_pt(line.end.y_mm))
    cr.stroke()
    cr.restore()


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
            color=style.color_atlas.constellation_boundaries if style.color_atlas else None,
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
            color=style.color_atlas.constellation_lines if style.color_atlas else None,
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
    color: str | None = None,
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
    cr.set_source_rgb(*(_hex_rgb(color) if color else (tone, tone, tone)))
    for stroke in strokes:
        cr.set_line_width(mm_to_pt(style.constellation.lines.width_mm_for(stroke.weight)))
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
    for outline in scene.nebula_outlines:
        _draw_segments(
            cr,
            transform,
            (outline,),
            gray=style.dso.outline_gray,
            line_width_mm=style.dso.outline_line_width_mm,
            dash_mm=(style.dso.outline_dash_mm, style.dso.outline_dash_mm)
            if outline.dashed
            else None,
        )


def _draw_nebula_outline_fills(
    cr: cairo.Context[cairo.Surface],
    transform: PageTransform,
    scene: ChartScene,
    style: StyleConfig,
) -> None:
    if style.color_atlas is None or not scene.nebula_outlines:
        return
    nebulae = {
        item.dso.id: item
        for item in scene.deep_sky_objects
        if item.dso.object_type in (DsoType.BRIGHT_NEBULA, DsoType.SUPERNOVA_REMNANT)
    }
    fills = tuple(
        (outline, nebulae.get(outline.dso_id))
        for outline in scene.nebula_outlines
        if outline.fill_points is not None
    )
    fills = tuple((outline, item) for outline, item in fills if item is not None)
    if not fills:
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
    for outline, item in fills:
        color = _dso_fill_color(style, item)
        if color is None or outline.fill_points is None:
            continue
        first = transform.to_page(outline.fill_points[0])
        cr.move_to(mm_to_pt(first.x_mm), mm_to_pt(first.y_mm))
        for chart_point in outline.fill_points[1:]:
            page_point = transform.to_page(chart_point)
            cr.line_to(mm_to_pt(page_point.x_mm), mm_to_pt(page_point.y_mm))
        cr.close_path()
        cr.set_source_rgba(*_hex_rgb(color), 0.24)
        cr.fill()
    cr.restore()


def _draw_magellanic_clouds(
    cr: cairo.Context[cairo.Surface],
    transform: PageTransform,
    scene: ChartScene,
    style: StyleConfig,
) -> None:
    magellanic = style.magellanic_clouds
    if not magellanic.enabled or not scene.magellanic_polygons:
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
    for level in magellanic.levels:
        alpha = (
            style.color_atlas.magellanic_cloud_fill_alpha.get(level, 1.0)
            if style.color_atlas is not None
            else 1.0
        )
        if style.color_atlas is None:
            gray = magellanic.level_fill_gray[level]
            cr.set_source_rgb(gray, gray, gray)
        else:
            color = style.color_atlas.magellanic_cloud_fills.get(
                level, magellanic.level_color[level]
            )
            cr.set_source_rgba(*_hex_rgb(color), alpha)
        for polygon in scene.magellanic_polygons:
            if polygon.level != level:
                continue
            _append_closed_polygon(cr, transform, polygon.fill_points)
            cr.fill()
    cr.set_line_width(mm_to_pt(magellanic.line_width_mm))
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    for polygon in scene.magellanic_polygons:
        if style.color_atlas is None:
            gray = magellanic.level_gray[polygon.level]
            cr.set_source_rgb(gray, gray, gray)
        else:
            cr.set_source_rgb(*_hex_rgb(style.color_atlas.magellanic_cloud_outline))
        _append_closed_polygon(cr, transform, polygon.contour_points)
        cr.stroke()
    cr.restore()


def _append_closed_polygon(
    cr: cairo.Context[cairo.Surface],
    transform: PageTransform,
    points: tuple[ChartPoint, ...],
) -> None:
    for index, chart_point in enumerate(points):
        point = transform.to_page(chart_point)
        if index == 0:
            cr.move_to(mm_to_pt(point.x_mm), mm_to_pt(point.y_mm))
        else:
            cr.line_to(mm_to_pt(point.x_mm), mm_to_pt(point.y_mm))
    cr.close_path()


def _draw_milky_way_contours(
    cr: cairo.Context[cairo.Surface],
    transform: PageTransform,
    scene: ChartScene,
    style: StyleConfig,
) -> None:
    milky_way = style.milky_way
    if not milky_way.enabled or not milky_way.levels or not (
        scene.milky_way_contours
        or scene.milky_way_polygons
        or scene.milky_way_fill_available
    ):
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
    cr.set_line_width(mm_to_pt(milky_way.line_width_mm))
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    palette = style.color_atlas
    if palette is not None:
        ancestor_groups: list[list[list[SceneMilkyWayPolygon]]] = []
        for level in sorted(milky_way.levels):
            color = palette.milky_way_fills.get(level)
            if color is None:
                continue
            groups = _milky_way_polygon_groups(scene.milky_way_polygons, level)
            if not groups:
                continue
            if ancestor_groups:
                cr.save()
                for parent_groups in ancestor_groups:
                    cr.new_path()
                    cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
                    _append_milky_way_groups(cr, transform, rect, parent_groups)
                    cr.clip()
            cr.new_path()
            cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
            _append_milky_way_groups(cr, transform, rect, groups)
            cr.set_source_rgb(*_hex_rgb(color))
            cr.fill()
            if ancestor_groups:
                cr.restore()
            ancestor_groups.append(groups)
    for level in milky_way.levels:
        gray = milky_way.level_gray[level]
        cr.set_source_rgb(
            *_hex_rgb(palette.milky_way_outline)
            if palette is not None
            else (gray, gray, gray)
        )
        for contour in scene.milky_way_contours:
            if contour.level != level:
                continue
            for index, chart_point in enumerate(contour.points):
                point = transform.to_page(chart_point)
                if index == 0:
                    cr.move_to(mm_to_pt(point.x_mm), mm_to_pt(point.y_mm))
                else:
                    cr.line_to(mm_to_pt(point.x_mm), mm_to_pt(point.y_mm))
            cr.stroke()
    cr.restore()


def _append_milky_way_fill_paths(
    cr: cairo.Context[cairo.Surface],
    transform: PageTransform,
    polygons: Iterable[SceneMilkyWayPolygon],
) -> None:
    for polygon in polygons:
        for index, chart_point in enumerate(polygon.points):
            point = transform.to_page(chart_point)
            if index == 0:
                cr.move_to(mm_to_pt(point.x_mm), mm_to_pt(point.y_mm))
            else:
                cr.line_to(mm_to_pt(point.x_mm), mm_to_pt(point.y_mm))
        cr.close_path()


def _milky_way_polygon_groups(
    polygons: Iterable[SceneMilkyWayPolygon], level: int
) -> list[list[SceneMilkyWayPolygon]]:
    groups: dict[str, list[SceneMilkyWayPolygon]] = {}
    for index, polygon in enumerate(polygons):
        if polygon.level != level:
            continue
        group_id = polygon.polygon_id or f"unGrouped:{index}"
        groups.setdefault(group_id, []).append(polygon)
    return list(groups.values())


def _append_milky_way_groups(
    cr: cairo.Context[cairo.Surface],
    transform: PageTransform,
    chart_rect: PageRect,
    groups: Iterable[Iterable[SceneMilkyWayPolygon]],
) -> None:
    for group in groups:
        polygons = tuple(group)
        if polygons and polygons[0].complement:
            cr.rectangle(
                mm_to_pt(chart_rect.left_mm),
                mm_to_pt(chart_rect.top_mm),
                mm_to_pt(chart_rect.width_mm),
                mm_to_pt(chart_rect.height_mm),
            )
        _append_milky_way_fill_paths(cr, transform, polygons)


def _draw_segments(
    cr: cairo.Context[cairo.Surface],
    transform: PageTransform,
    segments: Iterable[SceneSegment | SceneOutline],
    *,
    gray: float,
    color: str | None = None,
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
    cr.set_source_rgb(*(_hex_rgb(color) if color else (tone, tone, tone)))
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
    for line in lines:
        polar_ra = line.kind == "ra" and line.polar
        gray = style.grid.gray
        line_width_mm = style.grid.line_width_mm
        if polar_ra:
            if style.grid.polar_ra_gray is not None:
                gray = style.grid.polar_ra_gray
            if style.grid.polar_ra_line_width_mm is not None:
                line_width_mm = style.grid.polar_ra_line_width_mm
        gray = min(max(gray, 0.0), 1.0)
        color = style.color_atlas.coordinate_grid if style.color_atlas else None
        cr.set_source_rgb(*(_hex_rgb(color) if color else (gray, gray, gray)))
        cr.set_line_width(mm_to_pt(line_width_mm))
        for index, point in enumerate(line.points):
            if index == 0:
                cr.move_to(mm_to_pt(point.x_mm), mm_to_pt(point.y_mm))
            else:
                cr.line_to(mm_to_pt(point.x_mm), mm_to_pt(point.y_mm))
        cr.stroke()
    cr.restore()
    return lines


def _draw_grid_ticks(
    cr: cairo.Context[cairo.Surface],
    transform: PageTransform,
    definition: ChartDefinition,
    style: StyleConfig,
) -> None:
    ticks = build_grid_ticks(definition, transform, style)
    if not ticks:
        return
    rect = transform.chart_rect
    gray = style.grid.tick_gray
    cr.save()
    cr.set_source_rgb(gray, gray, gray)
    cr.set_line_width(mm_to_pt(style.grid.tick_line_width_mm))
    for tick in ticks:
        position = mm_to_pt(tick.position_mm)
        length = mm_to_pt(tick.length_mm)
        if tick.edge == "top":
            edge = mm_to_pt(rect.top_mm)
            cr.move_to(position, edge)
            cr.line_to(position, edge - length)
        elif tick.edge == "bottom":
            edge = mm_to_pt(rect.bottom_mm)
            cr.move_to(position, edge)
            cr.line_to(position, edge + length)
        elif tick.edge == "left":
            edge = mm_to_pt(rect.left_mm)
            cr.move_to(edge, position)
            cr.line_to(edge - length, position)
        else:
            edge = mm_to_pt(rect.right_mm)
            cr.move_to(edge, position)
            cr.line_to(edge + length, position)
    cr.stroke()
    cr.restore()


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
