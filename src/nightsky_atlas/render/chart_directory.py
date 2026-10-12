"""Vector rendering for the compact, printable chart directory."""

from __future__ import annotations

import math

import cairo

from nightsky_atlas.atlas.config import EditionConfig, PageGeometry, StyleConfig
from nightsky_atlas.atlas.directory import ChartDirectoryEntry, DetailChartDirectoryEntry
from nightsky_atlas.chart.page import PageRect
from nightsky_atlas.render.pdf_navigation import PdfNavigation
from nightsky_atlas.render.text import TextMeasurer, draw_text
from nightsky_atlas.units import mm_to_pt

__all__ = [
    "chart_directory_page_count",
    "detail_chart_directory_page_count",
    "draw_chart_directory_pages",
    "draw_detail_chart_directory_pages",
]

_COLUMNS = 2
_ROW_MM = 5.0
_HEADER_MM = 22.0
_DETAIL_ROW_MM = 8.0


def _capacity(page: PageGeometry) -> int:
    return (
        max(1, math.floor((page.height_mm - 2 * page.margin_mm - _HEADER_MM) / _ROW_MM)) * _COLUMNS
    )


def chart_directory_page_count(entries: tuple[ChartDirectoryEntry, ...], page: PageGeometry) -> int:
    return max(1, math.ceil(len(entries) / _capacity(page)))


def detail_chart_directory_page_count(
    entries: tuple[DetailChartDirectoryEntry, ...], page: PageGeometry
) -> int:
    rows_per_column = max(
        1, math.floor((page.height_mm - 2 * page.margin_mm - _HEADER_MM) / _DETAIL_ROW_MM)
    )
    return math.ceil(len(entries) / (rows_per_column * _COLUMNS)) if entries else 0


def _footer(
    cr: cairo.Context[cairo.Surface],
    page: PageGeometry,
    edition: EditionConfig,
    number: int,
    family: str,
) -> None:
    draw_text(
        cr,
        f"NightSky Atlas — {edition.name} · Chart directory · {number}",
        mm_to_pt(page.margin_mm),
        mm_to_pt(page.height_mm - page.margin_mm + 2.5),
        family,
        7.0,
    )


def draw_chart_directory_pages(
    cr: cairo.Context[cairo.Surface],
    surface: cairo.Surface,
    entries: tuple[ChartDirectoryEntry, ...],
    page: PageGeometry,
    style: StyleConfig,
    edition: EditionConfig,
    pdf_navigation: PdfNavigation | None = None,
    *,
    outline_parent_id: int | None = None,
) -> int:
    """Append paginated directory pages and return the number written."""
    family = style.typography.sans_family
    capacity_per_column = _capacity(page) // _COLUMNS
    capacity = capacity_per_column * _COLUMNS
    column_width = (page.width_mm - 2 * page.margin_mm) / _COLUMNS
    for page_number, offset in enumerate(range(0, max(1, len(entries)), capacity), start=1):
        if pdf_navigation is not None and offset == 0:
            pdf_navigation.mark_page(
                surface, cr, "chart-directory", label="Chart Directory"
            )
            if outline_parent_id is not None:
                pdf_navigation.add_page_outline(
                    surface, outline_parent_id, "Chart Directory", "chart-directory"
                )
        cr.set_source_rgb(0.0, 0.0, 0.0)
        draw_text(
            cr,
            "CHART DIRECTORY",
            mm_to_pt(page.margin_mm),
            mm_to_pt(page.margin_mm),
            family,
            11.0,
            "semibold",
        )
        for column in range(_COLUMNS):
            x = page.margin_mm + column * column_width
            for text, x_offset in (("Chart", 0), ("Centre", 17), ("Field", 57), ("Neighbours", 82)):
                draw_text(
                    cr,
                    text,
                    mm_to_pt(x + x_offset),
                    mm_to_pt(page.margin_mm + 9),
                    family,
                    7.0,
                    "semibold",
                )
        for local, entry in enumerate(entries[offset : offset + capacity]):
            column, row = divmod(local, capacity_per_column)
            x = page.margin_mm + column * column_width
            y = page.margin_mm + 14 + row * _ROW_MM
            code_metrics = TextMeasurer(family, 7.5).measure_mm(entry.chart_code)
            code_rect = PageRect(x, y, code_metrics.width_mm, code_metrics.height_mm)
            if pdf_navigation is None:
                draw_text(cr, entry.chart_code, mm_to_pt(x), mm_to_pt(y), family, 7.5, "semibold")
            else:
                with pdf_navigation.link(cr, entry.chart_code, code_rect):
                    draw_text(
                        cr, entry.chart_code, mm_to_pt(x), mm_to_pt(y), family, 7.5, "semibold"
                    )
            draw_text(
                cr,
                f"{entry.center_ra} {entry.center_dec}",
                mm_to_pt(x + 17),
                mm_to_pt(y),
                family,
                7.5,
            )
            draw_text(cr, entry.field, mm_to_pt(x + 57), mm_to_pt(y), family, 7.5)
            draw_text(
                cr, ", ".join(entry.neighbours) or "—", mm_to_pt(x + 82), mm_to_pt(y), family, 7.5
            )
        _footer(cr, page, edition, page_number, family)
        surface.show_page()
    return chart_directory_page_count(entries, page)


