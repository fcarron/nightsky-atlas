"""Merge a primary star catalogue with a bright-star supplement.

Tycho-2 is the primary star catalogue, but its star mapper saturated on the
brightest stars, so it omits objects such as Deneb, Vega, Altair and Sirius.
Hipparcos supplies exactly those stars.  Duplicates (stars present in both
catalogues) are resolved deterministically in favour of the primary catalogue:
a supplement star is dropped when a primary star lies within
``radius_arcsec`` of it.

Matching is positional.  Both catalogues are first normalized to J2000, so a
small radius is sufficient; a slightly generous default guards against the
residual proper-motion and epoch differences.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Iterator

from nightsky_atlas.catalog.models import Star

__all__ = ["DEFAULT_MATCH_RADIUS_ARCSEC", "merge_stars"]

DEFAULT_MATCH_RADIUS_ARCSEC = 3.0

# Cell size for the positional hash.  Must be at least the match radius so a
# match can only fall into the same or an adjacent cell.
_CELL_DEG = 0.01
_CELLS_PER_DEG = 100
_RA_CELLS = 360 * _CELLS_PER_DEG


def _cell(ra_deg: float, dec_deg: float) -> tuple[int, int]:
    return int(ra_deg // _CELL_DEG) % _RA_CELLS, int(dec_deg // _CELL_DEG)


def _separation_arcsec(
    ra_a: float, dec_a: float, ra_b: float, dec_b: float
) -> float:
    """Approximate angular separation for nearby positions, in arcseconds."""
    delta_ra = (ra_a - ra_b + 180.0) % 360.0 - 180.0
    mean_dec = math.radians((dec_a + dec_b) / 2.0)
    d_ra = delta_ra * math.cos(mean_dec)
    d_dec = dec_a - dec_b
    return math.hypot(d_ra, d_dec) * 3600.0


def merge_stars(
    primary: Iterable[Star],
    supplement: Iterable[Star],
    *,
    radius_arcsec: float = DEFAULT_MATCH_RADIUS_ARCSEC,
) -> Iterator[Star]:
    """Yield ``primary`` plus supplement stars absent from ``primary``.

    Every primary star is yielded unchanged.  Supplement stars are buffered and
    emitted only when no primary star lies within ``radius_arcsec``.
    """
    candidates = list(supplement)
    grid: dict[tuple[int, int], list[int]] = {}
    for index, star in enumerate(candidates):
        grid.setdefault(_cell(star.ra_deg, star.dec_deg), []).append(index)

    consumed = [False] * len(candidates)
    max_ra_cell = _RA_CELLS

    for star in primary:
        if grid:
            ra_cell, dec_cell = _cell(star.ra_deg, star.dec_deg)
            for dra in (-1, 0, 1):
                for ddec in (-1, 0, 1):
                    bucket = grid.get(((ra_cell + dra) % max_ra_cell, dec_cell + ddec))
                    if not bucket:
                        continue
                    for index in bucket:
                        if consumed[index]:
                            continue
                        candidate = candidates[index]
                        if (
                            _separation_arcsec(
                                star.ra_deg, star.dec_deg, candidate.ra_deg, candidate.dec_deg
                            )
                            <= radius_arcsec
                        ):
                            consumed[index] = True
        yield star

    for index, star in enumerate(candidates):
        if not consumed[index]:
            yield star
