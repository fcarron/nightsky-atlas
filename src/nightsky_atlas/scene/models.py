"""Scene models.

A :class:`ChartScene` is the astronomical content selected for one chart after
projection.  It contains chart-plane coordinates but no page coordinates and no
typesetting decisions (``AGENTS.md`` section 6.3); labels and layout arrive in
later milestones.
"""

from __future__ import annotations

from dataclasses import dataclass

from nightsky_atlas.catalog.models import DeepSkyObject, Star
from nightsky_atlas.chart.models import ChartDefinition
from nightsky_atlas.projection.base import ChartPoint

__all__ = ["ChartScene", "SceneDso", "SceneStar"]


@dataclass(frozen=True, slots=True)
class SceneStar:
    """A star placed on the chart plane."""

    star: Star
    chart_point: ChartPoint


@dataclass(frozen=True, slots=True)
class SceneDso:
    """A deep-sky object placed on the chart plane."""

    dso: DeepSkyObject
    chart_point: ChartPoint


@dataclass(frozen=True, slots=True)
class ChartScene:
    """Everything selected and projected for a single chart."""

    definition: ChartDefinition
    stars: tuple[SceneStar, ...] = ()
    deep_sky_objects: tuple[SceneDso, ...] = ()

    @property
    def star_count(self) -> int:
        """Number of stars in the scene."""
        return len(self.stars)

    @property
    def dso_count(self) -> int:
        """Number of deep-sky objects in the scene."""
        return len(self.deep_sky_objects)