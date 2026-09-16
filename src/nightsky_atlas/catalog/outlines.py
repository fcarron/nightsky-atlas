"""Large-object outline geometry.

Some deep-sky objects (the Veil Nebula, the North America Nebula and similar
extended nebulae) are far too irregular to be represented by an ellipse.  Their
outlines are schematic closed RA/Dec polygons, authored for this project and
loaded from a small fixture directory.  Source and provenance are documented in
``data/fixtures/outlines/SOURCE.md``.

Like constellation geometry this is observing furniture: it carries no
catalogue identity of its own beyond the deep-sky object it belongs to, and it
is normalized to plain RA/Dec vertices before projection.  Coordinate fields are
``[ra_deg, dec_deg]`` with RA increasing eastward.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nightsky_atlas.catalog.models import Provenance

__all__ = [
    "CATALOGUE",
    "VERSION",
    "DEFAULT_FIXTURE_DIR",
    "FILENAME",
    "NebulaOutline",
    "load_outlines",
]

CATALOGUE = "nightsky-atlas-authored"
VERSION = "1"
DEFAULT_FIXTURE_DIR = Path("data/fixtures/outlines")
FILENAME = "nebulae.json"


@dataclass(frozen=True, slots=True)
class NebulaOutline:
    """A closed schematic RA/Dec polygon for one extended object.

    ``points`` are the polygon vertices in order; the ring is implicitly closed
    (the first vertex is not repeated).  ``id`` is the stable outline ID used by
    diffs, tests and overrides, derived from the deep-sky object it belongs to
    (``outline:dso:NGC7000``).
    """

    id: str
    dso_id: str
    points: tuple[tuple[float, float], ...]
    provenance: Provenance
    name: str | None = None

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("outline id must not be blank")
        if not self.dso_id.strip():
            raise ValueError("outline dso_id must not be blank")
        if not isinstance(self.provenance, Provenance):
            raise ValueError("provenance must be a Provenance instance")
        if len(self.points) < 3:
            raise ValueError("an outline needs at least three vertices")
        for ra_deg, dec_deg in self.points:
            if not math.isfinite(ra_deg) or not math.isfinite(dec_deg):
                raise ValueError("outline coordinates must be finite")
            if not -90.0 <= dec_deg <= 90.0:
                raise ValueError(f"declination must be within [-90, 90], got {dec_deg!r}")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid outline JSON {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"outline JSON root must be an object: {path}")
    return data


def _vertices(raw: Any, source: str) -> tuple[tuple[float, float], ...]:
    if not isinstance(raw, list):
        raise ValueError(f"outline points must be a list in {source}")
    points: list[tuple[float, float]] = []
    for point in raw:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            raise ValueError(f"malformed outline coordinate in {source}: {point!r}")
        ra_deg = float(point[0])
        dec_deg = float(point[1])
        if not math.isfinite(ra_deg) or not math.isfinite(dec_deg):
            raise ValueError(f"non-finite outline coordinate in {source}: {point!r}")
        points.append((ra_deg, dec_deg))
    return tuple(points)


def load_outlines(
    directory: str | Path = DEFAULT_FIXTURE_DIR,
) -> tuple[NebulaOutline, ...]:
    """Load the vendored schematic outline fixture directory."""
    path = Path(directory) / FILENAME
    if not path.exists():
        return ()
    data = _load_json(path)
    provenance = Provenance(catalogue=CATALOGUE, version=VERSION, source_id=FILENAME)
    outlines: list[NebulaOutline] = []
    for entry in data.get("outlines", ()):
        if not isinstance(entry, dict):
            raise ValueError(f"malformed outline entry in {path}: {entry!r}")
        dso_id = str(entry.get("dso_id", "")).strip()
        if not dso_id:
            raise ValueError(f"outline entry without dso_id in {path}")
        name = entry.get("name")
        outlines.append(
            NebulaOutline(
                id=f"outline:dso:{dso_id}",
                dso_id=dso_id,
                points=_vertices(entry.get("points"), path.name),
                provenance=provenance,
                name=str(name) if name is not None else None,
            )
        )
    return tuple(outlines)
