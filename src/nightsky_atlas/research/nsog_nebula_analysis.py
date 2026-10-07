"""Local-only NSOG nebula population analysis.

The module reads only the numeric NSOG rating and coarse object type from
AstroPlanner plan rows. It never writes source notes or descriptions.
"""

from __future__ import annotations

import csv
import json
import math
import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from nightsky_atlas.catalog.models import DeepSkyObject, DsoType
from nightsky_atlas.research.observing_lists.models import CoverageMatch, CoverageReport

_DARK = "dark_nebula"
_EMISSION = "emission_bright_nebula"
_REFLECTION = "reflection_nebula"
_SNR = "supernova_remnant"
_MIXED = "mixed_nebula"
_NEBULA_TYPES = {_DARK, _EMISSION, _REFLECTION, _SNR, _MIXED}
_SOURCE_FAMILY = {
    "OpenNGC": "NGC/IC/OpenNGC",
    "VII/7A": "LDN",
    "VII/9": "LBN",
    "VII/20": "Sharpless",
    "VII/21": "vdB",
    "VII/220A": "Barnard",
}
_EDITION_IDS = ("pocket", "standard", "deep", "reference")
_SPECIAL_DARK_TARGETS = {
    "Horsehead / B33": {"B033", "Barnard33", "B 33"},
    "Coalsack": {"C099", "C 99"},
    "Snake / B72": {"B072", "Barnard72", "B 72"},
    "Ink Spot / B86": {"B086", "Barnard86", "B 86"},
    "Pipe components": {
        "B059",
        "B 59",
        "B065",
        "B 65",
        "B066",
        "B 66",
        "B067",
        "B 67",
        "B068",
        "B 68",
        "B069",
        "B 69",
        "B070",
        "B 70",
        "B078",
        "B 78",
    },
}


def read_nsog_annotations(paths: Iterable[str | Path]) -> dict[str, dict[str, Any]]:
    """Read minimal annotations from local APTF NSOG plans, keyed by row locator."""
    annotations: dict[str, dict[str, Any]] = {}
    for raw_path in sorted((Path(path) for path in paths), key=lambda item: item.name):
        if raw_path.suffix.casefold() != ".txt":
            continue
        try:
            try:
                lines = raw_path.read_text(encoding="utf-8-sig").splitlines()
            except UnicodeDecodeError:
                lines = raw_path.read_text(encoding="latin-1").splitlines()
        except OSError as exc:
            raise ValueError(f"cannot read local NSOG plan {raw_path}: {exc}") from exc
        if not lines or not lines[0].strip().upper().startswith("APTF,"):
            continue
        in_objects = False
        has_rating_column = any("NSOG Rating" in line for line in lines)
        constellation = _constellation_from_filename(raw_path.name)
        for line_number, line in enumerate(lines, start=1):
            marker = line.strip()
            if marker == "<<Objects>>":
                in_objects = True
                continue
            if marker == "<<Elements>>":
                break
            if not in_objects:
                continue
            cells = line.split("\t")
            if not cells or not cells[0].strip().isdigit():
                continue
            rating: int | None = None
            if has_rating_column and cells:
                try:
                    candidate = int(cells[-1].strip())
                except ValueError:
                    candidate = 0
                if 1 <= candidate <= 5:
                    rating = candidate
            nsog_type = cells[9].strip() if len(cells) > 9 else ""
            annotations[f"{raw_path.name}:{line_number}"] = {
                "rating": rating,
                "constellation": constellation,
                "category": _category_from_nsog_type(nsog_type),
            }
    return annotations


