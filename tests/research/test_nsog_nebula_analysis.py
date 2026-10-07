from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from nightsky_atlas.catalog.models import CatalogSourceRecord, DeepSkyObject, DsoType, Provenance
from nightsky_atlas.research.nsog_nebula_analysis import (
    _bright_identity_class,
    _dark_identity_class,
    _galactic_latitude_deg,
    _rating_summary,
    _target_category,
    _unmatched_class,
    read_nsog_annotations,
)
from nightsky_atlas.research.observing_lists.models import (
    CoverageMatch,
    CoverageReport,
    ExternalObservingListEntry,
)


def _object(
    object_id: str,
    *,
    object_type: DsoType = DsoType.DARK_NEBULA,
    catalogue_ids: tuple[str, ...] = (),
    aliases: tuple[str, ...] = (),
) -> DeepSkyObject:
    records = tuple(
        CatalogSourceRecord(
            catalogue_id=catalogue_id,
            designation=f"{catalogue_id}:{object_id}",
            source_url="https://example.invalid/catalogue",
            reference="synthetic fixture",
            retrieved="2026-01-01",
            coordinate_frame="ICRS",
        )
        for catalogue_id in catalogue_ids
    )
    return DeepSkyObject(
        id=object_id,
        ra_deg=10.0,
        dec_deg=5.0,
        object_type=object_type,
        provenance=Provenance("OpenNGC", object_id),
        cross_ids=aliases,
        catalogue_records=records,
    )


def _entry(locator: str) -> ExternalObservingListEntry:
    return ExternalObservingListEntry(
        source="AstroPlanner",
        source_list="synthetic",
        locator=locator,
        imported_file="fixture.txt",
        raw_designation="B 1",
        normalized_designation="B1",
    )


def test_nsog_plan_ratings_are_read_only_when_rating_column_is_declared(tmp_path: Path) -> None:
    unscored = tmp_path / "NSOG_Aql_D.txt"
    unscored.write_text(
        "APTF,2\n<<Objects>>\n1\tLDN 1\tname\t10\t5\t4\t999\t20\t0\tDkNeb\tLDN\t1\tnote\t5\n"
        "<<Elements>>\n",
        encoding="utf-8",
    )
    scored = tmp_path / "NSOG_And_D.txt"
    scored.write_text(
        "APTF,2\n<<Objects>>\n1\tLDN 2\tname\t10\t5\t4\t999\t20\t0\tDkNeb\tLDN\t2\tnote\t4\n"
        "<<Elements>>\n<<Columns>>\nNSOG Rating\n",
        encoding="utf-8",
    )

    result = read_nsog_annotations([unscored, scored])

    assert result["NSOG_Aql_D.txt:3"]["rating"] is None
    assert result["NSOG_And_D.txt:3"]["rating"] == 4
    assert "note" not in str(result)


def test_dark_identity_class_counts_barnard_ldn_overlap_once() -> None:
    assert _dark_identity_class({"Barnard", "LDN"}, ["B 33", "LDN 954"]) == "Barnard + LDN"
    assert _dark_identity_class({"LDN"}, ["LDN 66"]) == "LDN-only"
    assert _dark_identity_class({"Barnard"}, ["B 72"]) == "Barnard-backed"
    assert _dark_identity_class(set(), ["Coalsack"]) == "non-Barnard/non-LDN"


def test_bright_identity_class_separates_lbn_only_and_catalogue_overlap() -> None:
    assert _bright_identity_class({"LBN"}) == "LBN-only"
    assert _bright_identity_class({"Sharpless"}) == "Sharpless-backed"
    assert _bright_identity_class({"NGC/IC/OpenNGC", "LBN"}) == "multi-catalogue overlap"


def test_galactic_latitude_is_derived_from_coordinates() -> None:
    obj = replace(_object("GC"), ra_deg=266.4051, dec_deg=-28.936175)
    assert _galactic_latitude_deg(obj) == pytest.approx(0.0, abs=0.01)


def test_untyped_normalized_object_with_nebula_hint_is_ambiguous_not_promoted() -> None:
    obj = _object("NGC9999", object_type=DsoType.OTHER)
    assert _target_category(obj, [{"category": "emission_bright_nebula"}]) == "mixed_nebula"


def test_rating_aggregation_deduplicates_physical_object_and_uses_max() -> None:
    obj = _object("B001")
    first = CoverageMatch(_entry("fixture.txt:2"), "canonical_exact", 1.0, obj)
    second = CoverageMatch(_entry("fixture.txt:3"), "alias_exact", 0.9, obj)
    report = CoverageReport(
        metadata={},
        summary={},
        matches=(first, second),
        targets=(
            {
                "physical_object_id": "B001",
                "editions": {
                    name: {"selected": name in {"deep", "reference"}}
                    for name in ("pocket", "standard", "deep", "reference")
                },
            },
        ),
        type_coverage={},
        source_catalogue_coverage={},
        nebula_source_analysis={},
        manual_review_queue=(),
    )

    summary = _rating_summary(
        report,
        {
            "fixture.txt:2": {"rating": 3},
            "fixture.txt:3": {"rating": 5},
        },
    )

    assert summary["unique_target_count"] == 1
    assert summary["conflicting_target_count"] == 1
    assert summary["by_rating"][4]["targets"] == 1
    assert summary["by_rating"][4]["deep"] == 1


def test_unmatched_nebula_rows_keep_ambiguous_and_possible_database_gaps_separate() -> None:
    plain = CoverageMatch(_entry("fixture.txt:2"), "unresolved", 0.0)
    ambiguous = CoverageMatch(
        _entry("fixture.txt:3"),
        "coordinate_ambiguous",
        0.0,
        candidate_ids=("B001", "B002"),
        ambiguity_status="ambiguous_coordinate",
    )
    located = replace(_entry("fixture.txt:4"), ra_deg=10.0, dec_deg=5.0)
    possible_gap = CoverageMatch(located, "unresolved", 0.0)

    assert _unmatched_class(plain) == "unresolved identity; database gap not established"
    assert _unmatched_class(ambiguous) == "ambiguous identity"
    assert _unmatched_class(possible_gap) == "possible database gap"
