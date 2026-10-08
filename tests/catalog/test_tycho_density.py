"""Tests for Tycho-2 density calculations and report serialization."""

from __future__ import annotations

import csv
import json
import sqlite3

import pytest

from nightsky_atlas.catalog.tycho_density import (
    LIMITS,
    build_report,
    effective_alpha,
    spherical_rectangle_area_sq_deg,
    stars_per_cm2,
    write_csv,
    write_json,
)


@pytest.fixture
def tiny_store(tmp_path):
    path = tmp_path / "stars.sqlite"
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE stars (id TEXT, ra_deg REAL, dec_deg REAL, magnitude REAL, catalogue TEXT)"
    )
    connection.executemany(
        "INSERT INTO stars VALUES (?, ?, ?, ?, ?)",
        [
            (f"T{i}", 187.5, 12.0, mag, "TYC2")
            for i, mag in enumerate((6.0, 7.0, 7.5, 8.0, 8.5, 9.0, 9.5, 10.0, 10.5, 11.0, 11.5))
        ]
        + [("HIP", 187.5, 12.0, 1.0, "HIP")],
    )
    connection.commit()
    connection.close()
    return path


def test_cumulative_counts_monotonic_and_bins_sum(tiny_store):
    report = build_report(tiny_store)
    counts = list(report["all_sky_cumulative_counts"].values())
    assert counts == sorted(counts)
    assert sum(report["all_sky_incremental_counts"].values()) == counts[-1] - counts[0]
    assert report["source_row_counts"] == {"HIP": 1, "TYC2": 11}


def test_growth_factor_and_effective_alpha():
    assert effective_alpha(100, 200, 0.5) == pytest.approx(0.6020599913)
    report_counts = {m: 10**m for m in LIMITS}
    assert report_counts[7.5] / report_counts[7.0] == pytest.approx(3.16227766)


def test_stars_per_cm2_and_scale_normalization():
    assert stars_per_cm2(25.0, 10.0) == pytest.approx(25.0)
    assert stars_per_cm2(100.0, 20.0) == pytest.approx(stars_per_cm2(25.0, 10.0))


def test_regional_spherical_area_and_normalization(tiny_store):
    assert spherical_rectangle_area_sq_deg(20.0, -10.0, 10.0) < 400.0
    report = build_report(tiny_store)
    region = report["regions"]["virgo"]
    assert region["stars_per_sq_deg"]["7.5"] == pytest.approx(3 / region["sky_area_sq_deg"])


def test_report_outputs_are_deterministic_and_serializable(tiny_store, tmp_path):
    first, second = build_report(tiny_store), build_report(tiny_store)
    assert first == second
    json_path, csv_path = tmp_path / "report.json", tmp_path / "report.csv"
    write_json(first, json_path)
    write_csv(first, csv_path)
    assert json.loads(json_path.read_text()) == first
    with csv_path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert any(row["section"] == "growth" for row in rows)
    assert any(row["section"] == "paper_density" for row in rows)


def test_production_edition_limits_unchanged():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    assert "stellar_limit_magnitude: 9.0" in (root / "atlas/standard.yaml").read_text()
    assert "stellar_limit_magnitude: 7.5" in (root / "atlas/pocket.yaml").read_text()
    assert "stellar_limit_magnitude: 10.5" in (root / "atlas/deep.yaml").read_text()
