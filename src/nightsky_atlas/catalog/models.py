"""Catalogue-independent domain models for normalized sky objects.

Every normalized object carries provenance so processed data can always be
traced back to its originating catalogue (``AGENTS.md`` section 8).  Angles are
stored as explicit float degrees (``ra_deg``, ``dec_deg``) and coordinates are
J2000/ICRS compatible (``AGENTS.md`` section 7.2).
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

__all__ = ["DeepSkyObject", "DsoType", "Provenance", "Star"]


class DsoType(StrEnum):
    """Semantic deep-sky object classes used for symbol selection.

    The names match the symbol vocabulary in ``AGENTS.md`` section 12 rather
    than any single catalogue's type codes.
    """

    GALAXY = "galaxy"
    OPEN_CLUSTER = "open_cluster"
    GLOBULAR_CLUSTER = "globular_cluster"
    PLANETARY_NEBULA = "planetary_nebula"
    BRIGHT_NEBULA = "bright_nebula"
    SUPERNOVA_REMNANT = "supernova_remnant"
    DARK_NEBULA = "dark_nebula"
    GALAXY_CLUSTER = "galaxy_cluster"
    DOUBLE_STAR = "double_star"
    STAR = "star"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class Provenance:
    """Where a normalized value came from."""

    catalogue: str
    source_id: str
    version: str | None = None

    def __post_init__(self) -> None:
        if not self.catalogue.strip():
            raise ValueError("catalogue must not be blank")
        if not self.source_id.strip():
            raise ValueError("source_id must not be blank")

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable mapping of this provenance."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Provenance:
        """Reconstruct provenance from a mapping produced by :meth:`to_dict`."""
        return cls(**data)


@dataclass(frozen=True, slots=True)
class Star:
    """A normalized star with provenance.

    ``magnitude`` is the documented display magnitude for the source (visual or
    an explicitly documented equivalent).  The model is deliberately small:
    colour index, proper motion and stellar designations are added only when a
    catalogue actually needs them.
    """

    id: str
    ra_deg: float
    dec_deg: float
    magnitude: float
    provenance: Provenance
    epoch: str = "J2000"
    hip_id: str | None = None

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("id must not be blank")
        if not isinstance(self.provenance, Provenance):
            raise ValueError("provenance must be a Provenance instance")
        if not self.epoch.strip():
            raise ValueError("epoch must not be blank")
        if self.hip_id is not None and not self.hip_id.strip():
            raise ValueError("hip_id must not be blank when present")
        for name in ("ra_deg", "dec_deg", "magnitude"):
            if not math.isfinite(getattr(self, name)):
                raise ValueError(f"{name} must be finite")
        if not -90.0 <= self.dec_deg <= 90.0:
            raise ValueError(f"dec_deg must be within [-90, 90], got {self.dec_deg!r}")

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable mapping of this star."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Star:
        """Reconstruct a star from a mapping produced by :meth:`to_dict`."""
        payload = dict(data)
        payload["provenance"] = Provenance.from_dict(payload["provenance"])
        return cls(**payload)


@dataclass(frozen=True, slots=True)
class DeepSkyObject:
    """A normalized deep-sky object with provenance.

    Every optional field may be absent: the model must not assume a catalogue
    supplies magnitude, dimensions, position angle, a common name or a
    constellation (``AGENTS.md`` section 8.2).  Angular dimensions are in
    arcminutes and position angle is degrees from north through east.
    """

    id: str
    ra_deg: float
    dec_deg: float
    object_type: DsoType
    provenance: Provenance
    magnitude: float | None = None
    magnitude_band: str | None = None
    b_magnitude: float | None = None
    v_magnitude: float | None = None
    mean_surface_brightness_mag_arcsec2: float | None = None
    hubble_type: str | None = None
    sources: str | None = None
    major_axis_arcmin: float | None = None
    minor_axis_arcmin: float | None = None
    position_angle_deg: float | None = None
    common_name: str | None = None
    constellation: str | None = None
    cross_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("id must not be blank")
        if not isinstance(self.provenance, Provenance):
            raise ValueError("provenance must be a Provenance instance")
        if not isinstance(self.object_type, DsoType):
            raise ValueError("object_type must be a DsoType")
        for name in ("ra_deg", "dec_deg"):
            if not math.isfinite(getattr(self, name)):
                raise ValueError(f"{name} must be finite")
        if not -90.0 <= self.dec_deg <= 90.0:
            raise ValueError(f"dec_deg must be within [-90, 90], got {self.dec_deg!r}")
        for name in ("major_axis_arcmin", "minor_axis_arcmin", "position_angle_deg"):
            value = getattr(self, name)
            if value is not None and not math.isfinite(value):
                raise ValueError(f"{name} must be finite when present")
        for name in (
            "b_magnitude",
            "v_magnitude",
            "mean_surface_brightness_mag_arcsec2",
        ):
            value = getattr(self, name)
            if value is not None and not math.isfinite(value):
                raise ValueError(f"{name} must be finite when present")
        if self.major_axis_arcmin is not None and self.major_axis_arcmin <= 0.0:
            raise ValueError("major_axis_arcmin must be positive when present")
        if self.minor_axis_arcmin is not None and self.minor_axis_arcmin <= 0.0:
            raise ValueError("minor_axis_arcmin must be positive when present")
        if self.magnitude is not None and not math.isfinite(self.magnitude):
            raise ValueError("magnitude must be finite when present")

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable mapping of this object."""
        payload = asdict(self)
        payload["object_type"] = self.object_type.value
        payload["cross_ids"] = list(self.cross_ids)
        return payload

    def surface_brightness_mag_arcsec2(self) -> float | None:
        """Mean surface brightness in mag/arcsec^2, when derivable.

        Derived from the display magnitude and the ellipse area
        ``pi/4 * major * minor``; ``None`` when magnitude or both axes are
        unknown.  This is a selection aid for extended objects, not a
        scientifically exact visibility prediction.
        """
        if (
            self.magnitude is None
            or self.major_axis_arcmin is None
            or self.minor_axis_arcmin is None
        ):
            return None
        area_arcmin2 = (
            math.pi / 4.0 * self.major_axis_arcmin * self.minor_axis_arcmin
        )
        if area_arcmin2 <= 0.0:
            return None
        area_arcsec2 = area_arcmin2 * 60.0**2
        return self.magnitude + 2.5 * math.log10(area_arcsec2)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DeepSkyObject:
        """Reconstruct an object from a mapping produced by :meth:`to_dict`."""
        payload = dict(data)
        payload["provenance"] = Provenance.from_dict(payload["provenance"])
        payload["object_type"] = DsoType(payload["object_type"])
        payload["cross_ids"] = tuple(payload.get("cross_ids") or ())
        return cls(**payload)
