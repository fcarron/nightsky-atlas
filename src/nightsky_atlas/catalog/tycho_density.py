"""Measured Tycho-2 stellar-density report for atlas edition calibration."""

from __future__ import annotations

import csv
import json
import math
import sqlite3
from pathlib import Path
from typing import Any

LIMITS = (7.0, 7.5, 8.0, 8.5, 9.0, 9.5, 10.0, 10.5, 11.0, 11.5)
REGIONS = {
    "sparse": {"center_ra_deg": 192.0, "center_dec_deg": 27.0},
    "virgo": {"center_ra_deg": 187.5, "center_dec_deg": 12.0},
    "cygnus": {"center_ra_deg": 307.0, "center_dec_deg": 41.0},
    "sagittarius": {"center_ra_deg": 280.7, "center_dec_deg": -24.7},
    "southern_milky_way": {"center_ra_deg": 100.0, "center_dec_deg": -60.0},
}
REGION_WIDTH_DEG = 27.0
REGION_HEIGHT_DEG = 18.5
EDITIONS = {
    "Pocket 7.5": (5.0, 7.5),
    "Pocket 8.0": (5.0, 8.0),
    "Standard 9.0": (10.0, 9.0),
    "Deep 10.0": (20.0, 10.0),
    "Deep 10.5": (20.0, 10.5),
    "Eyepiece 11.0": (40.0, 11.0),
    "Eyepiece 11.5": (40.0, 11.5),
}
COMPLETENESS_NOTE = (
    "Tycho-2 is reported approximately 99% complete to V=11.0 and 90% complete "
    "to V=11.5. The 11.0–11.5 bin is therefore an observed catalogue count, "
    "not a corrected estimate of the true stellar population. Lower growth "
    "there can partly reflect incompleteness. No correction is applied."
)


def effective_alpha(n1: int, n2: int, delta_mag: float) -> float:
    if n1 <= 0 or n2 <= 0 or delta_mag <= 0:
        raise ValueError("counts and magnitude interval must be positive")
    return math.log10(n2 / n1) / delta_mag


def spherical_rectangle_area_sq_deg(
    ra_width_deg: float, dec_min_deg: float, dec_max_deg: float
) -> float:
    """Exact spherical area of an RA/Dec rectangle, expressed in square degrees."""
    if not 0 < ra_width_deg <= 360 or not -90 <= dec_min_deg < dec_max_deg <= 90:
        raise ValueError("invalid spherical rectangle")
    area_sr = math.radians(ra_width_deg) * (
        math.sin(math.radians(dec_max_deg)) - math.sin(math.radians(dec_min_deg))
    )
    return area_sr * (180.0 / math.pi) ** 2


def stars_per_cm2(stars_per_sq_deg: float, scale_mm_per_deg: float) -> float:
    if stars_per_sq_deg < 0 or scale_mm_per_deg <= 0:
        raise ValueError("density must be non-negative and scale must be positive")
    return stars_per_sq_deg / (scale_mm_per_deg**2) * 100.0


def _count(
    connection: sqlite3.Connection,
    magnitude: float,
    ra_min: float,
    ra_max: float,
    dec_min: float,
    dec_max: float,
) -> int:
    row = connection.execute(
        "SELECT COUNT(*) FROM stars WHERE catalogue='TYC2' AND magnitude<=? "
        "AND dec_deg>=? AND dec_deg<=? AND ra_deg>=? AND ra_deg<=?",
        (magnitude, dec_min, dec_max, ra_min % 360.0, ra_max % 360.0),
    ).fetchone()
    if ra_min % 360.0 > ra_max % 360.0:
        row = connection.execute(
            "SELECT COUNT(*) FROM stars WHERE catalogue='TYC2' AND magnitude<=? "
            "AND dec_deg>=? AND dec_deg<=? AND (ra_deg>=? OR ra_deg<=?)",
            (magnitude, dec_min, dec_max, ra_min % 360.0, ra_max % 360.0),
        ).fetchone()
    return int(row[0])


