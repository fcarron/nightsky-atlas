"""Parent-chart locator frames for supplementary detail maps."""

from __future__ import annotations

from dataclasses import dataclass

import cairo

from nightsky_atlas.atlas.config import DetailChartConfig, StyleConfig
from nightsky_atlas.chart.models import ChartDefinition
from nightsky_atlas.chart.page import PagePoint, PageRect, PageTransform
from nightsky_atlas.projection.stereographic import StereographicProjection
from nightsky_atlas.render.pdf_navigation import PdfNavigation
from nightsky_atlas.render.text import TextMeasurer, draw_text
from nightsky_atlas.units import mm_to_pt

__all__ = ["DetailMapMarker", "build_detail_marker", "draw_detail_markers"]

_BOUNDARY_SAMPLES_PER_EDGE = 12
_FRAME_WIDTH_MM = 0.25
_LABEL_SIZE_FACTOR = 1.0
_LABEL_PAD_X_MM = 1.0
_LABEL_PAD_Y_MM = 0.45


@dataclass(frozen=True, slots=True)
class DetailMapMarker:
    """Projected detail-field outline and its linked parent-chart label."""

    chart_code: str
    label: str
    boundary: tuple[PagePoint, ...]


def build_detail_marker(
    detail: DetailChartConfig,
    parent: ChartDefinition,
    parent_transform: PageTransform,
) -> DetailMapMarker:
    """Project the detail chart's actual stereographic footprint on its parent."""
    detail_projection = StereographicProjection(detail.center_ra_deg, detail.center_dec_deg)
    parent_projection = StereographicProjection(parent.center_ra_deg, parent.center_dec_deg)
    offsets: list[tuple[float, float]] = []
    half_width = detail.width_deg / 2.0
    half_height = detail.height_deg / 2.0
    samples = _BOUNDARY_SAMPLES_PER_EDGE
    for index in range(samples):
        fraction = index / samples
        offsets.append((-half_width + 2.0 * half_width * fraction, half_height))
    for index in range(samples):
        fraction = index / samples
        offsets.append((half_width, half_height - 2.0 * half_height * fraction))
    for index in range(samples):
        fraction = index / samples
        offsets.append((half_width - 2.0 * half_width * fraction, -half_height))
    for index in range(samples):
        fraction = index / samples
        offsets.append((-half_width, -half_height + 2.0 * half_height * fraction))

    boundary = tuple(
        parent_transform.to_page(
            parent_projection.project(*detail_projection.inverse(xi, eta))
        )
        for xi, eta in offsets
    )
    return DetailMapMarker(
        chart_code=detail.code,
        label=detail.name,
        boundary=boundary,
    )


def draw_detail_markers(
    cr: cairo.Context[cairo.Surface],
    markers: tuple[DetailMapMarker, ...],
    transform: PageTransform,
    style: StyleConfig,
    pdf_navigation: PdfNavigation | None = None,
) -> None:
    """Draw subtle zoom frames and link their labels in combined atlas PDFs."""
    if not markers:
        return
    chart_rect = transform.chart_rect
    cr.save()
    cr.rectangle(
        mm_to_pt(chart_rect.left_mm),
        mm_to_pt(chart_rect.top_mm),
        mm_to_pt(chart_rect.width_mm),
        mm_to_pt(chart_rect.height_mm),
    )
    cr.clip()
    for marker in markers:
        cr.set_source_rgb(0.38, 0.38, 0.38)
        cr.set_line_width(mm_to_pt(_FRAME_WIDTH_MM))
        cr.set_dash((mm_to_pt(1.2), mm_to_pt(0.8)))
        first = marker.boundary[0]
        cr.move_to(mm_to_pt(first.x_mm), mm_to_pt(first.y_mm))
        for point in marker.boundary[1:]:
            cr.line_to(mm_to_pt(point.x_mm), mm_to_pt(point.y_mm))
        cr.close_path()
        cr.stroke()
        cr.set_dash(())

        text = f"{marker.label} · {marker.chart_code}"
        font_size_pt = style.label.font_size_pt * _LABEL_SIZE_FACTOR
        metrics = TextMeasurer(style.label.font_family, font_size_pt).measure_mm(text)
        tag_width = metrics.width_mm + 2.0 * _LABEL_PAD_X_MM
        tag_height = metrics.height_mm + 2.0 * _LABEL_PAD_Y_MM
        min_x = min(point.x_mm for point in marker.boundary)
        min_y = min(point.y_mm for point in marker.boundary)
        max_x = max(point.x_mm for point in marker.boundary)
        max_y = max(point.y_mm for point in marker.boundary)
        x = min(
            max(min_x + 0.5, chart_rect.left_mm + 0.5),
            chart_rect.right_mm - tag_width - 0.5,
        )
        y = min(
            max(min_y + 0.5, chart_rect.top_mm + 0.5),
            chart_rect.bottom_mm - tag_height - 0.5,
        )
        x = min(x, max_x - tag_width - 0.5)
        y = min(y, max_y - tag_height - 0.5)
        x = max(x, chart_rect.left_mm + 0.5)
        y = max(y, chart_rect.top_mm + 0.5)
        tag = PageRect(x, y, tag_width, tag_height)
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.94)
        cr.rectangle(
            mm_to_pt(tag.left_mm),
            mm_to_pt(tag.top_mm),
            mm_to_pt(tag.width_mm),
            mm_to_pt(tag.height_mm),
        )
        cr.fill_preserve()
        cr.set_source_rgb(0.38, 0.38, 0.38)
        cr.set_line_width(mm_to_pt(0.15))
        cr.stroke()
        if pdf_navigation is None:
            draw_text(
                cr,
                text,
                mm_to_pt(x + _LABEL_PAD_X_MM),
                mm_to_pt(y + _LABEL_PAD_Y_MM),
                style.label.font_family,
                font_size_pt,
            )
        else:
            with pdf_navigation.link(cr, marker.chart_code, tag):
                draw_text(
                    cr,
                    text,
                    mm_to_pt(x + _LABEL_PAD_X_MM),
                    mm_to_pt(y + _LABEL_PAD_Y_MM),
                    style.label.font_family,
                    font_size_pt,
                )
    cr.restore()
