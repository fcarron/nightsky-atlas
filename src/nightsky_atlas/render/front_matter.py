"""Compact printed field guide and edition-specific symbol legend."""

from __future__ import annotations

import math
from dataclasses import dataclass

import cairo

from nightsky_atlas.atlas.config import AtlasConfig, GalaxyContourStyle, StyleConfig
from nightsky_atlas.catalog.models import DeepSkyObject, DsoType, Provenance
from nightsky_atlas.chart.models import PageGeometry
from nightsky_atlas.chart.page import PagePoint
from nightsky_atlas.render.cairo import _draw_double_star_mark, draw_dso_symbol, draw_star_disk
from nightsky_atlas.render.double_stars import DoubleStarMark
from nightsky_atlas.render.symbols import (
    StarSizeModel,
    SymbolExtent,
    compact_star_reference_magnitudes,
    dso_symbol_extent,
)
from nightsky_atlas.render.text import draw_text, measure_point_size
from nightsky_atlas.units import mm_to_pt

__all__ = ["LegendSymbol", "draw_field_guide", "legend_symbols"]


@dataclass(frozen=True, slots=True)
class LegendSymbol:
    name: str
    object_type: DsoType
    angular_size_arcmin: float | None
    extent: SymbolExtent


@dataclass(frozen=True, slots=True)
class GalaxyVisibilityExample:
    contour_class: str
    contour: GalaxyContourStyle
    meaning: str


def galaxy_visibility_examples(style: StyleConfig) -> tuple[GalaxyVisibilityExample, ...]:
    """Return the four configured production contour styles and key wording."""
    contours = style.dso.galaxy_contours
    return (
        GalaxyVisibilityExample("bold", contours.bold, "easy"),
        GalaxyVisibilityExample("normal", contours.normal, "moderate"),
        GalaxyVisibilityExample("fine", contours.fine, "difficult"),
        GalaxyVisibilityExample("dotted", contours.dotted, "threshold"),
    )


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
    draw_star_disk(cr, x_mm, y_mm, diameter_mm)


def _footer(
    cr: cairo.Context[cairo.Surface], page: PageGeometry, edition: str, family: str
) -> None:
    text = f"NightSky Atlas — {edition} · Field guide & symbol key"
    width_pt, _ = measure_point_size(cr, text, family, 7.0)
    x_pt = mm_to_pt(page.width_mm - page.margin_mm) - width_pt
    _text(
        cr,
        text,
        x_pt * 25.4 / 72.0,
        page.height_mm - page.margin_mm - 4.0,
        family,
        7.0,
        gray=0.38,
    )


