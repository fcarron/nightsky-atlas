"""Semantic symbol geometry, independent of any renderer.

Symbols are defined by meaning (``AGENTS.md`` section 12), not by draw calls.
The star diameter model here is shared by the renderer and, later, the collision
system, so both agree on how large a star will print.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from nightsky_atlas.atlas.config import StarStyle
from nightsky_atlas.catalog.models import DeepSkyObject, DsoType

__all__ = ["DsoShape", "EllipseGeometry", "StarSizeModel", "dso_shape", "galaxy_ellipse"]


class DsoShape(StrEnum):
    """Semantic deep-sky symbol shape, independent of the renderer."""

    CIRCLE = "circle"
    DASHED_CIRCLE = "dashed_circle"
    CIRCLE_CROSS = "circle_cross"
    SPOKED_CIRCLE = "spoked_circle"
    DASHED_SQUARE = "dashed_square"
    SQUARE = "square"
    DOT = "dot"


_SHAPE_BY_TYPE: dict[DsoType, DsoShape] = {
    DsoType.GALAXY: DsoShape.CIRCLE,
    DsoType.OPEN_CLUSTER: DsoShape.DASHED_CIRCLE,
    DsoType.GLOBULAR_CLUSTER: DsoShape.CIRCLE_CROSS,
    DsoType.PLANETARY_NEBULA: DsoShape.SPOKED_CIRCLE,
    DsoType.BRIGHT_NEBULA: DsoShape.DASHED_SQUARE,
    DsoType.DARK_NEBULA: DsoShape.DASHED_SQUARE,
    DsoType.GALAXY_CLUSTER: DsoShape.SQUARE,
    DsoType.DOUBLE_STAR: DsoShape.DOT,
    DsoType.STAR: DsoShape.DOT,
    DsoType.OTHER: DsoShape.CIRCLE,
}


def dso_shape(object_type: DsoType) -> DsoShape:
    """Return the symbol shape for a deep-sky object class.

    Galaxies default to a circle here; when axis data is present the renderer
    draws an oriented ellipse instead.
    """
    return _SHAPE_BY_TYPE.get(object_type, DsoShape.CIRCLE)


@dataclass(frozen=True, slots=True)
class EllipseGeometry:
    """A galaxy ellipse in page millimetres and a page-space rotation."""

    major_mm: float
    minor_mm: float
    rotation_rad: float

    @property
    def major_axis_direction(self) -> tuple[float, float]:
        """Unit vector of the major axis in page coordinates (x right, y down)."""
        return (math.cos(self.rotation_rad), math.sin(self.rotation_rad))


def galaxy_ellipse(
    dso: DeepSkyObject,
    *,
    mm_per_deg: float,
    min_axis_mm: float,
    max_axis_mm: float | None = None,
) -> EllipseGeometry | None:
    """Compute a true-scale, oriented ellipse for a galaxy.

    Returns ``None`` when the object has no major-axis data.  The major axis is
    scaled from arcminutes to millimetres using the chart scale; if it is below
    ``min_axis_mm`` it is enlarged to the minimum while preserving the axis
    ratio and position angle.  Position angle is measured from north through
    east and converted to a page rotation, where north is up and east is left.
    """
    if dso.major_axis_arcmin is None:
        return None

    major_mm = dso.major_axis_arcmin / 60.0 * mm_per_deg
    minor_mm = (dso.minor_axis_arcmin or dso.major_axis_arcmin) / 60.0 * mm_per_deg
    ratio = minor_mm / major_mm if major_mm > 0.0 else 1.0
    major_mm = max(major_mm, min_axis_mm)
    minor_mm = major_mm * ratio
    if max_axis_mm is not None and major_mm > max_axis_mm:
        scale = max_axis_mm / major_mm
        major_mm *= scale
        minor_mm *= scale

    position_angle = math.radians(dso.position_angle_deg or 0.0)
    # Direction of the major axis: rotate north (0, -1) toward east (-1, 0).
    direction_x = -math.sin(position_angle)
    direction_y = -math.cos(position_angle)
    rotation_rad = math.atan2(direction_y, direction_x)
    return EllipseGeometry(major_mm=major_mm, minor_mm=minor_mm, rotation_rad=rotation_rad)


@dataclass(frozen=True, slots=True)
class StarSizeModel:
    """Map stellar magnitude to a printed star diameter in millimetres.

    The mapping is piecewise linear and monotonic non-increasing in magnitude:

    - magnitudes at or brighter than ``bright_magnitude`` use ``max_diameter_mm``;
    - magnitudes at or fainter than ``faint_magnitude`` use ``min_diameter_mm``;
    - values in between are linearly interpolated.

    Increasing faintness therefore never increases the printed diameter.
    """

    min_diameter_mm: float
    max_diameter_mm: float
    bright_magnitude: float
    faint_magnitude: float

    def __post_init__(self) -> None:
        if self.min_diameter_mm <= 0.0:
            raise ValueError("min_diameter_mm must be positive")
        if self.max_diameter_mm < self.min_diameter_mm:
            raise ValueError("max_diameter_mm must be >= min_diameter_mm")
        if self.faint_magnitude <= self.bright_magnitude:
            raise ValueError("faint_magnitude must be larger than bright_magnitude")

    @classmethod
    def from_style(cls, style: StarStyle) -> StarSizeModel:
        """Build a size model from validated style configuration."""
        return cls(
            min_diameter_mm=style.min_diameter_mm,
            max_diameter_mm=style.max_diameter_mm,
            bright_magnitude=style.bright_magnitude,
            faint_magnitude=style.faint_magnitude,
        )

    def diameter_mm(self, magnitude: float) -> float:
        """Return the printed diameter in millimetres for a magnitude."""
        if magnitude <= self.bright_magnitude:
            return self.max_diameter_mm
        if magnitude >= self.faint_magnitude:
            return self.min_diameter_mm
        fraction = (magnitude - self.bright_magnitude) / (
            self.faint_magnitude - self.bright_magnitude
        )
        return self.max_diameter_mm + fraction * (self.min_diameter_mm - self.max_diameter_mm)

    def radius_mm(self, magnitude: float) -> float:
        """Return the printed radius in millimetres for a magnitude."""
        return self.diameter_mm(magnitude) / 2.0