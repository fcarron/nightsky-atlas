from dataclasses import replace
from pathlib import Path

import pytest

from nightsky_atlas.atlas.config import EditionConfig, load_atlas_config
from nightsky_atlas.atlas.index import build_atlas_index
from nightsky_atlas.atlas.observing_config import (
    load_observing_lists_config,
    resolve_edition,
    resolve_edition_hierarchy,
)
from nightsky_atlas.catalog.models import DeepSkyObject, DsoType
from nightsky_atlas.catalog.observing_lists import build_membership_index, load_observing_lists
from nightsky_atlas.catalog.openngc import parse_openngc_row
from nightsky_atlas.catalog.selection import select_dso
from nightsky_atlas.chart.models import ChartDefinition
from nightsky_atlas.layout.dso_labels import DsoLabelTier, format_dso_label, primary_designation
from nightsky_atlas.projection.base import ChartPoint
from nightsky_atlas.scene.models import SceneDso

ROOT = Path(__file__).resolve().parents[2]


def source_object(name, type_code, **fields):
    obj = parse_openngc_row(
        {
            "Name": name,
            "Type": type_code,
            "RA": "05:00:00",
            "Dec": "+20:00:00",
            **fields,
        }
    )
    assert obj is not None
    return obj


def index_entry(obj):
    chart = ChartDefinition("pocket-001", 75, 20, 54, 36)
    index = build_atlas_index(
        {chart.id: (SceneDso(obj, ChartPoint(0, 0)),)},
        {},
        (chart,),
        EditionConfig(name="Pocket", code="P", chart_index_width=2),
    )
    return index.dso_entries[0]


def test_m102_is_messier_alias_without_replacing_ngc_identity():
    obj = source_object("NGC5866", "G")
    assert obj.id == "NGC5866"
    assert "M102" in obj.cross_ids
    assert primary_designation(obj) == "M102"
    assert format_dso_label(obj).tier == DsoLabelTier.MESSIER
    assert index_entry(obj).designation == "M102"
    assert DeepSkyObject.from_dict(obj.to_dict()) == obj


@pytest.mark.parametrize("constellation", ["Se1", "Se2", "Ser"])
def test_serpens_printed_as_ser_preserves_catalogue_region(constellation):
    obj = source_object("NGC5904", "GCl", Const=constellation)
    assert obj.constellation == constellation
    assert index_entry(obj).constellation == "Ser"


@pytest.mark.parametrize(
    ("code", "subtype", "type_name"),
    [
        ("G", None, "Galaxy"),
        ("GPair", "galaxy pair", "Galaxy Pair"),
        ("GTrpl", "galaxy triplet", "Galaxy Group"),
        ("GGroup", "galaxy group", "Galaxy Group"),
    ],
)
def test_source_galaxy_system_types_survive_import_and_index(code, subtype, type_name):
    obj = source_object("NGC0520", code)
    assert obj.semantic_subtype == subtype
    assert index_entry(obj).object_type == type_name
    assert index_entry(replace(obj, semantic_subtype=None)).object_type == (
        "Galaxy" if code == "G" else "Galaxy Cluster"
    )


@pytest.mark.parametrize(
    "name",
    [
        "NGC1981",
        "NGC2239",
        "NGC6530",
        "NGC6823",
        "NGC6997",
        "NGC7380",
    ],
)
def test_cluster_identities_are_open_clusters(name):
    obj = source_object(name, "Cl+N")
    assert obj.object_type == DsoType.OPEN_CLUSTER
    assert obj.semantic_subtype == "cluster with nebulosity"
    assert index_entry(obj).object_type == "Open Cluster"


def test_cluster_nebula_identity_overrides_preserve_orion_and_recognize_open_clusters():
    assert source_object("NGC1976", "Cl+N").object_type == DsoType.BRIGHT_NEBULA
    for name, type_code in (("NGC3247", "HII"), ("NGC6250", "Cl+N")):
        obj = source_object(name, type_code)
        assert obj.object_type == DsoType.OPEN_CLUSTER
        assert obj.semantic_subtype == "cluster with nebulosity"


