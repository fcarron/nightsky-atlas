"""UCAC4-derived, unlabeled faint-star supplement store."""

from __future__ import annotations

import hashlib
import json
import math
import random
import sqlite3
import statistics
import urllib.request
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from nightsky_atlas.catalog.store import QueryBox

UCAC4_RECORD_SIZE = 78
UCAC4_MAS_PER_DEG = 3_600_000.0
UCAC4_SPD_POLE_MAS = 324_000_000
UCAC4_BASE_URL = "https://cdsarc.cds.unistra.fr/ftp/cats/I/322A/UCAC4/u4b"
CALIBRATION_SAMPLE_SIZE = 100_000
CALIBRATION_SEED = 20261005
TYCHO_SOURCE_FLAGS = {3, 4, 5}
HIPPARCOS_SOURCE_FLAGS = {1, 2, 7}
FAINT_STORE_SCHEMA = """
CREATE TABLE faint_stars (
    id INTEGER PRIMARY KEY,
    ra_deg REAL NOT NULL,
    dec_deg REAL NOT NULL,
    magnitude REAL NOT NULL
);
"""


@dataclass(frozen=True, slots=True)
class FaintStar:
    """Minimal star data; deliberately carries no names or catalogue metadata."""

    id: str
    ra_deg: float
    dec_deg: float
    magnitude: float


@dataclass(frozen=True, slots=True)
class Ucac4Record:
    zone: int
    record_number: int
    ra_deg: float
    dec_deg: float
    atlas_magnitude: float
    magnitude_source: str
    primary_source_flag: int
    fmag: float | None
    apass_v: float | None
    apass_v_error_cmag: int
    jk_color: float | None


@dataclass(frozen=True, slots=True)
class MagnitudeCalibration:
    linear_intercept: float
    linear_slope: float
    color_intercept: float
    color_slope: float
    color_coefficient: float
    use_linear: bool
    use_color: bool
    sample_size: int
    color_sample_size: int
    fmag_range: tuple[float, float]
    diagnostics: dict[str, object]

    def predict(self, fmag: float, jk_color: float | None) -> tuple[float, str]:
        if self.fmag_range[0] <= fmag <= self.fmag_range[1]:
            if self.use_color and jk_color is not None:
                return (
                    self.color_intercept
                    + self.color_slope * fmag
                    + self.color_coefficient * jk_color,
                    "UCAC_fmag_color_calibrated",
                )
            if self.use_linear:
                return self.linear_intercept + self.linear_slope * fmag, "UCAC_fmag_calibrated"
            return fmag, "UCAC_fmag_raw_fallback"
        return fmag, "UCAC_fmag_raw_fallback"


def _signed(data: bytes, start: int, size: int) -> int:
    return int.from_bytes(data[start : start + size], "little", signed=True)


