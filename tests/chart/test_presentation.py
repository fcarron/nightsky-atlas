"""Tests for centralised visible chart naming."""

from __future__ import annotations

from nightsky_atlas.chart.models import ChartDefinition
from nightsky_atlas.chart.presentation import (
    PRODUCT_NAME,
    chart_index,
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
    assert presentation.title == f"{PRODUCT_NAME} \N{EM DASH} Standard \N{MIDDLE DOT} S068"


def test_edition_name_and_code_override_registry() -> None:
    presentation = presentation_for(
        make_definition("deep-007", atlas_id="deep"),
        edition_name="Deep Field",
        edition_code="D",
    )
    assert presentation.chart_code == "D007"
    assert "Deep Field" in presentation.title


def test_manual_chart_falls_back_to_internal_id() -> None:
    presentation = presentation_for(make_definition("test-virgo"))
    assert presentation.chart_code == "test-virgo"


def test_neighbour_code_uses_short_code() -> None:
    assert neighbour_code("standard-082", "S") == "S082"
    assert neighbour_code("deep-142", "D") == "D142"
    assert neighbour_code("test-sparse", "S") == "test-sparse"
