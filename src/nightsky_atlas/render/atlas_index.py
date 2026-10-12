"""Vector renderer for compact, paginated atlas-index pages."""

from __future__ import annotations

import math

import cairo

from nightsky_atlas.atlas.config import EditionConfig, PageGeometry, StyleConfig
from nightsky_atlas.atlas.index import (
    AtlasIndex,
    ConstellationIndexEntry,
    DsoIndexEntry,
    NamedStarIndexEntry,
)
from nightsky_atlas.chart.page import PageRect
from nightsky_atlas.render.pdf_navigation import PdfNavigation
from nightsky_atlas.render.text import TextMeasurer, draw_text
from nightsky_atlas.units import mm_to_pt

__all__ = ["draw_atlas_index_pages", "index_page_count"]

_FONT_SIZE_PT, _ROW_MM, _CONSTELLATION_ROW_MM, _HEADER_MM, _COLUMNS = 7.5, 4.1, 8.0, 22.0, 2


def _capacity(page: PageGeometry, row_mm: float = _ROW_MM) -> int:
    return (
        max(1, math.floor((page.height_mm - 2 * page.margin_mm - _HEADER_MM) / row_mm)) * _COLUMNS
    )


def index_page_count(index: AtlasIndex, page: PageGeometry) -> int:
    dso_capacity = _capacity(page)
    constellation_capacity = _capacity(page, _CONSTELLATION_ROW_MM)
    count = max(1, math.ceil(len(index.dso_entries) / dso_capacity))
    count += (
        max(1, math.ceil(len(index.named_star_entries) / dso_capacity))
        if index.named_star_entries
        else 0
    )
    count += max(1, math.ceil(len(index.constellation_entries) / constellation_capacity))
    count += max(1, math.ceil(len(index.aliases) / dso_capacity)) if index.aliases else 0
    return count


def _compact_position(ra_deg: float, dec_deg: float) -> str:
    ra_minutes = round((ra_deg % 360.0) * 4.0) % (24 * 60)
    hours, minutes = divmod(ra_minutes, 60)
    declination_minutes = round(abs(dec_deg) * 60.0)
    degrees, arcminutes = divmod(declination_minutes, 60)
    sign = "−" if dec_deg < 0.0 else "+"
    return f"{hours:02d}h{minutes:02d}m {sign}{degrees:02d}°{arcminutes:02d}"


def _footer(
    cr: cairo.Context[cairo.Surface],
    page: PageGeometry,
    edition: EditionConfig,
    number: int,
    family: str,
) -> None:
    draw_text(
        cr,
        f"NightSky Atlas — {edition.name} · Index · {number}",
        mm_to_pt(page.margin_mm),
        mm_to_pt(page.height_mm - page.margin_mm + 2.5),
        family,
        7.0,
    )


def _draw_dso_row(
    cr: cairo.Context[cairo.Surface],
    entry: DsoIndexEntry,
    x: float,
    y: float,
    family: str,
    pdf_navigation: PdfNavigation | None,
) -> None:
    for text, offset in (
        (entry.designation, 0),
        (_compact_position(entry.ra_deg, entry.dec_deg), 32),
        (entry.object_type, 62),
        (entry.constellation, 94),
    ):
        draw_text(cr, text, mm_to_pt(x + offset), mm_to_pt(y), family, _FONT_SIZE_PT)
    _draw_chart_references(
        cr,
        (entry.primary_chart, *entry.secondary_charts),
        x + 106,
        y,
        family,
        pdf_navigation,
        parenthesize_after_first=True,
    )


def _draw_constellation_row(
    cr: cairo.Context[cairo.Surface],
    entry: ConstellationIndexEntry,
    x: float,
    y: float,
    family: str,
    pdf_navigation: PdfNavigation | None,
) -> None:
    draw_text(
        cr, f"{entry.name} ({entry.abbreviation})", mm_to_pt(x), mm_to_pt(y), family, _FONT_SIZE_PT
    )
    for line_number, chart_line in enumerate(_chart_lines(entry.chart_ids)):
        _draw_chart_references(
            cr,
            tuple(part.strip() for part in chart_line.split(",")),
            x + 52,
            y + line_number * 3.4,
            family,
            pdf_navigation,
        )


