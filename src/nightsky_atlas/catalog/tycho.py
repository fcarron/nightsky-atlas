"""Tycho-2 catalogue importer.

Source: I/259, *The Tycho-2 Catalogue* (Hog et al. 2000), CDS/VizieR.
The catalogue is distributed as fixed-width records split across
``tyc2.dat.NN.gz`` parts.  Byte ranges below follow the CDS ReadMe.

Normalization rules (documented because they define the stored display
magnitude, ``AGENTS.md`` section 5.1):

- coordinates prefer the ICRS J2000 mean position (``RAmdeg``/``DEmdeg``),
  except for ``pflag=P`` photocentre solutions: their component-specific
  observed positions are propagated to J2000 with the catalogue proper motion;
  when the mean position is absent, the observed position is used as a fallback;
- display magnitude is Johnson ``V`` derived from Tycho magnitudes as
  ``V = VT - 0.090 * (BT - VT)``; if only one is present it is used directly.

Import is deterministic and performs no network access.  Use
:func:`download_tycho2` explicitly to fetch raw parts.
"""

from __future__ import annotations

import gzip
import math
import urllib.request
from collections.abc import Iterable, Iterator
from pathlib import Path

from nightsky_atlas.catalog.models import Provenance, Star

__all__ = [
    "CATALOGUE",
    "CDS_BASE_URL",
    "PART_COUNT",
    "VERSION",
    "download_tycho2",
    "iter_tycho2_stars",
    "parse_tycho2_record",
    "raw_part_paths",
]

CATALOGUE = "TYC2"
VERSION = "I/259"
CDS_BASE_URL = "https://cdsarc.cds.unistra.fr/ftp/I/259"
PART_COUNT = 20

# Byte slices are 0-based half-open translations of the CDS ReadMe byte ranges.
_TYC1 = slice(0, 4)
_TYC2 = slice(5, 10)
_TYC3 = slice(11, 12)
_RA_MEAN = slice(15, 27)
_DEC_MEAN = slice(28, 40)
_PFLAG = 13
_PM_RA = slice(41, 48)
_PM_DEC = slice(49, 56)
_BT_MAG = slice(110, 116)
_VT_MAG = slice(123, 129)
_HIP = slice(142, 148)
_RA_OBSERVED = slice(152, 164)
_DEC_OBSERVED = slice(165, 177)
_EPOCH_RA = slice(178, 182)
_EPOCH_DEC = slice(183, 187)
_MAS_PER_DEG = 3_600_000.0


def raw_part_paths(raw_dir: str | Path) -> list[Path]:
    """Return the Tycho-2 part paths in deterministic order."""
    directory = Path(raw_dir)
    return [
        directory / f"tyc2.dat.{index:02d}.gz" for index in range(PART_COUNT)
    ]


def download_tycho2(dest_dir: str | Path, *, base_url: str = CDS_BASE_URL) -> list[Path]:
    """Download all raw Tycho-2 parts into ``dest_dir`` (explicit network use)."""
    directory = Path(dest_dir)
    directory.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for index in range(PART_COUNT):
        filename = f"tyc2.dat.{index:02d}.gz"
        target = directory / filename
        url = f"{base_url}/{filename}"
        with urllib.request.urlopen(url) as response, target.open("wb") as handle:
            handle.write(response.read())
        paths.append(target)
    return paths


def _parse_float(text: str) -> float | None:
    text = text.strip()
    if not text:
        return None
    return float(text)


def _parse_int(text: str) -> int | None:
    text = text.strip()
    if not text:
        return None
    return int(text)


def _component_position_j2000(line: str) -> tuple[float, float] | None:
    ra_deg = _parse_float(line[_RA_OBSERVED])
    dec_deg = _parse_float(line[_DEC_OBSERVED])
    if ra_deg is None or dec_deg is None:
        return None
    pm_dec = _parse_float(line[_PM_DEC])
    dec_epoch = _parse_float(line[_EPOCH_DEC])
    if pm_dec is not None and dec_epoch is not None:
        dec_deg += pm_dec * (2000.0 - 1990.0 - dec_epoch) / _MAS_PER_DEG
    pm_ra = _parse_float(line[_PM_RA])
    ra_epoch = _parse_float(line[_EPOCH_RA])
    if pm_ra is not None and ra_epoch is not None:
        cos_dec = math.cos(math.radians(dec_deg))
        if abs(cos_dec) > 1e-9:
            ra_deg += pm_ra * (2000.0 - 1990.0 - ra_epoch) / (_MAS_PER_DEG * cos_dec)
    return ra_deg % 360.0, dec_deg


def parse_tycho2_record(line: str) -> Star | None:
    """Parse one fixed-width Tycho-2 record into a :class:`Star`.

    Returns ``None`` when the record has no usable position or magnitude,
    which would make it unplottable.
    """
    tyc1 = _parse_int(line[_TYC1])
    tyc2 = _parse_int(line[_TYC2])
    tyc3 = _parse_int(line[_TYC3])
    if tyc1 is None or tyc2 is None or tyc3 is None:
        return None

    component_position = _component_position_j2000(line) if line[_PFLAG] == "P" else None
    if component_position is not None:
        ra_deg, dec_deg = component_position
    else:
        ra_deg = _parse_float(line[_RA_MEAN])
        dec_deg = _parse_float(line[_DEC_MEAN])
        if ra_deg is None or dec_deg is None:
            ra_deg = _parse_float(line[_RA_OBSERVED])
            dec_deg = _parse_float(line[_DEC_OBSERVED])
    if ra_deg is None or dec_deg is None:
        return None

    bt_mag = _parse_float(line[_BT_MAG])
    vt_mag = _parse_float(line[_VT_MAG])
    if bt_mag is not None and vt_mag is not None:
        magnitude = vt_mag - 0.090 * (bt_mag - vt_mag)
    elif vt_mag is not None:
        magnitude = vt_mag
    elif bt_mag is not None:
        magnitude = bt_mag
    else:
        return None

    source_id = f"{tyc1:04d}-{tyc2:05d}-{tyc3}"
    hip = _parse_int(line[_HIP])
    return Star(
        id=f"TYC {tyc1}-{tyc2}-{tyc3}",
        ra_deg=ra_deg,
        dec_deg=dec_deg,
        magnitude=magnitude,
        provenance=Provenance(catalogue=CATALOGUE, source_id=source_id, version=VERSION),
        hip_id=None if hip is None else f"HIP {hip}",
    )


def iter_tycho2_stars(paths: Iterable[Path]) -> Iterator[Star]:
    """Yield normalized stars from one or more raw Tycho-2 part files."""
    for path in paths:
        opener = gzip.open if path.suffix == ".gz" else Path.open
        with opener(path, "rt", encoding="ascii") as handle:  # type: ignore[operator]
            for line in handle:
                if not line.strip():
                    continue
                star = parse_tycho2_record(line)
                if star is not None:
                    yield star
