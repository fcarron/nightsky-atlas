"""Repeatable inventory of normalized DSO catalogue records."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from nightsky_atlas.atlas.observing_config import (
    load_observing_lists_config,
    resolve_edition,
)
from nightsky_atlas.catalog.dso_store import load_dso_catalog
from nightsky_atlas.catalog.models import DeepSkyObject
from nightsky_atlas.catalog.observing_lists import (
    build_membership_index,
    load_observing_lists,
)
from nightsky_atlas.catalog.selection import select_dso

_TYPE_NAMES = {
    "galaxy": "galaxy",
    "galaxy_cluster": "galaxy group / cluster",
    "open_cluster": "open cluster",
    "globular_cluster": "globular cluster",
    "planetary_nebula": "planetary nebula",
    "bright_nebula": "bright nebula / H-II",
    "dark_nebula": "dark nebula",
    "supernova_remnant": "SNR",
    "star": "star",
    "double_star": "double star",
    "other": "other",
}


def _tsv_data_rows(path: Path) -> int:
    if not path.is_file():
        return 0
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    header = next((index for index, line in enumerate(lines) if not line.startswith("#")), None)
    if header is None:
        return 0
    count = 0
    for row in csv.reader(lines[header + 1 :], delimiter="\t"):
        if row and not all(not value.strip() or set(value.strip()) <= {"-", "="} for value in row):
            count += 1
    return count


def _csv_data_rows(paths: list[Path]) -> int:
    total = 0
    for path in paths:
        if not path.is_file():
            continue
        with path.open(encoding="utf-8-sig", newline="") as stream:
            total += sum(1 for _ in csv.DictReader(stream))
    return total


def _edition_counts(
    objects: list[DeepSkyObject],
    *,
    observing_config_path: Path,
    observing_lists_dir: Path,
) -> tuple[dict[str, int], dict[str, dict[str, int]]]:
    config = load_observing_lists_config(observing_config_path)
    index = build_membership_index(load_observing_lists(observing_lists_dir), objects)
    per_edition: dict[str, dict[str, int]] = {}
    selected_by_edition: dict[str, set[str]] = {}
    for edition in ("standard", "deep", "reference"):
        policy = resolve_edition(config, edition)
        selected: set[str] = set()
        for obj in objects:
            metadata = select_dso(obj, index=index, policy=policy)
            if metadata.visible or metadata.forced:
                selected.add(obj.id)
        selected_by_edition[edition] = selected
        per_edition[edition] = {"total_unique": len(selected)}

    by_source: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for obj in objects:
        sources = {obj.provenance.catalogue}
        sources.update(record.catalogue_id for record in obj.catalogue_records)
        for source in sources:
            for edition, selected in selected_by_edition.items():
                if obj.id in selected:
                    by_source[source][edition].add(obj.id)
    source_counts = {
        source: {
            edition: len(by_source[source][edition])
            for edition in ("standard", "deep", "reference")
        }
        for source in by_source
    }
    return {edition: len(ids) for edition, ids in selected_by_edition.items()}, source_counts


def build_catalogue_inventory(
    *,
    catalogue_path: str | Path = "data/processed/dso/catalogue.json",
    catalogue_manifest_path: str | Path = "data/processed/dso/catalogue.manifest.json",
    openngc_path: str | Path = "data/processed/dso/openngc.json",
    openngc_manifest_path: str | Path = "data/processed/dso/openngc.manifest.json",
    openngc_raw_dir: str | Path = "data/raw/openngc",
    vizier_raw_dir: str | Path = "data/raw/vizier_dso",
    crossmatch_report_path: str | Path = "data/processed/dso/vizier-crossmatch.json",
    observing_config_path: str | Path = "config/observing_lists.yaml",
    observing_lists_dir: str | Path = "data/fixtures/observing_lists",
) -> dict[str, Any]:
    """Summarize physical objects and source-row outcomes from current artifacts."""
    catalogue_file = Path(catalogue_path)
    objects = load_dso_catalog(catalogue_file)
    catalogue_manifest_file = Path(catalogue_manifest_path)
    catalogue_manifest = (
        json.loads(catalogue_manifest_file.read_text(encoding="utf-8"))
        if catalogue_manifest_file.is_file()
        else {}
    )
    openngc_manifest_file = Path(openngc_manifest_path)
    openngc_manifest = (
        json.loads(openngc_manifest_file.read_text(encoding="utf-8"))
        if openngc_manifest_file.is_file()
        else {}
    )
    source_manifests = {
        str(item.get("catalogue_id")): item for item in catalogue_manifest.get("sources", [])
    }
    raw_manifest_file = Path(vizier_raw_dir) / "manifest.json"
    raw_manifest = (
        json.loads(raw_manifest_file.read_text(encoding="utf-8"))
        if raw_manifest_file.is_file()
        else {}
    )
    raw_entries = {
        str(item.get("catalogue_id")): item for item in raw_manifest.get("catalogues", [])
    }
    crossmatch_file = Path(crossmatch_report_path)
    crossmatch_report = (
        json.loads(crossmatch_file.read_text(encoding="utf-8")) if crossmatch_file.is_file() else {}
    )
    outcomes: dict[str, Counter[str]] = defaultdict(Counter)
    for item in crossmatch_report.get("decisions", []):
        outcomes[str(item.get("catalogue_id"))][str(item.get("status"))] += 1

    source_ids = {obj.provenance.catalogue for obj in objects}
    for obj in objects:
        source_ids.update(record.catalogue_id for record in obj.catalogue_records)
    rows: list[dict[str, Any]] = []
    openngc_objects = load_dso_catalog(openngc_path) if Path(openngc_path).is_file() else []
    openngc_source = str(openngc_manifest.get("catalogue", "OpenNGC"))
    source_ids.add(openngc_source)
    for source in sorted(source_ids, key=lambda value: (value != "OpenNGC", value)):
        records = [
            record
            for obj in objects
            for record in obj.catalogue_records
            if record.catalogue_id == source
        ]
        if source == "OpenNGC":
            raw_meta = {}
            parsed = len(openngc_objects)
            raw_files = [
                Path(openngc_raw_dir) / name for name in openngc_manifest.get("raw_files", [])
            ]
            raw = int(openngc_manifest.get("raw_row_count", _csv_data_rows(raw_files) or parsed))
            new = parsed
            aliases = 0
            uncertain = 0
            unmatched_aliases = 0
            rejected = max(0, raw - parsed)
        else:
            meta = source_manifests.get(source, {})
            raw_meta = raw_entries.get(source, {})
            parsed = outcomes[source].total() or len(records)
            raw_file = Path(vizier_raw_dir) / str(raw_meta.get("raw_file", ""))
            raw = int(
                raw_meta.get(
                    "family_raw_row_count",
                    raw_meta.get(
                        "input_row_count",
                        _tsv_data_rows(raw_file)
                        or meta.get("raw_row_count", meta.get("row_count", parsed)),
                    ),
                )
            )
            new = outcomes[source]["new"]
            aliases = outcomes[source]["matched_alias"]
            uncertain = outcomes[source]["uncertain"] + outcomes[source]["uncertain_alias"]
            unmatched_aliases = outcomes[source]["unmatched_alias"]
            # Older cross-match reports omit rejected counts; quantify the difference.
            rejected = max(0, raw - parsed)
        rows.append(
            {
                "catalogue": source,
                "raw_rows": raw,
                "source_table_rows": int(raw_meta.get("source_table_row_count", raw)),
                "filtered_parent_rows": max(
                    0, int(raw_meta.get("source_table_row_count", raw)) - raw
                ),
                "parsed_rows": parsed,
                "new_physical_objects": new,
                "matched_aliases": aliases,
                "uncertain_matches": uncertain,
                "unmatched_aliases": unmatched_aliases if source != "OpenNGC" else 0,
                "rejected_or_invalid": rejected,
                "eligible": {},
            }
        )

    total_eligible, source_eligibility = _edition_counts(
        objects,
        observing_config_path=Path(observing_config_path),
        observing_lists_dir=Path(observing_lists_dir),
    )
    for row in rows:
        row["eligible"] = source_eligibility.get(
            row["catalogue"], {"standard": 0, "deep": 0, "reference": 0}
        )

    type_counts: Counter[str] = Counter()
    for obj in objects:
        if obj.object_type.value == "bright_nebula":
            subtype = (obj.semantic_subtype or "").casefold()
            if "reflection" in subtype:
                type_name = "reflection nebula"
            elif "hii" in subtype or "bright nebula" in subtype:
                type_name = "bright nebula / H-II"
            else:
                type_name = "bright nebula (unspecified subtype)"
        else:
            type_name = _TYPE_NAMES.get(obj.object_type.value, "other")
        type_counts[type_name] += 1
    type_counts.setdefault("galaxy group / cluster", 0)
    type_counts.setdefault("reflection nebula", 0)
    type_counts.setdefault("bright nebula / H-II", 0)
    type_counts.setdefault("star", 0)
    type_counts.setdefault("double star", 0)
    type_counts.setdefault("other", 0)
    decisions = crossmatch_report.get("decisions", [])
    aliases_by_catalogue: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in decisions:
        if item.get("status") == "matched_alias":
            aliases_by_catalogue[str(item.get("catalogue_id"))].append(
                {
                    "designation": item.get("designation"),
                    "canonical_object": item.get("canonical_id"),
                    "distance_arcmin": item.get("match_distance_arcmin"),
                    "reason": item.get("reason"),
                }
            )
    uncertain_examples = [
        item for item in decisions if str(item.get("status", "")).startswith("uncertain")
    ][:25]
    alias_examples = {
        catalogue: rows[:10] for catalogue, rows in sorted(aliases_by_catalogue.items())
    }
    return {
        "catalogue_file": str(catalogue_file),
        "physical_object_count": len(objects),
        "physical_dso_count": sum(
            obj.object_type.value not in {"star", "double_star"} for obj in objects
        ),
        "source_rows": rows,
        "physical_objects_by_type": dict(sorted(type_counts.items())),
        "unique_eligible_by_edition": total_eligible,
        "alias_examples_by_catalogue": alias_examples,
        "top_uncertain_matches": uncertain_examples,
        "duplicate_prevention_examples": [
            item for rows in alias_examples.values() for item in rows[:2]
        ][:20],
        "notes": [
            (
                "Source eligibility rows may overlap because one physical object can have "
                "several catalogue records."
            ),
            (
                "Raw/parsed counts use archived source manifests; rejected counts are raw "
                "minus represented parsed records."
            ),
        ],
    }