def _chart_lines(chart_ids: tuple[str, ...], max_characters: int = 44) -> tuple[str, ...]:
    """Wrap chart codes only between codes, never through a visible reference."""
    lines: list[str] = []
    current = ""
    for chart_id in chart_ids:
        candidate = f"{current}, {chart_id}" if current else chart_id
        if current and len(candidate) > max_characters:
            lines.append(current)
            current = chart_id
        else:
            current = candidate
    if current:
        lines.append(current)
    return tuple(lines)


def _draw_alias_row(
    cr: cairo.Context[cairo.Surface], entry: tuple[str, str], x: float, y: float, family: str
) -> None:
    alias, canonical_id = entry
    draw_text(cr, alias, mm_to_pt(x), mm_to_pt(y), family, _FONT_SIZE_PT)
    draw_text(cr, canonical_id, mm_to_pt(x + 70), mm_to_pt(y), family, _FONT_SIZE_PT)


def _draw_named_star_row(
    cr: cairo.Context[cairo.Surface],
    entry: NamedStarIndexEntry,
    x: float,
    y: float,
    family: str,
    pdf_navigation: PdfNavigation | None,
) -> None:
    for text, offset in (
        (entry.name, 0),
        (entry.designation, 35),
        (entry.constellation, 75),
    ):
        draw_text(cr, text, mm_to_pt(x + offset), mm_to_pt(y), family, _FONT_SIZE_PT)
    _draw_chart_references(
        cr,
        (entry.primary_chart, *entry.secondary_charts),
        x + 90,
        y,
        family,
        pdf_navigation,
        parenthesize_after_first=True,
    )


def _draw_chart_references(
    cr: cairo.Context[cairo.Surface],
    chart_ids: tuple[str, ...],
    x: float,
    y: float,
    family: str,
    pdf_navigation: PdfNavigation | None,
    *,
    parenthesize_after_first: bool = False,
) -> None:
    measurer = TextMeasurer(family, _FONT_SIZE_PT)
    cursor = x
    for index, chart_id in enumerate(chart_ids):
        if index:
            separator = " (" if parenthesize_after_first and index == 1 else ", "
            draw_text(cr, separator, mm_to_pt(cursor), mm_to_pt(y), family, _FONT_SIZE_PT)
            cursor += measurer.measure_mm(separator).width_mm
        metrics = measurer.measure_mm(chart_id)
        rect = PageRect(cursor, y, metrics.width_mm, metrics.height_mm)
        if pdf_navigation is None:
            draw_text(cr, chart_id, mm_to_pt(cursor), mm_to_pt(y), family, _FONT_SIZE_PT)
        else:
            with pdf_navigation.link(cr, chart_id, rect):
                draw_text(cr, chart_id, mm_to_pt(cursor), mm_to_pt(y), family, _FONT_SIZE_PT)
        cursor += metrics.width_mm
    if parenthesize_after_first and len(chart_ids) > 1:
        draw_text(cr, ")", mm_to_pt(cursor), mm_to_pt(y), family, _FONT_SIZE_PT)


def _draw_headers(
    cr: cairo.Context[cairo.Surface],
    cells: tuple[tuple[str, float], ...],
    x: float,
    y: float,
    family: str,
) -> None:
    for text, offset in cells:
        draw_text(cr, text, mm_to_pt(x + offset), mm_to_pt(y), family, 7.0, "semibold")


