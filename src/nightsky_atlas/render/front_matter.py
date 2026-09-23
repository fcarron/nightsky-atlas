"""Compact printed field guide and edition-specific symbol legend."""

from __future__ import annotations

import math
from dataclasses import dataclass

import cairo

from nightsky_atlas.atlas.config import AtlasConfig, StyleConfig
from nightsky_atlas.catalog.models import DeepSkyObject, DsoType, Provenance
from nightsky_atlas.chart.models import PageGeometry
from nightsky_atlas.render.cairo import draw_dso_symbol
from nightsky_atlas.render.symbols import (
    StarSizeModel,
    SymbolExtent,
    compact_star_reference_magnitudes,
    dso_symbol_extent,
)
from nightsky_atlas.render.text import draw_text
from nightsky_atlas.units import mm_to_pt

__all__ = ["LegendSymbol", "draw_field_guide", "legend_symbols"]


@dataclass(frozen=True, slots=True)
class LegendSymbol:
    name: str
    object_type: DsoType
    angular_size_arcmin: float | None
    extent: SymbolExtent


_SAMPLES: tuple[tuple[str, DsoType, float | None, float | None], ...] = (
    ("Galaxy", DsoType.GALAXY, 24.0, 10.0),
    ("Globular cluster", DsoType.GLOBULAR_CLUSTER, 12.0, None),
    ("Open cluster", DsoType.OPEN_CLUSTER, 20.0, None),
    ("Planetary nebula", DsoType.PLANETARY_NEBULA, 6.0, None),
    ("Bright nebula / SNR", DsoType.BRIGHT_NEBULA, 24.0, None),
    ("Dark nebula", DsoType.DARK_NEBULA, 24.0, None),
    ("Galaxy cluster", DsoType.GALAXY_CLUSTER, 20.0, None),
    ("Other / unknown", DsoType.OTHER, None, None),
)


def legend_symbols(style: StyleConfig, mm_per_degree: float) -> tuple[LegendSymbol, ...]:
    """Use the same physical DSO geometry as the chart renderer."""
    symbols = []
    for name, object_type, major_arcmin, minor_arcmin in _SAMPLES:
        sample = DeepSkyObject(
            id=f"legend:{object_type.value}",
            ra_deg=0.0,
            dec_deg=0.0,
            object_type=object_type,
            provenance=Provenance("atlas-legend", object_type.value),
            major_axis_arcmin=major_arcmin,
            minor_axis_arcmin=minor_arcmin,
            position_angle_deg=45.0 if object_type == DsoType.GALAXY else None,
        )
        symbols.append(
            LegendSymbol(
                name,
                object_type,
                major_arcmin,
                dso_symbol_extent(sample, mm_per_deg=mm_per_degree, style=style),
            )
        )
    return tuple(symbols)


def _text(
    cr: cairo.Context[cairo.Surface],
    text: str,
    x_mm: float,
    y_mm: float,
    family: str,
    size_pt: float = 8.0,
    *,
    bold: bool = False,
    gray: float = 0.0,
) -> None:
    cr.set_source_rgb(gray, gray, gray)
    draw_text(
        cr,
        text,
        mm_to_pt(x_mm),
        mm_to_pt(y_mm),
        family,
        size_pt,
        "bold" if bold else "normal",
    )


def _rule(cr: cairo.Context[cairo.Surface], left_mm: float, right_mm: float, y_mm: float) -> None:
    cr.set_source_rgb(0.72, 0.72, 0.72)
    cr.set_line_width(mm_to_pt(0.15))
    cr.move_to(mm_to_pt(left_mm), mm_to_pt(y_mm))
    cr.line_to(mm_to_pt(right_mm), mm_to_pt(y_mm))
    cr.stroke()


def _dot(cr: cairo.Context[cairo.Surface], x_mm: float, y_mm: float, diameter_mm: float) -> None:
    cr.set_source_rgb(0.0, 0.0, 0.0)
    cr.arc(mm_to_pt(x_mm), mm_to_pt(y_mm), mm_to_pt(diameter_mm / 2), 0, 2 * math.pi)
    cr.fill()


def _footer(
    cr: cairo.Context[cairo.Surface], page: PageGeometry, edition: str, family: str
) -> None:
    _text(
        cr,
        f"NightSky Atlas — {edition} · Field guide & symbol key",
        page.margin_mm,
        page.height_mm - page.margin_mm + 2.5,
        family,
        7.0,
        gray=0.38,
    )


