"""Tests for normalized catalogue models."""

from __future__ import annotations

import pytest

from nightsky_atlas.catalog.models import (
    DeepSkyObject,
    DsoType,
    Provenance,
    Star,
)


def make_provenance(**overrides: object) -> Provenance:
    values: dict[str, object] = {"catalogue": "FIXTURE", "source_id": "F-001"}
    values.update(overrides)
    return Provenance(**values)  # type: ignore[arg-type]


def make_star(**overrides: object) -> Star:
    values: dict[str, object] = {
        "id": "star-001",
        "ra_deg": 187.5,
        "dec_deg": 12.0,
        "magnitude": 3.5,
        "provenance": make_provenance(),
    }
    values.update(overrides)
    return Star(**values)  # type: ignore[arg-type]


def test_valid_star_defaults() -> None:
    star = make_star()
    assert star.epoch == "J2000"
    assert star.provenance.catalogue == "FIXTURE"


@pytest.mark.parametrize(
    "overrides",
    [
        {"id": "  "},
        {"dec_deg": 90.5},
        {"dec_deg": -90.5},
        {"ra_deg": float("nan")},
        {"magnitude": float("inf")},
        {"epoch": ""},
        {"provenance": "FIXTURE:F-001"},
    ],
)
def test_invalid_star_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        make_star(**overrides)


@pytest.mark.parametrize("overrides", [{"catalogue": ""}, {"source_id": "  "}])
def test_invalid_provenance_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        make_provenance(**overrides)


def test_star_serialization_round_trip() -> None:
    star = make_star()
    assert Star.from_dict(star.to_dict()) == star


def test_provenance_serialization_round_trip() -> None:
    provenance = make_provenance(version="test-1")
    assert Provenance.from_dict(provenance.to_dict()) == provenance


def make_dso(**overrides: object) -> DeepSkyObject:
    values: dict[str, object] = {
        "id": "NGC0001",
        "ra_deg": 10.0,
        "dec_deg": 20.0,
        "object_type": DsoType.GALAXY,
        "provenance": make_provenance(),
        "magnitude": 10.0,
        "major_axis_arcmin": 2.0,
        "minor_axis_arcmin": 1.0,
    }
    values.update(overrides)
    return DeepSkyObject(**values)  # type: ignore[arg-type]


def test_surface_brightness_derived_from_magnitude_and_axes() -> None:
    # 2 x 1 arcmin ellipse: area ~ 1.5708 arcmin^2 = 5654 arcsec^2
    brightness = make_dso().surface_brightness_mag_arcsec2()
    assert brightness == pytest.approx(10.0 + 2.5 * 3.7524, abs=1e-3)


@pytest.mark.parametrize(
    "overrides",
    [
        {"magnitude": None},
        {"minor_axis_arcmin": None},
        {"major_axis_arcmin": None},
    ],
)
def test_surface_brightness_requires_magnitude_and_axes(
    overrides: dict[str, object],
) -> None:
    assert make_dso(**overrides).surface_brightness_mag_arcsec2() is None


def test_dso_serialization_round_trip() -> None:
    dso = make_dso()
    assert DeepSkyObject.from_dict(dso.to_dict()) == dso
