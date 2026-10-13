"""Pinned UCC catalogue fetch, parsing and conservative DSO cross-matching."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import urllib.request
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from scipy.spatial import cKDTree

from nightsky_atlas.catalog.models import CatalogSourceRecord, DeepSkyObject, DsoType, Provenance
from nightsky_atlas.catalog.observing_lists import canonical_designation

__all__ = [
    "UCC_DATA_URL",
    "UCC_MD5",
    "UCC_VERSION",
    "UccImportResult",
    "crossmatch_ucc_objects",
    "download_ucc",
    "iter_ucc_objects",
    "normalize_ucc_alias",
    "parse_ucc_csv",
]

UCC_VERSION = "260615"
UCC_RECORD_URL = "https://zenodo.org/records/20705026"
UCC_DATA_URL = f"{UCC_RECORD_URL}/files/UCC_cat.csv?download=1"
UCC_README_URL = f"{UCC_RECORD_URL}/files/README.txt?download=1"
UCC_MD5 = "b09c51f12865df0233df8fd90e4a8443"
UCC_README_MD5 = "2b7ee76fb08e7f21976ee03f81ad4b83"
UCC_CATALOGUE_ID = "UCC"
UCC_REFERENCE = "Perren et al. 2023, MNRAS 526, 4107–4119, doi:10.1093/mnras/stad2826"
UCC_COORDINATE_FRAME = "ICRS; release README identifies RA_ICRS and DE_ICRS"
_REQUIRED_COLUMNS = (
    "Name(s)",
    "name",
    "RA_ICRS",
    "DE_ICRS",
    "r_50",
    "N_membs",
    "C3",
    "UTI",
    "P_dup",
    "bad_oc",
)
_ALIAS_SPLIT = re.compile(r"\s*(?:;|,|\|)\s*")
_CLUSTER_ID = re.compile(
    r"^(STOCK|TRUMPLER|TR|HARVARD|H|STEPHENSON|MEL|MELOTTE|CR|COLLINDER)\s*0*(\d+)([A-Z]?)$",
    re.I,
)


@dataclass(frozen=True, slots=True)
class UccImportResult:
    objects: tuple[DeepSkyObject, ...]
    decisions: tuple[dict[str, object], ...]
    summary: dict[str, int]


def normalize_ucc_alias(value: str) -> str:
    """Normalize common cluster designations without discarding catalogue identity."""
    text = re.sub(r"\s+", " ", value.strip()).upper()
    match = _CLUSTER_ID.fullmatch(text)
    if match:
        prefix = match.group(1)
        aliases = {"TR": "TRUMPLER", "MEL": "MELOTTE", "CR": "COLLINDER", "H": "HARVARD"}
        return f"{aliases.get(prefix, prefix)}{int(match.group(2))}{match.group(3)}"
    return canonical_designation(text)


def _names(value: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(part.strip() for part in _ALIAS_SPLIT.split(value) if part.strip()))


def _number(row: dict[str, str], field: str) -> float | None:
    value = row.get(field, "").strip()
    if not value or value.casefold() in {"nan", "na", "null", "--"}:
        return None
    try:
        result = float(value)
    except ValueError as exc:
        raise ValueError(f"invalid UCC {field} value {value!r}") from exc
    return result if math.isfinite(result) else None


def _truth(value: str) -> bool | None:
    normalized = value.strip().casefold()
    if normalized in {"true", "t", "1", "yes", "y"}:
        return True
    if normalized in {"false", "f", "0", "no", "n"}:
        return False
    return None if not normalized else None


def parse_ucc_csv(text: str, *, retrieved: str = "fixture") -> tuple[DeepSkyObject, ...]:
    """Parse release CSV columns documented by that release's README."""
    reader = csv.DictReader(text.splitlines())
    fields = tuple(reader.fieldnames or ())
    missing = sorted(set(_REQUIRED_COLUMNS) - set(fields))
    if missing:
        raise ValueError(f"UCC {UCC_VERSION} CSV missing documented columns: {', '.join(missing)}")
    result: list[DeepSkyObject] = []
    seen_source_ids: set[str] = set()
    for line, raw in enumerate(reader, start=2):
        row = {str(key): (value or "").strip() for key, value in raw.items() if key is not None}
        source_id = row["name"].strip()
        aliases = _names(row["Name(s)"])
        ra, dec = _number(row, "RA_ICRS"), _number(row, "DE_ICRS")
        if not source_id or ra is None or dec is None:
            raise ValueError(f"UCC row {line} has no stable name or valid ICRS coordinates")
        if not 0.0 <= ra < 360.0 or not -90.0 <= dec <= 90.0:
            raise ValueError(f"UCC row {line} has out-of-range ICRS coordinates")
        if source_id in seen_source_ids:
            raise ValueError(f"duplicate UCC main name at row {line}: {source_id}")
        seen_source_ids.add(source_id)
        designation = aliases[0] if aliases else source_id
        raw_fields = tuple(sorted((key, value) for key, value in row.items() if value))
        source = CatalogSourceRecord(
            catalogue_id=UCC_CATALOGUE_ID,
            designation=designation,
            source_url=UCC_RECORD_URL,
            reference=UCC_REFERENCE,
            retrieved=retrieved,
            coordinate_frame=UCC_COORDINATE_FRAME,
            source_ra=row["RA_ICRS"],
            source_dec=row["DE_ICRS"],
            raw_fields=raw_fields,
        )
        # r_50 remains source metadata: it is a half-membership radius, not a
        # visual diameter and therefore is deliberately not mapped to an extent.
        result.append(
            DeepSkyObject(
                id=designation,
                ra_deg=ra,
                dec_deg=dec,
                object_type=DsoType.OPEN_CLUSTER,
                provenance=Provenance(UCC_CATALOGUE_ID, source_id, UCC_VERSION),
                cross_ids=tuple(alias for alias in aliases[1:] if alias != designation),
                semantic_subtype="UCC open-cluster candidate",
                member_count=(
                    int(n)
                    if (n := _number(row, "N_membs")) is not None and n.is_integer()
                    else None
                ),
                catalogue_records=(source,),
            )
        )
    return tuple(result)