def _guide_step(
    cr: cairo.Context[cairo.Surface],
    x_mm: float,
    y_mm: float,
    number: str,
    title: str,
    lines: tuple[str, str],
    family: str,
) -> None:
    _text(cr, f"{number}  {title}", x_mm, y_mm, family, 9.0, bold=True)
    _text(cr, lines[0], x_mm, y_mm + 6.0, family, 7.7)
    _text(cr, lines[1], x_mm, y_mm + 10.5, family, 7.7)


def _draw_map_lines(
    cr: cairo.Context[cairo.Surface], style: StyleConfig, family: str, left: float
) -> None:
    samples: list[tuple[str, float, float, tuple[float, ...]]] = []
    if style.constellation.lines.enabled:
        samples.extend(
            (
                (
                    "Figure bold",
                    style.constellation.lines.gray,
                    style.constellation.lines.bold_width_mm,
                    (),
                ),
                (
                    "Figure normal",
                    style.constellation.lines.gray,
                    style.constellation.lines.normal_width_mm,
                    (),
                ),
                (
                    "Figure thin",
                    style.constellation.lines.gray,
                    style.constellation.lines.thin_width_mm,
                    (),
                ),
            )
        )
    if style.constellation.boundaries.enabled:
        samples.append(
            (
                "Boundary",
                style.constellation.boundaries.gray,
                style.constellation.boundaries.line_width_mm,
                (style.constellation.boundaries.dash_mm, style.constellation.boundaries.gap_mm),
            )
        )
    if style.grid.enabled:
        samples.append(("Grid", style.grid.gray, style.grid.line_width_mm, ()))
    if style.ecliptic.enabled:
        samples.append(
            (
                "Ecliptic",
                style.ecliptic.gray,
                style.ecliptic.line_width_mm,
                (style.ecliptic.dash_mm, style.ecliptic.gap_mm),
            )
        )
    samples.extend(
        (
            (
                "Bright nebula / SNR",
                style.dso.outline_gray,
                style.dso.outline_line_width_mm,
                (),
            ),
            (
                "Dark nebula",
                style.dso.outline_gray,
                style.dso.outline_line_width_mm,
                (style.dso.outline_dash_mm, style.dso.outline_dash_mm),
            ),
        )
    )
    _text(cr, "Map lines", left, 184.0, family, 8.5, bold=True)
    for index, (name, gray, width_mm, dash_mm) in enumerate(samples):
        column, row = index % 4, index // 4
        x = left + 34.0 + column * 58.0
        y = 190.0 + row * 7.0
        cr.save()
        cr.set_source_rgb(gray, gray, gray)
        cr.set_line_width(mm_to_pt(width_mm))
        if dash_mm:
            cr.set_dash([mm_to_pt(value) for value in dash_mm])
        cr.move_to(mm_to_pt(x), mm_to_pt(y))
        cr.line_to(mm_to_pt(x + 11.0), mm_to_pt(y))
        cr.stroke()
        cr.restore()
        _text(cr, name, x + 13.0, y - 4.0, family, 6.7)