def parse_ucac4_record(data: bytes, *, zone: int, record_number: int) -> Ucac4Record | None:
    """Parse the official 78-byte UCAC4 zone record; return None if unusable.

    APASS V, UCAC f.mag, 2MASS J/K, and the UCAC4 source flag are read from
    the documented binary fields. Calibrated fallback conversion happens in
    the importer after its deterministic calibration sample is fitted.
    """
    if len(data) != UCAC4_RECORD_SIZE:
        raise ValueError(f"UCAC4 record must be {UCAC4_RECORD_SIZE} bytes")
    ra_mas = _signed(data, 0, 4)
    spd_mas = _signed(data, 4, 4)
    ra_deg = ra_mas / UCAC4_MAS_PER_DEG
    dec_deg = (spd_mas - UCAC4_SPD_POLE_MAS) / UCAC4_MAS_PER_DEG
    if not (0.0 <= ra_deg < 360.0 and -90.0 <= dec_deg <= 90.0):
        return None

    apass_v_mmag = _signed(data, 48, 2)
    apass_v_error = int.from_bytes(data[57:58], "little", signed=True)
    apass_v: float | None = None
    fmag: float | None = None
    if 0 < apass_v_mmag < 20_000 and 0 < abs(apass_v_error) < 90:
        apass_v = apass_v_mmag / 1000.0
    fmag_mmag = _signed(data, 8, 2)
    if 0 < fmag_mmag < 20_000:
        fmag = fmag_mmag / 1000.0
    if apass_v is not None:
        magnitude = apass_v
        magnitude_source = "APASS_V"
    else:
        if fmag is None:
            return None
        magnitude = fmag
        magnitude_source = "UCAC_fmag_fallback"

    jmag = _signed(data, 34, 2)
    kmag = _signed(data, 38, 2)
    j_quality = int.from_bytes(data[40:41], "little", signed=True)
    k_quality = int.from_bytes(data[42:43], "little", signed=True)
    jk_color = None
    if 0 < jmag < 20_000 and 0 < kmag < 20_000 and j_quality == 5 and k_quality == 5:
        jk_color = (jmag - kmag) / 1000.0

    # mcf is a decimal packed set of flags. Its first digit is the
    # Hipparcos/Tycho/FK6 source flag; 3 means Tycho-2.
    mcf = _signed(data, 62, 4)
    primary_source_flag = int(f"{mcf:09d}"[0]) if mcf >= 0 else 0
    return Ucac4Record(
        zone,
        record_number,
        ra_deg,
        dec_deg,
        magnitude,
        magnitude_source,
        primary_source_flag,
        fmag,
        apass_v,
        apass_v_error,
        jk_color,
    )


def _fit_linear(points: list[tuple[float, float]]) -> tuple[float, float]:
    if len(points) < 2:
        raise ValueError("UCAC4/APASS calibration needs at least two paired magnitudes")
    x_mean = statistics.fmean(x for x, _ in points)
    y_mean = statistics.fmean(y for _, y in points)
    denominator = sum((x - x_mean) ** 2 for x, _ in points)
    if denominator == 0:
        raise ValueError("UCAC4 calibration sample has no f.mag range")
    slope = sum((x - x_mean) * (y - y_mean) for x, y in points) / denominator
    return y_mean - slope * x_mean, slope


def _fit_color(points: list[tuple[float, float, float]]) -> tuple[float, float, float]:
    if len(points) < 3:
        raise ValueError("UCAC4 colour calibration needs at least three paired colours")
    rows = [
        [
            len(points),
            sum(x for x, _, _ in points),
            sum(c for _, _, c in points),
            sum(y for _, y, _ in points),
        ],
        [
            sum(x for x, _, _ in points),
            sum(x * x for x, _, _ in points),
            sum(x * c for x, _, c in points),
            sum(x * y for x, y, _ in points),
        ],
        [
            sum(c for _, _, c in points),
            sum(x * c for x, _, c in points),
            sum(c * c for _, _, c in points),
            sum(c * y for _, y, c in points),
        ],
    ]
    for pivot in range(3):
        best = max(range(pivot, 3), key=lambda row: abs(rows[row][pivot]))
        if abs(rows[best][pivot]) < 1e-12:
            raise ValueError("UCAC4 colour sample is singular")
        rows[pivot], rows[best] = rows[best], rows[pivot]
        divisor = rows[pivot][pivot]
        rows[pivot] = [value / divisor for value in rows[pivot]]
        for row in range(3):
            if row == pivot:
                continue
            factor = rows[row][pivot]
            rows[row] = [a - factor * b for a, b in zip(rows[row], rows[pivot], strict=True)]
    return rows[0][3], rows[1][3], rows[2][3]


def _residual_metrics(residuals: list[float]) -> dict[str, float]:
    median = statistics.median(residuals)
    return {
        "median_residual_mag": median,
        "rms_residual_mag": math.sqrt(statistics.fmean(value * value for value in residuals)),
        "mad_residual_mag": statistics.median(abs(value - median) for value in residuals),
    }