def _unit(obj: DeepSkyObject) -> tuple[float, float, float]:
    ra, dec = math.radians(obj.ra_deg), math.radians(obj.dec_deg)
    return math.cos(dec) * math.cos(ra), math.cos(dec) * math.sin(ra), math.sin(dec)


def _distance_arcmin(a: DeepSkyObject, b: DeepSkyObject) -> float:
    ra1, dec1, ra2, dec2 = map(math.radians, (a.ra_deg, a.dec_deg, b.ra_deg, b.dec_deg))
    cosine = math.sin(dec1) * math.sin(dec2) + math.cos(dec1) * math.cos(dec2) * math.cos(ra2 - ra1)
    return math.degrees(math.acos(min(1.0, max(-1.0, cosine)))) * 60.0


def _aliases(obj: DeepSkyObject) -> set[str]:
    return {normalize_ucc_alias(value) for value in (obj.id, *obj.cross_ids) if value.strip()}


def _ucc_source_key(source: CatalogSourceRecord) -> str:
    return dict(source.raw_fields).get("name", source.designation)


def _merge(
    canonical: DeepSkyObject, incoming: DeepSkyObject, distance: float | None, reason: str
) -> DeepSkyObject:
    source_records = tuple(
        replace(
            record,
            crossmatch_decision="matched_alias",
            matched_object_id=canonical.id,
            match_distance_arcmin=distance,
            match_confidence="high",
            match_reason=reason,
        )
        for record in incoming.catalogue_records
    )
    aliases = tuple(dict.fromkeys((*canonical.cross_ids, incoming.id, *incoming.cross_ids)))
    aliases = tuple(alias for alias in aliases if alias != canonical.id)
    known = {(r.catalogue_id, r.designation) for r in canonical.catalogue_records}
    return replace(
        canonical,
        cross_ids=aliases,
        catalogue_records=canonical.catalogue_records
        + tuple(
            record
            for record in source_records
            if (record.catalogue_id, record.designation) not in known
        ),
        member_count=canonical.member_count or incoming.member_count,
    )