def build_report(store_path: str | Path) -> dict[str, Any]:
    connection = sqlite3.connect(store_path)
    try:
        sources = {
            str(name): int(count)
            for name, count in connection.execute(
                "SELECT catalogue,COUNT(*) FROM stars GROUP BY catalogue ORDER BY catalogue"
            )
        }
        total = sources.get("TYC2", 0)
        allsky_counts = {
            f"{m:.1f}": int(
                connection.execute(
                    "SELECT COUNT(*) FROM stars WHERE catalogue='TYC2' AND magnitude<=?", (m,)
                ).fetchone()[0]
            )
            for m in LIMITS
        }
        increments = {
            f"{a:.1f}-{b:.1f}": allsky_counts[f"{b:.1f}"] - allsky_counts[f"{a:.1f}"]
            for a, b in zip(LIMITS, LIMITS[1:], strict=False)
        }
        growth = []
        for a, b in zip(LIMITS, LIMITS[1:], strict=False):
            n1, n2 = allsky_counts[f"{a:.1f}"], allsky_counts[f"{b:.1f}"]
            growth.append(
                {
                    "interval": f"{a:.1f} -> {b:.1f}",
                    "factor": n2 / n1,
                    "alpha": effective_alpha(n1, n2, b - a),
                    "increment": n2 - n1,
                }
            )
        regions: dict[str, Any] = {}
        for name, center in REGIONS.items():
            dec_min = max(-90.0, center["center_dec_deg"] - REGION_HEIGHT_DEG / 2)
            dec_max = min(90.0, center["center_dec_deg"] + REGION_HEIGHT_DEG / 2)
            ra_min, ra_max = (
                center["center_ra_deg"] - REGION_WIDTH_DEG / 2,
                center["center_ra_deg"] + REGION_WIDTH_DEG / 2,
            )
            area = spherical_rectangle_area_sq_deg(REGION_WIDTH_DEG, dec_min, dec_max)
            counts = {
                f"{m:.1f}": _count(connection, m, ra_min, ra_max, dec_min, dec_max)
                for m in LIMITS[1:]
            }
            regions[name] = {
                **center,
                "ra_width_deg": REGION_WIDTH_DEG,
                "dec_min_deg": dec_min,
                "dec_max_deg": dec_max,
                "sky_area_sq_deg": area,
                "cumulative_counts": counts,
                "stars_per_sq_deg": {m: n / area for m, n in counts.items()},
            }

        regional_stress = {}
        for name in ("cygnus", "sagittarius"):
            counts = regions[name]["cumulative_counts"]
            intervals = {}
            for a, b in ((9.0, 10.0), (9.0, 10.5), (10.5, 11.0), (11.0, 11.5)):
                n1, n2 = counts[f"{a:.1f}"], counts[f"{b:.1f}"]
                intervals[f"{a:.1f}->{b:.1f}"] = {
                    "factor": None if n1 == 0 else n2 / n1,
                    "added_stars": n2 - n1,
                    "added_stars_per_sq_deg": (n2 - n1) / regions[name]["sky_area_sq_deg"],
                }
            regional_stress[name] = intervals

        allsky_area = 4 * math.pi * (180 / math.pi) ** 2
        densities: dict[str, Any] = {}
        standard = None
        for edition, (scale, limit) in EDITIONS.items():
            key = f"{limit:.1f}"
            per_region = {"all_sky": allsky_counts[key] / allsky_area}
            per_region.update(
                {name: region["stars_per_sq_deg"][key] for name, region in regions.items()}
            )
            densities[edition] = {
                "scale_mm_per_degree": scale,
                "magnitude_limit": limit,
                "stars_per_sq_deg": per_region,
                "stars_per_cm2": {
                    name: stars_per_cm2(density, scale) for name, density in per_region.items()
                },
            }
            if edition == "Standard 9.0":
                standard = densities[edition]
        assert standard is not None
        for _edition, item in densities.items():
            item["density_ratio_to_standard"] = {
                field: (
                    None
                    if standard["stars_per_cm2"][field] == 0
                    else item["stars_per_cm2"][field] / standard["stars_per_cm2"][field]
                )
                for field in ("all_sky", "sparse", "cygnus", "sagittarius")
            }
        # Magnitude needed at each larger scale to preserve the measured baseline density.
        scale_doubling = {}
        for (lower, upper), baseline_mag in zip(
            ((5.0, 10.0), (10.0, 20.0), (20.0, 40.0)), (7.5, 9.0, 10.0), strict=True
        ):
            baseline_count = allsky_counts[f"{baseline_mag:.1f}"]
            target = baseline_count * 4
            upper_magnitude = None
            for a, b in zip(LIMITS, LIMITS[1:], strict=False):
                na, nb = allsky_counts[f"{a:.1f}"], allsky_counts[f"{b:.1f}"]
                if na <= target <= nb:
                    upper_magnitude = a + (b - a) * (target - na) / (nb - na)
                    break
            scale_doubling[f"{lower:.0f}->{upper:.0f}"] = {
                "baseline_magnitude": baseline_mag,
                "magnitude_at_upper_scale_for_equal_paper_density": upper_magnitude,
                "delta_magnitude": None
                if upper_magnitude is None
                else upper_magnitude - baseline_mag,
                "target_count": target,
            }
        return {
            "catalogue": "Tycho-2 rows in the production normalized SQLite star store",
            "store_path": str(store_path),
            "source_row_counts": sources,
            "measured_catalogue_rows": total,
            "magnitude_field": (
                "stars.magnitude: Johnson V = VT - 0.090 * (BT - VT), normalized at Tycho-2 import"
            ),
            "all_sky_cumulative_counts": allsky_counts,
            "all_sky_incremental_counts": increments,
            "growth_intervals": growth,
            "regional_stress_growth": regional_stress,
            "average_alpha": {
                "7.5-9.0": effective_alpha(allsky_counts["7.5"], allsky_counts["9.0"], 1.5),
                "9.0-10.5": effective_alpha(allsky_counts["9.0"], allsky_counts["10.5"], 1.5),
                "10.5-11.5": effective_alpha(allsky_counts["10.5"], allsky_counts["11.5"], 1.0),
                "7.5-11.5": effective_alpha(allsky_counts["7.5"], allsky_counts["11.5"], 4.0),
            },
            "regions": regions,
            "edition_densities": densities,
            "all_sky_area_sq_deg": allsky_area,
            "scale_doubling_constant_density": scale_doubling,
            "completeness_note": COMPLETENESS_NOTE,
            "recommendation": {
                "official_defaults": {
                    "Pocket": 7.5,
                    "Standard": 9.0,
                    "Deep": 10.0,
                    "Eyepiece": 11.0,
                },
                "optional_deeper_modes": {"Pocket": 8.0, "Deep": 10.5, "Eyepiece": 11.5},
                "reasoning": (
                    "Keep the official editions moderate in dense Milky Way fields. The deeper "
                    "settings add useful star-hopping detail at the larger scales, but are best "
                    "exposed as optional layers; at V=11.5 the Tycho-2 count is near the "
                    "catalogue completeness edge."
                ),
            },
            "caveat": (
                "Regional windows are equal RA/Dec rectangles centered on listed "
                "benchmark/control coordinates; exact spherical areas are used."
            ),
        }
    finally:
        connection.close()


