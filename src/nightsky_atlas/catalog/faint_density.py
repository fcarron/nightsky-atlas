"""Regional count and paper-density reports for the optional UCAC4 layer."""

from __future__ import annotations

import math
import sqlite3
import time
import tracemalloc
from pathlib import Path
from typing import Any

from nightsky_atlas.catalog.faint_stars import FaintStarStore
from nightsky_atlas.catalog.store import QueryBox
from nightsky_atlas.catalog.tycho_density import (
    REGION_HEIGHT_DEG,
    REGION_WIDTH_DEG,
    REGIONS,
    spherical_rectangle_area_sq_deg,
    stars_per_cm2,
)

LIMITS = (12.0, 12.5, 13.0, 13.5, 14.0)
ATLAS_CASES = {
    "40mm@12.0": (40.0, 12.0),
    "40mm@12.5": (40.0, 12.5),
    "40mm@13.0": (40.0, 13.0),
    "80mm@13.0": (80.0, 13.0),
    "80mm@13.5": (80.0, 13.5),
    "80mm@14.0": (80.0, 14.0),
}


def _count(
    connection: sqlite3.Connection,
    table: str,
    limit: float,
    ra_min: float,
    ra_max: float,
    dec_min: float,
    dec_max: float,
) -> int:
    ra_filter = (
        "(ra_deg>=? OR ra_deg<=?)" if ra_min % 360 > ra_max % 360 else "ra_deg>=? AND ra_deg<=?"
    )
    params = (limit, dec_min, dec_max, ra_min % 360, ra_max % 360)
    return int(
        connection.execute(
            f"SELECT COUNT(*) FROM {table} WHERE magnitude<=? "
            f"AND dec_deg>=? AND dec_deg<=? AND {ra_filter}",
            params,
        ).fetchone()[0]
    )


def build_faint_density_report(faint_path: str | Path, primary_path: str | Path) -> dict[str, Any]:
    """Count primary plus faint stars and normalize density to chart paper."""
    primary = sqlite3.connect(primary_path)
    faint = sqlite3.connect(faint_path)
    try:
        regions: dict[str, Any] = {}
        for name, center in REGIONS.items():
            dec_min = max(-90.0, center["center_dec_deg"] - REGION_HEIGHT_DEG / 2)
            dec_max = min(90.0, center["center_dec_deg"] + REGION_HEIGHT_DEG / 2)
            ra_min = center["center_ra_deg"] - REGION_WIDTH_DEG / 2
            ra_max = center["center_ra_deg"] + REGION_WIDTH_DEG / 2
            area = spherical_rectangle_area_sq_deg(REGION_WIDTH_DEG, dec_min, dec_max)
            counts: dict[str, int] = {}
            for limit in LIMITS:
                counts[f"{limit:.1f}"] = _count(
                    primary, "stars", limit, ra_min, ra_max, dec_min, dec_max
                ) + _count(faint, "faint_stars", limit, ra_min, ra_max, dec_min, dec_max)
            regions[name] = {
                "sky_area_sq_deg": area,
                "cumulative_counts": counts,
                "stars_per_sq_deg": {key: value / area for key, value in counts.items()},
            }
        all_sky_area = 4 * math.pi * (180 / math.pi) ** 2
        all_sky = {
            f"{limit:.1f}": int(
                primary.execute(
                    "SELECT COUNT(*) FROM stars WHERE magnitude<=?", (limit,)
                ).fetchone()[0]
            )
            + int(
                faint.execute(
                    "SELECT COUNT(*) FROM faint_stars WHERE magnitude<=?", (limit,)
                ).fetchone()[0]
            )
            for limit in LIMITS
        }
        densities = {}
        for edition, (scale, limit) in ATLAS_CASES.items():
            mag = f"{limit:.1f}"
            per_region = {"all_sky": all_sky[mag] / all_sky_area}
            per_region.update({name: row["stars_per_sq_deg"][mag] for name, row in regions.items()})
            densities[edition] = {
                "scale_mm_per_degree": scale,
                "magnitude_limit": limit,
                "stars_per_sq_deg": per_region,
                "stars_per_cm2": {
                    name: stars_per_cm2(value, scale) for name, value in per_region.items()
                },
            }
        baselines = {
            "Standard 10mm@9.0": (10.0, 9.0),
            "Deep 20mm@10.5": (20.0, 10.5),
        }
        for values in densities.values():
            values["paper_density_ratio"] = {}
            for label, (scale, limit) in baselines.items():
                # The primary store has both limits; only the faint component
                # may extend the cumulative count beyond its own stored cutoff.
                base_total = int(
                    primary.execute(
                        "SELECT COUNT(*) FROM stars WHERE magnitude<=?", (limit,)
                    ).fetchone()[0]
                ) + int(
                    faint.execute(
                        "SELECT COUNT(*) FROM faint_stars WHERE magnitude<=?", (limit,)
                    ).fetchone()[0]
                )
                base_density = base_total / all_sky_area
                values["paper_density_ratio"][label] = (
                    values["stars_per_sq_deg"]["all_sky"] / values["scale_mm_per_degree"] ** 2
                ) / (base_density / scale**2)
        return {
            "regions": regions,
            "all_sky_cumulative_counts": all_sky,
            "edition_combinations": densities,
            "all_sky_area_sq_deg": all_sky_area,
        }
    finally:
        primary.close()
        faint.close()


def build_faint_query_performance_report(
    store_path: str | Path, limits: tuple[float, ...] = (13.5, 14.0)
) -> dict[str, Any]:
    """Measure region query duration, returned rows and peak Python memory."""
    report: dict[str, Any] = {}
    with FaintStarStore.open(store_path) as store:
        for name, center in REGIONS.items():
            dec_min = max(-90.0, center["center_dec_deg"] - REGION_HEIGHT_DEG / 2)
            dec_max = min(90.0, center["center_dec_deg"] + REGION_HEIGHT_DEG / 2)
            ra_min = (center["center_ra_deg"] - REGION_WIDTH_DEG / 2) % 360.0
            ra_max = (center["center_ra_deg"] + REGION_WIDTH_DEG / 2) % 360.0
            box = QueryBox(ra_min, ra_max, dec_min, dec_max)
            report[name] = {}
            for limit in limits:
                tracemalloc.start()
                started = time.perf_counter()
                stars = store.query_box(box, magnitude_limit=limit)
                elapsed = time.perf_counter() - started
                _current, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
                report[name][f"{limit:.1f}"] = {
                    "rows_returned": len(stars),
                    "query_seconds": elapsed,
                    "python_peak_bytes": peak,
                }
                del stars
    return report
