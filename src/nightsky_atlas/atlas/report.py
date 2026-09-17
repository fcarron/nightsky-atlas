"""Automatic draft evaluation for a tiled atlas.

After a build, this module turns the tiling and the per-page diagnostics into a
compact review report: coverage, overlap, density outliers, neighbour-reference
problems and a region checklist (``AGENTS.md`` M16.2 groundwork).  It is a
diagnostic only and never changes the atlas.
"""

from __future__ import annotations

import statistics
from pathlib import Path
from typing import Any

from nightsky_atlas.astronomy.angles import angular_separation_deg
from nightsky_atlas.atlas.config import AtlasConfig, load_atlas_config
from nightsky_atlas.atlas.tiling import (
    TilingSpec,
    coverage_report,
    neighbour_overlap_report,
    resolve_ring_counts,
    tile_sky,
    with_neighbours,
)
from nightsky_atlas.chart.models import ChartDefinition

__all__ = [
    "REVIEW_REGIONS",
    "build_draft_report",
    "render_text_summary",
]

# Named regions to call out for visual review (name, ra_deg, dec_deg).
REVIEW_REGIONS: tuple[tuple[str, float, float], ...] = (
    ("Virgo Cluster", 187.7, 12.4),
    ("Cygnus", 305.0, 40.0),
    ("Sagittarius / Scutum", 283.0, -25.0),
    ("Orion", 83.5, -1.0),
    ("Large Magellanic Cloud", 80.9, -69.8),
    ("Small Magellanic Cloud", 13.2, -72.8),
    ("North Pole", 0.0, 90.0),
    ("South Pole", 0.0, -90.0),
)


def _nearest_chart(
    charts: tuple[ChartDefinition, ...], ra_deg: float, dec_deg: float
) -> ChartDefinition:
    return min(
        charts,
        key=lambda chart: angular_separation_deg(
            ra_deg, dec_deg, chart.center_ra_deg, chart.center_dec_deg
        ),
    )


def _density_summary(pages: list[dict[str, Any]]) -> dict[str, Any]:
    """Flag pages whose content density is unusually high or low."""

    def values(key: str) -> list[float]:
        return [float(page.get(key, 0)) for page in pages]

    summary: dict[str, Any] = {}
    for key in ("star_count", "dso_count", "label_count"):
        data = values(key)
        if not data:
            summary[key] = {
                "mean": 0.0,
                "max": 0.0,
                "min": 0.0,
                "high": [],
                "low": [],
                "highest_pages": [],
                "lowest_pages": [],
            }
            continue
        mean = statistics.fmean(data)
        stdev = statistics.pstdev(data)
        threshold_high = mean + 2.0 * stdev if stdev > 0.0 else mean
        threshold_low = mean - 2.0 * stdev if stdev > 0.0 else mean
        ranked = sorted(pages, key=lambda page: float(page.get(key, 0)))
        summary[key] = {
            "mean": round(mean, 2),
            "max": round(max(data), 2),
            "min": round(min(data), 2),
            "high": [
                page["chart_id"]
                for page in pages
                if float(page.get(key, 0)) >= threshold_high
            ],
            "low": [
                page["chart_id"]
                for page in pages
                if float(page.get(key, 0)) <= threshold_low
            ],
            "highest_pages": [page["chart_id"] for page in ranked[-5:][::-1]],
            "lowest_pages": [page["chart_id"] for page in ranked[:5]],
        }
    return summary


