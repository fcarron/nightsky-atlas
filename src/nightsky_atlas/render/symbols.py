"""Semantic symbol geometry, independent of any renderer.

Symbols are defined by meaning (``AGENTS.md`` section 12), not by draw calls.
The star diameter model here is shared by the renderer and the collision and
label-exclusion systems, so every consumer agrees on how large a symbol prints.

Deep-sky extent is centralised in :func:`dso_symbol_extent`: it is the single
source of truth for DSO symbol size.  The renderer, debug overlays, label
exclusion zones and collision detection all call it instead of recomputing an
ellipse or a fixed diameter.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from nightsky_atlas.atlas.config import DsoExtentStyle, StarStyle, StyleConfig
from nightsky_atlas.catalog.models import DeepSkyObject, DsoType

__all__ = [
    "CIRCLE_CROSS_REACH_FACTOR",
    "SPOKED_CIRCLE_INNER_FACTOR",
    "SPOKED_CIRCLE_OUTER_FACTOR",
    "DsoShape",
    "EllipseGeometry",
    "StarSizeModel",
    "SymbolExtent",
    "dso_shape",
    "dso_symbol_extent",
    "galaxy_ellipse",
]


class DsoShape(StrEnum):
    """Semantic deep-sky symbol shape, independent of the renderer."""

    CIRCLE = "circle"
    DASHED_CIRCLE = "dashed_circle"
    CIRCLE_CROSS = "circle_cross"
    SPOKED_CIRCLE = "spoked_circle"
    DASHED_SQUARE = "dashed_square"
    SQUARE = "square"
    DOT = "dot"


# Decorative-mark reach as a multiple of the symbol's collision radius.  The
# drawn symbol must never extend beyond the :class:`SymbolExtent` that label
# exclusion and collision detection consume, so every outer factor stays <= 1.0
# (``AGENTS.md`` section 12).
CIRCLE_CROSS_REACH_FACTOR = 1.0
SPOKED_CIRCLE_INNER_FACTOR = 0.5
SPOKED_CIRCLE_OUTER_FACTOR = 1.0


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


# Beyond this an angular extent is treated as a catalogue error and the
# type-specific fallback is used instead (60 deg).
_MAX_PLAUSIBLE_EXTENT_ARCMIN = 3600.0


@dataclass(frozen=True, slots=True)
class SymbolExtent:
    """Printed extent of one deep-sky symbol, in page millimetres.

    This is the shared geometry contract between rendering, label exclusion and
    collision detection.  ``width_mm``/``height_mm`` are the full axis lengths
    (equal for circular symbols), ``rotation_rad`` is the page-space rotation of
    the width axis, ``shape`` is the semantic type mark and
    ``uses_angular_size`` records whether a real catalogue size was used.
    """

    shape: DsoShape
    width_mm: float
    height_mm: float
    rotation_rad: float = 0.0
    uses_angular_size: bool = False

    def __post_init__(self) -> None:
        for name in ("width_mm", "height_mm"):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and positive")

    @property
    def radius_x_mm(self) -> float:
        """Half the extent along the (possibly rotated) width axis."""
        return self.width_mm / 2.0

    @property
    def radius_y_mm(self) -> float:
        """Half the extent along the (possibly rotated) height axis."""
        return self.height_mm / 2.0

    @property
    def collision_radius_mm(self) -> float:
        """Conservative bounding-circle radius for collision and exclusion.

        The farthest point of an ellipse from its centre lies on the major axis,
        so the largest semi-axis is a safe, rotation-independent bound.
        """
        return max(self.radius_x_mm, self.radius_y_mm)

    @property
    def is_elliptical(self) -> bool:
        """Whether the symbol should be drawn as an oriented ellipse."""
        return not math.isclose(self.width_mm, self.height_mm, rel_tol=1e-9, abs_tol=1e-9)


def _usable_axis_arcmin(dso: DeepSkyObject) -> float | None:
    """Return a catalogue diameter in arcminutes, or ``None`` when unusable.

    The major axis is the symbol diameter; the minor axis is used only when the
    major axis is absent.  Missing, non-finite, non-positive or implausibly
    large values are rejected so the caller can fall back to the type-specific
    default.  Catalogue data itself is never modified.
    """
    for value in (dso.major_axis_arcmin, dso.minor_axis_arcmin):
        if value is None:
            continue
        if math.isfinite(value) and 0.0 < value <= _MAX_PLAUSIBLE_EXTENT_ARCMIN:
            return value
        return None
    return None


def _clamped_diameter_mm(diameter_mm: float, extent: DsoExtentStyle) -> float:
    diameter_mm = max(diameter_mm, extent.min_diameter_mm)
    if extent.max_diameter_mm is not None:
        diameter_mm = min(diameter_mm, extent.max_diameter_mm)
    return diameter_mm


def dso_symbol_extent(
    dso: DeepSkyObject,
    *,
    mm_per_deg: float,
    style: StyleConfig,
) -> SymbolExtent:
    """Return the printed extent of a deep-sky symbol.

    This is the **only** place DSO symbol size is computed.  Galaxies keep their
    true major/minor axis and position angle; classes opted into
    ``use_angular_size`` (globular clusters, open clusters) scale their diameter
    from the catalogue angular size.  When a size is missing or unreliable, the
    class-specific ``fallback_diameter_mm`` is used, always clamped by
    ``min_diameter_mm`` and any ``max_diameter_mm``.
    """
    shape = dso_shape(dso.object_type)
    extent = style.dso.extent_style(dso.object_type)

    if extent.use_angular_size:
        if dso.object_type == DsoType.GALAXY:
            ellipse = galaxy_ellipse(
                dso,
                mm_per_deg=mm_per_deg,
                min_axis_mm=extent.min_diameter_mm,
                max_axis_mm=extent.max_diameter_mm,
            )
            if ellipse is not None:
                return SymbolExtent(
                    shape=shape,
                    width_mm=ellipse.major_mm,
                    height_mm=ellipse.minor_mm,
                    rotation_rad=ellipse.rotation_rad,
                    uses_angular_size=True,
                )
        else:
            axis_arcmin = _usable_axis_arcmin(dso)
            if axis_arcmin is not None:
                diameter_mm = _clamped_diameter_mm(
                    axis_arcmin / 60.0 * mm_per_deg, extent
                )
                return SymbolExtent(
                    shape=shape,
                    width_mm=diameter_mm,
                    height_mm=diameter_mm,
                    uses_angular_size=True,
                )

    diameter_mm = _clamped_diameter_mm(extent.fallback_diameter_mm, extent)
    return SymbolExtent(shape=shape, width_mm=diameter_mm, height_mm=diameter_mm)


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