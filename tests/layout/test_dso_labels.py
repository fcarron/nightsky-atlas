"""Tests for the deep-sky label formatting layer."""

from __future__ import annotations

import pytest

from nightsky_atlas.atlas.config import DsoLabelStyle
from nightsky_atlas.catalog.models import DeepSkyObject, DsoType, Provenance
from nightsky_atlas.layout.dso_labels import (
    DsoLabelTier,
    format_catalog_designation,
    format_dso_label,
    primary_designation,
)

STYLE = DsoLabelStyle()


def make_dso(
    object_id: str,
    *,
    cross_ids: tuple[str, ...] = (),
    common_name: str | None = None,
) -> DeepSkyObject:
    return DeepSkyObject(
        id=object_id,
        ra_deg=187.6,
        dec_deg=12.1,
        object_type=DsoType.GALAXY,
        provenance=Provenance(catalogue="TEST", source_id=object_id),
        magnitude=8.0,
        cross_ids=cross_ids,
        common_name=common_name,
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("NGC 4565", "4565"),
        ("NGC4565", "4565"),
        ("ngc 0456", "456"),
        ("NGC4411B", "4411B"),
        ("IC 3476", "I3476"),
        ("IC0001", "I1"),
        ("IC0405A", "I405A"),
        ("M87", "M87"),
        ("Messier 87", "M87"),
        ("M 42", "M42"),
        ("Sh2-101", "Sh2-101"),
        ("Sh2 101", "Sh2-101"),
        ("LDN 0123", "LDN 123"),
        ("LBN 00456", "LBN 456"),
        ("vdB 012", "vdB 12"),
        ("SH 2-155", "Sh2-155"),
        ("Sharpless 101", "Sh2-101"),
        ("Barnard 168", "B168"),
        ("B 168", "B168"),
        ("B033", "B33"),
        ("Collinder 399", "Cr 399"),
        ("Cl399", "Cr 399"),
        ("Cr 399", "Cr 399"),
        ("Melotte 111", "Mel 111"),
        ("Mel 025", "Mel 25"),
        ("Stock 2", "Stock 2"),
        ("Abell 426", "Abell 426"),
        ("HCG 92", "HCG 92"),
        ("Hickson Compact Group 92", "HCG 92"),
        ("Arp 244", "Arp 244"),
        ("C009", "C9"),
    ],
)
def test_format_catalog_designation(raw: str, expected: str) -> None:
    assert format_catalog_designation(raw) == expected


def test_format_unknown_designation_is_preserved() -> None:
    assert format_catalog_designation("ESO 056-115") == "ESO 056-115"
    assert format_catalog_designation(None) is None
    assert format_catalog_designation("  ") is None


def test_primary_designation_drops_ngc_prefix() -> None:
    assert primary_designation(make_dso("NGC4565")) == "4565"


def test_primary_designation_messier_wins_over_ngc() -> None:
    dso = make_dso("NGC4486", cross_ids=("M87",))
    assert primary_designation(dso) == "M87"


def test_primary_designation_prefers_ngc_over_ic() -> None:
    dso = make_dso("IC0001", cross_ids=("NGC1234",))
    assert primary_designation(dso) == "1234"


def test_primary_designation_uses_ic_when_no_ngc() -> None:
    assert primary_designation(make_dso("IC3476")) == "I3476"


def test_primary_designation_falls_back_to_other_catalogue() -> None:
    assert primary_designation(make_dso("Sh2-101")) == "Sh2-101"
    assert primary_designation(make_dso("Cl399")) == "Cr 399"


def test_common_name_does_not_replace_designation() -> None:
    dso = make_dso("NGC0224", cross_ids=("M31",), common_name="Andromeda Galaxy")
    assert primary_designation(dso) == "M31"


def test_ngc_label_is_normal_regular() -> None:
    result = format_dso_label(make_dso("NGC4565"), STYLE)
    assert result.text == "4565"
    assert result.tier is DsoLabelTier.NORMAL
    assert result.weight == "normal"
    assert result.size_factor == pytest.approx(1.0)


def test_herschel400_label_is_bold_normal_size() -> None:
    result = format_dso_label(make_dso("NGC4472"), STYLE, memberships=frozenset({"herschel400"}))
    assert result.text == "4472"
    assert result.tier is DsoLabelTier.HERSCHEL400
    assert result.weight == "bold"
    assert result.size_factor == pytest.approx(1.0)


def test_messier_label_is_bold_and_larger() -> None:
    dso = make_dso("NGC4486", cross_ids=("M87",))
    result = format_dso_label(dso, STYLE, memberships=frozenset({"herschel400"}))
    assert result.text == "M87"
    assert result.tier is DsoLabelTier.MESSIER
    assert result.weight == "bold"
    assert result.size_factor == pytest.approx(1.15)


def test_messier_wins_over_herschel400_tier() -> None:
    dso = make_dso("NGC4486", cross_ids=("M87",))
    result = format_dso_label(dso, STYLE, memberships=frozenset({"herschel400"}))
    assert result.tier is DsoLabelTier.MESSIER


def test_ic_label_is_normal_regular() -> None:
    result = format_dso_label(make_dso("IC3476"), STYLE)
    assert result.text == "I3476"
    assert result.weight == "normal"
    assert result.size_factor == pytest.approx(1.0)


def test_other_catalogue_labels() -> None:
    assert format_dso_label(make_dso("Sh2-101"), STYLE).text == "Sh2-101"
    assert format_dso_label(make_dso("Barnard 168"), STYLE).text == "B168"
