"""Import OpenNGC level-2 nebula outlines into the atlas outline format."""

from __future__ import annotations

import csv
import json
from pathlib import Path

__all__ = ["import_openngc_outlines"]

CATALOGUE = "OpenNGC"
LICENSE = "CC-BY-SA-4.0"
SOURCE_URL = "https://github.com/mattiaverga/OpenNGC"


def import_openngc_outlines(source: str | Path, destination: str | Path) -> Path:
    """Convert OpenNGC's level-2 tab-separated polygons to atlas JSON.

    Level 2 is OpenNGC's normal DSS2-colour threshold.  Multiple components
    retain individual stable IDs while sharing the astronomical DSO ID.
    """
    source_dir = Path(source)
    object_dir = source_dir / "objects"
    if not object_dir.is_dir():
        raise ValueError(f"OpenNGC outline objects directory not found: {object_dir}")
    entries: list[dict[str, object]] = []
    for path in sorted(object_dir.glob("*_lv2.txt")):
        dso_id = path.name.removesuffix("_lv2.txt")
        parts: list[list[list[float]]] = [[]]
        with path.open(encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream, delimiter="\t"):
                parts[-1].append([float(row["RAJ2000"]), float(row["DEJ2000"])])
                if row["Cont_Flag"] == "*":
                    parts.append([])
        for index, points in enumerate(part for part in parts if len(part) >= 3):
            entries.append(
                {
                    "id": f"outline:openngc:{dso_id}:2:{index}",
                    "dso_id": dso_id,
                    "points": points,
                    "source_id": path.name,
                }
            )
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            {
                "source": {
                    "name": "OpenNGC nebula outlines",
                    "license": LICENSE,
                    "level": 2,
                    "catalogue": CATALOGUE,
                    "source_url": SOURCE_URL,
                },
                "outlines": entries,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return target
