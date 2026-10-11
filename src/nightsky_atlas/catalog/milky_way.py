"""Milky Way brightness-contour source geometry."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = ["DEFAULT_DATA_PATH", "MilkyWayContour", "load_milky_way_contours"]

DEFAULT_DATA_PATH = Path("data/third_party/d3-celestial/mw.json")
_LEVEL = re.compile(r"^ol([1-5])$")


@dataclass(frozen=True, slots=True)
class MilkyWayContour:
    """One open or closed contour ring in J2000 equatorial coordinates."""

    id: str
    level: int
    points: tuple[tuple[float, float], ...]
    polygon_id: str | None = None
    is_hole: bool = False
    edge_midpoint_vectors: tuple[tuple[float, float, float], ...] = field(init=False, repr=False)
    max_edge_half_angle_deg: float = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("Milky Way contour id must not be blank")
        if self.level not in range(1, 6):
            raise ValueError("Milky Way contour level must be between 1 and 5")
        if len(self.points) < 2:
            raise ValueError("a Milky Way contour needs at least two points")
        for ra_deg, dec_deg in self.points:
            if not math.isfinite(ra_deg) or not math.isfinite(dec_deg):
                raise ValueError("Milky Way contour coordinates must be finite")
            if not -90.0 <= dec_deg <= 90.0:
                raise ValueError("Milky Way contour declination must be in [-90, 90]")
        vectors = tuple(_unit_vector(ra, dec) for ra, dec in self.points)
        midpoints: list[tuple[float, float, float]] = []
        max_half_angle = 0.0
        for first, second in zip(vectors, vectors[1:], strict=False):
            midpoint = tuple(a + b for a, b in zip(first, second, strict=True))
            norm = math.sqrt(sum(value * value for value in midpoint))
            if norm <= 1e-15:
                midpoint = first
                half_angle = 180.0
            else:
                midpoint = tuple(value / norm for value in midpoint)
                cosine = max(-1.0, min(1.0, sum(a * b for a, b in zip(first, second, strict=True))))
                half_angle = math.degrees(math.acos(cosine)) / 2.0
            midpoints.append(midpoint)
            max_half_angle = max(max_half_angle, half_angle)
        object.__setattr__(self, "edge_midpoint_vectors", tuple(midpoints))
        object.__setattr__(self, "max_edge_half_angle_deg", max_half_angle)


def _unit_vector(ra_deg: float, dec_deg: float) -> tuple[float, float, float]:
    ra = math.radians(ra_deg)
    dec = math.radians(dec_deg)
    cos_dec = math.cos(dec)
    return cos_dec * math.cos(ra), cos_dec * math.sin(ra), math.sin(dec)


def _coordinates(raw: Any, source: str) -> tuple[tuple[float, float], ...]:
    if not isinstance(raw, list):
        raise ValueError(f"Milky Way ring must be a coordinate list in {source}")
    points: list[tuple[float, float]] = []
    for pair in raw:
        if not isinstance(pair, (list, tuple)) or len(pair) < 2:
            raise ValueError(f"malformed Milky Way coordinate in {source}: {pair!r}")
        longitude, dec_deg = float(pair[0]), float(pair[1])
        if not math.isfinite(longitude) or not math.isfinite(dec_deg):
            raise ValueError(f"non-finite Milky Way coordinate in {source}")
        if not -180.0 <= longitude <= 180.0 or not -90.0 <= dec_deg <= 90.0:
            raise ValueError(f"Milky Way coordinate outside GeoJSON bounds in {source}")
        ra_deg = longitude % 360.0
        points.append((ra_deg, dec_deg))
    if len(points) < 2:
        raise ValueError(f"Milky Way ring needs at least two coordinates in {source}")
    if points[0] != points[-1]:
        points.append(points[0])
    return tuple(points)


def load_milky_way_contours(
    path: str | Path = DEFAULT_DATA_PATH,
) -> tuple[MilkyWayContour, ...]:
    """Load the five d3-celestial GeoJSON outline levels."""
    source_path = Path(path)
    try:
        data = json.loads(source_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid Milky Way GeoJSON {source_path}: {exc}") from exc
    if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
        raise ValueError(f"Milky Way data must be a GeoJSON FeatureCollection: {source_path}")
    features = data.get("features")
    if not isinstance(features, list):
        raise ValueError(f"Milky Way FeatureCollection has no feature list: {source_path}")

    contours: list[MilkyWayContour] = []
    found_levels: set[int] = set()
    for feature in features:
        if not isinstance(feature, dict):
            raise ValueError(f"malformed Milky Way feature in {source_path}")
        feature_id = str(feature.get("id", ""))
        match = _LEVEL.fullmatch(feature_id)
        if match is None:
            raise ValueError(f"unknown Milky Way level id {feature_id!r} in {source_path}")
        level = int(match.group(1))
        found_levels.add(level)
        geometry = feature.get("geometry")
        if not isinstance(geometry, dict) or geometry.get("type") != "MultiPolygon":
            raise ValueError(f"Milky Way feature {feature_id} must be a MultiPolygon")
        polygons = geometry.get("coordinates")
        if not isinstance(polygons, list):
            raise ValueError(f"Milky Way feature {feature_id} has malformed polygons")
        for polygon_index, polygon in enumerate(polygons):
            if not isinstance(polygon, list):
                raise ValueError(f"Milky Way polygon is malformed in {feature_id}")
            polygon_id = f"milky-way:{level}:{polygon_index}"
            for ring_index, ring in enumerate(polygon):
                contour_id = f"milky-way:{level}:{polygon_index}:{ring_index}"
                contours.append(
                    MilkyWayContour(
                        id=contour_id,
                        level=level,
                        points=_coordinates(ring, contour_id),
                        polygon_id=polygon_id,
                        is_hole=ring_index > 0,
                    )
                )
    if found_levels != set(range(1, 6)):
        raise ValueError(f"Milky Way data must contain levels 1–5, got {sorted(found_levels)}")
    return tuple(contours)
