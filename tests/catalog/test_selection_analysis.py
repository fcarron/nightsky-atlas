from __future__ import annotations

import json

from nightsky_atlas.catalog.dso_store import write_dso_catalog
from nightsky_atlas.catalog.models import DeepSkyObject, DsoType, Provenance
from nightsky_atlas.catalog.selection import SelectionPolicy, select_dso
from nightsky_atlas.catalog.selection_analysis import (
    _selection_warnings,
    build_selection_report,
    explain_selection,
    find_object,
    write_selection_csv,
)
from nightsky_atlas.catalog.visibility import VisibilityLimits


def _galaxy() -> DeepSkyObject:
    return DeepSkyObject(
        id="NGC0891",
        ra_deg=35.639,
        dec_deg=42.349,
        object_type=DsoType.GALAXY,
        provenance=Provenance(catalogue="OpenNGC", source_id="NGC0891"),
        magnitude=9.9,
        b_magnitude=10.4,
        v_magnitude=9.9,
        major_axis_arcmin=13.5,
        minor_axis_arcmin=2.5,
        hubble_type="Sb",
        cross_ids=("UGC 1861", "Arp 23"),
    )


def test_find_object_matches_canonical_and_alias_without_duplication() -> None:
    galaxy = _galaxy()
    assert find_object([galaxy], "  arp   23 ") is galaxy
    assert find_object([galaxy], "NGC 891") is galaxy
    assert find_object([galaxy], "NGC0891") is galaxy
    assert find_object([galaxy], "NGC 892") is None


def test_selection_explanation_uses_current_result_and_structured_reasons() -> None:
    galaxy = _galaxy()
    policy = SelectionPolicy(visibility=VisibilityLimits())
    decision = explain_selection(
        galaxy,
        edition="deep",
        policy=policy,
        index={},
    )
    current = select_dso(galaxy, policy=policy)
    assert decision["selected"] == (current.visible or current.forced)
    assert decision["edition"] == "deep"
    assert any(reason["code"] == "type_visibility_passed" for reason in decision["reasons"])
    assert decision["dimensions"]["catalogue_coverage"]["source_catalogues"] == ["OpenNGC"]
    assert decision["missing_selection_metadata"] == []


def test_missing_metadata_is_explained_for_abell_style_planetary_nebula() -> None:
    pn = DeepSkyObject(
        id="Abell PN 39",
        ra_deg=246.88,
        dec_deg=27.90,
        object_type=DsoType.PLANETARY_NEBULA,
        provenance=Provenance(catalogue="IV/24:AbellPN", source_id="Abell PN 39"),
    )
    decision = explain_selection(
        pn,
        edition="deep",
        policy=SelectionPolicy(),
        index={},
    )
    assert not decision["selected"]
    assert {"magnitude", "angular_size", "surface_brightness"}.issubset(
        decision["missing_selection_metadata"]
    )
    assert any(reason["code"] == "no-photometry" for reason in decision["reasons"])


def test_hierarchy_warning_detects_standard_object_missing_from_deep() -> None:
    galaxy = _galaxy()
    decisions = {
        galaxy.id: {
            "standard": {"selected": True, "reasons": []},
            "deep": {
                "selected": False,
                "reasons": [{"code": "catalogue_not_enabled"}],
            },
            "reference": {"selected": True, "reasons": []},
        }
    }
    warnings = _selection_warnings([galaxy], decisions)
    issue = next(item for item in warnings if item["code"] == "standard_not_deep")
    assert issue["count"] == 1
    assert issue["reason_code_counts"] == {"catalogue_not_enabled": 1}


def test_report_counts_one_physical_object_despite_multiple_aliases(tmp_path) -> None:
    galaxy = _galaxy()
    catalogue = tmp_path / "catalogue.json"
    openngc = tmp_path / "openngc.json"
    write_dso_catalog(catalogue, [galaxy])
    write_dso_catalog(openngc, [galaxy])
    manifest = tmp_path / "catalogue.manifest.json"
    manifest.write_text(json.dumps({"sources": []}), encoding="utf-8")
    openngc_manifest = tmp_path / "openngc.manifest.json"
    openngc_manifest.write_text(
        json.dumps({"catalogue": "OpenNGC", "raw_row_count": 1, "raw_files": []}),
        encoding="utf-8",
    )
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "manifest.json").write_text(json.dumps({"catalogues": []}), encoding="utf-8")
    crossmatch = tmp_path / "crossmatch.json"
    crossmatch.write_text(json.dumps({"decisions": []}), encoding="utf-8")

    options = {
        "catalogue_path": catalogue,
        "catalogue_manifest_path": manifest,
        "openngc_path": openngc,
        "openngc_manifest_path": openngc_manifest,
        "openngc_raw_dir": raw,
        "vizier_raw_dir": raw,
        "crossmatch_report_path": crossmatch,
        "observing_config_path": "config/observing_lists.yaml",
        "observing_lists_dir": "data/fixtures/observing_lists",
    }
    first = build_selection_report(**options)
    second = build_selection_report(**options)
    assert first["physical_dso_count"] == 1
    assert sum(row["total"] for row in first["type_counts"]) == 1
    assert first["edition_totals"] == {
        edition: sum(row[edition] for row in first["type_counts"])
        for edition in ("standard", "deep", "reference")
    }
    assert first == second
    assert len(first["objects"]) == 1
    assert first["objects"][galaxy.id]["visibility"]["class"]
    assert first["edition_policies"].keys() == {"standard", "deep", "reference"}

    csv_path = tmp_path / "report.csv"
    write_selection_csv(first, csv_path)
    assert csv_path.read_text(encoding="utf-8").count("NGC0891") == 1
