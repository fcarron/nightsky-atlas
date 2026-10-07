"""Adapter for AstroPlanner text/CSV object-list exports."""

from __future__ import annotations

import math
from pathlib import Path

from nightsky_atlas.research.observing_lists.models import (
    ExternalObservingList,
    ExternalObservingListEntry,
)
from nightsky_atlas.research.observing_lists.parser_base import (
    as_external_list,
    entries_from_csv,
    entries_from_designation_text,
    normalize_external_designation,
)

SOURCE_NAME = "AstroPlanner"


def parse(paths: tuple[Path, ...], *, list_name: str | None = None) -> ExternalObservingList:
    """Parse APTF plan text, exported CSV/TSV tables or designation lists."""
    if not paths:
        raise ValueError("no AstroPlanner input files found")
    unsupported = [path for path in paths if path.suffix.casefold() not in {".csv", ".tsv", ".txt"}]
    if unsupported:
        names = ", ".join(path.name for path in unsupported)
        raise ValueError(
            f"unsupported AstroPlanner file(s): {names}; export the plan object list as CSV/TSV "
            "or save one designation per line as .txt"
        )
    planfiles = tuple(path for path in paths if _is_planfile(path))
    name = list_name or (
        "NSOG DSO plans"
        if planfiles
        else (paths[0].parent.name if len(paths) > 1 else paths[0].stem)
    )
    tables = tuple(path for path in paths if path.suffix.casefold() in {".csv", ".tsv"})
    text = tuple(
        path for path in paths if path.suffix.casefold() == ".txt" and path not in planfiles
    )
    entries = entries_from_csv(tables, source=SOURCE_NAME, source_list=name)
    for path in planfiles:
        entries += _entries_from_planfile(path, source_list=name)
    entries += entries_from_designation_text(text, source=SOURCE_NAME, source_list=name)
    return as_external_list(entries, paths, source=SOURCE_NAME, source_list=name)


def _is_planfile(path: Path) -> bool:
    if path.suffix.casefold() != ".txt":
        return False
    try:
        with path.open("rb") as handle:
            signature = handle.readline().strip().upper().split(b",", maxsplit=1)
            return len(signature) == 2 and signature[0] == b"APTF" and signature[1].isdigit()
    except OSError as exc:
        raise ValueError(f"cannot read AstroPlanner file {path}: {exc}") from exc


def _entries_from_planfile(
    path: Path, *, source_list: str
) -> tuple[ExternalObservingListEntry, ...]:
    try:
        try:
            lines = path.read_text(encoding="utf-8-sig").splitlines()
        except UnicodeDecodeError:
            lines = path.read_text(encoding="latin-1").splitlines()
    except OSError as exc:
        raise ValueError(f"cannot read AstroPlanner plan {path}: {exc}") from exc

    if "<<Objects>>" not in lines or "<<Elements>>" not in lines:
        raise ValueError(
            f"{path}: malformed AstroPlanner plan; expected Objects and Elements sections"
        )

    in_objects = False
    entries: list[ExternalObservingListEntry] = []
    for line_number, line in enumerate(lines, start=1):
        marker = line.strip()
        if marker == "<<Objects>>":
            in_objects = True
            continue
        if marker == "<<Elements>>":
            break
        if not in_objects:
            continue
        row = line.split("\t")
        if not row or not row[0].strip().isdigit():
            continue

        raw = row[1].strip() if len(row) > 1 else ""
        if not raw and len(row) > 2:
            raw = row[2].strip()
        problem: str | None = None if raw else "missing object designation"
        ra_deg: float | None = None
        dec_deg: float | None = None
        if len(row) > 4:
            try:
                ra_hours = float(row[3])
                dec_deg = float(row[4])
                if not math.isfinite(ra_hours) or not 0.0 <= ra_hours < 24.0:
                    raise ValueError("RA hours must be finite and in [0, 24)")
                if not math.isfinite(dec_deg) or not -90.0 <= dec_deg <= 90.0:
                    raise ValueError("Dec must be finite and in [-90, 90] degrees")
                ra_deg = ra_hours * 15.0
            except ValueError as exc:
                problem = str(exc)
                ra_deg = dec_deg = None
        else:
            problem = "missing coordinate fields"

        type_hint = _type_hint(row[9]) if len(row) > 9 else None
        entries.append(
            ExternalObservingListEntry(
                source=SOURCE_NAME,
                source_list=source_list,
                locator=f"{path.name}:{line_number}",
                imported_file=path.name,
                raw_designation=raw,
                normalized_designation=normalize_external_designation(raw),
                object_type_hint=type_hint,
                ra_deg=ra_deg,
                dec_deg=dec_deg,
                parse_error=problem,
            )
        )
    return tuple(entries)


def _type_hint(value: str) -> str | None:
    key = "".join(character for character in value.casefold() if character.isalnum())
    hints = {
        "galaxy": "galaxy",
        "open": "open cluster",
        "opencl": "open cluster",
        "globular": "globular cluster",
        "pneb": "planetary nebula",
        "dkneb": "dark nebula",
        "brneb": "bright nebula",
        "eneb": "bright nebula",
        "rneb": "reflection nebula",
        "snr": "supernova remnant",
        "galclus": "galaxy group",
        "other": "other",
    }
    if key in hints:
        return hints[key]
    return f"unclassified:{key}" if key else None
