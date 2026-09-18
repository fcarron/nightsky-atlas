"""J2000 mean ecliptic geometry for chart rendering."""

from __future__ import annotations

import math

from nightsky_atlas.chart.models import ChartDefinition
from nightsky_atlas.chart.page import PagePoint, PageTransform
from nightsky_atlas.projection.base import ProjectionError
from nightsky_atlas.scene.builder import default_projection

__all__ = ["build_ecliptic"]

_OBLIQUITY_DEG = 23.4392911
_SAMPLES = 361


def build_ecliptic(
    definition: ChartDefinition, transform: PageTransform
) -> tuple[tuple[PagePoint, ...], ...]:
    """Project the mean J2000 ecliptic, splitting at projection discontinuities."""
    projection = default_projection(definition)
    epsilon = math.radians(_OBLIQUITY_DEG)
    paths: list[tuple[PagePoint, ...]] = []
    current: list[PagePoint] = []
    for index in range(_SAMPLES):
        longitude = math.radians(index)
        ra = (
            math.degrees(math.atan2(math.sin(longitude) * math.cos(epsilon), math.cos(longitude)))
            % 360.0
        )
        dec = math.degrees(math.asin(math.sin(longitude) * math.sin(epsilon)))
        try:
            point = transform.to_page(projection.project(ra, dec))
        except ProjectionError:
            if len(current) > 1:
                paths.append(tuple(current))
            current = []
            continue
        current.append(point)
    if len(current) > 1:
        paths.append(tuple(current))
    return tuple(paths)
