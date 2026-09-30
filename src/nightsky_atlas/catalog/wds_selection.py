"""Astronomical profile filters for WDS double-star overlay records."""

from __future__ import annotations

from typing import Protocol

from nightsky_atlas.catalog.systems import StarSystem


class _PairLimit(Protocol):
    min_sep_arcsec: float | None
    max_sep_arcsec: float
    max_secondary_mag: float


class _DeltaMagnitudeLimit(Protocol):
    max_sep_arcsec: float
    max_delta_mag: float


class _SelectionConfig(Protocol):
    limits: tuple[_PairLimit, ...]
    delta_mag_limits: tuple[_DeltaMagnitudeLimit, ...]


def pair_passes_profile(pair: StarSystem, config: _SelectionConfig) -> bool:
    """Whether a WDS pair meets the configured separation/magnitude envelope."""
    separation = pair.separation_arcsec
    secondary_magnitude = pair.secondary_magnitude
    if separation is None or secondary_magnitude is None:
        return False
    limit = next(
        (
            item
            for item in config.limits
            if separation <= item.max_sep_arcsec
            and (item.min_sep_arcsec is None or separation > item.min_sep_arcsec)
        ),
        None,
    )
    if limit is None or secondary_magnitude > limit.max_secondary_mag:
        return False
    return pair_passes_delta_magnitude(pair, config)


def pair_passes_delta_magnitude(pair: StarSystem, config: _SelectionConfig) -> bool:
    """Apply a deliberately simple close-pair magnitude-difference filter."""
    separation = pair.separation_arcsec
    delta_magnitude = pair.delta_magnitude
    if separation is None or delta_magnitude is None:
        return True
    limit = next(
        (item for item in config.delta_mag_limits if separation < item.max_sep_arcsec),
        None,
    )
    return limit is None or delta_magnitude <= limit.max_delta_mag
