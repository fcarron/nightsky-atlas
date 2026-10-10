from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from nightsky_atlas.atlas.config import TilingConfig, load_atlas_config
from nightsky_atlas.atlas.tiling import TilingSpec, tile_sky, with_neighbours
from nightsky_atlas.chart.models import ChartDefinition
from nightsky_atlas.projection.stereographic import StereographicProjection

ROOT = Path(__file__).resolve().parents[1]
MM_PER_DEGREE = 20.0
GLOBAL_STEP_DEG = 0.25
FINE_RA_STEP_DEG = 0.125
FINE_DEC_STEP_DEG = 0.0125
BASELINE_CENTERS = tuple(-82.5 + 7.5 * index for index in range(23))


@dataclass(frozen=True)
class AuditResult:
    name: str
    charts: tuple[ChartDefinition, ...]
    gaps: int
    fractions: tuple[float, float, float, float]
    mean_multiplicity: float
    margin_mm: float
    margin_ra_deg: float
    margin_dec_deg: float
    margin_chart: str
    fine_margin_mm: float
    fine_margin_ra_deg: float
    fine_margin_dec_deg: float
    corner_margin_mm: float
    corner_ra_deg: float
    corner_dec_deg: float
    horizontal_mm: float
    horizontal_dec_deg: float
    transition_deg: float
    transition_low_dec_deg: float
    transition_high_dec_deg: float
    transition_ra_deg: float
    polar_mm: float
    polar_ra_deg: float
    neighbour_refs: int
    missing_neighbour_refs: int


def _clearance(
    center_ra_deg: float,
    center_dec_deg: float,
    ra_deg: np.ndarray,
    dec_deg: np.ndarray,
    width_deg: float,
    height_deg: float,
) -> np.ndarray:
    dec_rad = np.deg2rad(dec_deg)[:, None]
    delta_ra = np.deg2rad((ra_deg[None, :] - center_ra_deg + 180.0) % 360.0 - 180.0)
    center_dec_rad = math.radians(center_dec_deg)
    cos_c = (
        math.sin(center_dec_rad) * np.sin(dec_rad)
        + math.cos(center_dec_rad) * np.cos(dec_rad) * np.cos(delta_ra)
    )
    denominator = 1.0 + cos_c
    valid = denominator > 1e-12
    k = np.divide(2.0, denominator, out=np.zeros_like(denominator), where=valid)
    xi = np.rad2deg(k * np.cos(dec_rad) * np.sin(delta_ra))
    eta = np.rad2deg(
        k
        * (
            math.cos(center_dec_rad) * np.sin(dec_rad)
            - math.sin(center_dec_rad) * np.cos(dec_rad) * np.cos(delta_ra)
        )
    )
    clearance = np.minimum(width_deg / 2.0 - np.abs(xi), height_deg / 2.0 - np.abs(eta))
    return np.where(valid, clearance, -np.inf)


def _fine_margin_near(
    charts: tuple[ChartDefinition, ...], ra_center: float, dec_center: float
) -> tuple[float, float, float]:
    ra_offsets = np.arange(-1.0, 1.00001, 0.025)
    dec_offsets = np.arange(-1.0, 1.00001, FINE_DEC_STEP_DEG)
    best = (math.inf, 0.0, 0.0)
    for ra0 in (ra_center, (ra_center + 180.0) % 360.0):
        for dec0 in (dec_center, -dec_center):
            ra = (ra0 + ra_offsets) % 360.0
            dec = dec0 + dec_offsets
            margin = np.full((len(dec), len(ra)), -np.inf, dtype=np.float32)
            for chart in charts:
                rows = np.flatnonzero(
                    (dec >= max(-90.0, chart.center_dec_deg - 10.0))
                    & (dec <= min(90.0, chart.center_dec_deg + 10.0))
                )
                clearance = _clearance(
                    chart.center_ra_deg,
                    chart.center_dec_deg,
                    ra,
                    dec[rows],
                    chart.width_deg,
                    chart.height_deg,
                )
                current = margin[rows]
                np.maximum(current, clearance, out=current)
                margin[rows] = current
            row, col = np.unravel_index(np.argmin(margin), margin.shape)
            value = float(margin[row, col]) * MM_PER_DEGREE
            if value < best[0]:
                best = (value, float(ra[col]), float(dec[row]))
    return best


