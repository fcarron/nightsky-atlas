"""Gaia DR3 density contours for the Magellanic Clouds."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = ["DEFAULT_DATA_PATH", "MagellanicContour", "load_magellanic_contours"]

DEFAULT_DATA_PATH = Path("data/third_party/gaia_dr3_magellanic/contours.geojson")
_CLOUD_DSO_IDS = {"LMC": "ESO056-115", "SMC": "NGC0292"}


@dataclass(frozen=True, slots=True)
class MagellanicContour:
    """One nested Gaia-density polygon in ICRS coordinates."""

    id: str
    cloud_id: str
    dso_id: str
    level: int
    points: tuple[tuple[float, float], ...]

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.cloud_id.strip() or not self.dso_id.strip():
            raise ValueError("Magellanic contour identifiers must not be blank")
        if self.level not in (1, 2, 3):
            raise ValueError("Magellanic contour level must be between 1 and 3")
        if len(self.points) < 4 or self.points[0] != self.points[-1]:
            raise ValueError("Magellanic contour must be a closed polygon with three vertices")
        for ra_deg, dec_deg in self.points:
            if not math.isfinite(ra_deg) or not math.isfinite(dec_deg):
                raise ValueError("Magellanic contour coordinates must be finite")
            if not 0.0 <= ra_deg < 360.0 or not -90.0 <= dec_deg <= 90.0:
                raise ValueError("Magellanic contour coordinate is outside ICRS bounds")


def _polygon_points(raw: Any, source: str) -> tuple[tuple[float, float], ...]:
    if not isinstance(raw, list) or len(raw) != 1 or not isinstance(raw[0], list):
        raise ValueError(f"expected one GeoJSON polygon ring in {source}")
    points: list[tuple[float, float]] = []
    for coordinate in raw[0]:
        if not isinstance(coordinate, (list, tuple)) or len(coordinate) < 2:
            raise ValueError(f"malformed Magellanic contour coordinate in {source}")
        points.append((float(coordinate[0]), float(coordinate[1])))
    result = tuple(points)
    if len(result) < 4 or result[0] != result[-1]:
        raise ValueError(f"Magellanic contour must be a closed polygon in {source}")
    if len(set(result[:-1])) < 3:
        raise ValueError(f"Magellanic contour has fewer than three distinct vertices in {source}")
    unwrapped: list[tuple[float, float]] = [result[0]]
    for ra_deg, dec_deg in result[1:]:
        previous_ra = unwrapped[-1][0]
        delta = (ra_deg - previous_ra + 180.0) % 360.0 - 180.0
        unwrapped.append((previous_ra + delta, dec_deg))

    def orientation(
        a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]
    ) -> float:
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    def crosses(
        a: tuple[float, float],
        b: tuple[float, float],
        c: tuple[float, float],
        d: tuple[float, float],
    ) -> bool:
        eps = 1e-12
        return (
            orientation(a, b, c) * orientation(a, b, d) < -eps
            and orientation(c, d, a) * orientation(c, d, b) < -eps
        )

    segments = list(zip(unwrapped, unwrapped[1:], strict=False))
    area2 = sum(a[0] * b[1] - b[0] * a[1] for a, b in segments)
    count = len(segments)
    for i, (a, b) in enumerate(segments):
        for j in range(i + 1, count):
            if j == i + 1 or (i == 0 and j == count - 1):
                continue
            c, d = segments[j]
            if crosses(a, b, c, d):
                raise ValueError(f"Magellanic contour polygon self-intersects in {source}")
    if abs(area2) <= 1e-12:
        raise ValueError(f"Magellanic contour polygon has zero area in {source}")
    return result


def load_magellanic_contours(
    path: str | Path = DEFAULT_DATA_PATH,
) -> tuple[MagellanicContour, ...]:
    """Load and validate the compact Gaia-derived contour FeatureCollection."""
    source_path = Path(path)
    try:
        data = json.loads(source_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid Magellanic contour GeoJSON {source_path}: {exc}") from exc
    if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
        raise ValueError(
            f"Magellanic contour data must be a GeoJSON FeatureCollection: {source_path}"
        )
    source = data.get("source")
    if not isinstance(source, dict) or source.get("license") != "ODbL-1.0":
        raise ValueError(
            f"Magellanic contour source must record its ODbL-1.0 provenance: {source_path}"
        )
    features = data.get("features")
    if not isinstance(features, list):
        raise ValueError(f"Magellanic contour FeatureCollection has no features: {source_path}")
    contours: list[MagellanicContour] = []
    ids: set[str] = set()
    found: set[tuple[str, int]] = set()
    for feature in features:
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise ValueError(f"malformed Magellanic contour feature in {source_path}")
        geometry = feature.get("geometry")
        props = feature.get("properties")
        if not isinstance(geometry, dict) or geometry.get("type") != "Polygon":
            raise ValueError(
                f"Magellanic contour must use GeoJSON Polygon geometry in {source_path}"
            )
        if not isinstance(props, dict):
            raise ValueError(f"Magellanic contour has no properties in {source_path}")
        contour_id = str(feature.get("id", ""))
        cloud_id = str(props.get("cloud_id", ""))
        dso_id = str(props.get("dso_id", ""))
        level = int(props.get("level", 0))
        if cloud_id not in _CLOUD_DSO_IDS or dso_id != _CLOUD_DSO_IDS.get(cloud_id):
            raise ValueError(
                f"Magellanic contour has an unknown cloud/DSO identity in {source_path}"
            )
        if contour_id in ids or (cloud_id, level) in found:
            raise ValueError(f"duplicate Magellanic contour id or level in {source_path}")
        ids.add(contour_id)
        found.add((cloud_id, level))
        contours.append(
            MagellanicContour(
                id=contour_id,
                cloud_id=cloud_id,
                dso_id=dso_id,
                level=level,
                points=_polygon_points(geometry.get("coordinates"), contour_id),
            )
        )
    if found != {(cloud, level) for cloud in ("LMC", "SMC") for level in (1, 2, 3)}:
        raise ValueError("Magellanic contours must contain levels 1–3 for both LMC and SMC")
    return tuple(sorted(contours, key=lambda contour: (contour.cloud_id, contour.level)))
