"""Explicit, source-audited common names for normalized physical DSOs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from nightsky_atlas.catalog.models import DeepSkyObject
from nightsky_atlas.catalog.observing_lists import canonical_designation

DEFAULT_COMMON_NAMES_PATH = Path("data/fixtures/dso_common_names.json")


@dataclass(frozen=True, slots=True)
class CuratedCommonName:
    object_id: str
    name: str
    pocket_label: bool
    label_mode: str
    show_in_all_editions: bool
    sources: tuple[str, ...]


@lru_cache(maxsize=4)
def load_curated_common_names(
    path: str | Path = DEFAULT_COMMON_NAMES_PATH,
) -> dict[str, CuratedCommonName]:
    """Load a deterministic mapping keyed by normalized physical-object ID."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    sources = data["sources"]
    if not isinstance(sources, dict) or not sources:
        raise ValueError("curated common names require source provenance")
    result: dict[str, CuratedCommonName] = {}
    names: set[str] = set()
    for row in data["objects"]:
        object_id = canonical_designation(row["id"])
        name = row["name"].strip()
        label_mode = row.get("label_mode", "designation_and_name")
        evidence = tuple(row["sources"])
        if (
            not object_id
            or not name
            or len(set(evidence)) < 2
            or label_mode not in {"designation_and_name", "name_only"}
        ):
            raise ValueError(f"incomplete common-name entry: {row!r}")
        if any(source not in sources for source in evidence):
            raise ValueError(f"unknown common-name source for {object_id}")
        if object_id in result or name.casefold() in names:
            raise ValueError(f"duplicate curated DSO identity or name: {object_id}")
        names.add(name.casefold())
        result[object_id] = CuratedCommonName(
            object_id=object_id,
            name=name,
            pocket_label=bool(row.get("pocket_label", False)),
            label_mode=label_mode,
            show_in_all_editions=bool(row.get("show_in_all_editions", False)),
            sources=evidence,
        )
    return result


def curated_common_name(dso: DeepSkyObject) -> CuratedCommonName | None:
    """Return the curated name of this physical object, if one exists."""
    return load_curated_common_names().get(canonical_designation(dso.id))
