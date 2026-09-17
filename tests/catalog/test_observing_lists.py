"""Tests for observing-list fixtures and membership matching."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nightsky_atlas.catalog.models import DeepSkyObject, DsoType, Provenance
from nightsky_atlas.catalog.observing_lists import (
    build_membership_index,
    canonical_designation,
    dso_memberships,
    load_observing_lists,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "data" / "fixtures" / "observing_lists"


def make_dso(object_id: str, *, cross_ids: tuple[str, ...] = ()) -> DeepSkyObject:
    return DeepSkyObject(
        id=object_id,
        ra_deg=187.5,
        dec_deg=12.0,
        object_type=DsoType.GALAXY,
        provenance=Provenance(catalogue="TEST", source_id=object_id),
        magnitude=12.0,
        cross_ids=cross_ids,
    )


def test_load_herschel400_fixture() -> None:
    lists = load_observing_lists(FIXTURE_DIR)
    assert set(lists) == {"herschel400"}
    herschel = lists["herschel400"]
    assert herschel.name == "Herschel 400"
    assert herschel.license == "CC-BY-SA-4.0"
    assert len(herschel.objects) == 402
    assert {"NGC869", "NGC6514", "NGC7000"} <= herschel.objects


def test_missing_and_empty_directory_yield_no_lists() -> None:
    assert load_observing_lists(FIXTURE_DIR / "does-not-exist") == {}
    assert load_observing_lists("") == {}
    assert load_observing_lists(None) == {}


def test_canonical_designation_normalizes_forms() -> None:
    assert canonical_designation("NGC 869") == "NGC869"
    assert canonical_designation("NGC0869") == "NGC869"
    assert canonical_designation("ngc 0001") == "NGC1"
    assert canonical_designation("M 42") == "M42"
    assert canonical_designation("IC 0507") == "IC507"
    assert canonical_designation("Barnard 33") == "BARNARD33"
    assert canonical_designation("   ") == ""


def test_dso_memberships_matches_zero_padded_id() -> None:
    index = build_membership_index(load_observing_lists(FIXTURE_DIR))
    assert dso_memberships(make_dso("NGC0869"), index) == {"herschel400"}


def test_dso_memberships_matches_cross_id_and_plain_ngc() -> None:
    index = build_membership_index(load_observing_lists(FIXTURE_DIR))
    dso = make_dso("M76", cross_ids=("NGC 650", "Little Dumbbell"))
    assert dso_memberships(dso, index) == {"herschel400"}


def test_dso_memberships_unknown_object_is_empty() -> None:
    index = build_membership_index(load_observing_lists(FIXTURE_DIR))
    assert dso_memberships(make_dso("IC9999"), index) == frozenset()


def test_malformed_fixture_raises(tmp_path: Path) -> None:
    (tmp_path / "bad.json").write_text(json.dumps({"id": "x"}), encoding="utf-8")
    with pytest.raises(ValueError, match="name"):
        load_observing_lists(tmp_path)


def test_fixture_without_objects_raises(tmp_path: Path) -> None:
    payload = {"id": "x", "name": "X", "objects": []}
    (tmp_path / "bad.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="no objects"):
        load_observing_lists(tmp_path)


def test_duplicate_list_id_raises(tmp_path: Path) -> None:
    payload = {"id": "dup", "name": "Dup", "objects": ["NGC1"]}
    for name in ("a.json", "b.json"):
        (tmp_path / name).write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        load_observing_lists(tmp_path)
