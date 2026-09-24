"""Mapping from chart-plane coordinates to physical page coordinates.

The transform fits the chart field into the printable rectangle of the page
without distortion: the stereographic projection is conformal, so the same
millimetres-per-degree scale is used on both axes and the chart is centred
within the printable area (letterboxed where page and chart aspect ratios
differ).

Printed orientation follows the conventional naked-eye star-chart convention
(``AGENTS.md`` section 7.3): **north up, east left**.  Page coordinates use a
top-left origin with ``+x`` to the right and ``+y`` down, matching Cairo's
default user space.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.projection.base import ChartPoint

__all__ = ["PagePoint", "PageRect", "PageTransform"]

_DEFAULT_TOLERANCE_MM = 1e-9


@dataclass(frozen=True, slots=True)
class PagePoint:
    """A point on the physical page, in millimetres from the top-left corner."""

    x_mm: float
    y_mm: float


@dataclass(frozen=True, slots=True)
class PageRect:
    """An axis-aligned rectangle on the page, in millimetres."""

    left_mm: float
    top_mm: float
    width_mm: float
    height_mm: float

    @property
    def right_mm(self) -> float:
        """X coordinate of the right edge."""
        return self.left_mm + self.width_mm

    @property
    def bottom_mm(self) -> float:
        """Y coordinate of the bottom edge."""
        return self.top_mm + self.height_mm

    @property
    def center(self) -> PagePoint:
        """Centre of the rectangle."""
        return PagePoint(
            x_mm=self.left_mm + self.width_mm / 2.0,
            y_mm=self.top_mm + self.height_mm / 2.0,
        )


@dataclass(frozen=True, slots=True)
class PageTransform:
    """Convert chart-plane points into page millimetres for one chart."""

    chart: ChartDefinition
    page: PageGeometry
    scale_mm_per_degree: float | None = None

    def __post_init__(self) -> None:
        if self.chart.rotation_deg != 0.0:
            raise NotImplementedError(
                "rotated charts are not implemented yet; rotation_deg must be 0"
            )
        if self.scale_mm_per_degree is not None:
            if not math.isfinite(self.scale_mm_per_degree) or self.scale_mm_per_degree <= 0.0:
                raise ValueError("scale_mm_per_degree must be finite and positive")
            if (
                self.chart.width_deg * self.scale_mm_per_degree
                > self.page.printable_width_mm + _DEFAULT_TOLERANCE_MM
                or self.chart.height_deg * self.scale_mm_per_degree
                > self.page.printable_height_mm + _DEFAULT_TOLERANCE_MM
            ):
                raise ValueError("configured scale makes the chart field exceed the printable page")

    @property
    def mm_per_deg(self) -> float:
        """Configured design scale, or the largest scale that fits the page."""
        if self.scale_mm_per_degree is not None:
            return self.scale_mm_per_degree
        return min(
            self.page.printable_width_mm / self.chart.width_deg,
            self.page.printable_height_mm / self.chart.height_deg,
        )

    @property
    def center_page(self) -> PagePoint:
        """Page position of the chart centre, in millimetres."""
        return PagePoint(
            x_mm=self.page.margin_mm + self.page.printable_width_mm / 2.0,
            y_mm=self.page.margin_mm + self.page.printable_height_mm / 2.0,
        )

    def to_page(self, point: ChartPoint) -> PagePoint:
        """Map a chart-plane point onto the page (north up, east left)."""
        scale = self.mm_per_deg
        center = self.center_page
        return PagePoint(
            x_mm=center.x_mm - point.xi_deg * scale,
            y_mm=center.y_mm - point.eta_deg * scale,
        )

    @property
    def chart_rect(self) -> PageRect:
        """The chart field as an axis-aligned rectangle on the page."""
        left = self.to_page(ChartPoint(self.chart.width_deg / 2.0, 0.0)).x_mm
        right = self.to_page(ChartPoint(-self.chart.width_deg / 2.0, 0.0)).x_mm
        top = self.to_page(ChartPoint(0.0, self.chart.height_deg / 2.0)).y_mm
        bottom = self.to_page(ChartPoint(0.0, -self.chart.height_deg / 2.0)).y_mm
        return PageRect(left_mm=left, top_mm=top, width_mm=right - left, height_mm=bottom - top)

    def chart_contains(self, point: ChartPoint, *, tolerance_deg: float = 1e-9) -> bool:
        """Return whether a chart-plane point lies inside the chart field."""
        return self.chart.contains(point, tolerance_deg=tolerance_deg)

    def page_contains(
        self, point: PagePoint, *, tolerance_mm: float = _DEFAULT_TOLERANCE_MM
    ) -> bool:
        """Return whether a page point lies inside the printable rectangle."""
        left = self.page.margin_mm - tolerance_mm
        top = self.page.margin_mm - tolerance_mm
        right = self.page.width_mm - self.page.margin_mm + tolerance_mm
        bottom = self.page.height_mm - self.page.margin_mm + tolerance_mm
        return left <= point.x_mm <= right and top <= point.y_mm <= bottom
