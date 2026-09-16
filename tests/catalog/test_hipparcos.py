"""Tests for the Hipparcos bright-star importer."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from nightsky_atlas.catalog.hipparcos import (
    CATALOGUE,
    VERSION,
    iter_hipparcos_stars,
    parse_hipparcos_record,
    raw_path,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "data" / "fixtures" / "hipparcos" / "sample.dat"


def records() -> dict[str, str]:
    lines = FIXTURE.read_text(encoding="ascii").splitlines()
    return {line[8:14].strip().lstrip("0"): line for line in lines if line.strip()}


def test_parse_deneb() -> None:
    star = parse_hipparcos_record(records()["102098"])
    assert star is not None
    assert star.id == "HIP 102098"
    assert star.provenance.catalogue == CATALOGUE
    assert star.provenance.source_id == "102098"
    assert star.provenance.version == VERSION
    assert star.magnitude == pytest.approx(1.25)


def test_position_is_propagated_to_j2000() -> None:
    line = records()["102098"]
    star = parse_hipparcos_record(line)
    assert star is not None
    ra_j1991 = float(line[51:63])
    dec_j1991 = float(line[64:76])
    pm_ra = float(line[87:95])
    pm_dec = float(line[96:104])
    # Proper motion moves the star northward, so J2000 declination is larger.
    assert star.dec_deg > dec_j1991
    dec_j2000 = dec_j1991 + pm_dec * 8.75 / 3_600_000.0
    assert star.dec_deg == pytest.approx(dec_j2000)
    expected_ra = ra_j1991 + pm_ra * 8.75 / (
        3_600_000.0 * math.cos(math.radians(dec_j2000))
    )
    assert star.ra_deg == pytest.approx(expected_ra)
    assert star.ra_deg == pytest.approx(310.357978, abs=1e-5)


def test_missing_position_is_skipped() -> None:
    line = records()["102098"]
    blanked = line[:51] + " " * 12 + line[63:64] + " " * 12 + line[76:]
    assert parse_hipparcos_record(blanked) is None


def test_missing_vmag_falls_back_to_hpmag() -> None:
    line = records()["102098"]
    blanked = line[:41] + " " * 5 + line[46:]
    star = parse_hipparcos_record(blanked)
    assert star is not None
    assert star.magnitude == pytest.approx(float(line[274:281]))


def test_iterates_committed_fixture() -> None:
    stars = list(iter_hipparcos_stars(FIXTURE))
    assert len(stars) == 6
    assert {star.id for star in stars} >= {"HIP 102098", "HIP 91262", "HIP 97649"}


def test_raw_path_is_deterministic() -> None:
    assert raw_path("data/raw/hipparcos").name == "hip_main.dat"
