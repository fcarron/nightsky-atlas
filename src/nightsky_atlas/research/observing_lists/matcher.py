"""Deterministic external designation and coordinate matching."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from nightsky_atlas.astronomy.angles import angular_separation_deg
from nightsky_atlas.catalog.models import DeepSkyObject, DsoType
from nightsky_atlas.catalog.observing_lists import canonical_designation
from nightsky_atlas.research.observing_lists.models import (
    CoverageMatch,
    ExternalObservingListEntry,
)
from nightsky_atlas.research.observing_lists.parser_base import normalize_external_designation

DEFAULT_COORDINATE_TOLERANCE_ARCMIN = 2.0


@dataclass(frozen=True, slots=True)
class ManualMatchOverride:
    source: str
    raw_designation: str
    canonical_object: str
    reason: str


def match_entries(
    entries: Iterable[ExternalObservingListEntry],
    objects: Iterable[DeepSkyObject],
    *,
    coordinate_tolerance_arcmin: float = DEFAULT_COORDINATE_TOLERANCE_ARCMIN,
    overrides: Iterable[ManualMatchOverride] = (),
) -> tuple[CoverageMatch, ...]:
    """Match parsed entries without fuzzy designation guessing.

    Canonical IDs are resolved before aliases. Coordinate matches are used only
    when no name candidate exists; multiple plausible targets remain ambiguous.
    """
    if coordinate_tolerance_arcmin <= 0:
        raise ValueError("coordinate tolerance must be positive")
    object_list = tuple(sorted(objects, key=lambda obj: obj.id))
    by_id = {obj.id: obj for obj in object_list}
    canonical_index: dict[str, set[str]] = defaultdict(set)
    direct_index: dict[str, set[str]] = defaultdict(set)
    alias_index: dict[str, set[str]] = defaultdict(set)
    enhanced_index: dict[str, set[str]] = defaultdict(set)
    for obj in object_list:
        canonical_index[canonical_designation(obj.id)].add(obj.id)
        direct_index[_direct_designation(obj.id)].add(obj.id)
        all_aliases = (*obj.cross_ids, *(record.designation for record in obj.catalogue_records))
        for alias in all_aliases:
            alias_index[canonical_designation(alias)].add(obj.id)
        enhanced_index[normalize_external_designation(obj.id)].add(obj.id)
        for alias in all_aliases:
            enhanced_index[normalize_external_designation(alias)].add(obj.id)

    override_index: dict[tuple[str, str], ManualMatchOverride] = {}
    for override in overrides:
        key = (override.source.casefold(), normalize_external_designation(override.raw_designation))
        if key in override_index:
            raise ValueError(
                f"duplicate manual override for {override.source}: {override.raw_designation}"
            )
        if override.canonical_object not in by_id:
            raise ValueError(
                f"manual override target {override.canonical_object!r} is not a canonical DSO ID"
            )
        override_index[key] = override

    results: list[CoverageMatch] = []
    for entry in entries:
        if entry.parse_error:
            results.append(
                CoverageMatch(
                    entry,
                    "parse_failure",
                    0.0,
                    ambiguity_status="parse_failure",
                    note=entry.parse_error,
                )
            )
            continue
        external_key = entry.normalized_designation or normalize_external_designation(
            entry.raw_designation
        )
        override = override_index.get((entry.source.casefold(), external_key))
        if override is not None:
            obj = by_id[override.canonical_object]
            results.append(
                CoverageMatch(
                    entry,
                    "manual_override",
                    1.0,
                    obj,
                    (obj.id,),
                    ambiguity_status="resolved_by_override",
                    note=override.reason,
                )
            )
            continue

        direct_key = _direct_designation(entry.raw_designation)
        exact_ids = direct_index.get(direct_key, set())
        if exact_ids:
            results.append(_from_candidates(entry, exact_ids, by_id, "canonical_exact", 1.0))
            continue

        alias_ids = alias_index.get(canonical_designation(entry.raw_designation), set())
        if alias_ids:
            results.append(_from_candidates(entry, alias_ids, by_id, "alias_exact", 0.98))
            continue

        normalized_ids = enhanced_index.get(external_key, set())
        if normalized_ids:
            canonical_id_set = canonical_index.get(external_key, set())
            prefixes_match = all(
                _designation_prefix(entry.raw_designation)
                == _designation_prefix(by_id[object_id].id)
                for object_id in normalized_ids
            )
            if not prefixes_match:
                method = "alias_exact"
            elif normalized_ids & canonical_id_set:
                method = "canonical_exact"
            else:
                method = "catalogue_normalized"
            results.append(
                _from_candidates(
                    entry,
                    normalized_ids,
                    by_id,
                    method,
                    1.0 if method == "canonical_exact" else 0.95,
                )
            )
            continue

        if entry.ra_deg is not None and entry.dec_deg is not None:
            nearby: list[tuple[str, float]] = []
            for obj in object_list:
                if not _type_compatible(entry.object_type_hint, obj.object_type):
                    continue
                separation = angular_separation_deg(
                    entry.ra_deg, entry.dec_deg, obj.ra_deg, obj.dec_deg
                )
                distance = separation * 60.0
                if distance <= coordinate_tolerance_arcmin:
                    nearby.append((obj.id, distance))
            nearby.sort(key=lambda item: (item[1], item[0]))
            if len(nearby) == 1:
                object_id, distance = nearby[0]
                results.append(
                    CoverageMatch(
                        entry,
                        "coordinate_exactish",
                        max(0.5, 0.9 * (1.0 - distance / coordinate_tolerance_arcmin)),
                        by_id[object_id],
                        (object_id,),
                        distance,
                        "unique_coordinate_candidate",
                    )
                )
            elif nearby:
                results.append(
                    CoverageMatch(
                        entry,
                        "coordinate_ambiguous",
                        0.0,
                        None,
                        tuple(item[0] for item in nearby),
                        nearby[0][1],
                        "multiple_coordinate_candidates",
                    )
                )
            else:
                results.append(
                    CoverageMatch(
                        entry,
                        "unresolved",
                        0.0,
                        None,
                        ambiguity_status="no_coordinate_candidate",
                        note="coordinates supplied; no compatible database object within tolerance",
                    )
                )
        else:
            results.append(
                CoverageMatch(
                    entry,
                    "unresolved",
                    0.0,
                    None,
                    ambiguity_status="unknown_designation",
                    note="no exact designation or coordinate match",
                )
            )
    return tuple(results)


def _from_candidates(
    entry: ExternalObservingListEntry,
    candidate_ids: set[str],
    objects: Mapping[str, DeepSkyObject],
    method: str,
    confidence: float,
) -> CoverageMatch:
    ordered = tuple(sorted(candidate_ids))
    if len(ordered) != 1:
        return CoverageMatch(
            entry,
            "unresolved",
            0.0,
            None,
            ordered,
            ambiguity_status="ambiguous_designation",
            note="designation maps to more than one physical object",
        )
    return CoverageMatch(entry, method, confidence, objects[ordered[0]], ordered)


def _type_compatible(hint: str | None, object_type: DsoType) -> bool:
    if not hint:
        return True
    value = re.sub(r"[^a-z0-9]", "", hint.casefold())
    expected = {
        DsoType.GALAXY: {"gx", "galaxy", "gal"},
        DsoType.GALAXY_CLUSTER: {
            "galaxycluster",
            "galaxyclustergroup",
            "group",
            "clusterofgalaxies",
            "hcg",
        },
        DsoType.OPEN_CLUSTER: {"oc", "opencluster", "cluster"},
        DsoType.GLOBULAR_CLUSTER: {"gc", "globularcluster"},
        DsoType.PLANETARY_NEBULA: {"pn", "planetarynebula", "planetary"},
        DsoType.BRIGHT_NEBULA: {
            "bn",
            "brightnebula",
            "en",
            "emissionnebula",
            "hii",
            "rn",
            "reflectionnebula",
        },
        DsoType.DARK_NEBULA: {"dn", "darknebula"},
        DsoType.SUPERNOVA_REMNANT: {"snr", "supernovaremnant"},
        DsoType.OTHER: {"other"},
    }
    return value in expected.get(object_type, set())


def _direct_designation(value: str) -> str:
    """Normalize formatting while retaining a catalogue's actual prefix."""
    return re.sub(r"[\s./-]+", "", value).upper()


def _designation_prefix(value: str) -> str:
    compact = re.sub(r"[^A-Z]", "", value.upper())
    match = re.match(r"[A-Z]+", compact)
    return match.group(0) if match else ""
