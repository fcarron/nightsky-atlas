from __future__ import annotations

from pathlib import Path

import pytest

from nightsky_atlas.catalog.faint_stars import (
    FaintStarStore,
    _magnitude_source_bucket,
    fit_magnitude_calibration,
    import_ucac4_faint,
    parse_ucac4_record,
)
from nightsky_atlas.catalog.models import Provenance, Star
from nightsky_atlas.catalog.store import QueryBox, build_star_store


def _put(data: bytearray, start: int, size: int, value: int) -> None:
    data[start : start + size] = value.to_bytes(size, "little", signed=True)


def _record(
    ra_deg: float,
    dec_deg: float,
    *,
    vmag: int = 13000,
    fmag: int = 12900,
    primary_flag: int = 0,
    jk_mmag: tuple[int, int] | None = None,
) -> bytes:
    data = bytearray(78)
    _put(data, 0, 4, round(ra_deg * 3_600_000))
    _put(data, 4, 4, round(dec_deg * 3_600_000 + 324_000_000))
    _put(data, 8, 2, fmag)
    _put(data, 48, 2, vmag)
    data[57] = 5
    if jk_mmag is not None:
        _put(data, 34, 2, jk_mmag[0])
        _put(data, 38, 2, jk_mmag[1])
        data[40] = 5
        data[42] = 5
    _put(data, 62, 4, primary_flag * 100_000_000)
    return bytes(data)


def _primary(path: Path, ra_deg: float, dec_deg: float) -> None:
    star = Star(
        "TYC test",
        ra_deg,
        dec_deg,
        8.0,
        Provenance("TYC2", "test"),
    )
    build_star_store(path, [star])


def test_ucac4_apass_v_preferred_and_raw_fallback_is_explicit() -> None:
    apass = parse_ucac4_record(_record(10, -20), zone=101, record_number=2)
    fallback = parse_ucac4_record(_record(10, -20, vmag=20000), zone=101, record_number=2)
    assert apass is not None and apass.atlas_magnitude == pytest.approx(13.0)
    assert apass.magnitude_source == "APASS_V"
    assert fallback is not None and fallback.atlas_magnitude == pytest.approx(12.9)
    assert fallback.magnitude_source == "UCAC_fmag_fallback"
    assert fallback.fmag == pytest.approx(12.9)
    assert fallback.apass_v is None


def test_calibration_reproducible_and_color_term_reduces_heldout_residual() -> None:
    records = []
    for number in range(1, 1001):
        fmag = 10.0 + (number % 60) / 10
        color = 0.0 + (number % 20) / 20
        vmag = round((1.0 + 0.9 * fmag + 0.3 * color) * 1000)
        data = _record(
            10 + number / 10000,
            0,
            vmag=vmag,
            fmag=round(fmag * 1000),
            jk_mmag=(round((10 + color) * 1000), 10000),
        )
        record = parse_ucac4_record(data, zone=100, record_number=number)
        assert record is not None
        records.append(record)
    first = fit_magnitude_calibration(records)
    second = fit_magnitude_calibration(records)
    assert first == second
    assert first.use_color
    assert first.color_coefficient == pytest.approx(0.3, abs=0.02)
    assert first.diagnostics["linear_fmag_plus_j_minus_ks"]["rms_residual_mag"] < 0.01
    predicted, source = first.predict(12.0, 0.5)
    assert predicted == pytest.approx(11.95, abs=0.02)
    assert source == "UCAC_fmag_color_calibrated"


def test_ucac4_parser_rejects_wrong_record_size() -> None:
    with pytest.raises(ValueError, match="78 bytes"):
        parse_ucac4_record(b"short", zone=1, record_number=1)


@pytest.mark.parametrize(
    ("source", "bucket"),
    (
        ("APASS_V", "APASS_V"),
        ("UCAC_fmag_calibrated", "calibrated_fmag"),
        ("UCAC_fmag_color_calibrated", "calibrated_fmag"),
        ("UCAC_fmag_raw_fallback", "raw_fmag_fallback"),
    ),
)
def test_magnitude_source_report_buckets(source: str, bucket: str) -> None:
    assert _magnitude_source_bucket(source) == bucket


