"""Tests for the processed deep-sky catalogue store."""

from __future__ import annotations

from pathlib import Path

import pytest

from nightsky_atlas.catalog.dso_store import load_dso_catalog, write_dso_catalog
from nightsky_atlas.catalog.models import DeepSkyObject, DsoType, Provenance


def make_dso(object_id: str, magnitude: float | None = 8.0) -> DeepSkyObject:
    return DeepSkyObject(
        id=object_id,
        ra_deg=187.7,
        dec_deg=12.4,
        object_type=DsoType.GALAXY,
        provenance=Provenance(catalogue="OpenNGC", source_id=object_id),
        magnitude=magnitude,
        magnitude_band="V",
        major_axis_arcmin=8.0,
        minor_axis_arcmin=4.0,
        position_angle_deg=35.0,
        common_name="Test",
        constellation="Vir",
        cross_ids=("M87",),
    )


def test_round_trip(tmp_path: Path) -> None:
    objects = [make_dso("NGC4486"), make_dso("NGC4472")]
    path = tmp_path / "openngc.json"
    count = write_dso_catalog(path, objects)
    assert count == 2
    loaded = load_dso_catalog(path)
    assert loaded == objects


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_dso_catalog(tmp_path / "missing.json")


def test_missing_magnitude_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "openngc.json"
    write_dso_catalog(path, [make_dso("X", magnitude=None)])
    loaded = load_dso_catalog(path)
    assert loaded[0].magnitude is None
    assert loaded[0].cross_ids == ("M87",)
