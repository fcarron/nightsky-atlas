"""Tests for sky tiling (declination rings and legacy bands)."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from nightsky_atlas.atlas.config import load_atlas_config
from nightsky_atlas.atlas.tiling import (
    TilingSpec,
    coverage_report,
    neighbour_overlap_report,
    resolve_ring_counts,
    tile_sky,
    with_neighbours,
)
from nightsky_atlas.chart.models import ChartDefinition

REPO_ROOT = Path(__file__).resolve().parents[2]
ATLAS = REPO_ROOT / "atlas" / "standard.yaml"


def standard_spec() -> TilingSpec:
    config = load_atlas_config(ATLAS)
    assert config.tiling is not None
    return TilingSpec.from_config(config.tiling)


def ring_spec(**overrides: object) -> TilingSpec:
    params: dict[str, object] = {
        "width_deg": 27.0,
        "height_deg": 18.5,
        "declination_centers": (-72.0, -56.0, -40.0, -24.0, -8.0, 8.0, 24.0, 40.0, 56.0, 72.0),
        "chart_counts": (5, 8, 11, 13, 14, 14, 13, 11, 8, 5),
        "polar_caps": True,
        "stagger_ra_centers": True,
        "auto_adjust_counts": True,
    }
    params.update(overrides)
    return TilingSpec(**params)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"width_deg": 0.0, "height_deg": 18.5, "overlap_deg": 3.0},
        {"width_deg": 27.0, "height_deg": 18.5, "overlap_deg": 0.0},
        {"width_deg": 27.0, "height_deg": 18.5, "overlap_deg": 20.0},
        {"width_deg": 27.0, "height_deg": 18.5},
    ],
)
def test_invalid_spec_rejected(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        TilingSpec(**kwargs)


def test_ring_spec_requires_centre_inside_poles() -> None:
    with pytest.raises(ValueError):
        ring_spec(declination_centers=(90.0,), chart_counts=(1,))


def test_ring_spec_counts_must_match_centres() -> None:
    with pytest.raises(ValueError):
        ring_spec(chart_counts=(1, 2))


def test_resolve_ring_counts_raises_start_values() -> None:
    spec = ring_spec()
    assert resolve_ring_counts(spec) == (10, 10, 12, 13, 14, 14, 13, 12, 10, 10)


def test_ring_counts_follow_their_centres_when_unsorted() -> None:
    # chart_counts is parallel to declination_centers, which need not be
    # ascending; sorting the centres must not shuffle the counts.
    spec = ring_spec(
        declination_centers=(24.0, -24.0),
        chart_counts=(3, 7),
        polar_caps=False,
        auto_adjust_counts=False,
    )
    assert resolve_ring_counts(spec) == (7, 3)


def test_resolve_ring_counts_respects_auto_adjust_off() -> None:
    spec = ring_spec(auto_adjust_counts=False)
    assert resolve_ring_counts(spec) == (5, 8, 11, 13, 14, 14, 13, 11, 8, 5)


def test_tile_sky_is_deterministic_and_unique() -> None:
    spec = standard_spec()
    first = tile_sky("standard", spec)
    second = tile_sky("standard", spec)
    assert [chart.id for chart in first] == [chart.id for chart in second]
    assert len({chart.id for chart in first}) == len(first)
    assert len(first) > 50
    assert first[0].id == "standard-001"


def test_ring_tiling_has_polar_caps_and_aligned_ra_centres() -> None:
    charts = tile_sky("standard", standard_spec())
    assert len(charts) == 129
    assert charts[0].center_dec_deg == pytest.approx(90.0)
    assert charts[-1].center_dec_deg == pytest.approx(-90.0)
    rings = {chart.center_dec_deg for chart in charts}
    assert set(range(-75, 76, 15)) <= rings
    by_dec = {
        dec: [chart.center_ra_deg for chart in charts if chart.center_dec_deg == dec]
        for dec in rings
        if abs(dec) < 89.0
    }
    assert by_dec[-75.0] == pytest.approx(by_dec[75.0])
    assert by_dec[-45.0] == pytest.approx(by_dec[45.0])
    assert by_dec[-15.0] == pytest.approx(by_dec[15.0])


def test_ra_offset_rotates_every_ring_and_polar_cap_without_changing_coverage() -> None:
    atlas = load_atlas_config(ATLAS)
    assert atlas.tiling is not None
    base = TilingSpec.from_config(atlas.tiling.model_copy(update={"ra_offset_deg": 0.0}))
    shifted = TilingSpec.from_config(atlas.tiling)
    base_charts = tile_sky("standard", base)
    shifted_charts = tile_sky("standard", shifted)

    assert len(shifted_charts) == len(base_charts) == 129
    assert [chart.center_dec_deg for chart in shifted_charts] == [
        chart.center_dec_deg for chart in base_charts
    ]
    for original, rotated in zip(base_charts, shifted_charts, strict=True):
        assert rotated.center_ra_deg == pytest.approx(
            (original.center_ra_deg + 12.0) % 360.0
        )
    report = coverage_report(shifted_charts, step_deg=1.0)
    assert report.covers_all, report.gaps[:5]


def test_atlas_order_runs_north_to_south_and_westward_from_each_ra_anchor() -> None:
    spec = ring_spec(ra_offset_deg=23.0)
    charts = tile_sky("standard", spec)
    declinations = [chart.center_dec_deg for chart in charts]
    assert declinations[0] == pytest.approx(90.0)
    assert declinations[-1] == pytest.approx(-90.0)
    # Declination is non-increasing from north to south (caps at the ends).
    assert all(
        later <= earlier + 1e-9
        for earlier, later in zip(declinations, declinations[1:], strict=False)
    )
    # Within each ring the RA anchor stays first, then chart numbers proceed
    # westward (decreasing RA), wrapping continuously through 0h.
    ring_centers = {
        chart.center_dec_deg for chart in charts if abs(chart.center_dec_deg) < 89.0
    }
    counts = dict(zip(sorted(spec.declination_centers), resolve_ring_counts(spec), strict=True))
    for ring_index, center in enumerate(sorted(ring_centers)):
        ring = [chart for chart in charts if chart.center_dec_deg == center]
        ras = [chart.center_ra_deg for chart in ring]
        count = counts[center]
        phase = 0.5 if spec.stagger_ra_centers and ring_index % 2 == 1 else 0.0
        anchor = (spec.ra_offset_deg + phase * 360.0 / count) % 360.0
        expected = [(anchor - index * 360.0 / count) % 360.0 for index in range(count)]
        assert ras == pytest.approx(expected)


@pytest.mark.parametrize(
    ("edition", "expected_count"),
    (("pocket", 39), ("standard", 129), ("deep", 492)),
)
def test_main_editions_keep_geometry_counts_and_westward_neighbours(
    edition: str, expected_count: int
) -> None:
    atlas = load_atlas_config(REPO_ROOT / "atlas" / f"{edition}.yaml")
    assert atlas.tiling is not None
    spec = TilingSpec.from_config(atlas.tiling)
    charts = with_neighbours(tile_sky(edition, spec))
    assert len(charts) == expected_count
    assert charts[0].center_dec_deg == pytest.approx(90.0)
    assert charts[-1].center_dec_deg == pytest.approx(-90.0)
    assert len({chart.id for chart in charts}) == expected_count

    bands = sorted({chart.center_dec_deg for chart in charts})
    for dec in bands:
        if abs(dec) >= 89.0:
            continue
        ring = [chart for chart in charts if chart.center_dec_deg == dec]
        if len(ring) < 2:
            continue
        by_id = {chart.id: dict(chart.neighbours) for chart in ring}
        for index, chart in enumerate(ring):
            assert by_id[chart.id]["W"] == ring[(index + 1) % len(ring)].id
            assert by_id[chart.id]["E"] == ring[(index - 1) % len(ring)].id


def test_frozen_ring_counts_match_declination_rings() -> None:
    spec = standard_spec()
    charts = tile_sky("standard", spec)
    per_ring: dict[float, int] = {}
    for chart in charts:
        per_ring[chart.center_dec_deg] = per_ring.get(chart.center_dec_deg, 0) + 1
    assert [per_ring[dec] for dec in (75, 60, 45, 30, 15, 0, -15, -30, -45, -60, -75)] == [
        5,
        10,
        11,
        15,
        15,
        15,
        15,
        15,
        11,
        10,
        5,
    ]
    assert per_ring[90.0] == 1
    assert per_ring[-90.0] == 1


def test_tiling_covers_sky_with_overlap() -> None:
    charts = tile_sky("standard", standard_spec())
    report = coverage_report(charts, step_deg=1.0)
    assert report.covers_all, report.gaps[:5]
    assert report.has_overlap
    assert report.min_overlap >= 1
    assert report.max_overlap >= 2


def test_neighbours_reference_existing_charts() -> None:
    charts = with_neighbours(tile_sky("standard", standard_spec()))
    ids = {chart.id for chart in charts}
    directions_seen: set[str] = set()
    for chart in charts:
        present = {direction for direction, _ in chart.neighbours}
        if abs(chart.center_dec_deg) < 89.0:
            assert {"E", "W"} <= present
        for direction, neighbour_id in chart.neighbours:
            assert direction in {"N", "S", "E", "W"}
            assert neighbour_id in ids
            directions_seen.add(direction)
    assert {"N", "S"} <= directions_seen


def test_polar_caps_navigate_to_surrounding_charts_on_all_edges() -> None:
    charts = with_neighbours(tile_sky("standard", standard_spec()))
    for chart in charts:
        if abs(chart.center_dec_deg) >= 89.0:
            directions = {direction for direction, _ in chart.neighbours}
            assert directions == {"N", "E", "S", "W"}
            assert len({neighbour for _, neighbour in chart.neighbours}) >= 3


def test_east_west_neighbours_are_symmetric() -> None:
    charts = {chart.id: chart for chart in with_neighbours(tile_sky("standard", standard_spec()))}
    for chart in charts.values():
        if abs(chart.center_dec_deg) >= 89.0:
            continue
        neighbours = dict(chart.neighbours)
        if "E" not in neighbours:
            continue
        east = charts[neighbours["E"]]
        assert dict(east.neighbours)["W"] == chart.id


def test_declared_neighbours_share_covered_sky() -> None:
    charts = with_neighbours(tile_sky("standard", standard_spec()))
    report = neighbour_overlap_report(charts, step_deg=1.0)
    assert report.checked_pairs > 0
    assert report.is_complete, report.missing_overlaps[:5]


def test_multiple_edge_neighbours_are_bounded_and_only_used_across_bands() -> None:
    charts = with_neighbours(tile_sky("standard", standard_spec()))
    multiple = 0
    for chart in charts:
        counts = Counter(direction for direction, _ in chart.neighbours)
        assert all(count <= 3 for count in counts.values())
        assert counts["E"] <= 1
        assert counts["W"] <= 1
        multiple += sum(count > 1 for direction, count in counts.items() if direction in {"N", "S"})
    assert multiple > 0


def test_cygnus_chart_gets_two_meaningful_southern_handoffs() -> None:
    charts = {chart.id: chart for chart in with_neighbours(tile_sky("standard", standard_spec()))}
    south = [
        neighbour
        for direction, neighbour in charts["standard-019"].neighbours
        if direction == "S"
    ]
    assert set(south) == {"standard-030", "standard-031"}


def test_wide_edge_can_select_three_ordered_handoffs() -> None:
    charts = (
        ChartDefinition("source", 0.0, 0.0, 90.0, 20.0),
        ChartDefinition("north-west", 330.0, 15.0, 40.0, 20.0),
        ChartDefinition("north-middle", 0.0, 15.0, 40.0, 20.0),
        ChartDefinition("north-east", 30.0, 15.0, 40.0, 20.0),
    )
    source = next(chart for chart in with_neighbours(charts) if chart.id == "source")
    assert source.neighbours == (
        ("N", "north-east"),
        ("N", "north-middle"),
        ("N", "north-west"),
    )


def test_legacy_band_mode_still_tiles() -> None:
    spec = TilingSpec(width_deg=27.0, height_deg=18.5, overlap_deg=3.0)
    charts = tile_sky("legacy", spec)
    assert len(charts) > 50
    report = coverage_report(charts, step_deg=5.0)
    assert report.covers_all


def test_legacy_band_mode_runs_north_to_south() -> None:
    spec = TilingSpec(width_deg=13.5, height_deg=9.0, overlap_deg=0.5)
    charts = tile_sky("legacy", spec)
    declinations = [chart.center_dec_deg for chart in charts]
    assert declinations == sorted(declinations, reverse=True)
    assert declinations[0] > 0.0
    assert declinations[-1] < 0.0
    for center in sorted(set(declinations)):
        ras = [chart.center_ra_deg for chart in charts if chart.center_dec_deg == center]
        assert ras == sorted(ras)