def _point_clearance(
    chart: ChartDefinition, ra: np.ndarray, dec: np.ndarray
) -> np.ndarray:
    dec_rad = np.deg2rad(dec)
    delta_ra = np.deg2rad((ra - chart.center_ra_deg + 180.0) % 360.0 - 180.0)
    center_dec_rad = math.radians(chart.center_dec_deg)
    cos_c = (
        math.sin(center_dec_rad) * np.sin(dec_rad)
        + math.cos(center_dec_rad) * np.cos(dec_rad) * np.cos(delta_ra)
    )
    denominator = 1.0 + cos_c
    valid = denominator > 1e-12
    k = np.divide(2.0, denominator, out=np.zeros_like(denominator), where=valid)
    xi = np.rad2deg(k * np.cos(dec_rad) * np.sin(delta_ra))
    eta = np.rad2deg(
        k
        * (
            math.cos(center_dec_rad) * np.sin(dec_rad)
            - math.sin(center_dec_rad) * np.cos(dec_rad) * np.cos(delta_ra)
        )
    )
    return np.where(
        valid,
        np.minimum(chart.width_deg / 2.0 - np.abs(xi), chart.height_deg / 2.0 - np.abs(eta)),
        -np.inf,
    )


def _corner_minimum(charts: tuple[ChartDefinition, ...]) -> tuple[float, float, float]:
    ras = []
    decs = []
    for chart in charts:
        projection = StereographicProjection(chart.center_ra_deg, chart.center_dec_deg)
        for xi in (-chart.width_deg / 2.0, chart.width_deg / 2.0):
            for eta in (-chart.height_deg / 2.0, chart.height_deg / 2.0):
                ra, dec = projection.inverse(xi, eta)
                ras.append(ra)
                decs.append(dec)
    ra_array = np.asarray(ras)
    dec_array = np.asarray(decs)
    best = np.full(len(ra_array), -np.inf)
    for chart in charts:
        np.maximum(best, _point_clearance(chart, ra_array, dec_array), out=best)
    index = int(np.argmin(best))
    return float(best[index]) * MM_PER_DEGREE, float(ra_array[index]), float(dec_array[index])


def _global_coverage(charts: tuple[ChartDefinition, ...]) -> tuple[
    int, tuple[float, float, float, float], float, float, float, str
]:
    ra = np.arange(0.0, 360.0, GLOBAL_STEP_DEG)
    dec = np.arange(-90.0 + GLOBAL_STEP_DEG / 2.0, 90.0, GLOBAL_STEP_DEG)
    counts = np.zeros((len(dec), len(ra)), dtype=np.uint8)
    best_clearance = np.full(counts.shape, -np.inf, dtype=np.float32)
    best_chart = np.full(counts.shape, -1, dtype=np.int16)
    for index, chart in enumerate(charts):
        rows = np.flatnonzero(
            (dec >= max(-90.0, chart.center_dec_deg - 10.0))
            & (dec <= min(90.0, chart.center_dec_deg + 10.0))
        )
        clearance = _clearance(
            chart.center_ra_deg,
            chart.center_dec_deg,
            ra,
            dec[rows],
            chart.width_deg,
            chart.height_deg,
        )
        inside = clearance >= -1e-9
        counts[rows] += inside.astype(np.uint8)
        current = best_clearance[rows]
        update = inside & (clearance > current)
        current[update] = clearance[update]
        best_clearance[rows] = current
        owners = best_chart[rows]
        owners[update] = index
        best_chart[rows] = owners

    weights = np.broadcast_to(np.cos(np.deg2rad(dec))[:, None], counts.shape)
    total_weight = float(weights.sum())
    fractions = tuple(
        float(weights[(counts >= lower) & (counts <= upper)].sum() / total_weight * 100.0)
        for lower, upper in ((1, 1), (2, 2), (3, 3), (4, 255))
    )
    mean = float((counts * weights).sum() / total_weight)
    gaps = int(np.count_nonzero(counts == 0))
    row, col = np.unravel_index(np.argmin(best_clearance), best_clearance.shape)
    owner = int(best_chart[row, col])
    owner_id = charts[owner].id if owner >= 0 else "uncovered"
    return (
        gaps,
        fractions,
        mean,
        float(best_clearance[row, col]) * MM_PER_DEGREE,
        float(ra[col]),
        float(dec[row]),
        owner_id,
    )


