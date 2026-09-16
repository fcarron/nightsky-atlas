"""Tests for chart geometry domain models."""

from __future__ import annotations

import pytest

from nightsky_atlas.chart.models import ChartDefinition, PageGeometry


def make_definition(**overrides: object) -> ChartDefinition:
    values: dict[str, object] = {
        "id": "standard-042",
        "center_ra_deg": 187.5,
        "center_dec_deg": 12.0,
        "width_deg": 20.0,
        "height_deg": 14.0,
    }
    values.update(overrides)
    return ChartDefinition(**values)  # type: ignore[arg-type]


def test_page_geometry_printable_area() -> None:
    page = PageGeometry(width_mm=297.0, height_mm=210.0, margin_mm=12.0)
    assert page.printable_width_mm == pytest.approx(273.0)
    assert page.printable_height_mm == pytest.approx(186.0)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"width_mm": 0.0, "height_mm": 210.0},
        {"width_mm": 297.0, "height_mm": -1.0},
        {"width_mm": 297.0, "height_mm": 210.0, "margin_mm": 0.0},
        {"width_mm": 297.0, "height_mm": 210.0, "margin_mm": 150.0},
        {"width_mm": float("nan"), "height_mm": 210.0},
    ],
)
def test_page_geometry_rejects_invalid_dimensions(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        PageGeometry(**kwargs)


def test_page_geometry_serialization_round_trip() -> None:
    page = PageGeometry(width_mm=297.0, height_mm=210.0, margin_mm=12.0)
    assert PageGeometry.from_dict(page.to_dict()) == page


def test_definition_defaults_and_repr() -> None:
    definition = make_definition()
    assert definition.projection == "stereographic"
    assert definition.rotation_deg == 0.0
    assert definition.atlas_id == "standard"
    assert "standard-042" in repr(definition)


@pytest.mark.parametrize(
    "overrides",
    [
        {"id": "   "},
        {"atlas_id": ""},
        {"center_dec_deg": 90.1},
        {"center_dec_deg": -90.1},
        {"width_deg": 0.0},
        {"height_deg": -5.0},
        {"center_ra_deg": float("nan")},
        {"rotation_deg": float("inf")},
        {"projection": "  "},
    ],
)
def test_definition_rejects_invalid_values(overrides: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        make_definition(**overrides)


def test_definition_serialization_round_trip() -> None:
    definition = make_definition()
    assert ChartDefinition.from_dict(definition.to_dict()) == definition


def test_neighbours_serialization_round_trip() -> None:
    definition = make_definition(neighbours=(("N", "test-sparse"), ("E", "test-other")))
    assert definition.neighbours == (("N", "test-sparse"), ("E", "test-other"))
    assert ChartDefinition.from_dict(definition.to_dict()) == definition


def test_definition_is_immutable() -> None:
    definition = make_definition()
    with pytest.raises((AttributeError, TypeError)):
        definition.width_deg = 30.0  # type: ignore[misc]
