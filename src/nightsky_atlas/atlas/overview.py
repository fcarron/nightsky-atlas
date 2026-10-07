"""Whole-sky overview map construction.

An :class:`OverviewMap` is the projected, ready-to-draw content of a
pole-centred finder map: the simplified constellation background, the bright
stars, one clean **cell** per chart (with a visible chart code) and a light
coordinate grid.  It is a *presentation* structure built from chart geometry
and the constellation fixture; it never mutates astronomical objects or chart
definitions (``AGENTS.md`` section 5).

Two consumers share the same structure:

- the front-of-atlas **overview pages**, one for the northern and one for the
  southern sky. Equatorial charts appear on both hemisphere pages;
- the optional per-chart **locator inset**, which reuses the hemisphere map
  containing the current chart.

Charts overlap by design (star-hop overlap), so drawing every chart field
rectangle produces a tangle of near-parallel lines.  Instead each chart is
represented by the declination-ring / right-ascension sector around its centre:
the band boundaries lie midway between adjacent ring centres and the RA
boundaries midway between adjacent chart centres. Every chart therefore
contributes one trapezoidal cell per hemisphere it covers. Adjacent cells
share a single boundary, and there is no overlap within a hemisphere. This is
an index schematic, not a reproduction of the chart fields; constellation
lines are drawn as straight chords so the whole overview reads as a clean line
drawing.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from nightsky_atlas.atlas.config import EditionConfig, default_edition
from nightsky_atlas.catalog.constellations import (
    ConstellationCatalogue,
    ConstellationSegment,
    constellation_name,
)
from nightsky_atlas.catalog.models import Star
from nightsky_atlas.chart.models import ChartDefinition
from nightsky_atlas.chart.presentation import presentation_for
from nightsky_atlas.projection.azimuthal import AzimuthalEquidistantProjection
from nightsky_atlas.projection.base import ChartPoint

__all__ = [
    "NORTH",
    "SOUTH",
    "OverviewCell",
    "OverviewMap",
    "OverviewName",
    "OverviewSegment",
    "OverviewStar",
    "build_overview",
    "hemisphere_for",
    "overview_centres",
]

NORTH = "north"
SOUTH = "south"

# RA origins chosen so right ascension zero reads at the top of both disks;
# the handedness then differs between the hemispheres, as it must when looking
# at opposite sides of the celestial sphere.
_OVERVIEW_CENTRES: dict[str, tuple[float, float]] = {
    NORTH: (180.0, 90.0),
    SOUTH: (0.0, -90.0),
}
_HEMISPHERE_LABELS: dict[str, str] = {
    NORTH: "Northern sky",
    SOUTH: "Southern sky",
}

_VISIBLE_EPSILON_DEG = 1e-6
_LABEL_MARGIN_DEG = 1.5
# Trapezoidal cell boundaries: declination arcs are sampled at this step and
# the polar-cap ring is drawn with this many segments.
_SECTOR_ARC_STEP_DEG = 3.0
_RING_SEGMENTS = 144
# A constellation segment is drawn only when both endpoints are at most this
# far beyond the hemisphere rim, so the straight chord is a valid schematic.
_SEGMENT_MARGIN_DEG = 15.0


def overview_centres(hemisphere: str) -> tuple[float, float]:
    """Return the ``(ra_deg, dec_deg)`` projection centre for a hemisphere."""
    try:
        return _OVERVIEW_CENTRES[hemisphere]
    except KeyError:
        raise ValueError(f"unknown hemisphere {hemisphere!r}") from None


def hemisphere_for(dec_deg: float) -> str:
    """Return the overview hemisphere containing a declination."""
    return NORTH if dec_deg >= 0.0 else SOUTH


@dataclass(frozen=True, slots=True)
class OverviewSegment:
    """A projected polyline run on the overview plane, in degrees."""

    points: tuple[ChartPoint, ...]
    weight: str = "normal"


@dataclass(frozen=True, slots=True)
class OverviewName:
    """A constellation name positioned on the overview plane."""

    text: str
    point: ChartPoint


@dataclass(frozen=True, slots=True)
class OverviewCell:
    """One chart's index cell on the overview plane.

    ``polygon`` is the chart's trapezoidal ring/RA-sector cell: declination
    boundaries lie midway between adjacent rings and RA boundaries midway
    between adjacent chart centres in a ring.  Adjacent cells share a single
    boundary, so each chart contributes exactly one outline and overlapping
    chart fields never appear.  ``label_point`` is the projected chart centre.
    """

    chart_id: str
    chart_code: str
    polygon: tuple[ChartPoint, ...]
    label_point: ChartPoint | None


@dataclass(frozen=True, slots=True)
class OverviewStar:
    """A bright star projected onto the overview plane."""

    point: ChartPoint
    magnitude: float


@dataclass(frozen=True, slots=True)
class OverviewMap:
    """A complete projected overview for one hemisphere."""

    hemisphere: str
    edition_name: str
    title: str
    center_ra_deg: float
    center_dec_deg: float
    radius_deg: float
    cells: tuple[OverviewCell, ...]
    stars: tuple[OverviewStar, ...]
    constellation_lines: tuple[OverviewSegment, ...]
    constellation_boundaries: tuple[OverviewSegment, ...]
    constellation_names: tuple[OverviewName, ...]
    grid_segments: tuple[OverviewSegment, ...]
    chart_count: int

    def cell_for(self, chart_id: str) -> OverviewCell | None:
        """Return the cell for a chart, or ``None`` when it is absent."""
        for cell in self.cells:
            if cell.chart_id == chart_id:
                return cell
        return None


def build_overview(
    charts: tuple[ChartDefinition, ...],
    *,
    hemisphere: str,
    constellations: ConstellationCatalogue | None = None,
    edition: EditionConfig | None = None,
    bright_stars: Sequence[Star] = (),
    star_limit_magnitude: float | None = None,
    equatorial_extension_deg: float = 0.0,
) -> OverviewMap:
    """Build the overview map for one hemisphere.

    Equatorial charts appear on both overview pages. ``equatorial_extension_deg``
    extends each overview past the equator so those charts can be shown in full.
    ``bright_stars`` are projected as a quiet foreground; when
    ``star_limit_magnitude`` is given, fainter stars are dropped.
    """
    center_ra, center_dec = overview_centres(hemisphere)
    projector = AzimuthalEquidistantProjection(center_ra, center_dec)
    radius_deg = 90.0
    catalogue = constellations if constellations is not None else ConstellationCatalogue()
    resolved_edition = edition if edition is not None else default_edition("standard")

    hemisphere_charts: list[ChartDefinition] = []
    codes: dict[str, str] = {}
    for chart in charts:
        if chart.center_dec_deg != 0.0 and hemisphere_for(chart.center_dec_deg) != hemisphere:
            continue
        presentation = presentation_for(
            chart,
            edition_name=resolved_edition.name,
            edition_code=resolved_edition.code,
            chart_index_width=resolved_edition.chart_index_width,
        )
        hemisphere_charts.append(chart)
        codes[chart.id] = presentation.chart_code

    ring_decs = sorted({chart.center_dec_deg for chart in hemisphere_charts})
    has_equatorial_ring = 0.0 in ring_decs
    extension = equatorial_extension_deg if has_equatorial_ring else 0.0
    radius_deg += extension
    polygons = _sector_cells(
        hemisphere_charts,
        projector,
        hemisphere,
        equatorial_extension_deg=extension,
    )
    ring_bounds = _band_boundaries(
        ring_decs, hemisphere, equatorial_extension_deg=extension
    )
    equator_label_dec = None
    if 0.0 in ring_decs:
        index = ring_decs.index(0.0)
        equator_label_dec = (ring_bounds[index] + ring_bounds[index + 1]) / 2.0
    cells = tuple(
        OverviewCell(
            chart_id=chart.id,
            chart_code=codes[chart.id],
            polygon=polygons[chart.id],
            label_point=_label_point(
                projector.project(
                    chart.center_ra_deg,
                    equator_label_dec if chart.center_dec_deg == 0.0 else chart.center_dec_deg,
                ),
                radius_deg,
            ),
        )
        for chart in hemisphere_charts
    )

    stars = _project_stars(
        bright_stars, projector, radius_deg, star_limit_magnitude
    )

    lines = _project_segments(catalogue.lines, projector, radius_deg)
    boundaries = _project_segments(catalogue.boundaries, projector, radius_deg)
    names = _constellation_names(catalogue, projector, radius_deg)
    grid = _grid_segments(projector, radius_deg)

    return OverviewMap(
        hemisphere=hemisphere,
        edition_name=resolved_edition.name,
        title=_HEMISPHERE_LABELS[hemisphere],
        center_ra_deg=center_ra,
        center_dec_deg=center_dec,
        radius_deg=radius_deg,
        cells=cells,
        stars=stars,
        constellation_lines=lines,
        constellation_boundaries=boundaries,
        constellation_names=names,
        grid_segments=grid,
        chart_count=len(cells),
    )


def _label_point(point: ChartPoint, radius_deg: float) -> ChartPoint | None:
    if math.hypot(point.xi_deg, point.eta_deg) > radius_deg - _LABEL_MARGIN_DEG:
        return None
    return point


def _project_stars(
    stars: Sequence[Star],
    projector: AzimuthalEquidistantProjection,
    radius_deg: float,
    star_limit_magnitude: float | None,
) -> tuple[OverviewStar, ...]:
    projected: list[OverviewStar] = []
    for star in stars:
        if star_limit_magnitude is not None and star.magnitude > star_limit_magnitude:
            continue
        if (
            projector.angular_distance_deg(star.ra_deg, star.dec_deg)
            > radius_deg - _VISIBLE_EPSILON_DEG
        ):
            continue
        projected.append(
            OverviewStar(
                point=projector.project(star.ra_deg, star.dec_deg),
                magnitude=star.magnitude,
            )
        )
    # Faintest first so the brightest stars are drawn on top; the sort is
    # stable, so equal magnitudes keep catalogue order and stay reproducible.
    projected.sort(key=lambda item: item.magnitude, reverse=True)
    return tuple(projected)


def _sector_cells(
    charts: Sequence[ChartDefinition],
    projector: AzimuthalEquidistantProjection,
    hemisphere: str,
    *,
    equatorial_extension_deg: float = 0.0,
) -> dict[str, tuple[ChartPoint, ...]]:
    """Partition the hemisphere into one trapezoidal cell per chart.

    The tiling is organised as declination rings split into right-ascension
    sectors, so the natural non-overlapping index cell is the sector around
    each chart centre: declination boundaries lie midway between adjacent ring
    centres (and at the pole and equator), RA boundaries midway between
    adjacent chart centres within a ring.  Cell sides are straight meridians
    and cell tops and bottoms follow declination circles, giving a clean
    trapezoidal mesh rather than a Voronoi honeycomb.
    """
    by_dec: dict[float, list[ChartDefinition]] = {}
    for chart in charts:
        by_dec.setdefault(chart.center_dec_deg, []).append(chart)
    decs = sorted(by_dec)
    boundaries = _band_boundaries(
        decs, hemisphere, equatorial_extension_deg=equatorial_extension_deg
    )

    cells: dict[str, tuple[ChartPoint, ...]] = {}
    for index, dec in enumerate(decs):
        dec_low = boundaries[index]
        dec_high = boundaries[index + 1]
        ring = sorted(by_dec[dec], key=lambda chart: chart.center_ra_deg)
        if len(ring) == 1:
            cells[ring[0].id] = _ring_cell(projector, dec_low, dec_high)
            continue
        edges = _ra_sector_edges([chart.center_ra_deg for chart in ring])
        for chart, (ra_left, ra_right) in zip(ring, edges, strict=True):
            cells[chart.id] = _sector_cell(
                projector, ra_left, ra_right, dec_low, dec_high
            )
    return cells


def _band_boundaries(
    decs: list[float],
    hemisphere: str,
    *,
    equatorial_extension_deg: float = 0.0,
) -> list[float]:
    """Declination boundaries between adjacent rings plus the outer edges."""
    midpoints = [
        (decs[index] + decs[index + 1]) / 2.0 for index in range(len(decs) - 1)
    ]
    if hemisphere == NORTH:
        if equatorial_extension_deg > 0.0 and decs and decs[0] == 0.0:
            return [
                -equatorial_extension_deg,
                equatorial_extension_deg,
                *midpoints[1:],
                90.0,
            ]
        return [0.0, *midpoints, 90.0]
    if equatorial_extension_deg > 0.0 and decs and decs[-1] == 0.0:
        return [
            -90.0,
            *midpoints[:-1],
            -equatorial_extension_deg,
            equatorial_extension_deg,
        ]
    return [-90.0, *midpoints, 0.0]


def _ra_sector_edges(ras_deg: list[float]) -> list[tuple[float, float]]:
    """Return the ``(left, right)`` RA boundary of each chart in a ring."""
    count = len(ras_deg)
    bounds = [
        _mid_ra(ras_deg[index], ras_deg[(index + 1) % count])
        for index in range(count)
    ]
    return [(bounds[index - 1], bounds[index]) for index in range(count)]


def _mid_ra(first_deg: float, second_deg: float) -> float:
    """Right-ascension midpoint taking the short way around 0h."""
    delta = (second_deg - first_deg + 180.0) % 360.0 - 180.0
    return (first_deg + delta / 2.0) % 360.0


def _sector_cell(
    projector: AzimuthalEquidistantProjection,
    ra_left_deg: float,
    ra_right_deg: float,
    dec_low_deg: float,
    dec_high_deg: float,
) -> tuple[ChartPoint, ...]:
    """Build one trapezoidal ring/RA-sector cell."""
    span = (ra_right_deg - ra_left_deg) % 360.0
    samples = max(2, int(math.ceil(span / _SECTOR_ARC_STEP_DEG)) + 1)
    top = [
        projector.project(
            ra_left_deg + span * index / (samples - 1), dec_high_deg
        )
        for index in range(samples)
    ]
    bottom = [
        projector.project(
            ra_right_deg - span * index / (samples - 1), dec_low_deg
        )
        for index in range(samples)
    ]
    return tuple(top + bottom)


def _ring_cell(
    projector: AzimuthalEquidistantProjection,
    dec_low_deg: float,
    dec_high_deg: float,
) -> tuple[ChartPoint, ...]:
    """A whole-ring cell (a lone chart in its declination band)."""
    if abs(dec_high_deg) >= 90.0 - _VISIBLE_EPSILON_DEG:
        boundary_dec = dec_low_deg
    elif abs(dec_low_deg) >= 90.0 - _VISIBLE_EPSILON_DEG:
        boundary_dec = dec_high_deg
    else:
        boundary_dec = dec_high_deg
    return tuple(
        projector.project(360.0 * index / _RING_SEGMENTS, boundary_dec)
        for index in range(_RING_SEGMENTS)
    )


def _visible_runs(
    sky_points: list[tuple[float, float]],
    projector: AzimuthalEquidistantProjection,
    radius_deg: float,
) -> tuple[tuple[ChartPoint, ...], ...]:
    """Project a sky polyline and keep the runs on the visible hemisphere."""
    visible = [
        projector.angular_distance_deg(ra, dec) <= radius_deg + _VISIBLE_EPSILON_DEG
        for ra, dec in sky_points
    ]
    if not any(visible):
        return ()
    if all(visible):
        projected = [projector.project(ra, dec) for ra, dec in sky_points]
        return (tuple(projected),)

    start = visible.index(False)
    order = list(range(start, len(sky_points))) + list(range(0, start))
    runs: list[tuple[ChartPoint, ...]] = []
    current: list[ChartPoint] = []
    for index in order:
        if visible[index]:
            ra, dec = sky_points[index]
            current.append(projector.project(ra, dec))
        else:
            if len(current) >= 2:
                runs.append(tuple(current))
            current = []
    if len(current) >= 2:
        runs.append(tuple(current))
    return tuple(runs)


def _project_segments(
    segments: tuple[ConstellationSegment, ...],
    projector: AzimuthalEquidistantProjection,
    radius_deg: float,
) -> tuple[OverviewSegment, ...]:
    """Project constellation segments as straight chords clipped to the disk.

    The overview is a schematic, so stick figures and boundaries are drawn as
    straight lines between the projected endpoints instead of densified
    great-circle arcs.  Segments whose endpoints are more than a short way
    beyond the rim are dropped, so a chord never connects two far-hemisphere
    points through the centre.
    """
    result: list[OverviewSegment] = []
    for segment in segments:
        start = projector.project(segment.ra1_deg, segment.dec1_deg)
        end = projector.project(segment.ra2_deg, segment.dec2_deg)
        if (
            math.hypot(start.xi_deg, start.eta_deg) > radius_deg + _SEGMENT_MARGIN_DEG
            or math.hypot(end.xi_deg, end.eta_deg) > radius_deg + _SEGMENT_MARGIN_DEG
        ):
            continue
        run = _clip_segment_to_disk(start, end, radius_deg)
        if run is not None:
            result.append(OverviewSegment(points=run, weight=segment.weight))
    return tuple(result)


def _clip_segment_to_disk(
    start: ChartPoint, end: ChartPoint, radius_deg: float
) -> tuple[ChartPoint, ChartPoint] | None:
    """Clip a straight segment to the disk, or ``None`` when it misses it."""
    delta_x = end.xi_deg - start.xi_deg
    delta_y = end.eta_deg - start.eta_deg
    quadratic = delta_x * delta_x + delta_y * delta_y
    if quadratic <= 1e-12:
        return None
    linear = 2.0 * (start.xi_deg * delta_x + start.eta_deg * delta_y)
    constant = start.xi_deg**2 + start.eta_deg**2 - radius_deg**2
    discriminant = linear * linear - 4.0 * quadratic * constant
    if discriminant <= 0.0:
        if constant <= 0.0:
            return (start, end)
        return None
    root = math.sqrt(discriminant)
    enter = max(0.0, (-linear - root) / (2.0 * quadratic))
    leave = min(1.0, (-linear + root) / (2.0 * quadratic))
    if enter >= leave - 1e-9:
        return None
    return (_lerp(start, end, enter), _lerp(start, end, leave))


def _lerp(start: ChartPoint, end: ChartPoint, fraction: float) -> ChartPoint:
    return ChartPoint(
        xi_deg=start.xi_deg + fraction * (end.xi_deg - start.xi_deg),
        eta_deg=start.eta_deg + fraction * (end.eta_deg - start.eta_deg),
    )


def _constellation_names(
    catalogue: ConstellationCatalogue,
    projector: AzimuthalEquidistantProjection,
    radius_deg: float,
) -> tuple[OverviewName, ...]:
    """Place a name at each constellation's spherical centroid of line vertices."""
    accumulators: dict[str, list[float]] = {}
    for segment in catalogue.lines:
        if not segment.constellation_id:
            continue
        for ra_deg, dec_deg in (
            (segment.ra1_deg, segment.dec1_deg),
            (segment.ra2_deg, segment.dec2_deg),
        ):
            vector = _unit_vector(ra_deg, dec_deg)
            total = accumulators.setdefault(segment.constellation_id, [0.0, 0.0, 0.0])
            total[0] += vector[0]
            total[1] += vector[1]
            total[2] += vector[2]

    names: list[OverviewName] = []
    for abbreviation, total in accumulators.items():
        norm = math.sqrt(total[0] ** 2 + total[1] ** 2 + total[2] ** 2)
        if norm <= 1e-9:
            continue
        ra_deg = math.degrees(math.atan2(total[1], total[0])) % 360.0
        dec_deg = math.degrees(math.asin(max(-1.0, min(1.0, total[2] / norm))))
        if projector.angular_distance_deg(ra_deg, dec_deg) > radius_deg - _LABEL_MARGIN_DEG:
            continue
        names.append(
            OverviewName(
                text=constellation_name(abbreviation),
                point=projector.project(ra_deg, dec_deg),
            )
        )
    return tuple(names)


