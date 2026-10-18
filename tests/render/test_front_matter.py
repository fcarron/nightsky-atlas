from pathlib import Path

import cairo
import pytest

from nightsky_atlas import __version__
from nightsky_atlas.atlas.config import load_atlas_config, load_style_config
from nightsky_atlas.atlas.tiling import chart_definitions
from nightsky_atlas.chart.page import PagePoint, PageTransform
from nightsky_atlas.render import front_matter
from nightsky_atlas.render.front_matter import (
    draw_field_guide,
    draw_introduction,
    galaxy_visibility_examples,
    legend_symbols,
    planetary_nebula_size_ranges,
    telrad_ring_diameters_mm,
)
from nightsky_atlas.render.symbols import (
    SPOKED_CIRCLE_OUTER_FACTOR,
    DsoShape,
    compact_star_reference_magnitudes,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _configured_mm_per_degree(edition: str) -> float:
    atlas = load_atlas_config(REPO_ROOT / "atlas" / f"{edition}.yaml")
    if atlas.mm_per_degree is not None:
        return atlas.mm_per_degree
    if atlas.tiling is None:
        raise AssertionError(f"{edition} has no tiling scale")
    if atlas.tiling.mm_per_degree is not None:
        return atlas.tiling.mm_per_degree
    page = atlas.page.to_geometry()
    return min(
        page.printable_width_mm / atlas.tiling.width_deg,
        page.printable_height_mm / atlas.tiling.height_deg,
    )


@pytest.mark.parametrize(
    ("edition", "mm_per_degree", "minimum", "sample_size"),
    (
        ("pocket", 5.0, 20.0, 50.0),
        ("standard", 10.0, 10.0, 25.0),
        ("deep", 20.0, 5.0, 12.5),
        ("eyepiece", 40.0, 2.5, 6.25),
        ("eyepiece_deep", 80.0, 2.5, 6.25),
    ),
)
def test_legend_uses_edition_dso_geometry(
    edition: str,
    mm_per_degree: float,
    minimum: float,
    sample_size: float,
) -> None:
    style = load_style_config(REPO_ROOT / "styles" / f"{edition}.yaml")
    symbols = {item.name: item for item in legend_symbols(style, mm_per_degree)}

    assert len(symbols) == 10
    assert symbols["Bright nebula"].extent.shape == DsoShape.SQUARE
    assert symbols["Reflection nebula"].extent.shape == DsoShape.SQUARE
    assert symbols["Supernova remnant"].extent.shape == DsoShape.DASHED_SQUARE
    galaxy = symbols["Galaxy"]
    globular = symbols["Globular cluster"]
    assert galaxy.angular_size_arcmin == pytest.approx(sample_size)
    assert galaxy.extent.width_mm == pytest.approx(sample_size / 60.0 * mm_per_degree)
    assert globular.extent.width_mm == pytest.approx(sample_size / 60.0 * mm_per_degree)
    assert galaxy.minimum_label == f"<{minimum:g}′"
    assert globular.minimum_label == f"<{minimum:g}′"
    assert galaxy.minimum_extent is not None
    assert galaxy.minimum_extent.width_mm == pytest.approx(
        minimum / 60.0 * mm_per_degree
    )
    assert globular.minimum_extent is not None
    assert symbols["Open cluster"].minimum_extent is not None
    assert symbols["Planetary nebula"].minimum_extent is not None
    planetary = symbols["Planetary nebula"]
    assert planetary.angular_size_arcmin == pytest.approx(minimum)
    assert tuple(label for label, _ in planetary.size_classes) == (
        "large",
        "medium",
        "small",
    )
    pn_widths = tuple(extent.width_mm for _, extent in planetary.size_classes)
    assert pn_widths[0] > pn_widths[1] > pn_widths[2]
    if edition in {"deep", "eyepiece", "eyepiece_deep"}:
        assert symbols["Bright nebula"].minimum_extent is None
        assert symbols["Dark nebula"].minimum_extent is None
    else:
        assert symbols["Bright nebula"].minimum_extent is not None
        assert symbols["Dark nebula"].minimum_extent is not None
    assert symbols["Galaxy cluster"].minimum_extent is not None
    assert planetary.extent.width_mm == pytest.approx(
        minimum / 60.0 * mm_per_degree * SPOKED_CIRCLE_OUTER_FACTOR
    )
    assert symbols["Other / unknown"].size_classes == ()
    assert symbols["Other / unknown"].angular_size_arcmin is None
    assert symbols["Other / unknown"].minimum_extent is None


@pytest.mark.parametrize(
    ("threshold", "expected"),
    (
        (20.0, ("≥20′", "5–<20′", "2–<5′", "<2′")),
        (10.0, ("≥10′", "2.5–<10′", "1–<2.5′", "<1′")),
        (5.0, ("≥5′", "1.25–<5′", "0.5–<1.25′", "<0.5′")),
        (2.5, ("≥2.5′", "0.625–<2.5′", "0.25–<0.625′", "<0.25′")),
    ),
)
def test_planetary_nebula_legend_prints_edition_specific_size_ranges(
    threshold: float, expected: tuple[str, ...]
) -> None:
    assert planetary_nebula_size_ranges(threshold) == expected


@pytest.mark.parametrize(
    ("limit", "expected"),
    (
        (7.5, (0.0, 2.0, 4.0, 6.0, 7.5)),
        (9.0, (0.0, 2.0, 4.0, 6.0, 8.0, 9.0)),
        (10.0, (0.0, 2.0, 4.0, 6.0, 8.0, 10.0)),
        (11.0, (0.0, 2.0, 4.0, 6.0, 8.0, 10.0, 11.0)),
    ),
)
def test_compact_magnitude_scale_uses_intervals_and_exact_limit(
    limit: float, expected: tuple[float, ...]
) -> None:
    assert compact_star_reference_magnitudes(limit) == expected


@pytest.mark.parametrize("edition", ("pocket", "standard", "deep"))
def test_telrad_reference_uses_edition_chart_scale(edition: str) -> None:
    scale = _configured_mm_per_degree(edition)
    expected_scale = tuple(scale * degrees for degrees in (0.5, 2.0, 4.0))
    assert telrad_ring_diameters_mm(scale) == pytest.approx(expected_scale)


@pytest.mark.parametrize("edition", ("pocket", "standard", "deep"))
def test_galaxy_visibility_key_uses_all_configured_contour_styles(edition: str) -> None:
    style = load_style_config(REPO_ROOT / "styles" / f"{edition}.yaml")
    examples = galaxy_visibility_examples(style)

    assert tuple(item.contour_class for item in examples) == ("bold", "normal", "fine", "dotted")
    assert tuple(item.meaning for item in examples) == (
        "easy",
        "moderate",
        "difficult",
        "threshold",
    )
    assert tuple(item.contour for item in examples) == (
        style.dso.galaxy_contours.bold,
        style.dso.galaxy_contours.normal,
        style.dso.galaxy_contours.fine,
        style.dso.galaxy_contours.dotted,
    )


def test_standard_design_scale_is_exact_and_chart_frame_follows_it() -> None:
    atlas = load_atlas_config(REPO_ROOT / "atlas" / "standard.yaml")
    chart = chart_definitions(atlas)[0]
    transform = PageTransform(
        chart,
        atlas.page.to_geometry(),
        scale_mm_per_degree=atlas.mm_per_degree,
    )

    assert atlas.mm_per_degree == 10.0
    assert transform.mm_per_deg == 10.0
    assert transform.chart_rect.width_mm == pytest.approx(chart.width_deg * 10.0)
    assert transform.chart_rect.height_mm == pytest.approx(chart.height_deg * 10.0)
    assert transform.chart_rect.width_mm == pytest.approx(270.0)
    assert transform.chart_rect.height_mm == pytest.approx(185.0)
    assert transform.chart_rect.left_mm >= transform.page.margin_mm
    assert transform.chart_rect.right_mm <= transform.page.width_mm - transform.page.margin_mm
    assert transform.chart_rect.top_mm >= transform.page.margin_mm
    assert transform.chart_rect.bottom_mm <= transform.page.height_mm - transform.page.margin_mm


def test_standard_star_scale_and_telrad_sizes_are_exact() -> None:
    atlas = load_atlas_config(REPO_ROOT / "atlas" / "standard.yaml")
    assert compact_star_reference_magnitudes(atlas.stellar_limit_magnitude) == (
        0.0,
        2.0,
        4.0,
        6.0,
        8.0,
        9.0,
    )
    assert telrad_ring_diameters_mm(atlas.mm_per_degree) == pytest.approx((5.0, 20.0, 40.0))
    for edition in ("pocket", "deep"):
        other = load_atlas_config(REPO_ROOT / "atlas" / f"{edition}.yaml")
        assert other.mm_per_degree == pytest.approx(5.0 if edition == "pocket" else 20.0)


@pytest.mark.parametrize(
    ("edition", "layout_fact"),
    (
        ("pocket", "39 main charts: 37 arranged in 5 declination rings, plus 2 polar charts"),
        (
            "standard",
            "129 main charts: 127 arranged in 11 declination rings, plus 2 polar charts",
        ),
        ("deep", "492 main charts: 490 arranged in 23 declination rings, plus 2 polar charts"),
    ),
)
def test_introduction_uses_current_edition_chart_geometry(
    edition: str, layout_fact: str, monkeypatch
) -> None:
    atlas = load_atlas_config(REPO_ROOT / "atlas" / f"{edition}.yaml")
    style = load_style_config(REPO_ROOT / "styles" / f"{edition}.yaml")
    rendered_text: list[str] = []
    paragraphs: list[str] = []
    paragraph_widths: list[float] = []
    paragraph_starts: list[float] = []
    paragraph_ends: list[float] = []
    draw_paragraph = front_matter._paragraph

    def record_paragraph(_cr, value, x, y, width, family, **kwargs):
        paragraphs.append(value)
        paragraph_widths.append(width)
        paragraph_starts.append(y)
        end_y = draw_paragraph(_cr, value, x, y, width, family, **kwargs)
        paragraph_ends.append(end_y)
        return end_y

    monkeypatch.setattr(
        front_matter,
        "_text",
        lambda _cr, value, *_a, **_k: rendered_text.append(value),
    )
    monkeypatch.setattr(front_matter, "_paragraph", record_paragraph)
    surface = cairo.RecordingSurface(cairo.CONTENT_COLOR_ALPHA, None)
    draw_introduction(cairo.Context(surface), atlas, style)
    text = " ".join(rendered_text)

    assert "NightSky Atlas" in text
    assert f"Public Alpha · v{__version__}" in text
    assert any("Some label overlaps remain" in value for value in paragraphs)
    assert paragraphs[:3] == [
        "NightSky Atlas is a freely available, printable star atlas designed for visual observing.",
        "The atlas PDFs can be downloaded and printed free of charge. The software used to "
        "generate them is open source, allowing anyone to customize the charts or create their "
        "own atlas editions.",
        "Three editions offer different levels of detail, while sharing the same cartographic "
        "conventions and A4 page format.",
    ]
    assert "amateur astronomer" not in text
    assert paragraph_widths[:3] == [154.0, 154.0, 154.0]
    assert paragraph_starts[1] - paragraph_ends[0] == pytest.approx(
        paragraph_starts[2] - paragraph_ends[1]
    )
    assert paragraphs[3] == (
        "Pocket provides a wide-field overview of the sky, suitable for general orientation, "
        "binoculars and small telescopes. It includes all Messier and Herschel 400 objects, "
        "along with many additional deep-sky targets. Its broad coverage also makes it useful "
        "with larger telescopes, particularly for locating objects and exploring wider regions "
        "of the sky."
    )
    assert paragraphs[4] == (
        "Standard offers twice the map scale of Pocket, with more stars and a richer selection "
        "of deep-sky objects. It is intended as a general-purpose observing atlas, particularly "
        "well suited to medium-sized telescopes. The additional detail makes it easier to "
        "navigate smaller star patterns and locate fainter targets."
    )
    assert paragraphs[5] == (
        "Deep provides the highest level of detail, with denser star fields and a more extensive "
        "deep-sky catalogue. It is intended for detailed exploration of smaller sky regions, "
        "especially when observing faint or challenging objects with larger telescopes."
    )
    assert "Pocket gives the wider view" not in text
    assert layout_fact in paragraphs[-2]
    assert "The northern and southern overview maps" in paragraphs[-2]
    assert "their own scales and stellar magnitude limits" in paragraphs[-2]
    assert "Print at 100% (actual size)" in paragraphs[-1]


@pytest.mark.parametrize("edition", ("pocket", "standard", "deep"))
def test_introduction_is_deterministic_and_within_page(edition: str) -> None:
    atlas = load_atlas_config(REPO_ROOT / "atlas" / f"{edition}.yaml")
    style = load_style_config(REPO_ROOT / "styles" / f"{edition}.yaml")
    page = atlas.page.to_geometry()
    extents = []
    for _ in range(2):
        surface = cairo.RecordingSurface(cairo.CONTENT_COLOR_ALPHA, None)
        draw_introduction(cairo.Context(surface), atlas, style)
        extents.append(surface.ink_extents())

    assert extents[0] == extents[1]
    x, y, width, height = extents[0]
    left = page.margin_mm * 72.0 / 25.4
    right = (page.width_mm - page.margin_mm) * 72.0 / 25.4
    top = page.margin_mm * 72.0 / 25.4
    bottom = (page.height_mm - page.margin_mm) * 72.0 / 25.4
    assert x >= left - 1.0
    assert y >= top - 1.0
    assert x + width <= right + 1.0
    assert y + height <= bottom + 1.0


def test_field_guide_double_star_example_uses_production_renderer(monkeypatch) -> None:
    atlas = load_atlas_config(REPO_ROOT / "atlas" / "standard.yaml")
    style = load_style_config(REPO_ROOT / "styles" / "standard.yaml")
    calls = []
    star_disks = []
    text = []

    def record_mark(_cr, mark, _model):
        calls.append(mark)

    def record_disk(_cr, x, y, diameter):
        star_disks.append((x, y, diameter))

    def record_text(_cr, value, *_args, **_kwargs):
        text.append(value)

    monkeypatch.setattr(front_matter, "_draw_double_star_mark", record_mark)
    monkeypatch.setattr(front_matter, "draw_star_disk", record_disk)
    monkeypatch.setattr(front_matter, "_text", record_text)
    surface = cairo.RecordingSurface(cairo.CONTENT_COLOR_ALPHA, None)
    cr = cairo.Context(surface)

    draw_field_guide(cr, atlas, style, chart_count=5, mm_per_degree=10.0)

    assert len(calls) == 1
    assert calls[0].system_id == "legend:unresolved"
    assert calls[0].marker_length_mm > 0.0
    assert calls[0].marker_length_mm == pytest.approx(
        max(
            style.double_stars.min_marker_length_mm,
            style.double_stars.marker_length_factor
            * front_matter.StarSizeModel.from_style(style.star).diameter_mm(6.0),
        )
    )
    magnitudes = compact_star_reference_magnitudes(atlas.stellar_limit_magnitude)
    star_model = front_matter.StarSizeModel.from_style(style.star)
    expected_scale_diameters = tuple(star_model.diameter_mm(value) for value in magnitudes)
    rendered_diameters = tuple(item[2] for item in star_disks)
    assert all(value in rendered_diameters for value in expected_scale_diameters)
    assert len(star_disks) == len(magnitudes) + 3
    first_component, second_component = star_disks[-2:]
    component_separation = second_component[0] - first_component[0]
    component_radii = (first_component[2] + second_component[2]) / 2.0
    assert component_separation + 1e-9 >= component_radii + 0.35
    assert "unresolved" in text
    assert "resolved" in text
    assert any(
        value.startswith("Contours estimate visual difficulty") for value in text
    )
    assert all(word in text for word in ("easy", "moderate", "difficult", "threshold"))
    assert not any("extreme" in value.lower() for value in text)
    assert not any("Reference model:" in value for value in text)


def test_field_guide_contains_edition_content_and_pn_ranges(monkeypatch) -> None:
    atlas = load_atlas_config(REPO_ROOT / "atlas" / "standard.yaml")
    style = load_style_config(REPO_ROOT / "styles" / "standard.yaml")
    drawn_text: list[str] = []
    centered_text: list[str] = []
    monkeypatch.setattr(
        front_matter,
        "_text",
        lambda _cr, value, *_args, **_kwargs: drawn_text.append(value),
    )
    monkeypatch.setattr(
        front_matter,
        "draw_centered_text",
        lambda _cr, value, *_args, **_kwargs: centered_text.append(value),
    )

    surface = cairo.RecordingSurface(cairo.CONTENT_COLOR_ALPHA, None)
    draw_field_guide(cairo.Context(surface), atlas, style, chart_count=129, mm_per_degree=10.0)

    assert all(
        heading in drawn_text
        for heading in (
            "STARS",
            "DOUBLE STARS",
            "CONSTELLATIONS",
            "MAP LINES",
            "DEEP-SKY OBJECTS",
            "OBJECT LABELS",
            "GALAXY VISIBILITY",
            "TELRAD REFERENCE",
        )
    )
    assert {
        "Galaxy",
        "Globular cluster",
        "Open cluster",
        "Planetary nebula",
        "Bright nebula",
        "Reflection nebula",
        "Supernova remnant",
        "Dark nebula",
        "Galaxy cluster",
        "Other / unknown",
    } <= set(drawn_text)
    assert all(value in centered_text for value in (
        "≥10′",
        "2.5–<10′",
        "1–<2.5′",
        "<1′",
    ))


def test_double_star_primitives_discard_stale_paths_without_connector_artifacts() -> None:
    from nightsky_atlas.render.cairo import _draw_double_star_mark, draw_star_disk
    from nightsky_atlas.render.double_stars import DoubleStarMark
    from nightsky_atlas.units import mm_to_pt

    style = load_style_config(REPO_ROOT / "styles" / "standard.yaml")
    size_model = front_matter.StarSizeModel.from_style(style.star)
    surface = cairo.RecordingSurface(cairo.CONTENT_COLOR_ALPHA, None)
    cr = cairo.Context(surface)
    cr.move_to(mm_to_pt(2.0), mm_to_pt(2.0))
    cr.line_to(mm_to_pt(12.0), mm_to_pt(12.0))
    draw_star_disk(cr, 50.0, 50.0, size_model.diameter_mm(6.0))
    mark = DoubleStarMark(
        system_id="legend:test",
        page_point=PagePoint(70.0, 50.0),
        magnitude=6.0,
        suppress_star_ids=frozenset(("a", "b")),
        marker_length_mm=1.0,
        marker_line_width_mm=0.15,
    )
    cr.move_to(mm_to_pt(2.0), mm_to_pt(2.0))
    cr.line_to(mm_to_pt(12.0), mm_to_pt(12.0))
    _draw_double_star_mark(cr, mark, size_model)

    x, y, _width, _height = surface.ink_extents()
    assert x > mm_to_pt(45.0)
    assert y > mm_to_pt(45.0)


@pytest.mark.parametrize("edition", ("pocket", "standard", "deep"))
@pytest.mark.parametrize("color", (False, True))
def test_field_guide_is_deterministic_and_paints_within_page(edition: str, color: bool) -> None:
    atlas = load_atlas_config(REPO_ROOT / "atlas" / f"{edition}.yaml")
    style_dir = REPO_ROOT / "styles" / "color" if color else REPO_ROOT / "styles"
    style = load_style_config(style_dir / f"{edition}.yaml")
    scale = _configured_mm_per_degree(edition)
    page = atlas.page.to_geometry()
    records = []
    for _ in range(2):
        surface = cairo.RecordingSurface(cairo.CONTENT_COLOR_ALPHA, None)
        cr = cairo.Context(surface)
        draw_field_guide(cr, atlas, style, chart_count=5, mm_per_degree=scale)
        records.append(surface.ink_extents())

    assert records[0] == records[1]
    x, y, width, height = records[0]
    assert x >= page.margin_mm * 72.0 / 25.4 - 1.0
    assert y >= page.margin_mm * 72.0 / 25.4 - 1.0
    assert x + width <= (page.width_mm - page.margin_mm) * 72.0 / 25.4 + 1.0
    assert y + height <= (page.height_mm - page.margin_mm) * 72.0 / 25.4 + 1.0


@pytest.mark.parametrize("edition", ("pocket", "standard", "deep"))
@pytest.mark.parametrize("color", (False, True))
def test_field_guide_renders_dso_palette_only_in_color_editions(
    edition: str, color: bool,
) -> None:
    atlas = load_atlas_config(REPO_ROOT / "atlas" / f"{edition}.yaml")
    style_dir = REPO_ROOT / "styles" / "color" if color else REPO_ROOT / "styles"
    style = load_style_config(style_dir / f"{edition}.yaml")
    page = atlas.page.to_geometry()
    surface = cairo.ImageSurface(
        cairo.FORMAT_ARGB32,
        round(page.width_mm * 144.0 / 25.4),
        round(page.height_mm * 144.0 / 25.4),
    )
    cr = cairo.Context(surface)
    options = cairo.FontOptions()
    options.set_antialias(cairo.ANTIALIAS_GRAY)
    cr.set_font_options(options)
    cr.set_source_rgb(1.0, 1.0, 1.0)
    cr.paint()
    cr.scale(2.0, 2.0)
    draw_field_guide(
        cr, atlas, style, chart_count=39, mm_per_degree=_configured_mm_per_degree(edition),
    )
    surface.flush()
    colors = {value & 0xFFFFFF for value in surface.get_data().cast("I")}
    assert 0 in colors
    if style.color_atlas is None:
        assert all(value >> 16 == (value >> 8) & 255 == value & 255 for value in colors)
    else:
        palette = style.color_atlas.dso
        for value in (
            palette.galaxies, palette.clusters, palette.planetary_nebulae,
            palette.bright_nebulae, palette.reflection_nebulae, palette.dark_nebulae,
            palette.supernova_remnants,
        ):
            assert int(value[1:], 16) in colors, f"Missing legend fill: {value}"
