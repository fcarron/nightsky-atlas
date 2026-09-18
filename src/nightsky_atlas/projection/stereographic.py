"""Stereographic projection onto the tangent plane at the chart centre.

Mathematical definition
-----------------------
On a unit sphere, the stereographic projection with centre ``C`` maps a point
``P`` to the tangent plane at ``C`` along the ray from the antipode ``-C``.
Expressed in equatorial coordinates relative to the chart centre
``(ra0, dec0)`` this is (Snyder, *Map Projections -- A Working Manual*, NOAA
Professional Paper 1395, eqs. 21-2/21-3, adapted to the chart-axis convention
below)::

    cos c = sin(dec0) sin(dec) + cos(dec0) cos(dec) cos(ra - ra0)
    k     = 2 / (1 + cos c)
    xi    = k cos(dec) sin(ra - ra0)
    eta   = k (cos(dec0) sin(dec) - sin(dec0) cos(dec) cos(ra - ra0))

where ``ra - ra0`` is wrapped to ``[-180, 180)`` and ``c`` is the angular
distance from the centre.  The projected radius is ``2 tan(c / 2)`` on a unit
sphere, so for small offsets ``xi`` and ``eta`` in degrees equal the angular
offset in degrees.  The projection is conformal: local shapes are preserved.

The antipode of the centre (``cos c = -1``) is not representable and raises
:class:`ProjectionError`.  Every point within a normal chart field of view is
finite.

Axis convention
---------------
``+xi`` points east (toward increasing right ascension) and ``+eta`` points
north (toward increasing declination) at the chart centre.  Printed naked-eye
orientation (north up, east left) is applied later by the page transform.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from nightsky_atlas.astronomy.angles import signed_deg
from nightsky_atlas.projection.base import ChartPoint, ProjectionError

__all__ = ["StereographicProjection"]

_ANTIPODE_EPSILON = 1e-12


@dataclass(frozen=True, slots=True)
class StereographicProjection:
    """Forward stereographic projection about an explicit chart centre."""

    center_ra_deg: float
    center_dec_deg: float
    name: str = "stereographic"

    def __post_init__(self) -> None:
        if not math.isfinite(self.center_ra_deg) or not math.isfinite(self.center_dec_deg):
            raise ValueError("projection centre must be finite")
        if not -90.0 <= self.center_dec_deg <= 90.0:
            raise ValueError(
                f"center_dec_deg must be within [-90, 90], got {self.center_dec_deg!r}"
            )

    def project(self, ra_deg: float, dec_deg: float) -> ChartPoint:
        """Project an equatorial position to chart-plane degrees."""
        center_dec_rad = math.radians(self.center_dec_deg)
        dec_rad = math.radians(dec_deg)
        delta_ra_rad = math.radians(signed_deg(ra_deg - self.center_ra_deg))

        cos_c = math.sin(center_dec_rad) * math.sin(dec_rad) + math.cos(
            center_dec_rad
        ) * math.cos(dec_rad) * math.cos(delta_ra_rad)
        denominator = 1.0 + cos_c
        if denominator <= _ANTIPODE_EPSILON:
            raise ProjectionError(
                f"position (ra={ra_deg}, dec={dec_deg}) is at the antipode of the "
                f"projection centre and is not representable"
            )

        k = 2.0 / denominator
        xi_rad = k * math.cos(dec_rad) * math.sin(delta_ra_rad)
        eta_rad = k * (
            math.cos(center_dec_rad) * math.sin(dec_rad)
            - math.sin(center_dec_rad) * math.cos(dec_rad) * math.cos(delta_ra_rad)
        )
        return ChartPoint(xi_deg=math.degrees(xi_rad), eta_deg=math.degrees(eta_rad))

    def inverse(self, xi_deg: float, eta_deg: float) -> tuple[float, float]:
        """Invert a chart-plane point to ``(ra_deg, dec_deg)``.

        The inverse is used to recover the sky directions bounding a chart
        field for overview/locator maps.  It is the exact algebraic inverse of
        :meth:`project`; the antipode is not reachable because it maps to
        infinity.
        """
        if not math.isfinite(xi_deg) or not math.isfinite(eta_deg):
            raise ProjectionError("chart-plane coordinates must be finite")
        xi_rad = math.radians(xi_deg)
        eta_rad = math.radians(eta_deg)
        rho = math.hypot(xi_rad, eta_rad)
        center_dec_rad = math.radians(self.center_dec_deg)
        if rho <= _ANTIPODE_EPSILON:
            return self.center_ra_deg, self.center_dec_deg
        c = 2.0 * math.atan(rho / 2.0)
        sin_c = math.sin(c)
        cos_c = math.cos(c)
        east = xi_rad / rho
        north = eta_rad / rho
        sin_dec = cos_c * math.sin(center_dec_rad) + north * sin_c * math.cos(
            center_dec_rad
        )
        sin_dec = max(-1.0, min(1.0, sin_dec))
        dec_rad = math.asin(sin_dec)
        delta_ra_rad = math.atan2(
            east * sin_c,
            cos_c * math.cos(center_dec_rad)
            - north * sin_c * math.sin(center_dec_rad),
        )
        ra_deg = (self.center_ra_deg + math.degrees(delta_ra_rad)) % 360.0
        return ra_deg, math.degrees(dec_rad)