def fit_magnitude_calibration(records: Iterable[Ucac4Record]) -> MagnitudeCalibration:
    """Fit simple UCAC f.mag to APASS V models and compare on held-out records."""
    eligible = [
        record
        for record in records
        if record.fmag is not None
        and record.apass_v is not None
        and 0 < abs(record.apass_v_error_cmag) <= 30
        and 8.0 <= record.fmag <= 16.0
        and 8.0 <= record.apass_v <= 16.0
    ]
    if len(eligible) < 100:
        raise ValueError("at least 100 valid APASS V / UCAC f.mag pairs are required")
    eligible.sort(key=lambda record: (record.zone, record.record_number))
    holdout = [r for r in eligible if (r.record_number + r.zone) % 5 == 0]
    training = [r for r in eligible if (r.record_number + r.zone) % 5 != 0]
    if not holdout or not training:
        raise ValueError("UCAC4 calibration sample cannot be split for validation")
    linear_points = [
        (r.fmag, r.apass_v) for r in training if r.fmag is not None and r.apass_v is not None
    ]
    linear_a, linear_b = _fit_linear(linear_points)
    color_train = [
        (r.fmag, r.apass_v, r.jk_color)
        for r in training
        if r.fmag is not None and r.apass_v is not None and r.jk_color is not None
    ]
    color_test = [
        r
        for r in holdout
        if r.fmag is not None and r.apass_v is not None and r.jk_color is not None
    ]
    color_a, color_b, color_c = _fit_color(color_train) if len(color_train) >= 100 else (0, 1, 0)
    linear_test = [r for r in color_test if r.fmag is not None and r.apass_v is not None]
    raw_residuals = [r.fmag - r.apass_v for r in linear_test]
    linear_residuals = [linear_a + linear_b * r.fmag - r.apass_v for r in linear_test]
    color_residuals = [
        color_a + color_b * r.fmag + color_c * r.jk_color - r.apass_v
        for r in linear_test
        if r.fmag is not None and r.apass_v is not None and r.jk_color is not None
    ]
    raw_metrics = _residual_metrics(raw_residuals)
    linear_metrics = _residual_metrics(linear_residuals)
    color_metrics = _residual_metrics(color_residuals)
    use_linear = raw_metrics["rms_residual_mag"] - linear_metrics["rms_residual_mag"] >= 0.02
    baseline_metrics = linear_metrics if use_linear else raw_metrics
    use_color = len(color_residuals) >= 100 and (
        baseline_metrics["rms_residual_mag"] - color_metrics["rms_residual_mag"] >= 0.02
    )
    all_linear = [
        (r.fmag, r.apass_v) for r in eligible if r.fmag is not None and r.apass_v is not None
    ]
    final_a, final_b = _fit_linear(all_linear)
    all_color = [
        (r.fmag, r.apass_v, r.jk_color)
        for r in eligible
        if r.fmag is not None and r.apass_v is not None and r.jk_color is not None
    ]
    final_color_a, final_color_b, final_color_c = (
        _fit_color(all_color) if len(all_color) >= 100 else (0, 1, 0)
    )
    selected_test = color_test if use_color else linear_test
    selected_a, selected_b, selected_c = (
        (color_a, color_b, color_c)
        if use_color
        else (linear_a, linear_b, 0.0)
        if use_linear
        else (0.0, 1.0, 0.0)
    )
    diagnostics: dict[str, object] = {
        "holdout_rows_with_color": len(color_residuals),
        "raw_fmag_as_v": raw_metrics,
        "linear_fmag": linear_metrics,
        "linear_fmag_plus_j_minus_ks": color_metrics,
        "holdout_residual_by_fmag_bin": _binned_residuals(
            selected_test,
            lambda record: record.fmag,
            selected_a,
            selected_b,
            selected_c,
        ),
        "holdout_residual_by_j_minus_ks_bin": _binned_residuals(
            color_test, lambda record: record.jk_color, color_a, color_b, color_c
        ),
        "linear_selected": use_linear,
        "color_selected": use_color,
    }
    magnitudes = [r.fmag for r in eligible if r.fmag is not None]
    return MagnitudeCalibration(
        final_a,
        final_b,
        final_color_a,
        final_color_b,
        final_color_c,
        use_linear,
        use_color,
        len(eligible),
        len(all_color),
        (min(magnitudes), max(magnitudes)),
        diagnostics,
    )


