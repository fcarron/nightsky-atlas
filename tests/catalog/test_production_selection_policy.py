from __future__ import annotations

from pathlib import Path

import pytest

from nightsky_atlas.atlas.observing_config import (
    load_observing_lists_config,
    resolve_edition,
)
from nightsky_atlas.catalog.dso_store import load_dso_catalog
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
    expected = {
        "galaxy": (10522, 2280, 5200, 10462),
        "galaxy group / cluster": (361, 2, 179, 361),
        "open cluster": (818, 319, 642, 818),
        "globular cluster": (228, 171, 226, 228),
        "planetary nebula": (202, 126, 129, 130),
        "bright nebula / H-II": (1387, 43, 822, 1387),
        "reflection nebula": (130, 1, 1, 130),
        "dark nebula": (2128, 0, 995, 2128),
        "supernova remnant": (11, 6, 6, 11),
        "bright nebula (unspecified subtype)": (196, 49, 49, 196),
        "other": (421, 5, 5, 5),
    }
    for type_name, counts in expected.items():
        row = rows[type_name]
        assert tuple(row[key] for key in ("total", "standard", "deep", "reference")) == counts
    assert report["edition_totals"] == {
        "standard": 3002,
        "deep": 8254,
        "reference": 15856,
    }
    assert not {
        warning["code"]
        for warning in report["hierarchy_warnings"]
        if warning["code"] in {"standard_not_deep", "deep_not_reference"}
    }


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
