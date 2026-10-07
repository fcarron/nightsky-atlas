"""Shared, copyright-conscious parsers for simple observing-list exports."""

from __future__ import annotations

import csv
import math
import re
from pathlib import Path
from typing import Any

from nightsky_atlas.catalog.observing_lists import canonical_designation
from nightsky_atlas.research.observing_lists.models import (
    ExternalObservingList,
    ExternalObservingListEntry,
)

_HEADER_ALIASES = {
    "designation": {"designation", "object", "objectid", "id", "name", "target", "catalogueid"},
    "catalogue": {"catalogue", "catalog", "catalogname", "catalogueprefix"},
    "ra": {"ra", "rightascension", "radeg", "ra2000", "raj2000"},
    "dec": {"dec", "declination", "decdeg", "dec2000", "decj2000"},
    "object_type": {"type", "objecttype", "class"},
    "constellation": {"constellation", "con", "const"},
    "size": {"size", "diameter", "extent", "majoraxis"},
}


def normalize_external_designation(value: str) -> str:
    """Normalize catalogue spelling using project rules plus common separators."""
    text = value.strip()
    if not text:
        return ""
    compact = re.sub(r"\s+", "", text).upper()
    compact = re.sub(r"^(NGC|IC)[-./]+", r"\1", compact)
    compact = re.sub(r"^(HCG|PGC|MEL|CR|CL)[-./]+", r"\1", compact)
    return canonical_designation(compact)


def normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def columns_for(headers: list[str]) -> dict[str, int]:
    normalized = [normalize_header(value) for value in headers]
    result: dict[str, int] = {}
    for field, aliases in _HEADER_ALIASES.items():
        found = next((i for i, value in enumerate(normalized) if value in aliases), None)
        if found is not None:
            result[field] = found
    return result


def designation_from_row(row: list[str], columns: dict[str, int]) -> str:
    designation = _cell(row, columns.get("designation"))
    catalogue = _cell(row, columns.get("catalogue"))
    if designation and catalogue and not re.match(r"^[A-Za-z]+", designation):
        return f"{catalogue} {designation}"
    return designation


def _cell(row: list[str], index: int | None) -> str:
    return row[index].strip() if index is not None and index < len(row) else ""


def parse_angle(value: str, *, is_ra: bool) -> float | None:
    """Parse decimal degrees or common sexagesimal coordinates."""
    value = value.strip()
    if not value:
        return None
    try:
        number = float(value)
    except ValueError:
        pass
    else:
        if math.isfinite(number):
            if is_ra and 0.0 <= number <= 24.0 and "." not in value:
                return number * 15.0
            return number
        raise ValueError(f"coordinate is not finite: {value!r}")

    cleaned = value.casefold().replace("−", "-")
    sign = -1.0 if cleaned.lstrip().startswith("-") else 1.0
    parts = re.findall(r"\d+(?:\.\d+)?", cleaned)
    if not parts or len(parts) > 3:
        raise ValueError(f"invalid coordinate: {value!r}")
    numbers = [float(part) for part in parts]
    degrees = numbers[0] + (numbers[1] / 60.0 if len(numbers) > 1 else 0.0)
    degrees += numbers[2] / 3600.0 if len(numbers) > 2 else 0.0
    result = sign * degrees * (15.0 if is_ra else 1.0)
    if not math.isfinite(result):
        raise ValueError(f"coordinate is not finite: {value!r}")
    return result


def parse_size_arcmin(value: str) -> float | None:
    value = value.strip().replace(",", ".")
    if not value:
        return None
    match = re.search(r"\d+(?:\.\d+)?", value)
    if not match:
        raise ValueError(f"invalid angular size: {value!r}")
    size = float(match.group())
    if '"' in value or "sec" in value.casefold() or "arcsec" in value.casefold():
        size /= 60.0
    if not math.isfinite(size) or size <= 0:
        raise ValueError(f"invalid angular size: {value!r}")
    return size