def build_nsog_nebula_analysis(
    report: CoverageReport,
    *,
    annotations: dict[str, dict[str, Any]],
    all_catalogue_objects: Iterable[DeepSkyObject] | None = None,
    selection_decisions: dict[str, dict[str, Any]] | None = None,
    outline_path: str | Path = "data/fixtures/outlines/nebulae.json",
) -> dict[str, Any]:
    """Build a local detailed report from existing coverage matches and catalog data."""
    targets_by_id = {item["physical_object_id"]: item for item in report.targets}
    matches_by_id: dict[str, list[CoverageMatch]] = defaultdict(list)
    all_target_rows: dict[str, list[CoverageMatch]] = defaultdict(list)
    for match in report.matches:
        object_id = match.matched_object_id
        if object_id is not None:
            all_target_rows[object_id].append(match)

    for object_id, rows in all_target_rows.items():
        obj = rows[0].matched_object
        if obj is None:
            continue
        category = _target_category(obj, [annotations.get(row.entry.locator, {}) for row in rows])
        if category in _NEBULA_TYPES:
            matches_by_id[object_id].extend(rows)

    outline_ids = _outline_ids(outline_path)
    matched_targets: list[dict[str, Any]] = []
    for object_id, matches in sorted(matches_by_id.items()):
        object_rows = all_target_rows[object_id]
        obj = matches[0].matched_object
        if obj is None:
            continue
        annotation_rows = [annotations.get(match.entry.locator, {}) for match in object_rows]
        category = _target_category(obj, annotation_rows)
        family_flags, identities = _identities(obj)
        rating_values = sorted(
            {int(item["rating"]) for item in annotation_rows if item.get("rating") is not None}
        )
        source_target = targets_by_id[object_id]
        shape = _shape_quality(obj, outline_ids)
        matched_targets.append(
            {
                "physical_object_id": object_id,
                "preferred_designation": obj.id,
                "common_name": obj.common_name,
                "nebula_category": category,
                "normalized_object_type": obj.object_type.value,
                "nsog_type_conflict": (
                    obj.object_type == DsoType.OTHER
                    and bool(
                        {item.get("category") for item in annotation_rows}
                        & {_DARK, _EMISSION, _REFLECTION, _SNR}
                    )
                ),
                "nsog_designations": sorted({m.entry.raw_designation for m in matches}),
                "nsog_raw_type_categories": sorted(
                    {
                        annotations.get(match.entry.locator, {}).get("category")
                        for match in object_rows
                        if annotations.get(match.entry.locator, {}).get("category")
                    }
                ),
                "nsog_rating": max(rating_values) if rating_values else None,
                "rating_values_seen": rating_values,
                "rating_conflict": len(rating_values) > 1,
                "constellation": _most_common(
                    [item.get("constellation") for item in annotation_rows]
                )
                or obj.constellation,
                "ra_deg": obj.ra_deg,
                "dec_deg": obj.dec_deg,
                "major_axis_arcmin": obj.major_axis_arcmin,
                "minor_axis_arcmin": obj.minor_axis_arcmin,
                "position_angle_deg": obj.position_angle_deg,
                "catalogue_identities": identities,
                "catalogue_families": sorted(family_flags),
                "dark_identity_class": _dark_identity_class(family_flags, identities),
                "bright_identity_class": _bright_identity_class(family_flags),
                "ldn_opacity": _record_numeric(obj, "VII/7A", "Opacity"),
                "lbn_brightness": _record_numeric(obj, "VII/9", "Bright", aggregate="min"),
                "galactic_latitude_deg": _record_numeric(obj, "VII/7A", "GLAT", aggregate="median")
                or _galactic_latitude_deg(obj),
                "size_quality": shape["size_quality"],
                "contour_quality": shape["contour_quality"],
                "has_project_outline": shape["has_project_outline"],
                "catalogue_sources": sorted(
                    {
                        obj.provenance.catalogue,
                        *(record.catalogue_id for record in obj.catalogue_records),
                    }
                ),
                "deep_selected": source_target["editions"]["deep"]["selected"],
                "reference_selected": source_target["editions"]["reference"]["selected"],
                "deep_reason_codes": source_target["editions"]["deep"]["reason_codes"],
                "reference_reason_codes": source_target["editions"]["reference"]["reason_codes"],
                "match_methods": sorted({m.match_method for m in matches}),
                "match_confidence": min(m.confidence for m in matches),
                "source_row_locators": sorted({m.entry.locator for m in matches}),
            }
        )

    unmatched_nebula_rows = []
    for match in report.matches:
        if match.matched_object is not None:
            continue
        annotation = annotations.get(match.entry.locator, {})
        category = annotation.get("category")
        if category not in _NEBULA_TYPES:
            continue
        unmatched_nebula_rows.append(
            {
                "raw_designation": match.entry.raw_designation,
                "constellation": annotation.get("constellation"),
                "nebula_category": category,
                "nsog_rating": annotation.get("rating"),
                "review_class": _unmatched_class(match),
                "candidate_ids": list(match.candidate_ids),
                "match_method": match.match_method,
                "locator": match.entry.locator,
            }
        )

    matched_targets.sort(key=lambda item: (item["nebula_category"], item["physical_object_id"]))
    full_rating_summary = _rating_summary(report, annotations)
    categories = {}
    for category in sorted(_NEBULA_TYPES):
        rows = [item for item in matched_targets if item["nebula_category"] == category]
        categories[category] = _category_summary(rows)

    dark_rows = [item for item in matched_targets if item["nebula_category"] == _DARK]
    bright_rows = [
        item for item in matched_targets if item["nebula_category"] in {_EMISSION, _REFLECTION}
    ]
    catalogue_objects = tuple(
        all_catalogue_objects
        if all_catalogue_objects is not None
        else (match.matched_object for match in report.matches if match.matched_object is not None)
    )
    catalog_population = _catalog_population_from_objects(catalogue_objects, outline_ids)
    selection_missing = [item for item in matched_targets if not item["deep_selected"]]
    missing_rating_counts = Counter(
        str(item["nsog_rating"] or "unrated") for item in selection_missing
    )
    special_targets = _special_dark_report(
        matched_targets,
        catalogue_objects,
        outline_ids,
        selection_decisions or {},
    )
    pn_2242 = _pn_2242_report(all_target_rows, targets_by_id)
    al_local = _local_al_nebula_availability()

    return {
        "schema_version": 1,
        "source_policy": "Local NSOG plan rows only; no source notes or descriptions retained.",
        "rating_aggregation": {
            "rule": "maximum numeric rating per deduplicated physical target",
            **full_rating_summary,
        },
        "coverage_summary": {
            "raw_rows": report.summary["raw_rows"],
            "unique_external_designations": report.summary["unique_external_designations"],
            "estimated_unique_external_targets": report.summary[
                "estimated_unique_external_targets"
            ],
            "unique_matched_physical_targets": report.summary["unique_matched_physical_targets"],
            "database_coverage_percent": report.summary["database_coverage_percent"],
            "deep_matched_target_count": report.summary["edition_selected_target_count"]["deep"],
            "reference_matched_target_count": report.summary["edition_selected_target_count"][
                "reference"
            ],
            "nebula_category_summaries": categories,
            "matched_targets_with_mixed_or_compound_nsog_type_hint": sum(
                _MIXED in row["nsog_raw_type_categories"] for row in matched_targets
            ),
            "unmatched_nebula_rows": len(unmatched_nebula_rows),
        },
        "catalogue_populations": catalog_population,
        "dark_nebula_catalogue_contribution": _dark_catalogue_summary(dark_rows),
        "dark_rating_by_catalogue": _rating_by_source(dark_rows, dark=True),
        "bright_nebula_catalogue_contribution": _bright_catalogue_summary(bright_rows),
        "bright_rating_by_catalogue": _rating_by_source(bright_rows, dark=False),
        "dark_property_comparison": _dark_property_comparison(dark_rows, catalog_population),
        "bright_property_comparison": _bright_property_comparison(bright_rows, catalog_population),
        "deep_missing": {
            "matched_nebula_targets_not_selected": len(selection_missing),
            "by_rating": {key: missing_rating_counts[key] for key in sorted(missing_rating_counts)},
            "targets": selection_missing,
            "unmatched_nebula_targets": unmatched_nebula_rows,
            "gap_counts": _gap_summary(selection_missing, unmatched_nebula_rows),
        },
        "special_dark_targets": special_targets,
        "ngc2242": pn_2242,
        "astronomical_league_local_crosscheck": al_local,
        "matched_nebula_targets": matched_targets,
        "limitations": [
            "NSOG rating aggregation uses the maximum observed rating when duplicate "
            "target rows disagree.",
            "Catalogue source families are physical-object provenance, not independent "
            "target counts.",
            "LDN area-derived equivalent diameters are not true object contours or "
            "measured major axes.",
            "No Tycho local-density calculation was made; NSOG membership is not a "
            "visibility measurement.",
            "Project-authored nebula paths are schematic outlines, not independent "
            "survey contours.",
        ],
        "hypotheses": [
            "Treat NSOG ratings and source-catalogue overlap as review evidence; do not "
            "copy the full NSOG membership into production rules.",
            "For dark nebulae, compare Barnard-backed targets with LDN-only targets "
            "after grouping LDN subregions by parent ID and measuring contour quality.",
            "For bright nebulae, test whether LBN-only 4-5 star targets add real value "
            "beyond NGC/IC, Sharpless and vdB before testing a brightness-index threshold.",
            "Do not adopt a general opacity, LBN brightness or angular-size cut until "
            "its southern-sky and morphology effects are reviewed.",
        ],
    }


