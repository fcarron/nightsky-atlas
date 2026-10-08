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
from nightsky_atlas.render.text import draw_text, draw_tracked_text, measure_point_size
from nightsky_atlas.render.variable_stars import draw_variable_star_ring
from nightsky_atlas.units import mm_to_pt

__all__ = [
    "LegendSymbol",
    "draw_credits_page",
    "draw_field_guide",
    "draw_introduction",
    "legend_symbols",
]


@dataclass(frozen=True, slots=True)
class LegendSymbol:
    name: str
    object_type: DsoType
    angular_size_arcmin: float | None
    extent: SymbolExtent
    minimum_extent: SymbolExtent | None = None
    minimum_label: str | None = None


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


def dso_size_legend_text(style: StyleConfig) -> str:
    """Describe edition angular floors for DSO sizes and galaxy axes."""
    minimum = style.dso.galaxy.min_angular_major_axis_arcmin
    if minimum is None:
        return "Angular extents follow catalogue sizes."
    value = f"{minimum:g}′"
    return (
        f"First mark: to scale · second: <{value}, drawn at {value} minimum. "
        f"Print floors may exceed it; galaxy limit is major axis. Other: fixed."
    )


_SAMPLES: tuple[tuple[str, DsoType], ...] = (
    ("Galaxy", DsoType.GALAXY),
    ("Globular cluster", DsoType.GLOBULAR_CLUSTER),
    ("Open cluster", DsoType.OPEN_CLUSTER),
    ("Planetary nebula", DsoType.PLANETARY_NEBULA),
    ("Bright nebula / SNR", DsoType.BRIGHT_NEBULA),
    ("Dark nebula", DsoType.DARK_NEBULA),
    ("Galaxy cluster", DsoType.GALAXY_CLUSTER),
    ("Other / unknown", DsoType.OTHER),
)


