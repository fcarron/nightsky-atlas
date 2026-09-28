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
    assert {"messier", "caldwell", "herschel400"} <= set(lists)
    herschel = lists["herschel400"]
    assert herschel.name == "Herschel 400"
    assert herschel.license == "CC-BY-SA-4.0"
    assert len(herschel.objects) == 402
    assert {"NGC869", "NGC6514", "NGC7000"} <= herschel.objects
    assert herschel.raw_entry_count == 400
    assert dict(herschel.object_aliases)["NGC651"] == "NGC650"


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
    assert dso_memberships(make_dso("NGC0869"), index) == {"herschel400", "caldwell"}


def test_dso_memberships_matches_cross_id_and_plain_ngc() -> None:
    index = build_membership_index(load_observing_lists(FIXTURE_DIR))
    dso = make_dso("M76", cross_ids=("NGC 650", "Little Dumbbell"))
    assert dso_memberships(dso, index) == {"herschel400", "messier"}


def test_observing_list_aliases_and_non_dso_entries_are_kept_separate() -> None:
    lists = load_observing_lists(FIXTURE_DIR)
    index = build_membership_index(lists)
    assert dso_memberships(make_dso("NGC06882"), index) >= {"caldwell", "herschel400"}
    assert "M40" in lists["messier"].non_dso_entries
    assert "C14" not in lists["caldwell"].objects
    assert {"NGC869", "NGC884"} <= lists["caldwell"].objects


def test_canonical_list_target_does_not_leak_to_another_objects_cross_id() -> None:
    lists = load_observing_lists(FIXTURE_DIR)
    host = make_dso("NGC4656")
    companion = make_dso("NGC4656 NED01", cross_ids=("NGC4656",))
    index = build_membership_index(lists, [host, companion])
    assert "herschel400" in dso_memberships(host, index)
    assert "herschel400" not in dso_memberships(companion, index)


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