def entries_from_csv(
    paths: tuple[Path, ...], *, source: str, source_list: str
) -> tuple[ExternalObservingListEntry, ...]:
    entries: list[ExternalObservingListEntry] = []
    for path in paths:
        delimiter = "\t" if path.suffix.casefold() == ".tsv" else ","
        try:
            with path.open(encoding="utf-8-sig", newline="") as handle:
                reader = csv.reader(handle, delimiter=delimiter)
                headers = next(reader, None)
                if not headers:
                    raise ValueError(f"empty list file: {path}")
                columns = columns_for(headers)
                if "designation" not in columns:
                    raise ValueError(
                        f"{path}: no designation column; recognized headers include "
                        "designation, object, name, id, catalogue, RA, Dec, type, constellation"
                    )
                for row_number, row in enumerate(reader, start=2):
                    if not any(cell.strip() for cell in row):
                        continue
                    raw = designation_from_row(row, columns)
                    try:
                        ra = parse_angle(_cell(row, columns.get("ra")), is_ra=True)
                        dec = parse_angle(_cell(row, columns.get("dec")), is_ra=False)
                        if (ra is None) != (dec is None):
                            raise ValueError("both RA and Dec are required together")
                        if ra is not None and not 0.0 <= ra < 360.0:
                            raise ValueError("RA must be in [0, 360) degrees")
                        if dec is not None and not -90.0 <= dec <= 90.0:
                            raise ValueError("Dec must be in [-90, 90] degrees")
                        size = parse_size_arcmin(_cell(row, columns.get("size")))
                        problem = None if raw else "missing designation"
                    except ValueError as exc:
                        ra = dec = size = None
                        problem = str(exc)
                    entries.append(
                        ExternalObservingListEntry(
                            source=source,
                            source_list=source_list,
                            locator=f"{path.name}:{row_number}",
                            imported_file=path.name,
                            raw_designation=raw,
                            normalized_designation=normalize_external_designation(raw),
                            object_type_hint=_optional(_cell(row, columns.get("object_type"))),
                            constellation_hint=_optional(_cell(row, columns.get("constellation"))),
                            ra_deg=ra,
                            dec_deg=dec,
                            size_arcmin=size,
                            parse_error=problem,
                        )
                    )
        except UnicodeDecodeError as exc:
            raise ValueError(f"{path}: list file must be UTF-8 text: {exc}") from exc
    return tuple(entries)


def entries_from_designation_text(
    paths: tuple[Path, ...], *, source: str, source_list: str
) -> tuple[ExternalObservingListEntry, ...]:
    """Read one designation per line; comments and blank lines are ignored."""
    entries: list[ExternalObservingListEntry] = []
    for path in paths:
        try:
            lines = path.read_text(encoding="utf-8-sig").splitlines()
        except UnicodeDecodeError as exc:
            raise ValueError(f"{path}: list file must be UTF-8 text: {exc}") from exc
        for row_number, line in enumerate(lines, start=1):
            designation = line.strip()
            if not designation or designation.startswith("#"):
                continue
            entries.append(
                ExternalObservingListEntry(
                    source=source,
                    source_list=source_list,
                    locator=f"{path.name}:{row_number}",
                    imported_file=path.name,
                    raw_designation=designation,
                    normalized_designation=normalize_external_designation(designation),
                )
            )
    return tuple(entries)


def as_external_list(
    entries: tuple[ExternalObservingListEntry, ...],
    paths: tuple[Path, ...],
    *,
    source: str,
    source_list: str,
) -> ExternalObservingList:
    return ExternalObservingList(
        source=source,
        source_list=source_list,
        imported_files=tuple(path.name for path in paths),
        entries=entries,
    )


def _optional(value: str) -> str | None:
    return value or None


def parse_record_for_test(row: dict[str, Any]) -> dict[str, Any]:
    """Stable hook for synthetic parser tests; never persists arbitrary columns."""
    return {key: value for key, value in row.items() if key in _HEADER_ALIASES}
