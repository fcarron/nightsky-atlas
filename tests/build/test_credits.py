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
