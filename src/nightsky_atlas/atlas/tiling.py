"""Sky tiling for complete atlases.

Two strategies share one coverage validator:

- **Declination-ring tiling** (Standard v0.1, ``AGENTS.md`` sections 11 and M14):
  explicit ring-centre declinations are filled with charts spaced in right
  ascension, alternate rings are staggered by half a chart, and optional polar
  caps close the sky.  Per-ring chart counts are start values that the tiler
  raises until each ring covers its declination slice at every right ascension.
- **Legacy declination-band tiling**: bands of constant height step from pole to
  pole with a fixed overlap.

Because the chart field is a rectangle in the tangent plane, its declination
extent shrinks away from the central meridian.  Coverage and overlap are
therefore *validated numerically* (``coverage_report``) instead of trusting a
``cos(dec)`` approximation.
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
    "NeighbourOverlapReport",
    "TilingSpec",
    "coverage_report",
    "neighbour_overlap_report",
    "resolve_ring_counts",
    "tile_sky",
    "with_neighbours",
]

_CONTAIN_EPSILON = 1e-9


@dataclass(frozen=True, slots=True)
class TilingSpec:
    """Resolved tiling parameters.

    ``overlap_deg`` selects the legacy band mode; a non-empty
    ``declination_centers`` selects ring mode.  ``chart_counts`` holds per-ring
    *start* counts (empty means "derive from geometry").  ``vertical_overlap_deg``
    and ``horizontal_overlap_min_deg`` are design targets used for diagnostics.
    """

    width_deg: float
    height_deg: float
    overlap_deg: float | None = None
    coverage_step_deg: float = 1.0
    declination_centers: tuple[float, ...] = ()
    chart_counts: tuple[int, ...] = ()
    polar_caps: bool = False
    vertical_overlap_deg: float = 2.0
    horizontal_overlap_min_deg: float = 1.5
    stagger_ra_centers: bool = False
    auto_adjust_counts: bool = True

    def __post_init__(self) -> None:
        if self.width_deg <= 0.0 or self.height_deg <= 0.0:
            raise ValueError("tiling width_deg and height_deg must be positive")
        if self.overlap_deg is None and not self.declination_centers:
            raise ValueError(
                "tiling requires overlap_deg (band mode) or declination_centers "
                "(ring mode)"
            )
        if self.overlap_deg is not None:
            if self.overlap_deg <= 0.0:
                raise ValueError("overlap_deg must be positive")
            if self.overlap_deg >= min(self.width_deg, self.height_deg):
                raise ValueError("overlap_deg must be smaller than the chart field")
        for center in self.declination_centers:
            if not -90.0 < center < 90.0:
                raise ValueError(
                    "declination_centers must lie strictly inside (-90, 90)"
                )
        if len(set(self.declination_centers)) != len(self.declination_centers):
            raise ValueError("declination_centers must be unique")
        if self.chart_counts and len(self.chart_counts) != len(self.declination_centers):
            raise ValueError("chart_counts must have one entry per declination_center")
        if any(count < 1 for count in self.chart_counts):
            raise ValueError("chart_counts entries must be positive")
        if self.polar_caps and not self.declination_centers:
            raise ValueError("polar_caps requires declination_centers")

    @property
    def is_ring_mode(self) -> bool:
        """Whether this spec uses explicit declination rings."""
        return bool(self.declination_centers)

    @classmethod
    def from_config(cls, config: TilingConfig) -> TilingSpec:
        return cls(
            width_deg=config.width_deg,
            height_deg=config.height_deg,
            overlap_deg=config.overlap_deg,
            coverage_step_deg=config.coverage_step_deg,
            declination_centers=config.declination_centers,
            chart_counts=config.chart_counts,
            polar_caps=config.polar_caps,
            vertical_overlap_deg=config.target_overlap.vertical_deg,
            horizontal_overlap_min_deg=config.target_overlap.horizontal_min_deg,
            stagger_ra_centers=config.stagger_ra_centers,
            auto_adjust_counts=config.auto_adjust_counts,
        )


def _contains(
    center_ra_deg: float,
    center_dec_deg: float,
    ra_deg: float,
    dec_deg: float,
    width_deg: float,
    height_deg: float,
) -> bool:
    """Whether a sky direction lies inside a chart field (inline projection)."""
    center_dec_rad = math.radians(center_dec_deg)
    dec_rad = math.radians(dec_deg)
    delta_ra = math.radians((ra_deg - center_ra_deg + 180.0) % 360.0 - 180.0)
    cos_c = math.sin(center_dec_rad) * math.sin(dec_rad) + math.cos(
        center_dec_rad
    ) * math.cos(dec_rad) * math.cos(delta_ra)
    denominator = 1.0 + cos_c
    if denominator <= 1e-12:
        return False
    k = 2.0 / denominator
    xi = k * math.cos(dec_rad) * math.sin(delta_ra)
    eta = k * (
        math.cos(center_dec_rad) * math.sin(dec_rad)
        - math.sin(center_dec_rad) * math.cos(dec_rad) * math.cos(delta_ra)
    )
    return (
        abs(math.degrees(xi)) <= width_deg / 2.0 + _CONTAIN_EPSILON
        and abs(math.degrees(eta)) <= height_deg / 2.0 + _CONTAIN_EPSILON
    )


def _ra_half_width_deg(
    center_dec_deg: float, dec_deg: float, width_deg: float, height_deg: float
) -> float:
    """Largest RA offset from the central meridian covered at ``dec_deg``.

    Scans outward from the central meridian and returns the first RA offset that
    leaves the field, so the result is the covered interval containing the
    chart centre even if the declination parallel crosses the field twice.
    """
    if not _contains(0.0, center_dec_deg, 0.0, dec_deg, width_deg, height_deg):
        return 0.0
    step = 0.5
    offset = 0.0
    while offset < 180.0:
        probe = min(offset + step, 180.0)
        if not _contains(0.0, center_dec_deg, probe, dec_deg, width_deg, height_deg):
            low, high = offset, probe
            for _ in range(40):
                mid = (low + high) / 2.0
                if _contains(0.0, center_dec_deg, mid, dec_deg, width_deg, height_deg):
                    low = mid
                else:
                    high = mid
            return low
        offset = probe
    return 180.0


def _polar_cap_reach_dec(width_deg: float, height_deg: float) -> float:
    """Lowest declination a polar cap covers in *every* direction.

    A polar chart is a tangent-plane rectangle centred on the pole; the largest
    inscribed circle has the smaller half-field as radius.  The angular reach of
    that radius follows from the stereographic relation
    ``projected_radius = 2 tan(c / 2)``.
    """
    half = min(width_deg, height_deg) / 2.0
    angular = 2.0 * math.degrees(math.atan(math.radians(half) / 2.0))
    return 90.0 - angular


def _slice_bounds(spec: TilingSpec) -> tuple[tuple[float, float], ...]:
    """Declination interval each ring must cover on its own.

    Interior boundaries are the midpoints between adjacent ring centres; the
    outer boundaries are the polar caps' guaranteed reach (or the pole itself
    when no caps are configured).
    """
    centers = sorted(spec.declination_centers)
    if spec.polar_caps:
        reach = _polar_cap_reach_dec(spec.width_deg, spec.height_deg)
    else:
        reach = 90.0
    bounds: list[tuple[float, float]] = []
    for index, center in enumerate(centers):
        low = -reach if index == 0 else (centers[index - 1] + center) / 2.0
        high = reach if index == len(centers) - 1 else (center + centers[index + 1]) / 2.0
        bounds.append((low, high))
    return tuple(bounds)


def _required_ring_count(
    spec: TilingSpec, center_dec_deg: float, low_dec_deg: float, high_dec_deg: float
) -> int | None:
    """Smallest chart count whose ring covers ``[low, high]`` at every RA.

    Samples the declination slice, finds the narrowest right-ascension half
    width, and converts it to a chart count.  ``None`` means the ring cannot
    reach the slice with this field size.
    """
    dec = low_dec_deg
    narrowest = math.inf
    while dec <= high_dec_deg + 1e-9:
        half = _ra_half_width_deg(center_dec_deg, dec, spec.width_deg, spec.height_deg)
        if half <= 0.0:
            return None
        narrowest = min(narrowest, half)
        dec += 0.1
    if narrowest <= 0.0 or not math.isfinite(narrowest):
        return None
    return math.ceil(360.0 / (2.0 * narrowest) - 1e-9)


def resolve_ring_counts(spec: TilingSpec) -> tuple[int, ...]:
    """Resolve the chart count for each declination ring.

    Start counts come from ``chart_counts`` when present.  With
    ``auto_adjust_counts`` the count is raised to the geometry minimum so the
    ring covers its declination slice at every right ascension.
    """
    if not spec.is_ring_mode:
        raise ValueError("resolve_ring_counts requires declination_centers")
    centers = sorted(spec.declination_centers)
    bounds = _slice_bounds(spec)
    resolved: list[int] = []
    for index, center in enumerate(centers):
        start = spec.chart_counts[index] if spec.chart_counts else 1
        required = _required_ring_count(spec, center, *bounds[index])
        if spec.auto_adjust_counts:
            if required is None:
                raise ValueError(
                    f"declination ring {center:g} cannot cover its slice with a "
                    f"{spec.width_deg:g} x {spec.height_deg:g} deg field"
                )
            resolved.append(max(start, required))
        else:
            resolved.append(start)
    return tuple(resolved)


def _ring_phase(spec: TilingSpec, ring_index: int) -> float:
    if spec.stagger_ra_centers and ring_index % 2 == 1:
        return 0.5
    return 0.0


def _charts_in_ring(
    spec: TilingSpec, center_dec_deg: float, count: int, phase: float
) -> list[ChartDefinition]:
    return [
        ChartDefinition(
            id=f"ring-{center_dec_deg:+.0f}-{index}",
            center_ra_deg=((index + phase) * 360.0 / count) % 360.0,
            center_dec_deg=center_dec_deg,
            width_deg=spec.width_deg,
            height_deg=spec.height_deg,
        )
        for index in range(count)
    ]


def _tile_rings(atlas_id: str, spec: TilingSpec) -> list[ChartDefinition]:
    """Tile declination rings north to south.

    The chart order is the reading order of the atlas: the north polar cap
    first, then each declination ring from the north down to the south, and the
    south polar cap last.  Within a ring the charts run in increasing right
    ascension (0h -> 24h); the per-ring RA stagger is a half chart and never
    breaks that order.  Phases are tied to the *ascending* ring index so the
    stagger pattern is independent of the reading direction.
    """
    centers = sorted(spec.declination_centers)
    counts = resolve_ring_counts(spec)
    charts: list[ChartDefinition] = []
    if spec.polar_caps:
        charts.append(
            ChartDefinition(
                id="ring-north-cap",
                center_ra_deg=0.0,
                center_dec_deg=90.0,
                width_deg=spec.width_deg,
                height_deg=spec.height_deg,
            )
        )
    for index in reversed(range(len(centers))):
        charts.extend(
            _charts_in_ring(
                spec, centers[index], counts[index], _ring_phase(spec, index)
            )
        )
    if spec.polar_caps:
        charts.append(
            ChartDefinition(
                id="ring-south-cap",
                center_ra_deg=0.0,
                center_dec_deg=-90.0,
                width_deg=spec.width_deg,
                height_deg=spec.height_deg,
            )
        )
    return charts


def _band_centers(spec: TilingSpec) -> list[float]:
    half = spec.height_deg / 2.0
    max_center = 90.0 - half
    assert spec.overlap_deg is not None
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
    assert spec.overlap_deg is not None
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
    if spec.is_ring_mode:
        charts = _tile_rings(atlas_id, spec)
    else:
        charts = []
        for center_dec in _band_centers(spec):
            charts.extend(_charts_in_band(atlas_id, spec, center_dec))
    numbered = [
        replace(chart, id=f"{atlas_id}-{index + 1:03d}")
        for index, chart in enumerate(charts)
    ]
    return tuple(numbered)


@dataclass(frozen=True, slots=True)
class CoverageReport:
    """Result of sampling the sky against a chart set.

    ``min_overlap``/``max_overlap`` are the smallest/largest number of charts
    covering a sampled direction; ``overlap_histogram`` counts samples by that
    number.  A gap is a sampled direction covered by no chart.
    """

    sample_count: int
    gap_count: int
    gaps: tuple[tuple[float, float], ...]
    min_overlap: int
    max_overlap: int
    overlap_histogram: tuple[tuple[int, int], ...]

    @property
    def covers_all(self) -> bool:
        """Whether every sampled direction falls inside at least one chart."""
        return self.gap_count == 0

    @property
    def has_overlap(self) -> bool:
        """Whether at least one sampled direction lies in two or more charts."""
        return self.max_overlap >= 2

    @property
    def single_overlap_count(self) -> int:
        """Number of samples covered by exactly one chart (seam-only coverage)."""
        return dict(self.overlap_histogram).get(1, 0)


def coverage_report(
    charts: tuple[ChartDefinition, ...], *, step_deg: float = 2.0
) -> CoverageReport:
    """Sample the sphere and report uncovered directions and overlap."""
    if not charts:
        return CoverageReport(0, 0, (), 0, 0, ())

    projections = {
        chart.id: StereographicProjection(chart.center_ra_deg, chart.center_dec_deg)
        for chart in charts
    }
    samples = 0
    gaps: list[tuple[float, float]] = []
    histogram: dict[int, int] = {}
    min_overlap = math.inf
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
                    abs(point.xi_deg) <= chart.width_deg / 2.0 + _CONTAIN_EPSILON
                    and abs(point.eta_deg) <= half_height + _CONTAIN_EPSILON
                ):
                    count += 1
            histogram[count] = histogram.get(count, 0) + 1
            if count == 0:
                gaps.append((ra, dec))
            min_overlap = min(min_overlap, count)
            max_overlap = max(max_overlap, count)
            ra += step_deg
        dec += step_deg

    return CoverageReport(
        sample_count=samples,
        gap_count=len(gaps),
        gaps=tuple(gaps),
        min_overlap=0 if not math.isfinite(min_overlap) else min_overlap,
        max_overlap=max_overlap,
        overlap_histogram=tuple(sorted(histogram.items())),
    )


@dataclass(frozen=True, slots=True)
class NeighbourOverlapReport:
    """Whether declared neighbour charts actually share covered sky."""

    checked_pairs: int
    missing_overlaps: tuple[tuple[str, str], ...]

    @property
    def is_complete(self) -> bool:
        return not self.missing_overlaps


def neighbour_overlap_report(
    charts: tuple[ChartDefinition, ...], *, step_deg: float = 0.5
) -> NeighbourOverlapReport:
    """Verify every N/S/E/W neighbour pair shares at least one sky sample.

    Charts without neighbours are ignored.  ``missing_overlaps`` lists
    ``(chart_id, direction)`` entries whose declared neighbour never appears in
    the same sampled direction.
    """
    if not charts:
        return NeighbourOverlapReport(0, ())
    by_id = {chart.id: chart for chart in charts}
    projections = {
        chart.id: StereographicProjection(chart.center_ra_deg, chart.center_dec_deg)
        for chart in charts
    }
    pairs: set[frozenset[str]] = set()
    dec = -90.0 + step_deg / 2.0
    while dec < 90.0:
        ra = 0.0
        while ra < 360.0:
            covering: list[str] = []
            for chart in charts:
                if abs(dec - chart.center_dec_deg) > chart.height_deg / 2.0 + step_deg:
                    continue
                try:
                    point = projections[chart.id].project(ra, dec)
                except ProjectionError:
                    continue
                if (
                    abs(point.xi_deg) <= chart.width_deg / 2.0 + _CONTAIN_EPSILON
                    and abs(point.eta_deg) <= chart.height_deg / 2.0 + _CONTAIN_EPSILON
                ):
                    covering.append(chart.id)
            for index, first in enumerate(covering):
                for second in covering[index + 1 :]:
                    pairs.add(frozenset((first, second)))
            ra += step_deg
        dec += step_deg

    checked = 0
    missing: list[tuple[str, str]] = []
    for chart in charts:
        for direction, neighbour_id in chart.neighbours:
            if neighbour_id not in by_id:
                missing.append((chart.id, direction))
                continue
            checked += 1
            if frozenset((chart.id, neighbour_id)) not in pairs:
                missing.append((chart.id, direction))
    return NeighbourOverlapReport(checked, tuple(missing))


def with_neighbours(
    charts: tuple[ChartDefinition, ...], tolerance_deg: float = 0.0
) -> tuple[ChartDefinition, ...]:
    """Assign N/S/E/W neighbour references between adjacent charts.

    East is increasing right ascension.  Charts are grouped by declination band
    (centre declination) and connected within a band by RA order and across
    bands by nearest angular separation.  Single-chart rings (the polar caps)
    have no east/west neighbour.
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
        neighbours: list[tuple[str, str]] = []
        if len(arc) > 1:
            neighbours.append(("E", arc[(position + 1) % len(arc)].id))
            neighbours.append(("W", arc[(position - 1) % len(arc)].id))
        index = band_index[chart.center_dec_deg]
        if index + 1 < len(bands):
            neighbours.append(("N", nearest(chart, by_band[bands[index + 1]]).id))
        if index - 1 >= 0:
            neighbours.append(("S", nearest(chart, by_band[bands[index - 1]]).id))
        result.append(replace(chart, neighbours=tuple(neighbours)))
    return tuple(result)
