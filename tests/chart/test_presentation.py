"""Tests for centralised visible chart naming."""

from __future__ import annotations

import pytest

from nightsky_atlas.chart.models import ChartDefinition
from nightsky_atlas.chart.presentation import (
    PRODUCT_NAME,
    chart_index,
    constellation_context,
    neighbour_code,
    presentation_for,
)


def make_definition(chart_id: str, atlas_id: str = "standard") -> ChartDefinition:
    return ChartDefinition(
        id=chart_id,
        center_ra_deg=0.0,
        center_dec_deg=0.0,
        width_deg=27.0,
        height_deg=18.5,
        atlas_id=atlas_id,
    )


def test_chart_index_parses_tiled_ids() -> None:
    assert chart_index("standard-068") == 68
    assert chart_index("deep-142") == 142
    assert chart_index("standard-001") == 1


def test_chart_index_missing_for_manual_ids() -> None:
    assert chart_index("test-virgo") is None
    assert chart_index("pole") is None
    assert chart_index("standard-x") is None


def test_visible_chart_code_uses_edition_code() -> None:
    presentation = presentation_for(make_definition("standard-068"))
    assert presentation.chart_code == "S068"
    assert presentation.title == f"{PRODUCT_NAME} \N{MIDDLE DOT} S068"


def test_chart_header_includes_compact_constellation_context() -> None:
    presentation = presentation_for(
        make_definition("standard-042"),
        constellation_area_fractions={"Cyg": 0.65, "Cep": 0.20, "Lac": 0.15},
    )
    assert presentation.chart_code == "S042"
    assert presentation.chart_header_code == "Cyg \N{MIDDLE DOT} S042"
    assert presentation.title == "NightSky Atlas · Cyg · S042"


def test_constellation_context_uses_two_names_only_for_shared_fields() -> None:
    assert constellation_context({"Cyg": 0.48, "Cep": 0.44, "Lac": 0.08}) == "Cyg/Cep"


def test_constellation_context_requires_both_shared_field_thresholds() -> None:
    assert constellation_context({"Vir": 0.55, "Com": 0.30, "Leo": 0.15}) == "Vir"
    assert constellation_context({"Cyg": 0.60, "Cep": 0.39, "Lac": 0.01}) == "Cyg"
    assert constellation_context({"Cyg": 0.50, "Cep": 0.29, "Lac": 0.21}) == "Cyg"


def test_constellation_context_is_area_ordered_and_never_shows_more_than_two() -> None:
    assert constellation_context({"Vir": 0.32, "Com": 0.40, "Leo": 0.28}) == "Com/Vir"
    result = constellation_context({"Ari": 0.34, "Tau": 0.32, "Per": 0.31})
    assert result == "Ari/Tau"
    assert result.count("/") == 1


def test_constellation_context_without_visible_regions_is_absent() -> None:
    assert constellation_context({}) is None


def test_edition_name_and_code_override_registry() -> None:
    presentation = presentation_for(
        make_definition("deep-007", atlas_id="deep"),
        edition_name="Deep Field",
        edition_code="D",
    )
    assert presentation.chart_code == "D007"
    assert presentation.title == "NightSky Atlas · D007"


@pytest.mark.parametrize(
    ("chart_id", "atlas_id", "edition_name", "edition_code", "width", "context", "expected"),
    (
        ("pocket-17", "pocket", "Pocket", "P", 2, "Cyg", "NightSky Atlas · Cyg · P17"),
        ("standard-004", "standard", "Standard", "S", 3, "Cam", "NightSky Atlas · Cam · S004"),
        ("deep-087", "deep", "Deep", "D", 3, "Vir", "NightSky Atlas · Vir · D087"),
        (
            "eyepiece-0432",
            "eyepiece",
            "Eyepiece",
            "E",
            4,
            "And",
            "NightSky Atlas · And · E0432",
        ),
    ),
)
def test_chart_titles_keep_brand_constellation_and_code_without_edition_name(
    chart_id, atlas_id, edition_name, edition_code, width, context, expected
) -> None:
    presentation = presentation_for(
        make_definition(chart_id, atlas_id),
        edition_name=edition_name,
        edition_code=edition_code,
        chart_index_width=width,
        constellation_area_fractions={context: 1.0},
    )
    assert presentation.title == expected
    assert edition_name not in presentation.title
    assert presentation.product_name == PRODUCT_NAME


def test_boundary_chart_title_keeps_both_constellations() -> None:
    presentation = presentation_for(
        make_definition("standard-042"),
        constellation_area_fractions={"Cyg": 0.48, "Cep": 0.44, "Lac": 0.08},
    )
    assert presentation.title == "NightSky Atlas · Cyg/Cep · S042"


def test_chart_title_markup_subordinates_brand_and_emphasizes_chart_code() -> None:
    presentation = presentation_for(
        make_definition("standard-004"),
        constellation_area_fractions={"Cam": 1.0},
    )
    assert presentation.title_markup == (
        '<span size="small">NightSky Atlas</span> · Cam · <b>S004</b>'
    )


def test_manual_chart_falls_back_to_internal_id() -> None:
    presentation = presentation_for(make_definition("test-virgo"))
    assert presentation.chart_code == "test-virgo"


def test_neighbour_code_uses_short_code() -> None:
    assert neighbour_code("standard-082", "S") == "S082"
    assert neighbour_code("deep-142", "D") == "D142"
    assert neighbour_code("test-sparse", "S") == "test-sparse"
