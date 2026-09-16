"""Hipparcos bright-star importer.

Source: I/239, *The Hipparcos and Tycho Catalogues* (ESA 1997), CDS/VizieR.
The main catalogue is distributed as a single fixed-width file,
``hip_main.dat``.  Byte ranges below follow the CDS ReadMe.

The Hipparcos catalogue is used as a **bright-star supplement** to Tycho-2:
Tycho's star mapper saturated on the brightest stars, so Tycho-2 omits them
(Deneb, Vega, Altair, Sirius, ...) while Hipparcos contains them.  Both
catalogues share the same ``CC-BY-NC-3.0 IGO`` license.

Normalization rules (documented because they define the stored display
magnitude and position, ``AGENTS.md`` section 5.1):

- store a J2000 position by propagating the ICRS position at epoch J1991.25
  with the catalogue proper motion over 8.75 years;
- display magnitude is Johnson ``V`` (``Vmag``); the single record without a
  ``Vmag`` falls back to the Hipparcos magnitude ``Hpmag``.

Import is deterministic and performs no network access.  Use
:func:`download_hipparcos` explicitly to fetch the raw file.
"""

from __future__ import annotations

import gzip
import math
import urllib.request
from collections.abc import Iterator
from pathlib import Path

from nightsky_atlas.catalog.models import Provenance, Star

__all__ = [
    "CATALOGUE",
    "CDS_URL",
    "EPOCH_J2000_YEAR",
    "FILENAME",
    "HIPPARCOS_EPOCH_YEAR",
    "VERSION",
    "download_hipparcos",
    "iter_hipparcos_stars",
    "parse_hipparcos_record",
    "raw_path",
]

CATALOGUE = "HIP"
VERSION = "I/239"
CDS_URL = "https://cdsarc.cds.unistra.fr/ftp/I/239/hip_main.dat"
FILENAME = "hip_main.dat"

HIPPARCOS_EPOCH_YEAR = 1991.25
EPOCH_J2000_YEAR = 2000.0
_EPOCH_DELTA_YEARS = EPOCH_J2000_YEAR - HIPPARCOS_EPOCH_YEAR

# Byte slices are 0-based half-open translations of the CDS ReadMe byte ranges.
_HIP = slice(8, 14)
_VMAG = slice(41, 46)
_RA_DEG = slice(51, 63)
_DEC_DEG = slice(64, 76)
_PM_RA = slice(87, 95)
_PM_DEC = slice(96, 104)
_HPMAG = slice(274, 281)

_MAS_PER_DEG = 3_600_000.0


def raw_path(raw_dir: str | Path) -> Path:
    """Return the expected raw ``hip_main.dat`` path."""
    return Path(raw_dir) / FILENAME


def download_hipparcos(dest_dir: str | Path, *, url: str = CDS_URL) -> Path:
    """Download the raw Hipparcos main catalogue (explicit network use)."""
    directory = Path(dest_dir)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / FILENAME
    with urllib.request.urlopen(url) as response, target.open("wb") as handle:
        handle.write(response.read())
    return target


def _parse_float(text: str) -> float | None:
    text = text.strip()
    if not text:
        return None
    return float(text)


def _propagate_to_j2000(
    ra_deg: float, dec_deg: float, pm_ra_mas: float | None, pm_dec_mas: float | None
) -> tuple[float, float]:
    """Propagate an ICRS position from J1991.25 to J2000.0."""
    dec = dec_deg
    ra = ra_deg
    if pm_dec_mas is not None:
        dec += pm_dec_mas * _EPOCH_DELTA_YEARS / _MAS_PER_DEG
    if pm_ra_mas is not None:
        cos_dec = math.cos(math.radians(dec))
        if abs(cos_dec) > 1e-9:
            ra += pm_ra_mas * _EPOCH_DELTA_YEARS / (_MAS_PER_DEG * cos_dec)
    return ra % 360.0, dec


def parse_hipparcos_record(line: str) -> Star | None:
    """Parse one fixed-width Hipparcos record into a :class:`Star`.

    Returns ``None`` when the record has no usable astrometric solution or no
    magnitude, which would make it unplottable.
    """
    hip = _parse_float(line[_HIP])
    if hip is None:
        return None
    ra_deg = _parse_float(line[_RA_DEG])
    dec_deg = _parse_float(line[_DEC_DEG])
    if ra_deg is None or dec_deg is None:
        return None

    magnitude = _parse_float(line[_VMAG])
    if magnitude is None:
        magnitude = _parse_float(line[_HPMAG])
    if magnitude is None:
        return None

    ra_deg, dec_deg = _propagate_to_j2000(
        ra_deg,
        dec_deg,
        _parse_float(line[_PM_RA]),
        _parse_float(line[_PM_DEC]),
    )

    identifier = int(hip)
    return Star(
        id=f"HIP {identifier}",
        ra_deg=ra_deg,
        dec_deg=dec_deg,
        magnitude=magnitude,
        provenance=Provenance(
            catalogue=CATALOGUE, source_id=f"{identifier:06d}", version=VERSION
        ),
    )


def iter_hipparcos_stars(path: str | Path) -> Iterator[Star]:
    """Yield normalized bright stars from the raw Hipparcos main catalogue."""
    resolved = Path(path)
    opener = gzip.open if resolved.suffix == ".gz" else Path.open
    with opener(resolved, "rt", encoding="ascii") as handle:  # type: ignore[operator]
        for line in handle:
            if not line.strip():
                continue
            star = parse_hipparcos_record(line)
            if star is not None:
                yield star
