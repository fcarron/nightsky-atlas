"""Tests for the SQLite star store."""

from __future__ import annotations

import math
import sqlite3
from pathlib import Path

import pytest

from nightsky_atlas.catalog.models import Provenance, Star
from nightsky_atlas.catalog.store import (
    QueryBox,
    StarStore,
    build_star_store,
    chart_query_box,
)
from nightsky_atlas.chart.models import ChartDefinition


def make_star(
    star_id: str, ra_deg: float, dec_deg: float, magnitude: float, hip_id: str | None = None
) -> Star:
    return Star(
        id=star_id,
        ra_deg=ra_deg,
        dec_deg=dec_deg,
        magnitude=magnitude,
        provenance=Provenance(catalogue="TEST", source_id=star_id, version="1"),
        hip_id=hip_id,
    )


@pytest.fixture
def store_path(tmp_path: Path) -> Path:
    stars = [
        make_star("s1", 10.0, 5.0, 4.0),
        make_star("s2", 20.0, 6.0, 8.0),
        make_star("s3", 350.0, 5.0, 9.0),
        make_star("s4", 5.0, -10.0, 11.0),
    ]
    path = tmp_path / "stars.sqlite"
    build_star_store(path, stars)
    return path


def test_build_and_count(store_path: Path) -> None:
    with StarStore.open(store_path) as store:
        assert store.count() == 4


def test_query_region_without_wrap(store_path: Path) -> None:
    with StarStore.open(store_path) as store:
        box = QueryBox(ra_min_deg=0.0, ra_max_deg=30.0, dec_min_deg=0.0, dec_max_deg=10.0)
        found = {star.id for star in store.query_box(box)}
    assert found == {"s1", "s2"}


def test_query_region_with_ra_wrap(store_path: Path) -> None:
    with StarStore.open(store_path) as store:
        box = QueryBox(ra_min_deg=340.0, ra_max_deg=15.0, dec_min_deg=0.0, dec_max_deg=10.0)
        found = {star.id for star in store.query_box(box)}
    assert found == {"s1", "s3"}


def test_query_respects_magnitude_limit(store_path: Path) -> None:
    with StarStore.open(store_path) as store:
        box = QueryBox(ra_min_deg=0.0, ra_max_deg=360.0, dec_min_deg=-90.0, dec_max_deg=90.0)
        found = {star.id for star in store.query_box(box, magnitude_limit=5.0)}
    assert found == {"s1"}


def test_query_is_ordered_by_stable_id(tmp_path: Path) -> None:
    stars = [
        make_star("s9", 10.0, 5.0, 4.0),
        make_star("s1", 11.0, 5.0, 4.0),
        make_star("s5", 12.0, 5.0, 4.0),
    ]
    path = tmp_path / "ordered.sqlite"
    build_star_store(path, stars)
    with StarStore.open(path) as store:
        box = QueryBox(ra_min_deg=0.0, ra_max_deg=360.0, dec_min_deg=-90.0, dec_max_deg=90.0)
        ids = [star.id for star in store.query_box(box)]
    assert ids == ["s1", "s5", "s9"]


def test_star_round_trips_through_store(store_path: Path) -> None:
    with StarStore.open(store_path) as store:
        box = QueryBox(ra_min_deg=0.0, ra_max_deg=30.0, dec_min_deg=0.0, dec_max_deg=10.0)
        star = next(item for item in store.query_box(box) if item.id == "s1")
    assert star.provenance.catalogue == "TEST"
    assert star.provenance.version == "1"


def test_hip_id_round_trips_through_store(tmp_path: Path) -> None:
    stars = [make_star("TYC 1-8-1", 10.0, 5.0, 4.0, hip_id="HIP 565")]
    path = tmp_path / "hip.sqlite"
    build_star_store(path, stars)
    with StarStore.open(path) as store:
        star = store.query_box(
            QueryBox(ra_min_deg=0.0, ra_max_deg=30.0, dec_min_deg=0.0, dec_max_deg=10.0)
        )[0]
    assert star.hip_id == "HIP 565"


def test_missing_store_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        StarStore.open(tmp_path / "missing.sqlite")


def test_chart_query_box_equatorial() -> None:
    definition = ChartDefinition(
        id="c", center_ra_deg=187.5, center_dec_deg=12.0, width_deg=20.0, height_deg=14.0
    )
    box = chart_query_box(definition, padding_deg=2.0)
    radius = math.hypot(definition.width_deg / 2.0, definition.height_deg / 2.0) + 2.0
    assert box.dec_min_deg == pytest.approx(12.0 - radius)
    assert box.dec_max_deg == pytest.approx(12.0 + radius)
    assert not box.wraps_ra
    worst_dec = max(abs(box.dec_min_deg), abs(box.dec_max_deg))
    half_width = radius / math.cos(math.radians(worst_dec))
    assert box.ra_min_deg == pytest.approx(187.5 - half_width)
    assert box.ra_max_deg == pytest.approx(187.5 + half_width)


def test_chart_query_box_reaches_projected_polar_corners() -> None:
    definition = ChartDefinition(
        id="p", center_ra_deg=0.0, center_dec_deg=90.0, width_deg=54.0, height_deg=36.0
    )
    box = chart_query_box(definition, padding_deg=0.0)
    corner_radius = math.hypot(definition.width_deg / 2.0, definition.height_deg / 2.0)
    assert box.ra_min_deg == 0.0
    assert box.ra_max_deg == 360.0
    assert box.dec_min_deg == pytest.approx(90.0 - corner_radius)
    assert box.dec_max_deg == 90.0


def test_chart_query_box_near_pole_uses_full_ra() -> None:
    definition = ChartDefinition(
        id="p", center_ra_deg=0.0, center_dec_deg=89.0, width_deg=20.0, height_deg=14.0
    )
    box = chart_query_box(definition)
    assert box.ra_min_deg == 0.0
    assert box.ra_max_deg == 360.0


def _index_names(path: Path) -> set[str]:
    connection = sqlite3.connect(path)
    try:
        return {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
            if not str(row[0]).startswith("sqlite_autoindex")
        }
    finally:
        connection.close()


def test_build_creates_combined_index(store_path: Path) -> None:
    assert _index_names(store_path) == {"stars_dec_mag_ra_idx"}


def test_reindex_is_idempotent_and_drops_legacy(store_path: Path) -> None:
    connection = sqlite3.connect(store_path)
    try:
        connection.execute("CREATE INDEX stars_ra_idx ON stars(ra_deg)")
        connection.commit()
    finally:
        connection.close()
    with StarStore.open(store_path) as store:
        store.reindex()
        store.reindex()
    assert _index_names(store_path) == {"stars_dec_mag_ra_idx"}
