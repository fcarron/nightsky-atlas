from __future__ import annotations

import pytest

from nightsky_atlas.atlas.observing_config import load_observing_lists_config, resolve_edition
from nightsky_atlas.catalog import ucc
from nightsky_atlas.catalog.models import DeepSkyObject, DsoType, Provenance
from nightsky_atlas.catalog.selection import SelectionPolicy, select_dso
from nightsky_atlas.catalog.ucc import (
    crossmatch_ucc_objects,
    normalize_ucc_alias,
    parse_ucc_csv,
)

HEADER = "Name(s),name,N_membs,r_50,r_core,RA_ICRS,DE_ICRS,C3,P_dup,UTI,bad_oc"


def row(
    names: str,
    name: str,
    ra: str = "10.0",
    dec: str = "20.0",
    *,
    bad: str = "False",
    p_dup: str = "0.0",
) -> str:
    return f'"{names}",{name},42,8.5,1.2,{ra},{dec},AB, {p_dup},0.72,{bad}'


def test_parse_ucc_csv_retains_source_quality_without_treating_r50_as_visual_extent():
    objects = parse_ucc_csv(HEADER + "\n" + row("Stock 2, OCL 348", "stock2"))
    assert len(objects) == 1
    obj = objects[0]
    assert obj.id == "Stock 2"
    assert obj.cross_ids == ("OCL 348",)
    assert obj.ra_deg == 10.0 and obj.dec_deg == 20.0
    assert obj.major_axis_arcmin is None
    assert obj.member_count == 42
    raw = dict(obj.catalogue_records[0].raw_fields)
    assert raw["r_50"] == "8.5"
    assert raw["C3"] == "AB"
    assert raw["bad_oc"] == "False"


def test_parser_requires_fields_documented_in_pinned_readme():
    with pytest.raises(ValueError, match="missing documented columns"):
        parse_ucc_csv("name,RA_ICRS,DE_ICRS\nfoo,10,20")


def test_fetcher_verifies_and_preserves_manifest_retrieval_time(tmp_path, monkeypatch):
    import hashlib
    import io
    import json

    readme = b"release README fixture"
    csv_data = (HEADER + "\n" + row("Fixture Cluster", "fixture")).encode()
    monkeypatch.setattr(ucc, "UCC_README_MD5", hashlib.md5(readme).hexdigest())
    monkeypatch.setattr(ucc, "UCC_MD5", hashlib.md5(csv_data).hexdigest())
    payloads = iter((readme, csv_data))

    def fake_urlopen(*_args, **_kwargs):
        return io.BytesIO(next(payloads))

    monkeypatch.setattr(ucc.urllib.request, "urlopen", fake_urlopen)
    ucc.download_ucc(tmp_path)
    first = json.loads((tmp_path / "manifest.json").read_text())

    def unexpected_network(*_args, **_kwargs):
        raise AssertionError("valid cached UCC files must not be downloaded again")

    monkeypatch.setattr(ucc.urllib.request, "urlopen", unexpected_network)
    ucc.download_ucc(tmp_path)
    second = json.loads((tmp_path / "manifest.json").read_text())
    assert first == second


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Mel 0025", "MELOTTE25"),
        ("Collinder 0399", "COLLINDER399"),
        ("Cr 399", "COLLINDER399"),
        ("Stock 02", "STOCK2"),
        ("Tr 0002", "TRUMPLER2"),
        ("Harvard 020", "HARVARD20"),
    ],
)
def test_normalize_cluster_alias(value: str, expected: str):
    assert normalize_ucc_alias(value) == expected


def test_crossmatch_uses_explicit_alias_preserves_existing_identity_and_measurements():
    canonical = DeepSkyObject(
        "C041",
        12.0,
        22.0,
        DsoType.OPEN_CLUSTER,
        Provenance("VII/92A:Melotte", "C041"),
        major_axis_arcmin=60.0,
        cross_ids=("Melotte 25",),
    )
    incoming = parse_ucc_csv(HEADER + "\n" + row("Melotte 25, C041", "mel25", "12.01", "22.01"))
    result = crossmatch_ucc_objects([canonical], incoming)
    assert result.summary["matched"] == 1
    assert result.summary["new"] == 0
    merged = result.objects[0]
    assert merged.id == "C041"
    assert merged.ra_deg == canonical.ra_deg
    assert merged.major_axis_arcmin == 60.0
    assert "Melotte 25" in merged.cross_ids
    assert merged.catalogue_records[-1].catalogue_id == "UCC"


