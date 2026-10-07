"""Coverage aggregation using the production DSO selector."""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml

from nightsky_atlas.atlas.config import load_atlas_config
from nightsky_atlas.atlas.observing_config import (
    load_observing_lists_config,
    resolve_edition_hierarchy,
)
from nightsky_atlas.catalog.dso_store import load_dso_catalog
from nightsky_atlas.catalog.models import DeepSkyObject, DsoType
from nightsky_atlas.catalog.observing_lists import build_membership_index, load_observing_lists
from nightsky_atlas.catalog.selection_analysis import explain_selection
from nightsky_atlas.research.observing_lists.matcher import (
    ManualMatchOverride,
    match_entries,
)
from nightsky_atlas.research.observing_lists.models import (
    CoverageMatch,
    CoverageReport,
    ExternalObservingList,
)
from nightsky_atlas.research.observing_lists.sources import (
    astronomical_league,
    astroplanner,
)

_SOURCES = {
    "astroplanner": astroplanner.parse,
    "astronomical-league": astronomical_league.parse,
    "al": astronomical_league.parse,
}
_NON_DSO = {DsoType.STAR, DsoType.DOUBLE_STAR}
_EDITION_IDS = ("pocket", "standard", "deep", "reference")
_CATALOGUE_FAMILIES = {
    "OpenNGC": "OpenNGC / NGC / IC",
    "VII/7A": "LDN",
    "VII/9": "LBN",
    "VII/20": "Sharpless",
    "VII/21": "vdB",
    "VII/220A": "Barnard",
    "IV/24": "Abell PN",
    "VII/202:Palomar": "Palomar",
    "VII/202:Terzan": "Terzan",
    "VII/213": "HCG",
}


def discover_input_files(path: str | Path) -> tuple[Path, ...]:
    """Expand a file or directory into supported local research files."""
    root = Path(path).expanduser()
    if not root.exists():
        raise FileNotFoundError(f"observing-list input does not exist: {root}")
    if root.is_file():
        return (root,)
    files = tuple(
        item
        for item in sorted(root.rglob("*"))
        if item.is_file() and item.suffix.casefold() in {".csv", ".tsv", ".txt"}
    )
    if not files:
        raise ValueError(f"no supported CSV/TSV/TXT observing-list files found under {root}")
    return files


def load_external_list(
    *,
    source: str,
    input_path: str | Path | tuple[Path, ...],
    list_name: str | None = None,
) -> ExternalObservingList:
    """Parse a local source file/directory without retaining arbitrary columns."""
    key = source.casefold()
    parser = _SOURCES.get(key)
    if parser is None:
        raise ValueError(f"unknown source {source!r}; choose astroplanner or astronomical-league")
    if isinstance(input_path, tuple):
        paths = tuple(path for item in input_path for path in discover_input_files(item))
    else:
        paths = discover_input_files(input_path)
    return parser(paths, list_name=list_name)


