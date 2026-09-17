"""Scene models.

A :class:`ChartScene` is the astronomical content selected for one chart after
projection.  It contains chart-plane coordinates but no page coordinates and no
typesetting decisions (``AGENTS.md`` section 6.3); labels and layout arrive in
later milestones.
"""

from __future__ import annotations

from dataclasses import dataclass

from nightsky_atlas.catalog.models import DeepSkyObject, Star
from nightsky_atlas.catalog.selection import DsoMetadata
from nightsky_atlas.chart.models import ChartDefinition
from nightsky_atlas.projection.base import ChartPoint

__all__ = ["ChartScene", "SceneDso", "SceneOutline", "SceneSegment", "SceneStar"]


@dataclass(frozen=True, slots=True)
class SceneStar:
    """A star placed on the chart plane."""

    star: Star
    chart_point: ChartPoint


@dataclass(frozen=True, slots=True)
class SceneDso:
    """A deep-sky object placed on the chart plane.

    ``metadata`` carries the atlas selection state (observing-list memberships
    and render/label priorities).  It is presentation metadata, so it lives on
    the scene entry rather than on the immutable astronomical object.
    """

    dso: DeepSkyObject
    chart_point: ChartPoint
    metadata: DsoMetadata | None = None


@dataclass(frozen=True, slots=True)
class SceneSegment:
    """A clipped constellation line or boundary polyline on the chart plane."""

    source_id: str
    points: tuple[ChartPoint, ...]

    def __post_init__(self) -> None:
        if len(self.points) < 2:
            raise ValueError("a scene segment needs at least two points")


@dataclass(frozen=True, slots=True)
class SceneOutline:
    """A clipped schematic nebula outline on the chart plane.

    ``points`` form an open run of the projected outline; a fully contained
    outline is closed (its first and last points coincide), otherwise it is the
    portion inside the chart field.  Outlines are stroke-only furniture.
    """

    outline_id: str
    dso_id: str
    points: tuple[ChartPoint, ...]

    def __post_init__(self) -> None:
        if not self.outline_id.strip():
            raise ValueError("outline_id must not be blank")
        if not self.dso_id.strip():
            raise ValueError("dso_id must not be blank")
        if len(self.points) < 2:
            raise ValueError("a scene outline needs at least two points")


@dataclass(frozen=True, slots=True)
class ChartScene:
    """Everything selected and projected for a single chart."""

    definition: ChartDefinition
    stars: tuple[SceneStar, ...] = ()
    deep_sky_objects: tuple[SceneDso, ...] = ()
    constellation_lines: tuple[SceneSegment, ...] = ()
    constellation_boundaries: tuple[SceneSegment, ...] = ()
    nebula_outlines: tuple[SceneOutline, ...] = ()

    @property
    def star_count(self) -> int:
        """Number of stars in the scene."""
        return len(self.stars)

    @property
    def dso_count(self) -> int:
        """Number of deep-sky objects in the scene."""
        return len(self.deep_sky_objects)

    @property
    def outline_count(self) -> int:
        """Number of nebula outline runs in the scene."""
        return len(self.nebula_outlines)