def _draw_map_lines(
    cr: cairo.Context[cairo.Surface],
    style: StyleConfig,
    family: str,
    left: float,
    top: float,
    width: float,
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
    _text(cr, "MAP LINES", left, top, family, 7.0, bold=True, gray=0.38)
    for index, (name, gray, width_mm, dash_mm) in enumerate(samples):
        column, row = index % 2, index // 2
        x = left + column * width / 2.0
        y = top + 8.0 + row * 5.4
        cr.save()
        cr.set_source_rgb(gray, gray, gray)
        cr.set_line_width(mm_to_pt(width_mm))
        if dash_mm:
            cr.set_dash([mm_to_pt(value) for value in dash_mm])
        cr.move_to(mm_to_pt(x), mm_to_pt(y))
        cr.line_to(mm_to_pt(x + 10.0), mm_to_pt(y))
        cr.stroke()
        cr.restore()
        _text(cr, name, x + 12.0, y - 3.3, family, 6.1)


def telrad_ring_diameters_mm(mm_per_degree: float) -> tuple[float, float, float]:
    """Physical diameters of the standard 0.5°, 2° and 4° Telrad rings."""
    if not math.isfinite(mm_per_degree) or mm_per_degree <= 0.0:
        raise ValueError("mm_per_degree must be finite and positive")
    return tuple(value * mm_per_degree for value in (0.5, 2.0, 4.0))


def _draw_telrad(
    cr: cairo.Context[cairo.Surface],
    center_x: float,
    center_y: float,
    mm_per_degree: float,
    family: str,
) -> None:
    diameters = telrad_ring_diameters_mm(mm_per_degree)
    cr.save()
    cr.set_source_rgb(0.12, 0.12, 0.12)
    cr.set_line_width(mm_to_pt(0.18))
    for diameter in diameters:
        cr.new_sub_path()
        cr.arc(
            mm_to_pt(center_x),
            mm_to_pt(center_y),
            mm_to_pt(diameter / 2.0),
            0.0,
            math.tau,
        )
    cr.stroke()
    cr.restore()
    for diameter, label in zip(diameters, ("0.5°", "2°", "4°"), strict=True):
        _text(
            cr,
            label,
            center_x + diameter / 2.0 + 1.0,
            center_y + 0.8,
            family,
            6.0,
            gray=0.28,
        )


def _draw_double_star_examples(
    cr: cairo.Context[cairo.Surface],
    x: float,
    y: float,
    style: StyleConfig,
    size_model: StarSizeModel,
    family: str,
) -> None:
    _text(cr, "DOUBLE STARS", x, y, family, 7.0, bold=True, gray=0.38)
    magnitude = 6.0
    disk = size_model.diameter_mm(magnitude)
    collapsed = DoubleStarMark(
        system_id="legend:unresolved",
        page_point=PagePoint(x_mm=x + 11.0, y_mm=y + 12.0),
        magnitude=magnitude,
        suppress_star_ids=frozenset(("legend:a", "legend:b")),
        marker_length_mm=max(
            style.double_stars.min_marker_length_mm,
            style.double_stars.marker_length_factor * disk,
        ),
        marker_line_width_mm=style.double_stars.marker_line_width_mm,
    )
    _draw_double_star_mark(cr, collapsed, size_model)
    _text(cr, "unresolved", x + 18.0, y + 14.5, family, 6.2)

    first_diameter = size_model.diameter_mm(5.0)
    second_diameter = size_model.diameter_mm(6.5)
    separation = max(
        style.double_stars.min_component_separation_mm + 0.2,
        (first_diameter + second_diameter) / 2.0 + 0.35,
    )
    first_x = x + 72.0
    second_x = first_x + separation
    _dot(cr, first_x, y + 12.0, first_diameter)
    _dot(cr, second_x, y + 12.0, second_diameter)
    _text(cr, "resolved", second_x + 4.0, y + 14.5, family, 6.2)


def draw_field_guide(
    cr: cairo.Context[cairo.Surface],
    atlas: AtlasConfig,
    style: StyleConfig,
    chart_count: int,
    mm_per_degree: float,
) -> None:
    """Draw the compact, edition-aware atlas symbol key."""
    page = atlas.page.to_geometry()
    family = style.label.font_family
    left = page.margin_mm + 4.0
    right = page.width_mm - page.margin_mm - 4.0
    width = right - left

    _text(
        cr,
        "NIGHTSKY ATLAS  /  FIELD GUIDE",
        left,
        page.margin_mm,
        family,
        7.0,
        bold=True,
        gray=0.42,
    )
    _text(cr, "Field guide & symbol key", left, page.margin_mm + 5.5, family, 14.0, bold=True)
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
    _rule(cr, left, right, page.margin_mm + 23.0)

    # Three compact lookup cues replace the former four instructional blocks.
    _text(cr, "USING THE ATLAS", left, 43.0, family, 7.0, bold=True, gray=0.38)
    usage = (
        ("Find chart", "overview maps / directory"),
        ("Continue", "neighbour codes at edges"),
        ("Find object", "indexes at the back"),
    )
    step_width = width / len(usage)
    for index, (title, detail) in enumerate(usage):
        x = left + index * step_width
        _text(cr, title, x, 50.5, family, 7.5, bold=True)
        _text(cr, detail, x + 25.0, 50.5, family, 6.8, gray=0.3)
    _rule(cr, left, right, 57.0)

    _text(
        cr,
        f"STARS  ·  limiting mag {atlas.stellar_limit_magnitude:g}",
        left,
        63.0,
        family,
        7.0,
        bold=True,
        gray=0.38,
    )
    star_model = StarSizeModel.from_style(style.star)
    magnitudes = compact_star_reference_magnitudes(atlas.stellar_limit_magnitude)
    spacing = min(20.0, (width * 0.48 - 25.0) / max(1, len(magnitudes) - 1))
    scale_start = left + 14.0
    for index, magnitude in enumerate(magnitudes):
        x = scale_start + index * spacing
        diameter = star_model.diameter_mm(magnitude)
        _text(cr, f"{magnitude:g}", x - 2.4, 69.5, family, 6.3, bold=True)
        _dot(cr, x, 77.0, diameter)

    if style.double_stars.enabled:
        _draw_double_star_examples(cr, left, 88.0, style, star_model, family)

    # Telrad rings are physical circles derived directly from the edition's
    # chart scale, using a right-hand column so Deep's 80 mm ring fits too.
    _text(
        cr,
        "TELRAD  ·  angular diameters",
        left + width * 0.57,
        59.5,
        family,
        7.0,
        bold=True,
        gray=0.38,
    )
    telrad_center_x = left + width * 0.72
    outer_radius = telrad_ring_diameters_mm(mm_per_degree)[-1] / 2.0
    telrad_center_y = max(87.0, 64.0 + outer_radius)
    _draw_telrad(cr, telrad_center_x, telrad_center_y, mm_per_degree, family)

    _text(cr, "DEEP-SKY OBJECTS", left, 114.0, family, 7.0, bold=True, gray=0.38)
    _text(
        cr,
        "Shape = type · extent = angular size; print minimums apply",
        left,
        119.0,
        family,
        6.4,
        gray=0.35,
    )
    for index, symbol in enumerate(legend_symbols(style, mm_per_degree)):
        column, row = index % 2, index // 2
        x = left + column * 67.0
        y = 124.0 + row * 7.5
        cr.set_source_rgb(0.0, 0.0, 0.0)
        cr.set_line_width(mm_to_pt(style.dso.line_width_mm))
        cr.new_path()
        draw_dso_symbol(
            cr,
            mm_to_pt(x + 5.5),
            mm_to_pt(y + 3.5),
            symbol.extent,
            style.dso.dash_mm,
        )
        _text(cr, symbol.name, x + 12.0, y + 1.5, family, 6.3, bold=True)

    _rule(cr, left, right, 154.0)
    _text(cr, "GALAXY VISIBILITY", left, 160.0, family, 7.0, bold=True, gray=0.38)
    _text(
        cr,
        "Stronger contour = easier integrated-light visibility",
        left + 39.0,
        160.0,
        family,
        6.1,
        gray=0.32,
    )
    for index, example in enumerate(galaxy_visibility_examples(style)):
        contour = example.contour
        y = 168.0 + index * 4.0
        cr.save()
        cr.set_source_rgb(0.0, 0.0, 0.0)
        cr.set_line_width(mm_to_pt(contour.line_width_mm))
        if contour.dash_mm > 0.0:
            cr.set_dash([mm_to_pt(contour.dash_mm), mm_to_pt(contour.gap_mm or contour.dash_mm)])
        cr.move_to(mm_to_pt(left), mm_to_pt(y))
        cr.line_to(mm_to_pt(left + 16.0), mm_to_pt(y))
        cr.stroke()
        cr.restore()
        _text(cr, example.meaning, left + 19.0, y - 2.0, family, 6.2)
    _text(
        cr,
        "Reference model: 100 / 200 / 400 mm apertures · sky 21.5 mag/arcsec² · "
        "transmission 0.75 · pupil 7 mm",
        left,
        188.0,
        family,
        5.8,
        gray=0.32,
    )
    _text(cr, "Atlas aid, not a guarantee of detection.", left, 192.0, family, 5.8, gray=0.32)

    _draw_map_lines(cr, style, family, left + width * 0.52, 160.0, width * 0.48)
    _footer(cr, page, atlas.resolved_edition().name, family)
