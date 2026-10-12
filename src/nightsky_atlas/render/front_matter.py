"""Compact printed field guide and edition-specific symbol legend."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

import cairo

from nightsky_atlas import __version__
from nightsky_atlas.atlas.config import AtlasConfig, GalaxyContourStyle, StyleConfig
from nightsky_atlas.atlas.detail_geometry import detail_chart_parent_ids
from nightsky_atlas.atlas.tiling import chart_definitions
from nightsky_atlas.catalog.models import DeepSkyObject, DsoType, Provenance
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.chart.page import PagePoint, PageTransform
from nightsky_atlas.render.cairo import _draw_double_star_mark, draw_dso_symbol, draw_star_disk
from nightsky_atlas.render.detail_markers import build_detail_marker, draw_detail_markers
from nightsky_atlas.render.double_stars import DoubleStarMark
from nightsky_atlas.render.symbols import (
    StarSizeModel,
    SymbolExtent,
    compact_star_reference_magnitudes,
    dso_symbol_extent,
)
from nightsky_atlas.render.text import (
    draw_centered_text,
    draw_text,
    draw_tracked_text,
    measure_point_size,
)
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
    size_classes: tuple[tuple[str, SymbolExtent], ...] = ()


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


def planetary_nebula_size_ranges(threshold_arcmin: float) -> tuple[str, ...]:
    """Return edition-specific printed size ranges for the PN legend samples."""

    def format_arcmin(value: float) -> str:
        return f"{value:.3f}".rstrip("0").rstrip(".")

    large_min = threshold_arcmin * 0.25
    medium_min = threshold_arcmin * 0.10
    return (
        f"≥{format_arcmin(threshold_arcmin)}′",
        f"{format_arcmin(large_min)}–<{format_arcmin(threshold_arcmin)}′",
        f"{format_arcmin(medium_min)}–<{format_arcmin(large_min)}′",
        f"<{format_arcmin(medium_min)}′",
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
        if object_type == DsoType.PLANETARY_NEBULA and minimum_arcmin is not None:
            sample_arcmin = minimum_arcmin
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
        size_classes: tuple[tuple[str, SymbolExtent], ...] = ()
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
            if object_type == DsoType.PLANETARY_NEBULA:
                class_samples = (
                    ("large", minimum_arcmin * 0.5),
                    ("medium", minimum_arcmin * 0.15),
                    ("small", minimum_arcmin * 0.05),
                )
                size_classes = tuple(
                    (
                        label,
                        dso_symbol_extent(
                            make_sample(
                                f"legend:{object_type.value}:{label}",
                                object_type,
                                size_arcmin,
                                None,
                            ),
                            mm_per_deg=mm_per_degree,
                            style=style,
                        ),
                    )
                    for label, size_arcmin in class_samples
                )
        symbols.append(
            LegendSymbol(
                name,
                object_type,
                sample_arcmin,
                dso_symbol_extent(sample, mm_per_deg=mm_per_degree, style=style),
                minimum_extent,
                minimum_label,
                size_classes,
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
    tracking_pt: float = 0.35,
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
    max_y_mm: float | None = None,
) -> float:
    line = ""

    def draw_line(value: str, baseline_y: float) -> None:
        if max_y_mm is not None and baseline_y > max_y_mm:
            raise ValueError("credits text exceeds its available page area")
        _text(cr, value, x_mm, baseline_y, family, size_pt, gray=gray)

    def split_long_word(word: str) -> list[str]:
        chunks: list[str] = []
        chunk = ""
        for character in word:
            candidate = chunk + character
            width_pt, _ = measure_point_size(cr, candidate, family, size_pt)
            if chunk and width_pt > mm_to_pt(width_mm):
                chunks.append(chunk)
                chunk = character
            else:
                chunk = candidate
        if chunk:
            chunks.append(chunk)
        return chunks

    words_to_place = [chunk for word in words.split() for chunk in split_long_word(word)]
    for word in words_to_place:
        candidate = f"{line} {word}" if line else word
        candidate_width_pt, _ = measure_point_size(cr, candidate, family, size_pt)
        if line and candidate_width_pt > mm_to_pt(width_mm):
            draw_line(line, y_mm)
            y_mm += line_step_mm
            line = word
        else:
            line = candidate
    if line:
        draw_line(line, y_mm)
        y_mm += line_step_mm
    return y_mm


def _draw_credit_column(
    cr: cairo.Context[cairo.Surface],
    sections: tuple[tuple[str, tuple[str, ...]], ...],
    x_mm: float,
    y_mm: float,
    width_mm: float,
    family: str,
    *,
    max_y_mm: float,
) -> float:
    y = y_mm
    for heading, entries in sections:
        if not entries:
            continue
        if y > max_y_mm:
            raise ValueError("credits section heading exceeds its available page area")
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
                max_y_mm=max_y_mm,
            )
            y += 0.6
        y += 2.0
    return y


def draw_credits_page(
    cr: cairo.Context[cairo.Surface],
    page: PageGeometry,
    family: str,
    left_sections: tuple[tuple[str, tuple[str, ...]], ...],
    right_sections: tuple[tuple[str, tuple[str, ...]], ...],
    *,
    edition: str = "",
    catalogue_data_label: str = "per-source metadata in the build manifest",
) -> None:
    """Draw source credits, conservative licence notes and build-specific metadata."""
    left = page.margin_mm + 4.0
    right = page.width_mm - page.margin_mm - 4.0
    gap = 12.0
    column_width = (right - left - gap) / 2.0
    right_column = left + column_width + gap
    licence_y = page.height_mm - 59.0
    source_bottom = licence_y - 12.0

    _text(cr, "Data Sources & Credits", left, page.margin_mm, family, 15.0, bold=True)
    y = page.margin_mm + 10.0
    y = _paragraph(
        cr,
        "NightSky Atlas uses astronomical catalogues, published research and openly available "
        "cartographic data. The principal sources are listed below.",
        left,
        y,
        right - left,
        family,
        size_pt=8.6,
        line_step_mm=4.2,
        gray=0.12,
    )
    y += 0.2
    source_y = max(page.margin_mm + 29.0, y + 2.0)
    _draw_credit_column(
        cr,
        left_sections,
        left,
        source_y,
        column_width,
        family,
        max_y_mm=source_bottom,
    )
    _draw_credit_column(
        cr,
        right_sections,
        right_column,
        source_y,
        column_width,
        family,
        max_y_mm=source_bottom,
    )

    _rule(cr, left, right, licence_y - 5.0)
    _text(cr, "LICENCE & USAGE", left, licence_y, family, 8.0, bold=True, gray=0.34)
    left_text = (
        "Source code and atlas generator: MIT License.",
        "Original cartographic design and project-authored artwork: CC BY 4.0 where explicitly "
        "identified. Third-party material retains its applicable licences and attribution.",
    )
    right_text = (
        "The atlas PDFs are freely available for download and printing. Further redistribution "
        "and modification must respect the applicable licences and notices.",
        "The MIT License applies to the generator, not automatically to generated atlases. "
        "No blanket commercial permission is asserted for third-party material.",
    )
    metadata_y = page.height_mm - page.margin_mm - 14.0
    documentation_y = page.height_mm - page.margin_mm - 5.0
    licence_bottom = metadata_y - 3.0
    for entries, x in ((left_text, left), (right_text, right_column)):
        y = licence_y + 7.0
        for text in entries:
            y = _paragraph(
                cr,
                text,
                x,
                y,
                column_width,
                family,
                size_pt=7.8,
                line_step_mm=3.8,
                gray=0.1,
                max_y_mm=licence_bottom,
            )
            y += 1.8

    _text(
        cr,
        f"Edition: {edition} · Atlas version: {__version__} · "
        f"Catalogue data: {catalogue_data_label}",
        left,
        metadata_y,
        family,
        6.5,
        gray=0.38,
    )
    _text(
        cr,
        "Project: github.com/fcarron/nightsky-atlas",
        left,
        documentation_y - 3.0,
        family,
        6.5,
        gray=0.38,
    )
    _text(
        cr,
        "Full references and licence details: docs/DATA_SOURCES.md · THIRD_PARTY_LICENSES.md",
        left,
        documentation_y + 1.0,
        family,
        6.5,
        gray=0.38,
    )
    footer = "NightSky Atlas · Created by Frédéric Carron"
    width_pt, _ = measure_point_size(cr, footer, family, 7.0)
    _text(
        cr,
        footer,
        (mm_to_pt(page.width_mm - page.margin_mm) - width_pt) * 25.4 / 72.0,
        page.height_mm - page.margin_mm - 5.0,
        family,
        7.0,
        gray=0.42,
    )


def draw_introduction(
    cr: cairo.Context[cairo.Surface],
    atlas: AtlasConfig,
    style: StyleConfig,
    main_charts: Sequence[ChartDefinition] | None = None,
) -> None:
    """Draw the approved practical introduction using active edition geometry."""
    page = atlas.page.to_geometry()
    family = style.typography.sans_family
    left = page.margin_mm + 4.0
    right = page.width_mm - page.margin_mm - 4.0
    width = right - left
    charts = tuple(main_charts) if main_charts is not None else tuple(chart_definitions(atlas))
    ring_centers = tuple(atlas.tiling.declination_centers) if atlas.tiling else ()
    polar_count = 2 if atlas.tiling and atlas.tiling.polar_caps else 0
    ring_counts_by_center = Counter(
        round(chart.center_dec_deg, 6)
        for chart in charts
        if abs(chart.center_dec_deg) < 90.0 - 1e-6
    )
    ring_counts = tuple(
        ring_counts_by_center.get(round(dec, 6), 0) for dec in sorted(ring_centers, reverse=True)
    )
    chart_layout = _edition_chart_layout(
        atlas,
        chart_count=len(charts),
        ring_counts=ring_counts,
        ring_count=len(ring_centers),
        polar_count=polar_count,
    )

    _text(cr, "NightSky Atlas", left, page.margin_mm + 0.5, family, 22.0, bold=True)
    _text(cr, "INTRODUCTION", left, page.margin_mm + 11.0, family, 9.5, bold=True, gray=0.34)
    intro_y = page.margin_mm + 19.0
    paragraph_gap_mm = 2.0
    intro_y = _paragraph(
        cr,
        "NightSky Atlas is a freely available, printable star atlas designed for visual observing.",
        left,
        intro_y,
        154.0,
        family,
        size_pt=9.2,
        line_step_mm=4.45,
    )
    intro_y += paragraph_gap_mm
    intro_y = _paragraph(
        cr,
        "The atlas PDFs can be downloaded and printed free of charge. The software used to "
        "generate them is open source, allowing anyone to customize the charts or create their "
        "own atlas editions.",
        left,
        intro_y,
        154.0,
        family,
        size_pt=9.2,
        line_step_mm=4.45,
    )
    intro_y += paragraph_gap_mm
    _paragraph(
        cr,
        "Three editions offer different levels of detail, while sharing the same cartographic "
        "conventions and A4 page format.",
        left,
        intro_y,
        154.0,
        family,
        size_pt=9.2,
        line_step_mm=4.45,
    )
    _rule(cr, left, right, 68.0)
    _text(cr, "THREE EDITIONS", left, 74.0, family, 9.5, bold=True, gray=0.34)
    gap = 10.0
    col_width = (width - 2.0 * gap) / 3.0
    editions = (
        (
            "Pocket",
            "5 mm/° · Stars to magnitude 7.5",
            "Pocket provides a wide-field overview of the sky, suitable for general orientation, "
            "binoculars and small telescopes. It includes all Messier and Herschel 400 objects, "
            "along with many additional deep-sky targets. Its broad coverage also makes it useful "
            "with larger telescopes, particularly for locating objects and exploring wider regions "
            "of the sky.",
        ),
        (
            "Standard",
            "10 mm/° · Stars to magnitude 9",
            "Standard offers twice the map scale of Pocket, with more stars and a richer "
            "selection of deep-sky objects. It is intended as a general-purpose observing atlas, "
            "particularly well suited to medium-sized telescopes. The additional detail makes "
            "it easier to navigate smaller star patterns and locate fainter targets.",
        ),
        (
            "Deep",
            "20 mm/° · Stars to magnitude 10.5",
            "Deep provides the highest level of detail, with denser star fields and a more "
            "extensive deep-sky catalogue. It is intended for detailed exploration of smaller "
            "sky regions, especially when observing faint or challenging objects with larger "
            "telescopes.",
        ),
    )
    for index, (heading, specification, text) in enumerate(editions):
        x = left + index * (col_width + gap)
        _text(cr, heading, x, 82.0, family, 12.0, bold=True)
        _text(cr, specification, x, 89.0, family, 8.5, gray=0.3)
        _paragraph(
            cr,
            text,
            x,
            95.0,
            col_width,
            family,
            size_pt=8.5,
            line_step_mm=4.2,
            max_y_mm=134.0,
        )
    _rule(cr, left, right, 139.0)
    lower_gap = 12.0
    lower_width = (width - lower_gap) / 2.0
    _text(cr, "CHART LAYOUT", left, 146.0, family, 9.5, bold=True, gray=0.34)
    _paragraph(
        cr,
        chart_layout,
        left,
        153.0,
        lower_width,
        family,
        size_pt=8.4,
        line_step_mm=4.25,
        max_y_mm=page.height_mm - page.margin_mm - 10.0,
    )
    printing_x = left + lower_width + lower_gap
    _text(cr, "PRINTING", printing_x, 146.0, family, 9.5, bold=True, gray=0.34)
    _paragraph(
        cr,
        "The atlas is designed for A4 landscape printing. Print at 100% (actual size) and "
        "disable automatic scaling or Fit to page to preserve the intended map scale. The charts "
        "are vector graphics and remain sharp when printed.",
        printing_x,
        153.0,
        lower_width,
        family,
        size_pt=8.4,
        line_step_mm=4.25,
        max_y_mm=page.height_mm - page.margin_mm - 10.0,
    )
    _footer(cr, page, atlas.resolved_edition().name, family, "Introduction")


def _edition_chart_layout(
    atlas: AtlasConfig,
    *,
    chart_count: int,
    ring_counts: tuple[int, ...],
    ring_count: int,
    polar_count: int,
) -> str:
    edition = atlas.resolved_edition().name
    if not ring_count:
        return (
            f"This {edition} build contains {chart_count} configured charts. The overview maps "
            "show their arrangement and numbering. Adjacent chart fields overlap where "
            "configured to support navigation; selected regions have additional detail charts."
        )
    if ring_counts:
        ring_chart_count = sum(ring_counts)
        centers = tuple(sorted(atlas.tiling.declination_centers, reverse=True))
        if len(set(ring_counts)) == 1:
            grid_text = "The rings use regular right ascension grids, aligned north to south."
        else:
            grid_text = (
                "The rings use regular right ascension grids, with matching centres where the "
                "grid counts allow."
            )
        if centers and centers == tuple(-value for value in reversed(centers)):
            symmetry = "The layout is symmetrical about the celestial equator."
        else:
            symmetry = "The rings follow the active edition tiling."
        if polar_count:
            chart_summary = (
                f"The {edition} edition covers the entire sky with {chart_count} main charts: "
                f"{ring_chart_count} arranged in {ring_count} declination rings, plus "
                f"{polar_count} polar charts."
            )
        else:
            chart_summary = (
                f"The {edition} edition covers the entire sky with {chart_count} main charts "
                f"arranged in {ring_count} declination rings."
            )
        return (
            f"{chart_summary} {symmetry} "
            f"{grid_text} Adjacent charts overlap to allow continuous navigation. The northern "
            "and southern overview maps show the arrangement and numbering. Additional detail "
            "charts are provided for selected regions."
        )
    return (
        f"{edition} covers the whole sky with {chart_count} charts. The chart fields are "
        "arranged in overlapping declination bands, with separate coverage of the celestial "
        "poles. The northern and southern overview maps show the chart arrangement and "
        "numbering. Selected regions have additional detail charts."
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
    _text(cr, "MAP LINES", left, top, family, 8.0, bold=True, gray=0.38)
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
        _text(cr, name, x + 12.0, y - 3.3, family, 7.5)


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
            7.0,
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
    _text(cr, "DOUBLE STARS", x, y, family, 8.0, bold=True, gray=0.38)
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
    _text(cr, "unresolved", x + 18.0, y + 14.5, family, 7.0)

    first_diameter = size_model.diameter_mm(5.0)
    second_diameter = size_model.diameter_mm(6.5)
    separation = (
        style.double_stars.marginal_clearance_mm + 0.2 + (first_diameter + second_diameter) / 2.0
    )
    first_x = x + 72.0
    second_x = first_x + separation
    _dot(cr, first_x, y + 12.0, first_diameter)
    _dot(cr, second_x, y + 12.0, second_diameter)
    _text(cr, "resolved", second_x + 4.0, y + 14.5, family, 7.0)


def draw_field_guide(
    cr: cairo.Context[cairo.Surface],
    atlas: AtlasConfig,
    style: StyleConfig,
    chart_count: int,
    mm_per_degree: float,
) -> None:
    """Draw a graphical guide to the edition's real chart marks and symbols."""
    page = atlas.page.to_geometry()
    family = style.typography.sans_family
    left = page.margin_mm + 4.0
    right = page.width_mm - page.margin_mm - 4.0
    width = right - left
    gap = 8.0
    column_width = (width - gap) / 2.0
    right_column = left + column_width + gap

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
    _text(cr, "Field guide & symbol key", left, page.margin_mm + 5.5, family, 19.0, bold=True)
    _text(
        cr,
        f"{atlas.resolved_edition().name}  ·  {chart_count} charts  ·  stars to "
        f"magnitude {atlas.stellar_limit_magnitude:g}  ·  J2000 / ICRS  ·  "
        f"{mm_per_degree:.1f} mm/°",
        left,
        page.margin_mm + 17.0,
        family,
        8.2,
        gray=0.3,
    )
    _rule(cr, left, right, page.margin_mm + 23.0)

    _text(cr, "STARS", left, 43.0, family, 8.5, bold=True, gray=0.34)
    _paragraph(
        cr,
        "Larger disks are brighter. Selected labels use proper names, Bayer letters or "
        "Flamsteed numbers.",
        left,
        49.0,
        column_width,
        family,
        size_pt=8.0,
        line_step_mm=4.1,
    )
    star_model = StarSizeModel.from_style(style.star)
    magnitudes = compact_star_reference_magnitudes(atlas.stellar_limit_magnitude)
    spacing = min(19.0, (column_width - 20.0) / max(1, len(magnitudes) - 1))
    scale_start = left + 8.0
    for index, magnitude in enumerate(magnitudes):
        x = scale_start + index * spacing
        diameter = star_model.diameter_mm(magnitude)
        _text(cr, f"{magnitude:g}", x - 2.4, 61.0, family, 7.0, bold=True)
        _dot(cr, x, 67.0, diameter)

    if style.variable_stars.enabled:
        _draw_variable_star_example(cr, left + 3.0, 76.0, style, star_model)
        _text(
            cr,
            "Selected variable stars are ringed; selection is incomplete and current brightness "
            "is not shown.",
            left + 11.0,
            77.7,
            family,
            7.4,
            gray=0.32,
        )
    if style.double_stars.enabled:
        _draw_double_star_examples(cr, left, 84.0, style, star_model, family)
        _paragraph(
            cr,
            "Resolved pairs show separate components; close pairs use a double-star marker.",
            left,
            103.5,
            column_width,
            family,
            size_pt=7.4,
            line_step_mm=3.0,
        )

    _text(cr, "CONSTELLATIONS", right_column, 43.0, family, 8.5, bold=True, gray=0.34)
    _paragraph(
        cr,
        "Figures follow Sky & Telescope patterns distributed with Stellarium. Boundaries follow "
        "the International Astronomical Union (IAU).",
        right_column,
        49.0,
        column_width,
        family,
        size_pt=8.0,
        line_step_mm=4.1,
    )
    _draw_map_lines(cr, style, family, right_column, 59.0, column_width)

    _text(cr, "DEEP-SKY OBJECTS", left, 108.0, family, 8.5, bold=True, gray=0.34)
    _paragraph(
        cr,
        "Symbols identify object classes. Reliable sizes are approximately to scale; small "
        "objects are enlarged. Galaxy ellipses follow catalogue size and orientation. Nebula "
        "outlines are approximate, not physical boundaries.",
        left,
        114.0,
        column_width,
        family,
        size_pt=8.0,
        line_step_mm=3.8,
    )
    symbols = legend_symbols(style, mm_per_degree)
    for index, symbol in enumerate(symbols):
        x = left
        y = 123.0 + index * 6.0 + (2.0 if index >= 4 else 0.0)
        _text(cr, symbol.name, x + 1.0, y + 1.3, family, 7.0, bold=True)
        if symbol.size_classes:
            ranges = planetary_nebula_size_ranges(symbol.angular_size_arcmin or 0.0)
            samples = (("scale", symbol.extent), *symbol.size_classes)
            for sample_index, (_, extent) in enumerate(samples):
                center_x = x + 68.0 + sample_index * 14.0
                cr.new_path()
                draw_dso_symbol(
                    cr,
                    mm_to_pt(center_x),
                    mm_to_pt(y + 3.2),
                    extent,
                    style.dso.dash_mm,
                )
                draw_centered_text(
                    cr,
                    ranges[sample_index],
                    mm_to_pt(center_x),
                    mm_to_pt(y + 5.7),
                    family,
                    6.0,
                    "normal",
                )
            continue
        sample_x = x + 68.0
        cr.new_path()
        draw_dso_symbol(cr, mm_to_pt(sample_x), mm_to_pt(y + 3.1), symbol.extent, style.dso.dash_mm)
        if symbol.minimum_extent is not None:
            draw_centered_text(
                cr,
                f"{symbol.angular_size_arcmin:g}′",
                mm_to_pt(sample_x + 9.0),
                mm_to_pt(y + 3.8),
                family,
                6.0,
                "normal",
            )
            cr.new_path()
            draw_dso_symbol(
                cr,
                mm_to_pt(sample_x + 23.0),
                mm_to_pt(y + 3.1),
                symbol.minimum_extent,
                style.dso.dash_mm,
            )
            draw_centered_text(
                cr,
                symbol.minimum_label or "",
                mm_to_pt(sample_x + 32.0),
                mm_to_pt(y + 3.8),
                family,
                6.0,
                "normal",
            )
        else:
            draw_centered_text(
                cr,
                "fixed",
                mm_to_pt(sample_x + 15.0),
                mm_to_pt(y + 3.8),
                family,
                6.0,
                "normal",
            )

    _text(cr, "OBJECT LABELS", left, 174.0, family, 8.0, bold=True, gray=0.34)
    _text(cr, "M31", left + 42.0, 174.0, family, 7.5, bold=True)
    _text(cr, "Messier", left + 52.0, 174.0, family, 7.0)
    _text(cr, "891", left + 79.0, 174.0, family, 7.5)
    _text(cr, "NGC", left + 89.0, 174.0, family, 7.0)
    _text(cr, "I1396", left + 108.0, 174.0, family, 7.5)
    _text(cr, "IC", left + 121.0, 174.0, family, 7.0)
    _text(
        cr,
        "Messier and Herschel 400 labels are bold; other designations are usually regular.",
        left,
        179.0,
        family,
        7.5,
    )

    _text(
        cr,
        "CHART COORDINATES AND NAVIGATION",
        right_column,
        88.0,
        family,
        8.0,
        bold=True,
        gray=0.34,
    )
    _paragraph(
        cr,
        "Charts use J2000 / ICRS coordinates; north is up and east is left. Right ascension is "
        "marked in hours, declination in degrees. Edge codes point to overlapping neighbours; "
        "dashed frames mark detail charts. Overviews and the object index aid navigation.",
        right_column,
        93.0,
        column_width,
        family,
        size_pt=7.8,
        line_step_mm=3.9,
    )
    _text(cr, "GALAXY VISIBILITY", left, 183.0, family, 8.0, bold=True, gray=0.34)
    _text(
        cr,
        "Contours estimate visual difficulty from apparent size and surface brightness "
        "(Crumey, 2014).",
        left,
        188.0,
        family,
        7.2,
        gray=0.18,
    )
    for index, example in enumerate(galaxy_visibility_examples(style)):
        contour = example.contour
        x = left + index * (column_width / 4.0)
        y = 192.0
        cr.save()
        cr.set_source_rgb(0.0, 0.0, 0.0)
        cr.set_line_width(mm_to_pt(contour.line_width_mm))
        if contour.dash_mm > 0.0:
            cr.set_dash([mm_to_pt(contour.dash_mm), mm_to_pt(contour.gap_mm or contour.dash_mm)])
        cr.move_to(mm_to_pt(x), mm_to_pt(y))
        cr.line_to(mm_to_pt(x + 12.0), mm_to_pt(y))
        cr.stroke()
        cr.restore()
        _text(cr, example.meaning, x, 193.5, family, 7.0)

    _draw_detail_frame_example(cr, atlas, style, right - 18.0, 110.0)
    telrad_diameter = telrad_ring_diameters_mm(mm_per_degree)[-1]
    telrad_radius = telrad_diameter / 2.0
    telrad_center_y = page.height_mm - page.margin_mm - 4.0 - telrad_radius
    telrad_heading_y = telrad_center_y - telrad_radius - 8.0
    _text(
        cr,
        "TELRAD REFERENCE",
        right_column,
        telrad_heading_y,
        family,
        8.0,
        bold=True,
        gray=0.34,
    )
    _text(
        cr,
        "Angular diameters: 0.5°, 2° and 4°",
        right_column + 37.0,
        telrad_heading_y,
        family,
        7.0,
        gray=0.3,
    )
    telrad_center_x = right_column + 30.0
    _draw_telrad(cr, telrad_center_x, telrad_center_y, mm_per_degree, family)
    _footer(cr, page, atlas.resolved_edition().name, family)


def _draw_detail_frame_example(
    cr: cairo.Context[cairo.Surface],
    atlas: AtlasConfig,
    style: StyleConfig,
    x_mm: float,
    y_mm: float,
) -> None:
    if not atlas.detail_charts:
        return
    charts = tuple(chart_definitions(atlas))
    detail = atlas.detail_charts[0]
    parent_ids = detail_chart_parent_ids((detail,), charts)[detail.id]
    parent = next((item for item in charts if parent_ids and item.id == parent_ids[0]), None)
    if parent is None:
        return
    sample_scale = min(30.0 / parent.width_deg, 16.0 / parent.height_deg)
    transform = PageTransform(
        parent,
        atlas.page.to_geometry(),
        scale_mm_per_degree=sample_scale,
    )
    marker = build_detail_marker(
        detail.model_copy(update={"parent_marker_label": ""}),
        parent,
        transform,
    )
    cr.save()
    cr.translate(
        mm_to_pt(x_mm - atlas.page.width_mm / 2.0),
        mm_to_pt(y_mm - atlas.page.height_mm / 2.0),
    )
    if marker is not None:
        draw_detail_markers(cr, (marker,), transform, style)
    cr.restore()


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
