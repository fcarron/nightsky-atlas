from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from nightsky_atlas.atlas.observing_config import load_observing_lists_config, resolve_edition
from nightsky_atlas.catalog.models import (
    CatalogSourceRecord,
    DeepSkyObject,
    DsoType,
    Provenance,
)
from nightsky_atlas.catalog.observing_lists import build_membership_index, load_observing_lists
from nightsky_atlas.catalog.selection_analysis import explain_selection
from nightsky_atlas.research.observing_lists.coverage import (
    build_coverage_report,
    compare_reports,
    load_external_list,
    load_manual_overrides,
    write_csv_report,
    write_json_report,
)
from nightsky_atlas.research.observing_lists.matcher import ManualMatchOverride, match_entries
from nightsky_atlas.research.observing_lists.models import ExternalObservingListEntry
from nightsky_atlas.research.observing_lists.parser_base import (
    normalize_external_designation,
    parse_angle,
)


def _object(
    designation: str,
    *,
    aliases: tuple[str, ...] = (),
    ra: float = 12.0,
    dec: float = 5.0,
    object_type: DsoType = DsoType.GALAXY,
    catalogue: str = "OpenNGC",
    source_records: tuple[CatalogSourceRecord, ...] = (),
) -> DeepSkyObject:
    return DeepSkyObject(
        id=designation,
        ra_deg=ra,
        dec_deg=dec,
        object_type=object_type,
        provenance=Provenance(catalogue, designation),
        magnitude=9.0,
        major_axis_arcmin=3.0,
        minor_axis_arcmin=2.0,
        cross_ids=aliases,
        catalogue_records=source_records,
    )


def _entry(
    designation: str,
    *,
    type_hint: str | None = None,
    ra: float | None = None,
    dec: float | None = None,
    row: str = "case.csv:2",
) -> ExternalObservingListEntry:
    return ExternalObservingListEntry(
        source="AstroPlanner",
        source_list="synthetic",
        locator=row,
        imported_file="case.csv",
        raw_designation=designation,
        normalized_designation=normalize_external_designation(designation),
        object_type_hint=type_hint,
        ra_deg=ra,
        dec_deg=dec,
    )


def test_formatting_normalization_and_exact_canonical_match() -> None:
    obj = _object("NGC7000")
    matches = match_entries([_entry("NGC 7000"), _entry("NGC-7000")], [obj])
    assert [item.matched_object_id for item in matches] == ["NGC7000", "NGC7000"]
    assert all(item.match_method == "canonical_exact" for item in matches)


def test_alias_match_and_duplicate_aliases_collapse_by_physical_id() -> None:
    obj = _object("NGC1976", aliases=("M 42", "NGC 1976"))
    matches = match_entries([_entry("M42"), _entry("NGC 1976")], [obj])
    assert [item.matched_object_id for item in matches] == ["NGC1976", "NGC1976"]
    assert matches[0].match_method == "alias_exact"
    assert len({item.matched_object_id for item in matches}) == 1


def test_cross_catalogue_collinder_normalization_is_reused() -> None:
    obj = _object("Cr 399")
    match = match_entries([_entry("Cl 399")], [obj])[0]
    assert match.matched_object_id == "Cr 399"
    assert match.match_method == "alias_exact"


def test_duplicate_alias_collision_is_not_silently_resolved() -> None:
    first = _object("NGC1", aliases=("Shared alias",))
    second = _object("NGC2", aliases=("Shared alias",))
    match = match_entries([_entry("Shared alias")], [first, second])[0]
    assert match.matched_object is None
    assert match.match_method == "unresolved"
    assert match.ambiguity_status == "ambiguous_designation"
    assert match.candidate_ids == ("NGC1", "NGC2")


def test_unknown_designation_and_coordinate_missing_are_separate() -> None:
    matches = match_entries(
        [_entry("XYZ 99"), _entry("XYZ 100", ra=140.0, dec=-35.0)],
        [_object("NGC1")],
    )
    assert matches[0].match_method == "unresolved"
    assert matches[0].ambiguity_status == "unknown_designation"
    assert matches[1].match_method == "unresolved"
    assert matches[1].ambiguity_status == "no_coordinate_candidate"


