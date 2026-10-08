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
    TypeSelectionRule,
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


def make_open_cluster(
    object_id: str,
    *,
    magnitude: float | None,
    size: float | None,
    catalogue: str = "OpenNGC",
) -> DeepSkyObject:
    return DeepSkyObject(
        id=object_id,
        ra_deg=187.5,
        dec_deg=12.0,
        object_type=DsoType.OPEN_CLUSTER,
        provenance=Provenance(catalogue=catalogue, source_id=object_id),
        magnitude=magnitude,
        major_axis_arcmin=size,
    )


def _oc_policy(
    *,
    minimum_size: float,
    gate_magnitude: float,
    gate_size: float,
    edition: str,
    forced_lists: frozenset[str] = frozenset(),
    included_catalogues: frozenset[str] = frozenset({"OpenNGC"}),
    excluded_designations: tuple[str, ...] = (),
    automatic_designation_prefixes: tuple[str, ...] = (),
    parents: tuple[SelectionPolicy, ...] = (),
) -> SelectionPolicy:
    return SelectionPolicy(
        forced_lists=forced_lists,
        included_catalogues=included_catalogues,
        excluded_designations=excluded_designations,
        type_rules=(
            (
                DsoType.OPEN_CLUSTER.value,
                TypeSelectionRule(
                    use_visibility=False,
                    minimum_major_axis_arcmin=minimum_size,
                    magnitude_size_gate_maximum_magnitude=gate_magnitude,
                    magnitude_size_gate_minimum_major_axis_arcmin=gate_size,
                    automatic_designation_prefixes=automatic_designation_prefixes,
                ),
            ),
        ),
        edition_id=edition,
        hierarchy_policies=parents,
    )


def test_pocket_open_cluster_selection_gates_and_forced_membership() -> None:
    pocket = _oc_policy(
        minimum_size=20.0,
        gate_magnitude=9.0,
        gate_size=3.0,
        edition="pocket",
        forced_lists=frozenset({"pocket_classics"}),
    )
    cases = (
        (9.0, 3.0, True),
        (9.1, 3.0, False),
        (None, 20.0, True),
        (15.0, 20.0, True),
        (None, 19.9, False),
    )
    for index, (magnitude, size, expected) in enumerate(cases):
        result = select_dso(
            make_open_cluster(f"NGC{index + 1}", magnitude=magnitude, size=size),
            policy=pocket,
        )
        assert (result.visible or result.forced) is expected

    explicit = select_dso(
        make_open_cluster("NGC9999", magnitude=15.0, size=1.0),
        index={"NGC9999": frozenset({"pocket_classics"})},
        policy=pocket,
    )
    assert explicit.forced


def test_standard_open_cluster_gates_inherit_pocket_and_keep_source_limit() -> None:
    pocket = _oc_policy(
        minimum_size=20.0,
        gate_magnitude=9.0,
        gate_size=3.0,
        edition="pocket",
        forced_lists=frozenset({"pocket_classics"}),
    )
    standard = _oc_policy(
        minimum_size=10.0,
        gate_magnitude=10.0,
        gate_size=3.0,
        edition="standard",
        automatic_designation_prefixes=("NGC", "IC"),
        parents=(pocket,),
    )
    cases = (
        (10.0, 3.0, True),
        (10.1, 3.0, False),
        (None, 10.0, True),
        (None, 9.9, False),
        (12.0, 3.0, False),
    )
    for index, (magnitude, size, expected) in enumerate(cases):
        result = select_dso(
            make_open_cluster(f"NGC{index + 1}", magnitude=magnitude, size=size),
            policy=standard,
        )
        assert (result.visible or result.forced) is expected

    pocket_only = select_dso(
        make_open_cluster("NGC8888", magnitude=15.0, size=1.0),
        index={"NGC8888": frozenset({"pocket_classics"})},
        policy=standard,
    )
    assert pocket_only.visible
    assert "included_by_pocket_hierarchy" in pocket_only.visibility_reasons

    non_openngc = select_dso(
        make_open_cluster("Mel 999", magnitude=None, size=15.0, catalogue="VII/92A:Melotte"),
        policy=standard,
    )
    assert not non_openngc.visible and not non_openngc.forced

    non_ngc_designation = select_dso(
        make_open_cluster("Mel 999", magnitude=None, size=15.0),
        policy=standard,
    )
    assert not non_ngc_designation.visible and not non_ngc_designation.forced


def test_explicit_exclusion_suppresses_even_a_forced_membership() -> None:
    dso = make_open_cluster("C014", magnitude=None, size=50.0)
    result = select_dso(
        dso,
        index={"C014": frozenset({"caldwell"})},
        policy=_oc_policy(
            minimum_size=10.0,
            gate_magnitude=10.0,
            gate_size=3.0,
            edition="deep",
            forced_lists=frozenset({"caldwell"}),
            excluded_designations=("C014",),
        ),
    )
    assert not result.visible and not result.forced
    assert result.list_memberships == {"caldwell"}


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
