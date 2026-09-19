"""Deterministic scene construction.

The builder selects catalogue objects that fall inside a chart field and
projects them onto the chart plane.  It performs no label or layout work.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping

from nightsky_atlas.catalog.constellations import ConstellationSegment
from nightsky_atlas.catalog.models import DeepSkyObject, Star
from nightsky_atlas.catalog.outlines import NebulaOutline
from nightsky_atlas.catalog.selection import SelectionPolicy, select_dso
from nightsky_atlas.catalog.systems import StarSystem
from nightsky_atlas.chart.models import ChartDefinition
from nightsky_atlas.projection.base import ChartPoint, ProjectionError
from nightsky_atlas.projection.stereographic import StereographicProjection
from nightsky_atlas.scene.models import (
    ChartScene,
    SceneDso,
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
    stars: Iterable[Star] = (),
    deep_sky_objects: Iterable[DeepSkyObject] = (),
    *,
    projection: StereographicProjection | None = None,
    dso_magnitude_limit: float | None = None,
    constellation_lines: Iterable[ConstellationSegment] = (),
    constellation_boundaries: Iterable[ConstellationSegment] = (),
    nebula_outlines: Iterable[NebulaOutline] = (),
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
            primary_point = _project_inside(
                projector, definition, system.ra_deg, system.dec_deg
            )
        if primary_point is None:
            continue
        component_points = tuple(
            star_points[star_id]
            for star_id in system.component_star_ids
            if star_id in star_points
        )
        scene_systems.append(
            SceneStarSystem(
                system=system,
                chart_point=primary_point,
                component_points=component_points,
            )
        )

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
        nebula_outlines=_project_outlines(
            nebula_outlines, projector, definition
        ),
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


def _project_outlines(
    sources: Iterable[NebulaOutline],
    projector: StereographicProjection,
    definition: ChartDefinition,
) -> tuple[SceneOutline, ...]:
    """Project, densify and clip closed nebula outlines for one chart."""
    half_width = definition.width_deg / 2.0
    half_height = definition.height_deg / 2.0
    outlines: list[SceneOutline] = []
    for source in sources:
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
                    dso_id=source.dso_id,
                    points=tuple(ChartPoint(xi_deg=x, eta_deg=y) for x, y in run),
                )
            )
    return tuple(outlines)


def build_star_scene(
    definition: ChartDefinition,
    stars: Iterable[Star],
    *,
    projection: StereographicProjection | None = None,
) -> ChartScene:
    """Backwards-compatible star-only scene builder."""
    return build_scene(definition, stars, projection=projection)
