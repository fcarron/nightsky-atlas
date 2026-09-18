"""Projection implementations."""

from __future__ import annotations

from nightsky_atlas.projection.azimuthal import AzimuthalEquidistantProjection
from nightsky_atlas.projection.base import ChartPoint, Projection, ProjectionError
from nightsky_atlas.projection.stereographic import StereographicProjection

__all__ = [
    "AzimuthalEquidistantProjection",
    "ChartPoint",
    "Projection",
    "ProjectionError",
    "StereographicProjection",
]