def legend_symbols(style: StyleConfig, mm_per_degree: float) -> tuple[LegendSymbol, ...]:
    """Build to-scale and below-minimum examples with chart symbol geometry."""
    symbols = []
    for name, object_type in _SAMPLES:
        extent_style = style.dso.extent_style(object_type)
        minimum_arcmin = (
            extent_style.min_angular_major_axis_arcmin
            if object_type == DsoType.GALAXY
            else extent_style.min_angular_size_arcmin
        )
        if not extent_style.use_angular_size or minimum_arcmin is None:
            minimum_arcmin = None
        sample_arcmin = minimum_arcmin * 2.5 if minimum_arcmin is not None else None
        minor_arcmin = (
            sample_arcmin * 0.4 if object_type == DsoType.GALAXY and sample_arcmin else None
        )

        def make_sample(
            sample_id: str,
            sample_type: DsoType,
            major: float | None,
            minor: float | None,
        ) -> DeepSkyObject:
            return DeepSkyObject(
                id=sample_id,
                ra_deg=0.0,
                dec_deg=0.0,
                object_type=sample_type,
                provenance=Provenance("atlas-legend", sample_type.value),
                major_axis_arcmin=major,
                minor_axis_arcmin=minor,
                position_angle_deg=90.0 if sample_type == DsoType.GALAXY else None,
            )

        sample = make_sample(
            f"legend:{object_type.value}", object_type, sample_arcmin, minor_arcmin
        )
        minimum_extent = None
        minimum_label = None
        if minimum_arcmin is not None:
            below_minimum = minimum_arcmin * 0.5
            below_minor = below_minimum * 0.4 if object_type == DsoType.GALAXY else None
            minimum_sample = make_sample(
                f"legend:{object_type.value}:below-minimum",
                object_type,
                below_minimum,
                below_minor,
            )
            minimum_extent = dso_symbol_extent(
                minimum_sample,
                mm_per_deg=mm_per_degree,
                style=style,
            )
            minimum_label = f"<{minimum_arcmin:g}′"
        symbols.append(
            LegendSymbol(
                name,
                object_type,
                sample_arcmin,
                dso_symbol_extent(sample, mm_per_deg=mm_per_degree, style=style),
                minimum_extent,
                minimum_label,
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
    tracking_pt: float = 0.18,
) -> None:
    cr.set_source_rgb(gray, gray, gray)
    weight = "semibold" if bold else "normal"
    if bold and text == text.upper():
        draw_tracked_text(
            cr,
            text,
            mm_to_pt(x_mm),
            mm_to_pt(y_mm),
            family,
            size_pt,
            weight,
            tracking_pt,
        )
    else:
        draw_text(
            cr,
            text,
            mm_to_pt(x_mm),
            mm_to_pt(y_mm),
            family,
            size_pt,
            weight,
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
    cr: cairo.Context[cairo.Surface],
    page: PageGeometry,
    edition: str,
    family: str,
    section: str = "Field guide & symbol key",
) -> None:
    text = f"NightSky Atlas — {edition} · {section}"
    width_pt, _ = measure_point_size(cr, text, family, 7.0)
    x_pt = mm_to_pt(page.width_mm - page.margin_mm) - width_pt - mm_to_pt(0.5)
    _text(
        cr,
        text,
        x_pt * 25.4 / 72.0,
        page.height_mm - page.margin_mm - 4.0,
        family,
        7.0,
        gray=0.38,
    )


def _paragraph(
    cr: cairo.Context[cairo.Surface],
    words: str,
    x_mm: float,
    y_mm: float,
    width_mm: float,
    family: str,
    *,
    size_pt: float = 8.3,
    line_step_mm: float = 5.4,
    gray: float = 0.0,
) -> float:
    line = ""
    for word in words.split():
        candidate = f"{line} {word}" if line else word
        candidate_width_pt, _ = measure_point_size(cr, candidate, family, size_pt)
        if line and candidate_width_pt > mm_to_pt(width_mm):
            _text(cr, line, x_mm, y_mm, family, size_pt, gray=gray)
            y_mm += line_step_mm
            line = word
        else:
            line = candidate
    if line:
        _text(cr, line, x_mm, y_mm, family, size_pt, gray=gray)
        y_mm += line_step_mm
    return y_mm


def _draw_credit_column(
    cr: cairo.Context[cairo.Surface],
    sections: tuple[tuple[str, tuple[str, ...]], ...],
    x_mm: float,
    y_mm: float,
    width_mm: float,
    family: str,
) -> None:
    y = y_mm
    for heading, entries in sections:
        if not entries:
            continue
        _text(cr, heading.upper(), x_mm, y, family, 8.0, bold=True, gray=0.34)
        y += 5.2
        for entry in entries:
            y = _paragraph(
                cr,
                entry,
                x_mm,
                y,
                width_mm,
                family,
                size_pt=8.5,
                line_step_mm=4.1,
                gray=0.08,
            )
            y += 0.6
        y += 2.0


def draw_credits_page(
    cr: cairo.Context[cairo.Surface],
    page: PageGeometry,
    family: str,
    left_sections: tuple[tuple[str, tuple[str, ...]], ...],
    right_sections: tuple[tuple[str, tuple[str, ...]], ...],
) -> None:
    """Draw the source acknowledgements and concise licence summary."""
    left = page.margin_mm + 4.0
    right = page.width_mm - page.margin_mm - 4.0
    gap = 12.0
    column_width = (right - left - gap) / 2.0
    right_column = left + column_width + gap

    _text(cr, "Data Sources & Acknowledgements", left, page.margin_mm, family, 15.0, bold=True)
    y = page.margin_mm + 10.0
    y = _paragraph(
        cr,
        "NightSky Atlas builds upon the work of astronomers, researchers and open-source "
        "contributors who have made astronomical data and tools available.",
        left,
        y,
        right - left,
        family,
        size_pt=8.6,
        line_step_mm=4.2,
        gray=0.12,
    )
    y = _paragraph(
        cr,
        "The following sources and projects have contributed to the atlas.",
        left,
        y + 0.2,
        right - left,
        family,
        size_pt=8.6,
        line_step_mm=4.2,
        gray=0.12,
    )
    source_y = max(page.margin_mm + 29.0, y + 2.0)
    _draw_credit_column(cr, left_sections, left, source_y, column_width, family)
    _draw_credit_column(cr, right_sections, right_column, source_y, column_width, family)

    licence_y = page.height_mm - 59.0
    _rule(cr, left, right, licence_y - 5.0)
    _text(cr, "LICENCE & USAGE", left, licence_y, family, 8.0, bold=True, gray=0.34)
    left_text = (
        "Source code and atlas generator: MIT License.",
        "Original cartographic design and project-authored artwork: CC BY 4.0, where identified.",
    )
    right_text = (
        "Official atlas PDFs are free to download, print and share for non-commercial purposes, "
        "subject to applicable third-party licences. Retain credits and notices.",
        "Third-party material keeps its own terms. The MIT License applies to the generator, "
        "not automatically to generated atlases.",
    )
    for entries, x in ((left_text, left), (right_text, right_column)):
        for row, text in enumerate(entries):
            _paragraph(
                cr,
                text,
                x,
                licence_y + 7.0 + row * 8.2,
                column_width,
                family,
                size_pt=7.8,
                line_step_mm=3.8,
                gray=0.1,
            )

    _text(
        cr,
        "Full references, source URLs and licence details are in docs/DATA_SOURCES.md "
        "and THIRD_PARTY_LICENSES.md.",
        left,
        page.height_mm - page.margin_mm - 8.0,
        family,
        7.2,
        gray=0.38,
    )
    footer = "NightSky Atlas · Created and maintained by Frédéric Carron"
    width_pt, _ = measure_point_size(cr, footer, family, 7.2)
    _text(
        cr,
        footer,
        (mm_to_pt(page.width_mm - page.margin_mm) - width_pt) * 25.4 / 72.0,
        page.height_mm - page.margin_mm,
        family,
        7.2,
        gray=0.42,
    )


def draw_introduction(
    cr: cairo.Context[cairo.Surface], atlas: AtlasConfig, style: StyleConfig
) -> None:
    """Draw the short practical introduction shared by all editions."""
    page = atlas.page.to_geometry()
    family = style.typography.sans_family
    left = page.margin_mm + 4.0
    right = page.width_mm - page.margin_mm - 4.0
    width = right - left
    column_width = (width - 12.0) / 2.0
    right_column = left + column_width + 12.0

    _text(
        cr,
        "NIGHTSKY ATLAS  /  INTRODUCTION",
        left,
        page.margin_mm,
        family,
        7.0,
        bold=True,
        gray=0.42,
    )
    _text(
        cr,
        "A practical atlas for the night sky",
        left,
        page.margin_mm + 13.0,
        family,
        19.3,
        bold=True,
    )
    _text(
        cr,
        "Open-source charts for visual observing and star-hopping",
        left,
        page.margin_mm + 22.0,
        family,
        8.8,
        gray=0.32,
    )
    _rule(cr, left, right, page.margin_mm + 27.0)

    _text(
        cr,
        "PURPOSE",
        left,
        47.0,
        family,
        7.2,
        bold=True,
        gray=0.38,
        tracking_pt=0.25,
    )
    _paragraph(
        cr,
        "NightSky Atlas is an open-source set of printable sky charts for visual observers. "
        "Use star patterns to find a target at the telescope. The source code is MIT licensed; "
        "catalogue and artwork terms are listed on the credits page.",
        left,
        53.0,
        page.width_mm - page.margin_mm - left,
        family,
        size_pt=8.6,
    )

    _text(
        cr,
        "THREE EDITIONS",
        left,
        73.0,
        family,
        7.2,
        bold=True,
        gray=0.38,
        tracking_pt=0.25,
    )
    _text(cr, "Edition", left, 81.0, family, 7.0, bold=True)
    _text(cr, "Scale", left + 57.0, 81.0, family, 7.0, bold=True)
    _text(cr, "Stars to", left + 100.0, 81.0, family, 7.0, bold=True)
    _text(cr, "Field and deep-sky content", left + 135.0, 81.0, family, 7.0, bold=True)
    for row, (name, scale, magnitude, use) in enumerate(
        (
            ("Pocket", "5 mm/°", "mag 7.5", "Wide fields; selected bright targets"),
            ("Standard", "10 mm/°", "mag 9", "Balanced observing; Messier and Herschel 400"),
            ("Deep", "20 mm/°", "mag 10.5", "Small fields; deeper DSO catalogue"),
        )
    ):
        y = 90.0 + row * 8.0
        _text(cr, name, left, y, family, 8.2, bold=name == atlas.resolved_edition().name)
        _text(cr, scale, left + 57.0, y, family, 8.2)
        _text(cr, magnitude, left + 100.0, y, family, 8.2)
        _text(cr, use, left + 135.0, y, family, 8.2)
    _text(
        cr,
        "Stellar limits describe plotted stars; visibility at the eyepiece depends on conditions.",
        left,
        114.0,
        family,
        6.6,
        gray=0.34,
    )
    _rule(cr, left, right, 119.0)

    _text(
        cr,
        "READING A CHART",
        left,
        128.0,
        family,
        7.2,
        bold=True,
        gray=0.38,
        tracking_pt=0.25,
    )
    _paragraph(
        cr,
        "Start with the north or south overview, then use chart codes and the object index. "
        "Main charts overlap; codes at the edges point to neighbouring pages. A dashed frame "
        "and its code lead to a detail map. Coordinates are J2000/ICRS, north is up and east "
        "is left. Small ticks outside the chart frame mark coordinate intervals.",
        left,
        134.0,
        column_width,
        family,
        size_pt=8.7,
    )
    _text(
        cr,
        "STARS AND DOUBLE STARS",
        left,
        169.0,
        family,
        7.2,
        bold=True,
        gray=0.38,
        tracking_pt=0.25,
    )
    _paragraph(
        cr,
        "Star disks encode magnitude; familiar names, Bayer letters and Flamsteed numbers are "
        "selective. Tycho-2 is supplemented by Hipparcos for bright stars. Selected WDS pairs "
        "show two real positions when separable; a short bar marks an unresolved pair, "
        "not its angle.",
        left,
        175.0,
        column_width,
        family,
        size_pt=7.8,
        line_step_mm=4.7,
    )

    _text(
        cr,
        "DEEP-SKY OBJECTS",
        right_column,
        128.0,
        family,
        7.2,
        bold=True,
        gray=0.38,
        tracking_pt=0.25,
    )
    _paragraph(
        cr,
        "Symbols distinguish galaxies, clusters and nebulae. M denotes Messier; bare numbers "
        "mean NGC and I denotes IC. Galaxy ellipses follow catalogue axes when available. A small "
        "dashed nebula symbol locates an object; a traced outline shows image-based form where "
        "available. Stronger galaxy contours suggest easier visual detection, never certainty.",
        right_column,
        134.0,
        column_width,
        family,
        size_pt=8.2,
        line_step_mm=5.1,
    )
    _text(
        cr,
        "PRINTING AND USE",
        right_column,
        174.0,
        family,
        7.2,
        bold=True,
        gray=0.38,
        tracking_pt=0.25,
    )
    _paragraph(
        cr,
        "Print the vector PDF on A4 landscape at 100% or actual size. Personal printing is free. "
        "Check the credits and source licences before redistributing an atlas PDF.",
        right_column,
        180.0,
        column_width,
        family,
        size_pt=7.8,
        line_step_mm=4.7,
    )
    _footer(cr, page, atlas.resolved_edition().name, family, "Introduction")


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
    label_x = center_x + diameters[-1] / 2.0 + 2.0
    for label, label_offset_mm in zip(("0.5°", "2°", "4°"), (-5.0, 0.0, 5.0), strict=True):
        _text(
            cr,
            label,
            label_x,
            center_y + label_offset_mm + 0.8,
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
        star_id="legend:a",
        page_point=PagePoint(x_mm=x + 11.0, y_mm=y + 12.0),
        magnitude=magnitude,
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
    separation = (
        style.double_stars.marginal_clearance_mm + 0.2 + (first_diameter + second_diameter) / 2.0
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
    family = style.typography.sans_family
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

    if style.variable_stars.enabled:
        _draw_variable_star_example(cr, left + 4.0, 85.0, style, star_model)
        _text(
            cr,
            "Strong variables only · incomplete selection · no current brightness",
            left + 12.0,
            86.7,
            family,
            6.0,
            gray=0.32,
        )
    if style.double_stars.enabled:
        _draw_double_star_examples(cr, left, 94.0, style, star_model, family)

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
        "Shape = type · " + dso_size_legend_text(style),
        left,
        119.0,
        family,
        6.4,
        gray=0.35,
    )
    for index, symbol in enumerate(legend_symbols(style, mm_per_degree)):
        column, row = index % 2, index // 2
        x = left + column * 67.0
        y = 122.0 + row * 8.0
        _text(cr, symbol.name, x + 1.5, y + 1.5, family, 5.8, bold=True)
        cr.set_source_rgb(0.0, 0.0, 0.0)
        cr.set_line_width(mm_to_pt(style.dso.line_width_mm))
        cr.new_path()
        draw_dso_symbol(
            cr,
            mm_to_pt(x + (30.0 if symbol.minimum_extent is not None else 5.5)),
            mm_to_pt(y + 5.5),
            symbol.extent,
            style.dso.dash_mm,
        )
        if symbol.minimum_extent is not None:
            _text(
                cr,
                f"{symbol.angular_size_arcmin:g}′",
                x + 33.5,
                y + 6.4,
                family,
                5.0,
            )
            cr.new_path()
            draw_dso_symbol(
                cr,
                mm_to_pt(x + 47.0),
                mm_to_pt(y + 5.5),
                symbol.minimum_extent,
                style.dso.dash_mm,
            )
            _text(cr, symbol.minimum_label or "", x + 50.5, y + 6.4, family, 5.0)
        else:
            _text(cr, "fixed", x + 10.0, y + 6.4, family, 5.0, gray=0.35)

    _rule(cr, left, right, 156.0)
    _text(cr, "GALAXY VISIBILITY", left, 162.0, family, 7.0, bold=True, gray=0.38)
    _text(
        cr,
        "Stronger contour = easier integrated-light visibility",
        left + 39.0,
        162.0,
        family,
        6.1,
        gray=0.32,
    )
    for index, example in enumerate(galaxy_visibility_examples(style)):
        contour = example.contour
        y = 170.0 + index * 4.0
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


def _draw_variable_star_example(
    cr: cairo.Context[cairo.Surface],
    x: float,
    y: float,
    style: StyleConfig,
    size_model: StarSizeModel,
) -> None:
    diameter = size_model.diameter_mm(4.5)
    _dot(cr, x, y, diameter)
    draw_variable_star_ring(cr, x, y, diameter, style)
