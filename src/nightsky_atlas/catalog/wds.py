"""Washington Double Star Catalog (WDS) importer.

Source: CDS ``B/wds``, *The Washington Visual Double Star Catalog* (Mason et al.),
maintained by the U.S. Naval Observatory.  The main part ``wds.dat`` is a
fixed-width file (130 bytes per record); byte ranges below follow the CDS
ReadMe.  The catalogue is a U.S. government work and is treated as public
domain; the USNO requests the acknowledgement recorded in
``data/fixtures/double_stars/SOURCE.md``.

WDS is an **overlay**, not a replacement for the star base: the importer yields
:class:`~nightsky_atlas.catalog.systems.StarSystem` records with catalogue
identity, components, separation, position angle and component magnitudes, but
no links to Tycho-2 stars.  Linking happens per chart
(:func:`~nightsky_atlas.catalog.systems.match_star_systems`), so WDS can never
overwrite Tycho-2 positions or magnitudes.

Import is deterministic and performs no network access.  Use
:func:`download_wds` explicitly to fetch the raw file.
"""

from __future__ import annotations

import gzip
import math
import urllib.request
from collections.abc import Iterator
from pathlib import Path

from nightsky_atlas.catalog.systems import StarSystem, combined_magnitude

__all__ = [
    "CATALOGUE",
    "CDS_URL",
    "EDITION",
    "FILENAME",
    "download_wds",
    "iter_wds_systems",
    "parse_wds_record",
    "raw_path",
]

CATALOGUE = "WDS"
EDITION = "2026-08-10"
CDS_URL = "https://cdsarc.cds.unistra.fr/ftp/B/wds/wds.dat.gz"
FILENAME = "wds.dat.gz"

_RECORD_LENGTH = 130

# Byte slices are 0-based half-open translations of the CDS ReadMe byte ranges.
_WDS_NAME = slice(0, 10)
_DISC = slice(10, 17)
_COMP = slice(17, 22)
_PA1 = slice(38, 41)
_PA2 = slice(42, 45)
_SEP1 = slice(46, 51)
_SEP2 = slice(52, 58)
_MAG1 = slice(58, 64)
_MAG2 = slice(64, 69)
_RAH = slice(112, 114)
_RAM = slice(114, 116)
_RAS = slice(116, 121)
_DE_SIGN = slice(121, 122)
_DED = slice(122, 124)
_DEM = slice(124, 126)
_DES = slice(126, 130)


def raw_path(raw_dir: str | Path) -> Path:
    """Return the expected raw ``wds.dat.gz`` path."""
    return Path(raw_dir) / FILENAME


def download_wds(dest_dir: str | Path, *, url: str = CDS_URL) -> Path:
    """Download the raw WDS main catalogue (explicit network use)."""
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
    try:
        return float(text)
    except ValueError:
        return None


def _parse_int(text: str) -> int | None:
    text = text.strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _parse_position(line: str) -> tuple[float, float] | None:
    ra_h = _parse_int(line[_RAH])
    ra_m = _parse_int(line[_RAM])
    ra_s = _parse_float(line[_RAS])
    dec_sign = line[_DE_SIGN].strip()
    dec_d = _parse_int(line[_DED])
    dec_m = _parse_int(line[_DEM])
    dec_s = _parse_float(line[_DES])
    if ra_h is None or ra_m is None or ra_s is None:
        return None
    if dec_d is None or dec_m is None or dec_s is None:
        return None
    ra_deg = ra_h * 15.0 + ra_m / 4.0 + ra_s / 240.0
    dec_deg = dec_d + dec_m / 60.0 + dec_s / 3600.0
    if dec_sign == "-":
        dec_deg = -dec_deg
    return ra_deg % 360.0, dec_deg


def _normalise(designation: str) -> str:
    return "".join(designation.split())


def _component_count(designation: str) -> int:
    """Count distinct components named in a WDS component designation.

    WDS letters components ``A``, ``B``, ``C`` ...; a lower-case suffix denotes
    a sub-component of the same letter (``Aa``), and ``-``/``,`` separate
    hierarchical or additional components.  Counting distinct upper-case letters
    therefore gives the number of components: ``AB`` -> 2, ``AB,CD`` -> 4,
    ``Aa,Ab`` -> 1.
    """
    return len({char for char in designation if char.isupper()})


def parse_wds_record(line: str) -> StarSystem | None:
    """Parse one fixed-width WDS record into a :class:`StarSystem`.

    Returns ``None`` when the record has no discoverer designation or no usable
    J2000 position, which would make it unusable as an overlay.
    """
    padded = line.rstrip("\n").ljust(_RECORD_LENGTH)
    designation = padded[_DISC].strip()
    wds_name = padded[_WDS_NAME].strip()
    if not designation or not wds_name:
        return None
    position = _parse_position(padded)
    if position is None:
        return None
    ra_deg, dec_deg = position

    component = padded[_COMP].strip()
    separation = _parse_float(padded[_SEP2])
    if separation is None:
        separation = _parse_float(padded[_SEP1])
    position_angle = _parse_float(padded[_PA2])
    if position_angle is None:
        position_angle = _parse_float(padded[_PA1])
    # WDS uses negative sentinels (typically -1) for unknown measures.
    if separation is not None and separation < 0.0:
        separation = None
    if position_angle is not None and not 0.0 <= position_angle <= 360.0:
        position_angle = None

    mag1 = _parse_float(padded[_MAG1])
    mag2 = _parse_float(padded[_MAG2])
    magnitudes = tuple(
        value for value in (mag1, mag2) if value is not None and math.isfinite(value)
    )

    source_id = _normalise(designation)
    identifier = f"system:wds:{source_id}"
    if component:
        identifier = f"{identifier}:{_normalise(component)}"
        source_id = f"{source_id}:{_normalise(component)}"

    return StarSystem(
        id=identifier,
        source=CATALOGUE,
        source_id=source_id,
        ra_deg=ra_deg,
        dec_deg=dec_deg,
        is_multiple=_component_count(component) > 2,
        separation_arcsec=separation,
        position_angle_deg=position_angle,
        component_magnitudes=magnitudes,
        combined_magnitude=combined_magnitude(magnitudes),
    )


def iter_wds_systems(path: str | Path) -> Iterator[StarSystem]:
    """Yield normalized systems from a raw WDS main catalogue file."""
    resolved = Path(path)
    opener = gzip.open if resolved.suffix == ".gz" else Path.open
    with opener(resolved, "rt", encoding="ascii") as handle:  # type: ignore[operator]
        for line in handle:
            if not line.strip():
                continue
            system = parse_wds_record(line)
            if system is not None:
                yield system