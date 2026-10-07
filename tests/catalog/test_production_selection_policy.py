from __future__ import annotations

from pathlib import Path

import pytest

from nightsky_atlas.atlas.observing_config import (
    load_observing_lists_config,
    resolve_edition,
)
from nightsky_atlas.catalog.dso_store import load_dso_catalog
from nightsky_atlas.catalog.galaxy_visibility import estimate_galaxy_visibility
from nightsky_atlas.catalog.models import DsoType
from nightsky_atlas.catalog.observing_lists import (
    build_membership_index,
    load_observing_lists,
)
from nightsky_atlas.catalog.selection import select_dso
from nightsky_atlas.catalog.selection_analysis import (
    build_selection_report,
    explain_selection,
    find_object,
)
from nightsky_atlas.layout.dso_labels import primary_designation

CATALOGUE = Path("data/processed/dso/catalogue.json")
pytestmark = pytest.mark.skipif(
    not CATALOGUE.is_file(),
    reason="normalized local DSO catalogue is not built",
)


@pytest.fixture(scope="module")
def production_state():
    objects = load_dso_catalog(CATALOGUE)
    config = load_observing_lists_config()
    index = build_membership_index(load_observing_lists())
    policies = {
        edition: resolve_edition(config, edition) for edition in ("standard", "deep", "reference")
    }
    return objects, index, policies


def _decisions(query, objects, index, policies):
    obj = find_object(objects, query)
    assert obj is not None, query
    return obj, {
        edition: (
            select_dso(obj, index=index, policy=policy).visible
            or select_dso(obj, index=index, policy=policy).forced
        )
        for edition, policy in policies.items()
    }


def test_observer_catalogue_examples_follow_production_policy(production_state) -> None:
    objects, index, policies = production_state
    expectations = {
        "M 31": (True, True, True),
        "NGC 891": (True, True, True),
        "NGC 7331": (True, True, True),
        "NGC 6207": (True, True, True),
        "IC 4617": (False, True, True),
        "Cr 399": (True, True, True),
        "Pal 5": (False, True, True),
        "Ter 7": (False, True, True),
        "Abell 39": (False, False, False),
        "NGC 7000": (True, True, True),
        "Sh2-101": (False, True, True),
        "LDN 123": (False, False, True),
        "B 168": (False, False, True),
        "HCG 92": (False, True, True),
    }
    for designation, expected in expectations.items():
        obj, decisions = _decisions(designation, objects, index, policies)
        assert tuple(decisions.values()) == expected, designation
        if designation == "HCG 92":
            assert obj.object_type == DsoType.GALAXY_CLUSTER
            assert len(obj.member_designations) >= 4
            member = find_object(objects, "NGC 7317")
            assert member is not None
            assert member.id != obj.id
        if designation == "B 168":
            assert any(
                record.crossmatch_decision == "uncertain" for record in obj.catalogue_records
            )


def test_production_selection_hierarchy_and_type_counts(production_state) -> None:
    report = build_selection_report()
    rows = {row["type"]: row for row in report["type_counts"]}
    assert rows["galaxy"]["total"] >= 10522
    assert sum(row["total"] for row in rows.values()) == report["physical_dso_count"]
    for edition in ("standard", "deep", "reference"):
        assert sum(row[edition] for row in rows.values()) == report["edition_totals"][edition]
    assert report["edition_totals"] == {
        # The verified Caldwell fixture activates the already-configured
        # Standard open-cluster membership rule for NGC 4755 and NGC 6193.
        "standard": 2989,
        "deep": 8245,
        "reference": 15857,
    }
    assert not {
        warning["code"]
        for warning in report["hierarchy_warnings"]
        if warning["code"] in {"standard_not_deep", "deep_not_reference"}
    }


def test_rc3_only_galaxies_are_ingested_but_not_enabled(production_state) -> None:
    objects, index, policies = production_state
    rc3_only = [
        obj for obj in objects
        if obj.provenance.catalogue == "VII/155"
        and {record.catalogue_id for record in obj.catalogue_records} == {"VII/155"}
    ]
    if not rc3_only:
        pytest.skip("RC3 snapshot is not imported")
    for obj in rc3_only[:20]:
        assert all(
            not (decision.visible or decision.forced)
            for policy in policies.values()
            if (decision := select_dso(obj, index=index, policy=policy))
        )


def test_why_object_uses_production_reason_codes(production_state) -> None:
    objects, index, policies = production_state
    ic4617 = find_object(objects, "IC 4617")
    assert ic4617 is not None
    standard = explain_selection(
        ic4617,
        edition="standard",
        policy=policies["standard"],
        index=index,
    )
    deep = explain_selection(
        ic4617,
        edition="deep",
        policy=policies["deep"],
        index=index,
    )
    assert not standard["selected"]
    assert deep["selected"]
    assert any(reason["code"] == "galaxy_visibility_deep" for reason in deep["reasons"])
    assert deep["visibility"]["class"] == "dotted"
    pocket = resolve_edition(load_observing_lists_config(), "pocket")
    ngc253 = find_object(objects, "NGC 253")
    assert ngc253 is not None
    pocket_reason = explain_selection(
        ngc253,
        edition="pocket",
        policy=pocket,
        index=index,
    )
    assert pocket_reason["selected"]
    assert any(reason["code"] == "pocket_caldwell" for reason in pocket_reason["reasons"])


