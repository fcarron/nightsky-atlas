"""Declination-band sky tiling.

Bands of constant height step from pole to pole with a fixed overlap, and each
band is filled with charts spaced in right ascension so that neighbouring
charts overlap by at least the configured amount.  Spacing is based on the
band edge nearest the equator, where a chart covers the least right ascension,
so coverage is guaranteed everywhere (``AGENTS.md`` sections 11 and M14).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from nightsky_atlas.astronomy.angles import angular_separation_deg
from nightsky_atlas.atlas.config import TilingConfig
from nightsky_atlas.chart.models import ChartDefinition
from nightsky_atlas.projection.base import ProjectionError
from nightsky_atlas.projection.stereographic import StereographicProjection

__all__ = [
    "CoverageReport",
    "TilingSpec",
    "coverage_report",
    "tile_sky",
    "with_neighbours",
]


@dataclass(frozen=True, slots=True)
class TilingSpec:
    """Resolved tiling parameters."""

    width_deg: float
    height_deg: float
    overlap_deg: float

    def __post_init__(self) -> None:
        if self.width_deg <= 0.0 or self.height_deg <= 0.0:
            raise ValueError("tiling width_deg and height_deg must be positive")
        if self.overlap_deg <= 0.0:
            raise ValueError("overlap_deg must be positive")
        if self.overlap_deg >= min(self.width_deg, self.height_deg):
            raise ValueError("overlap_deg must be smaller than the chart field")

    @classmethod
    def from_config(cls, config: TilingConfig) -> TilingSpec:
        return cls(
            width_deg=config.width_deg,
            height_deg=config.height_deg,
            overlap_deg=config.overlap_deg,
        )


def _band_centers(spec: TilingSpec) -> list[float]:
    half = spec.height_deg / 2.0
    max_center = 90.0 - half
    step = spec.height_deg - spec.overlap_deg
    centers: list[float] = []
    center = -max_center
    while center <= max_center + 1e-9:
        centers.append(center)
        center += step
    if centers[-1] < max_center - 1e-9:
        centers.append(max_center)
    return centers


def _charts_in_band(atlas_id: str, spec: TilingSpec, center_dec: float) -> list[ChartDefinition]:
    half = spec.height_deg / 2.0
    equatorward_edge = min(abs(center_dec - half), abs(center_dec + half))
    cos_dec = max(math.cos(math.radians(equatorward_edge)), 1e-6)
    ra_step = (spec.width_deg - spec.overlap_deg) / cos_dec
    count = max(1, math.ceil(360.0 / ra_step - 1e-9))
    return [
        ChartDefinition(
            id=f"{atlas_id}-T{index}",
            center_ra_deg=index * 360.0 / count,
            center_dec_deg=center_dec,
            width_deg=spec.width_deg,
            height_deg=spec.height_deg,
            atlas_id=atlas_id,
        )
        for index in range(count)
    ]


def tile_sky(atlas_id: str, spec: TilingSpec) -> tuple[ChartDefinition, ...]:
    """Generate deterministic chart definitions covering the whole sky."""
    charts: list[ChartDefinition] = []
    for center_dec in _band_centers(spec):
        charts.extend(_charts_in_band(atlas_id, spec, center_dec))
    numbered = [
        replace(chart, id=f"{atlas_id}-{index + 1:03d}")
        for index, chart in enumerate(charts)
    ]
    return tuple(numbered)


@dataclass(frozen=True, slots=True)
class CoverageReport:
    """Result of sampling the sky against a chart set."""

    sample_count: int
    gap_count: int
    gaps: tuple[tuple[float, float], ...]
    max_overlap: int

    @property
    def covers_all(self) -> bool:
        """Whether every sampled direction falls inside at least one chart."""
        return self.gap_count == 0

    @property
    def has_overlap(self) -> bool:
        """Whether at least one sampled direction lies in two or more charts."""
        return self.max_overlap >= 2


def coverage_report(
    charts: tuple[ChartDefinition, ...], *, step_deg: float = 2.0
) -> CoverageReport:
    """Sample the sphere and report uncovered directions and overlap."""
    if not charts:
        return CoverageReport(0, 0, (), 0)

    projections = {
        chart.id: StereographicProjection(chart.center_ra_deg, chart.center_dec_deg)
        for chart in charts
    }
    samples = 0
    gaps: list[tuple[float, float]] = []
    max_overlap = 0

    dec = -90.0 + step_deg / 2.0
    while dec < 90.0:
        ra = 0.0
        while ra < 360.0:
            samples += 1
            count = 0
            for chart in charts:
                half_height = chart.height_deg / 2.0
                if abs(dec - chart.center_dec_deg) > half_height + step_deg:
                    continue
                try:
                    point = projections[chart.id].project(ra, dec)
                except ProjectionError:
                    continue
                if (
                    abs(point.xi_deg) <= chart.width_deg / 2.0 + 1e-9
                    and abs(point.eta_deg) <= half_height + 1e-9
                ):
                    count += 1
            if count == 0:
                gaps.append((ra, dec))
            max_overlap = max(max_overlap, count)
            ra += step_deg
        dec += step_deg

    return CoverageReport(
        sample_count=samples,
        gap_count=len(gaps),
        gaps=tuple(gaps),
        max_overlap=max_overlap,
    )


def with_neighbours(
    charts: tuple[ChartDefinition, ...], tolerance_deg: float = 0.0
) -> tuple[ChartDefinition, ...]:
    """Assign N/S/E/W neighbour references between adjacent charts.

    East is increasing right ascension.  Charts are grouped by declination band
    (centre declination) and connected within a band by RA order and across
    bands by nearest angular separation.
    """
    bands = sorted({chart.center_dec_deg for chart in charts})
    band_index = {center: index for index, center in enumerate(bands)}
    by_band: dict[float, list[ChartDefinition]] = {
        center: sorted(
            (chart for chart in charts if chart.center_dec_deg == center),
            key=lambda chart: chart.center_ra_deg,
        )
        for center in bands
    }

    def nearest(source: ChartDefinition, candidates: list[ChartDefinition]) -> ChartDefinition:
        return min(
            candidates,
            key=lambda chart: angular_separation_deg(
                source.center_ra_deg,
                source.center_dec_deg,
                chart.center_ra_deg,
                chart.center_dec_deg,
            ),
        )

    result: list[ChartDefinition] = []
    for chart in charts:
        arc = by_band[chart.center_dec_deg]
        position = arc.index(chart)
        neighbours: list[tuple[str, str]] = [
            ("E", arc[(position + 1) % len(arc)].id),
            ("W", arc[(position - 1) % len(arc)].id),
        ]
        index = band_index[chart.center_dec_deg]
        if index + 1 < len(bands):
            neighbours.append(("N", nearest(chart, by_band[bands[index + 1]]).id))
        if index - 1 >= 0:
            neighbours.append(("S", nearest(chart, by_band[bands[index - 1]]).id))
        result.append(replace(chart, neighbours=tuple(neighbours)))
    return tuple(result)