def _binned_residuals(records, color_fn, intercept: float, slope: float, color_coeff: float):
    bins: dict[str, list[float]] = {}
    for record in records:
        x = color_fn(record)
        if x is None or record.apass_v is None or record.fmag is None:
            continue
        low = math.floor(x * 2.0) / 2.0
        key = f"{low:.1f}..{low + 0.5:.1f}"
        color = record.jk_color if color_coeff else 0.0
        bins.setdefault(key, []).append(
            intercept + slope * record.fmag + color_coeff * color - record.apass_v
        )
    return {
        key: _residual_metrics(values) | {"count": len(values)}
        for key, values in sorted(bins.items())
    }


def _fit_import_calibration(paths: list[Path]) -> MagnitudeCalibration | None:
    rng = random.Random(CALIBRATION_SEED)
    sample: list[Ucac4Record] = []
    seen = 0
    for record in iter_ucac4_binary_zones(paths):
        if record.fmag is None or record.apass_v is None:
            continue
        seen += 1
        if len(sample) < CALIBRATION_SAMPLE_SIZE:
            sample.append(record)
        else:
            slot = rng.randrange(seen)
            if slot < CALIBRATION_SAMPLE_SIZE:
                sample[slot] = record
    try:
        return fit_magnitude_calibration(sample)
    except ValueError:
        return None


def _magnitude_source_bucket(source: str) -> str:
    if source == "APASS_V":
        return "APASS_V"
    if source in {"UCAC_fmag_calibrated", "UCAC_fmag_color_calibrated"}:
        return "calibrated_fmag"
    return "raw_fmag_fallback"


class FaintStarStore:
    def __init__(self, connection: sqlite3.Connection, path: Path) -> None:
        self._connection = connection
        self.path = path

    @classmethod
    def open(cls, path: str | Path) -> FaintStarStore:
        resolved = Path(path)
        if not resolved.is_file():
            raise FileNotFoundError(f"faint-star store not found: {resolved}")
        return cls(sqlite3.connect(resolved), resolved)

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> FaintStarStore:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def count(self) -> int:
        return int(self._connection.execute("SELECT COUNT(*) FROM faint_stars").fetchone()[0])

    def cumulative_counts(self, limits: Iterable[float]) -> dict[float, int]:
        return {
            limit: int(
                self._connection.execute(
                    "SELECT COUNT(*) FROM faint_stars WHERE magnitude<=?", (limit,)
                ).fetchone()[0]
            )
            for limit in limits
        }

    def storage_stats(self) -> dict[str, int]:
        page_size = int(self._connection.execute("PRAGMA page_size").fetchone()[0])
        page_count = int(self._connection.execute("PRAGMA page_count").fetchone()[0])
        result = {"database_bytes": page_size * page_count}
        try:
            result.update(
                {
                    str(name): int(size)
                    for name, size in self._connection.execute(
                        "SELECT name,SUM(pgsize) FROM dbstat GROUP BY name"
                    )
                }
            )
        except sqlite3.OperationalError:
            pass
        return result

    def query_box(self, box: QueryBox, *, magnitude_limit: float) -> list[FaintStar]:
        sql = (
            "SELECT id,ra_deg,dec_deg,magnitude FROM faint_stars "
            "WHERE dec_deg>=? AND dec_deg<=? AND magnitude<=?"
        )
        params: list[float] = [box.dec_min_deg, box.dec_max_deg, magnitude_limit]
        if box.wraps_ra:
            sql += " AND (ra_deg>=? OR ra_deg<=?)"
        else:
            sql += " AND ra_deg>=? AND ra_deg<=?"
        params.extend((box.ra_min_deg, box.ra_max_deg))
        sql += " ORDER BY id"
        return [
            FaintStar(f"UCAC4-{row[0]:010d}", float(row[1]), float(row[2]), float(row[3]))
            for row in self._connection.execute(sql, params)
        ]


