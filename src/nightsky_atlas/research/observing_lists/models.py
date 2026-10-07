"""Source-neutral data models for external observing-list audits."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from nightsky_atlas.catalog.models import DeepSkyObject


@dataclass(frozen=True, slots=True)
class ExternalObservingListEntry:
    """One sanitized target row from a user-supplied list."""

    source: str
    source_list: str
    locator: str
    imported_file: str
    raw_designation: str
    normalized_designation: str
    object_type_hint: str | None = None
    constellation_hint: str | None = None
    ra_deg: float | None = None
    dec_deg: float | None = None
    size_arcmin: float | None = None
    parse_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ExternalObservingList:
    """Parsed external list content kept in memory for the current audit."""

    source: str
    source_list: str
    imported_files: tuple[str, ...]
    entries: tuple[ExternalObservingListEntry, ...]

    def metadata(self) -> dict[str, Any]:
        designations = {
            entry.normalized_designation for entry in self.entries if entry.normalized_designation
        }
        raw_designations = {
            entry.raw_designation for entry in self.entries if entry.raw_designation
        }
        return {
            "source": self.source,
            "source_list": self.source_list,
            "imported_files": list(self.imported_files),
            "raw_rows": len(self.entries),
            "unique_raw_designations": len(raw_designations),
            "unique_external_designations": len(designations),
        }


@dataclass(frozen=True, slots=True)
class CoverageMatch:
    """A match decision for one external row."""

    entry: ExternalObservingListEntry
    match_method: str
    confidence: float
    matched_object: DeepSkyObject | None = field(default=None, repr=False, compare=False)
    candidate_ids: tuple[str, ...] = ()
    separation_arcmin: float | None = None
    ambiguity_status: str = "none"
    note: str | None = None

    @property
    def matched_object_id(self) -> str | None:
        return self.matched_object.id if self.matched_object is not None else None

    def to_dict(self, *, include_raw_designation: bool = True) -> dict[str, Any]:
        payload = self.entry.to_dict()
        if not include_raw_designation:
            payload.pop("raw_designation", None)
        obj = self.matched_object
        payload.update(
            {
                "match_method": self.match_method,
                "match_confidence": self.confidence,
                "matched_physical_object_id": self.matched_object_id,
                "matched_canonical_designation": obj.id if obj is not None else None,
                "candidate_count": len(self.candidate_ids),
                "candidate_ids": list(self.candidate_ids),
                "ambiguity_status": self.ambiguity_status,
                "separation_arcmin": self.separation_arcmin,
                "match_note": self.note,
                "object_type": obj.object_type.value if obj is not None else None,
                "catalogue_sources": _object_sources(obj) if obj is not None else [],
            }
        )
        return payload


@dataclass(frozen=True, slots=True)
class CoverageReport:
    """Deterministic, sanitized audit output."""

    metadata: dict[str, Any]
    summary: dict[str, Any]
    matches: tuple[CoverageMatch, ...]
    targets: tuple[dict[str, Any], ...]
    type_coverage: dict[str, Any]
    source_catalogue_coverage: dict[str, Any]
    nebula_source_analysis: dict[str, Any]
    manual_review_queue: tuple[dict[str, Any], ...]
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "metadata": self.metadata,
            "summary": self.summary,
            "targets": list(self.targets),
            "entries": [match.to_dict() for match in self.matches],
            "type_coverage": self.type_coverage,
            "source_catalogue_coverage": self.source_catalogue_coverage,
            "nebula_source_analysis": self.nebula_source_analysis,
            "manual_review_queue": list(self.manual_review_queue),
        }


def _object_sources(obj: DeepSkyObject) -> list[str]:
    return sorted(
        {obj.provenance.catalogue, *(record.catalogue_id for record in obj.catalogue_records)}
    )