def crossmatch_ucc_objects(
    existing: Iterable[DeepSkyObject], incoming: Iterable[DeepSkyObject]
) -> UccImportResult:
    """Merge exact identities; quarantine positional-only and duplicate-risk rows."""
    objects = list(existing)
    index: dict[str, set[int]] = {}
    source_id_index: dict[str, set[int]] = {}

    def index_object(i: int, obj: DeepSkyObject) -> None:
        for alias in _aliases(obj):
            index.setdefault(alias, set()).add(i)

    for i, obj in enumerate(objects):
        index_object(i, obj)
        for source in obj.catalogue_records:
            if source.catalogue_id == UCC_CATALOGUE_ID:
                source_id_index.setdefault(
                    source.catalogue_id + ":" + _ucc_source_key(source), set()
                ).add(i)
    incoming_sorted = sorted(incoming, key=lambda obj: obj.provenance.source_id)
    spatial_indices = [
        i for i, obj in enumerate(objects) if obj.provenance.catalogue != UCC_CATALOGUE_ID
    ]
    tree = cKDTree([_unit(objects[i]) for i in spatial_indices]) if spatial_indices else None
    search_chord = 2 * math.sin(math.radians(1.5) / 2)
    counts = {
        key: 0
        for key in (
            "raw",
            "matched",
            "new",
            "uncertain",
            "rejected_bad_oc",
            "rejected_duplicate_risk",
        )
    }
    decisions: list[dict[str, object]] = []
    for record in incoming_sorted:
        counts["raw"] += 1
        raw = dict(record.catalogue_records[0].raw_fields)
        aliases = _aliases(record)
        exact_all = sorted(
            {i for alias in aliases for i in index.get(alias, ())}
            | source_id_index.get(
                UCC_CATALOGUE_ID + ":" + _ucc_source_key(record.catalogue_records[0]), set()
            )
        )
        exact = [i for i in exact_all if objects[i].object_type == DsoType.OPEN_CLUSTER]
        nearby_local = (
            tree.query_ball_point(_unit(record), search_chord) if tree is not None else []
        )
        nearby = [spatial_indices[i] for i in nearby_local]
        nearby_candidates = []
        for i in nearby:
            candidate = objects[i]
            if candidate.object_type != DsoType.OPEN_CLUSTER:
                continue
            separation = _distance_arcmin(record, candidate)
            # Reuse the established open-cluster search envelope, but never
            # auto-merge from position alone. UCC r_50 is not a chart extent.
            search_radius = max(
                20.0,
                min(90.0, (candidate.major_axis_arcmin or 0.0) * 0.35),
            )
            if separation <= search_radius:
                nearby_candidates.append((separation, i))
        bad_oc = _truth(raw.get("bad_oc", ""))
        p_dup = _number(raw, "P_dup")
        status, reason, canonical_id = "", "", None
        prior_ucc = source_id_index.get(
            UCC_CATALOGUE_ID + ":" + _ucc_source_key(record.catalogue_records[0]), set()
        )
        if len(prior_ucc) == 1:
            i = next(iter(prior_ucc))
            prior = next(
                source
                for source in objects[i].catalogue_records
                if source.catalogue_id == UCC_CATALOGUE_ID
                and _ucc_source_key(source) == _ucc_source_key(record.catalogue_records[0])
            )
            distance = prior.match_distance_arcmin
            canonical_id = prior.matched_object_id or objects[i].id
            reason = prior.match_reason
            if prior.crossmatch_decision == "new":
                status = "new"
                counts["new"] += 1
            else:
                status = "matched"
                counts["matched"] += 1
        elif exact_all and (len(exact_all) != 1 or len(exact) != 1):
            distance = None
            status, reason = "uncertain", "designation_conflicts_with_other_catalogue_identity"
            counts["uncertain"] += 1
        elif len(exact) == 1:
            i = exact[0]
            distance = _distance_arcmin(record, objects[i])
            search_radius = max(
                20.0,
                min(90.0, (objects[i].major_axis_arcmin or 0.0) * 0.35),
            )
            if distance > search_radius:
                status, reason = "uncertain", "explicit_designation_coordinate_disagreement"
                nearby_candidates.append((distance, i))
                counts["uncertain"] += 1
            else:
                objects[i] = _merge(objects[i], record, distance, "exact_normalized_designation")
                index_object(i, objects[i])
                counts["matched"] += 1
                status, reason, canonical_id = (
                    "matched",
                    "exact_normalized_designation",
                    objects[i].id,
                )
        elif len(exact) > 1:
            distance = None
            status, reason = "uncertain", "designation_matches_multiple_existing_objects"
            counts["uncertain"] += 1
        elif bad_oc is True:
            distance = None
            status, reason = "rejected", "ucc_bad_oc_flag"
            counts["rejected_bad_oc"] += 1
        elif p_dup is not None and p_dup >= 0.5:
            distance = None
            status, reason = "uncertain", "ucc_duplicate_probability_at_least_0.5"
            counts["rejected_duplicate_risk"] += 1
        elif nearby_candidates:
            distances = sorted((distance, objects[i].id) for distance, i in nearby_candidates)
            distance = distances[0][0]
            status, reason = "uncertain", "position_only_candidate_requires_identity_review"
            counts["uncertain"] += 1
        else:
            distance = None
            status, reason = "new", "no_existing_open_cluster_alias_or_nearby_candidate"
            updated = replace(
                record,
                catalogue_records=tuple(
                    replace(
                        source,
                        crossmatch_decision="new",
                        matched_object_id=record.id,
                        match_confidence="high",
                        match_reason=reason,
                    )
                    for source in record.catalogue_records
                ),
            )
            objects.append(updated)
            index_object(len(objects) - 1, updated)
            source_id_index.setdefault(
                UCC_CATALOGUE_ID + ":" + _ucc_source_key(record.catalogue_records[0]), set()
            ).add(len(objects) - 1)
            counts["new"] += 1
            canonical_id = record.id
        decisions.append(
            {
                "ucc_id": record.provenance.source_id,
                "designation": record.id,
                "aliases": list(record.cross_ids),
                "status": status,
                "canonical_id": canonical_id,
                "distance_arcmin": distance,
                "bad_oc": bad_oc,
                "UTI": _number(raw, "UTI"),
                "C3": raw.get("C3"),
                "P_dup": p_dup,
                "r_50_arcmin": _number(raw, "r_50"),
                "nearby_candidates": [
                    {"id": objects[i].id, "distance_arcmin": round(distance, 4)}
                    for distance, i in sorted(nearby_candidates)[:10]
                ],
                "reason": reason,
            }
        )
    return UccImportResult(tuple(objects), tuple(decisions), counts)


