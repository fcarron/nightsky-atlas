"""Deterministic scene construction.

The builder selects catalogue objects that fall inside a chart field and
projects them onto the chart plane.  It performs no label or layout work.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
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
        milky_way_contours, frozenset(milky_way_levels), projector, definition
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
    segments: list[SceneSegment] = []
    for source in sources:
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
        for run_index, run in enumerate(runs):
            suffix = "" if len(runs) == 1 else f"#{run_index}"
            outlines.append(
                SceneOutline(
                    outline_id=f"{source.id}{suffix}",
                    dso_id=dso.id,
                    points=tuple(ChartPoint(xi_deg=x, eta_deg=y) for x, y in run),
                    dashed=dso.object_type == DsoType.DARK_NEBULA,
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


def build_star_scene(
    definition: ChartDefinition,
    stars: Iterable[Star],
    *,
    projection: StereographicProjection | None = None,
) -> ChartScene:
    """Backwards-compatible star-only scene builder."""
    return build_scene(definition, stars, projection=projection)
