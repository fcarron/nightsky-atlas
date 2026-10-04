from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from nightsky_atlas.catalog.dso_store import load_dso_catalog
from nightsky_atlas.research.nebula_curation import (
    merge_candidate_sources,
    preferred_dark_designation,
    southern_counts,
    validate_curated_document,
)


def test_candidate_union_deduplicates_only_stable_physical_ids() -> None:
    merged = merge_candidate_sources(
        [
            {"object_id": "LDN 93", "evidence": ["program_a"], "status": "review"},
            {"object_id": "B 86", "evidence": ["program_a"], "status": "include"},
        ],
        [
            {"object_id": "LDN 93", "evidence": ["program_b"], "status": "include"},
        ],
    )

    assert [row["object_id"] for row in merged] == ["B 86", "LDN 93"]
    assert merged[1]["evidence"] == ["program_a", "program_b"]
    assert merged[1]["status"] == "include"


def test_cross_id_does_not_merge_physical_identity() -> None:
    merged = merge_candidate_sources(
        [
            {"object_id": "LDN 93", "aliases": ["B 86"], "evidence": []},
            {"object_id": "B 86", "evidence": []},
        ]
    )

    assert [row["object_id"] for row in merged] == ["B 86", "LDN 93"]


def test_preferred_dark_designation_requires_same_visual_target() -> None:
    assert preferred_dark_designation("LDN 93", "B 86", "SAME_VISUAL_TARGET") == "B 86"
    assert preferred_dark_designation("LDN 93", "B 86", "CATALOG_CROSS_ID") == "LDN 93"


def test_southern_audit_counts_positions_without_inventing_missing_values() -> None:
    assert southern_counts(
        [
            {"status": "include", "dec_deg": -45},
            {"status": "include", "dec_deg": 10},
            {"status": "include", "dec_deg": None},
            {"status": "review", "dec_deg": -70},
        ]
    ) == {
        "included_with_position": 2,
        "northern_or_equatorial": 1,
        "southern": 1,
        "south_of_minus_30": 1,
        "missing_position": 1,
    }


def test_curated_yaml_has_unique_ids_and_no_third_party_research_fields() -> None:
    root = Path(__file__).parents[2]
    catalogue_ids = {
        obj.id for obj in load_dso_catalog(root / "data/processed/dso/catalogue.json")
    }
    for filename, kind in (
        ("curated_dark_nebulae_v1.yaml", "dark_nebula"),
        ("curated_bright_nebulae_v1.yaml", "bright_nebula"),
    ):
        data = yaml.safe_load((root / "config" / filename).read_text(encoding="utf-8"))
        validate_curated_document(data, expected_kind=kind)
        assert all(
            object_id in catalogue_ids
            for entry in data["entries"]
            for object_id in entry["object_ids"]
        )
        assert yaml.safe_dump(data, sort_keys=False, allow_unicode=True) == (
            root / "config" / filename
        ).read_text(encoding="utf-8")
        text = (root / "config" / filename).read_text(encoding="utf-8").casefold()
        assert "nsog_rating" not in text
        assert "description:" not in text


def test_curated_yaml_rejects_nsog_rating_leak() -> None:
    with pytest.raises(ValueError, match="third-party research fields"):
        validate_curated_document(
            {
                "schema_version": 1,
                "kind": "dark_nebula",
                "entries": [
                    {
                        "id": "ldn-93",
                        "object_ids": ["LDN 93"],
                        "status": "include",
                        "nsog_rating": 5,
                    }
                ],
            },
            expected_kind="dark_nebula",
        )
