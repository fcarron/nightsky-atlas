"""Tests for the OpenNGC importer."""

from __future__ import annotations

from pathlib import Path

import pytest

from nightsky_atlas.catalog.models import DsoType
from nightsky_atlas.catalog.openngc import (
    CATALOGUE,
    iter_openngc_objects,
    load_sample_dsos,
    parse_openngc_row,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "data" / "fixtures" / "openngc" / "sample.csv"


def base_row(**overrides: str) -> dict[str, str]:
    row = {
        "Name": "NGC0224",
        "Type": "G",
        "RA": "00:42:44.35",
        "Dec": "+41:16:08.6",
        "Const": "And",
        "MajAx": "177.83",
        "MinAx": "69.66",
        "PosAng": "35",
        "B-Mag": "4.29",
        "V-Mag": "3.44",
        "SurfBr": "22.5",
        "Hubble": "Sb",
        "Sources": "Type:1|RA:1|Dec:1",
        "M": "031",
        "Identifiers": "2MASX J00424433+4116074, UGC 00454",
        "Common names": "Andromeda Galaxy",
    }
    row.update(overrides)
    return row


def test_parse_galaxy_row() -> None:
    obj = parse_openngc_row(base_row())
    assert obj is not None
    assert obj.id == "NGC0224"
    assert obj.object_type == DsoType.GALAXY
    assert obj.ra_deg == pytest.approx(10.6847917, abs=1e-6)
    assert obj.dec_deg == pytest.approx(41.2690556, abs=1e-6)
    assert obj.magnitude == pytest.approx(3.44)
    assert obj.magnitude_band == "V"
    assert obj.b_magnitude == pytest.approx(4.29)
    assert obj.v_magnitude == pytest.approx(3.44)
    assert obj.mean_surface_brightness_mag_arcsec2 == pytest.approx(22.5)
    assert obj.hubble_type == "Sb"
    assert obj.sources == "Type:1|RA:1|Dec:1"
    assert obj.major_axis_arcmin == pytest.approx(177.83)
    assert obj.minor_axis_arcmin == pytest.approx(69.66)
    assert obj.position_angle_deg == pytest.approx(35.0)
    assert obj.common_name == "Andromeda Galaxy"
    assert obj.constellation == "And"
    assert "M31" in obj.cross_ids
    assert obj.provenance.catalogue == CATALOGUE


def test_magnitude_falls_back_to_b_band() -> None:
    obj = parse_openngc_row(base_row(**{"V-Mag": ""}))
    assert obj is not None
    assert obj.magnitude == pytest.approx(4.29)
    assert obj.magnitude_band == "B"


def test_missing_optional_fields_are_none() -> None:
    blank = {
        "V-Mag": "",
        "B-Mag": "",
        "SurfBr": "",
        "Hubble": "",
        "Sources": "",
        "MajAx": "",
        "MinAx": "",
        "PosAng": "",
        "Common names": "",
    }
    obj = parse_openngc_row(base_row(**blank))
    assert obj is not None
    assert obj.magnitude is None
    assert obj.b_magnitude is None
    assert obj.v_magnitude is None
    assert obj.mean_surface_brightness_mag_arcsec2 is None
    assert obj.hubble_type is None
    assert obj.sources is None
    assert obj.major_axis_arcmin is None
    assert obj.minor_axis_arcmin is None
    assert obj.position_angle_deg is None
    assert obj.common_name is None


@pytest.mark.parametrize(
    ("type_code", "expected"),
    [
        ("G", DsoType.GALAXY),
        ("OCl", DsoType.OPEN_CLUSTER),
        ("GCl", DsoType.GLOBULAR_CLUSTER),
        ("PN", DsoType.PLANETARY_NEBULA),
        ("Cl+N", DsoType.BRIGHT_NEBULA),
        ("SNR", DsoType.SUPERNOVA_REMNANT),
        ("GPair", DsoType.GALAXY_CLUSTER),
        ("**", DsoType.DOUBLE_STAR),
    ],
)
def test_type_mapping(type_code: str, expected: DsoType) -> None:
    obj = parse_openngc_row(base_row(Type=type_code))
    assert obj is not None
    assert obj.object_type == expected


@pytest.mark.parametrize("type_code", ["Dup", "NonEx", ""])
def test_skipped_types(type_code: str) -> None:
    assert parse_openngc_row(base_row(Type=type_code)) is None


def test_row_without_position_is_skipped() -> None:
    assert parse_openngc_row(base_row(RA="", Dec="")) is None


def test_loads_committed_fixture() -> None:
    objects = load_sample_dsos(FIXTURE)
    assert len(objects) == 12
    by_id = {obj.id: obj for obj in objects}
    assert by_id["NGC6205"].object_type == DsoType.GLOBULAR_CLUSTER
    assert by_id["NGC6720"].object_type == DsoType.PLANETARY_NEBULA
    assert by_id["NGC1976"].object_type == DsoType.BRIGHT_NEBULA


def test_iteration_is_deterministic() -> None:
    first = [obj.id for obj in iter_openngc_objects([FIXTURE])]
    second = [obj.id for obj in iter_openngc_objects([FIXTURE])]
    assert first == second