def download_ucc(destination: str | Path) -> Path:
    """Download and checksum the pinned catalogue and its version README."""
    root = Path(destination)
    root.mkdir(parents=True, exist_ok=True)
    for filename, url, expected in (
        ("README.txt", UCC_README_URL, UCC_README_MD5),
        ("UCC_cat.csv", UCC_DATA_URL, UCC_MD5),
    ):
        target = root / filename
        if target.exists():
            digest = hashlib.md5(target.read_bytes()).hexdigest()
            if digest == expected:
                continue
            raise ValueError(
                f"existing UCC source does not match pinned {filename} checksum: {target}"
            )
        request = urllib.request.Request(
            url, headers={"User-Agent": "NightSkyAtlas catalogue importer"}
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = response.read()
        digest = hashlib.md5(payload).hexdigest()
        if digest != expected:
            raise ValueError(f"UCC {filename} checksum mismatch: expected {expected}, got {digest}")
        target.write_bytes(payload)
    csv_path = root / "UCC_cat.csv"
    manifest_path = root / "manifest.json"
    retrieved = datetime.now(UTC).isoformat(timespec="seconds")
    if manifest_path.is_file():
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (
            previous.get("version") == UCC_VERSION
            and previous.get("files", {}).get("README.txt", {}).get("md5") == UCC_README_MD5
            and previous.get("files", {}).get("UCC_cat.csv", {}).get("md5") == UCC_MD5
        ):
            retrieved = previous.get("retrieved", retrieved)
    manifest = {
        "catalogue": "Unified Cluster Catalogue",
        "version": UCC_VERSION,
        "released": "2026-06-15",
        "record_url": UCC_RECORD_URL,
        "download_url": UCC_DATA_URL,
        "citation": UCC_REFERENCE,
        "data_license": (
            "Not specified in the versioned README or Zenodo record metadata; "
            "redistribution rights unresolved."
        ),
        "redistribution": (
            "Do not redistribute the raw or derived catalogue until the data "
            "licence/terms are clarified."
        ),
        "retrieved": retrieved,
        "files": {
            "README.txt": {
                "md5": UCC_README_MD5,
                "sha256": hashlib.sha256((root / "README.txt").read_bytes()).hexdigest(),
            },
            "UCC_cat.csv": {
                "md5": UCC_MD5,
                "sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
            },
        },
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return csv_path


def iter_ucc_objects(directory: str | Path) -> Iterator[DeepSkyObject]:
    """Read cached UCC data after verifying both release checksums."""
    root = Path(directory)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("version") != UCC_VERSION:
        raise ValueError(f"expected UCC version {UCC_VERSION}, got {manifest.get('version')!r}")
    for filename, expected in (("README.txt", UCC_README_MD5), ("UCC_cat.csv", UCC_MD5)):
        path = root / filename
        if hashlib.md5(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"UCC source checksum mismatch for {path}")
    retrieved = manifest.get("retrieved")
    if not retrieved:
        raise ValueError("UCC source manifest has no retrieval date")
    yield from parse_ucc_csv(
        (root / "UCC_cat.csv").read_text(encoding="utf-8-sig"), retrieved=retrieved
    )