def _inside_parallel(
    projection: StereographicProjection, offset_deg: float, dec_deg: float
) -> bool:
    point = projection.project(offset_deg, dec_deg)
    return abs(point.xi_deg) <= 6.75 + 1e-9 and abs(point.eta_deg) <= 4.5 + 1e-9


def _horizontal_minimum(
    charts: tuple[ChartDefinition, ...], ring_centers: tuple[float, ...]
) -> tuple[float, float]:
    minimum = (math.inf, 0.0)
    for dec in ring_centers:
        ring = tuple(chart for chart in charts if abs(chart.center_dec_deg - dec) < 1e-8)
        if not ring:
            continue
        count = len(ring)
        ra_step = 360.0 / count
        projection = StereographicProjection(ring[0].center_ra_deg, dec)
        low, high = 0.0, ra_step
        while high < 180.0 and _inside_parallel(projection, high, dec):
            high = min(high * 2.0, 180.0)
        for _ in range(48):
            middle = (low + high) / 2.0
            if _inside_parallel(projection, middle, dec):
                low = middle
            else:
                high = middle
        overlap_deg = max(0.0, 2.0 * low - ra_step) * math.cos(math.radians(dec))
        overlap_mm = overlap_deg * MM_PER_DEGREE
        if overlap_mm < minimum[0]:
            minimum = (overlap_mm, dec)
    return minimum


def _coverage_by_ring(
    charts: tuple[ChartDefinition, ...],
    center_dec_deg: float,
    ra: np.ndarray,
    dec: np.ndarray,
) -> np.ndarray:
    result = np.zeros((len(dec), len(ra)), dtype=bool)
    for chart in charts:
        if abs(chart.center_dec_deg - center_dec_deg) > 1e-8:
            continue
        result |= (
            _clearance(
                chart.center_ra_deg,
                chart.center_dec_deg,
                ra,
                dec,
                chart.width_deg,
                chart.height_deg,
            )
            >= -1e-9
        )
    return result


def _minimum_run_width(mask: np.ndarray, step_deg: float) -> tuple[float, int]:
    run = np.zeros(mask.shape, dtype=np.uint16)
    for row in range(mask.shape[0]):
        if row:
            run[row] = np.where(mask[row], run[row - 1] + 1, 0)
        else:
            run[row] = mask[row]
    longest = run.max(axis=0)
    column = int(np.argmin(longest))
    return float(longest[column]) * step_deg, column


def _vertical_minima(
    charts: tuple[ChartDefinition, ...], centers: tuple[float, ...]
) -> tuple[tuple[float, float, float, float], tuple[float, float]]:
    ra = np.arange(0.0, 360.0, FINE_RA_STEP_DEG)
    results = []
    north = tuple(center for center in centers if center >= 0.0)
    for low, high in zip(north[:-1], north[1:], strict=True):
        count = max(1, round((high - low) / FINE_DEC_STEP_DEG))
        dec = np.linspace(low, high, count + 1)
        low_mask = _coverage_by_ring(charts, low, ra, dec)
        high_mask = _coverage_by_ring(charts, high, ra, dec)
        width, column = _minimum_run_width(low_mask & high_mask, FINE_DEC_STEP_DEG)
        results.append((low, high, width, float(ra[column])))

    top = north[-1]
    count = max(1, round((90.0 - top) / FINE_DEC_STEP_DEG))
    dec = np.linspace(top, 90.0, count + 1)
    cap_mask = _coverage_by_ring(
        (ChartDefinition("north-cap", 0.0, 90.0, 13.5, 9.0),), 90.0, ra, dec
    )
    top_mask = _coverage_by_ring(charts, top, ra, dec)
    width, column = _minimum_run_width(cap_mask & top_mask, FINE_DEC_STEP_DEG)
    polar = (width, float(ra[column]))
    return min(results, key=lambda row: row[2]), polar


def _make_centers(
    base: tuple[float, ...], shifts: tuple[float, float, float]
) -> tuple[float, ...]:
    replacements = {82.5: shifts[0], 75.0: shifts[1], 52.5: shifts[2]}
    return tuple(
        math.copysign(replacements.get(abs(center), abs(center)), center) for center in base
    )


