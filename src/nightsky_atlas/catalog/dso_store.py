"""Processed deep-sky catalogue storage.

OpenNGC contains on the order of ten thousand objects, so a compact JSON file
loaded into memory is the simplest adequate storage (``AGENTS.md`` section 9).
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from nightsky_atlas.catalog.models import DeepSkyObject

__all__ = ["load_dso_catalog", "write_dso_catalog"]


def write_dso_catalog(path: str | Path, objects: Iterable[DeepSkyObject]) -> int:
    """Write objects as compact, deterministic JSON and return the count."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = [obj.to_dict() for obj in objects]
    target.write_text(
        json.dumps(payload, separators=(",", ":"), sort_keys=True),
        encoding="utf-8",
    )
    return len(payload)


def load_dso_catalog(path: str | Path) -> list[DeepSkyObject]:
    """Load a processed deep-sky catalogue from JSON."""
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"deep-sky catalogue not found: {target}")
    payload = json.loads(target.read_text(encoding="utf-8"))
    return [DeepSkyObject.from_dict(item) for item in payload]