def test_pocket_policy_forces_verified_lists_without_changing_display_names(
    production_state,
) -> None:
    objects, index, _ = production_state
    config = load_observing_lists_config()
    pocket = resolve_edition(config, "pocket")
    for designation in ("M31", "NGC 253", "NGC 891", "NGC 869", "NGC 884"):
        obj = find_object(objects, designation)
        assert obj is not None
        result = select_dso(obj, index=index, policy=pocket)
        assert result.visible or result.forced
        assert result.forced
        assert any(reason.startswith("pocket_") for reason in result.visibility_reasons)
    ngc253 = find_object(objects, "NGC 253")
    assert ngc253 is not None
    assert primary_designation(ngc253) == "253"
    assert not primary_designation(ngc253).startswith("C")


def test_pocket_ordinary_galaxies_use_100mm_score_and_size(production_state) -> None:
    objects, index, _ = production_state
    config = load_observing_lists_config()
    pocket = resolve_edition(config, "pocket")
    candidates = [obj for obj in objects if obj.object_type == DsoType.GALAXY]
    passed = next(
        obj for obj in candidates
        if not select_dso(obj, index=index, policy=pocket).forced
        and obj.provenance.catalogue == "OpenNGC"
        and obj.major_axis_arcmin is not None
        and obj.major_axis_arcmin >= 3.0
        and 100 in estimate_galaxy_visibility(obj).by_aperture
        and estimate_galaxy_visibility(obj).by_aperture[100].score >= -0.25
    )
    selected = select_dso(passed, index=index, policy=pocket)
    assert selected.visible
    assert "pocket_galaxy_visibility_100mm" in selected.visibility_reasons
    rejected = next(
        obj for obj in candidates
        if not select_dso(obj, index=index, policy=pocket).forced
        and obj.provenance.catalogue == "OpenNGC"
        and obj.major_axis_arcmin is not None
        and obj.major_axis_arcmin >= 3.0
        and 100 in estimate_galaxy_visibility(obj).by_aperture
        and estimate_galaxy_visibility(obj).by_aperture[100].score < -0.25
    )
    result = select_dso(rejected, index=index, policy=pocket)
    assert not result.visible
    assert "pocket_below_100mm_visibility" in result.visibility_reasons


def test_pocket_non_galaxy_is_not_scored_with_galaxy_visibility(production_state) -> None:
    objects, index, _ = production_state
    pocket = resolve_edition(load_observing_lists_config(), "pocket")
    globular = find_object(objects, "NGC 5139")
    assert globular is not None and globular.object_type == DsoType.GLOBULAR_CLUSTER
    result = select_dso(globular, index=index, policy=pocket)
    assert result.visible and result.forced
    assert result.galaxy_contour_class is None


def test_pocket_rc3_galaxies_only_enter_through_the_100mm_model(production_state) -> None:
    objects, index, _ = production_state
    pocket = resolve_edition(load_observing_lists_config(), "pocket")
    rc3_only = [
        obj for obj in objects
        if obj.provenance.catalogue == "VII/155"
        and {record.catalogue_id for record in obj.catalogue_records} == {"VII/155"}
        and obj.object_type == DsoType.GALAXY
        and not select_dso(obj, index=index, policy=pocket).forced
    ]
    for obj in rc3_only:
        decision = select_dso(obj, index=index, policy=pocket)
        if decision.visible:
            assert obj.major_axis_arcmin is not None and obj.major_axis_arcmin >= 3.0
            score = estimate_galaxy_visibility(obj).by_aperture.get(100)
            assert score is not None and score.score >= -0.25
            assert "pocket_galaxy_visibility_100mm" in decision.visibility_reasons


def test_pocket_list_alias_resolves_rossette_target_without_duplicate(production_state) -> None:
    objects, _, _ = production_state
    rosette = find_object(objects, "NGC 2244")
    assert rosette is not None
    assert rosette.id == "NGC2239"
    index = build_membership_index(load_observing_lists(), objects)
    pocket = resolve_edition(load_observing_lists_config(), "pocket")
    result = select_dso(rosette, index=index, policy=pocket)
    assert result.visible and result.forced
    assert {"caldwell", "herschel400"} <= result.list_memberships
    assert primary_designation(rosette) == "2244"


def test_pocket_caldwell_double_cluster_has_only_component_objects(production_state) -> None:
    objects, index, _ = production_state
    pocket = resolve_edition(load_observing_lists_config(), "pocket")
    aggregate = find_object(objects, "C014")
    assert aggregate is not None
    assert not select_dso(aggregate, index=index, policy=pocket).visible
    assert {find_object(objects, "NGC 869").id, find_object(objects, "NGC 884").id} == {
        "NGC0869", "NGC0884"
    }


def test_new_observing_list_data_does_not_change_deep_or_reference_counts(production_state) -> None:
    report = build_selection_report()
    assert report["edition_totals"]["deep"] == 8245
    assert report["edition_totals"]["reference"] == 15857
