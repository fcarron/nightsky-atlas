"""Geometric relationships between detail-chart fields and main charts."""

from __future__ import annotations

import math
from dataclasses import dataclass

from nightsky_atlas.atlas.config import DetailChartConfig
from nightsky_atlas.chart.models import ChartDefinition
from nightsky_atlas.projection.base import ProjectionError
from nightsky_atlas.projection.stereographic import StereographicProjection

__all__ = [
    "DetailChartOverlap",
    "detail_chart_contains_position",
    "detail_chart_overlaps_main_chart",
    "detail_chart_parent_ids",
    "detail_footprint_in_chart",
]

_BOUNDARY_SAMPLES_PER_EDGE = 32
_MIN_OVERLAP_AREA_DEG2 = 0.01
_MIN_DETAIL_AREA_FRACTION = 0.01
_GEOMETRY_TOLERANCE_DEG = 1e-9


@dataclass(frozen=True, slots=True)
class DetailChartOverlap:
    """Measured intersection of a detail footprint with a main chart."""

    area_deg2: float
    detail_area_fraction: float


def detail_footprint_in_chart(
    detail: DetailChartConfig,
    chart: ChartDefinition,
) -> tuple[tuple[float, float], ...]:
    """Return the detail's projected boundary in a main chart's tangent plane."""
    detail_projection = StereographicProjection(detail.center_ra_deg, detail.center_dec_deg)
    chart_projection = StereographicProjection(chart.center_ra_deg, chart.center_dec_deg)
    half_width = detail.width_deg / 2.0
    half_height = detail.height_deg / 2.0
    offsets: list[tuple[float, float]] = []
    for index in range(_BOUNDARY_SAMPLES_PER_EDGE):
        fraction = index / _BOUNDARY_SAMPLES_PER_EDGE
        offsets.append((-half_width + 2.0 * half_width * fraction, half_height))
    for index in range(_BOUNDARY_SAMPLES_PER_EDGE):
        fraction = index / _BOUNDARY_SAMPLES_PER_EDGE
        offsets.append((half_width, half_height - 2.0 * half_height * fraction))
    for index in range(_BOUNDARY_SAMPLES_PER_EDGE):
        fraction = index / _BOUNDARY_SAMPLES_PER_EDGE
        offsets.append((half_width - 2.0 * half_width * fraction, -half_height))
    for index in range(_BOUNDARY_SAMPLES_PER_EDGE):
        fraction = index / _BOUNDARY_SAMPLES_PER_EDGE
        offsets.append((-half_width, -half_height + 2.0 * half_height * fraction))

    return tuple(
        (
            point.xi_deg,
            point.eta_deg,
        )
        for xi_deg, eta_deg in offsets
        for point in (chart_projection.project(*detail_projection.inverse(xi_deg, eta_deg)),)
    )


def detail_chart_contains_position(
    detail: DetailChartConfig,
    ra_deg: float,
    dec_deg: float,
    *,
    tolerance_deg: float = _GEOMETRY_TOLERANCE_DEG,
) -> bool:
    """Return whether a sky position lies inside the actual detail field."""
    try:
        point = StereographicProjection(detail.center_ra_deg, detail.center_dec_deg).project(
            ra_deg, dec_deg
        )
    except ProjectionError:
        return False
    return (
        abs(point.xi_deg) <= detail.width_deg / 2.0 + tolerance_deg
        and abs(point.eta_deg) <= detail.height_deg / 2.0 + tolerance_deg
    )


def detail_chart_overlaps_main_chart(
    detail: DetailChartConfig,
    chart: ChartDefinition,
) -> DetailChartOverlap | None:
    """Return meaningful projected overlap, excluding edge-only contact.

    The detail boundary is sampled in its own stereographic plane, projected
    into the main chart plane, then clipped to the main chart's actual field
    rectangle. A relationship requires at least 1% of the detail footprint
    and 0.01 square projected degrees of overlap.
    """
    center_distance = _angular_distance_deg(
        detail.center_ra_deg,
        detail.center_dec_deg,
        chart.center_ra_deg,
        chart.center_dec_deg,
    )
    if center_distance > _field_angular_radius(detail.width_deg, detail.height_deg) + (
        _field_angular_radius(chart.width_deg, chart.height_deg)
    ):
        return None
    try:
        footprint = detail_footprint_in_chart(detail, chart)
    except ProjectionError:
        return None
    detail_area = _polygon_area(footprint)
    if detail_area <= 0.0:
        return None
    clipped = _clip_to_rect(
        footprint,
        left=-chart.width_deg / 2.0,
        right=chart.width_deg / 2.0,
        bottom=-chart.height_deg / 2.0,
        top=chart.height_deg / 2.0,
    )
    overlap_area = _polygon_area(clipped)
    fraction = overlap_area / detail_area
    if overlap_area < _MIN_OVERLAP_AREA_DEG2 or fraction < _MIN_DETAIL_AREA_FRACTION:
        return None
    return DetailChartOverlap(overlap_area, fraction)


