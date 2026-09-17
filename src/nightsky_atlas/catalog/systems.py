"""Visual double/multiple star systems and their matching to catalogue stars.

Double stars are **not** inferred from the primary star catalogue.  Proximity in
Tycho-2 does not make a physical or even a catalogued pair, so the star base
(Tycho-2 plus the bright-star supplement) stays the source of truth for single
star positions and magnitudes, while a dedicated overlay catalogue (the
Washington Double Star Catalog, :mod:`nightsky_atlas.catalog.wds`) supplies
system identity, components, separation, position angle and component
magnitudes (``AGENTS.md`` sections 5 and 8).

A :class:`StarSystem` never mutates a :class:`~nightsky_atlas.catalog.models.Star`.
It only *links* to stars by stable ID, and the link carries a
:class:`MatchStatus` so an uncertain match can never silently change the chart:
only ``exact`` and ``positional`` matches are treated as safe.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import asdict, dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Any

from nightsky_atlas.astronomy.angles import angular_separation_deg
from nightsky_atlas.catalog.models import Star

__all__ = [
    "DEFAULT_AMBIGUOUS_RADIUS_ARCSEC",
    "DEFAULT_COMPANION_TOLERANCE_ARCSEC",
    "DEFAULT_MATCH_TOLERANCE_ARCSEC",
    "MatchStatus",
    "StarSystem",
    "VisualPriority",
    "combined_magnitude",
    "load_system_catalog",
    "match_star_system",
    "match_star_systems",
    "write_system_catalog",
]

_SAFE_STATUSES = frozenset({"exact", "positional"})

DEFAULT_MATCH_TOLERANCE_ARCSEC = 2.0
DEFAULT_COMPANION_TOLERANCE_ARCSEC = 3.0
DEFAULT_AMBIGUOUS_RADIUS_ARCSEC = 30.0

# Coarse positional hash so matching does not scan every star for every system.
_CELL_DEG = 0.05
_RA_CELLS = int(round(360.0 / _CELL_DEG))


class MatchStatus(StrEnum):
    """How confidently a system was linked to catalogue stars.

    ``EXACT`` means a catalogue cross-identifier linked the system; ``POSITIONAL``
    means a single star matched the system position within tolerance;
    ``AMBIGUOUS`` means several candidates competed; ``UNMATCHED`` means no star
    was found.  Only the first two may influence the printed chart.
    """

    EXACT = "exact"
    POSITIONAL = "positional"
    AMBIGUOUS = "ambiguous"
    UNMATCHED = "unmatched"


class VisualPriority(StrEnum):
    """Observing interest of a visual double, for later label/symbol weighting."""

    NORMAL = "normal"
    NOTABLE = "notable"
    SHOWCASE = "showcase"


def combined_magnitude(magnitudes: Iterable[float | None]) -> float | None:
    """Combine component magnitudes into one, or ``None`` when none are known.

    ``m = -2.5 * log10(sum(10 ** (-0.4 * m_i)))``; for 6.0 and 7.0 this gives
    approximately 5.64.
    """
    values = [
        float(value)
        for value in magnitudes
        if value is not None and math.isfinite(float(value))
    ]
    if not values:
        return None
    total = sum(10.0 ** (-0.4 * value) for value in values)
    return -2.5 * math.log10(total)


@dataclass(frozen=True, slots=True)
class StarSystem:
    """A catalogued visual double or multiple star system.

    ``primary_star_id`` and ``component_star_ids`` link to
    :class:`~nightsky_atlas.catalog.models.Star` IDs; they stay empty until a
    match succeeds.  ``component_star_ids`` holds the companions, not the
    primary.  ``source``/``source_id`` record catalogue provenance
    (``wds``/``STF3050``-style discoverer designation).
    """

    id: str
    source: str
    source_id: str
    ra_deg: float | None = None
    dec_deg: float | None = None
    primary_star_id: str | None = None
    component_star_ids: tuple[str, ...] = ()
    is_multiple: bool = False
    separation_arcsec: float | None = None
    position_angle_deg: float | None = None
    component_magnitudes: tuple[float, ...] = ()
    combined_magnitude: float | None = None
    visual_priority: VisualPriority = VisualPriority.NORMAL
    match_status: MatchStatus = MatchStatus.UNMATCHED

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("id must not be blank")
        if not self.source.strip():
            raise ValueError("source must not be blank")
        if not self.source_id.strip():
            raise ValueError("source_id must not be blank")
        for name in ("ra_deg", "dec_deg", "separation_arcsec", "position_angle_deg"):
            value = getattr(self, name)
            if value is not None and not math.isfinite(value):
                raise ValueError(f"{name} must be finite when present")
        if self.dec_deg is not None and not -90.0 <= self.dec_deg <= 90.0:
            raise ValueError(f"dec_deg must be within [-90, 90], got {self.dec_deg!r}")
        if self.ra_deg is not None and not 0.0 <= self.ra_deg < 360.0:
            raise ValueError(f"ra_deg must be within [0, 360), got {self.ra_deg!r}")
        if self.separation_arcsec is not None and self.separation_arcsec < 0.0:
            raise ValueError("separation_arcsec must not be negative")
        if self.position_angle_deg is not None and not (
            0.0 <= self.position_angle_deg <= 360.0
        ):
            raise ValueError(
                f"position_angle_deg must be within [0, 360], got {self.position_angle_deg!r}"
            )
        for magnitude in self.component_magnitudes:
            if not math.isfinite(magnitude):
                raise ValueError("component_magnitudes must be finite")
        if self.combined_magnitude is not None and not math.isfinite(
            self.combined_magnitude
        ):
            raise ValueError("combined_magnitude must be finite when present")
        if self.primary_star_id is not None and not self.primary_star_id.strip():
            raise ValueError("primary_star_id must not be blank when present")
        for star_id in self.component_star_ids:
            if not star_id.strip():
                raise ValueError("component_star_ids must not contain blank values")

    @property
    def is_safe_match(self) -> bool:
        """Whether the match is strong enough to influence the chart."""
        return self.match_status.value in _SAFE_STATUSES and self.primary_star_id is not None

    def linked_star_ids(self) -> tuple[str, ...]:
        """Return every linked star ID (primary first, then companions)."""
        ids = [self.primary_star_id] if self.primary_star_id else []
        ids.extend(self.component_star_ids)
        return tuple(ids)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable mapping of this system."""
        payload = asdict(self)
        payload["component_star_ids"] = list(self.component_star_ids)
        payload["component_magnitudes"] = list(self.component_magnitudes)
        payload["match_status"] = self.match_status.value
        payload["visual_priority"] = self.visual_priority.value
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StarSystem:
        """Reconstruct a system from a mapping produced by :meth:`to_dict`."""
        payload = dict(data)
        payload["component_star_ids"] = tuple(payload.get("component_star_ids") or ())
        payload["component_magnitudes"] = tuple(
            float(value) for value in payload.get("component_magnitudes") or ()
        )
        payload["match_status"] = MatchStatus(payload.get("match_status", "unmatched"))
        payload["visual_priority"] = VisualPriority(
            payload.get("visual_priority", "normal")
        )
        return cls(**payload)