def test_coordinate_fallback_uses_type_and_reports_ambiguous_candidates() -> None:
    first = _object("NGC1", ra=10.0, dec=0.0)
    second = _object("IC1", ra=10.01, dec=0.0)
    entry = _entry("unknown", type_hint="galaxy", ra=10.005, dec=0.0)
    result = match_entries([entry], [first, second], coordinate_tolerance_arcmin=2.0)[0]
    assert result.match_method == "coordinate_ambiguous"
    assert result.candidate_ids == ("IC1", "NGC1")
    no_type = _object("NGC2", ra=10.0, dec=0.0, object_type=DsoType.OPEN_CLUSTER)
    filtered = match_entries([entry], [no_type], coordinate_tolerance_arcmin=2.0)[0]
    assert filtered.ambiguity_status == "no_coordinate_candidate"


def test_coordinate_unique_match_is_deterministic() -> None:
    entry = _entry("uncatalogued alias", ra=10.0, dec=0.0, type_hint="galaxy")
    obj = _object("NGC2", ra=10.01, dec=0.0)
    result = match_entries([entry], [obj], coordinate_tolerance_arcmin=2.0)[0]
    assert result.match_method == "coordinate_exactish"
    assert result.matched_object_id == "NGC2"
    assert result.separation_arcmin == pytest.approx(0.6)


def test_manual_override_resolves_and_requires_a_real_canonical_object() -> None:
    entry = _entry("very obscure")
    obj = _object("NGC1234")
    result = match_entries(
        [entry],
        [obj],
        overrides=(ManualMatchOverride("AstroPlanner", "very obscure", "NGC1234", "verified"),),
    )[0]
    assert result.match_method == "manual_override"
    assert result.note == "verified"
    with pytest.raises(ValueError, match="not a canonical DSO ID"):
        match_entries(
            [entry],
            [obj],
            overrides=(ManualMatchOverride("AstroPlanner", "very obscure", "NGC99", "bad"),),
        )


def test_astroplanner_csv_discards_notes_and_ratings(tmp_path: Path) -> None:
    source = tmp_path / "local.csv"
    source.write_text(
        "Catalogue,Name,RA,Dec,Type,Constellation,Rating,Description,Notes\n"
        'NGC,7000,"20:58:48","+44:20:00",EN,Cyg,5,"copyright text","private note"\n',
        encoding="utf-8",
    )
    parsed = load_external_list(source="astroplanner", input_path=source, list_name="NSOG export")
    entry = parsed.entries[0]
    assert entry.raw_designation == "NGC 7000"
    assert entry.ra_deg == pytest.approx(314.7)
    assert entry.dec_deg == pytest.approx(44.333333, abs=1e-5)
    serialized = json.dumps(entry.to_dict(), sort_keys=True)
    assert "copyright text" not in serialized
    assert "private note" not in serialized
    assert "Rating" not in serialized


def test_astroplanner_apft_plan_extracts_only_identity_fields(tmp_path: Path) -> None:
    source = tmp_path / "NSOG_And_D.txt"
    source.write_text(
        "APTF,2\n<<Description>>\nignored private description\n<<Objects>>\n"
        "1\tNGC7000\tNorth America\t20.9800000\t44.3333333\t4\t999\t120\t0\tGalaxy"
        "\tNGC\t6996\tcopyrighted object note\t5\n"
        "2\t\tvdB 62\t5.9100000\t1.7000000\t8\t999\t10\t0\tBrNeb"
        "\tvdB\t62\tanother note\t4\n"
        "<<Elements>>\n<<Columns>>\n",
        encoding="utf-8",
    )
    parsed = load_external_list(source="astroplanner", input_path=source)
    assert len(parsed.entries) == 2
    first, second = parsed.entries
    assert first.raw_designation == "NGC7000"
    assert first.ra_deg == pytest.approx(314.7)
    assert first.dec_deg == pytest.approx(44.3333333)
    assert first.object_type_hint == "galaxy"
    assert second.raw_designation == "vdB 62"
    assert second.object_type_hint == "bright nebula"
    serialized = json.dumps([entry.to_dict() for entry in parsed.entries])
    assert "copyrighted object note" not in serialized
    assert "another note" not in serialized
    assert "ignored private description" not in serialized
    assert "North America" not in serialized
    assert "rating" not in first.to_dict()