def write_json(report: dict[str, Any], path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(report: dict[str, Any], path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=(
                "section",
                "region",
                "magnitude",
                "count",
                "increment",
                "stars_per_sq_deg",
                "stars_per_cm2",
                "density_ratio_to_standard",
                "growth_factor",
                "alpha",
            ),
        )
        writer.writeheader()
        for mag, count in report["all_sky_cumulative_counts"].items():
            writer.writerow({"section": "all_sky", "magnitude": mag, "count": count})
        for interval in report["growth_intervals"]:
            writer.writerow(
                {
                    "section": "growth",
                    "region": interval["interval"],
                    "increment": interval["increment"],
                    "growth_factor": interval["factor"],
                    "alpha": interval["alpha"],
                }
            )
        for name, region in report["regions"].items():
            for mag, count in region["cumulative_counts"].items():
                writer.writerow(
                    {
                        "section": "regional",
                        "region": name,
                        "magnitude": mag,
                        "count": count,
                        "stars_per_sq_deg": region["stars_per_sq_deg"][mag],
                    }
                )
        for edition, item in report["edition_densities"].items():
            for region, value in item["stars_per_cm2"].items():
                writer.writerow(
                    {
                        "section": "paper_density",
                        "region": f"{edition}:{region}",
                        "magnitude": item["magnitude_limit"],
                        "stars_per_cm2": value,
                        "density_ratio_to_standard": item["density_ratio_to_standard"].get(region),
                    }
                )