def _draw_section(
    cr: cairo.Context[cairo.Surface],
    surface: cairo.Surface,
    entries: (
        tuple[DsoIndexEntry, ...]
        | tuple[ConstellationIndexEntry, ...]
        | tuple[NamedStarIndexEntry, ...]
        | tuple[tuple[str, str], ...]
    ),
    title: str,
    headers: tuple[tuple[str, float], ...],
    page: PageGeometry,
    style: StyleConfig,
    edition: EditionConfig,
    page_number: int,
    row_mm: float = _ROW_MM,
    pdf_navigation: PdfNavigation | None = None,
    *,
    page_id: str | None = None,
    outline_parent_id: int | None = None,
) -> int:
    capacity_per_column = _capacity(page, row_mm) // _COLUMNS
    capacity = capacity_per_column * _COLUMNS
    family = style.typography.sans_family
    column_width = (page.width_mm - 2 * page.margin_mm) / _COLUMNS
    for offset in range(0, max(1, len(entries)), capacity):
        if pdf_navigation is not None and page_id is not None and offset == 0:
            label = title.title().replace("Dso", "DSO")
            pdf_navigation.mark_page(surface, cr, page_id, label=label)
            if outline_parent_id is not None:
                pdf_navigation.add_page_outline(surface, outline_parent_id, label, page_id)
        cr.set_source_rgb(0.0, 0.0, 0.0)
        draw_text(
            cr, title, mm_to_pt(page.margin_mm), mm_to_pt(page.margin_mm), family, 11.0, "semibold"
        )
        for column in range(_COLUMNS):
            _draw_headers(
                cr,
                headers,
                page.margin_mm + column * column_width,
                page.margin_mm + 9,
                family,
            )
        for local, entry in enumerate(entries[offset : offset + capacity]):
            column, row = divmod(local, capacity_per_column)
            x, y = page.margin_mm + column * column_width, page.margin_mm + 14 + row * row_mm
            if isinstance(entry, DsoIndexEntry):
                _draw_dso_row(cr, entry, x, y, family, pdf_navigation)
            elif isinstance(entry, ConstellationIndexEntry):
                _draw_constellation_row(cr, entry, x, y, family, pdf_navigation)
            elif isinstance(entry, NamedStarIndexEntry):
                _draw_named_star_row(cr, entry, x, y, family, pdf_navigation)
            else:
                _draw_alias_row(cr, entry, x, y, family)
        _footer(cr, page, edition, page_number, family)
        surface.show_page()
        page_number += 1
    return page_number


def draw_atlas_index_pages(
    cr: cairo.Context[cairo.Surface],
    surface: cairo.Surface,
    index: AtlasIndex,
    page: PageGeometry,
    style: StyleConfig,
    edition: EditionConfig,
    pdf_navigation: PdfNavigation | None = None,
    *,
    outline_parent_id: int | None = None,
) -> int:
    """Append compact vector index pages and return the number written."""
    index_outline = None
    if pdf_navigation is not None and outline_parent_id is not None:
        index_outline = pdf_navigation.add_page_outline(
            surface, outline_parent_id, "Object Index", "index-dso", open_item=False
        )
    cr.set_source_rgb(0.0, 0.0, 0.0)
    next_page = _draw_section(
        cr,
        surface,
        index.dso_entries,
        "DEEP-SKY OBJECT INDEX",
        (("Designation", 0), ("RA/Dec", 32), ("Type", 62), ("Con", 94), ("Chart", 106)),
        page,
        style,
        edition,
        1,
        pdf_navigation=pdf_navigation,
        page_id="index-dso",
        outline_parent_id=index_outline,
    )
    if index.named_star_entries:
        next_page = _draw_section(
            cr,
            surface,
            index.named_star_entries,
            "NAMED STAR INDEX",
            (("Name", 0), ("Designation", 35), ("Con", 75), ("Chart", 90)),
            page,
            style,
            edition,
            next_page,
            pdf_navigation=pdf_navigation,
            page_id="index-stars",
            outline_parent_id=index_outline,
        )
    next_page = _draw_section(
        cr,
        surface,
        index.constellation_entries,
        "CONSTELLATION INDEX",
        (("Constellation", 0), ("Charts", 52)),
        page,
        style,
        edition,
        next_page,
        _CONSTELLATION_ROW_MM,
        pdf_navigation,
        page_id="index-constellations",
        outline_parent_id=index_outline,
    )
    if index.aliases:
        next_page = _draw_section(
            cr,
            surface,
            index.aliases,
            "CROSS-REFERENCE INDEX",
            (("Common name", 0), ("See", 70)),
            page,
            style,
            edition,
            next_page,
            pdf_navigation=pdf_navigation,
            page_id="index-cross-references",
            outline_parent_id=index_outline,
        )
    return index_page_count(index, page)
