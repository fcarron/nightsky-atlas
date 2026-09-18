"""Azimuthal equidistant projection for whole-sky overview maps.

Overview and locator maps need a projection of the whole celestial sphere, not
the local tangent-plane stereographic used for a single chart.  The azimuthal
equidistant projection maps a point at angular distance ``c`` from an explicit
centre to chart-plane radius ``c`` (in degrees), preserving direction and
radial distance; a pole-centred map therefore shows a hemisphere as a disk of
radius 90 degrees.  Local shapes are distorted away from the centre, but radial
positions and the relation "further from the pole means lower declination" stay
exact, which is what a finder map needs.

Axis convention matches :class:`~nightsky_atlas.projection.base.ChartPoint`:
``+xi`` points east and ``+eta`` points north at the projection centre.  The
printed orientation is applied later by the renderer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from nightsky_atlas.projection.base import ChartPoint

__all__ = ["AzimuthalEquidistantProjection"]

_ANTIPODE_EPSILON = 1e-12


@dataclass(frozen=True, slots=True)
class AzimuthalEquidistantProjection:
    """Azimuthal equidistant projection about an explicit centre.

    ``center_ra_deg``/``center_dec_deg`` select the point that maps to the
    origin; the polar overviews use the celestial poles.
    """

    center_ra_deg: float
    center_dec_deg: float
    name: str = "azimuthal_equidistant"

    def __post_init__(self) -> None:
        if not math.isfinite(self.center_ra_deg) or not math.isfinite(
            self.center_dec_deg
        ):
            raise ValueError("projection centre must be finite")
        if not -90.0 <= self.center_dec_deg <= 90.0:
            raise ValueError(
                f"center_dec_deg must be within [-90, 90], got {self.center_dec_deg!r}"
            )

    def angular_distance_deg(self, ra_deg: float, dec_deg: float) -> float:
        """Great-circle distance from the projection centre, in degrees."""
        center_dec_rad = math.radians(self.center_dec_deg)
        dec_rad = math.radians(dec_deg)
        delta_ra_rad = math.radians(
            (ra_deg - self.center_ra_deg + 180.0) % 360.0 - 180.0
        )
        cos_c = math.sin(center_dec_rad) * math.sin(dec_rad) + math.cos(
            center_dec_rad
        ) * math.cos(dec_rad) * math.cos(delta_ra_rad)
        return math.degrees(math.acos(max(-1.0, min(1.0, cos_c))))

    def project(self, ra_deg: float, dec_deg: float) -> ChartPoint:
        """Project an equatorial position to overview chart-plane degrees."""
        ra0 = math.radians(self.center_ra_deg)
        dec0 = math.radians(self.center_dec_deg)
        ra = math.radians(ra_deg)
        dec = math.radians(dec_deg)

        cx, cy, cz = math.cos(dec0) * math.cos(ra0), math.cos(dec0) * math.sin(ra0), math.sin(dec0)
        px, py, pz = math.cos(dec) * math.cos(ra), math.cos(dec) * math.sin(ra), math.sin(dec)
        dot = max(-1.0, min(1.0, cx * px + cy * py + cz * pz))
        c = math.acos(dot)
        if c <= _ANTIPODE_EPSILON:
            return ChartPoint(xi_deg=0.0, eta_deg=0.0)

        sin_c = math.sin(c)
        if sin_c <= _ANTIPODE_EPSILON:
            # The antipode has no defined azimuth; place it on the negative
            # eta axis at radius 180 so it is unambiguously outside any disk.
            return ChartPoint(xi_deg=0.0, eta_deg=-math.degrees(c))

        ex, ey, ez = -math.sin(ra0), math.cos(ra0), 0.0
        nx = -math.sin(dec0) * math.cos(ra0)
        ny = -math.sin(dec0) * math.sin(ra0)
        nz = math.cos(dec0)
        east = (px * ex + py * ey + pz * ez) / sin_c
        north = (px * nx + py * ny + pz * nz) / sin_c
        return ChartPoint(xi_deg=math.degrees(c * east), eta_deg=math.degrees(c * north))