def test_astroleague_text_list_parsing(tmp_path: Path) -> None:
    source = tmp_path / "dark.txt"
    source.write_text("# local list\nB 33\nLDN 1622\n", encoding="utf-8")
    parsed = load_external_list(source="astronomical-league", input_path=source)
    assert [entry.normalized_designation for entry in parsed.entries] == ["B33", "LDN1622"]


def test_parse_angle_handles_decimal_and_sexagesimal() -> None:
    assert parse_angle("18:50:00", is_ra=True) == pytest.approx(282.5)
    assert parse_angle("-35:30:00", is_ra=False) == pytest.approx(-35.5)
    assert parse_angle("12.5", is_ra=False) == pytest.approx(12.5)


def test_malformed_csv_has_actionable_error(tmp_path: Path) -> None:
    source = tmp_path / "bad.csv"
    source.write_text("magnitude,notes\n12,ignore\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no designation column"):
        load_external_list(source="astroplanner", input_path=source)


def test_malformed_coordinates_are_counted_as_parse_failures(tmp_path: Path) -> None:
    source = tmp_path / "bad-coordinate.csv"
    source.write_text("designation,ra,dec\nNGC7000,abc,+10\n", encoding="utf-8")
    parsed = load_external_list(source="astroplanner", input_path=source)
    assert parsed.entries[0].parse_error
    result = match_entries(parsed.entries, [_object("NGC7000")])[0]
    assert result.match_method == "parse_failure"


def test_manual_override_yaml_is_supported(tmp_path: Path) -> None:
    path = tmp_path / "overrides.yaml"
    path.write_text(
        "overrides:\n  - source: AstroPlanner\n    raw_designation: obscure\n"
        "    canonical_object: NGC1\n    reason: checked\n",
        encoding="utf-8",
    )
    overrides = load_manual_overrides(path)
    assert overrides == (ManualMatchOverride("AstroPlanner", "obscure", "NGC1", "checked"),)


def test_report_deduplicates_targets_and_uses_production_selector(tmp_path: Path) -> None:
    catalogue_path = tmp_path / "catalogue.json"
    external_path = tmp_path / "list.csv"
    obj = _object("NGC1976", aliases=("M42",), object_type=DsoType.BRIGHT_NEBULA)
    catalogue_path.write_text(json.dumps([obj.to_dict()]), encoding="utf-8")
    external_path.write_text(
        "designation,type,note\nNGC 1976,EN,ignore this\nM42,EN,also ignore\n",
        encoding="utf-8",
    )
    external = load_external_list(source="astroplanner", input_path=external_path)
    report = build_coverage_report(external, catalogue_path=catalogue_path)
    assert report.summary["unique_matched_physical_targets"] == 1
    assert report.summary["unique_external_designations"] == 2
    assert report.summary["unique_alias_designations_collapsed"] == 1

    config = load_observing_lists_config("config/observing_lists.yaml")
    lists = load_observing_lists("data/fixtures/observing_lists")
    index = build_membership_index(lists, [obj])
    policy = resolve_edition(config, "deep")
    expected = explain_selection(obj, edition="deep", policy=policy, index=index)
    target = report.targets[0]
    assert target["editions"]["deep"]["selected"] == expected["selected"]
    assert target["editions"]["deep"]["reason_codes"] == [
        item["code"] for item in expected["reasons"]
    ]


def test_nebula_source_analysis_uses_catalogue_provenance_families(tmp_path: Path) -> None:
    catalogue_path = tmp_path / "catalogue.json"
    source_path = tmp_path / "nebulae.txt"
    dark = _object("LDN1", object_type=DsoType.DARK_NEBULA, catalogue="VII/7A")
    bright = _object("LBN2", object_type=DsoType.BRIGHT_NEBULA, catalogue="VII/9")
    catalogue_path.write_text(json.dumps([dark.to_dict(), bright.to_dict()]), encoding="utf-8")
    source_path.write_text("LDN1\nLBN2\n", encoding="utf-8")
    external = load_external_list(source="astronomical-league", input_path=source_path)
    report = build_coverage_report(external, catalogue_path=catalogue_path)
    assert report.source_catalogue_coverage["VII/7A"]["matched_physical_targets"] == 1
    dark_analysis = report.nebula_source_analysis["by_type"]["dark nebula"]
    bright_analysis = report.nebula_source_analysis["by_type"]["bright nebula / H-II"]
    assert dark_analysis["catalogue_coverage_counts"]["LDN"] == 1
    assert dark_analysis["ldn_only_targets"] == ["LDN1"]
    assert bright_analysis["catalogue_coverage_counts"]["LBN"] == 1
    assert bright_analysis["lbn_only_targets"] == ["LBN2"]


