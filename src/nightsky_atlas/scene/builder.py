"""Deterministic scene construction.

The builder selects catalogue objects that fall inside a chart field and
projects them onto the chart plane.  It performs no label or layout work.
"""

from __future__ import annotations

from collections.abc import Iterable

from nightsky_atlas.catalog.models import DeepSkyObject, Star
from nightsky_atlas.chart.models import ChartDefinition
from nightsky_atlas.projection.base import ChartPoint, ProjectionError
from nightsky_atlas.projection.stereographic import StereographicProjection
from nightsky_atlas.scene.models import ChartScene, SceneDso, SceneStar

__all__ = ["build_scene", "build_star_scene", "default_projection"]


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
) -> ChartScene:
    """Select and project stars and deep-sky objects into a :class:`ChartScene`.

    Objects outside the chart field are excluded, as is a star at the projection
    antipode.  Deep-sky objects fainter than ``dso_magnitude_limit`` are
    excluded; objects with no known magnitude are always retained.  Input order
    is preserved so the scene is deterministic for a given catalogue.
    """
    projector = projection if projection is not None else default_projection(definition)

    scene_stars: list[SceneStar] = []
    for star in stars:
        point = _project_inside(projector, definition, star.ra_deg, star.dec_deg)
        if point is not None:
            scene_stars.append(SceneStar(star=star, chart_point=point))

    scene_dsos: list[SceneDso] = []
    for dso in deep_sky_objects:
        if (
            dso_magnitude_limit is not None
            and dso.magnitude is not None
            and dso.magnitude > dso_magnitude_limit
        ):
            continue
        point = _project_inside(projector, definition, dso.ra_deg, dso.dec_deg)
        if point is not None:
            scene_dsos.append(SceneDso(dso=dso, chart_point=point))

    return ChartScene(
        definition=definition,
        stars=tuple(scene_stars),
        deep_sky_objects=tuple(scene_dsos),
    )


def build_star_scene(
    definition: ChartDefinition,
    stars: Iterable[Star],
    *,
    projection: StereographicProjection | None = None,
) -> ChartScene:
    """Backwards-compatible star-only scene builder."""
    return build_scene(definition, stars, projection=projection)