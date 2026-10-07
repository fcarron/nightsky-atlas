"""Adapter for user-supplied Astronomical League tables or plain text lists."""

from __future__ import annotations

from pathlib import Path

from nightsky_atlas.research.observing_lists.models import ExternalObservingList
from nightsky_atlas.research.observing_lists.parser_base import (
    as_external_list,
    entries_from_csv,
    entries_from_designation_text,
)

SOURCE_NAME = "Astronomical League"


def parse(paths: tuple[Path, ...], *, list_name: str | None = None) -> ExternalObservingList:
    """Parse normalized CSV/TSV or one-designation-per-line user input."""
    if not paths:
        raise ValueError("no Astronomical League input files found")
    unsupported = [path for path in paths if path.suffix.casefold() not in {".csv", ".tsv", ".txt"}]
    if unsupported:
        names = ", ".join(path.name for path in unsupported)
        raise ValueError(
            f"unsupported AL file(s): {names}; use CSV/TSV or one designation per .txt line"
        )
    name = list_name or (paths[0].parent.name if len(paths) > 1 else paths[0].stem)
    tables = tuple(path for path in paths if path.suffix.casefold() in {".csv", ".tsv"})
    text = tuple(path for path in paths if path.suffix.casefold() == ".txt")
    entries = entries_from_csv(tables, source=SOURCE_NAME, source_list=name)
    entries += entries_from_designation_text(text, source=SOURCE_NAME, source_list=name)
    return as_external_list(entries, paths, source=SOURCE_NAME, source_list=name)