def _cell_key(ra_deg: float, dec_deg: float) -> tuple[int, int]:
    return int(ra_deg // _CELL_DEG) % _RA_CELLS, int(dec_deg // _CELL_DEG)


def _build_grid(stars: Sequence[Star]) -> dict[tuple[int, int], list[Star]]:
    grid: dict[tuple[int, int], list[Star]] = {}
    for star in stars:
        grid.setdefault(_cell_key(star.ra_deg, star.dec_deg), []).append(star)
    return grid


def _nearby(
    grid: dict[tuple[int, int], list[Star]],
    ra_deg: float,
    dec_deg: float,
    radius_deg: float,
) -> Iterator[Star]:
    span = max(1, int(math.ceil(radius_deg / _CELL_DEG)))
    ra_cell, dec_cell = _cell_key(ra_deg, dec_deg)
    seen: set[str] = set()
    for dra in range(-span, span + 1):
        for ddec in range(-span, span + 1):
            for star in grid.get(((ra_cell + dra) % _RA_CELLS, dec_cell + ddec), ()):
                if star.id in seen:
                    continue
                seen.add(star.id)
                yield star


def _within(
    star: Star, ra_deg: float, dec_deg: float, tolerance_arcsec: float
) -> bool:
    separation_arcsec = (
        angular_separation_deg(star.ra_deg, star.dec_deg, ra_deg, dec_deg) * 3600.0
    )
    return separation_arcsec <= tolerance_arcsec


def _companion_position(
    ra_deg: float,
    dec_deg: float,
    separation_arcsec: float,
    position_angle_deg: float,
) -> tuple[float, float]:
    """Approximate the companion's position from separation and position angle.

    Position angle is measured from north through east.  The flat approximation
    is exact enough at the arcsecond scale of a double-star separation.
    """
    separation_deg = separation_arcsec / 3600.0
    angle = math.radians(position_angle_deg)
    dec2_deg = dec_deg + separation_deg * math.cos(angle)
    cos_dec = math.cos(math.radians(dec_deg))
    if abs(cos_dec) < 1e-12:
        return ra_deg, dec2_deg
    ra2_deg = ra_deg + separation_deg * math.sin(angle) / cos_dec
    return ra2_deg % 360.0, dec2_deg


def match_star_system(
    system: StarSystem,
    stars: Sequence[Star],
    *,
    tolerance_arcsec: float = DEFAULT_MATCH_TOLERANCE_ARCSEC,
    companion_tolerance_arcsec: float = DEFAULT_COMPANION_TOLERANCE_ARCSEC,
    ambiguous_radius_arcsec: float = DEFAULT_AMBIGUOUS_RADIUS_ARCSEC,
) -> StarSystem:
    """Link one system to the nearest matching stars.

    The primary is the dominant match: a single star within ``tolerance_arcsec``
    links positionally; several stars within that radius make the match
    ambiguous and the system is left unlinked, so it cannot change the chart.
    When separation and position angle are known the expected companion
    position is matched within the (wider) ``companion_tolerance_arcsec``; an
    ambiguous companion is simply not linked.
    """
    if system.primary_star_id or system.match_status is MatchStatus.EXACT:
        return system
    if system.ra_deg is None or system.dec_deg is None:
        return replace(system, match_status=MatchStatus.UNMATCHED)

    grid = _build_grid(stars)
    return _match_with_grid(
        system,
        grid,
        tolerance_arcsec=tolerance_arcsec,
        companion_tolerance_arcsec=companion_tolerance_arcsec,
        ambiguous_radius_arcsec=ambiguous_radius_arcsec,
    )


def _match_with_grid(
    system: StarSystem,
    grid: dict[tuple[int, int], list[Star]],
    *,
    tolerance_arcsec: float,
    companion_tolerance_arcsec: float,
    ambiguous_radius_arcsec: float,
) -> StarSystem:
    ra_deg = system.ra_deg
    dec_deg = system.dec_deg
    assert ra_deg is not None and dec_deg is not None

    ambiguous_radius_deg = ambiguous_radius_arcsec / 3600.0
    primary_candidates = [
        star
        for star in _nearby(grid, ra_deg, dec_deg, ambiguous_radius_deg)
        if _within(star, ra_deg, dec_deg, tolerance_arcsec)
    ]
    if not primary_candidates:
        return replace(system, match_status=MatchStatus.UNMATCHED)
    if len(primary_candidates) > 1:
        return replace(system, match_status=MatchStatus.AMBIGUOUS)

    primary = primary_candidates[0]
    component_ids: list[str] = []
    ambiguous = False
    if system.separation_arcsec is not None:
        position_angle = system.position_angle_deg or 0.0
        companion_ra, companion_dec = _companion_position(
            primary.ra_deg,
            primary.dec_deg,
            system.separation_arcsec,
            position_angle,
        )
        companion_candidates = [
            star
            for star in _nearby(
                grid, companion_ra, companion_dec, ambiguous_radius_deg
            )
            if star.id != primary.id
            and _within(star, companion_ra, companion_dec, companion_tolerance_arcsec)
        ]
        if len(companion_candidates) == 1:
            component_ids.append(companion_candidates[0].id)
        elif len(companion_candidates) > 1:
            ambiguous = True

    if ambiguous:
        return replace(system, match_status=MatchStatus.AMBIGUOUS)
    return replace(
        system,
        primary_star_id=primary.id,
        component_star_ids=tuple(component_ids),
        match_status=MatchStatus.POSITIONAL,
    )


def match_star_systems(
    systems: Iterable[StarSystem],
    stars: Sequence[Star],
    *,
    tolerance_arcsec: float = DEFAULT_MATCH_TOLERANCE_ARCSEC,
    companion_tolerance_arcsec: float = DEFAULT_COMPANION_TOLERANCE_ARCSEC,
    ambiguous_radius_arcsec: float = DEFAULT_AMBIGUOUS_RADIUS_ARCSEC,
) -> tuple[StarSystem, ...]:
    """Match many systems against one chart's stars, reusing a positional grid."""
    grid = _build_grid(stars)
    return tuple(
        _match_with_grid(
            system,
            grid,
            tolerance_arcsec=tolerance_arcsec,
            companion_tolerance_arcsec=companion_tolerance_arcsec,
            ambiguous_radius_arcsec=ambiguous_radius_arcsec,
        )
        for system in systems
    )


def write_system_catalog(path: str | Path, systems: Iterable[StarSystem]) -> int:
    """Write systems as compact, deterministic JSON and return the count."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = [system.to_dict() for system in systems]
    target.write_text(
        json.dumps(payload, separators=(",", ":"), sort_keys=True),
        encoding="utf-8",
    )
    return len(payload)


def load_system_catalog(path: str | Path) -> list[StarSystem]:
    """Load a processed star-system catalogue from JSON, or none if absent."""
    target = Path(path)
    if not target.exists():
        return []
    payload = json.loads(target.read_text(encoding="utf-8"))
    return [StarSystem.from_dict(item) for item in payload]