def build_draft_report(
    *,
    atlas_path: str | Path,
    pages: list[dict[str, Any]] | None = None,
    coverage_step_deg: float | None = None,
) -> dict[str, Any]:
    """Build a full-sky draft report from an atlas definition and page data."""
    atlas: AtlasConfig = load_atlas_config(atlas_path)
    if atlas.tiling is None:
        raise ValueError(f"atlas {atlas.id!r} has no tiling section")
    spec = TilingSpec.from_config(atlas.tiling)
    step = coverage_step_deg if coverage_step_deg is not None else spec.coverage_step_deg

    charts = with_neighbours(tile_sky(atlas.id, spec))
    coverage = coverage_report(charts, step_deg=step)
    neighbours = neighbour_overlap_report(charts, step_deg=min(step, 0.5))

    chart_ids = {chart.id for chart in charts}
    neighbour_reference_problems: list[dict[str, str]] = []
    for chart in charts:
        for direction, neighbour_id in chart.neighbours:
            if neighbour_id not in chart_ids:
                neighbour_reference_problems.append(
                    {"chart_id": chart.id, "direction": direction, "neighbour_id": neighbour_id}
                )
    for chart_id, direction in neighbours.missing_overlaps:
        neighbour_reference_problems.append(
            {"chart_id": chart_id, "direction": direction, "neighbour_id": "no-overlap"}
        )

    by_dec: dict[float, int] = {}
    for chart in charts:
        by_dec[chart.center_dec_deg] = by_dec.get(chart.center_dec_deg, 0) + 1

    regions = []
    for name, ra_deg, dec_deg in REVIEW_REGIONS:
        chart = _nearest_chart(charts, ra_deg, dec_deg)
        regions.append(
            {
                "name": name,
                "ra_deg": ra_deg,
                "dec_deg": dec_deg,
                "chart_id": chart.id,
                "chart_center_ra_deg": chart.center_ra_deg,
                "chart_center_dec_deg": chart.center_dec_deg,
            }
        )

    report: dict[str, Any] = {
        "atlas_id": atlas.id,
        "chart_count": len(charts),
        "chart_order": "north-to-south",
        "charts_per_declination": {
            f"{dec:+.0f}": count
            for dec, count in sorted(by_dec.items(), reverse=True)
        },
        "polar_charts": [
            chart.id
            for chart in sorted(charts, key=lambda item: item.center_dec_deg, reverse=True)
            if abs(chart.center_dec_deg) >= 89.0
        ],
        "coverage": {
            "step_deg": step,
            "sample_count": coverage.sample_count,
            "gap_count": coverage.gap_count,
            "covers_all": coverage.covers_all,
            "min_overlap": coverage.min_overlap,
            "max_overlap": coverage.max_overlap,
            "overlap_histogram": dict(coverage.overlap_histogram),
            "single_overlap_count": coverage.single_overlap_count,
            "sample_gaps": [list(gap) for gap in coverage.gaps[:20]],
        },
        "neighbours": {
            "checked_pairs": neighbours.checked_pairs,
            "missing_overlaps": len(neighbours.missing_overlaps),
            "problems": neighbour_reference_problems[:50],
        },
        "density": _density_summary(pages or []),
        "review_regions": regions,
    }
    if atlas.tiling is not None and spec.is_ring_mode:
        centers = sorted(spec.declination_centers, reverse=True)
        counts = resolve_ring_counts(spec)
        ascending = dict(
            zip(sorted(spec.declination_centers), counts, strict=True)
        )
        report["ring_layout"] = [
            {
                "center_dec_deg": center,
                "chart_count": ascending[center],
                "ra_step_deg": round(360.0 / ascending[center], 3),
            }
            for center in centers
        ]
    return report


def render_text_summary(report: dict[str, Any]) -> str:
    """Render a compact human-readable draft summary."""
    coverage = report["coverage"]
    lines = [
        f"atlas: {report['atlas_id']}",
        f"charts: {report['chart_count']}",
        "charts per declination: "
        + ", ".join(f"{dec}={count}" for dec, count in report["charts_per_declination"].items()),
        "coverage: "
        f"{coverage['sample_count']} samples at {coverage['step_deg']} deg, "
        f"gaps={coverage['gap_count']}, "
        f"overlap {coverage['min_overlap']}..{coverage['max_overlap']}",
    ]
    for ring in report.get("ring_layout", []):
        lines.append(
            f"  ring dec {ring['center_dec_deg']:+.0f}: "
            f"{ring['chart_count']} charts, RA step {ring['ra_step_deg']:.2f} deg"
        )
    lines.append(
        "neighbours: "
        f"{report['neighbours']['checked_pairs']} pairs checked, "
        f"{report['neighbours']['missing_overlaps']} without overlap"
    )
    density = report.get("density", {})
    for key in ("dso_count", "label_count", "star_count"):
        entry = density.get(key)
        if not entry:
            continue
        lines.append(
            f"{key}: mean {entry['mean']}, max {entry['max']}, min {entry['min']} "
            f"(densest: {', '.join(entry['highest_pages']) or 'n/a'})"
        )
    lines.append("review regions:")
    for region in report["review_regions"]:
        lines.append(
            f"  {region['name']}: {region['chart_id']} "
            f"(RA {region['chart_center_ra_deg']:.1f}, Dec {region['chart_center_dec_deg']:+.1f})"
        )
    if report["neighbours"]["problems"]:
        lines.append("neighbour problems:")
        for problem in report["neighbours"]["problems"]:
            lines.append(
                f"  {problem['chart_id']} {problem['direction']} -> {problem['neighbour_id']}"
            )
    return "\n".join(lines)
