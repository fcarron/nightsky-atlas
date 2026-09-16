"""Immutable chart geometry domain models.

These are plain dataclasses, deliberately decoupled from the external
configuration schema in :mod:`nightsky_atlas.atlas.config`.  Configuration is
validated at the boundary; these models describe the internal geometry used by
the projection, page transform and, later, the scene builder.

Every angle and length carries its unit in the field name
(``AGENTS.md`` sections 6.2 and 7.1).  Chart coordinates are J2000/ICRS
compatible unless a later decision changes that.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

from nightsky_atlas.projection.base import ChartPoint

__all__ = ["ChartDefinition", "PageGeometry"]


def _require_finite(name: str, value: float) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite, got {value!r}")


@dataclass(frozen=True, slots=True)
class PageGeometry:
    """Physical page geometry in millimetres.

    ``margin_mm`` is the unprintable border on every side; the printable chart
    rectangle is inset by it.  The origin of page coordinates used by the page
    transform is the top-left corner of the sheet.
    """

    width_mm: float
    height_mm: float
    margin_mm: float = 10.0

    def __post_init__(self) -> None:
        for name in ("width_mm", "height_mm", "margin_mm"):
            value = getattr(self, name)
            _require_finite(name, value)
            if value <= 0.0:
                raise ValueError(f"{name} must be positive, got {value!r}")
        if 2.0 * self.margin_mm >= self.width_mm or 2.0 * self.margin_mm >= self.height_mm:
            raise ValueError(
                "margin_mm leaves no printable area on "
                f"{self.width_mm}x{self.height_mm} mm page"
            )

    @property
    def printable_width_mm(self) -> float:
        """Width of the printable area, in millimetres."""
        return self.width_mm - 2.0 * self.margin_mm

    @property
    def printable_height_mm(self) -> float:
        """Height of the printable area, in millimetres."""
        return self.height_mm - 2.0 * self.margin_mm

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable mapping of this geometry."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PageGeometry:
        """Reconstruct a geometry from a mapping produced by :meth:`to_dict`."""
        return cls(**data)


@dataclass(frozen=True, slots=True)
class ChartDefinition:
    """What part of the sky a single chart covers.

    This is *geometry only*: it contains no label placements and no visual
    decisions.  It corresponds to ``ChartDefinition`` in ``AGENTS.md`` section
    6.2.  ``width_deg`` and ``height_deg`` are the angular size of the chart
    field at its centre.
    """

    id: str
    center_ra_deg: float
    center_dec_deg: float
    width_deg: float
    height_deg: float
    projection: str = "stereographic"
    rotation_deg: float = 0.0
    atlas_id: str = "standard"
    neighbours: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("id must not be blank")
        if not self.atlas_id.strip():
            raise ValueError("atlas_id must not be blank")
        if not self.projection.strip():
            raise ValueError("projection must not be blank")
        for name in ("center_ra_deg", "center_dec_deg", "width_deg", "height_deg", "rotation_deg"):
            _require_finite(name, getattr(self, name))
        if not -90.0 <= self.center_dec_deg <= 90.0:
            raise ValueError(
                f"center_dec_deg must be within [-90, 90], got {self.center_dec_deg!r}"
            )
        if self.width_deg <= 0.0:
            raise ValueError(f"width_deg must be positive, got {self.width_deg!r}")
        if self.height_deg <= 0.0:
            raise ValueError(f"height_deg must be positive, got {self.height_deg!r}")

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable mapping of this definition."""
        payload = asdict(self)
        payload["neighbours"] = [list(item) for item in self.neighbours]
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChartDefinition:
        """Reconstruct a definition from a mapping produced by :meth:`to_dict`."""
        payload = dict(data)
        payload["neighbours"] = tuple(
            (str(direction), str(label)) for direction, label in payload.get("neighbours", ())
        )
        return cls(**payload)

    def contains(self, point: ChartPoint, *, tolerance_deg: float = 1e-9) -> bool:
        """Return whether a chart-plane point lies inside this chart's field."""
        return (
            abs(point.xi_deg) <= self.width_deg / 2.0 + tolerance_deg
            and abs(point.eta_deg) <= self.height_deg / 2.0 + tolerance_deg
        )