def audit(name: str, centers: tuple[float, ...], config: TilingConfig) -> AuditResult:
    spec = TilingSpec.from_config(config.model_copy(update={"declination_centers": centers}))
    charts = tile_sky("deep", spec)
    gaps, fractions, mean, margin, margin_ra, margin_dec, margin_chart = _global_coverage(charts)
    fine_margin, fine_ra, fine_dec = _fine_margin_near(charts, margin_ra, margin_dec)
    corner_margin, corner_ra, corner_dec = _corner_minimum(charts)
    horizontal, horizontal_dec = _horizontal_minimum(charts, centers)
    (low, high, vertical, vertical_ra), (polar, polar_ra) = _vertical_minima(charts, centers)
    with_refs = with_neighbours(charts)
    known = {chart.id for chart in with_refs}
    ref_count = sum(len(chart.neighbours) for chart in with_refs)
    missing = sum(
        1
        for chart in with_refs
        for _, target in chart.neighbours
        if target not in known
    )
    return AuditResult(
        name,
        charts,
        gaps,
        fractions,
        mean,
        margin,
        margin_ra,
        margin_dec,
        margin_chart,
        fine_margin,
        fine_ra,
        fine_dec,
        corner_margin,
        corner_ra,
        corner_dec,
        horizontal,
        horizontal_dec,
        vertical,
        low,
        high,
        vertical_ra,
        polar * MM_PER_DEGREE,
        polar_ra,
        ref_count,
        missing,
    )


def main() -> None:
    atlas = load_atlas_config(ROOT / "atlas" / "deep.yaml")
    assert atlas.tiling is not None
    base = BASELINE_CENTERS
    candidates = (
        ("Baseline", (82.5, 75.0, 52.5)),
        ("A", (83.5, 75.5, 52.5)),
        ("B", (83.5, 75.5, 53.0)),
        ("C", (83.5, 75.5, 53.25)),
        ("Selected", (83.0, 75.0, 53.0)),
    )
    print(f"Global raster: RA step {GLOBAL_STEP_DEG:g}°, Dec cell centres; area weight cos(Dec).")
    print(
        f"Transition scan: RA step {FINE_RA_STEP_DEG:g}°, Dec step "
        f"{FINE_DEC_STEP_DEG:g}°; projected stereographic rectangles."
    )
    print(
        "| Variant | Charts | Gaps | Edge margin mm (RA, Dec) | Fine local margin mm (RA, Dec) | "
        "Corner margin mm (RA, Dec) | Min RA overlap mm (ring) | Min ring overlap mm (pair, RA) | "
        "Polar overlap mm (RA) | Multiplicity 1/2/3/4+ | Mean | Neighbours |"
    )
    print("|---|---:|---:|---|---|---|---|---|---:|---|")
    for name, shifts in candidates:
        result = audit(name, _make_centers(base, shifts), atlas.tiling)
        one, two, three, four = result.fractions
        print(
            f"| {name} | {len(result.charts)} | {result.gaps} | "
            f"{result.margin_mm:.2f} ({result.margin_ra_deg:.3f}°, {result.margin_dec_deg:.3f}°; "
            f"{result.margin_chart}) | "
            f"{result.fine_margin_mm:.2f} ({result.fine_margin_ra_deg:.3f}°, "
            f"{result.fine_margin_dec_deg:.3f}°) | {result.corner_margin_mm:.2f} "
            f"({result.corner_ra_deg:.3f}°, {result.corner_dec_deg:.3f}°) | "
            f"{result.horizontal_mm:.2f} ({result.horizontal_dec_deg:+g}°) | "
            f"{result.transition_deg * MM_PER_DEGREE:.2f} "
            f"({result.transition_low_dec_deg:g}/{result.transition_high_dec_deg:g}°, "
            f"RA {result.transition_ra_deg:.3f}°) | {result.polar_mm:.2f} "
            f"(RA {result.polar_ra_deg:.3f}°) | {one:.2f}/{two:.2f}/{three:.2f}/{four:.2f}% | "
            f"{result.mean_multiplicity:.4f} | {result.neighbour_refs}, missing "
            f"{result.missing_neighbour_refs} |"
        )
        print(
            "  ring counts north→south: "
            + "/".join(str(count) for count in reversed(atlas.tiling.chart_counts))
            + "; declination centres: "
            + ", ".join(
                f"{center:g}"
                for center in sorted(_make_centers(base, shifts), reverse=True)
            )
        )


if __name__ == "__main__":
    main()