def draw_detail_chart_directory_pages(
    cr: cairo.Context[cairo.Surface],
    surface: cairo.Surface,
    entries: tuple[DetailChartDirectoryEntry, ...],
    page: PageGeometry,
    style: StyleConfig,
    edition: EditionConfig,
    pdf_navigation: PdfNavigation | None = None,
    *,
    outline_parent_id: int | None = None,
) -> int:
    """Append a compact lookup for detail codes and their parent charts."""
    if not entries:
        return 0
    family = style.typography.sans_family
    rows_per_column = max(
        1, math.floor((page.height_mm - 2 * page.margin_mm - _HEADER_MM) / _DETAIL_ROW_MM)
    )
    capacity = rows_per_column * _COLUMNS
    column_width = (page.width_mm - 2 * page.margin_mm) / _COLUMNS
    for page_number, offset in enumerate(range(0, len(entries), capacity), start=1):
        if pdf_navigation is not None and offset == 0:
            pdf_navigation.mark_page(
                surface, cr, "detail-directory", label="Detail Chart Directory"
            )
            if outline_parent_id is not None:
                pdf_navigation.add_page_outline(
                    surface,
                    outline_parent_id,
                    "Detail Chart Directory",
                    "detail-directory",
                )
        draw_text(
            cr,
            "DETAIL CHART DIRECTORY",
            mm_to_pt(page.margin_mm),
            mm_to_pt(page.margin_mm),
            family,
            11.0,
            "semibold",
        )
        for local, entry in enumerate(entries[offset : offset + capacity]):
            column, row = divmod(local, rows_per_column)
            x = page.margin_mm + column * column_width
            y = page.margin_mm + 13.0 + row * _DETAIL_ROW_MM
            code_metrics = TextMeasurer(family, 7.0).measure_mm(entry.chart_code)
            code_rect = PageRect(x, y, code_metrics.width_mm, code_metrics.height_mm)
            if pdf_navigation is None:
                draw_text(cr, entry.chart_code, mm_to_pt(x), mm_to_pt(y), family, 7.0, "semibold")
            else:
                with pdf_navigation.link(cr, entry.chart_code, code_rect):
                    draw_text(
                        cr,
                        entry.chart_code,
                        mm_to_pt(x),
                        mm_to_pt(y),
                        family,
                        7.0,
                        "semibold",
                    )
            draw_text(cr, entry.name, mm_to_pt(x + 17.0), mm_to_pt(y), family, 7.0)
            draw_text(
                cr,
                f"{entry.scale_mm_per_degree:g} mm/°",
                mm_to_pt(x + column_width - 45.0),
                mm_to_pt(y),
                family,
                7.0,
            )
            draw_text(
                cr,
                f"{entry.center_ra} {entry.center_dec} · {entry.field}",
                mm_to_pt(x + 17.0),
                mm_to_pt(y + 3.2),
                family,
                6.5,
            )
            parent_prefix = "Main chart " if len(entry.parent_chart_codes) == 1 else "Main charts "
            parent_parts = [parent_prefix]
            for index, chart_code in enumerate(entry.parent_chart_codes):
                if index:
                    parent_parts.append(", ")
                parent_parts.append(chart_code)
            parent_width = sum(
                TextMeasurer(family, 6.5).measure_mm(part).width_mm for part in parent_parts
            )
            cursor_x = x + column_width - parent_width - 2.0
            parent_y = y + 3.2
            for index, part in enumerate(parent_parts):
                part_metrics = TextMeasurer(family, 6.5).measure_mm(part)
                part_rect = PageRect(
                    cursor_x,
                    parent_y,
                    part_metrics.width_mm,
                    part_metrics.height_mm,
                )
                chart_code = (
                    entry.parent_chart_codes[(index - 1) // 2]
                    if index % 2 == 1 and index > 0
                    else None
                )
                if pdf_navigation is not None and chart_code is not None:
                    with pdf_navigation.link(cr, chart_code, part_rect):
                        draw_text(
                            cr,
                            part,
                            mm_to_pt(part_rect.left_mm),
                            mm_to_pt(part_rect.top_mm),
                            family,
                            6.5,
                        )
                else:
                    draw_text(
                        cr,
                        part,
                        mm_to_pt(part_rect.left_mm),
                        mm_to_pt(part_rect.top_mm),
                        family,
                        6.5,
                    )
                cursor_x += part_metrics.width_mm
        draw_text(
            cr,
            f"NightSky Atlas — {edition.name} · Detail chart directory · {page_number}",
            mm_to_pt(page.margin_mm),
            mm_to_pt(page.height_mm - page.margin_mm + 2.5),
            family,
            7.0,
        )
        surface.show_page()
    return detail_chart_directory_page_count(entries, page)
