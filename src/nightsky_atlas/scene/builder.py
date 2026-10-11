"""Deterministic scene construction.

The builder selects catalogue objects that fall inside a chart field and
projects them onto the chart plane.  It performs no label or layout work.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping
from dataclasses import replace

from nightsky_atlas.catalog.constellations import ConstellationPolygon, ConstellationSegment
from nightsky_atlas.catalog.faint_stars import FaintStar
from nightsky_atlas.catalog.milky_way import MilkyWayContour
from nightsky_atlas.catalog.models import DeepSkyObject, DsoType, Star
from nightsky_atlas.catalog.observing_lists import canonical_designation
from nightsky_atlas.catalog.outlines import NebulaOutline
from nightsky_atlas.catalog.selection import SelectionPolicy, select_dso
from nightsky_atlas.catalog.systems import StarSystem
from nightsky_atlas.chart.models import ChartDefinition
from nightsky_atlas.projection.base import ChartPoint, ProjectionError
from nightsky_atlas.projection.stereographic import StereographicProjection
from nightsky_atlas.scene.models import (
    ChartScene,
    SceneConstellationRegion,
    SceneDso,
    SceneMilkyWayContour,
    SceneMilkyWayPolygon,
    SceneOutline,
    SceneSegment,
    SceneStar,
    SceneStarSystem,
)

__all__ = ["build_scene", "build_star_scene", "default_projection"]

_DENSIFY_MAX_STEP_DEG = 0.5
_DENSIFY_MAX_SAMPLES = 256


def default_projection(definition: ChartDefinition) -> StereographicProjection:
    """Create the default projection for a chart definition."""
    return StereographicProjection(definition.center_ra_deg, definition.center_dec_deg)


def _project_inside(
    projector: StereographicProjection,
    definition: ChartDefinition,
    ra_deg: float,
    dec_deg: float,
) -> ChartPoint | None:
    try:
        chart_point = projector.project(ra_deg, dec_deg)
    except ProjectionError:
        return None
    return chart_point if definition.contains(chart_point) else None


def build_scene(
    definition: ChartDefinition,
    stars: Iterable[Star | FaintStar] = (),
    deep_sky_objects: Iterable[DeepSkyObject] = (),
    *,
    projection: StereographicProjection | None = None,
    dso_magnitude_limit: float | None = None,
    constellation_lines: Iterable[ConstellationSegment] = (),
    constellation_boundaries: Iterable[ConstellationSegment] = (),
    constellation_polygons: Iterable[ConstellationPolygon] = (),
    nebula_outlines: Iterable[NebulaOutline] = (),
    milky_way_contours: Iterable[MilkyWayContour] = (),
    milky_way_levels: Iterable[int] = (),
    milky_way_fill_enabled: bool = False,
    star_systems: Iterable[StarSystem] = (),
    observing_index: Mapping[str, frozenset[str]] | None = None,
    selection_policy: SelectionPolicy | None = None,
) -> ChartScene:
    """Select and project stars, deep-sky objects and constellation geometry.

    Objects outside the chart field are excluded, as is a star at the projection
    antipode.  Input order is preserved so the scene is deterministic for a
    given catalogue.

    When ``selection_policy`` is given, each deep-sky object receives atlas
    metadata (observing-list memberships, per-type visibility and render/label
    priorities) and is kept only if its type evaluator calls it visible or an
    observing-list forces it.  ``dso_magnitude_limit`` is the fallback rule used
    only when no policy is supplied.

    Constellation stick-figure lines are **not** densified: both endpoints are
    projected and the renderer draws a straight segment between them, because
    the figures are symbolic connections rather than physical great circles.
    Constellation boundaries and nebula outlines are still densified along
    RA/Dec before projection, so long constant-declination boundaries and
    closed outlines curve correctly.
    """
    projector = projection if projection is not None else default_projection(definition)
    milky_way_sources = tuple(milky_way_contours)

    scene_stars: list[SceneStar] = []
    for star in stars:
        point = _project_inside(projector, definition, star.ra_deg, star.dec_deg)
        if point is not None:
            scene_stars.append(SceneStar(star=star, chart_point=point))

    scene_dsos: list[SceneDso] = []
    selected_dsos: list[DeepSkyObject] = []
    for dso in deep_sky_objects:
        metadata = (
            select_dso(dso, index=observing_index, policy=selection_policy)
            if selection_policy is not None
            else None
        )
        if metadata is not None:
            if not (metadata.visible or metadata.forced):
                continue
        elif (
            dso_magnitude_limit is not None
            and dso.magnitude is not None
            and dso.magnitude > dso_magnitude_limit
        ):
            continue
        selected_dsos.append(dso)
        point = _project_inside(projector, definition, dso.ra_deg, dso.dec_deg)
        if point is not None:
            scene_dsos.append(SceneDso(dso=dso, chart_point=point, metadata=metadata))

    star_points = {scene_star.star.id: scene_star.chart_point for scene_star in scene_stars}
    scene_systems: list[SceneStarSystem] = []
    for system in star_systems:
        if not system.is_safe_match:
            continue
        primary_point = star_points.get(system.primary_star_id or "")
        if primary_point is None:
            if system.ra_deg is None or system.dec_deg is None:
                continue
            primary_point = _project_inside(projector, definition, system.ra_deg, system.dec_deg)
        if primary_point is None:
            continue
        component_points = tuple(
            star_points[star_id] for star_id in system.component_star_ids if star_id in star_points
        )
        scene_systems.append(
            SceneStarSystem(
                system=system,
                chart_point=primary_point,
                component_points=component_points,
            )
        )

    projected_outlines = _project_outlines(
        _outline_sources(nebula_outlines, selected_dsos), projector, definition
    )
    projected_milky_way = _project_milky_way(
        milky_way_sources, frozenset(milky_way_levels), projector, definition
    )
    projected_milky_way_polygons = (
        _project_milky_way_polygons(
            milky_way_sources, frozenset(milky_way_levels), projector, definition
        )
        if milky_way_fill_enabled
        else ()
    )
    outlined_ids = {outline.dso_id for outline in projected_outlines}
    scene_dsos = [
        replace(
            scene_dso,
            symbol_visible=not (
                scene_dso.dso.id in outlined_ids
                and scene_dso.dso.object_type
                in (DsoType.BRIGHT_NEBULA, DsoType.SUPERNOVA_REMNANT, DsoType.DARK_NEBULA)
            ),
        )
        for scene_dso in scene_dsos
    ]

    return ChartScene(
        definition=definition,
        stars=tuple(scene_stars),
        deep_sky_objects=tuple(scene_dsos),
        star_systems=tuple(scene_systems),
        constellation_lines=_project_constellation_lines(
            constellation_lines, projector, definition
        ),
        constellation_boundaries=_project_segments(
            constellation_boundaries, projector, definition, "boundary"
        ),
        constellation_regions=_project_constellation_regions(
            constellation_polygons, projector, definition
        ),
        nebula_outlines=projected_outlines,
        milky_way_contours=projected_milky_way,
        milky_way_polygons=projected_milky_way_polygons,
        milky_way_fill_available=milky_way_fill_enabled
        and any(contour.level == 1 for contour in milky_way_sources),
    )


def _densify(
    ra1_deg: float,
    dec1_deg: float,
    ra2_deg: float,
    dec2_deg: float,
) -> list[tuple[float, float]]:
    """Sample a segment along RA/Dec, taking the shortest RA path.

    Constellation edges are defined along lines of constant RA or Dec; sampling
    them before projection keeps those curves correct on the page.
    """
    delta_ra = ((ra2_deg - ra1_deg + 180.0) % 360.0) - 180.0
    delta_dec = dec2_deg - dec1_deg
    span = max(abs(delta_ra), abs(delta_dec))
    count = max(1, min(_DENSIFY_MAX_SAMPLES, int(math.ceil(span / _DENSIFY_MAX_STEP_DEG))))
    return [
        (ra1_deg + delta_ra * index / count, dec1_deg + delta_dec * index / count)
        for index in range(count + 1)
    ]


def _clip_segment(
    start: tuple[float, float],
    end: tuple[float, float],
    half_width: float,
    half_height: float,
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """Liang-Barsky clip of a chart-plane segment to the chart field."""
    x0, y0 = start
    x1, y1 = end
    dx = x1 - x0
    dy = y1 - y0
    t0, t1 = 0.0, 1.0
    bounds = (
        (-dx, x0 + half_width),
        (dx, half_width - x0),
        (-dy, y0 + half_height),
        (dy, half_height - y0),
    )
    for p, q in bounds:
        if p == 0.0:
            if q < 0.0:
                return None
        else:
            ratio = q / p
            if p < 0.0:
                if ratio > t1:
                    return None
                if ratio > t0:
                    t0 = ratio
            else:
                if ratio < t0:
                    return None
                if ratio < t1:
                    t1 = ratio
    clip_start = start if t0 == 0.0 else (x0 + t0 * dx, y0 + t0 * dy)
    clip_end = end if t1 == 1.0 else (x0 + t1 * dx, y0 + t1 * dy)
    return clip_start, clip_end


def _polyline_runs(
    points: list[tuple[float, float]],
    half_width: float,
    half_height: float,
) -> list[list[tuple[float, float]]]:
    """Clip a chart-plane polyline into connected runs inside the field."""
    runs: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    for start, end in zip(points, points[1:], strict=False):
        clipped = _clip_segment(start, end, half_width, half_height)
        if clipped is None:
            if len(current) >= 2:
                runs.append(current)
            current = []
            continue
        clip_start, clip_end = clipped
        if current and current[-1] == clip_start:
            current.append(clip_end)
        else:
            if len(current) >= 2:
                runs.append(current)
            current = [clip_start, clip_end]
    if len(current) >= 2:
        runs.append(current)
    return runs


def _project_constellation_lines(
    sources: Iterable[ConstellationSegment],
    projector: StereographicProjection,
    definition: ChartDefinition,
) -> tuple[SceneSegment, ...]:
    """Project stick-figure lines as straight two-point chart segments.

    Constellation lines are symbolic connections, so only the two endpoint
    coordinates are projected; the renderer then draws a direct straight line
    in the two-dimensional chart plane.  There is deliberately no spherical
    interpolation and no great-circle densification, which would curve the
    printed figure near the poles.  The projected chord is clipped to the
    chart field with a straight-line clip, so a partially visible segment is
    shown correctly rather than dropped.
    """
    half_width = definition.width_deg / 2.0
    half_height = definition.height_deg / 2.0
    center_dec_rad = math.radians(projector.center_dec_deg)
    segments: list[SceneSegment] = []
    for source in sources:
        if any(
            math.sin(center_dec_rad) * math.sin(math.radians(dec_deg))
            + math.cos(center_dec_rad)
            * math.cos(math.radians(dec_deg))
            * math.cos(math.radians(ra_deg - projector.center_ra_deg))
            <= 0.0
            for ra_deg, dec_deg in (
                (source.ra1_deg, source.dec1_deg),
                (source.ra2_deg, source.dec2_deg),
            )
        ):
            continue
        try:
            start = projector.project(source.ra1_deg % 360.0, source.dec1_deg)
            end = projector.project(source.ra2_deg % 360.0, source.dec2_deg)
        except ProjectionError:
            continue
        clipped = _clip_segment(
            (start.xi_deg, start.eta_deg),
            (end.xi_deg, end.eta_deg),
            half_width,
            half_height,
        )
        if clipped is None:
            continue
        clip_start, clip_end = clipped
        if clip_start == clip_end:
            continue
        segments.append(
            SceneSegment(
                source_id=source.id,
                points=(
                    ChartPoint(xi_deg=clip_start[0], eta_deg=clip_start[1]),
                    ChartPoint(xi_deg=clip_end[0], eta_deg=clip_end[1]),
                ),
                constellation_id=source.constellation_id,
                weight=source.weight,
            )
        )
    return tuple(segments)


def _project_segments(
    sources: Iterable[ConstellationSegment],
    projector: StereographicProjection,
    definition: ChartDefinition,
    kind: str,
) -> tuple[SceneSegment, ...]:
    """Project, densify and clip curved constellation boundary segments."""
    half_width = definition.width_deg / 2.0
    half_height = definition.height_deg / 2.0
    segments: list[SceneSegment] = []
    for source in sources:
        chart_points: list[tuple[float, float]] = []
        for ra_deg, dec_deg in _densify(
            source.ra1_deg, source.dec1_deg, source.ra2_deg, source.dec2_deg
        ):
            try:
                point = projector.project(ra_deg % 360.0, dec_deg)
            except ProjectionError:
                continue
            chart_points.append((point.xi_deg, point.eta_deg))
        if len(chart_points) < 2:
            continue
        runs = _polyline_runs(chart_points, half_width, half_height)
        if len(runs) == 1:
            segments.append(
                SceneSegment(
                    source_id=source.id,
                    points=tuple(ChartPoint(xi_deg=x, eta_deg=y) for x, y in runs[0]),
                    constellation_id=source.constellation_id,
                )
            )
        else:
            for run_index, run in enumerate(runs):
                segments.append(
                    SceneSegment(
                        source_id=f"{source.id}#{kind}:{run_index}",
                        points=tuple(ChartPoint(xi_deg=x, eta_deg=y) for x, y in run),
                        constellation_id=source.constellation_id,
                    )
                )
    return tuple(segments)


def _project_constellation_regions(
    polygons: Iterable[ConstellationPolygon],
    projector: StereographicProjection,
    definition: ChartDefinition,
) -> tuple[SceneConstellationRegion, ...]:
    """Project complete constellation footprints, clip them, and measure area."""
    half_width = definition.width_deg / 2.0
    half_height = definition.height_deg / 2.0
    regions: list[SceneConstellationRegion] = []
    for polygon in polygons:
        projected_rings: list[tuple[ChartPoint, ...]] = []
        ring_areas: list[float] = []
        outer_centroid: ChartPoint | None = None
        for ring_index, source_ring in enumerate(polygon.rings):
            projected: list[tuple[float, float]] = []
            for index, (ra1, dec1) in enumerate(source_ring):
                ra2, dec2 = source_ring[(index + 1) % len(source_ring)]
                for ra_deg, dec_deg in _densify(ra1, dec1, ra2, dec2)[:-1]:
                    try:
                        point = projector.project(ra_deg % 360.0, dec_deg)
                    except ProjectionError:
                        projected = []
                        break
                    projected.append((point.xi_deg, point.eta_deg))
                if not projected:
                    break
            clipped = _clip_polygon(
                projected, -half_width, half_width, -half_height, half_height
            )
            area = abs(_polygon_area(clipped))
            if area <= 1e-12:
                continue
            ring_points = tuple(ChartPoint(xi_deg=x, eta_deg=y) for x, y in clipped)
            projected_rings.append(ring_points)
            ring_areas.append(area if ring_index == 0 else -area)
            if ring_index == 0:
                cx, cy = _polygon_centroid(clipped)
                outer_centroid = ChartPoint(xi_deg=cx, eta_deg=cy)
        visible_area = max(0.0, sum(ring_areas))
        if not projected_rings or visible_area <= 1e-12 or outer_centroid is None:
            continue
        chart_area = definition.width_deg * definition.height_deg
        if (
            visible_area >= chart_area * (1.0 - 1e-9)
            and not _radec_ring_contains(
                definition.center_ra_deg, definition.center_dec_deg, polygon.rings[0]
            )
        ):
            # A footprint close to the projection antipode can wrap around
            # infinity and clip as a false full-chart polygon. A true full-field
            # constellation must contain the chart centre.
            continue
        antipode_ra = (definition.center_ra_deg + 180.0) % 360.0
        antipode_dec = -definition.center_dec_deg
        complement = _radec_ring_contains(
            antipode_ra, antipode_dec, polygon.rings[0]
        )
        if complement:
            clipped_area = min(chart_area, visible_area)
            visible_area = max(0.0, chart_area - clipped_area)
            if visible_area <= 1e-12:
                continue
            cx = -outer_centroid.xi_deg * clipped_area / visible_area
            cy = -outer_centroid.eta_deg * clipped_area / visible_area
            outer_centroid = ChartPoint(xi_deg=cx, eta_deg=cy)
        fraction = min(1.0, visible_area / chart_area)
        regions.append(
            SceneConstellationRegion(
                constellation_id=polygon.constellation_id,
                rings=tuple(projected_rings),
                visible_area_fraction=fraction,
                centroid=outer_centroid,
                complement=complement,
            )
        )
    return tuple(sorted(regions, key=lambda item: item.constellation_id))


def _clip_polygon(
    points: list[tuple[float, float]],
    left: float,
    right: float,
    bottom: float,
    top: float,
) -> list[tuple[float, float]]:
    """Clip a projected polygon to the rectangular chart field."""
    clipped = points
    edges = (
        (0, left, True),
        (0, right, False),
        (1, bottom, True),
        (1, top, False),
    )
    for axis, boundary, keep_greater in edges:
        if not clipped:
            break
        output: list[tuple[float, float]] = []
        previous = clipped[-1]
        previous_inside = (
            previous[axis] >= boundary if keep_greater else previous[axis] <= boundary
        )
        for current in clipped:
            current_inside = (
                current[axis] >= boundary if keep_greater else current[axis] <= boundary
            )
            if current_inside != previous_inside:
                delta = current[axis] - previous[axis]
                if delta != 0.0:
                    ratio = (boundary - previous[axis]) / delta
                    other_axis = 1 - axis
                    intersection = list(previous)
                    intersection[axis] = boundary
                    intersection[other_axis] = previous[other_axis] + ratio * (
                        current[other_axis] - previous[other_axis]
                    )
                    output.append((intersection[0], intersection[1]))
            if current_inside:
                output.append(current)
            previous = current
            previous_inside = current_inside
        clipped = output
    return clipped


def _polygon_area(points: list[tuple[float, float]]) -> float:
    if len(points) < 3:
        return 0.0
    return 0.5 * sum(
        x1 * y2 - x2 * y1
        for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1], strict=True)
    )


def _polygon_centroid(points: list[tuple[float, float]]) -> tuple[float, float]:
    area = _polygon_area(points)
    if abs(area) <= 1e-12:
        return (
            sum(point[0] for point in points) / len(points),
            sum(point[1] for point in points) / len(points),
        )
    factor = 1.0 / (6.0 * area)
    x = y = 0.0
    for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1], strict=True):
        cross = x1 * y2 - x2 * y1
        x += (x1 + x2) * cross
        y += (y1 + y2) * cross
    return x * factor, y * factor


def _radec_ring_contains(
    ra_deg: float,
    dec_deg: float,
    ring: tuple[tuple[float, float], ...],
) -> bool:
    """Return whether a sky coordinate lies inside a spherical RA/Dec ring.

    A planar RA/Dec ray test fails for rings enclosing a celestial pole because
    the pole has no unique right ascension.  The signed spherical winding angle
    handles those rings while the source ring orientation selects its intended
    interior rather than its antipodal complement.
    """
    vertices = ring[:-1] if ring and ring[0] == ring[-1] else ring
    if len(vertices) < 3:
        return False
    mean_ra = math.degrees(
        math.atan2(
            sum(math.sin(math.radians(ra)) for ra, _ in vertices),
            sum(math.cos(math.radians(ra)) for ra, _ in vertices),
        )
    ) % 360.0
    unwrapped = [(((ra - mean_ra + 180.0) % 360.0) - 180.0, dec) for ra, dec in vertices]
    planar_orientation = sum(
        x1 * y2 - x2 * y1
        for (x1, y1), (x2, y2) in zip(
            unwrapped, unwrapped[1:] + unwrapped[:1], strict=True
        )
    )
    if abs(planar_orientation) <= 1e-12:
        return False

    def unit_vector(ra: float, dec: float) -> tuple[float, float, float]:
        ra_rad = math.radians(ra)
        dec_rad = math.radians(dec)
        return (
            math.cos(dec_rad) * math.cos(ra_rad),
            math.cos(dec_rad) * math.sin(ra_rad),
            math.sin(dec_rad),
        )

    query = unit_vector(ra_deg, dec_deg)
    vectors = [unit_vector(ra, dec) for ra, dec in vertices]
    winding = 0.0
    for first, second in zip(vectors, vectors[1:] + vectors[:1], strict=True):
        first_dot = sum(q * v for q, v in zip(query, first, strict=True))
        second_dot = sum(q * v for q, v in zip(query, second, strict=True))
        cross = (
            first[1] * second[2] - first[2] * second[1],
            first[2] * second[0] - first[0] * second[2],
            first[0] * second[1] - first[1] * second[0],
        )
        numerator = sum(q * c for q, c in zip(query, cross, strict=True))
        denominator = (
            sum(a * b for a, b in zip(first, second, strict=True))
            - first_dot * second_dot
        )
        winding += math.atan2(numerator, denominator)
    return abs(winding) > math.pi and winding * planar_orientation > 0.0


def _outline_sources(
    outlines: Iterable[NebulaOutline], dsos: Iterable[DeepSkyObject]
) -> tuple[tuple[NebulaOutline, DeepSkyObject], ...]:
    aliases: dict[str, set[DeepSkyObject]] = {}
    for dso in dsos:
        for identifier in (dso.id, *dso.cross_ids):
            key = canonical_designation(identifier)
            if key:
                aliases.setdefault(key, set()).add(dso)
    sources = []
    for outline in outlines:
        targets = aliases.get(canonical_designation(outline.dso_id), set())
        if len(targets) == 1:
            sources.append((outline, next(iter(targets))))
    return tuple(sources)


def _project_outlines(
    sources: Iterable[tuple[NebulaOutline, DeepSkyObject]],
    projector: StereographicProjection,
    definition: ChartDefinition,
) -> tuple[SceneOutline, ...]:
    """Project, densify and clip closed nebula outlines for one chart."""
    half_width = definition.width_deg / 2.0
    half_height = definition.height_deg / 2.0
    outlines: list[SceneOutline] = []
    for source, dso in sources:
        vertices = list(source.points)
        chart_points: list[tuple[float, float]] = []
        failed = False
        for index, (ra1, dec1) in enumerate(vertices):
            ra2, dec2 = vertices[(index + 1) % len(vertices)]
            for ra_deg, dec_deg in _densify(ra1, dec1, ra2, dec2):
                try:
                    point = projector.project(ra_deg % 360.0, dec_deg)
                except ProjectionError:
                    failed = True
                    break
                chart_points.append((point.xi_deg, point.eta_deg))
            if failed:
                break
        if failed or len(chart_points) < 3:
            continue
        runs = _polyline_runs(chart_points, half_width, half_height)
        fill_points = tuple(ChartPoint(xi_deg=x, eta_deg=y) for x, y in chart_points)
        for run_index, run in enumerate(runs):
            suffix = "" if len(runs) == 1 else f"#{run_index}"
            outlines.append(
                SceneOutline(
                    outline_id=f"{source.id}{suffix}",
                    dso_id=dso.id,
                    points=tuple(ChartPoint(xi_deg=x, eta_deg=y) for x, y in run),
                    dashed=dso.object_type == DsoType.DARK_NEBULA,
                    fill_points=fill_points if run_index == 0 else None,
                )
            )
    return tuple(outlines)


def _unit_vector(ra_deg: float, dec_deg: float) -> tuple[float, float, float]:
    ra = math.radians(ra_deg)
    dec = math.radians(dec_deg)
    cos_dec = math.cos(dec)
    return cos_dec * math.cos(ra), cos_dec * math.sin(ra), math.sin(dec)


def _project_milky_way(
    contours: Iterable[MilkyWayContour],
    levels: frozenset[int],
    projector: StereographicProjection,
    definition: ChartDefinition,
) -> tuple[SceneMilkyWayContour, ...]:
    """Project selected outline rings and clip them to the chart viewport."""
    if not levels:
        return ()
    selected = tuple(contour for contour in contours if contour.level in levels)
    if not selected:
        return ()

    half_width = definition.width_deg / 2.0
    half_height = definition.height_deg / 2.0
    plane_radius_rad = math.radians(math.hypot(half_width, half_height))
    chart_radius_deg = math.degrees(2.0 * math.atan(plane_radius_rad / 2.0))
    maximum_half_angle = max(contour.max_edge_half_angle_deg for contour in selected)
    candidate_cosine = math.cos(math.radians(chart_radius_deg + maximum_half_angle + 0.02))
    center = _unit_vector(definition.center_ra_deg, definition.center_dec_deg)
    results: list[SceneMilkyWayContour] = []

    def append_runs(contour: MilkyWayContour, projected: list[tuple[float, float]]) -> None:
        for run_index, run in enumerate(_polyline_runs(projected, half_width, half_height)):
            results.append(
                SceneMilkyWayContour(
                    contour_id=f"{contour.id}#{run_index}",
                    level=contour.level,
                    points=tuple(ChartPoint(xi_deg=x, eta_deg=y) for x, y in run),
                )
            )

    for contour in selected:
        current: list[tuple[float, float]] = []

        def flush(source: MilkyWayContour) -> None:
            nonlocal current
            if len(current) >= 2:
                append_runs(source, current)
            current = []

        for index, ((ra1, dec1), (ra2, dec2)) in enumerate(
            zip(contour.points, contour.points[1:], strict=False)
        ):
            midpoint = contour.edge_midpoint_vectors[index]
            if sum(a * b for a, b in zip(center, midpoint, strict=True)) < candidate_cosine:
                flush(contour)
                continue
            projected: list[tuple[float, float]] = []
            try:
                for ra_deg, dec_deg in _densify(ra1, dec1, ra2, dec2):
                    point = projector.project(ra_deg % 360.0, dec_deg)
                    projected.append((point.xi_deg, point.eta_deg))
            except ProjectionError:
                flush(contour)
                continue
            if current and current[-1] == projected[0]:
                current.extend(projected[1:])
            else:
                flush(contour)
                current = projected
        flush(contour)
    return tuple(results)


def _project_milky_way_polygons(
    contours: Iterable[MilkyWayContour],
    levels: frozenset[int],
    projector: StereographicProjection,
    definition: ChartDefinition,
) -> tuple[SceneMilkyWayPolygon, ...]:
    if not levels:
        return ()
    source_groups: dict[tuple[int, str], list[MilkyWayContour]] = {}
    for contour in contours:
        if contour.level not in levels or contour.points[0] != contour.points[-1]:
            continue
        group_id = contour.polygon_id or contour.id
        source_groups.setdefault((contour.level, group_id), []).append(contour)
    polygons: list[SceneMilkyWayPolygon] = []
    for (level, group_id), rings in source_groups.items():
        for loop in _project_milky_way_polygon_group(rings, projector, definition):
            polygons.append(SceneMilkyWayPolygon(level, loop, polygon_id=group_id))
    return tuple(polygons)


def _project_milky_way_polygon_group(
    rings: list[MilkyWayContour],
    projector: StereographicProjection,
    definition: ChartDefinition,
) -> tuple[tuple[ChartPoint, ...], ...]:
    half_width = definition.width_deg / 2.0
    half_height = definition.height_deg / 2.0
    plane_radius_rad = math.radians(math.hypot(half_width, half_height))
    chart_radius_deg = math.degrees(2.0 * math.atan(plane_radius_rad / 2.0))
    center = _unit_vector(definition.center_ra_deg, definition.center_dec_deg)
    source_rings = tuple(contour.points for contour in rings)
    def contains(x: float, y: float) -> bool:
        return _d3_spherical_polygon_contains(source_rings, *projector.inverse(x, y))

    center_inside = contains(0.0, 0.0)
    near_cosine = math.cos(math.radians(chart_radius_deg + 0.5))
    edges: list[tuple[tuple[float, float], tuple[float, float]]] = []
    border_points: list[tuple[float, float]] = []
    for contour in rings:
        for start, end in zip(contour.points, contour.points[1:], strict=False):
            dense = _densify(*start, *end)
            for first, second in zip(dense, dense[1:], strict=False):
                first_near = _unit_dot(center, _unit_vector(*first)) >= near_cosine
                second_near = _unit_dot(center, _unit_vector(*second)) >= near_cosine
                if not first_near and not second_near:
                    continue
                try:
                    projected_first = projector.project(first[0] % 360.0, first[1])
                    projected_second = projector.project(second[0] % 360.0, second[1])
                except ProjectionError:
                    continue
                clipped = _clip_segment(
                    (projected_first.xi_deg, projected_first.eta_deg),
                    (projected_second.xi_deg, projected_second.eta_deg),
                    half_width,
                    half_height,
                )
                if clipped is None:
                    continue
                edges.append(clipped)
                border_points.extend(
                    point
                    for point in clipped
                    if _point_on_chart_border(point, half_width, half_height)
                )
    loops = _clip_milky_way_edges_to_chart(
        edges, border_points, half_width, half_height, contains
    )
    if not loops and center_inside and not border_points:
        loops = (
            (
                (-half_width, -half_height),
                (half_width, -half_height),
                (half_width, half_height),
                (-half_width, half_height),
                (-half_width, -half_height),
            ),
        )
    return tuple(
        tuple(ChartPoint(xi_deg=x, eta_deg=y) for x, y in loop) for loop in loops
    )


def _unit_dot(
    first: tuple[float, float, float], second: tuple[float, float, float]
) -> float:
    return sum(a * b for a, b in zip(first, second, strict=True))


def _point_on_chart_border(
    point: tuple[float, float], half_width: float, half_height: float
) -> bool:
    tolerance = 1e-8
    return (
        abs(abs(point[0]) - half_width) <= tolerance
        or abs(abs(point[1]) - half_height) <= tolerance
    )


def _clip_milky_way_edges_to_chart(
    edges: list[tuple[tuple[float, float], tuple[float, float]]],
    border_points: list[tuple[float, float]],
    half_width: float,
    half_height: float,
    contains: Callable[[float, float], bool],
) -> tuple[tuple[tuple[float, float], ...], ...]:
    tolerance = 1e-8

    def key(point: tuple[float, float]) -> tuple[int, int]:
        return round(point[0] / tolerance), round(point[1] / tolerance)

    graph: dict[tuple[int, int], list[tuple[int, tuple[float, float]]]] = {}
    graph_edges: list[
        tuple[tuple[int, int], tuple[int, int], tuple[tuple[float, float], ...]]
    ] = []

    def add_edge(path: tuple[tuple[float, float], ...]) -> None:
        if len(path) < 2 or math.dist(path[0], path[-1]) <= tolerance:
            return
        first_key, last_key = key(path[0]), key(path[-1])
        if first_key == last_key:
            return
        index = len(graph_edges)
        graph_edges.append((first_key, last_key, path))
        graph.setdefault(first_key, []).append((index, path[0]))
        graph.setdefault(last_key, []).append((index, path[-1]))

    for start, end in edges:
        add_edge((start, end))

    corners = (
        (-half_width, -half_height),
        (half_width, -half_height),
        (half_width, half_height),
        (-half_width, half_height),
    )
    sides = tuple(zip(corners, corners[1:] + corners[:1], strict=True))
    for start, end in sides:
        side_points = [start, end]
        side_points.extend(
            point
            for point in border_points
            if _point_on_segment(point, start, end, tolerance)
        )
        unique = {key(point): point for point in side_points}
        ordered = sorted(unique.values(), key=lambda point: math.dist(start, point))
        for first, second in zip(ordered, ordered[1:], strict=False):
            midpoint = ((first[0] + second[0]) / 2.0, (first[1] + second[1]) / 2.0)
            try:
                inside = contains(*midpoint)
            except ProjectionError:
                inside = False
            if inside:
                add_edge((first, second))

    loops: list[tuple[tuple[float, float], ...]] = []
    visited: set[int] = set()
    for first_index, (first_key, last_key, first_path) in enumerate(graph_edges):
        if first_index in visited:
            continue
        path = list(first_path)
        visited.add(first_index)
        start_key = first_key
        current_key = last_key
        while current_key != start_key:
            options = [item for item in graph.get(current_key, ()) if item[0] not in visited]
            if not options:
                path = []
                break
            next_index, _ = options[0]
            edge_start, edge_end, edge_path = graph_edges[next_index]
            if edge_start == current_key:
                oriented = edge_path
                current_key = edge_end
            else:
                oriented = tuple(reversed(edge_path))
                current_key = edge_start
            visited.add(next_index)
            path.extend(oriented[1:])
            if len(path) > len(graph_edges) + 2:
                path = []
                break
        if len(path) >= 4 and math.dist(path[0], path[-1]) <= tolerance:
            loops.append(tuple(path))
    return tuple(loops)


def _point_on_segment(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
    tolerance: float,
) -> bool:
    cross = (point[0] - start[0]) * (end[1] - start[1]) - (
        point[1] - start[1]
    ) * (end[0] - start[0])
    return (
        abs(cross) <= tolerance
        and min(start[0], end[0]) - tolerance <= point[0] <= max(start[0], end[0]) + tolerance
        and min(start[1], end[1]) - tolerance <= point[1] <= max(start[1], end[1]) + tolerance
    )


def _d3_spherical_polygon_contains(
    rings: tuple[tuple[tuple[float, float], ...], ...], ra_deg: float, dec_deg: float
) -> bool:
    """Match d3-geo's spherical GeoJSON polygon containment semantics."""
    tau = 2.0 * math.pi

    def longitude(value: float) -> float:
        return (math.radians(value) + math.pi) % tau - math.pi

    longitude_query = longitude(ra_deg)
    latitude_query = math.radians(dec_deg)
    normal = (math.sin(longitude_query), -math.cos(longitude_query), 0.0)
    angle = 0.0
    winding = 0
    spherical_area = 0.0

    def cartesian(longitude_rad: float, latitude_rad: float) -> tuple[float, float, float]:
        cos_latitude = math.cos(latitude_rad)
        return (
            cos_latitude * math.cos(longitude_rad),
            cos_latitude * math.sin(longitude_rad),
            math.sin(latitude_rad),
        )

    for source_ring in rings:
        points = (
            source_ring[:-1]
            if source_ring and source_ring[0] == source_ring[-1]
            else source_ring
        )
        if not points:
            continue
        lambda0, latitude0 = longitude(points[-1][0]), math.radians(points[-1][1])
        phi0 = latitude0 / 2.0 + math.pi / 4.0
        sin_phi0, cos_phi0 = math.sin(phi0), math.cos(phi0)
        for ra1, dec1 in points:
            lambda1, latitude1 = longitude(ra1), math.radians(dec1)
            phi1 = latitude1 / 2.0 + math.pi / 4.0
            sin_phi1, cos_phi1 = math.sin(phi1), math.cos(phi1)
            delta = lambda1 - lambda0
            direction = 1.0 if delta >= 0.0 else -1.0
            absolute_delta = direction * delta
            crosses_antimeridian = absolute_delta > math.pi
            product = sin_phi0 * sin_phi1
            spherical_area += math.atan2(
                product * direction * math.sin(absolute_delta),
                cos_phi0 * cos_phi1 + product * math.cos(absolute_delta),
            )
            angle += delta + (direction * tau if crosses_antimeridian else 0.0)
            if crosses_antimeridian ^ (lambda0 >= longitude_query) ^ (
                lambda1 >= longitude_query
            ):
                first = cartesian(lambda0, latitude0)
                second = cartesian(lambda1, latitude1)
                arc = (
                    first[1] * second[2] - first[2] * second[1],
                    first[2] * second[0] - first[0] * second[2],
                    first[0] * second[1] - first[1] * second[0],
                )
                arc_norm = math.sqrt(sum(component * component for component in arc))
                if arc_norm > 0.0:
                    arc = tuple(component / arc_norm for component in arc)
                    intersection = (
                        normal[1] * arc[2] - normal[2] * arc[1],
                        normal[2] * arc[0] - normal[0] * arc[2],
                        normal[0] * arc[1] - normal[1] * arc[0],
                    )
                    intersection_norm = math.sqrt(
                        sum(component * component for component in intersection)
                    )
                    if intersection_norm > 0.0:
                        intersection = tuple(
                            component / intersection_norm for component in intersection
                        )
                        arc_latitude = (
                            -1.0
                            if crosses_antimeridian ^ (delta >= 0.0)
                            else 1.0
                        ) * math.asin(max(-1.0, min(1.0, intersection[2])))
                        if latitude_query > arc_latitude or (
                            latitude_query == arc_latitude and (arc[0] or arc[1])
                        ):
                            winding += 1 if crosses_antimeridian ^ (delta >= 0.0) else -1
            lambda0, latitude0 = lambda1, latitude1
            phi0, sin_phi0, cos_phi0 = phi1, sin_phi1, cos_phi1

    inside = angle < -1e-6 or (angle < 1e-6 and spherical_area < -1e-6)
    return bool(winding & 1) ^ inside


def build_star_scene(
    definition: ChartDefinition,
    stars: Iterable[Star],
    *,
    projection: StereographicProjection | None = None,
) -> ChartScene:
    """Backwards-compatible star-only scene builder."""
    return build_scene(definition, stars, projection=projection)
