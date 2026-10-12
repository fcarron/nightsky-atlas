"""Internal navigation metadata for Cairo PDF atlas surfaces."""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import cairo

from nightsky_atlas.chart.page import PageRect
from nightsky_atlas.units import mm_to_pt

__all__ = ["PdfNavigation", "chart_destination", "page_destination"]

_CHART_CODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def chart_destination(chart_code: str) -> str:
    if not _CHART_CODE.fullmatch(chart_code):
        raise ValueError(f"invalid chart code for PDF destination: {chart_code!r}")
    return f"chart_{chart_code}"


def page_destination(page_id: str) -> str:
    """Return a stable named destination for a non-chart atlas page."""
    if not _CHART_CODE.fullmatch(page_id):
        raise ValueError(f"invalid page id for PDF destination: {page_id!r}")
    return f"page_{page_id}"


@dataclass(frozen=True, slots=True)
class PdfNavigation:
    chart_codes: frozenset[str]
    page_ids: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        destinations = [chart_destination(code) for code in self.chart_codes]
        if len(destinations) != len(set(destinations)):
            raise ValueError("PDF chart destinations must be unique")
        page_destinations = [page_destination(page_id) for page_id in self.page_ids]
        if len(page_destinations) != len(set(page_destinations)):
            raise ValueError("PDF page destinations must be unique")

    def has_chart(self, chart_code: str) -> bool:
        return chart_code in self.chart_codes

    def mark_chart_page(
        self,
        surface: cairo.PDFSurface,
        cr: cairo.Context[cairo.Surface],
        chart_code: str,
    ) -> None:
        if chart_code not in self.chart_codes:
            raise ValueError(f"chart is not part of this PDF: {chart_code}")
        surface.set_page_label(chart_code)
        cr.tag_begin(cairo.TAG_DEST, f"name='{chart_destination(chart_code)}' x=0 y=0")
        cr.tag_end(cairo.TAG_DEST)

    def mark_page(
        self,
        surface: cairo.PDFSurface,
        cr: cairo.Context[cairo.Surface],
        page_id: str,
        *,
        label: str | None = None,
    ) -> None:
        if page_id not in self.page_ids:
            raise ValueError(f"page is not registered in this PDF: {page_id}")
        surface.set_page_label(label or page_id)
        cr.tag_begin(cairo.TAG_DEST, f"name='{page_destination(page_id)}' x=0 y=0")
        cr.tag_end(cairo.TAG_DEST)

    def add_outline(
        self,
        surface: cairo.PDFSurface,
        parent_id: int,
        title: str,
        chart_code: str,
        *,
        open_item: bool = False,
    ) -> int | None:
        if chart_code not in self.chart_codes:
            return None
        flags = cairo.PDF_OUTLINE_FLAG_OPEN if open_item else 0
        return surface.add_outline(
            parent_id,
            title,
            f"dest='{chart_destination(chart_code)}'",
            flags,
        )

    def add_page_outline(
        self,
        surface: cairo.PDFSurface,
        parent_id: int,
        title: str,
        page_id: str,
        *,
        open_item: bool = False,
    ) -> int | None:
        if page_id not in self.page_ids:
            return None
        flags = cairo.PDF_OUTLINE_FLAG_OPEN if open_item else 0
        return surface.add_outline(
            parent_id,
            title,
            f"dest='{page_destination(page_id)}'",
            flags,
        )

    @contextmanager
    def link(
        self,
        cr: cairo.Context[cairo.Surface],
        chart_code: str,
        rect_mm: PageRect,
        *,
        padding_mm: float = 0.4,
    ) -> Iterator[bool]:
        if chart_code not in self.chart_codes:
            yield False
            return
        left = mm_to_pt(rect_mm.left_mm - padding_mm)
        top = mm_to_pt(rect_mm.top_mm - padding_mm)
        width = mm_to_pt(rect_mm.width_mm + 2.0 * padding_mm)
        height = mm_to_pt(rect_mm.height_mm + 2.0 * padding_mm)
        attributes = (
            f"dest='{chart_destination(chart_code)}' "
            f"rect=[{left:.6f} {top:.6f} {width:.6f} {height:.6f}]"
        )
        cr.tag_begin(cairo.TAG_LINK, attributes)
        try:
            yield True
        finally:
            cr.tag_end(cairo.TAG_LINK)
