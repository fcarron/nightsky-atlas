from __future__ import annotations

import json

import nightsky_atlas.cli as cli
import nightsky_atlas.cli_data as cli_data
from nightsky_atlas.catalog.models import DeepSkyObject, DsoType, Provenance


def _object() -> DeepSkyObject:
    return DeepSkyObject(
        id="HCG 92",
        ra_deg=339.0,
        dec_deg=33.9,
        object_type=DsoType.GALAXY_CLUSTER,
        provenance=Provenance(catalogue="VII/213", source_id="HCG 92"),
        major_axis_arcmin=3.2,
        member_count=5,
        member_designations=("NGC 7317", "NGC 7318A", "NGC 7318B", "NGC 7319", "NGC 7320"),
        cross_ids=("Stephan's Quintet",),
    )


def test_atlas_why_object_command_reports_all_editions(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "load_dso_catalog", lambda path: [_object()])
    args = cli.build_parser().parse_args(["atlas", "why-object", "Stephan's Quintet"])
    assert args.handler(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["canonical_designation"] == "HCG 92"
    assert payload["metadata"]["member_count"] == 5
    assert set(payload["selection"]) == {
        "pocket", "standard", "deep", "eyepiece", "reference"
    }
    assert "reasons" in payload["selection"]["deep"]


def test_selection_report_cli_exports_stable_json(monkeypatch, tmp_path, capsys) -> None:
    report = {
        "physical_dso_count": 1,
        "edition_totals": {
            "pocket": 1,
            "standard": 1,
            "deep": 1,
            "eyepiece": 1,
            "reference": 1,
        },
        "type_counts": [
            {
                "type": "galaxy",
                "total": 1,
                "pocket": 1,
                "standard": 1,
                "deep": 1,
                "eyepiece": 1,
                "reference": 1,
            }
        ],
        "source_counts": [
            {
                "source": "OpenNGC",
                "catalogue_entries": 1,
                "normalized_catalogue_records": 1,
                "unique_physical_objects_contributed": 1,
                "selected_unique_physical_objects": {
                    "pocket": 1,
                    "standard": 1,
                    "deep": 1,
                    "eyepiece": 1,
                    "reference": 1,
                },
            }
        ],
        "hierarchy_warnings": [],
        "metadata_availability": {},
        "numeric_distributions": {
            "galaxy_visibility": {
                "classes": {},
                "magnitude_bins": {},
                "score_by_aperture": {},
            }
        },
        "objects": {},
    }
    monkeypatch.setattr(cli_data, "build_selection_report", lambda **kwargs: report)
    parser = cli.build_parser()
    output_paths = [tmp_path / "first.json", tmp_path / "second.json"]
    for output_path in output_paths:
        args = parser.parse_args(["data", "selection-report", "--json", str(output_path)])
        assert args.handler(args) == 0
    capsys.readouterr()
    assert output_paths[0].read_bytes() == output_paths[1].read_bytes()
