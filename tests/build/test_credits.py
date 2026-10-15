from __future__ import annotations

import cairo
import pytest

from nightsky_atlas.build.atlas import _credits_columns
from nightsky_atlas.chart.models import PageGeometry
from nightsky_atlas.render.fonts import register_bundled_fonts
from nightsky_atlas.render.front_matter import draw_credits_page


def test_credits_show_only_catalogue_families_used_by_this_build() -> None:
    sources = [
        {
            "kind": "stars",
            "manifest": {
                "catalogue": "TYC2",
                "bright_star_supplement": {"catalogue": "HIP"},
            },
        },
        {
            "kind": "deep_sky",
            "manifest": {
                "catalogue": "NightSkyAtlas merged DSO catalogue",
                "acknowledgement": "VizieR acknowledgement",
                "sources": [
                    {"catalogue_id": "VII/20", "name": "Sharpless"},
                    {"catalogue_id": "VII/9", "name": "Lynds LBN"},
                    {"catalogue_id": "VII/213", "name": "Hickson"},
                    {"catalogue_id": "VII/74A", "name": "Arp"},
                ],
            },
        },
    ]
    left, right = _credits_columns(
        data_sources=sources,
        geometry_catalogues={
            "constellation_lines": ["Stellarium Western (Sky & Telescope)"],
            "constellation_boundaries": ["d3-celestial"],
            "outlines": ["nightsky-atlas-authored"],
            "milky_way": [],
        },
        used_dso_catalogues=frozenset({"OpenNGC", "VII/20", "VII/213"}),
        star_name_source="data/fixtures/starnames",
        has_iau_star_names=True,
        has_galaxies=True,
    )
    left_text = " ".join(entry for _, entries in left for entry in entries)
    right_text = " ".join(entry for _, entries in right for entry in entries)

    assert "Tycho-2" in left_text and "Hipparcos" in left_text
    assert "OpenNGC" in left_text and "Sharpless" in left_text
    assert "Hickson" in left_text
    assert "Herschel 400" in left_text and "CC BY-SA 4.0" in left_text
    assert "Lynds LBN" not in left_text
    assert "Arp" not in left_text
    assert "VizieR" in right_text
    assert "Milky Way" not in right_text
    assert "IAU Catalog of Star Names" in right_text


def test_optional_sources_appear_only_when_the_build_uses_them() -> None:
    left, right = _credits_columns(
        data_sources=[
            {
                "kind": "faint_stars",
                "manifest": {"catalogue": "UCAC4"},
            },
            {
                "kind": "double_stars",
                "manifest": {"catalogue": "WDS"},
            },
        ],
        geometry_catalogues={
            "constellation_lines": [],
            "constellation_boundaries": [],
            "outlines": [],
            "milky_way": ["d3-celestial"],
        },
        used_dso_catalogues=frozenset(),
        star_name_source=None,
        has_iau_star_names=False,
        has_galaxies=False,
    )
    left_text = " ".join(entry for _, entries in left for entry in entries)
    right_text = " ".join(entry for _, entries in right for entry in entries)

    assert "UCAC4" in left_text and "APASS V" in left_text
    assert "Washington Double Star Catalog" in left_text
    assert "VizieR" not in right_text
    assert "José R. Vieira" in right_text


def test_credits_state_source_specific_licences_and_attributions() -> None:
    left, right = _credits_columns(
        data_sources=[
            {
                "kind": "stars",
                "manifest": {
                    "catalogue": "TYC2",
                    "bright_star_supplement": {"catalogue": "HIP"},
                },
            },
            {"kind": "faint_stars", "manifest": {"catalogue": "UCAC4"}},
            {
                "kind": "deep_sky",
                "manifest": {
                    "sources": [
                        {"catalogue_id": "UCC", "name": "Unified Cluster Catalogue"}
                    ]
                },
            },
        ],
        geometry_catalogues={
            "constellation_lines": ["Stellarium Western (Sky & Telescope)"],
            "constellation_boundaries": ["d3-celestial"],
            "outlines": ["nightsky-atlas-authored"],
            "milky_way": ["d3-celestial"],
            "magellanic_clouds": ["Gaia DR3"],
        },
        used_dso_catalogues=frozenset({"OpenNGC", "UCC"}),
        star_name_source="data/fixtures/starnames",
        has_iau_star_names=True,
        has_galaxies=False,
    )
    left_text = " ".join(entry for _, entries in left for entry in entries)
    right_text = " ".join(entry for _, entries in right for entry in entries)

    assert "CC BY-NC 3.0 IGO" in left_text
    assert "CC BY-SA 4.0" in left_text and "adapted" in left_text
    assert "terms not specified" in left_text
    assert "Perren et al. (2023)" in left_text
    assert "CC BY-SA 2.0" in right_text
    assert "BSD-3-Clause" in right_text
    assert "José R. Vieira" in right_text and "Olaf Frohn" in right_text
    assert "Gaia DR3 density and G-flux" in right_text
    assert "ODbL 1.0" in right_text and "hips2fits" in right_text


def test_credits_reject_a_long_source_list_before_it_overlaps_licence() -> None:
    register_bundled_fonts()
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1200, 850)
    context = cairo.Context(surface)
    sections = (
        (
            "Deep-sky catalogues",
            tuple(
                f"Catalogue {number}: author group, catalogue table and source "
                "metadata retained in the NightSky Atlas build manifest."
                for number in range(1, 28)
            ),
        ),
    )

    with pytest.raises(ValueError, match="credits text exceeds"):
        draw_credits_page(
            context,
            PageGeometry(width_mm=297.0, height_mm=210.0, margin_mm=12.0),
            "Source Sans 3",
            sections,
            sections,
        )


def test_credits_page_project_metadata_and_licences_stay_inside_printable_area() -> None:
    register_bundled_fonts()
    page = PageGeometry(width_mm=297.0, height_mm=210.0, margin_mm=12.0)
    sections = (
        (
            "Stars and double stars",
            (
                "Tycho-2 — Høg et al. (2000), ESA",
                "Hipparcos — ESA (1997)",
                "Washington Double Star Catalog — Mason et al., U.S. Naval Observatory",
            ),
        ),
        (
            "Deep-sky catalogues",
            (
                "OpenNGC — Mattia Verga and contributors",
                "Sharpless; Lynds; Barnard; van den Bergh; Collinder; Melotte; Kohoutek; "
                "Palomar; Terzan; Hickson; Arp; de Vaucouleurs",
            ),
        ),
    )
    surface = cairo.RecordingSurface(cairo.CONTENT_COLOR_ALPHA, None)
    draw_credits_page(
        cairo.Context(surface),
        page,
        "Source Sans 3",
        sections,
        (("Constellations and cartography", ("IAU boundaries via d3-celestial",)),),
        edition="Standard",
        catalogue_data_label="source-specific dates in build manifest",
    )
    x, y, width, height = surface.ink_extents()
    margin = page.margin_mm * 72.0 / 25.4
    page_width = page.width_mm * 72.0 / 25.4
    page_height = page.height_mm * 72.0 / 25.4

    assert x >= margin - 1.0
    assert y >= margin - 1.0
    assert x + width <= page_width - margin + 1.0
    assert y + height <= page_height - margin + 1.0
