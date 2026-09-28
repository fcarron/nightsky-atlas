"""Tests for deterministic parsing and cross-matching of VizieR DSO tables."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest

from nightsky_atlas.catalog.dso_store import load_dso_catalog, write_dso_catalog
from nightsky_atlas.catalog.models import (
    CatalogSourceRecord,
    DeepSkyObject,
    DsoType,
    Provenance,
)
from nightsky_atlas.catalog.observing_lists import canonical_designation
from nightsky_atlas.catalog.selection import SelectionPolicy, select_dso
from nightsky_atlas.catalog.visibility import VisibilityLimits
from nightsky_atlas.catalog.vizier_dso import (
    VIZIER_CATALOGUES,
    crossmatch_vizier_objects,
    format_vizier_designation,
    iter_vizier_objects,
    parse_vizier_table,
)


@pytest.mark.parametrize(
    ("catalogue_id", "header", "row", "designation", "object_type", "subtype"),
    [
        (
            "VII/20",
            "Sh2\tRA1900\tDE1900\tDiam\t_RAJ2000\t_DEJ2000\tName",
            "101\t20:00:00\t+40:00:00\t60\t20:00:00\t+40:00:00\tNGC 7000",
            "Sh2-101",
            DsoType.BRIGHT_NEBULA,
            "HII region",
        ),
        (
            "VII/7A",
            "LDN\tRA1950\tDE1950\tArea\tOpacity\tID\tSeq\tLynds2\tBarn\t_RAJ2000\t_DEJ2000",
            "123\t20:00:00\t+40:00:00\t1.0\t3\t123\t123\t123\t168 169\t300.0\t40.0",
            "LDN 123",
            DsoType.DARK_NEBULA,
            "dark nebula",
        ),
        (
            "VII/9",
            "Seq\tRA1950\tDE1950\tDiam1\tDiam2\tArea\tName\t_RAJ2000\t_DEJ2000",
            "456\t20:00:00\t+40:00:00\t30\t20\t0.1\tIC 5070\t300.0\t40.0",
            "LBN 456",
            DsoType.BRIGHT_NEBULA,
            "bright nebula",
        ),
        (
            "VII/21",
            "VdB\t_HD\tType\tSurfBr\tBRadMax\tRRadMax\t_RAJ2000\t_DEJ2000",
            "12\t1234\tR\t2\t5\t6\t300.0\t40.0",
            "vdB 12",
            DsoType.BRIGHT_NEBULA,
            "reflection nebula",
        ),
        (
            "VII/220A",
            "Barn\tRA1875\tDE1875\tDiam\t_RAJ2000\t_DEJ2000",
            "168\t20:00:00\t+40:00:00\t30\t300.0\t40.0",
            "B 168",
            DsoType.DARK_NEBULA,
            "dark nebula",
        ),
    ],
)
def test_each_catalogue_parser_normalizes_representative_row(
    catalogue_id: str,
    header: str,
    row: str,
    designation: str,
    object_type: DsoType,
    subtype: str,
) -> None:
    objects = parse_vizier_table(
        f"# test table\n{header}\n{row}\n", catalogue_id, retrieved="2026-09-24"
    )

    assert len(objects) == 1
    obj = objects[0]
    assert obj.id == designation
    assert obj.object_type == object_type
    assert obj.semantic_subtype == subtype
    assert obj.ra_deg == pytest.approx(300.0)
    assert obj.dec_deg == pytest.approx(40.0)
    assert obj.catalogue_records[0].coordinate_frame
    assert obj.catalogue_records[0].retrieved == "2026-09-24"
    assert obj.catalogue_records[0].raw_fields


def test_catalogue_designation_formats_are_centralized() -> None:
    assert format_vizier_designation("VII/20", "101") == "Sh2-101"
    assert format_vizier_designation("VII/7A", "123") == "LDN 123"
    assert format_vizier_designation("VII/9", "456") == "LBN 456"
    assert format_vizier_designation("VII/21", "12") == "vdB 12"
    assert format_vizier_designation("VII/220A", "168") == "B 168"
    assert format_vizier_designation("VII/92A:Collinder", "399") == "Cr 399"
    assert format_vizier_designation("VII/92A:Melotte", "20") == "Mel 20"
    assert format_vizier_designation("VII/92A:Stock", "2") == "Stock 2"
    assert format_vizier_designation("IV/24:AbellPN", "Abell 39") == "Abell 39"
    assert format_vizier_designation("VII/202:Palomar", "Pal 5") == "Pal 5"
    assert format_vizier_designation("VII/202:Terzan", "Ter 7") == "Ter 7"
    assert format_vizier_designation("VII/213", "1") == "HCG 1"
    assert format_vizier_designation("VII/74A", "244") == "Arp 244"
    assert format_vizier_designation("VII/155", "NGC   891") == "NGC 891"
    assert format_vizier_designation("VII/155", "PGC009031") == "PGC 9031"


def test_rc3_log_axes_aliases_and_photometry() -> None:
    obj = parse_vizier_table(
        "name\taltname\tdesig\tPGC\tRA2000\tDE2000\t_RAJ2000\t_DEJ2000\tD25\tR25\tPA\tBT\tBT_code\tB-VT\tm'25\n"
        "NGC 891\tUGC 1831\tMCG +07-05-046\tPGC 9031\t02 22 33.4\t+42 20 57\t"
        "35.639\t42.349\t1.50\t0.30\t22\t10.8\t\t0.83\t13.2\n",
        "VII/155",
        retrieved="2026-09-27",
    )[0]
    assert obj.id == "PGC 9031"
    assert {"NGC 891", "UGC 1831", "MCG +07-05-046"} <= set(obj.cross_ids)
    assert obj.major_axis_arcmin == pytest.approx(10**1.5 / 10)
    assert obj.minor_axis_arcmin == pytest.approx((10**1.5 / 10) / 10**0.3)
    assert obj.magnitude == 10.8
    assert obj.magnitude_band == "B"
    assert obj.b_magnitude == 10.8
    assert obj.position_angle_deg == 22
    assert dict(obj.catalogue_records[0].raw_fields)["m'25"] == "13.2"


def test_rc3_blank_name_uses_pgc_and_v_coded_bt_is_not_b_magnitude() -> None:
    obj = parse_vizier_table(
        "name\taltname\tPGC\tRA2000\tDE2000\t_RAJ2000\t_DEJ2000\tBT\tBT_code\n"
        "\tUGC 12889\tPGC 2\t00 00 01.8\t+47 16 28\t0.007852\t47.274382\t14.2\tV\n",
        "VII/155",
        retrieved="2026-09-27",
    )[0]
    assert obj.id == "PGC 2"
    assert "UGC 12889" in obj.cross_ids
    assert obj.magnitude is None
    assert obj.b_magnitude is None


def test_ngc_component_suffix_remains_distinct_from_parent() -> None:
    assert canonical_designation("NGC 1023A") == "NGC1023A"
    assert canonical_designation("NGC 1023") == "NGC1023"
    assert canonical_designation("PGC 009031") == canonical_designation("PGC 9031")


@pytest.mark.parametrize(
    ("catalogue_id", "header", "row", "designation", "object_type"),
    [
        (
            "VII/92A:Collinder",
            "ClSeq\tClNum\tRA1950\tDE1950\tDiam\t_Ra.icrs\t_De.icrs",
            "6\t399\t20:00:00\t+40:00:00\t60\t300\t40",
            "Cr 399",
            DsoType.OPEN_CLUSTER,
        ),
        (
            "VII/92A:Melotte",
            "ClSeq\tClNum\tRA1950\tDE1950\tDiam\t_Ra.icrs\t_De.icrs",
            "27\t20\t20:00:00\t+40:00:00\t60\t300\t40",
            "Mel 20",
            DsoType.OPEN_CLUSTER,
        ),
        (
            "VII/92A:Stock",
            "ClSeq\tClNum\tRA1950\tDE1950\tDiam\t_Ra.icrs\t_De.icrs",
            "11\t2\t20:00:00\t+40:00:00\t60\t300\t40",
            "Stock 2",
            DsoType.OPEN_CLUSTER,
        ),
        (
            "IV/24:AbellPN",
            "Name\tPK\tf_PK\tRAB1950\tDEB1950\t_RAJ2000\t_DEJ2000",
            "A 39\t118+74.1\t*\t16:27:33\t+27:54:33\t246.3\t27.9",
            "Abell PN 39",
            DsoType.PLANETARY_NEBULA,
        ),
        (
            "VII/202:Palomar",
            "ID\tRAJ2000\tDEJ2000\t_RAJ2000\t_DEJ2000\tVt",
            "Pal 5\t15:16:05\t-00:06:41\t229.0\t-0.1\t11.8",
            "Pal 5",
            DsoType.GLOBULAR_CLUSTER,
        ),
        (
            "VII/202:Terzan",
            "ID\tRAJ2000\tDEJ2000\t_RAJ2000\t_DEJ2000\tVt",
            "Ter 7\t19:17:43\t-34:39:27\t289.4\t-34.7\t12.0",
            "Ter 7",
            DsoType.GLOBULAR_CLUSTER,
        ),
        (
            "VII/213",
            "HCG\tRA1950\tDE1950\t_RAJ2000\t_DEJ2000\tAngSize\tTotmag\tMCount",
            "92\t20:34:00\t+33:58:00\t308.5\t33.0\t4\t13.0\t4",
            "HCG 92",
            DsoType.GALAXY_CLUSTER,
        ),
        (
            "VII/74A",
            "APG\tName\tRA1970\tDE1970\t_Ra.icrs\t_De.icrs",
            "244\tNGC 4038/39\t12:01:53\t-18:52:00\t180.5\t-18.9",
            "Arp 244",
            DsoType.GALAXY,
        ),
    ],
)
def test_second_batch_catalogues_parse_to_expected_semantics(
    catalogue_id: str,
    header: str,
    row: str,
    designation: str,
    object_type: DsoType,
) -> None:
    objects = parse_vizier_table(f"{header}\n{row}\n", catalogue_id, retrieved="2026-09-24")
    assert len(objects) == 1
    assert objects[0].id == designation
    assert objects[0].object_type == object_type
    assert objects[0].catalogue_records[0].coordinate_frame


def test_abell_pn_parser_excludes_non_pn_and_keeps_pk_alias() -> None:
    rows = (
        "Name\tPK\tf_PK\tRAB1950\tDEB1950\t_RAJ2000\t_DEJ2000\n"
        "A 39\t118+74.1\t*\t16:27:33\t+27:54:33\t246.3\t27.9\n"
        "A 85\t123+12.1\tM\t18:00:00\t+10:00:00\t270\t10\n"
        "Other PN\t000+00.0\t\t00:00:00\t+00:00:00\t0\t0\n"
    )
    objects = parse_vizier_table(rows, "IV/24:AbellPN", retrieved="2026-09-24")
    assert [obj.id for obj in objects] == ["Abell PN 39"]
    assert "PK 118+74.1" in objects[0].cross_ids
    assert "Abell 39" in objects[0].cross_ids


def test_hickson_group_retains_member_relationships() -> None:
    members = {"92": ("NGC 7317", "NGC 7318A", "NGC 7318B", "NGC 7319")}
    obj = parse_vizier_table(
        "HCG\tRA1950\tDE1950\t_RAJ2000\t_DEJ2000\tMCount\n"
        "92\t20:34:00\t+33:58:00\t308.5\t33.0\t4\n",
        "VII/213",
        retrieved="2026-09-24",
        members_by_group=members,
    )[0]
    assert obj.id == "HCG 92"
    assert obj.object_type == DsoType.GALAXY_CLUSTER
    assert obj.member_designations == members["92"]


def test_hickson_group_matches_zero_padded_openngc_id_and_keeps_members() -> None:
    existing = _dso("HCG092", 339.0, dso_type=DsoType.GALAXY_CLUSTER, extent=4.4)
    group = parse_vizier_table(
        "HCG\tRA1950\tDE1950\t_RAJ2000\t_DEJ2000\tAngSize\tMCount\n"
        "92\t22:33:43\t+33:42:23\t339.0022\t33.96571\t3.2\t5\n",
        "VII/213",
        retrieved="2026-09-24",
        members_by_group={"92": ("NGC 7317", "NGC 7318A", "NGC 7318B", "NGC 7319", "NGC 7320")},
    )[0]
    result = crossmatch_vizier_objects([existing], [group])
    assert len(result.objects) == 1
    assert result.objects[0].id == "HCG092"
    assert result.counts["VII/213"]["matched_aliases"] == 1
    assert "HCG 92" in result.objects[0].cross_ids
    assert "NGC 7318B" in result.objects[0].member_designations
    assert result.objects[0].member_count == 5


def test_arp_alias_only_never_creates_unmatched_physical_objects() -> None:
    canonical = _dso("NGC 4038", 180.5, dso_type=DsoType.GALAXY, aliases=("NGC 4039",))
    arp = _vizier_record(
        _dso("Arp 244", 180.501, dso_type=DsoType.GALAXY, aliases=("NGC 4038/39",)),
        catalogue_id="VII/74A",
    )
    unmatched = _vizier_record(
        _dso("Arp 999", 40.0, dso_type=DsoType.GALAXY), catalogue_id="VII/74A"
    )
    result = crossmatch_vizier_objects([canonical], [arp, unmatched])
    assert [obj.id for obj in result.objects] == ["NGC 4038"]
    assert "Arp 244" in result.objects[0].cross_ids
    assert result.counts["VII/74A"]["matched_aliases"] == 1
    assert result.counts["VII/74A"]["unmatched_aliases"] == 1


def test_open_cluster_matching_uses_broader_but_conservative_radius() -> None:
    canonical = _dso("NGC 869", 30.0, dso_type=DsoType.OPEN_CLUSTER, extent=30)
    external = _vizier_record(
        _dso("Mel 14", 30.05, dso_type=DsoType.OPEN_CLUSTER, extent=30),
        catalogue_id="VII/92A:Melotte",
    )
    result = crossmatch_vizier_objects([canonical], [external])
    assert len(result.objects) == 1
    assert result.counts["VII/92A:Melotte"]["matched_aliases"] == 1


def test_sexagesimal_icrs_coordinate_conversion_and_original_frame_retention() -> None:
    spec = next(item for item in VIZIER_CATALOGUES if item.catalogue_id == "VII/220A")
    obj = parse_vizier_table(
        "Barn\tRA1875\tDE1875\tDiam\t_RAJ2000\t_DEJ2000\n"
        "168\t20:00:00\t-20:00:00\t30\t12:30:00\t-20:30:00\n",
        spec.catalogue_id,
        retrieved="2026-09-24",
    )[0]
    source = obj.catalogue_records[0]
    assert obj.ra_deg == pytest.approx(187.5)
    assert obj.dec_deg == pytest.approx(-20.5)
    assert source.coordinate_frame == "FK4, equinox/epoch B1875.0"
    assert source.source_ra == "20:00:00"
    assert source.source_dec == "-20:00:00"


def test_decimal_icrs_ra_below_24_hours_is_not_mistaken_for_hours() -> None:
    obj = parse_vizier_table(
        "Sh2\tRA1900\tDE1900\t_RAJ2000\t_DEJ2000\n1\t20:00:00\t+10:00:00\t10.5\t10.0\n",
        "VII/20",
        retrieved="2026-09-24",
    )[0]
    assert obj.ra_deg == pytest.approx(10.5)


def test_lynds_update_number_is_not_treated_as_global_alias() -> None:
    obj = parse_vizier_table(
        "LDN\tRA1950\tDE1950\tArea\tLynds2\tBarn\t_RAJ2000\t_DEJ2000\n"
        "935\t20:55:00\t+43:40:00\t2.25\t505\t168 169\t314.1990\t43.8599\n",
        "VII/7A",
        retrieved="2026-09-24",
    )[0]
    assert obj.cross_ids == ("B 168", "B 169")


def _dso(
    object_id: str,
    ra: float,
    *,
    dso_type: DsoType = DsoType.BRIGHT_NEBULA,
    aliases: tuple[str, ...] = (),
    extent: float = 60.0,
    source: str = "OpenNGC",
) -> DeepSkyObject:
    return DeepSkyObject(
        id=object_id,
        ra_deg=ra,
        dec_deg=0.0,
        object_type=dso_type,
        provenance=Provenance(catalogue=source, source_id=object_id),
        major_axis_arcmin=extent,
        minor_axis_arcmin=extent,
        cross_ids=aliases,
    )


def _vizier_record(obj: DeepSkyObject, *, catalogue_id: str = "VII/9") -> DeepSkyObject:
    record = CatalogSourceRecord(
        catalogue_id=catalogue_id,
        designation=obj.id,
        source_url="https://example.test/catalogue",
        reference="test-reference",
        retrieved="2026-09-24",
        coordinate_frame="B1950; test ICRS coordinate provided",
    )
    return DeepSkyObject(
        **{
            **obj.to_dict(),
            "provenance": Provenance(catalogue=catalogue_id, source_id=obj.id),
            "object_type": obj.object_type,
            "cross_ids": obj.cross_ids,
            "catalogue_records": (record,),
        }
    )


def test_openngc_lbn_cross_id_merges_to_one_physical_object() -> None:
    canonical = _dso("NGC7000", 300.0, aliases=("LBN 373", "Sh2-117"))
    external = _vizier_record(_dso("LBN 373", 300.01))

    result = crossmatch_vizier_objects([canonical], [external])

    assert len(result.objects) == 1
    assert result.counts["VII/9"]["matched_aliases"] == 1
    assert result.objects[0].id == "NGC7000"
    assert "LBN 373" in result.objects[0].cross_ids
    assert result.objects[0].catalogue_records[0].crossmatch_decision == "matched_alias"


def test_rc3_ngc_alias_merges_without_replacing_openngc_canonical() -> None:
    canonical = _dso("NGC 891", 35.639, dso_type=DsoType.GALAXY, extent=13.0)
    rc3 = parse_vizier_table(
        "name\taltname\tPGC\tRA2000\tDE2000\t_RAJ2000\t_DEJ2000\tD25\tR25\n"
        "NGC 891\tUGC 1831\tPGC 9031\t02 22 33\t+00 00 00\t35.640\t0.0\t2.0\t0.5\n",
        "VII/155",
        retrieved="2026-09-27",
    )[0]
    result = crossmatch_vizier_objects([canonical], [rc3])
    assert len(result.objects) == 1
    assert result.objects[0].id == "NGC 891"
    assert {"PGC 9031", "UGC 1831"} <= set(result.objects[0].cross_ids)
    assert result.counts["VII/155"]["matched_aliases"] == 1


def test_rc3_dense_field_does_not_merge_nearby_distinct_galaxies() -> None:
    canonical = _dso("NGC 100", 35.0, dso_type=DsoType.GALAXY, extent=1.0)
    rc3 = _vizier_record(
        _dso("PGC 999", 35.01, dso_type=DsoType.GALAXY, extent=1.0),
        catalogue_id="VII/155",
    )
    result = crossmatch_vizier_objects([canonical], [rc3])
    assert len(result.objects) == 2
    assert result.counts["VII/155"]["new_objects"] == 1


def test_rc3_conflicting_explicit_identifier_remains_uncertain() -> None:
    canonical = _dso("NGC 100", 35.0, dso_type=DsoType.GALAXY, extent=1.0)
    rc3 = _vizier_record(
        _dso("PGC 999", 36.0, dso_type=DsoType.GALAXY, aliases=("NGC 100",), extent=1.0),
        catalogue_id="VII/155",
    )
    result = crossmatch_vizier_objects([canonical], [rc3])
    assert len(result.objects) == 2
    assert result.counts["VII/155"]["uncertain"] == 1
    assert result.decisions[0]["reason"] == "explicit_identifier_coordinate_disagreement"


def test_rc3_component_name_does_not_merge_with_parent_galaxy() -> None:
    parent = _dso("NGC 1023", 35.0, dso_type=DsoType.GALAXY, extent=1.0)
    component = _vizier_record(
        _dso("PGC 10139", 35.1, dso_type=DsoType.GALAXY, aliases=("NGC 1023A",), extent=1.0),
        catalogue_id="VII/155",
    )
    result = crossmatch_vizier_objects([parent], [component])
    assert len(result.objects) == 2
    assert result.counts["VII/155"]["new_objects"] == 1


def test_nearby_distinct_dark_nebulae_remain_distinct() -> None:
    canonical = _dso("LDN 1", 300.0, dso_type=DsoType.DARK_NEBULA, extent=8.0)
    external = _vizier_record(
        _dso("B 1", 300.3, dso_type=DsoType.DARK_NEBULA, extent=8.0),
        catalogue_id="VII/220A",
    )

    result = crossmatch_vizier_objects([canonical], [external])

    assert len(result.objects) == 2
    assert result.counts["VII/220A"]["new_objects"] == 1


def test_ambiguous_positional_match_is_retained_and_reported() -> None:
    candidates = [_dso("NGC 1", 300.0), _dso("IC 1", 300.005)]
    external = _vizier_record(_dso("LBN 1", 300.002))

    result = crossmatch_vizier_objects(candidates, [external])

    assert len(result.objects) == 3
    assert result.counts["VII/9"]["uncertain"] == 1
    assert result.decisions[0]["status"] == "uncertain"


def test_extent_mismatch_prevents_confident_merge() -> None:
    canonical = _dso("NGC7000", 300.0, extent=300.0)
    nearby_subregion = _vizier_record(_dso("LBN 373", 300.0, extent=20.0))

    result = crossmatch_vizier_objects([canonical], [nearby_subregion])

    assert len(result.objects) == 2
    assert result.counts["VII/9"]["uncertain"] == 1


def test_catalogue_records_round_trip_with_processed_store(tmp_path) -> None:
    obj = _vizier_record(_dso("LBN 373", 300.0))
    path = tmp_path / "dsos.json"
    assert write_dso_catalog(path, [obj]) == 1
    loaded = load_dso_catalog(path)
    assert loaded == [obj]
    assert json.loads(path.read_text(encoding="utf-8"))[0]["catalogue_records"]


def test_cached_sources_require_manifest_and_validate_checksums(tmp_path) -> None:
    entries = []
    for spec in VIZIER_CATALOGUES:
        if spec.catalogue_id not in {"VII/20", "VII/7A", "VII/9", "VII/21", "VII/220A"}:
            continue
        path = tmp_path / f"{spec.catalogue_id.replace('/', '_')}.tsv"
        header = [
            spec.designation_field,
            spec.ra_field,
            spec.dec_field,
            spec.normalized_ra_field,
            spec.normalized_dec_field,
        ]
        row = ["1", "12:00:00", "+10:00:00", "180.0", "10.0"]
        if spec.catalogue_id == "VII/20":
            path.write_text("\t".join(header + ["Diam"]) + "\n" + "\t".join(row + ["10"]) + "\n")
        else:
            path.write_text("\t".join(header) + "\n" + "\t".join(row) + "\n")
        content = path.read_bytes()
        entries.append(
            {
                "catalogue_id": spec.catalogue_id,
                "retrieved": "2026-09-24T00:00:00+00:00",
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"catalogues": entries}), encoding="utf-8")

    objects = list(iter_vizier_objects(tmp_path))
    assert len(objects) == 5
    assert objects[0].catalogue_records[0].retrieved.startswith("2026-09-24")

    (tmp_path / "VII_20.tsv").write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum"):
        list(iter_vizier_objects(tmp_path))


def test_catalogue_inclusion_is_edition_selection_not_import_filter() -> None:
    openngc = _dso("NGC 7000", 300.0)
    imported = _vizier_record(_dso("Sh2-117", 300.01, extent=120.0), catalogue_id="VII/20")

    standard = SelectionPolicy(
        included_catalogues=frozenset({"OpenNGC"}),
        visibility=VisibilityLimits(include_all=True),
    )
    deep = SelectionPolicy(
        included_catalogues=frozenset({"OpenNGC", "VII/20"}),
        catalogue_minimum_extent_arcmin=(("VII/20", 90.0),),
        visibility=VisibilityLimits(include_all=True),
    )
    assert select_dso(imported, policy=standard).visible is False
    assert select_dso(imported, policy=deep).visible is True
    assert select_dso(openngc, policy=standard).visible is True


def test_external_catalogue_threshold_prevents_deep_include_all_from_showing_everything() -> None:
    compact_dso = _dso("LDN 1", 300.0, dso_type=DsoType.DARK_NEBULA, extent=25.0)
    extended_dso = _dso("LDN 2", 300.0, dso_type=DsoType.DARK_NEBULA, extent=120.0)
    compact = _vizier_record(compact_dso, catalogue_id="VII/7A")
    extended = _vizier_record(extended_dso, catalogue_id="VII/7A")
    policy = SelectionPolicy(
        included_catalogues=frozenset({"OpenNGC", "VII/7A"}),
        catalogue_minimum_extent_arcmin=(("VII/7A", 90.0),),
        visibility=VisibilityLimits(include_all=True),
    )

    assert select_dso(compact, policy=policy).visible is False
    assert "below-catalogue-minimum-extent" in select_dso(compact, policy=policy).visibility_reasons
    assert select_dso(extended, policy=policy).visible is True


def test_deep_hides_uncertain_crossmatch_until_reference_policy() -> None:
    source = CatalogSourceRecord(
        catalogue_id="VII/20",
        designation="Sh2-117",
        source_url="https://example.test/catalogue",
        reference="test-reference",
        retrieved="2026-09-24",
        coordinate_frame="B1900",
        crossmatch_decision="uncertain",
    )
    obj = replace(
        _dso("Sh2-117", 300.0, extent=240.0, source="VII/20"),
        catalogue_records=(source,),
    )
    deep = SelectionPolicy(
        included_catalogues=frozenset({"VII/20"}),
        catalogue_minimum_extent_arcmin=(("VII/20", 90.0),),
        visibility=VisibilityLimits(include_all=True),
    )
    reference = replace(deep, include_uncertain_catalogue_matches=True)
    unmeasured = replace(obj, major_axis_arcmin=None)
    reference = replace(
        reference,
        catalogue_minimum_extent_arcmin=(("VII/20", 0.0),),
    )

    assert select_dso(obj, policy=deep).visible is False
    assert "uncertain-catalogue-match" in select_dso(obj, policy=deep).visibility_reasons
    assert select_dso(obj, policy=reference).visible is True
    assert select_dso(unmeasured, policy=reference).visible is True
