"""Astronomical profile filters for WDS double-star overlay records."""

from __future__ import annotations

from typing import Protocol

from nightsky_atlas.catalog.systems import StarSystem


class _PairLimit(Protocol):
    max_sep_arcsec: float
    max_secondary_mag: float


class _SelectionConfig(Protocol):
    minimum_separation_arcsec: float
    limits: tuple[_PairLimit, ...]


def pair_passes_profile(pair: StarSystem, config: _SelectionConfig) -> bool:
    """Whether a WDS pair meets the configured separation/magnitude envelope."""
    separation = pair.separation_arcsec
    secondary_magnitude = pair.secondary_magnitude
    if separation is None or secondary_magnitude is None:
        return False
    if separation < config.minimum_separation_arcsec:
        return False
    limit = next(
        (
            item
            for item in config.limits
            if separation <= item.max_sep_arcsec
        ),
        None,
    )
    return limit is not None and secondary_magnitude <= limit.max_secondary_mag