def test_import_excludes_catalogue_primary_and_unique_positional_match(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    # one Tycho-flagged record, one positional counterpart, then a second
    # nearby UCAC detection which is preserved rather than removed twice.
    raw.joinpath("z001").write_bytes(
        _record(10, 0, primary_flag=3)
        + _record(20, 5)
        + _record(20 + 1 / 3600, 5, vmag=20000)
        + _record(40, 0, vmag=15000)
    )
    primary = tmp_path / "stars.sqlite"
    _primary(primary, 20, 5)
    output = tmp_path / "faint.sqlite"
    manifest = import_ucac4_faint(raw, output, primary_store=primary)
    assert manifest["rows_removed_ucac4_tycho_source_flags"] == 1
    assert manifest["rows_removed_ucac4_hipparcos_source_flags"] == 0
    assert manifest["rows_removed_positional_primary_crossmatch"] == 1
    assert manifest["ucac_fmag_raw_fallback_rows"] == 1
    assert manifest["magnitude_sources"]["raw_fmag_fallback"]["count"] == 1
    with FaintStarStore.open(output) as store:
        assert store.count() == 1
        assert store.cumulative_counts((12.5, 13.5, 14.0)) == {12.5: 0, 13.5: 1, 14.0: 1}


def test_query_ra_wrap_ordering_and_magnitude_cut(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    raw.joinpath("z900").write_bytes(_record(359, 0) + _record(1, 0) + _record(180, 0))
    output = tmp_path / "faint.sqlite"
    import_ucac4_faint(raw, output)
    with FaintStarStore.open(output) as store:
        stars = store.query_box(QueryBox(350, 10, -1, 1), magnitude_limit=13.0)
    assert [star.ra_deg for star in stars] == [359, 1]
    assert all(not hasattr(star, "hip_id") for star in stars)


def test_import_excludes_hipparcos_source_flag_and_retains_fk6_flag(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    raw.joinpath("z001").write_bytes(
        _record(10, 0, primary_flag=1)
        + _record(20, 0, primary_flag=7)
        + _record(30, 0, primary_flag=6)
    )
    manifest = import_ucac4_faint(raw, tmp_path / "faint.sqlite")
    assert manifest["rows_removed_ucac4_hipparcos_source_flags"] == 2
    assert manifest["rows_removed_ucac4_tycho_source_flags"] == 0
    assert manifest["final_faint_rows"] == 1


def test_ambiguous_primary_nearby_candidates_are_retained(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    raw.joinpath("z001").write_bytes(_record(20 + 0.2 / 3600, 5))
    primary = tmp_path / "stars.sqlite"
    build_star_store(
        primary,
        [
            Star("TYC left", 20, 5, 8, Provenance("TYC2", "test")),
            Star("TYC right", 20 + 0.4 / 3600, 5, 8, Provenance("TYC2", "test")),
        ],
    )
    manifest = import_ucac4_faint(raw, tmp_path / "faint.sqlite", primary_store=primary)
    assert manifest["ambiguous_positional_candidates_retained"] == 1
    assert manifest["final_faint_rows"] == 1


def test_one_primary_does_not_remove_two_close_ucac_detections(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    raw.joinpath("z001").write_bytes(_record(20 + 0.1 / 3600, 5) + _record(20 + 0.2 / 3600, 5))
    primary = tmp_path / "stars.sqlite"
    _primary(primary, 20, 5)
    manifest = import_ucac4_faint(raw, tmp_path / "faint.sqlite", primary_store=primary)
    assert manifest["rows_removed_positional_primary_crossmatch"] == 1
    assert manifest["ucac4_rows_retained_within_2_arcsec_of_primary"] == 1
    assert manifest["final_faint_rows"] == 1
