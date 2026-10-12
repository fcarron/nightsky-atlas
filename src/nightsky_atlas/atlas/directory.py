"""Deterministic chart-directory data derived from published chart geometry."""

from __future__ import annotations

from dataclasses import dataclass

from nightsky_atlas.atlas.config import DetailChartConfig, EditionConfig
from nightsky_atlas.atlas.detail_geometry import detail_chart_parent_ids
from nightsky_atlas.chart.models import ChartDefinition
from nightsky_atlas.chart.presentation import (
    format_dec_deg,
    format_ra_deg,
    presentation_from_edition,
)

__all__ = [
    "ChartDirectoryEntry",
    "DetailChartDirectoryEntry",
    "build_chart_directory",
    "build_detail_chart_directory",
]


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


@dataclass(frozen=True, slots=True)
class DetailChartDirectoryEntry:
    chart_code: str
    name: str
    center_ra: str
    center_dec: str
    field: str
    scale_mm_per_degree: float
    parent_chart_codes: tuple[str, ...]

    @property
    def parent_chart_code(self) -> str:
        """Return the preferred parent code for legacy callers."""
        return self.parent_chart_codes[0]

    def to_dict(self) -> dict[str, object]:
        return {
            "chart_code": self.chart_code,
            "name": self.name,
            "center_ra": self.center_ra,
            "center_dec": self.center_dec,
            "field": self.field,
            "scale_mm_per_degree": self.scale_mm_per_degree,
            "parent_chart_code": self.parent_chart_code,
            "parent_chart_codes": list(self.parent_chart_codes),
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


def build_detail_chart_directory(
    details: tuple[DetailChartConfig, ...],
    charts: tuple[ChartDefinition, ...],
    edition: EditionConfig,
) -> tuple[DetailChartDirectoryEntry, ...]:
    """Build stable detail-chart lookup rows with all geometric parent codes."""
    chart_by_id = {chart.id: chart for chart in charts}
    parent_ids_by_detail = detail_chart_parent_ids(details, charts)
    return tuple(
        DetailChartDirectoryEntry(
            chart_code=detail.code,
            name=detail.name,
            center_ra=format_ra_deg(detail.center_ra_deg),
            center_dec=format_dec_deg(detail.center_dec_deg),
            field=f"{detail.width_deg:g}° × {detail.height_deg:g}°",
            scale_mm_per_degree=detail.mm_per_degree,
            parent_chart_codes=tuple(
                presentation_from_edition(chart_by_id[chart_id], edition).chart_code
                for chart_id in parent_ids_by_detail[detail.id]
            ),
        )
        for detail in details
    )
