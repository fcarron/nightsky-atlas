from pathlib import Path

import cairo
import pytest

from nightsky_atlas.atlas.config import load_atlas_config, load_style_config
from nightsky_atlas.atlas.tiling import chart_definitions
from nightsky_atlas.chart.page import PagePoint, PageTransform
from nightsky_atlas.render import front_matter
from nightsky_atlas.render.front_matter import (
    draw_field_guide,
    dso_size_legend_text,
    galaxy_visibility_examples,
    legend_symbols,
    telrad_ring_diameters_mm,
)
from nightsky_atlas.render.symbols import compact_star_reference_magnitudes

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

    assert len(symbols) == 8
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
    if edition == "deep":
        assert symbols["Bright nebula / SNR"].minimum_extent is None
        assert symbols["Dark nebula"].minimum_extent is None
    else:
        assert symbols["Bright nebula / SNR"].minimum_extent is not None
        assert symbols["Dark nebula"].minimum_extent is not None
    assert symbols["Galaxy cluster"].minimum_extent is not None
    assert symbols["Planetary nebula"].extent.width_mm > mm_per_degree * 6.0 / 60.0
    assert symbols["Other / unknown"].angular_size_arcmin is None
    assert symbols["Other / unknown"].minimum_extent is None


@pytest.mark.parametrize("edition", ("pocket", "standard", "deep"))
def test_dso_legend_marks_large_example_to_scale_and_subminimum_sample(edition: str) -> None:
    style = load_style_config(REPO_ROOT / "styles" / f"{edition}.yaml")
    note = dso_size_legend_text(style)

    assert "First mark: to scale" in note
    assert "second: <" in note
    assert "drawn at" in note
    assert "Other: fixed" in note


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


@pytest.mark.parametrize(
    ("edition", "minimum"), (("pocket", "20′"), ("standard", "10′"), ("deep", "5′"))
)
def test_dso_size_legend_explains_edition_minimum(edition: str, minimum: str) -> None:
    style = load_style_config(REPO_ROOT / "styles" / f"{edition}.yaml")
    note = dso_size_legend_text(style)
    assert f"second: <{minimum}" in note
    assert f"drawn at {minimum} minimum" in note
    assert "Print floors may exceed it" in note
    assert "galaxy limit is major axis" in note


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
    assert "Stronger contour = easier integrated-light visibility" in text
    assert all(word in text for word in ("easy", "moderate", "difficult", "threshold"))
    assert not any("extreme" in value.lower() for value in text)
    assert any(value.startswith("Reference model: 100 / 200 / 400 mm apertures") for value in text)


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
def test_field_guide_is_deterministic_and_paints_within_page(edition: str) -> None:
    atlas = load_atlas_config(REPO_ROOT / "atlas" / f"{edition}.yaml")
    style = load_style_config(REPO_ROOT / "styles" / f"{edition}.yaml")
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