def test_m24_is_star_cloud_not_open_cluster():
    obj = source_object("IC4715", "*Ass", M="024")
    assert obj.object_type == DsoType.OTHER
    assert index_entry(obj).object_type == "Star Cloud"
    assert index_entry(obj).designation == "M24"


def test_ngc405_stellar_identity_is_excluded_from_dso_layer():
    obj = source_object("NGC0405", "Other", **{"V-Mag": "6.89"})
    assert obj.object_type == DsoType.DOUBLE_STAR
    result = select_dso(obj, policy=pocket_policy())
    assert not (result.visible or result.forced)


def test_openngc_duplicate_designations_are_aliases_and_preferred_display_is_shared():
    obj = source_object("NGC2239", "Cl+N", NGC="2244", IC="0123A, 00124")
    assert obj.cross_ids == ("NGC2244", "IC123A", "IC124")
    assert obj.id == "NGC2239"
    assert primary_designation(obj) == "2244"
    assert index_entry(obj).designation == "NGC 2244"
    obj = replace(obj, id="PGC 70070", cross_ids=("IC   5269B",))
    assert primary_designation(obj) == "I5269B"
    assert index_entry(obj).designation == "IC 5269B"


def pocket_policy():
    policy = resolve_edition(
        load_observing_lists_config(ROOT / "config/observing_lists.yaml"), "pocket"
    )
    return replace(
        policy, visibility=load_atlas_config(ROOT / "atlas/pocket.yaml").visibility.to_limits()
    )


@pytest.mark.parametrize("name", ["NGC1487 NED02", "NGC4656 NED01"])
def test_all_editions_retain_parent_and_exclude_ned_component_without_merging(name):
    parent = source_object(name.split()[0], "GPair", MajAx="8")
    component = source_object(name, "G", **{"V-Mag": "9", "MajAx": "6", "MinAx": "2"})
    index = build_membership_index(load_observing_lists(), [parent, component])
    for edition in ("pocket", "standard", "deep", "reference"):
        policy = resolve_edition(load_observing_lists_config(), edition)
        decision = select_dso(component, index=index, policy=policy)
        assert not (decision.visible or decision.forced)
        assert "edition_designation_excluded" in decision.visibility_reasons
    parent_decision = select_dso(parent, index=index, policy=pocket_policy())
    assert parent_decision.visible or parent_decision.forced
    assert component.id == name
    assert component.magnitude == 9
    assert parent.magnitude is None


@pytest.mark.parametrize(
    "name",
    [
        "PGC025886",
        "PGC 30484",
        "PGC 46039",
        "PGC 66669",
        "PGC 71943",
        "PGC 71948",
        "ESO208-021",
        "ESO221-026",
        "ESO383-087",
        "IC3322A",
        "IC2605",
        "IC3668",
        "IC3669",
    ],
)
def test_editorial_exclusions_are_pocket_only(name):
    obj = source_object(name, "G", **{"V-Mag": "8", "MajAx": "5", "MinAx": "2"})
    for edition in ("pocket", "standard", "deep", "reference"):
        policy = resolve_edition(load_observing_lists_config(), edition)
        result = select_dso(obj, policy=policy)
        if edition == "pocket":
            assert not result.visible
            assert "edition_designation_excluded" in result.visibility_reasons
        else:
            assert name not in policy.excluded_designations


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("Mel 20", "OCl"),
        ("NGC2359", "HII"),
        ("NGC0281", "HII"),
    ],
)
def test_classic_targets_selected_with_explicit_pocket_reason(name, code):
    obj = source_object(name, code)
    index = build_membership_index(load_observing_lists(), [obj])
    result = select_dso(obj, index=index, policy=pocket_policy())
    assert result.visible or result.forced
    assert result.forced
    assert "pocket_curated_visual_target" in result.visibility_reasons
    config = load_observing_lists_config(ROOT / "config/observing_lists.yaml")
    visibility = {
        edition: load_atlas_config(ROOT / "atlas" / f"{edition}.yaml").visibility.to_limits()
        for edition in ("pocket", "standard", "deep")
    }
    for edition in ("standard", "deep"):
        policy = resolve_edition(load_observing_lists_config(), edition)
        assert "nightsky_pocket_classics" not in policy.forced_lists
        inherited_policy = resolve_edition_hierarchy(
            config, edition, visibility_by_edition=visibility
        )
        inherited = select_dso(obj, index=index, policy=inherited_policy)
        assert inherited.visible or inherited.forced


