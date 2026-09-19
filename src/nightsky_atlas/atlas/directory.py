"""Deterministic chart-directory data derived from published chart geometry."""

from __future__ import annotations

from dataclasses import dataclass

from nightsky_atlas.atlas.config import EditionConfig
from nightsky_atlas.chart.models import ChartDefinition
from nightsky_atlas.chart.presentation import (
    format_dec_deg,
    format_ra_deg,
    presentation_from_edition,
)

__all__ = ["ChartDirectoryEntry", "build_chart_directory"]


@dataclass(frozen=True, slots=True)
class ChartDirectoryEntry:
    """One reader-facing lookup row for a chart actually in this build."""

    chart_code: str
    center_ra: str
    center_dec: str
    field: str
    neighbours: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "chart_code": self.chart_code,
            "center_ra": self.center_ra,
            "center_dec": self.center_dec,
            "field": self.field,
            "neighbours": list(self.neighbours),
        }


def build_chart_directory(
    charts: tuple[ChartDefinition, ...], edition: EditionConfig
) -> tuple[ChartDirectoryEntry, ...]:
    """Build reader navigation data from the same definitions used for pages."""
    codes = {chart.id: presentation_from_edition(chart, edition).chart_code for chart in charts}
    return tuple(
        ChartDirectoryEntry(
            chart_code=codes[chart.id],
            center_ra=format_ra_deg(chart.center_ra_deg),
            center_dec=format_dec_deg(chart.center_dec_deg),
            field=f"{chart.width_deg:g}° × {chart.height_deg:g}°",
            neighbours=tuple(codes[item] for _, item in chart.neighbours if item in codes),
        )
        for chart in charts
    )