def draw_field_guide(
    cr: cairo.Context[cairo.Surface],
    atlas: AtlasConfig,
    style: StyleConfig,
    chart_count: int,
    mm_per_degree: float,
) -> None:
    """Draw usage instructions and the true-size legend on one A4 page."""
    page = atlas.page.to_geometry()
    family = style.label.font_family
    left = page.margin_mm + 4.0
    right = page.width_mm - page.margin_mm - 4.0
    second = left + 136.0

    _text(cr, "FIELD GUIDE", left, page.margin_mm, family, 7.0, bold=True, gray=0.42)
    _text(cr, "Reading the sky", left, page.margin_mm + 6.0, family, 15.0, bold=True)
    _text(
        cr,
        f"{atlas.resolved_edition().name}  ·  {chart_count} "
        f"{'chart' if chart_count == 1 else 'charts'}  ·  "
        f"mag {atlas.stellar_limit_magnitude:g}  ·  J2000 / ICRS  ·  "
        f"{mm_per_degree:.1f} mm/°",
        left,
        page.margin_mm + 17.0,
        family,
        8.0,
        gray=0.3,
    )
    _rule(cr, left, right, page.margin_mm + 26.0)

    _guide_step(
        cr,
        left,
        49.0,
        "01",
        "Choose a field",
        (
            "Find its code on an overview map or in the chart directory.",
            "North is up, east left; right ascension increases leftward.",
        ),
        family,
    )
    _guide_step(
        cr,
        second,
        49.0,
        "02",
        "Continue across pages",
        (
            "Use neighbour codes at the chart edge.",
            "The overlap preserves the star pattern across a border.",
        ),
        family,
    )
    _guide_step(
        cr,
        left,
        72.0,
        "03",
        "Read a position",
        (
            "RA is on the upper/lower edges, declination on the sides.",
            "The fine grid is a positional aid, not an object list.",
        ),
        family,
    )
    _guide_step(
        cr,
        second,
        72.0,
        "04",
        "Find an object",
        (
            "Use the indexes at the back; chart IDs are printed codes.",
            "M42 = Messier 42 · 4565 = NGC 4565 · I5070 = IC 5070",
        ),
        family,
    )
    _rule(cr, left, right, 97.0)

    _text(cr, "Stars", left, 101.0, family, 9.5, bold=True)
    _text(
        cr,
        f"Print-size symbols · limit {atlas.stellar_limit_magnitude:g} · "
        "Deneb α = proper name + Bayer",
        left + 17.0,
        102.0,
        family,
        7.2,
        gray=0.35,
    )
    star_model = StarSizeModel.from_style(style.star)
    magnitudes = compact_star_reference_magnitudes(atlas.stellar_limit_magnitude)
    for index, magnitude in enumerate(magnitudes):
        x = left + 11.0 + index * 30.0
        diameter = star_model.diameter_mm(magnitude)
        _dot(cr, x, 116.0, diameter)
        _text(cr, f"mag {magnitude:g}", x - 8.0, 122.0, family, 6.8)
        _text(cr, f"{diameter:.2f} mm", x - 8.0, 127.0, family, 6.5)

    if style.double_stars.enabled:
        _text(cr, "Double stars", left + 178.0, 101.0, family, 9.5, bold=True)
        marker_size = star_model.diameter_mm(6.0)
        marker_length = max(
            style.double_stars.min_marker_length_mm,
            style.double_stars.marker_length_factor * marker_size,
        )
        cr.set_source_rgb(0.0, 0.0, 0.0)
        cr.set_line_width(mm_to_pt(style.double_stars.marker_line_width_mm))
        cr.move_to(mm_to_pt(left + 187.0 - marker_length / 2), mm_to_pt(116.0))
        cr.line_to(mm_to_pt(left + 187.0 + marker_length / 2), mm_to_pt(116.0))
        cr.stroke()
        _dot(cr, left + 187.0, 116.0, marker_size)
        _dot(cr, left + 228.0, 116.0, marker_size)
        _dot(cr, left + 230.8, 116.0, star_model.diameter_mm(7.0))
        _text(cr, "unresolved", left + 176.0, 124.0, family, 6.8)
        _text(cr, "resolved", left + 217.0, 124.0, family, 6.8)
    _rule(cr, left, right, 132.0)

    _text(cr, "Deep-sky objects", left, 135.0, family, 9.5, bold=True)
    _text(
        cr,
        "Shape = type · size follows angular extent · "
        f"10′ = {mm_per_degree / 6.0:.1f} mm before print minimums",
        left + 37.0,
        136.0,
        family,
        7.2,
        gray=0.35,
    )
    for index, symbol in enumerate(legend_symbols(style, mm_per_degree)):
        column, row = index % 4, index // 4
        x = left + column * 67.0
        y = 145.0 + row * 18.0
        cr.set_source_rgb(0.72, 0.72, 0.72)
        cr.set_line_width(mm_to_pt(0.14))
        cr.rectangle(mm_to_pt(x), mm_to_pt(y), mm_to_pt(63.0), mm_to_pt(16.0))
        cr.stroke()
        cr.set_source_rgb(0.0, 0.0, 0.0)
        cr.set_line_width(mm_to_pt(style.dso.line_width_mm))
        draw_dso_symbol(
            cr,
            mm_to_pt(x + 9.0),
            mm_to_pt(y + 8.0),
            symbol.extent,
            style.dso.dash_mm,
        )
        _text(cr, symbol.name, x + 17.0, y + 1.0, family, 7.2, bold=True)
        example = (
            f"{symbol.angular_size_arcmin:g}′ → {symbol.extent.width_mm:.1f} mm"
            if symbol.angular_size_arcmin is not None
            else f"fallback {symbol.extent.width_mm:.1f} mm"
        )
        _text(cr, example, x + 17.0, y + 8.0, family, 6.8, gray=0.35)

    _draw_map_lines(cr, style, family, left)
    _footer(cr, page, atlas.resolved_edition().name, family)