def test_json_and_csv_outputs_are_deterministic_and_content_is_sanitized(tmp_path: Path) -> None:
    source = tmp_path / "private.csv"
    source.write_text(
        "designation,notes,rating\nNGC7000,secret observation note,10\n",
        encoding="utf-8",
    )
    external = load_external_list(source="astroplanner", input_path=source)
    catalogue_path = tmp_path / "catalogue.json"
    catalogue_path.write_text(json.dumps([_object("NGC7000").to_dict()]), encoding="utf-8")
    report = build_coverage_report(external, catalogue_path=catalogue_path)
    one, two = tmp_path / "one.json", tmp_path / "two.json"
    write_json_report(report, one)
    write_json_report(report, two)
    assert one.read_bytes() == two.read_bytes()
    content = one.read_text(encoding="utf-8")
    assert "secret observation note" not in content
    assert "rating" not in content.casefold()
    csv_path = tmp_path / "report.csv"
    write_csv_report(report, csv_path)
    with csv_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["matched_canonical_designation"] == "NGC7000"
    assert "secret observation note" not in csv_path.read_text(encoding="utf-8")


def test_source_file_stays_external_and_is_not_copied(tmp_path: Path) -> None:
    outside = tmp_path / "local-research" / "nsog.csv"
    outside.parent.mkdir()
    outside.write_text("designation\nNGC7000\n", encoding="utf-8")
    parsed = load_external_list(source="astroplanner", input_path=outside)
    assert parsed.entries[0].imported_file == "nsog.csv"
    assert outside.exists()
    assert not (Path("data/fixtures/observing_lists") / outside.name).exists()


def test_research_cli_runs_without_copying_input(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    from nightsky_atlas.cli import main

    source = tmp_path / "user-list.csv"
    catalogue = tmp_path / "catalogue.json"
    output = tmp_path / "coverage.json"
    source.write_text("designation\nNGC7000\n", encoding="utf-8")
    catalogue.write_text(json.dumps([_object("NGC7000").to_dict()]), encoding="utf-8")
    result = main(
        [
            "research",
            "observing-list-coverage",
            "--source",
            "astroplanner",
            "--input",
            str(source),
            "--catalogue",
            str(catalogue),
            "--json",
            str(output),
        ]
    )
    assert result == 0
    assert "Unique matched physical targets: 1" in capsys.readouterr().out
    assert (
        json.loads(output.read_text(encoding="utf-8"))["summary"]["unique_matched_physical_targets"]
        == 1
    )


def test_cross_list_comparison_uses_physical_object_ids(tmp_path: Path) -> None:
    catalogue = tmp_path / "catalogue.json"
    catalogue.write_text(
        json.dumps([_object("NGC1").to_dict(), _object("NGC2").to_dict()]),
        encoding="utf-8",
    )
    reports = []
    for source_name, list_name, designations in (
        ("astroplanner", "list one", ("NGC1", "NGC2")),
        ("astronomical-league", "list two", ("NGC2",)),
    ):
        source = tmp_path / f"{list_name.replace(' ', '-')}.txt"
        source.write_text("\n".join(designations) + "\n", encoding="utf-8")
        report = build_coverage_report(
            load_external_list(
                source=source_name, input_path=source, list_name=list_name
            ),
            catalogue_path=catalogue,
        )
        report_path = tmp_path / f"{list_name.replace(' ', '-')}.json"
        write_json_report(report, report_path)
        reports.append(report_path)

    comparison = compare_reports(tuple(reports), minimum_lists=2)
    assert comparison["unique_physical_targets_union"] == 2
    assert comparison["intersection_count"] == 1
    assert comparison["targets_in_at_least_minimum_lists"] == ["NGC2"]
