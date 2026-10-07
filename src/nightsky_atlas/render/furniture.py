"""Page furniture: footer, scale bar, magnitude legend and navigation.

Everything here is *furniture*: quiet, outside the chart field, and always
drawn last so it can never compete with the map.  The precise placement is
centralised so the renderer and the coordinate-label obstacle system agree on
where the furniture sits (``AGENTS.md`` sections 16 and 27).

Visual order (from the chart frame outward): coordinate labels, then
navigation, then the footer tools along the page edge.  All visible strings are
built from :mod:`nightsky_atlas.chart.presentation`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import cairo

from nightsky_atlas.atlas.config import StyleConfig
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.chart.page import PageRect, PageTransform
from nightsky_atlas.chart.presentation import (
    ChartPresentation,
    neighbour_code,
    neighbour_markup,
    presentation_for,
    product_edition_title,
)
from nightsky_atlas.render.overview import locator_rect
from nightsky_atlas.render.pdf_navigation import PdfNavigation
from nightsky_atlas.render.symbols import StarSizeModel, star_reference_magnitudes
from nightsky_atlas.render.text import (
    TextMeasurer,
    TextMetrics,
    draw_centered_text,
    draw_markup_centered_text,
    draw_markup_text,
    draw_rotated_markup_centered_text,
    draw_text,
    escape_markup,
)
from nightsky_atlas.units import mm_to_pt

__all__ = [
    "FurniturePlan",
    "build_furniture_plan",
    "draw_furniture",
    "furniture_obstacles",
]

Align = Literal["left", "center", "right"]

_FOOTER_DOT_CENTER_FROM_BOTTOM_MM = 4.2
_FOOTER_TITLE_CENTER_FROM_BOTTOM_MM = 4.3
_LEGEND_LABEL_GAP_MM = 2.0
_LEGEND_DOT_NUMBER_GAP_MM = 0.6
_LEGEND_CENTER_FROM_BOTTOM_MM = 5.0
_LEGEND_BOTTOM_SAFE_MM = 2.0
_SCALE_LABEL_GAP_MM = 0.6
_SIDE_NAVIGATION_ANGLE_RAD = math.pi / 2.0


@dataclass(frozen=True, slots=True)
class PlacedText:
    """One furniture string, positioned by its logical text box.

    ``markup`` carries the mixed-weight Pango markup when the string has an
    emphasized part (the chart code); ``text`` stays the plain visible string.
    A non-zero ``rotation_rad`` rotates the string about ``(x_mm, y_mm)`` and
    ignores ``align`` -- used for the side-margin navigation.
    """

    text: str
    x_mm: float
    y_mm: float
    align: Align
    font_size_pt: float
    markup: str | None = None
    rotation_rad: float = 0.0
    target_chart_code: str | None = None


@dataclass(frozen=True, slots=True)
class ScaleBar:
    """A linear angular scale with the bar line and its ``5°`` label."""

    left_mm: float
    right_mm: float
    line_y_mm: float
    label_x_mm: float
    label_y_mm: float
    label: str
    font_size_pt: float
    tick_mm: float


@dataclass(frozen=True, slots=True)
class LegendDot:
    """One reference star symbol in the magnitude legend."""

    x_mm: float
    y_mm: float
    diameter_mm: float


@dataclass(frozen=True, slots=True)
class MagnitudeLegend:
    """Complete star-magnitude reference built from the real star size model."""

    label: PlacedText
    numbers: tuple[PlacedText, ...]
    dots: tuple[LegendDot, ...]


@dataclass(frozen=True, slots=True)
class FurniturePlan:
    """Resolved furniture for one chart page, in millimetres."""

    title: PlacedText | None
    brand: PlacedText | None
    navigation: tuple[PlacedText, ...]
    scale_bar: ScaleBar | None
    legend: MagnitudeLegend | None
    obstacles: tuple[PageRect, ...]


def _measure_placed(text: PlacedText, family: str) -> TextMetrics:
    """Measure a furniture string exactly as it will be drawn."""
    measurer = TextMeasurer(family, text.font_size_pt)
    if text.markup is not None:
        return measurer.measure_markup_mm(text.markup)
    return measurer.measure_mm(text.text)


def _text_bounds(
    text: str, x_mm: float, y_mm: float, align: Align, width_mm: float, height_mm: float
) -> PageRect:
    if align == "center":
        left = x_mm - width_mm / 2.0
    elif align == "right":
        left = x_mm - width_mm
    else:
        left = x_mm
    return PageRect(left_mm=left, top_mm=y_mm, width_mm=width_mm, height_mm=height_mm)


def _navigation(
    definition: ChartDefinition,
    transform: PageTransform,
    style: StyleConfig,
    presentation: ChartPresentation,
) -> tuple[PlacedText, ...]:
    nav = style.furniture.navigation
    if not nav.enabled or not definition.neighbours:
        return ()
    page = transform.page
    rect = transform.chart_rect
    family = style.label.font_family
    placed: list[PlacedText] = []
    grouped: dict[str, list[str]] = {direction: [] for direction in ("N", "E", "S", "W")}
    for direction, neighbour_id in definition.neighbours:
        if direction in grouped and len(grouped[direction]) < 3:
            grouped[direction].append(neighbour_id)
    for direction in ("N", "E", "S", "W"):
        neighbour_ids = grouped[direction]
        for position, neighbour_id in enumerate(neighbour_ids):
            along_edge = (position + 1) / (len(neighbour_ids) + 1)
            code = neighbour_code(
                neighbour_id,
                presentation.edition_code,
                presentation.chart_index_width,
            )
            text = f"{direction}: {code}"
            markup = neighbour_markup(
                direction,
                neighbour_id,
                presentation.edition_code,
                presentation.chart_index_width,
            )
            metrics = TextMeasurer(family, nav.font_size_pt).measure_markup_mm(markup)
            if direction == "N":
                placed.append(
                    PlacedText(
                        text,
                        rect.left_mm + rect.width_mm * along_edge,
                        rect.top_mm - nav.frame_gap_mm - metrics.height_mm,
                        "center",
                        nav.font_size_pt,
                        markup,
                        target_chart_code=code,
                    )
                )
            elif direction == "S":
                placed.append(
                    PlacedText(
                        text,
                        rect.left_mm + rect.width_mm * along_edge,
                        rect.bottom_mm + nav.frame_gap_mm,
                        "center",
                        nav.font_size_pt,
                        markup,
                        target_chart_code=code,
                    )
                )
            elif direction == "E":
                placed.append(
                    PlacedText(
                        text,
                        nav.side_inset_mm + metrics.height_mm / 2.0,
                        rect.bottom_mm - rect.height_mm * along_edge,
                        "center",
                        nav.font_size_pt,
                        markup,
                        -_SIDE_NAVIGATION_ANGLE_RAD,
                        code,
                    )
                )
            elif direction == "W":
                placed.append(
                    PlacedText(
                        text,
                        page.width_mm - nav.side_inset_mm - metrics.height_mm / 2.0,
                        rect.bottom_mm - rect.height_mm * along_edge,
                        "center",
                        nav.font_size_pt,
                        markup,
                        _SIDE_NAVIGATION_ANGLE_RAD,
                        code,
                    )
                )
    return tuple(placed)


def _scale_bar(
    transform: PageTransform, style: StyleConfig
) -> ScaleBar | None:
    bar = style.furniture.scale_bar
    if not bar.enabled:
        return None
    page = transform.page
    length_deg = bar.length_deg
    length_mm = length_deg * transform.mm_per_deg
    if length_mm <= 0.0:
        return None
    while length_mm > min(80.0, page.width_mm * 0.28):
        length_deg /= 2.0
        length_mm = length_deg * transform.mm_per_deg
    label = f"{length_deg:g}\N{DEGREE SIGN}"
    line_y = page.height_mm - _FOOTER_DOT_CENTER_FROM_BOTTOM_MM
    label_height = TextMeasurer(style.label.font_family, bar.font_size_pt).measure_mm(
        label
    ).height_mm
    return ScaleBar(
        left_mm=page.width_mm / 2.0 - length_mm / 2.0,
        right_mm=page.width_mm / 2.0 + length_mm / 2.0,
        line_y_mm=line_y,
        label_x_mm=page.width_mm / 2.0,
        label_y_mm=line_y - bar.tick_mm / 2.0 - _SCALE_LABEL_GAP_MM - label_height,
        label=label,
        font_size_pt=bar.font_size_pt,
        tick_mm=bar.tick_mm,
    )


def _magnitude_legend(
    page: PageGeometry, style: StyleConfig
) -> MagnitudeLegend | None:
    legend = style.furniture.magnitude_legend
    if not legend.enabled:
        return None
    family = style.label.font_family
    size_model = StarSizeModel.from_style(style.star)
    magnitudes = star_reference_magnitudes(style.star)
    measurer = TextMeasurer(family, legend.font_size_pt)
    # The limit is derived from the same star style used to select plotted
    # stars, so Pocket/Standard/Deep legends cannot drift out of sync.
    limit_label = f"{legend.label} {style.star.faint_magnitude:g}"
    label_metrics = measurer.measure_mm(limit_label)
    number_height = measurer.measure_mm("0").height_mm
    max_diameter = max(size_model.diameter_mm(magnitude) for magnitude in magnitudes)
    # Keep the largest legend dot clear of the print-safe bottom margin; the
    # standard centre distance is a floor so Pocket/Standard stay unchanged and
    # only editions with larger symbols (Deep) move the row up.
    dot_center = page.height_mm - max(
        _LEGEND_CENTER_FROM_BOTTOM_MM, _LEGEND_BOTTOM_SAFE_MM + max_diameter / 2.0
    )
    number_top = dot_center - max_diameter / 2.0 - _LEGEND_DOT_NUMBER_GAP_MM - number_height
    next_left = page.margin_mm + label_metrics.width_mm + _LEGEND_LABEL_GAP_MM
    dots_list: list[LegendDot] = []
    numbers_list: list[PlacedText] = []
    for magnitude in magnitudes:
        diameter_mm = size_model.diameter_mm(magnitude)
        center_x = next_left + diameter_mm / 2.0
        dots_list.append(LegendDot(center_x, dot_center, diameter_mm))
        numbers_list.append(
            PlacedText(f"{magnitude:g}", center_x, number_top, "center", legend.font_size_pt)
        )
        next_left += diameter_mm + legend.spacing_mm
    dots = tuple(dots_list)
    numbers = tuple(numbers_list)
    return MagnitudeLegend(
        label=PlacedText(
            limit_label,
            page.margin_mm,
            dot_center - label_metrics.height_mm / 2.0,
            "left",
            legend.font_size_pt,
        ),
        numbers=numbers,
        dots=dots,
    )


def _obstacle_for_text(text: PlacedText, family: str) -> PageRect:
    """Return the page rectangle a string occupies, honouring rotation."""
    metrics = _measure_placed(text, family)
    if text.rotation_rad != 0.0:
        return PageRect(
            left_mm=text.x_mm - metrics.height_mm / 2.0,
            top_mm=text.y_mm - metrics.width_mm / 2.0,
            width_mm=metrics.height_mm,
            height_mm=metrics.width_mm,
        )
    return _text_bounds(
        text.text, text.x_mm, text.y_mm, text.align, metrics.width_mm, metrics.height_mm
    )


def build_furniture_plan(
    transform: PageTransform,
    definition: ChartDefinition,
    style: StyleConfig,
    presentation: ChartPresentation,
) -> FurniturePlan:
    """Resolve all furniture geometry and the rectangles labels must avoid."""
    family = style.label.font_family
    page = transform.page
    obstacles: list[PageRect] = []

    title: PlacedText | None = None
    brand: PlacedText | None = None
    if style.furniture.footer_layout == "split":
        code = presentation.chart_header_code
        if code:
            code_markup = presentation.chart_header_markup
            code_size = style.furniture.footer_code_font_size_pt
            code_height = TextMeasurer(family, code_size).measure_markup_mm(code_markup).height_mm
            title = PlacedText(
                code,
                page.width_mm - page.margin_mm,
                page.height_mm - _FOOTER_TITLE_CENTER_FROM_BOTTOM_MM - code_height / 2.0,
                "right",
                code_size,
                code_markup,
            )
            obstacles.append(_obstacle_for_text(title, family))
        brand_text = product_edition_title(
            presentation.edition_name, product_name=presentation.product_name
        )
        brand_size = style.furniture.footer_brand_font_size_pt
        brand_height = TextMeasurer(family, brand_size).measure_mm(brand_text).height_mm
        brand = PlacedText(
            brand_text,
            page.width_mm / 2.0,
            page.height_mm - _FOOTER_TITLE_CENTER_FROM_BOTTOM_MM - brand_height / 2.0,
            "center",
            brand_size,
        )
        obstacles.append(_obstacle_for_text(brand, family))
    elif presentation.title:
        title_size = style.furniture.title_font_size_pt
        title_metrics = TextMeasurer(family, title_size).measure_markup_mm(
            presentation.title_markup
        )
        title = PlacedText(
            presentation.title,
            page.width_mm - page.margin_mm,
            page.height_mm - _FOOTER_TITLE_CENTER_FROM_BOTTOM_MM - title_metrics.height_mm / 2.0,
            "right",
            title_size,
            presentation.title_markup,
        )
        obstacles.append(_obstacle_for_text(title, family))

    navigation = _navigation(definition, transform, style, presentation)
    for nav_text in navigation:
        obstacles.append(_obstacle_for_text(nav_text, family))

    scale_bar = _scale_bar(transform, style)
    if scale_bar is not None:
        obstacles.append(
            PageRect(
                left_mm=scale_bar.left_mm,
                top_mm=scale_bar.label_y_mm,
                width_mm=scale_bar.right_mm - scale_bar.left_mm,
                height_mm=scale_bar.line_y_mm + scale_bar.tick_mm / 2.0
                - scale_bar.label_y_mm,
            )
        )

    legend = _magnitude_legend(page, style)
    if legend is not None:
        legend_metrics = TextMeasurer(family, legend.numbers[-1].font_size_pt)
        top = min(
            legend.label.y_mm,
            legend.numbers[0].y_mm,
            min(dot.y_mm - dot.diameter_mm / 2.0 for dot in legend.dots),
        )
        bottom = max(
            legend.label.y_mm + _measure_placed(legend.label, family).height_mm,
                legend.numbers[0].y_mm
                + legend_metrics.measure_mm(legend.numbers[0].text).height_mm,
            max(dot.y_mm + dot.diameter_mm / 2.0 for dot in legend.dots),
        )
        obstacles.append(
            PageRect(
                left_mm=page.margin_mm,
                top_mm=top,
                width_mm=max(
                    legend.label.x_mm + _measure_placed(legend.label, family).width_mm,
                    *(
                        number.x_mm + legend_metrics.measure_mm(number.text).width_mm / 2.0
                        for number in legend.numbers
                    ),
                )
                - page.margin_mm,
                height_mm=bottom - top,
            )
        )

    locator = locator_rect(transform, style)
    if locator is not None:
        obstacles.append(locator)

    return FurniturePlan(
        title=title,
        brand=brand,
        navigation=navigation,
        scale_bar=scale_bar,
        legend=legend,
        obstacles=tuple(obstacles),
    )


def furniture_obstacles(
    transform: PageTransform,
    definition: ChartDefinition,
    style: StyleConfig,
    presentation: ChartPresentation | None = None,
) -> tuple[PageRect, ...]:
    """Return the furniture rectangles a label must avoid.

    Convenience for the layout pipeline: when no ``presentation`` is supplied
    the bare chart definition drives the visible naming.
    """
    if presentation is None:
        presentation = presentation_for(definition)
    return build_furniture_plan(transform, definition, style, presentation).obstacles


def _draw_placed_text(
    cr: cairo.Context[cairo.Surface],
    text: PlacedText,
    family: str,
    gray: float,
) -> None:
    cr.set_source_rgb(gray, gray, gray)
    if text.rotation_rad != 0.0:
        markup = text.markup if text.markup is not None else escape_markup(text.text)
        draw_rotated_markup_centered_text(
            cr,
            markup,
            mm_to_pt(text.x_mm),
            mm_to_pt(text.y_mm),
            family,
            text.font_size_pt,
            text.rotation_rad,
        )
        return
    if text.markup is not None:
        metrics = _measure_placed(text, family)
        if text.align == "center":
            draw_markup_centered_text(
                cr,
                text.markup,
                mm_to_pt(text.x_mm),
                mm_to_pt(text.y_mm + metrics.height_mm / 2.0),
                family,
                text.font_size_pt,
            )
            return
        x = text.x_mm
        if text.align == "right":
            x = text.x_mm - metrics.width_mm
        draw_markup_text(
            cr, text.markup, mm_to_pt(x), mm_to_pt(text.y_mm), family, text.font_size_pt
        )
        return
    if text.align == "center":
        metrics = TextMeasurer(family, text.font_size_pt).measure_mm(text.text)
        draw_centered_text(
            cr,
            text.text,
            mm_to_pt(text.x_mm),
            mm_to_pt(text.y_mm + metrics.height_mm / 2.0),
            family,
            text.font_size_pt,
        )
        return
    x = text.x_mm
    if text.align == "right":
        width_mm = TextMeasurer(family, text.font_size_pt).measure_mm(text.text).width_mm
        x = text.x_mm - width_mm
    draw_text(cr, text.text, mm_to_pt(x), mm_to_pt(text.y_mm), family, text.font_size_pt)


def draw_furniture(
    cr: cairo.Context[cairo.Surface],
    plan: FurniturePlan,
    style: StyleConfig,
    pdf_navigation: PdfNavigation | None = None,
) -> None:
    """Draw a resolved furniture plan; always after all sky content."""
    family = style.label.font_family
    cr.set_line_cap(cairo.LINE_CAP_BUTT)

    scale = plan.scale_bar
    if scale is not None:
        bar = style.furniture.scale_bar
        cr.set_source_rgb(bar.gray, bar.gray, bar.gray)
        cr.set_line_width(mm_to_pt(bar.thickness_mm))
        tick = mm_to_pt(scale.tick_mm) / 2.0
        cr.move_to(mm_to_pt(scale.left_mm), mm_to_pt(scale.line_y_mm))
        cr.line_to(mm_to_pt(scale.right_mm), mm_to_pt(scale.line_y_mm))
        cr.move_to(mm_to_pt(scale.left_mm), mm_to_pt(scale.line_y_mm) - tick)
        cr.line_to(mm_to_pt(scale.left_mm), mm_to_pt(scale.line_y_mm) + tick)
        cr.move_to(mm_to_pt(scale.right_mm), mm_to_pt(scale.line_y_mm) - tick)
        cr.line_to(mm_to_pt(scale.right_mm), mm_to_pt(scale.line_y_mm) + tick)
        cr.stroke()
        cr.set_source_rgb(bar.gray, bar.gray, bar.gray)
        label_metrics = TextMeasurer(family, scale.font_size_pt).measure_mm(scale.label)
        draw_centered_text(
            cr,
            scale.label,
            mm_to_pt(scale.label_x_mm),
            mm_to_pt(scale.label_y_mm + label_metrics.height_mm / 2.0),
            family,
            scale.font_size_pt,
        )

    legend = plan.legend
    if legend is not None:
        gray = style.furniture.magnitude_legend.gray
        cr.set_source_rgb(gray, gray, gray)
        for dot in legend.dots:
            cr.arc(
                mm_to_pt(dot.x_mm),
                mm_to_pt(dot.y_mm),
                mm_to_pt(dot.diameter_mm) / 2.0,
                0.0,
                2.0 * math.pi,
            )
            cr.fill()
        _draw_placed_text(cr, legend.label, family, gray)
        for number in legend.numbers:
            _draw_placed_text(cr, number, family, gray)

    if plan.title is not None:
        title_gray = style.furniture.title_gray
        _draw_placed_text(cr, plan.title, family, title_gray)

    if plan.brand is not None:
        brand_gray = style.furniture.footer_brand_gray
        _draw_placed_text(cr, plan.brand, family, brand_gray)

    nav_gray = style.furniture.navigation.gray
    for nav_text in plan.navigation:
        if pdf_navigation is None or nav_text.target_chart_code is None:
            _draw_placed_text(cr, nav_text, family, nav_gray)
            continue
        with pdf_navigation.link(
            cr,
            nav_text.target_chart_code,
            _obstacle_for_text(nav_text, family),
        ):
            _draw_placed_text(cr, nav_text, family, nav_gray)