def test_pocket_target_inclusion_is_inherited_by_standard_and_deep():
    config = load_observing_lists_config(ROOT / "config/observing_lists.yaml")
    visibility = {
        edition: load_atlas_config(ROOT / "atlas" / f"{edition}.yaml").visibility.to_limits()
        for edition in ("pocket", "standard", "deep")
    }
    policies = {
        edition: resolve_edition_hierarchy(
            config, edition, visibility_by_edition=visibility
        )
        for edition in ("pocket", "standard", "deep")
    }
    obj = source_object("NGC0001", "G")
    index = {"NGC1": frozenset({"nightsky_pocket_classics"})}
    pocket = select_dso(obj, index=index, policy=policies["pocket"])
    standard = select_dso(obj, index=index, policy=policies["standard"])
    deep = select_dso(obj, index=index, policy=policies["deep"])
    assert pocket.forced
    assert standard.visible and "included_by_pocket_hierarchy" in standard.visibility_reasons
    assert deep.visible


def test_curated_bright_and_dark_nebulae_are_selected_in_standard_and_deep():
    config = load_observing_lists_config(ROOT / "config/observing_lists.yaml")
    lists = load_observing_lists(ROOT / "data/fixtures/observing_lists")
    bright = source_object("IC1396", "HII")
    dark = replace(source_object("B 72", "Other"), object_type=DsoType.DARK_NEBULA)
    index = build_membership_index(lists, [bright, dark])
    for edition in ("standard", "deep"):
        policy = resolve_edition(config, edition)
        for obj, list_id in (
            (bright, "nightsky_curated_bright_nebulae_v1"),
            (dark, "nightsky_curated_dark_nebulae_v1"),
        ):
            result = select_dso(obj, index=index, policy=policy)
            assert result.visible or result.forced
            assert result.forced
            assert list_id in result.list_memberships


def test_global_component_exclusions_apply_to_every_edition():
    config = load_observing_lists_config(ROOT / "config/observing_lists.yaml")
    for edition in ("pocket", "standard", "deep", "reference"):
        policy = resolve_edition(config, edition)
        assert {"NGC1487 NED02", "NGC4656 NED01"} <= set(policy.excluded_designations)


def test_special_galaxies_not_blanket_excluded():
    policy = pocket_policy()
    for name in ("ESO121-006", "ESO351-030", "ESO356-004", "PGC 70070", "NGC4496A"):
        assert name not in policy.excluded_designations


def test_pocket_report_counts_forced_targets_like_scene_builder(monkeypatch):
    from nightsky_atlas.catalog import pocket_selection

    ordinary = source_object("NGC1981", "Cl+N", **{"V-Mag": "4.2", "MajAx": "9"})
    forced = source_object("NGC2359", "HII", MajAx="10")
    monkeypatch.setattr(pocket_selection, "load_dso_catalog", lambda path: [ordinary, forced])
    report = pocket_selection.build_pocket_selection_report()
    assert report["selected_pocket_physical_objects"] == 2
    assert sum(row["selected"] for row in report["type_counts"].values()) == 2


def test_conflicting_live_catalogue_designation_is_not_imported_as_exact_alias(tmp_path):
    from nightsky_atlas.catalog.openngc import iter_openngc_objects

    path = tmp_path / "objects.csv"
    path.write_text(
        "Name;Type;RA;Dec;NGC;IC\n"
        "NGC7418;G;22:56:36;-37:01:48;;1459\n"
        "IC1459;G;22:57:10;-36:27:44;;\n"
        "NGC2239;Cl+N;06:31:55;+04:56:34;2244;\n"
        "NGC2244;Dup;06:31:55;+04:56:34;2239;\n"
    )
    objects = {obj.id: obj for obj in iter_openngc_objects([path])}
    assert len(objects) == 3
    assert "IC1459" not in objects["NGC7418"].cross_ids
    assert "NGC2244" in objects["NGC2239"].cross_ids