def _unit_vector(ra_deg: float, dec_deg: float) -> tuple[float, float, float]:
    ra = math.radians(ra_deg)
    dec = math.radians(dec_deg)
    return (math.cos(dec) * math.cos(ra), math.cos(dec) * math.sin(ra), math.sin(dec))


def _grid_segments(
    projector: AzimuthalEquidistantProjection, radius_deg: float
) -> tuple[OverviewSegment, ...]:
    """Light declination circles and RA meridians for orientation."""
    segments: list[OverviewSegment] = []
    for dec_deg in (-60.0, -30.0, 30.0, 60.0):
        points = [
            (ra_deg, dec_deg) for ra_deg in _range(0.0, 360.0, 5.0)
        ]
        for run in _visible_runs(points, projector, radius_deg):
            segments.append(OverviewSegment(points=run))
    for ra_deg in _range(0.0, 360.0, 30.0):
        points = [(ra_deg, dec_deg) for dec_deg in _range(-90.0, 90.0, 3.0)]
        for run in _visible_runs(points, projector, radius_deg):
            segments.append(OverviewSegment(points=run))
    return tuple(segments)


def _range(start: float, stop: float, step: float) -> list[float]:
    count = int(round((stop - start) / step))
    return [start + step * index for index in range(count + 1)]