def write_analysis_json(report: dict[str, Any], path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )


def write_target_csv(report: dict[str, Any], path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fields = (
        "nebula_category",
        "physical_object_id",
        "preferred_designation",
        "common_name",
        "nsog_rating",
        "rating_values_seen",
        "rating_conflict",
        "constellation",
        "ra_deg",
        "dec_deg",
        "major_axis_arcmin",
        "minor_axis_arcmin",
        "position_angle_deg",
        "catalogue_identities",
        "catalogue_families",
        "dark_identity_class",
        "bright_identity_class",
        "ldn_opacity",
        "lbn_brightness",
        "galactic_latitude_deg",
        "size_quality",
        "contour_quality",
        "has_project_outline",
        "normalized_object_type",
        "nsog_type_conflict",
        "nsog_raw_type_categories",
        "deep_selected",
        "reference_selected",
        "deep_reason_codes",
        "match_methods",
        "match_confidence",
        "source_row_locators",
    )
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in report["matched_nebula_targets"]:
            writer.writerow({key: _csv_value(row.get(key)) for key in fields})


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["coverage_summary"]
    rating = report["rating_aggregation"]
    matched_nebula_count = sum(
        values["unique_matched_targets"] for values in summary["nebula_category_summaries"].values()
    )
    lines = [
        "# Local NSOG nebula population analysis",
        "",
        "This is a private research artifact generated from local AstroPlanner plans "
        "and the current normalized NightSkyAtlas catalogue. It contains no NSOG "
        "descriptions or observing notes. It is not an atlas selection rule.",
        "",
        "## Scope and coverage",
        "",
        f"- Raw NSOG rows: {summary['raw_rows']}",
        f"- Estimated unique targets: {summary['estimated_unique_external_targets']}",
        f"- Unique matched physical targets: {summary['unique_matched_physical_targets']}",
        f"- Deep / Reference selected among all matched targets: "
        f"{summary['deep_matched_target_count']} / {summary['reference_matched_target_count']}",
        f"- Unique matched nebula targets in these categories: {matched_nebula_count}",
        "",
        "| NSOG nebula category | Raw rows | Unique matched targets | Deep | "
        "Reference | Rating distribution (1–5 / unrated) |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for category, values in sorted(summary["nebula_category_summaries"].items()):
        lines.append(
            f"| {category} | {values['raw_rows']} | {values['unique_matched_targets']} | "
            f"{values['deep_selected']} | {values['reference_selected']} | "
            f"{', '.join(f'{k}:{v}' for k, v in values['rating_counts'].items())} |"
        )
    lines += [
        "",
        "## Rating aggregation validation",
        "",
        f"Unique estimated NSOG targets: {rating['unique_target_count']}; targets "
        f"with no usable rating: {rating['unrated_target_count']}; physical targets "
        f"with conflicting ratings: {rating['conflicting_target_count']}. Conflicts "
        "use the maximum rating for disjoint aggregates; private JSON retains each "
        "observed value.",
        "",
        "| Rating | Unique targets | In database | Deep | Standard | Pocket | Reference |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for value in rating["by_rating"]:
        lines.append(
            f"| {value['rating']} | {value['targets']} | {value['matched']} | "
            f"{value['deep']} | {value['standard']} | {value['pocket']} | "
            f"{value['reference']} |"
        )
    lines += [
        "",
        "## Dark-nebula identity contribution",
        "",
        _markdown_table(report["dark_nebula_catalogue_contribution"]["by_identity_class"]),
        "",
        "### Dark targets by rating and catalogue identity",
        "",
        _markdown_table(report["dark_rating_by_catalogue"]),
        "",
        "### High-rated LDN-only targets",
        "",
        _target_list(report["dark_nebula_catalogue_contribution"]["important_ldn_only_targets"]),
        "",
        "### Dark properties and shape",
        "",
        _markdown_table(report["dark_property_comparison"]),
        "",
        "## Bright-nebula identity contribution",
        "",
        _markdown_table(report["bright_nebula_catalogue_contribution"]["by_identity_class"]),
        "",
        "### Bright targets by rating and catalogue identity",
        "",
        _markdown_table(report["bright_rating_by_catalogue"]),
        "",
        "### High-rated LBN-only targets",
        "",
        _target_list(report["bright_nebula_catalogue_contribution"]["important_lbn_only_targets"]),
        "",
        "### Bright properties and shape",
        "",
        _markdown_table(report["bright_property_comparison"]),
        "",
        "## Deep omissions, high-rated first",
        "",
        _markdown_table(report["deep_missing"]["gap_counts"]),
        "",
        _target_list(
            [row for row in report["deep_missing"]["targets"] if row["nsog_rating"] in {4, 5}]
        ),
        "",
        "## Classical dark-target sanity check",
        "",
        _markdown_table(report["special_dark_targets"]),
        "",
        "## NGC 2242",
        "",
        json.dumps(report["ngc2242"], ensure_ascii=False, sort_keys=True),
        "",
        "## Database / matching / selection / representation gaps",
        "",
        _markdown_table(report["deep_missing"]["gap_counts"]),
        "",
        "### Unmatched nebula review queue",
        "",
        _markdown_table(
            [
                {
                    "designation": row["raw_designation"],
                    "type": row["nebula_category"],
                    "rating": row["nsog_rating"],
                    "review_class": row["review_class"],
                    "candidates": row["candidate_ids"],
                }
                for row in report["deep_missing"]["unmatched_nebula_targets"]
            ]
        ),
        "",
        "The detailed matched-object table is local-only.",
        "",
        "## Local Astronomical League comparison",
        "",
        report["astronomical_league_local_crosscheck"]["note"],
        "",
        "## Limitations",
        "",
    ]
    lines.extend(f"- {item}" for item in report["limitations"])
    lines += ["", "## Hypotheses for later policy work", "", *report["hypotheses"], ""]
    return "\n".join(lines)


def write_markdown(report: dict[str, Any], path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_markdown(report), encoding="utf-8")


def _category_from_nsog_type(value: str) -> str | None:
    compact = re.sub(r"[^a-z]", "", value.casefold())
    if compact in {"dkneb", "dneb"}:
        return _DARK
    if compact in {"eneb", "brneb"}:
        return _EMISSION
    if compact.startswith("rneb"):
        return _REFLECTION
    if "dneb" in compact or "brneb" in compact or "open" in compact and "neb" in compact:
        return _MIXED
    if compact == "snr":
        return _SNR
    return None


def _constellation_from_filename(filename: str) -> str | None:
    match = re.match(r"NSOG_([A-Za-z]{2,3})_D\.[^.]+$", filename, re.IGNORECASE)
    return match.group(1) if match else None


def _match_category(match: CoverageMatch, annotation: dict[str, Any]) -> str | None:
    if annotation.get("category"):
        return annotation["category"]
    if match.matched_object is None:
        return None
    return _category_for_object(match.matched_object)


def _category_for_object(obj: DeepSkyObject) -> str | None:
    if obj.object_type == DsoType.DARK_NEBULA:
        return _DARK
    if obj.object_type == DsoType.SUPERNOVA_REMNANT:
        return _SNR
    if obj.object_type == DsoType.BRIGHT_NEBULA:
        if "reflection" in (obj.semantic_subtype or "").casefold():
            return _REFLECTION
        return _EMISSION
    return None


def _target_category(obj: DeepSkyObject, annotations: list[dict[str, Any]]) -> str | None:
    observed = {
        item.get("category") for item in annotations if item.get("category") in _NEBULA_TYPES
    }
    actual = _category_for_object(obj)
    if actual is not None:
        return actual
    if obj.object_type != DsoType.OTHER:
        return None
    if _MIXED in observed or len(observed) > 1:
        return _MIXED
    if observed:
        # Preserve a source's nebula hint without silently promoting an object
        # that the normalized catalogue classifies as something else/unknown.
        return _MIXED
    return None


def _identities(obj: DeepSkyObject) -> tuple[set[str], list[str]]:
    source_ids = {
        obj.provenance.catalogue,
        *(record.catalogue_id for record in obj.catalogue_records),
    }
    families = {_SOURCE_FAMILY[source] for source in source_ids if source in _SOURCE_FAMILY}
    identities = {str(alias) for alias in obj.cross_ids if alias}
    identities.update(record.designation for record in obj.catalogue_records if record.designation)
    identities.add(obj.id)
    return families, sorted(identities)


def _dark_identity_class(families: set[str], identities: list[str]) -> str:
    barnard = "Barnard" in families or any(_is_barnard(item) for item in identities)
    ldn = "LDN" in families or any(
        item.upper().replace(" ", "").startswith("LDN") for item in identities
    )
    if barnard and ldn:
        return "Barnard + LDN"
    if barnard:
        return "Barnard-backed"
    if ldn:
        return "LDN-only"
    return "non-Barnard/non-LDN"


def _bright_identity_class(families: set[str]) -> str:
    relevant = families & {"NGC/IC/OpenNGC", "Sharpless", "vdB", "LBN"}
    if len(relevant) > 1:
        return "multi-catalogue overlap"
    if "NGC/IC/OpenNGC" in relevant:
        return "OpenNGC/NGC/IC-backed"
    if "Sharpless" in relevant:
        return "Sharpless-backed"
    if "vdB" in relevant:
        return "vdB-backed"
    if "LBN" in relevant:
        return "LBN-only"
    return "other"


def _is_barnard(value: str) -> bool:
    return re.match(r"^B(?:arnard)?\s*\d+[A-Z]?$", value.strip(), re.IGNORECASE) is not None


def _record_numeric(
    obj: DeepSkyObject,
    catalogue_id: str,
    field_name: str,
    *,
    aggregate: str = "max",
) -> float | None:
    values: list[float] = []
    for record in obj.catalogue_records:
        if record.catalogue_id != catalogue_id:
            continue
        try:
            values.append(float(dict(record.raw_fields)[field_name]))
        except (KeyError, TypeError, ValueError):
            continue
    if not values:
        return None
    if aggregate == "min":
        return min(values)
    if aggregate == "median":
        ordered = sorted(values)
        middle = len(ordered) // 2
        return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2
    return max(values)


def _shape_quality(obj: DeepSkyObject, outline_ids: set[str]) -> dict[str, Any]:
    has_outline = obj.id in outline_ids
    fields = [dict(record.raw_fields) for record in obj.catalogue_records]
    has_two_axis_dimensions = any(
        any(a in item for a in ("Diam1", "MajAx", "MajAxis", "Major"))
        and any(b in item for b in ("Diam2", "MinAx", "MinAxis", "Minor"))
        for item in fields
    )
    has_single_axis_dimension = any(
        any(a in item for a in ("Diam", "Diameter", "Radius", "Rad")) for item in fields
    )
    ldn_area_only = any(
        record.catalogue_id == "VII/7A"
        and "Area" in dict(record.raw_fields)
        and not any(key in dict(record.raw_fields) for key in ("Diam", "Diam1", "Diam2"))
        for record in obj.catalogue_records
    )
    if has_outline:
        contour_quality = "project-authored schematic outline"
    else:
        contour_quality = "no contour"
    if has_two_axis_dimensions:
        size_quality = "two-axis catalogue dimensions"
    elif has_single_axis_dimension:
        size_quality = "single-axis catalogue extent"
    elif ldn_area_only:
        size_quality = "rough LDN area-derived equivalent diameter"
    elif obj.major_axis_arcmin is not None:
        size_quality = "normalized extent; source quality not separable"
    else:
        size_quality = "centre only / no extent"
    return {
        "has_project_outline": has_outline,
        "contour_quality": contour_quality,
        "size_quality": size_quality,
    }


def _outline_ids(path: str | Path) -> set[str]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read nebula outlines {path}: {exc}") from exc
    return {str(item["dso_id"]) for item in payload.get("outlines", []) if item.get("dso_id")}


def _category_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    all_matches = [locator for row in rows for locator in row["source_row_locators"]]
    raw_by_rating = Counter(str(row["nsog_rating"] or "unrated") for row in rows)
    return {
        "raw_rows": len(all_matches),
        "unique_matched_targets": len(rows),
        "deep_selected": sum(bool(row["deep_selected"]) for row in rows),
        "reference_selected": sum(bool(row["reference_selected"]) for row in rows),
        "rating_counts": {key: raw_by_rating[key] for key in sorted(raw_by_rating)},
    }


def _rating_summary(
    report: CoverageReport, annotations: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    targets: dict[str, dict[str, Any]] = {}
    for match in report.matches:
        key = match.matched_object_id or f"unmatched:{match.entry.normalized_designation}"
        item = targets.setdefault(
            key, {"ratings": set(), "matched": match.matched_object_id is not None}
        )
        rating = annotations.get(match.entry.locator, {}).get("rating")
        if rating is not None:
            item["ratings"].add(int(rating))
    all_targets = {item["physical_object_id"]: item for item in report.targets}
    result = []
    for value in range(1, 6):
        items = [
            item for item in targets.values() if item["ratings"] and max(item["ratings"]) == value
        ]
        matched_ids = [
            key
            for key, item in targets.items()
            if item["ratings"] and max(item["ratings"]) == value and item["matched"]
        ]
        selected = {
            edition: sum(
                bool(all_targets[key]["editions"][edition]["selected"])
                for key in matched_ids
                if key in all_targets
            )
            for edition in _EDITION_IDS
        }
        result.append(
            {"rating": value, "targets": len(items), "matched": len(matched_ids), **selected}
        )
    conflicts = sum(len(item["ratings"]) > 1 for item in targets.values())
    return {
        "unique_target_count": len(targets),
        "unrated_target_count": sum(not item["ratings"] for item in targets.values()),
        "conflicting_target_count": conflicts,
        "by_rating": result,
    }


def _rating_by_source(rows: list[dict[str, Any]], *, dark: bool) -> list[dict[str, Any]]:
    source_names = (
        ["Barnard", "LDN", "Other"]
        if dark
        else ["NGC/IC/OpenNGC", "Sharpless", "vdB", "LBN", "LBN-only", "Multi-catalogue"]
    )
    result = []
    for rating in range(1, 6):
        group = [row for row in rows if row["nsog_rating"] == rating]
        counts: dict[str, int] = {}
        for source in source_names:
            if dark:
                counts[source] = sum(
                    source in row["catalogue_families"]
                    if source != "Other"
                    else row["dark_identity_class"] == "non-Barnard/non-LDN"
                    for row in group
                )
            else:
                if source in {"LBN-only", "Multi-catalogue"}:
                    wanted = {
                        "LBN-only": "LBN-only",
                        "Multi-catalogue": "multi-catalogue overlap",
                    }[source]
                    counts[source] = sum(row["bright_identity_class"] == wanted for row in group)
                else:
                    counts[source] = sum(source in row["catalogue_families"] for row in group)
        result.append({"rating": rating, "targets": len(group), **counts})
    return result


def _dark_catalogue_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    classes = Counter(row["dark_identity_class"] for row in rows)
    important = [
        row
        for row in rows
        if row["nsog_rating"] in {4, 5} and row["dark_identity_class"] == "LDN-only"
    ]
    return {
        "total_targets": len(rows),
        "barnard_backed_including_overlap": sum(
            "Barnard" in row["catalogue_families"] for row in rows
        ),
        "ldn_backed_including_overlap": sum("LDN" in row["catalogue_families"] for row in rows),
        "ldn_only_count": classes["LDN-only"],
        "barnard_only_count": classes["Barnard-backed"],
        "barnard_plus_ldn_count": classes["Barnard + LDN"],
        "other_count": classes["non-Barnard/non-LDN"],
        "by_identity_class": [
            {"identity_class": key, "targets": classes[key]}
            for key in ("Barnard-backed", "LDN-only", "Barnard + LDN", "non-Barnard/non-LDN")
        ],
        "important_ldn_only_targets": [
            {
                "id": row["physical_object_id"],
                "rating": row["nsog_rating"],
                "deep": row["deep_selected"],
            }
            for row in sorted(
                important,
                key=lambda item: (-int(item["nsog_rating"] or 0), item["physical_object_id"]),
            )
        ],
        "high_rated_ldn_only_count": len(important),
        "high_rated_barnard_backed_count": sum(
            row["nsog_rating"] in {4, 5} and "Barnard" in row["catalogue_families"] for row in rows
        ),
    }


def _bright_catalogue_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    classes = Counter(row["bright_identity_class"] for row in rows)
    source_counts = {
        family: sum(family in row["catalogue_families"] for row in rows)
        for family in ("NGC/IC/OpenNGC", "Sharpless", "vdB", "LBN")
    }
    important_lbn_only = [
        row
        for row in rows
        if row["nsog_rating"] in {4, 5} and row["bright_identity_class"] == "LBN-only"
    ]
    return {
        "total_targets": len(rows),
        "source_coverage_counts_including_overlap": source_counts,
        "by_identity_class": [
            {"identity_class": key, "targets": classes[key]}
            for key in (
                "OpenNGC/NGC/IC-backed",
                "Sharpless-backed",
                "vdB-backed",
                "LBN-only",
                "multi-catalogue overlap",
                "other",
            )
        ],
        "important_lbn_only_targets": [
            {
                "id": row["physical_object_id"],
                "rating": row["nsog_rating"],
                "deep": row["deep_selected"],
            }
            for row in sorted(
                important_lbn_only,
                key=lambda item: (-int(item["nsog_rating"] or 0), item["physical_object_id"]),
            )
        ],
        "high_rated_lbn_only_count": len(important_lbn_only),
        "high_rated_ngc_ic_count": sum(
            row["nsog_rating"] in {4, 5} and "NGC/IC/OpenNGC" in row["catalogue_families"]
            for row in rows
        ),
        "high_rated_sharpless_only_count": sum(
            row["nsog_rating"] in {4, 5}
            and "Sharpless" in row["catalogue_families"]
            and not (set(row["catalogue_families"]) - {"Sharpless"})
            for row in rows
        ),
    }


def catalog_population_from_objects(
    objects: Iterable[DeepSkyObject],
    outline_path: str | Path = "data/fixtures/outlines/nebulae.json",
) -> dict[str, Any]:
    return _catalog_population_from_objects(objects, _outline_ids(outline_path))


def _catalog_population_from_objects(
    objects: Iterable[DeepSkyObject], outline_ids: set[str]
) -> dict[str, Any]:
    objects = tuple(objects)
    output: dict[str, Any] = {}
    for label, source_id in (
        ("Barnard", "VII/220A"),
        ("LDN", "VII/7A"),
        ("LBN", "VII/9"),
        ("Sharpless", "VII/20"),
        ("vdB", "VII/21"),
    ):
        rows = [
            obj
            for obj in objects
            if any(record.catalogue_id == source_id for record in obj.catalogue_records)
        ]
        sizes = [obj.major_axis_arcmin for obj in rows if obj.major_axis_arcmin is not None]
        minor = [obj.minor_axis_arcmin for obj in rows if obj.minor_axis_arcmin is not None]
        opacities = [
            _record_numeric(obj, "VII/7A", "Opacity")
            for obj in rows
            if _record_numeric(obj, "VII/7A", "Opacity") is not None
        ]
        brightness = [
            value
            for obj in rows
            if (value := _record_numeric(obj, "VII/9", "Bright", aggregate="min")) is not None
        ]
        galactic_latitudes = [
            value for obj in rows if (value := _galactic_latitude_deg(obj)) is not None
        ]
        absolute_latitudes = [abs(value) for value in galactic_latitudes]
        output[label] = {
            "unique_physical_objects": len(rows),
            "size_available": len(sizes),
            "size_missing": len(rows) - len(sizes),
            "minor_axis_available": len(minor),
            "has_project_outline": sum(obj.id in outline_ids for obj in rows),
            "major_axis_arcmin": _distribution(sizes),
            "opacity": _distribution(opacities),
            "brightness_index": _distribution(brightness),
            "galactic_latitude_available": len(galactic_latitudes),
            "galactic_latitude_missing": len(rows) - len(galactic_latitudes),
            "galactic_latitude_deg": _distribution(galactic_latitudes),
            "absolute_galactic_latitude_deg": _distribution(absolute_latitudes),
        }
    return output


def _dark_property_comparison(
    rows: list[dict[str, Any]], populations: dict[str, Any]
) -> list[dict[str, Any]]:
    groups = {
        "NSOG matched dark": rows,
        "NSOG dark rated 4-5": [r for r in rows if r["nsog_rating"] in {4, 5}],
        "NSOG dark LDN-only": [r for r in rows if r["dark_identity_class"] == "LDN-only"],
        "NSOG dark Barnard-backed": [r for r in rows if "Barnard" in r["catalogue_families"]],
    }
    result = []
    for label, items in groups.items():
        result.append(_object_group_properties(label, items))
    for label in ("Barnard", "LDN"):
        item = populations[label]
        result.append(
            {
                "population": f"all imported {label}",
                "targets": item["unique_physical_objects"],
                "major_axis_available": item["size_available"],
                "major_axis_missing": item["size_missing"],
                "major_axis_median_arcmin": item["major_axis_arcmin"]["median"],
                "minor_axis_available": item["minor_axis_available"],
                "opacity_available": item["opacity"]["count"],
                "opacity_missing": item["unique_physical_objects"] - item["opacity"]["count"],
                "opacity_median": item["opacity"]["median"],
                "galactic_latitude_available": item["galactic_latitude_available"],
                "galactic_latitude_missing": item["galactic_latitude_missing"],
                "galactic_latitude_median_deg": item["galactic_latitude_deg"]["median"],
                "absolute_galactic_latitude_median_deg": item["absolute_galactic_latitude_deg"][
                    "median"
                ],
                "project_outlines": item["has_project_outline"],
            }
        )
    return result


def _bright_property_comparison(
    rows: list[dict[str, Any]], populations: dict[str, Any]
) -> list[dict[str, Any]]:
    groups = {
        "NSOG matched bright/reflection": rows,
        "NSOG bright/reflection rated 4-5": [r for r in rows if r["nsog_rating"] in {4, 5}],
        "NSOG bright/reflection LBN-only": [
            r for r in rows if r["bright_identity_class"] == "LBN-only"
        ],
    }
    result = [_object_group_properties(label, items) for label, items in groups.items()]
    for label in ("LBN", "Sharpless", "vdB"):
        item = populations[label]
        result.append(
            {
                "population": f"all imported {label}",
                "targets": item["unique_physical_objects"],
                "major_axis_available": item["size_available"],
                "major_axis_missing": item["size_missing"],
                "major_axis_median_arcmin": item["major_axis_arcmin"]["median"],
                "minor_axis_available": item["minor_axis_available"],
                "brightness_index_available": item["brightness_index"]["count"],
                "brightness_index_missing": item["unique_physical_objects"]
                - item["brightness_index"]["count"],
                "brightness_index_median": item["brightness_index"]["median"],
                "project_outlines": item["has_project_outline"],
            }
        )
    return result


def _object_group_properties(label: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    sizes = [item["major_axis_arcmin"] for item in rows if item["major_axis_arcmin"] is not None]
    minors = [item["minor_axis_arcmin"] for item in rows if item["minor_axis_arcmin"] is not None]
    opacity = [item["ldn_opacity"] for item in rows if item["ldn_opacity"] is not None]
    brightness = [item["lbn_brightness"] for item in rows if item["lbn_brightness"] is not None]
    lat = [
        item["galactic_latitude_deg"] for item in rows if item["galactic_latitude_deg"] is not None
    ]
    absolute_latitudes = [abs(value) for value in lat]
    return {
        "population": label,
        "targets": len(rows),
        "major_axis_available": len(sizes),
        "major_axis_missing": len(rows) - len(sizes),
        "major_axis_median_arcmin": _distribution(sizes)["median"],
        "major_axis_q1_arcmin": _distribution(sizes)["q1"],
        "major_axis_q3_arcmin": _distribution(sizes)["q3"],
        "minor_axis_available": len(minors),
        "opacity_available": len(opacity),
        "opacity_missing": len(rows) - len(opacity),
        "opacity_median": _distribution(opacity)["median"],
        "brightness_index_available": len(brightness),
        "brightness_index_missing": len(rows) - len(brightness),
        "brightness_index_median": _distribution(brightness)["median"],
        "galactic_latitude_available": len(lat),
        "galactic_latitude_missing": len(rows) - len(lat),
        "galactic_latitude_median_deg": _distribution(lat)["median"],
        "galactic_latitude_q1_deg": _distribution(lat)["q1"],
        "galactic_latitude_q3_deg": _distribution(lat)["q3"],
        "absolute_galactic_latitude_median_deg": _distribution(absolute_latitudes)["median"],
        "project_outlines": sum(item["has_project_outline"] for item in rows),
        "size_quality_counts": dict(Counter(item["size_quality"] for item in rows)),
        "contour_quality_counts": dict(Counter(item["contour_quality"] for item in rows)),
    }


def _distribution(values: list[float]) -> dict[str, float | int | None]:
    ordered = sorted(values)
    if not ordered:
        return {"count": 0, "min": None, "q1": None, "median": None, "q3": None, "max": None}

    def quantile(fraction: float) -> float:
        pos = (len(ordered) - 1) * fraction
        low, high = int(pos), min(int(pos) + 1, len(ordered) - 1)
        return ordered[low] + (ordered[high] - ordered[low]) * (pos - low)

    return {
        "count": len(ordered),
        "min": ordered[0],
        "q1": quantile(0.25),
        "median": quantile(0.5),
        "q3": quantile(0.75),
        "max": ordered[-1],
    }


def _galactic_latitude_deg(obj: DeepSkyObject) -> float:
    """Derive Galactic latitude from the object's ICRS-compatible coordinates."""
    ra = math.radians(obj.ra_deg)
    dec = math.radians(obj.dec_deg)
    north_pole_ra = math.radians(192.85948)
    north_pole_dec = math.radians(27.12825)
    sin_b = math.sin(dec) * math.sin(north_pole_dec) + math.cos(dec) * math.cos(
        north_pole_dec
    ) * math.cos(ra - north_pole_ra)
    return math.degrees(math.asin(max(-1.0, min(1.0, sin_b))))


def _gap_summary(
    missing: list[dict[str, Any]], unmatched: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    counts = Counter()
    for item in missing:
        counts["selection gap"] += 1
        if not item["has_project_outline"] and item["size_quality"] in {
            "centre only / no extent",
            "rough LDN area-derived equivalent diameter",
        }:
            counts["representation concern among selected gaps"] += 1
    for item in unmatched:
        if item["review_class"] == "ambiguous identity":
            counts["matching gap / ambiguous identity"] += 1
        else:
            counts["possible database gap"] += 1
    return [{"gap_class": label, "targets": counts[label]} for label in sorted(counts)]


def _unmatched_class(match: CoverageMatch) -> str:
    if (
        match.match_method == "coordinate_ambiguous"
        or match.ambiguity_status == "ambiguous_designation"
    ):
        return "ambiguous identity"
    if match.entry.ra_deg is not None:
        return "possible database gap"
    return "unresolved identity; database gap not established"


def _special_dark_report(
    rows: list[dict[str, Any]],
    objects: Iterable[DeepSkyObject],
    outline_ids: set[str],
    selection_decisions: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    by_alias: dict[str, dict[str, Any]] = {}
    for row in rows:
        for alias in row["catalogue_identities"]:
            by_alias[_alias_key(alias)] = row
        by_alias[_alias_key(row["physical_object_id"])] = row
    normalized_rows = []
    for obj in objects:
        if obj.object_type != DsoType.DARK_NEBULA:
            continue
        aliases = {obj.id, *obj.cross_ids}
        aliases.update(record.designation for record in obj.catalogue_records)
        normalized_rows.append((obj, {_alias_key(alias) for alias in aliases}))

    result = []
    for name, aliases in _SPECIAL_DARK_TARGETS.items():
        keys = {_alias_key(alias) for alias in aliases}
        row = next((by_alias.get(key) for key in keys if by_alias.get(key)), None)
        if name == "Pipe components":
            matches = [(obj, keys_) for obj, keys_ in normalized_rows if keys & keys_]
            if matches:
                matched_ids = {row["physical_object_id"] for row in rows}
                components = []
                for obj, _ in matches:
                    decisions = selection_decisions.get(obj.id, {}).get("decisions", {})
                    components.append(
                        {
                            "id": obj.id,
                            "nsog_in_sample": obj.id in matched_ids,
                            "deep_selected": decisions.get("deep", {}).get("selected"),
                            "deep_status": decisions.get("deep", {}).get("status"),
                            "reference_selected": decisions.get("reference", {}).get("selected"),
                            "deep_reason_codes": [
                                item["code"]
                                for item in decisions.get("deep", {}).get("reasons", [])
                            ],
                            "major_axis_arcmin": obj.major_axis_arcmin,
                        }
                    )
                result.append(
                    {
                        "target": name,
                        "found_in_database": True,
                        "canonical_ids": [component["id"] for component in components],
                        "components": components,
                        "catalogue_families": sorted(
                            {family for obj, _ in matches for family in _identities(obj)[0]}
                        ),
                        "contour_quality": "none of these objects has a project outline",
                        "note": "Pipe is represented by multiple Barnard components; "
                        "this is a component set, not one catalogue object.",
                    }
                )
            else:
                result.append(
                    {
                        "target": name,
                        "found_in_database": False,
                        "note": "No matching Barnard component ID found in the "
                        "normalized dark-nebula pool.",
                    }
                )
            continue
        object_match = next(((obj, ids) for obj, ids in normalized_rows if keys & ids), None)
        if object_match is None:
            result.append(
                {
                    "target": name,
                    "found_in_database": False,
                    "note": "No matching identity found in the normalized dark-nebula pool.",
                }
            )
            continue
        obj, _ = object_match
        decisions = selection_decisions.get(obj.id, {}).get("decisions", {})
        nsog_row = row or next(
            (candidate for candidate in rows if candidate["physical_object_id"] == obj.id), None
        )
        shape = _shape_quality(obj, outline_ids)
        result.append(
            {
                "target": name,
                "found_in_database": True,
                "canonical_id": obj.id,
                "catalogue_families": sorted(_identities(obj)[0]),
                "nsog_in_sample": nsog_row is not None,
                "nsog_designation": "; ".join(nsog_row["nsog_designations"]) if nsog_row else None,
                "identity_class": nsog_row["dark_identity_class"]
                if nsog_row
                else _dark_identity_class(*_identities(obj)),
                "deep_selected": decisions.get("deep", {}).get("selected"),
                "deep_status": decisions.get("deep", {}).get("status"),
                "reference_selected": decisions.get("reference", {}).get("selected"),
                "deep_reason_codes": [
                    item["code"] for item in decisions.get("deep", {}).get("reasons", [])
                ],
                "contour_quality": shape["contour_quality"],
                "size_quality": shape["size_quality"],
                "note": "Deep/Reference selection is available only for objects "
                "in the NSOG coverage report.",
            }
        )
    return result


def _pn_2242_report(
    all_target_rows: dict[str, list[CoverageMatch]],
    target_rows: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    for _object_id, matches in all_target_rows.items():
        obj = matches[0].matched_object
        if obj is None or _alias_key(obj.id) != "NGC2242":
            continue
        return {
            "found_in_nsog": True,
            "nsog_designations": sorted({match.entry.raw_designation for match in matches}),
            "deep_selected": False,
            "selection_reasons": target_rows.get(obj.id, {})
            .get("editions", {})
            .get("deep", {})
            .get("reason_codes", []),
            "missing_magnitude": obj.magnitude is None,
            "major_axis_arcmin": obj.major_axis_arcmin,
            "abell_policy_relevant": False,
            "note": "Not an Abell catalogue target; current PN visibility selection "
            "excludes it on available photometry/size evidence.",
        }
    return {"found_in_nsog": False, "note": "NGC 2242 was not found as a matched NSOG target."}


def _local_al_nebula_availability() -> dict[str, Any]:
    root = Path("data/fixtures/observing_lists")
    candidates = [
        path.name
        for path in root.glob("*.json")
        if any(token in path.name.casefold() for token in ("dark", "bright", "nebula"))
    ]
    return {
        "available": bool(candidates),
        "files": sorted(candidates),
        "note": (
            "Local AL bright/dark nebula membership fixtures are absent; no AL-only "
            "or overlap comparison was run."
            if not candidates
            else "Potential local nebula observing-list data found; inspect before "
            "treating it as an AL list."
        ),
    }


def _most_common(values: list[str | None]) -> str | None:
    nonempty = [value for value in values if value]
    return Counter(nonempty).most_common(1)[0][0] if nonempty else None


def _alias_key(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def _csv_value(value: Any) -> str | int | float | bool:
    if value is None:
        return ""
    if isinstance(value, (list, dict, set, tuple)):
        return (
            ";".join(map(str, value))
            if not isinstance(value, dict)
            else json.dumps(value, sort_keys=True)
        )
    return value


def _markdown_table(rows: Any) -> str:
    if isinstance(rows, dict):
        items = [{"key": key, "value": value} for key, value in rows.items()]
    else:
        items = list(rows)
    if not items:
        return "No rows."
    columns = list(items[0])
    lines = ["| " + " | ".join(columns) + " |", "|" + "|".join("---" for _ in columns) + "|"]
    for item in items:
        lines.append("| " + " | ".join(_md_cell(item.get(column)) for column in columns) + " |")
    return "\n".join(lines)


def _md_cell(value: Any) -> str:
    if isinstance(value, dict):
        return ", ".join(f"{k}: {v}" for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return ", ".join(map(str, value))
    return "—" if value is None else str(value).replace("|", "\\|")


def _target_list(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "None."
    lines = []
    for row in rows:
        object_id = row.get("id", row.get("physical_object_id"))
        rating = row.get("rating", row.get("nsog_rating"))
        deep = "yes" if row.get("deep", row.get("deep_selected")) else "no"
        lines.append(f"- {object_id} (NSOG {rating}★; Deep={deep})")
    return "\n".join(lines)
