"""Projection of equatorial coordinates onto a chart plane.

Projection code must stay independent of the renderer so alternative
projections can be added later (``AGENTS.md`` sections 7.4 and 16).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

__all__ = ["ChartPoint", "Projection", "ProjectionError"]


@dataclass(frozen=True, slots=True)
class ChartPoint:
    """A point on the chart plane, in degrees.

    Axis convention (explicit and tested):

    - ``xi_deg`` increases toward increasing right ascension (east) at the
      chart centre;
    - ``eta_deg`` increases toward increasing declination (north).

    The chart plane is the undistorted tangent plane at the chart centre.  The
    stereographic projection is conformal, so for small offsets chart-plane
    degrees equal angular degrees.  Rotating or flipping the plane for a
    particular printed orientation is the page transform's job, not the
    projection's.
    """

    xi_deg: float
    eta_deg: float


class ProjectionError(ValueError):
    """Raised when a sky position cannot be represented by a projection."""


@runtime_checkable
class Projection(Protocol):
    """Forward projection from equatorial coordinates to the chart plane."""

    name: str

    def project(self, ra_deg: float, dec_deg: float) -> ChartPoint:
        """Project an equatorial position relative to the chart centre."""
        ...
