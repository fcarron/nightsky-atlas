"""Vector rendering for the compact, printable chart directory."""

from __future__ import annotations

import math

import cairo

from nightsky_atlas.atlas.config import EditionConfig, PageGeometry, StyleConfig
from nightsky_atlas.atlas.directory import ChartDirectoryEntry
from nightsky_atlas.chart.page import PageRect
from nightsky_atlas.render.pdf_navigation import PdfNavigation
from nightsky_atlas.render.text import TextMeasurer, draw_text
from nightsky_atlas.units import mm_to_pt

__all__ = ["chart_directory_page_count", "draw_chart_directory_pages"]

_COLUMNS = 2
_ROW_MM = 5.0
_HEADER_MM = 22.0


def _capacity(page: PageGeometry) -> int:
    return (
        max(1, math.floor((page.height_mm - 2 * page.margin_mm - _HEADER_MM) / _ROW_MM)) * _COLUMNS
    )


def chart_directory_page_count(entries: tuple[ChartDirectoryEntry, ...], page: PageGeometry) -> int:
    return max(1, math.ceil(len(entries) / _capacity(page)))


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
) -> int:
    """Append paginated directory pages and return the number written."""
    family = style.typography.sans_family
    capacity_per_column = _capacity(page) // _COLUMNS
    capacity = capacity_per_column * _COLUMNS
    column_width = (page.width_mm - 2 * page.margin_mm) / _COLUMNS
    for page_number, offset in enumerate(range(0, max(1, len(entries)), capacity), start=1):
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
