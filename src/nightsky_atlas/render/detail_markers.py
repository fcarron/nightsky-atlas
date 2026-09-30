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
_FRAME_WIDTH_MM = 0.17
_FRAME_GRAY = 0.62
_LABEL_SIZE_FACTOR = 0.9
_LABEL_PAD_X_MM = 0.65
_LABEL_PAD_Y_MM = 0.25
_LABEL_BACKING_ALPHA = 0.92
_TAG_OBSTACLE_GAP_MM = 0.6


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
        label=detail.name if detail.parent_marker_label is None else detail.parent_marker_label,
        boundary=boundary,
    )


def draw_detail_markers(
    cr: cairo.Context[cairo.Surface],
    markers: tuple[DetailMapMarker, ...],
    transform: PageTransform,
    style: StyleConfig,
    pdf_navigation: PdfNavigation | None = None,
    *,
    draw_frames: bool = True,
    draw_labels: bool = True,
    occupied_bounds: tuple[PageRect, ...] = (),
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
        if draw_frames:
            cr.set_source_rgb(_FRAME_GRAY, _FRAME_GRAY, _FRAME_GRAY)
            cr.set_line_width(mm_to_pt(_FRAME_WIDTH_MM))
            cr.set_dash((mm_to_pt(1.2), mm_to_pt(0.8)))
            first = marker.boundary[0]
            cr.move_to(mm_to_pt(first.x_mm), mm_to_pt(first.y_mm))
            for point in marker.boundary[1:]:
                cr.line_to(mm_to_pt(point.x_mm), mm_to_pt(point.y_mm))
            cr.close_path()
            cr.stroke()
            cr.set_dash(())

        if not draw_labels:
            continue
        text = (
            f"{marker.label} · {marker.chart_code}"
            if marker.label
            else marker.chart_code
        )
        font_size_pt = style.label.font_size_pt * _LABEL_SIZE_FACTOR
        metrics = TextMeasurer(style.label.font_family, font_size_pt).measure_mm(text)
        tag_width = metrics.width_mm + 2.0 * _LABEL_PAD_X_MM
        tag_height = metrics.height_mm + 2.0 * _LABEL_PAD_Y_MM
        min_x = min(point.x_mm for point in marker.boundary)
        min_y = min(point.y_mm for point in marker.boundary)
        max_x = max(point.x_mm for point in marker.boundary)
        max_y = max(point.y_mm for point in marker.boundary)
        tag = _marker_tag_rect(
            min_x=min_x,
            min_y=min_y,
            max_x=max_x,
            max_y=max_y,
            tag_width=tag_width,
            tag_height=tag_height,
            chart_rect=chart_rect,
            occupied_bounds=occupied_bounds,
        )
        cr.set_source_rgba(1.0, 1.0, 1.0, _LABEL_BACKING_ALPHA)
        cr.rectangle(
            mm_to_pt(tag.left_mm),
            mm_to_pt(tag.top_mm),
            mm_to_pt(tag.width_mm),
            mm_to_pt(tag.height_mm),
        )
        cr.fill()
        cr.set_source_rgb(0.0, 0.0, 0.0)
        x, y = tag.left_mm, tag.top_mm
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


def _marker_tag_rect(
    *,
    min_x: float,
    min_y: float,
    max_x: float,
    max_y: float,
    tag_width: float,
    tag_height: float,
    chart_rect: PageRect,
    occupied_bounds: tuple[PageRect, ...],
) -> PageRect:
    inset = 0.5
    candidates = (
        (min_x + inset, min_y + inset),
        (max_x - tag_width - inset, min_y + inset),
        (min_x + inset, max_y - tag_height - inset),
        (max_x - tag_width - inset, max_y - tag_height - inset),
    )
    bounded = tuple(
        (
            min(max(x, chart_rect.left_mm + inset), chart_rect.right_mm - tag_width - inset),
            min(max(y, chart_rect.top_mm + inset), chart_rect.bottom_mm - tag_height - inset),
        )
        for x, y in candidates
    )

    def overlap(rect: PageRect, obstacle: PageRect) -> float:
        obstacle_left = obstacle.left_mm - _TAG_OBSTACLE_GAP_MM
        obstacle_top = obstacle.top_mm - _TAG_OBSTACLE_GAP_MM
        obstacle_right = obstacle.right_mm + _TAG_OBSTACLE_GAP_MM
        obstacle_bottom = obstacle.bottom_mm + _TAG_OBSTACLE_GAP_MM
        width = max(
            0.0,
            min(rect.right_mm, obstacle_right) - max(rect.left_mm, obstacle_left),
        )
        height = max(
            0.0,
            min(rect.bottom_mm, obstacle_bottom) - max(rect.top_mm, obstacle_top),
        )
        return width * height

    selected = min(
        bounded,
        key=lambda position: (
            sum(
                overlap(PageRect(*position, tag_width, tag_height), item)
                for item in occupied_bounds
            ),
            sum(
                overlap(PageRect(*position, tag_width, tag_height), item) > 0.0
                for item in occupied_bounds
            ),
            bounded.index(position),
        ),
    )
    return PageRect(*selected, tag_width, tag_height)
