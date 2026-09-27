from __future__ import annotations

import json

from nightsky_atlas.catalog.dso_store import write_dso_catalog
from nightsky_atlas.catalog.inventory import build_catalogue_inventory
from nightsky_atlas.catalog.models import CatalogSourceRecord, DeepSkyObject, DsoType, Provenance


def test_inventory_counts_physical_objects_and_alias_only_outcomes(tmp_path) -> None:
    source_record = CatalogSourceRecord(
        catalogue_id="VII/74A",
        designation="Arp 244",
        source_url="https://vizier.cds.unistra.fr/viz-bin/VizieR?-source=VII/74A",
        reference="1966ApJS....14....1A",
        retrieved="2026-09-24",
        coordinate_frame="B1970; VizieR-computed ICRS position",
        crossmatch_decision="matched_alias",
        matched_object_id="NGC 4038",
        match_reason="unique_extent_aware_position_match",
    )
    physical = DeepSkyObject(
        id="NGC 4038",
        ra_deg=180.5,
        dec_deg=-18.9,
        object_type=DsoType.GALAXY,
        provenance=Provenance(catalogue="OpenNGC", source_id="NGC 4038"),
        cross_ids=("Arp 244",),
        catalogue_records=(source_record,),
    )
    catalogue = tmp_path / "catalogue.json"
    openngc = tmp_path / "openngc.json"
    write_dso_catalog(catalogue, [physical])
    write_dso_catalog(openngc, [physical])

    catalogue_manifest = tmp_path / "catalogue.manifest.json"
    catalogue_manifest.write_text(json.dumps({"sources": []}), encoding="utf-8")
    openngc_manifest = tmp_path / "openngc.manifest.json"
    openngc_manifest.write_text(
        json.dumps({"catalogue": "OpenNGC", "raw_row_count": 1, "raw_files": []}),
        encoding="utf-8",
    )
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "manifest.json").write_text(
        json.dumps(
            {
                "catalogues": [
                    {
                        "catalogue_id": "VII/74A",
                        "raw_file": "arp.tsv",
                        "family_raw_row_count": 3,
                        "source_table_row_count": 5,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    decisions_path = tmp_path / "decisions.json"
    decisions_path.write_text(
        json.dumps(
            {
                "decisions": [
                    {
                        "catalogue_id": "VII/74A",
                        "status": "matched_alias",
                        "designation": "Arp 244",
                        "canonical_id": "NGC 4038",
                    },
                    {
                        "catalogue_id": "VII/74A",
                        "status": "uncertain_alias",
                        "designation": "Arp 1",
                    },
                    {
                        "catalogue_id": "VII/74A",
                        "status": "unmatched_alias",
                        "designation": "Arp 2",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    report = build_catalogue_inventory(
        catalogue_path=catalogue,
        catalogue_manifest_path=catalogue_manifest,
        openngc_path=openngc,
        openngc_manifest_path=openngc_manifest,
        vizier_raw_dir=raw_dir,
        crossmatch_report_path=decisions_path,
        observing_config_path="config/observing_lists.yaml",
        observing_lists_dir="data/fixtures/observing_lists",
    )

    arp = next(row for row in report["source_rows"] if row["catalogue"] == "VII/74A")
    assert report["physical_object_count"] == 1
    assert report["physical_dso_count"] == 1
    assert report["physical_objects_by_type"]["galaxy"] == 1
    assert arp["raw_rows"] == 3
    assert arp["parsed_rows"] == 3
    assert arp["new_physical_objects"] == 0
    assert arp["matched_aliases"] == 1
    assert arp["uncertain_matches"] == 1
    assert arp["unmatched_aliases"] == 1
    assert arp["filtered_parent_rows"] == 2
    assert report["duplicate_prevention_examples"][0]["canonical_object"] == "NGC 4038"
