"""Tests for declination-band sky tiling."""

from __future__ import annotations

from pathlib import Path

import pytest

from nightsky_atlas.atlas.config import load_atlas_config
from nightsky_atlas.atlas.tiling import (
    TilingSpec,
    coverage_report,
    tile_sky,
    with_neighbours,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ATLAS = REPO_ROOT / "atlas" / "standard.yaml"


def standard_spec() -> TilingSpec:
    config = load_atlas_config(ATLAS)
    assert config.tiling is not None
    return TilingSpec.from_config(config.tiling)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"width_deg": 0.0, "height_deg": 18.5, "overlap_deg": 3.0},
        {"width_deg": 27.0, "height_deg": 18.5, "overlap_deg": 0.0},
        {"width_deg": 27.0, "height_deg": 18.5, "overlap_deg": 20.0},
    ],
)
def test_invalid_spec_rejected(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        TilingSpec(**kwargs)


def test_tile_sky_is_deterministic_and_unique() -> None:
    spec = standard_spec()
    first = tile_sky("standard", spec)
    second = tile_sky("standard", spec)
    assert [chart.id for chart in first] == [chart.id for chart in second]
    assert len({chart.id for chart in first}) == len(first)
    assert len(first) > 50
    assert first[0].id == "standard-001"


def test_tiling_covers_sky_with_overlap() -> None:
    charts = tile_sky("standard", standard_spec())
    report = coverage_report(charts, step_deg=5.0)
    assert report.covers_all, report.gaps[:5]
    assert report.has_overlap
    assert report.max_overlap >= 2


def test_neighbours_reference_existing_charts() -> None:
    charts = with_neighbours(tile_sky("standard", standard_spec()))
    ids = {chart.id for chart in charts}
    directions_seen: set[str] = set()
    for chart in charts:
        present = {direction for direction, _ in chart.neighbours}
        assert {"E", "W"} <= present  # every band is a ring
        for direction, neighbour_id in chart.neighbours:
            assert direction in {"N", "S", "E", "W"}
            assert neighbour_id in ids
            directions_seen.add(direction)
    assert {"N", "S"} <= directions_seen  # interior bands have both


def test_east_west_neighbours_are_symmetric() -> None:
    charts = {chart.id: chart for chart in with_neighbours(tile_sky("standard", standard_spec()))}
    for chart in charts.values():
        neighbours = dict(chart.neighbours)
        east = charts[neighbours["E"]]
        assert dict(east.neighbours)["W"] == chart.id