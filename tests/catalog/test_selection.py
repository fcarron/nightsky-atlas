"""Tests for deep-sky selection metadata and priorities."""

from __future__ import annotations

from pathlib import Path

import pytest

from nightsky_atlas.catalog.dso_store import load_dso_catalog
from nightsky_atlas.catalog.models import DeepSkyObject, DsoType, Provenance
from nightsky_atlas.catalog.observing_lists import (
    build_membership_index,
    dso_memberships,
    load_observing_lists,
)
from nightsky_atlas.catalog.priority import HERSCHEL_PRIORITY
from nightsky_atlas.catalog.selection import (
    SelectionPolicy,
    base_label_priority,
    select_dso,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "data" / "fixtures" / "observing_lists"
OPENNGC = REPO_ROOT / "data" / "processed" / "dso" / "openngc.json"

FORCED = SelectionPolicy(forced_lists=frozenset({"herschel400"}))


def make_dso(
    object_id: str,
    *,
    magnitude: float | None = 12.0,
    cross_ids: tuple[str, ...] = (),
    common_name: str | None = None,
) -> DeepSkyObject:
    return DeepSkyObject(
        id=object_id,
        ra_deg=187.5,
        dec_deg=12.0,
        object_type=DsoType.GALAXY,
        provenance=Provenance(catalogue="TEST", source_id=object_id),
        magnitude=magnitude,
        cross_ids=cross_ids,
        common_name=common_name,
    )


def test_base_label_priority_unchanged() -> None:
    assert base_label_priority(make_dso("NGC4486", cross_ids=("M87",))) == (100, True)
    assert base_label_priority(make_dso("X", common_name="Named")) == (90, True)
    assert base_label_priority(make_dso("Y", magnitude=8.0)) == (60, False)
    assert base_label_priority(make_dso("Z", magnitude=13.0)) == (30, False)


def test_select_dso_without_policy_is_catalogue_only() -> None:
    metadata = select_dso(make_dso("NGC4486", cross_ids=("M87",)))
    assert metadata.forced is False
    assert metadata.list_memberships == frozenset()
    assert metadata.label_priority == 100
    assert metadata.label_mandatory is True


def test_select_dso_forced_membership() -> None:
    index = build_membership_index(load_observing_lists(FIXTURE_DIR))
    metadata = select_dso(
        make_dso("NGC0869", magnitude=14.0), index=index, policy=FORCED
    )
    assert metadata.forced is True
    assert metadata.list_memberships == {"herschel400", "caldwell"}
    assert metadata.label_mandatory is True


def test_messier_membership_is_mandatory_even_without_m_alias() -> None:
    dso = make_dso("NGC1234")
    metadata = select_dso(
        dso,
        index={"NGC1234": frozenset({"messier"})},
        policy=SelectionPolicy(forced_lists=frozenset({"messier"})),
    )
    assert metadata.label_mandatory is True
    assert metadata.render_priority == FORCED.forced_render_priority
    assert metadata.label_priority >= HERSCHEL_PRIORITY


def test_select_dso_membership_bonus_without_force() -> None:
    index = build_membership_index(load_observing_lists(FIXTURE_DIR))
    policy = SelectionPolicy(list_weights=(("herschel400", 50),))
    metadata = select_dso(
        make_dso("NGC0869", magnitude=13.0), index=index, policy=policy
    )
    assert metadata.forced is False
    assert metadata.render_priority == policy.render_base_priority + 50
    assert metadata.label_priority == 30 + 50
    assert metadata.label_mandatory is True


def test_every_herschel400_designation_is_forced() -> None:
    observing_lists = load_observing_lists(FIXTURE_DIR)
    index = build_membership_index(observing_lists)
    aliases = dict(observing_lists["herschel400"].object_aliases)
    targets = (
        observing_lists["herschel400"].objects - aliases.keys()
    ) | set(aliases.values())
    for designation in sorted(targets):
        metadata = select_dso(make_dso(designation, magnitude=15.0), index=index, policy=FORCED)
        assert metadata.forced, designation
        assert metadata.label_mandatory, designation


@pytest.mark.skipif(not OPENNGC.exists(), reason="processed OpenNGC catalogue not built")
def test_all_resolvable_herschel400_objects_are_forced_in_openngc() -> None:
    dsos = load_dso_catalog(OPENNGC)
    index = build_membership_index(load_observing_lists(FIXTURE_DIR))
    forced = {
        dso.id for dso in dsos if select_dso(dso, index=index, policy=FORCED).forced
    }
    resolvable = {
        dso.id for dso in dsos if "herschel400" in dso_memberships(dso, index)
    }
    assert resolvable <= forced
    assert len(forced) >= 390
