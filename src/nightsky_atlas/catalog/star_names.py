"""Star names and designations used for star labels.

Labels for bright stars need human-readable designations, not catalogue
numbers.  This module loads a small vendored fixture derived from d3-celestial
(BSD-3-Clause, see ``data/fixtures/starnames/SOURCE.md``), keyed by Hipparcos
number.  The display text follows ``AGENTS.md`` section 14.3: common name first,
then Bayer, then Flamsteed, then variable-star designation.

Names are presentation state, not astronomical facts (``AGENTS.md`` section 5),
so they live in a lookup here rather than on the immutable :class:`Star`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = ["CATALOGUE", "VERSION", "DEFAULT_FIXTURE_DIR", "FILENAME", "StarName", "load_star_names"]

CATALOGUE = "d3-celestial"
VERSION = "master"
DEFAULT_FIXTURE_DIR = Path("data/fixtures/starnames")
FILENAME = "starnames.json"


@dataclass(frozen=True, slots=True)
class StarName:
    """Named/designated identity of a Hipparcos star."""

    hip_number: int
    name: str | None = None
    bayer: str | None = None
    flamsteed: str | None = None
    variable: str | None = None
    constellation: str | None = None

    def display_text(self) -> str | None:
        """Return the best available label, or ``None`` when undesignated."""
        if self.name:
            return self.name
        if self.constellation:
            for designation in (self.bayer, self.flamsteed, self.variable):
                if designation:
                    return f"{designation} {self.constellation}"
        return self.bayer or self.flamsteed or self.variable or None


def hip_number(hip_id: str | None) -> int | None:
    """Parse ``"HIP 102098"`` into its numeric Hipparcos number."""
    if not hip_id:
        return None
    parts = hip_id.replace("\u2009", " ").split()
    for part in reversed(parts):
        if part.isdigit():
            return int(part)
    return None


def load_star_names(
    directory: str | Path = DEFAULT_FIXTURE_DIR,
) -> dict[int, StarName]:
    """Load the vendored star-name fixture as a Hipparcos-number lookup."""
    path = Path(directory) / FILENAME
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid star name JSON {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"star name JSON root must be an object: {path}")

    names: dict[int, StarName] = {}
    for key, entry in data.items():
        if not isinstance(entry, dict):
            raise ValueError(f"malformed star name entry for {key!r} in {path}")
        number = _parse_key(key, path)
        names[number] = StarName(
            hip_number=number,
            name=_optional_str(entry.get("name")),
            bayer=_optional_str(entry.get("bayer")),
            flamsteed=_optional_str(entry.get("flam")),
            variable=_optional_str(entry.get("var")),
            constellation=_optional_str(entry.get("c")),
        )
    return names


def _parse_key(key: Any, path: Path) -> int:
    try:
        return int(str(key))
    except ValueError as exc:
        raise ValueError(f"non-numeric Hipparcos key {key!r} in {path}") from exc


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
