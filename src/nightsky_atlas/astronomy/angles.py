"""Angular helpers shared by astronomy and projection code.

All angles are in degrees and follow the internal naming convention required by
``AGENTS.md`` section 7.1: the unit is part of the value name.  Angles are
treated as plain ``float`` degrees internally; Astropy quantities belong at the
catalogue boundary, not in the performance-critical geometry core.
"""

from __future__ import annotations

import math

__all__ = ["angular_separation_deg", "signed_deg", "wrap_deg"]


def wrap_deg(value_deg: float, period_deg: float = 360.0) -> float:
    """Wrap ``value_deg`` into the half-open interval ``[0, period_deg)``."""
    if period_deg <= 0.0:
        raise ValueError("period_deg must be positive")
    return value_deg % period_deg


def signed_deg(value_deg: float) -> float:
    """Wrap ``value_deg`` into the half-open interval ``[-180, 180)``."""
    return (value_deg + 180.0) % 360.0 - 180.0


def angular_separation_deg(
    ra1_deg: float,
    dec1_deg: float,
    ra2_deg: float,
    dec2_deg: float,
) -> float:
    """Great-circle separation in degrees.

    Uses the haversine formula, which remains numerically stable for very small
    separations where a naive ``acos(dot)`` would lose precision.
    """
    dec1_rad = math.radians(dec1_deg)
    dec2_rad = math.radians(dec2_deg)
    delta_dec = dec2_rad - dec1_rad
    delta_ra = math.radians(signed_deg(ra2_deg - ra1_deg))
    haversine = (
        math.sin(delta_dec / 2.0) ** 2
        + math.cos(dec1_rad) * math.cos(dec2_rad) * math.sin(delta_ra / 2.0) ** 2
    )
    return math.degrees(2.0 * math.asin(min(1.0, math.sqrt(haversine))))
