"""Loader for small committed sample star catalogues.

This is intentionally **not** a Tycho importer.  It reads a tiny CSV fixture
sufficient for one development field so the scene builder and renderer can be
tested deterministically without large external data (``AGENTS.md`` section
36).  Full catalogue import arrives in M4.
"""

from __future__ import annotations

import csv
from pathlib import Path

from nightsky_atlas.catalog.models import Provenance, Star

__all__ = ["SAMPLE_STAR_FIELDS", "StarCatalogueError", "load_sample_stars"]

SAMPLE_STAR_FIELDS = ("id", "ra_deg", "dec_deg", "magnitude", "catalogue", "source_id")


class StarCatalogueError(ValueError):
    """Raised when a sample star catalogue cannot be read."""


def load_sample_stars(path: str | Path) -> list[Star]:
    """Load normalized stars from a small CSV fixture.

    The file must contain at least the columns in :data:`SAMPLE_STAR_FIELDS`.
    Coordinates are degrees and the magnitude is the documented display
    magnitude.  Malformed files fail loudly rather than being silently skipped.
    """
    path = Path(path)
    if not path.exists():
        raise StarCatalogueError(f"star catalogue not found: {path}")

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise StarCatalogueError(f"missing CSV header: {path}")
        missing = [field for field in SAMPLE_STAR_FIELDS if field not in reader.fieldnames]
        if missing:
            raise StarCatalogueError(f"missing columns {missing} in {path}")

        stars: list[Star] = []
        for line_number, row in enumerate(reader, start=2):
            try:
                stars.append(
                    Star(
                        id=row["id"],
                        ra_deg=float(row["ra_deg"]),
                        dec_deg=float(row["dec_deg"]),
                        magnitude=float(row["magnitude"]),
                        provenance=Provenance(
                            catalogue=row["catalogue"],
                            source_id=row["source_id"],
                        ),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise StarCatalogueError(f"{path}:{line_number}: {exc}") from exc

    if not stars:
        raise StarCatalogueError(f"no stars found in {path}")
    return stars