def load_manual_overrides(path: str | Path | None) -> tuple[ManualMatchOverride, ...]:
    if path is None:
        return ()
    target = Path(path).expanduser()
    if not target.exists():
        raise FileNotFoundError(f"manual override file not found: {target}")
    try:
        document = yaml.safe_load(target.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid manual override YAML {target}: {exc}") from exc
    if not isinstance(document, dict) or not isinstance(document.get("overrides"), list):
        raise ValueError(f"{target}: expected YAML mapping with an 'overrides' list")
    result: list[ManualMatchOverride] = []
    for index, item in enumerate(document["overrides"], start=1):
        if not isinstance(item, dict):
            raise ValueError(f"{target}: override {index} must be a mapping")
        required = ("source", "raw_designation", "canonical_object", "reason")
        missing = [name for name in required if not str(item.get(name, "")).strip()]
        if missing:
            raise ValueError(f"{target}: override {index} missing {', '.join(missing)}")
        result.append(ManualMatchOverride(**{name: str(item[name]).strip() for name in required}))
    return tuple(result)


def build_coverage_report(
    external_list: ExternalObservingList,
    *,
    catalogue_path: str | Path = "data/processed/dso/catalogue.json",
    observing_config_path: str | Path = "config/observing_lists.yaml",
    observing_lists_dir: str | Path = "data/fixtures/observing_lists",
    pocket_atlas_path: str | Path = "atlas/pocket.yaml",
    coordinate_tolerance_arcmin: float = 2.0,
    overrides: tuple[ManualMatchOverride, ...] = (),
) -> CoverageReport:
    """Build an external coverage audit without changing production inputs."""
    all_objects = load_dso_catalog(catalogue_path)
    objects = tuple(obj for obj in all_objects if obj.object_type not in _NON_DSO)
    matches = match_entries(
        external_list.entries,
        objects,
        coordinate_tolerance_arcmin=coordinate_tolerance_arcmin,
        overrides=overrides,
    )
    config = load_observing_lists_config(observing_config_path)
    memberships = build_membership_index(load_observing_lists(observing_lists_dir), objects)
    visibility_by_edition = {
        "pocket": load_atlas_config(pocket_atlas_path).visibility.to_limits(),
        "standard": load_atlas_config("atlas/standard.yaml").visibility.to_limits(),
        "deep": load_atlas_config("atlas/deep.yaml").visibility.to_limits(),
    }
    policies = {
        edition: resolve_edition_hierarchy(
            config, edition, visibility_by_edition=visibility_by_edition
        )
        if edition in visibility_by_edition
        else resolve_edition_hierarchy(config, edition)
        for edition in _EDITION_IDS
    }

    decision_cache: dict[str, dict[str, dict[str, Any]]] = {}
    by_id = {obj.id: obj for obj in objects}
    matched_by_id: dict[str, list[CoverageMatch]] = defaultdict(list)
    by_designation: dict[str, list[CoverageMatch]] = defaultdict(list)
    for match in matches:
        if match.entry.normalized_designation:
            by_designation[match.entry.normalized_designation].append(match)
        if match.matched_object is None:
            continue
        object_id = match.matched_object.id
        matched_by_id[object_id].append(match)
        if object_id not in decision_cache:
            decision_cache[object_id] = {
                edition: explain_selection(
                    match.matched_object,
                    edition=edition,
                    policy=policies[edition],
                    index=memberships,
                )
                for edition in _EDITION_IDS
            }

    unique_designations = sorted(by_designation)
    designation_results = {
        designation: _designation_outcome(rows) for designation, rows in by_designation.items()
    }
    designations_by_target: dict[str, set[str]] = defaultdict(set)
    for designation, result in designation_results.items():
        if result["matched_object_id"]:
            designations_by_target[result["matched_object_id"]].add(designation)
    matched_designations = sum(
        item["matched_object_id"] is not None for item in designation_results.values()
    )
    unique_target_ids = sorted(matched_by_id)
    parse_failure_count = sum(match.match_method == "parse_failure" for match in matches)
    ambiguous_designation_count = sum(
        item["status"] == "ambiguous" for item in designation_results.values()
    )
    unresolved_designation_count = sum(
        item["status"] == "unresolved" for item in designation_results.values()
    )
    possible_database_missing_count = sum(
        item["status"] == "possible_database_missing" for item in designation_results.values()
    )
    parse_failure_designation_count = sum(
        item["status"] == "parse_failure" for item in designation_results.values()
    )
    edition_counts = {
        edition: sum(
            bool(decision_cache[object_id][edition]["selected"]) for object_id in unique_target_ids
        )
        for edition in _EDITION_IDS
    }
    physical_target_estimate = (
        len(unique_target_ids)
        + unresolved_designation_count
        + possible_database_missing_count
        + ambiguous_designation_count
        + parse_failure_designation_count
    )
    summary = {
        "raw_rows": len(matches),
        "unique_external_designations": len(unique_designations),
        "unique_matched_physical_targets": len(unique_target_ids),
        "estimated_unique_external_targets": physical_target_estimate,
        "exact_canonical_matches": sum(item.match_method == "canonical_exact" for item in matches),
        "exact_alias_matches": sum(item.match_method == "alias_exact" for item in matches),
        "unique_alias_designations_collapsed": sum(
            max(0, len(names) - 1) for names in designations_by_target.values()
        ),
        "catalogue_normalized_matches": sum(
            item.match_method == "catalogue_normalized" for item in matches
        ),
        "coordinate_matches": sum(item.match_method == "coordinate_exactish" for item in matches),
        "manual_override_matches": sum(item.match_method == "manual_override" for item in matches),
        "ambiguous_designations": ambiguous_designation_count,
        "unresolved_designations": unresolved_designation_count,
        "possible_database_missing_designations": possible_database_missing_count,
        "parse_failures": parse_failure_count,
        "duplicate_or_alias_rows_collapsed": max(
            0,
            len(matches)
            - len(unique_target_ids)
            - unresolved_designation_count
            - ambiguous_designation_count
            - parse_failure_count,
        ),
        "match_coverage_percent": _percent(matched_designations, len(unique_designations)),
        "database_coverage_percent": _percent(len(unique_target_ids), physical_target_estimate),
        "edition_coverage_percent": {
            edition: _percent(edition_counts[edition], len(unique_target_ids))
            for edition in _EDITION_IDS
        },
        "edition_selected_target_count": edition_counts,
    }

    targets = tuple(
        _target_row(by_id[object_id], matched_by_id[object_id], decision_cache[object_id])
        for object_id in unique_target_ids
    )
    type_coverage = _type_coverage(targets, designation_results, by_designation)
    source_coverage = _source_coverage(targets)
    nebula_analysis = _nebula_analysis(targets)
    review_rows: dict[str, dict[str, Any]] = {}
    for match in matches:
        if match.matched_object is not None:
            continue
        item = _review_row(match)
        designation = match.entry.normalized_designation
        key = (
            f"{item['review_category']}:{designation}"
            if designation
            else f"{item['review_category']}:{match.entry.locator}"
        )
        if key not in review_rows:
            item["row_locators"] = [match.entry.locator]
            review_rows[key] = item
        else:
            review_rows[key]["row_locators"].append(match.entry.locator)
    review_queue = tuple(review_rows[key] for key in sorted(review_rows))
    metadata = {
        **external_list.metadata(),
        "matching_coordinate_tolerance_arcmin": coordinate_tolerance_arcmin,
        "normalized_catalogue_path": Path(catalogue_path).name,
        "source_files_local_only": True,
        "third_party_content_persisted": False,
    }
    return CoverageReport(
        metadata=metadata,
        summary=summary,
        matches=matches,
        targets=targets,
        type_coverage=type_coverage,
        source_catalogue_coverage=source_coverage,
        nebula_source_analysis=nebula_analysis,
        manual_review_queue=review_queue,
    )


def _designation_outcome(rows: list[CoverageMatch]) -> dict[str, Any]:
    matched_ids = sorted({match.matched_object_id for match in rows if match.matched_object_id})
    candidates = sorted({candidate for match in rows for candidate in match.candidate_ids})
    if len(matched_ids) == 1:
        return {
            "status": "matched",
            "matched_object_id": matched_ids[0],
            "candidate_ids": matched_ids,
        }
    if (
        len(matched_ids) > 1
        or candidates
        and any(match.ambiguity_status != "none" for match in rows)
    ):
        return {"status": "ambiguous", "matched_object_id": None, "candidate_ids": candidates}
    methods = {match.match_method for match in rows}
    if methods == {"parse_failure"}:
        status = "parse_failure"
    elif any(match.entry.ra_deg is not None for match in rows):
        status = "possible_database_missing"
    else:
        status = "unresolved"
    return {"status": status, "matched_object_id": None, "candidate_ids": candidates}


def _target_row(
    obj: DeepSkyObject,
    rows: list[CoverageMatch],
    decisions: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "physical_object_id": obj.id,
        "canonical_designation": obj.id,
        "object_type": _type_name(obj),
        "semantic_subtype": obj.semantic_subtype,
        "source_designations": sorted({row.entry.raw_designation for row in rows}),
        "source_row_locators": sorted({row.entry.locator for row in rows}),
        "match_methods": sorted({row.match_method for row in rows}),
        "match_confidence": min(row.confidence for row in rows),
        "catalogue_sources": sorted(
            {obj.provenance.catalogue, *(record.catalogue_id for record in obj.catalogue_records)}
        ),
        "catalogue_source_families": sorted(
            {
                _CATALOGUE_FAMILIES.get(source, source)
                for source in {
                    obj.provenance.catalogue,
                    *(record.catalogue_id for record in obj.catalogue_records),
                }
            }
        ),
        "editions": {
            edition: {
                "selected": bool(decisions[edition]["selected"]),
                "status": decisions[edition]["status"],
                "reason_codes": [item["code"] for item in decisions[edition]["reasons"]],
                "selection_reasons": decisions[edition]["reasons"],
            }
            for edition in _EDITION_IDS
        },
        "coordinates": {"ra_deg": obj.ra_deg, "dec_deg": obj.dec_deg},
        "size_arcmin": obj.major_axis_arcmin,
    }


def _type_coverage(
    targets: tuple[dict[str, Any], ...],
    designation_results: dict[str, dict[str, Any]],
    by_designation: dict[str, list[CoverageMatch]],
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for target in targets:
        grouped[target["object_type"]].append(target)
    target_by_id = {target["physical_object_id"]: target for target in targets}
    designation_groups: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: {"designations": set(), "matched_designations": set(), "matched_ids": set()}
    )
    for designation, outcome in designation_results.items():
        target_id = outcome["matched_object_id"]
        target = target_by_id.get(target_id) if target_id else None
        hint = next(
            (
                row.entry.object_type_hint
                for row in by_designation[designation]
                if row.entry.object_type_hint
            ),
            None,
        )
        type_name = target["object_type"] if target is not None else _hint_type_name(hint)
        designation_groups[type_name]["designations"].add(designation)
        if target_id:
            designation_groups[type_name]["matched_designations"].add(designation)
            designation_groups[type_name]["matched_ids"].add(target_id)

    result: dict[str, Any] = {}
    for type_name in sorted(set(grouped) | set(designation_groups)):
        items = grouped[type_name]
        external = designation_groups[type_name]
        result[type_name] = {
            "unique_external_designations": len(external["designations"]),
            "unambiguously_matched_external_designations": len(external["matched_designations"]),
            "unique_matched_physical_targets": len(items),
            "selected_by_edition": {
                edition: sum(item["editions"][edition]["selected"] for item in items)
                for edition in _EDITION_IDS
            },
        }
    return result


def _hint_type_name(hint: str | None) -> str:
    if not hint:
        return "unknown"
    value = "".join(char for char in hint.casefold() if char.isalnum())
    if value in {"gx", "gal", "galaxy"}:
        return "galaxy"
    if value in {"group", "hcg", "galaxycluster", "galaxyclustergroup"}:
        return "galaxy group"
    if value in {"oc", "opencluster"}:
        return "open cluster"
    if value in {"gc", "globularcluster"}:
        return "globular cluster"
    if value in {"pn", "planetary", "planetarynebula"}:
        return "planetary nebula"
    if value in {"rn", "reflection", "reflectionnebula"}:
        return "reflection nebula"
    if value in {"dn", "dark", "darknebula"}:
        return "dark nebula"
    if value in {"snr", "supernovaremnant"}:
        return "supernova remnant"
    if value in {"hii", "en", "emission", "emissionnebula", "brightnebula"}:
        return "bright nebula / H-II"
    return "other"


def _source_coverage(targets: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    selected: dict[str, Counter[str]] = defaultdict(Counter)
    for target in targets:
        for source in target["catalogue_sources"]:
            counts[source] += 1
            for edition in _EDITION_IDS:
                if target["editions"][edition]["selected"]:
                    selected[source][edition] += 1
    return {
        source: {
            "matched_physical_targets": counts[source],
            "selected_by_edition": {edition: selected[source][edition] for edition in _EDITION_IDS},
        }
        for source in sorted(counts)
    }


def _nebula_analysis(targets: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    nebula_types = {"bright nebula / H-II", "reflection nebula", "dark nebula", "supernova remnant"}
    nebulae = [target for target in targets if target["object_type"] in nebula_types]
    family_names = ("OpenNGC / NGC / IC", "Barnard", "Sharpless", "vdB", "LDN", "LBN")
    by_type: dict[str, Any] = {}
    for type_name in sorted(nebula_types):
        items = [target for target in nebulae if target["object_type"] == type_name]
        catalogue_breakdown: dict[str, int] = {}
        for display_name in family_names:
            catalogue_breakdown[display_name] = sum(
                display_name in item["catalogue_source_families"] for item in items
            )
        non_ldn = [
            item
            for item in items
            if "dark" in type_name and "LDN" not in item["catalogue_source_families"]
        ]
        ldn_only = [
            item
            for item in items
            if "dark" in type_name
            and "LDN" in item["catalogue_source_families"]
            and not (set(item["catalogue_source_families"]) - {"LDN"})
        ]
        non_lbn = [
            item
            for item in items
            if ("bright" in type_name or "reflection" in type_name)
            and "LBN" not in item["catalogue_source_families"]
        ]
        lbn_only = [
            item
            for item in items
            if ("bright" in type_name or "reflection" in type_name)
            and "LBN" in item["catalogue_source_families"]
            and not (set(item["catalogue_source_families"]) - {"LBN"})
        ]
        by_type[type_name] = {
            "unique_matched_external_targets": len(items),
            "catalogue_coverage_counts": catalogue_breakdown,
            "dark_targets_without_ldn": [item["physical_object_id"] for item in non_ldn],
            "ldn_only_targets": [item["physical_object_id"] for item in ldn_only],
            "bright_targets_without_lbn": [item["physical_object_id"] for item in non_lbn],
            "lbn_only_targets": [item["physical_object_id"] for item in lbn_only],
        }
    return {
        "matched_nebula_target_count": len(nebulae),
        "by_type": by_type,
        "policy_note": (
            "External-list membership is evidence for review, not a claim of visual "
            "importance or a production inclusion rule."
        ),
    }


def _review_row(match: CoverageMatch) -> dict[str, Any]:
    if match.match_method == "parse_failure":
        category = "parse_failure"
    elif (
        match.match_method == "coordinate_ambiguous"
        or match.ambiguity_status == "ambiguous_designation"
    ):
        category = "ambiguous_match"
    elif match.entry.ra_deg is not None and match.match_method == "unresolved":
        category = "possible_database_missing"
    else:
        category = "unknown_designation"
    row = match.to_dict()
    row["review_category"] = category
    return row


def _type_name(obj: DeepSkyObject) -> str:
    if obj.object_type == DsoType.BRIGHT_NEBULA:
        subtype = (obj.semantic_subtype or "").casefold()
        if "reflection" in subtype:
            return "reflection nebula"
        return "bright nebula / H-II"
    names = {
        DsoType.GALAXY: "galaxy",
        DsoType.GALAXY_CLUSTER: "galaxy group",
        DsoType.OPEN_CLUSTER: "open cluster",
        DsoType.GLOBULAR_CLUSTER: "globular cluster",
        DsoType.PLANETARY_NEBULA: "planetary nebula",
        DsoType.DARK_NEBULA: "dark nebula",
        DsoType.SUPERNOVA_REMNANT: "supernova remnant",
    }
    return names.get(obj.object_type, "other")


def _percent(numerator: int, denominator: int) -> float | None:
    return round(100.0 * numerator / denominator, 2) if denominator else None


def summarize_report(report: CoverageReport) -> str:
    """Format a compact human-readable terminal summary."""
    metadata, summary = report.metadata, report.summary
    lines = [
        f"External list: {metadata['source']} — {metadata['source_list']}",
        f"Raw rows: {summary['raw_rows']}",
        f"Unique raw designations: {metadata['unique_raw_designations']}",
        f"Unique external designations: {summary['unique_external_designations']}",
        f"Unique matched physical targets: {summary['unique_matched_physical_targets']}",
        f"Estimated unique external targets: {summary['estimated_unique_external_targets']}",
        "",
        f"Canonical matches: {summary['exact_canonical_matches']}",
        f"Alias matches: {summary['exact_alias_matches']}",
        f"Unique alias designations collapsed: {summary['unique_alias_designations_collapsed']}",
        f"Catalogue-normalized matches: {summary['catalogue_normalized_matches']}",
        f"Coordinate matches: {summary['coordinate_matches']}",
        f"Manual overrides: {summary['manual_override_matches']}",
        f"Ambiguous designations: {summary['ambiguous_designations']}",
        f"Unresolved designations: {summary['unresolved_designations']}",
        f"Parse failures: {summary['parse_failures']}",
        "",
        f"Match coverage: {_fmt_percent(summary['match_coverage_percent'])}",
        "Database coverage (estimated targets): "
        f"{_fmt_percent(summary['database_coverage_percent'])}",
        "Edition coverage of matched physical targets:",
    ]
    for edition in _EDITION_IDS:
        count = summary["edition_selected_target_count"][edition]
        percent = _fmt_percent(summary["edition_coverage_percent"][edition])
        total = summary["unique_matched_physical_targets"]
        lines.append(f"  {edition.title():<10} {count:>5} / {total:<5} {percent}")
    return "\n".join(lines)


def write_json_report(report: CoverageReport, path: str | Path) -> None:
    import json

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def write_csv_report(report: CoverageReport, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fields = (
        "source",
        "source_list",
        "locator",
        "imported_file",
        "raw_designation",
        "normalized_designation",
        "match_method",
        "match_confidence",
        "matched_canonical_designation",
        "matched_physical_object_id",
        "object_type",
        "catalogue_sources",
        "catalogue_source_families",
        "candidate_ids",
        "ambiguity_status",
        "match_note",
        "pocket_selected",
        "standard_selected",
        "deep_selected",
        "reference_selected",
    )
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for match in report.matches:
            row = match.to_dict()
            target_row = next(
                (
                    item
                    for item in report.targets
                    if item["physical_object_id"] == row["matched_physical_object_id"]
                ),
                None,
            )
            row["catalogue_source_families"] = (
                target_row["catalogue_source_families"] if target_row is not None else []
            )
            for edition in _EDITION_IDS:
                row[f"{edition}_selected"] = (
                    target_row["editions"][edition]["selected"] if target_row is not None else ""
                )
            for key in ("candidate_ids", "catalogue_sources", "catalogue_source_families"):
                row[key] = ";".join(row[key])
            writer.writerow({field: row.get(field, "") for field in fields})


def compare_reports(paths: tuple[str | Path, ...], *, minimum_lists: int = 1) -> dict[str, Any]:
    """Compare list reports by normalized physical object ID."""
    import json

    if minimum_lists < 1:
        raise ValueError("minimum_lists must be at least 1")
    lists_by_key: dict[tuple[str, str], dict[str, str]] = {}
    memberships: dict[str, set[str]] = defaultdict(set)
    object_types: dict[str, str] = {}
    for report_path in paths:
        data = json.loads(Path(report_path).read_text(encoding="utf-8"))
        source = str(data["metadata"]["source"])
        source_list = str(data["metadata"]["source_list"])
        list_name = f"{source} / {source_list}"
        list_key = (source.casefold(), source_list.casefold())
        lists_by_key.setdefault(list_key, {"name": list_name, "report": Path(report_path).name})
        for target in data.get("targets", []):
            object_id = target["physical_object_id"]
            memberships[object_id].add(list_name)
            object_types[object_id] = target["object_type"]
    lists = [lists_by_key[key] for key in sorted(lists_by_key)]
    counts = Counter(len(source_lists) for source_lists in memberships.values())
    return {
        "lists": lists,
        "unique_physical_targets_union": len(memberships),
        "intersection_count": sum(len(values) == len(lists) for values in memberships.values())
        if lists
        else 0,
        "minimum_lists": minimum_lists,
        "targets_in_at_least_minimum_lists": sorted(
            object_id for object_id, values in memberships.items() if len(values) >= minimum_lists
        ),
        "list_count_histogram": {str(count): counts[count] for count in sorted(counts)},
        "targets": [
            {
                "physical_object_id": object_id,
                "object_type": object_types[object_id],
                "lists": sorted(source_lists),
            }
            for object_id, source_lists in sorted(memberships.items())
        ],
    }


def _fmt_percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}%"