def test_position_only_match_is_quarantined_not_merged():
    canonical = DeepSkyObject(
        "Existing",
        10.0,
        20.0,
        DsoType.OPEN_CLUSTER,
        Provenance("VII/92A:Stock", "Existing"),
    )
    incoming = parse_ucc_csv(HEADER + "\n" + row("Unfamiliar Cluster", "ucc-1", "10.01", "20.01"))
    result = crossmatch_ucc_objects([canonical], incoming)
    assert result.summary["uncertain"] == 1
    assert len(result.objects) == 1
    assert result.decisions[0]["reason"] == "position_only_candidate_requires_identity_review"


def test_designation_shared_with_incompatible_object_type_is_quarantined():
    existing = DeepSkyObject(
        "IC5146",
        10.0,
        20.0,
        DsoType.BRIGHT_NEBULA,
        Provenance("OpenNGC", "IC5146"),
    )
    incoming = parse_ucc_csv(HEADER + "\n" + row("IC 5146", "ic5146", "10", "20"))
    result = crossmatch_ucc_objects([existing], incoming)
    assert result.summary["uncertain"] == 1
    assert result.objects == (existing,)
    assert result.decisions[0]["reason"] == "designation_conflicts_with_other_catalogue_identity"


def test_exact_alias_with_large_coordinate_disagreement_is_quarantined():
    existing = DeepSkyObject(
        "Stock 9",
        10.0,
        20.0,
        DsoType.OPEN_CLUSTER,
        Provenance("VII/92A:Stock", "Stock 9"),
    )
    incoming = parse_ucc_csv(HEADER + "\n" + row("Stock 9", "stock9", "15", "20"))
    result = crossmatch_ucc_objects([existing], incoming)
    assert result.summary["uncertain"] == 1
    assert result.objects == (existing,)
    assert result.decisions[0]["reason"] == "explicit_designation_coordinate_disagreement"


def test_quality_flags_quarantine_bad_oc_and_high_duplicate_probability():
    incoming = parse_ucc_csv(
        HEADER
        + "\n"
        + row("Asterism Candidate", "a1", bad="True")
        + "\n"
        + row("Duplicate Candidate", "d1", "100", "-20", p_dup="0.8")
    )
    result = crossmatch_ucc_objects([], incoming)
    assert result.summary["rejected_bad_oc"] == 1
    assert result.summary["rejected_duplicate_risk"] == 1
    assert not result.objects


def test_new_object_is_idempotent_and_not_selected_by_existing_edition_policy():
    incoming = parse_ucc_csv(HEADER + "\n" + row("New Cluster", "new-cluster", "180", "-30"))
    first = crossmatch_ucc_objects([], incoming)
    second = crossmatch_ucc_objects(first.objects, incoming)
    assert first.summary["new"] == 1
    assert second.summary == first.summary
    assert second.decisions == first.decisions
    assert len(second.objects) == 1
    assert (
        select_dso(
            second.objects[0], policy=SelectionPolicy(included_catalogues=frozenset({"OpenNGC"}))
        ).visible
        is False
    )


def test_ucc_is_not_added_to_existing_edition_catalogue_policies():
    obj = parse_ucc_csv(
        HEADER + "\n" + row("Uncurated Cluster", "unselected", "200", "-10")
    )[0]
    config = load_observing_lists_config()
    for edition in ("pocket", "standard", "deep"):
        policy = resolve_edition(config, edition)
        assert policy.included_catalogues is not None
        assert "UCC" not in policy.included_catalogues
        decision = select_dso(obj, policy=policy)
        assert not decision.visible
        assert not decision.forced