def detail_chart_parent_ids(
    details: tuple[DetailChartConfig, ...],
    charts: tuple[ChartDefinition, ...],
) -> dict[str, tuple[str, ...]]:
    """Map each detail chart to all meaningfully overlapping main charts.

    Larger overlaps come first, with chart-definition order as the stable tie
    breaker. No parent identifiers are stored in the detail configuration.
    """
    relations: dict[str, tuple[str, ...]] = {}
    for detail in details:
        overlaps = [
            (chart.id, overlap.detail_area_fraction, index)
            for index, chart in enumerate(charts)
            if (overlap := detail_chart_overlaps_main_chart(detail, chart)) is not None
        ]
        overlaps.sort(key=lambda item: (-item[1], item[2]))
        relations[detail.id] = tuple(chart_id for chart_id, _fraction, _index in overlaps)
    return relations


def _polygon_area(points: tuple[tuple[float, float], ...]) -> float:
    if len(points) < 3:
        return 0.0
    return (
        abs(
            sum(
                points[index][0] * points[(index + 1) % len(points)][1]
                - points[(index + 1) % len(points)][0] * points[index][1]
                for index in range(len(points))
            )
        )
        / 2.0
    )


def _field_angular_radius(width_deg: float, height_deg: float) -> float:
    projected_radius_rad = math.radians(math.hypot(width_deg / 2.0, height_deg / 2.0))
    return math.degrees(2.0 * math.atan(projected_radius_rad / 2.0))


def _angular_distance_deg(
    ra1_deg: float, dec1_deg: float, ra2_deg: float, dec2_deg: float
) -> float:
    ra1, dec1, ra2, dec2 = map(math.radians, (ra1_deg, dec1_deg, ra2_deg, dec2_deg))
    cosine = math.sin(dec1) * math.sin(dec2) + math.cos(dec1) * math.cos(dec2) * math.cos(ra1 - ra2)
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def _clip_to_rect(
    points: tuple[tuple[float, float], ...],
    *,
    left: float,
    right: float,
    bottom: float,
    top: float,
) -> tuple[tuple[float, float], ...]:
    clipped = points
    edges = (
        (lambda point: point[0] >= left, lambda start, end: _intersect_x(start, end, left)),
        (lambda point: point[0] <= right, lambda start, end: _intersect_x(start, end, right)),
        (lambda point: point[1] >= bottom, lambda start, end: _intersect_y(start, end, bottom)),
        (lambda point: point[1] <= top, lambda start, end: _intersect_y(start, end, top)),
    )
    for inside, intersection in edges:
        if not clipped:
            break
        output: list[tuple[float, float]] = []
        previous = clipped[-1]
        previous_inside = inside(previous)
        for current in clipped:
            current_inside = inside(current)
            if current_inside:
                if not previous_inside:
                    output.append(intersection(previous, current))
                output.append(current)
            elif previous_inside:
                output.append(intersection(previous, current))
            previous = current
            previous_inside = current_inside
        clipped = tuple(output)
    return clipped


def _intersect_x(
    start: tuple[float, float], end: tuple[float, float], x: float
) -> tuple[float, float]:
    dx = end[0] - start[0]
    if math.isclose(dx, 0.0, abs_tol=1e-15):
        return x, start[1]
    fraction = (x - start[0]) / dx
    return x, start[1] + fraction * (end[1] - start[1])


def _intersect_y(
    start: tuple[float, float], end: tuple[float, float], y: float
) -> tuple[float, float]:
    dy = end[1] - start[1]
    if math.isclose(dy, 0.0, abs_tol=1e-15):
        return start[0], y
    fraction = (y - start[1]) / dy
    return start[0] + fraction * (end[0] - start[0]), y