def iter_ucac4_binary_zones(paths: Iterable[Path]) -> Iterator[Ucac4Record]:
    """Stream official zone files (one 78-byte record per source star)."""
    for path in sorted(paths):
        zone = int(path.name[1:])
        with path.open("rb") as stream:
            record_number = 0
            while block := stream.read(UCAC4_RECORD_SIZE * 8192):
                usable = len(block) - len(block) % UCAC4_RECORD_SIZE
                if usable != len(block) and not stream.peek(1):
                    raise ValueError(f"truncated UCAC4 record in {path}")
                for offset in range(0, usable, UCAC4_RECORD_SIZE):
                    record_number += 1
                    record = parse_ucac4_record(
                        block[offset : offset + UCAC4_RECORD_SIZE],
                        zone=zone,
                        record_number=record_number,
                    )
                    if record is not None:
                        yield record


def import_ucac4_faint(
    raw_dir: str | Path,
    output: str | Path,
    *,
    magnitude_limit: float = 14.0,
    primary_store: str | Path | None = None,
    manifest_path: str | Path | None = None,
) -> dict[str, object]:
    """Build the compact store from locally obtained UCAC4 binary zone files."""
    if not math.isfinite(magnitude_limit) or not 0.0 < magnitude_limit <= 14.0:
        raise ValueError("UCAC4 master magnitude limit must be greater than 0 and at most 14.0")
    paths = sorted(Path(raw_dir).glob("z[0-9][0-9][0-9]"))
    if not paths:
        raise FileNotFoundError(f"no UCAC4 zone files z001..z900 found under {raw_dir}")
    calibration = _fit_import_calibration(paths)
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    connection = sqlite3.connect(temporary)
    source_count = selected_count = 0
    rows_before_crossmatch = 0
    apass_count = calibrated_count = raw_fallback_count = 0
    linear_calibrated_count = color_calibrated_count = 0
    tycho_flagged = hipparcos_flagged = 0
    positional_primary = 0
    ambiguous_positional = retained_near_primary = 0
    primary_grid: dict[tuple[int, int], list[tuple[str, float, float]]] = {}
    matched_primary: set[str] = set()
    if primary_store is not None:
        primary_connection = sqlite3.connect(primary_store)
        try:
            for star_id, ra_deg, dec_deg in primary_connection.execute(
                "SELECT id,ra_deg,dec_deg FROM stars"
            ):
                ra_deg, dec_deg = float(ra_deg), float(dec_deg)
                cell = (int(ra_deg * 100), int((dec_deg + 90.0) * 100))
                primary_grid.setdefault(cell, []).append((str(star_id), ra_deg, dec_deg))
        finally:
            primary_connection.close()
    try:
        connection.execute("PRAGMA journal_mode=OFF")
        connection.execute("PRAGMA synchronous=OFF")
        connection.executescript(FAINT_STORE_SCHEMA)
        batch: list[tuple[int, float, float, float]] = []
        for record in iter_ucac4_binary_zones(paths):
            source_count += 1
            atlas_magnitude, magnitude_source = record.atlas_magnitude, record.magnitude_source
            if (
                magnitude_source != "APASS_V"
                and record.fmag is not None
                and calibration is not None
            ):
                atlas_magnitude, magnitude_source = calibration.predict(
                    record.fmag, record.jk_color
                )
            if atlas_magnitude > magnitude_limit:
                continue
            rows_before_crossmatch += 1
            if record.primary_source_flag in TYCHO_SOURCE_FLAGS:
                tycho_flagged += 1
                continue
            if record.primary_source_flag in HIPPARCOS_SOURCE_FLAGS:
                hipparcos_flagged += 1
                continue
            cell = (int(record.ra_deg * 100), int((record.dec_deg + 90.0) * 100))
            nearby: list[tuple[float, str]] = []
            cos_dec = max(1e-6, math.cos(math.radians(record.dec_deg)))
            ra_cell_radius = min(36_000, math.ceil((2.0 / 3600.0 / cos_dec) * 100) + 1)
            for dx in range(-ra_cell_radius, ra_cell_radius + 1):
                for dy in (-1, 0, 1):
                    cell_ra = (cell[0] + dx) % 36_000
                    for primary_id, pra, pdec in primary_grid.get((cell_ra, cell[1] + dy), ()):
                        dra = ((record.ra_deg - pra + 180.0) % 360.0) - 180.0
                        separation_arcsec = (
                            math.hypot(
                                dra * math.cos(math.radians(record.dec_deg)),
                                record.dec_deg - pdec,
                            )
                            * 3600.0
                        )
                        if separation_arcsec <= 2.0:
                            nearby.append((separation_arcsec, primary_id))
            close = [(separation, star_id) for separation, star_id in nearby if separation <= 0.5]
            # Remove only a unique, close match and only once per primary star.
            # Multiple catalogue detections are preserved; close pairs stay in
            # the faint layer when the counterpart cannot be resolved uniquely.
            if len(close) == 1 and close[0][1] not in matched_primary:
                matched_primary.add(close[0][1])
                positional_primary += 1
                continue
            if len(close) > 1:
                ambiguous_positional += 1
            if nearby:
                retained_near_primary += 1
            selected_count += 1
            bucket = _magnitude_source_bucket(magnitude_source)
            if bucket == "APASS_V":
                apass_count += 1
            elif bucket == "calibrated_fmag":
                calibrated_count += 1
                if magnitude_source == "UCAC_fmag_color_calibrated":
                    color_calibrated_count += 1
                else:
                    linear_calibrated_count += 1
            else:
                raw_fallback_count += 1
            # A deterministic, catalogue-derived integer key keeps each source
            # record unique without storing per-row strings.
            uid = record.zone * 10_000_000 + record.record_number
            batch.append((uid, record.ra_deg, record.dec_deg, atlas_magnitude))
            if len(batch) >= 50_000:
                connection.executemany("INSERT INTO faint_stars VALUES(?,?,?,?)", batch)
                batch.clear()
        if batch:
            connection.executemany("INSERT INTO faint_stars VALUES(?,?,?,?)", batch)
        connection.execute(
            "CREATE INDEX faint_stars_dec_mag_ra_idx ON faint_stars(dec_deg,magnitude,ra_deg)"
        )
        connection.execute("ANALYZE")
        connection.commit()
    except Exception:
        connection.close()
        temporary.unlink(missing_ok=True)
        raise
    connection.close()
    target.unlink(missing_ok=True)
    temporary.replace(target)
    final_total = selected_count
    calibration_data: dict[str, object] = {
        "available": calibration is not None,
        "method": (
            "deterministic UCAC f.mag to APASS V calibration; "
            "80/20 record-number modulo holdout"
        ),
        "sample_size": calibration.sample_size if calibration else 0,
        "color_sample_size": calibration.color_sample_size if calibration else 0,
        "fmag_range": list(calibration.fmag_range) if calibration else None,
        "formula": (
            "APASS V if valid; else a+b*f.mag+c*(J-Ks) when colour model selected; "
            "else a+b*f.mag in calibration range; else raw f.mag flagged"
        ),
        "linear_coefficients": (
            {"a": calibration.linear_intercept, "b": calibration.linear_slope}
            if calibration
            else None
        ),
        "color_coefficients": (
            {
                "a": calibration.color_intercept,
                "b": calibration.color_slope,
                "c": calibration.color_coefficient,
            }
            if calibration
            else None
        ),
        "diagnostics": calibration.diagnostics if calibration else None,
        "sample_seed": CALIBRATION_SEED,
    }
    manifest: dict[str, object] = {
        "catalogue": "UCAC4",
        "version": "USNO CCD Astrograph Catalog DR4",
        "source": UCAC4_BASE_URL,
        "reference": "Zacharias et al. 2013, DOI 10.26131/IRSA17",
        "license": "No explicit redistribution license identified; retain locally and cite source",
        "original_rows": sum(path.stat().st_size // UCAC4_RECORD_SIZE for path in paths),
        "zones_imported": ",".join(path.name[1:] for path in paths),
        "all_sky_complete": len(paths) == 900
        and {int(path.name[1:]) for path in paths} == set(range(1, 901)),
        "rows_with_valid_coordinates_and_magnitude": source_count,
        "magnitude_limit": magnitude_limit,
        "magnitude_rule": (
            "valid APASS V; otherwise empirically calibrated f.mag, with J-Ks colour if "
            "held-out RMS improves by at least 0.02 mag; raw f.mag is counted separately"
        ),
        "magnitude_calibration": calibration_data,
        "magnitude_sources": {
            "APASS_V": {
                "count": apass_count,
                "percent": 100.0 * apass_count / final_total if final_total else 0.0,
            },
            "calibrated_fmag": {
                "count": calibrated_count,
                "percent": 100.0 * calibrated_count / final_total if final_total else 0.0,
                "linear_count": linear_calibrated_count,
                "color_count": color_calibrated_count,
            },
            "raw_fmag_fallback": {
                "count": raw_fallback_count,
                "percent": 100.0 * raw_fallback_count / final_total if final_total else 0.0,
            },
        },
        "apass_v_rows": apass_count,
        "ucac_fmag_calibrated_rows": calibrated_count,
        "ucac_fmag_raw_fallback_rows": raw_fallback_count,
        "rows_before_tycho_removal": rows_before_crossmatch,
        "rows_removed_ucac4_tycho_source_flags": tycho_flagged,
        "rows_removed_ucac4_hipparcos_source_flags": hipparcos_flagged,
        "rows_removed_positional_primary_crossmatch": positional_primary,
        "ambiguous_positional_candidates_retained": ambiguous_positional,
        "ucac4_rows_retained_within_2_arcsec_of_primary": retained_near_primary,
        "final_faint_rows": selected_count,
        "coordinate_rule": "UCAC4 integer RA and south-pole distance in mas, J2000 ICRS",
        "crossmatch_rule": (
            "first exclude UCAC4 tf source flags 1/2/7 (Hipparcos) and 3/4/5 (Tycho); "
            "flag 6 is FK6 and is checked against the primary store by position; "
            "then exclude a unique unused match within 0.5 arcsec; retain ambiguous matches"
        ),
        "processed_file": target.name,
        "processed_sha256": _sha256(target),
        "processed_bytes": target.stat().st_size,
    }
    manifest_target = Path(manifest_path) if manifest_path else target.with_suffix(".manifest.json")
    manifest_target.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest["manifest_path"] = str(manifest_target)
    return manifest


def download_ucac4_zones(
    dest_dir: str | Path, *, zones: Iterable[int] = range(1, 901)
) -> list[Path]:
    """Download selected official CDS UCAC4 binary zones (about 8+ GB all-sky)."""
    destination = Path(dest_dir)
    destination.mkdir(parents=True, exist_ok=True)
    downloaded: list[Path] = []
    for zone in zones:
        if not 1 <= zone <= 900:
            raise ValueError(f"UCAC4 zone out of range: {zone}")
        target = destination / f"z{zone:03d}"
        if target.exists():
            if target.stat().st_size > 0 and target.stat().st_size % UCAC4_RECORD_SIZE == 0:
                downloaded.append(target)
                continue
            target.unlink()
        url = f"https://cdsarc.cds.unistra.fr/ftp/cats/I/322A/UCAC4/u4b/z{zone:03d}"
        temporary = target.with_suffix(".download")
        try:
            with urllib.request.urlopen(url, timeout=120) as response, temporary.open("wb") as out:
                while block := response.read(1024 * 1024):
                    out.write(block)
            if temporary.stat().st_size % UCAC4_RECORD_SIZE:
                raise ValueError(f"downloaded UCAC4 zone has invalid size: {zone}")
            temporary.replace(target)
            downloaded.append(target)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
    return downloaded


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()
