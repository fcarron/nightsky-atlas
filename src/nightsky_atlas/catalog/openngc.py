"""OpenNGC deep-sky catalogue importer.

Source: OpenNGC (https://github.com/mattiaverga/OpenNGC), released under
CC-BY-SA-4.0.  The database is semicolon-separated with one object per row.

Normalization notes:

- ``Name`` is the canonical identifier;
- type codes are mapped onto the semantic :class:`DsoType` vocabulary rather
  than exposed directly;
- coordinates are sexagesimal and converted to explicit float degrees;
- magnitude prefers ``V-Mag`` and falls back to ``B-Mag``, recording the band;
- angular dimensions are arcminutes and position angle is degrees;
- "Identifiers" and the Messier number become cross identifiers.

Missing optional fields are stored as ``None``; the model never assumes they
exist.
"""

from __future__ import annotations

import csv
import urllib.request
from collections.abc import Iterable, Iterator
from pathlib import Path

from nightsky_atlas.catalog.models import DeepSkyObject, DsoType, Provenance

__all__ = [
    "CATALOGUE",
    "DEFAULT_SOURCE_URLS",
    "download_openngc",
    "iter_openngc_objects",
    "load_sample_dsos",
    "parse_openngc_row",
]

CATALOGUE = "OpenNGC"
DEFAULT_SOURCE_URLS = (
    "https://raw.githubusercontent.com/mattiaverga/OpenNGC/master/database_files/NGC.csv",
    "https://raw.githubusercontent.com/mattiaverga/OpenNGC/master/database_files/addendum.csv",
)

_TYPE_MAP: dict[str, DsoType] = {
    "G": DsoType.GALAXY,
    "GPair": DsoType.GALAXY_CLUSTER,
    "GTrpl": DsoType.GALAXY_CLUSTER,
    "GGroup": DsoType.GALAXY_CLUSTER,
    "OCl": DsoType.OPEN_CLUSTER,
    "Cl+N": DsoType.BRIGHT_NEBULA,
    "*Ass": DsoType.OPEN_CLUSTER,
    "GCl": DsoType.GLOBULAR_CLUSTER,
    "PN": DsoType.PLANETARY_NEBULA,
    "HII": DsoType.BRIGHT_NEBULA,
    "Neb": DsoType.BRIGHT_NEBULA,
    "EmN": DsoType.BRIGHT_NEBULA,
    "RfN": DsoType.BRIGHT_NEBULA,
    "SNR": DsoType.BRIGHT_NEBULA,
    "**": DsoType.DOUBLE_STAR,
    "*": DsoType.STAR,
    "Nova": DsoType.STAR,
    "Other": DsoType.OTHER,
}

_SKIP_TYPES = {"", "Dup", "NonEx", "Type"}


def download_openngc(
    dest_dir: str | Path, *, urls: Iterable[str] = DEFAULT_SOURCE_URLS
) -> list[Path]:
    """Download the raw OpenNGC CSV files into ``dest_dir`` (explicit network use)."""
    directory = Path(dest_dir)
    directory.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for url in urls:
        target = directory / url.rsplit("/", 1)[-1]
        with urllib.request.urlopen(url) as response, target.open("wb") as handle:
            handle.write(response.read())
        paths.append(target)
    return paths


def _parse_ra_hms(text: str) -> float:
    hours, minutes, seconds = (float(part) for part in text.strip().split(":"))
    return 15.0 * (hours + minutes / 60.0 + seconds / 3600.0)


def _parse_dec_dms(text: str) -> float:
    stripped = text.strip()
    sign = -1.0 if stripped.startswith("-") else 1.0
    degrees, minutes, seconds = (float(part) for part in stripped.lstrip("+-").split(":"))
    return sign * (degrees + minutes / 60.0 + seconds / 3600.0)


def _parse_float(text: str | None) -> float | None:
    if text is None or not text.strip():
        return None
    return float(text)


def _cross_ids(row: dict[str, str], name: str) -> tuple[str, ...]:
    identifiers: list[str] = []
    messier = row.get("M", "").strip()
    if messier:
        identifiers.append(f"M{int(messier)}")
    raw = row.get("Identifiers", "") or ""
    identifiers.extend(part.strip() for part in raw.split(",") if part.strip())
    seen: list[str] = []
    for identifier in identifiers:
        if identifier != name and identifier not in seen:
            seen.append(identifier)
    return tuple(seen)


def parse_openngc_row(row: dict[str, str]) -> DeepSkyObject | None:
    """Parse one OpenNGC row into a :class:`DeepSkyObject`.

    Returns ``None`` for rows that are duplicate or non-existent entries, or
    that have no usable position or recognized type.
    """
    name = (row.get("Name") or "").strip()
    type_code = (row.get("Type") or "").strip()
    if not name or type_code in _SKIP_TYPES:
        return None
    object_type = _TYPE_MAP.get(type_code)
    if object_type is None:
        object_type = DsoType.OTHER

    ra_text = (row.get("RA") or "").strip()
    dec_text = (row.get("Dec") or "").strip()
    if not ra_text or not dec_text:
        return None

    magnitude = _parse_float(row.get("V-Mag"))
    magnitude_band = "V" if magnitude is not None else None
    if magnitude is None:
        magnitude = _parse_float(row.get("B-Mag"))
        magnitude_band = "B" if magnitude is not None else None

    major = _parse_float(row.get("MajAx"))
    minor = _parse_float(row.get("MinAx"))
    position_angle = _parse_float(row.get("PosAng"))
    if major is not None and major <= 0.0:
        major = None
    if minor is not None and minor <= 0.0:
        minor = None

    common_name = (row.get("Common names") or "").strip() or None
    constellation = (row.get("Const") or "").strip() or None

    return DeepSkyObject(
        id=name,
        ra_deg=_parse_ra_hms(ra_text),
        dec_deg=_parse_dec_dms(dec_text),
        object_type=object_type,
        provenance=Provenance(catalogue=CATALOGUE, source_id=name, version=None),
        magnitude=magnitude,
        magnitude_band=magnitude_band,
        major_axis_arcmin=major,
        minor_axis_arcmin=minor,
        position_angle_deg=position_angle,
        common_name=common_name,
        constellation=constellation,
        cross_ids=_cross_ids(row, name),
    )


def iter_openngc_objects(paths: Iterable[Path]) -> Iterator[DeepSkyObject]:
    """Yield normalized deep-sky objects from OpenNGC CSV files."""
    for path in paths:
        with Path(path).open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle, delimiter=";")
            for row in reader:
                obj = parse_openngc_row(row)
                if obj is not None:
                    yield obj


def load_sample_dsos(path: str | Path) -> list[DeepSkyObject]:
    """Load a small committed OpenNGC-format fixture."""
    return list(iter_openngc_objects([Path(path)]))