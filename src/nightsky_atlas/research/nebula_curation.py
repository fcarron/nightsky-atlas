"""Validation helpers for NightSkyAtlas-owned nebula curation files."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

_FORBIDDEN_FIELDS = frozenset(
    {"nsog_rating", "rating", "description", "observing_notes", "al_text"}
)
_STATUSES = frozenset({"include", "review", "exclude"})
_RELATIONSHIPS = frozenset(
    {
        "EXACT_ALIAS",
        "SAME_VISUAL_TARGET",
        "OVERLAPPING_REGION",
        "SUBCOMPONENT",
        "SUBCOMPONENT_OF",
        "CONTAINS",
        "CATALOG_CROSS_ID",
        "NEARBY_ONLY",
        "DISTINCT",
        "REVIEW",
        "AMBIGUOUS",
    }
)


def merge_candidate_sources(*sources: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Union candidates by stable physical object ID, never by cross-ID alone."""
    merged: dict[str, dict[str, Any]] = {}
    for source in sources:
        for candidate in source:
            object_id = str(candidate.get("object_id", "")).strip()
            if not object_id:
                raise ValueError("candidate is missing a stable object_id")
            current = merged.get(object_id)
            if current is None:
                current = dict(candidate)
                current["evidence"] = sorted(set(candidate.get("evidence", ())))
                merged[object_id] = current
                continue
            current["evidence"] = sorted(
                set(current.get("evidence", ())) | set(candidate.get("evidence", ()))
            )
            if current.get("status") == "review" and candidate.get("status") == "include":
                current["status"] = "include"
    return [merged[key] for key in sorted(merged)]


def preferred_dark_designation(
    ldn_designation: str,
    barnard_designation: str | None,
    relationship: str,
) -> str:
    """Prefer Barnard only when curation establishes the same visual target."""
    if relationship not in _RELATIONSHIPS:
        raise ValueError(f"unknown dark-nebula relationship {relationship!r}")
    if relationship == "SAME_VISUAL_TARGET" and barnard_designation:
        return barnard_designation
    return ldn_designation


def southern_counts(entries: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """Count listed objects by hemisphere and the useful south-of-30° band."""
    rows = [entry for entry in entries if entry.get("status") == "include"]
    decs = [float(entry["dec_deg"]) for entry in rows if entry.get("dec_deg") is not None]
    return {
        "included_with_position": len(decs),
        "northern_or_equatorial": sum(dec >= 0 for dec in decs),
        "southern": sum(dec < 0 for dec in decs),
        "south_of_minus_30": sum(dec < -30 for dec in decs),
        "missing_position": len(rows) - len(decs),
    }


def validate_curated_document(data: Mapping[str, Any], *, expected_kind: str) -> None:
    """Validate the minimal, NightSkyAtlas-owned curation document shape."""
    if data.get("schema_version") != 1:
        raise ValueError("curation document schema_version must be 1")
    if data.get("kind") != expected_kind:
        raise ValueError(f"curation kind must be {expected_kind!r}")
    entries = data.get("entries")
    if not isinstance(entries, list):
        raise ValueError("curation entries must be a list")
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise ValueError("each curation entry must be a mapping")
        leaked = _FORBIDDEN_FIELDS & _all_keys(entry)
        if leaked:
            raise ValueError(f"third-party research fields are forbidden: {sorted(leaked)}")
        entry_id = str(entry.get("id", "")).strip()
        if not entry_id:
            raise ValueError("curation entry is missing id")
        if entry_id in seen:
            raise ValueError(f"duplicate curation entry id {entry_id!r}")
        seen.add(entry_id)
        if entry.get("status") not in _STATUSES:
            raise ValueError(f"invalid status for curation entry {entry_id!r}")
        object_ids = entry.get("object_ids", [])
        if not isinstance(object_ids, list) or any(not str(value).strip() for value in object_ids):
            raise ValueError(f"object_ids must be a list of stable IDs for {entry_id!r}")
        if entry.get("status") == "include" and not object_ids:
            raise ValueError(f"included target {entry_id!r} has no resolved object IDs")


def _all_keys(value: Any) -> set[str]:
    if isinstance(value, Mapping):
        return {str(key).casefold() for key in value} | set().union(
            *(_all_keys(item) for item in value.values())
        )
    if isinstance(value, list):
        return set().union(*(_all_keys(item) for item in value))
    return set()
