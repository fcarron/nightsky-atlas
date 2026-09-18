"""Vector renderer for compact, paginated atlas-index pages."""

from __future__ import annotations

import math

import cairo

from nightsky_atlas.atlas.config import EditionConfig, PageGeometry, StyleConfig
from nightsky_atlas.atlas.index import AtlasIndex, ConstellationIndexEntry, DsoIndexEntry
from nightsky_atlas.render.text import draw_text
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
    count += max(1, math.ceil(len(index.constellation_entries) / constellation_capacity))
    return count + (max(1, math.ceil(len(index.aliases) / dso_capacity)) if index.aliases else 0)


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
    cr: cairo.Context[cairo.Surface], entry: DsoIndexEntry, x: float, y: float, family: str
) -> None:
    charts = entry.primary_chart + (
        f" ({', '.join(entry.secondary_charts)})" if entry.secondary_charts else ""
    )
    for text, offset in (
        (entry.designation, 0),
        (entry.object_type, 30),
        (entry.constellation, 76),
        (charts, 91),
    ):
        draw_text(cr, text, mm_to_pt(x + offset), mm_to_pt(y), family, _FONT_SIZE_PT)


def _draw_constellation_row(
    cr: cairo.Context[cairo.Surface],
    entry: ConstellationIndexEntry,
    x: float,
    y: float,
    family: str,
) -> None:
    draw_text(
        cr, f"{entry.name} ({entry.abbreviation})", mm_to_pt(x), mm_to_pt(y), family, _FONT_SIZE_PT
    )
    for line_number, chart_line in enumerate(_chart_lines(entry.chart_ids)):
        draw_text(
            cr,
            chart_line,
            mm_to_pt(x + 52),
            mm_to_pt(y + line_number * 3.4),
            family,
            _FONT_SIZE_PT,
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


def _draw_headers(
    cr: cairo.Context[cairo.Surface],
    cells: tuple[tuple[str, float], ...],
    x: float,
    y: float,
    family: str,
) -> None:
    for text, offset in cells:
        draw_text(cr, text, mm_to_pt(x + offset), mm_to_pt(y), family, 7.0, "bold")


def _draw_section(
    cr: cairo.Context[cairo.Surface],
    surface: cairo.Surface,
    entries: (
        tuple[DsoIndexEntry, ...]
        | tuple[ConstellationIndexEntry, ...]
        | tuple[tuple[str, str], ...]
    ),
    title: str,
    headers: tuple[tuple[str, float], ...],
    page: PageGeometry,
    style: StyleConfig,
    edition: EditionConfig,
    page_number: int,
    row_mm: float = _ROW_MM,
) -> int:
    capacity_per_column = _capacity(page, row_mm) // _COLUMNS
    capacity = capacity_per_column * _COLUMNS
    family = style.label.font_family
    column_width = (page.width_mm - 2 * page.margin_mm) / _COLUMNS
    for offset in range(0, max(1, len(entries)), capacity):
        cr.set_source_rgb(0.0, 0.0, 0.0)
        draw_text(
            cr, title, mm_to_pt(page.margin_mm), mm_to_pt(page.margin_mm), family, 11.0, "bold"
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
                _draw_dso_row(cr, entry, x, y, family)
            elif isinstance(entry, ConstellationIndexEntry):
                _draw_constellation_row(cr, entry, x, y, family)
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
) -> int:
    """Append compact vector index pages and return the number written."""
    cr.set_source_rgb(0.0, 0.0, 0.0)
    next_page = _draw_section(
        cr,
        surface,
        index.dso_entries,
        "DEEP-SKY OBJECT INDEX",
        (("Designation", 0), ("Type", 30), ("Con", 76), ("Chart", 91)),
        page,
        style,
        edition,
        1,
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
    )
    if index.aliases:
        _draw_section(
            cr,
            surface,
            index.aliases,
            "CROSS-REFERENCE INDEX",
            (("Common name", 0), ("See", 70)),
            page,
            style,
            edition,
            next_page,
        )
    return index_page_count(index, page)
