"""Auditable summaries and explanations of the existing edition selection."""

from __future__ import annotations

import csv
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from nightsky_atlas.atlas.observing_config import (
    load_observing_lists_config,
    resolve_edition,
)
from nightsky_atlas.catalog.dso_store import load_dso_catalog
from nightsky_atlas.catalog.galaxy_visibility import (
    GalaxyContourClass,
    estimate_galaxy_visibility,
    morphology_priors,
)
from nightsky_atlas.catalog.inventory import build_catalogue_inventory
from nightsky_atlas.catalog.models import DeepSkyObject, DsoType
from nightsky_atlas.catalog.observing_lists import (
    build_membership_index,
    load_observing_lists,
)
from nightsky_atlas.catalog.selection import SelectionPolicy, select_dso
from nightsky_atlas.catalog.visibility import evaluate_visibility

EDITIONS = ("standard", "deep", "reference")
EDITION_REASON_NAMES = {
    "below-catalogue-minimum-extent": "below the edition's catalogue minimum angular extent",
    "catalogue-not-enabled-for-edition": "source catalogue is not enabled for this edition",
    "excluded-type": "object type is excluded from DSO rendering",
    "no-photometry": "no usable photometric or size data for this evaluator",
    "too-faint": "outside the current type-specific visibility limits",
    "below-minimum-size": "below the current minimum angular size",
    "uncertain-catalogue-match": "catalogue association is uncertain and policy excludes it",
    "observing_list_override": "included by an explicit observing-list override",
    "galaxy_visibility_standard": "galaxy meets the Standard visibility class and geometry policy",
    "galaxy_visibility_deep": "galaxy meets the Deep visibility score/class and geometry policy",
    "galaxy_visibility_reference": "galaxy has a classified visibility result and valid dimensions",
    "catalogue_policy_inclusion": "included by a configured catalogue-specific policy",
    "curated_object_policy": "included by a configured curated-object policy",
    "reference_catalogue_complete": "included as a valid object in Reference catalogue coverage",
    "missing_photometry": "no usable photometry or angular size for this edition rule",
    "missing_size": "required angular-size metadata is missing",
    "uncertain_crossmatch_excluded": "uncertain auxiliary-catalogue association is excluded",
    "catalogue_not_allowed_for_edition": "source catalogue is not enabled in this edition",
    "galaxy_visibility_below_edition_policy": (
        "visibility class, score or geometry is below this edition's policy"
    ),
    "below_minimum_size": "object is smaller than this edition's configured threshold",
    "no_matching_policy_rule": "no configured inclusion rule passed for this object type",
    "group_standard_curated_only": "this group is not among the curated Standard group objects",
    "insufficient_group_members": "group lacks the configured minimum member information",
}

TYPE_NAMES = {
    DsoType.GALAXY: "galaxy",
    DsoType.GALAXY_CLUSTER: "galaxy group / cluster",
    DsoType.OPEN_CLUSTER: "open cluster",
    DsoType.GLOBULAR_CLUSTER: "globular cluster",
    DsoType.PLANETARY_NEBULA: "planetary nebula",
    DsoType.DARK_NEBULA: "dark nebula",
    DsoType.SUPERNOVA_REMNANT: "supernova remnant",
    DsoType.OTHER: "other",
}


def _type_name(obj: DeepSkyObject) -> str:
    if obj.object_type != DsoType.BRIGHT_NEBULA:
        return TYPE_NAMES.get(obj.object_type, "other")
    subtype = (obj.semantic_subtype or "").casefold()
    if "reflection" in subtype:
        return "reflection nebula"
    if "hii" in subtype or "bright nebula" in subtype:
        return "bright nebula / H-II"
    return "bright nebula (unspecified subtype)"


def _source_catalogues(obj: DeepSkyObject) -> tuple[str, ...]:
    return tuple(
        sorted(
            {obj.provenance.catalogue} | {record.catalogue_id for record in obj.catalogue_records}
        )
    )


def _normalize_designation(value: str) -> str:
    compact = re.sub(r"[\s./-]+", "", value).upper()
    match = re.fullmatch(r"(NGC|IC)0*(\d+)([A-Z]?)", compact)
    if match:
        return f"{match.group(1)}{int(match.group(2))}{match.group(3)}"
    match = re.fullmatch(r"HCG0*(\d+)", compact)
    if match:
        return f"HCG{int(match.group(1))}"
    return compact


def _raw_fields(obj: DeepSkyObject) -> dict[str, str]:
    return {
        key.casefold(): value
        for record in obj.catalogue_records
        for key, value in record.raw_fields
    }


def _has_quality_metadata(obj: DeepSkyObject, tokens: tuple[str, ...]) -> bool:
    return any(
        token in key or (value and token in value.casefold())
        for key, value in _raw_fields(obj).items()
        for token in tokens
    )


def _valid_morphology(obj: DeepSkyObject) -> bool:
    prior = morphology_priors(obj.hubble_type)
    return not prior.missing and not prior.uncertain


def _field_values(obj: DeepSkyObject) -> dict[str, bool]:
    sb = obj.surface_brightness_mag_arcsec2()
    has_source = bool(_source_catalogues(obj))
    common = {"source_catalogue": has_source}
    if obj.object_type == DsoType.GALAXY:
        return {
            "integrated_magnitude": obj.magnitude is not None,
            "surface_brightness": sb is not None,
            "major_axis": obj.major_axis_arcmin is not None and obj.major_axis_arcmin > 0,
            "minor_axis": obj.minor_axis_arcmin is not None and obj.minor_axis_arcmin > 0,
            "visibility_model": (
                estimate_galaxy_visibility(obj).contour_class != GalaxyContourClass.UNCLASSIFIED
            ),
            "valid_morphology": _valid_morphology(obj),
            **common,
        }
    if obj.object_type == DsoType.OPEN_CLUSTER:
        return {
            "magnitude": obj.magnitude is not None,
            "angular_size": obj.major_axis_arcmin is not None and obj.major_axis_arcmin > 0,
            "richness_or_classification": (
                obj.member_count is not None
                or bool(obj.semantic_subtype)
                or _has_quality_metadata(obj, ("rich", "class", "member"))
            ),
            **common,
        }
    if obj.object_type == DsoType.GLOBULAR_CLUSTER:
        return {
            "magnitude": obj.magnitude is not None,
            "angular_size": obj.major_axis_arcmin is not None and obj.major_axis_arcmin > 0,
            **common,
        }
    if obj.object_type == DsoType.PLANETARY_NEBULA:
        return {
            "magnitude": obj.magnitude is not None,
            "angular_size": obj.major_axis_arcmin is not None and obj.major_axis_arcmin > 0,
            "surface_brightness": sb is not None,
            **common,
        }
    if obj.object_type == DsoType.BRIGHT_NEBULA:
        return {
            "angular_size": obj.major_axis_arcmin is not None and obj.major_axis_arcmin > 0,
            "brightness": obj.magnitude is not None or sb is not None,
            "brightness_or_class_field": (
                obj.magnitude is not None
                or sb is not None
                or bool(obj.semantic_subtype)
                or _has_quality_metadata(obj, ("class", "brightness", "flux"))
            ),
            **common,
        }
    if obj.object_type == DsoType.DARK_NEBULA:
        subtype = (obj.semantic_subtype or "").casefold()
        return {
            "angular_size": obj.major_axis_arcmin is not None and obj.major_axis_arcmin > 0,
            "opacity_or_class": (
                any(token in subtype for token in ("opacity", "opaque", "class ", "rank "))
                or _has_quality_metadata(obj, ("opacity", "class", "rank"))
            ),
            **common,
        }
    if obj.object_type == DsoType.GALAXY_CLUSTER:
        return {
            "member_count": obj.member_count is not None,
            "group_magnitude": obj.magnitude is not None,
            "surface_or_angular_extent": (
                sb is not None or (obj.major_axis_arcmin is not None and obj.major_axis_arcmin > 0)
            ),
            **common,
        }
    return {"magnitude": obj.magnitude is not None, **common}


def _assessment(obj: DeepSkyObject, policy: SelectionPolicy):
    primary_is_openngc = obj.provenance.catalogue == "OpenNGC"
    limits = policy.visibility
    if limits.include_all and not primary_is_openngc:
        limits = replace(limits, include_all=False)
    result = evaluate_visibility(obj, limits)
    minimum = dict(policy.catalogue_minimum_extent_arcmin).get(obj.provenance.catalogue)
    if minimum is not None:
        eligible = minimum <= 0 or (
            obj.major_axis_arcmin is not None and obj.major_axis_arcmin >= minimum
        )
        return replace(
            result,
            visible=eligible,
            reasons=("catalogue-extent-threshold",)
            if eligible
            else ("below-catalogue-minimum-extent",),
        )
    return result


def explain_selection(
    obj: DeepSkyObject,
    *,
    edition: str,
    policy: SelectionPolicy,
    index: dict[str, frozenset[str]],
) -> dict[str, Any]:
    """Explain the current selector result without changing it."""
    selected = select_dso(obj, index=index, policy=policy)
    assessment = _assessment(obj, policy)
    sources = _source_catalogues(obj)
    catalogue_allowed = policy.included_catalogues is None or bool(
        set(sources) & policy.included_catalogues
    )
    forced_sources = sorted(set(sources) & policy.forced_catalogues)
    forced_lists = sorted(selected.list_memberships & policy.forced_lists)
    uncertain_match = obj.provenance.catalogue != "OpenNGC" and any(
        record.crossmatch_decision == "uncertain" for record in obj.catalogue_records
    )
    reasons: list[dict[str, str]] = []

    def add(code: str, category: str, explanation: str) -> None:
        item = {"code": code, "category": category, "explanation": explanation}
        if item not in reasons:
            reasons.append(item)

    if selected.list_memberships:
        add(
            "observing_list_membership",
            "semantic_importance",
            "observing-list memberships affect priority; forced memberships are listed separately",
        )
    if forced_lists:
        add("forced_observing_list", "semantic_importance", ", ".join(forced_lists))
    if forced_sources:
        add("forced_catalogue", "catalogue_coverage", ", ".join(forced_sources))
    if not catalogue_allowed:
        add(
            "catalogue_not_enabled",
            "edition_policy",
            "none of the object's source catalogues is enabled for this edition",
        )
    if uncertain_match and not policy.include_uncertain_catalogue_matches:
        add(
            "uncertain_match_excluded",
            "catalogue_coverage",
            "an uncertain auxiliary-catalogue match is excluded by this edition policy",
        )
    elif uncertain_match:
        add(
            "conditional_uncertain_match_allowed",
            "catalogue_coverage",
            "this edition explicitly permits the uncertain auxiliary-catalogue association",
        )
    reason_categories = {
        "type_visibility_passed": (
            "physical_detectability",
            f"the production visibility evaluator passed (score {assessment.score:.3f})",
        ),
        "observing_list_override": (
            "semantic_importance",
            "selected through an explicit forced observing list",
        ),
        "galaxy_visibility_standard": (
            "physical_detectability",
            EDITION_REASON_NAMES["galaxy_visibility_standard"],
        ),
        "galaxy_visibility_deep": (
            "physical_detectability",
            EDITION_REASON_NAMES["galaxy_visibility_deep"],
        ),
        "galaxy_visibility_reference": (
            "physical_detectability",
            EDITION_REASON_NAMES["galaxy_visibility_reference"],
        ),
        "catalogue_policy_inclusion": (
            "catalogue_coverage",
            EDITION_REASON_NAMES["catalogue_policy_inclusion"],
        ),
        "curated_object_policy": (
            "semantic_importance",
            EDITION_REASON_NAMES["curated_object_policy"],
        ),
        "size_or_brightness_inclusion": (
            "physical_detectability",
            "included by configured size or brightness threshold",
        ),
        "reference_catalogue_complete": (
            "catalogue_coverage",
            EDITION_REASON_NAMES["reference_catalogue_complete"],
        ),
        "missing_photometry": (
            "physical_detectability",
            EDITION_REASON_NAMES["missing_photometry"],
        ),
        "missing_size": ("physical_detectability", EDITION_REASON_NAMES["missing_size"]),
        "uncertain_crossmatch_excluded": (
            "catalogue_coverage",
            EDITION_REASON_NAMES["uncertain_crossmatch_excluded"],
        ),
        "catalogue_not_allowed_for_edition": (
            "catalogue_coverage",
            EDITION_REASON_NAMES["catalogue_not_allowed_for_edition"],
        ),
        "galaxy_visibility_below_edition_policy": (
            "physical_detectability",
            EDITION_REASON_NAMES["galaxy_visibility_below_edition_policy"],
        ),
        "group_standard_curated_only": (
            "semantic_importance",
            "Standard includes only explicitly curated or strongly justified groups",
        ),
        "group_deep_policy": ("catalogue_coverage", "included by the Deep group-level policy"),
        "open_cluster_standard_policy": (
            "physical_detectability",
            "included by the Standard prominence, size, magnitude or curated-list rule",
        ),
        "open_cluster_deep_policy": (
            "catalogue_coverage",
            "included by the Deep open-cluster coverage policy",
        ),
        "globular_cluster_standard_policy": (
            "physical_detectability",
            "included by the Standard classical/prominent globular rule",
        ),
        "globular_cluster_deep_policy": (
            "catalogue_coverage",
            "included by the Deep globular-cluster policy",
        ),
        "planetary_nebula_deep_policy": (
            "physical_detectability",
            "included by the Deep planetary-nebula metadata rule",
        ),
        "bright_nebula_deep_size": (
            "physical_detectability",
            "included by the Deep bright-nebula size rule",
        ),
        "dark_nebula_deep_size": (
            "physical_detectability",
            "included by the Deep dark-nebula size rule",
        ),
        "below_minimum_size": (
            "physical_detectability",
            EDITION_REASON_NAMES["below_minimum_size"],
        ),
        "no_matching_policy_rule": (
            "edition_policy",
            EDITION_REASON_NAMES["no_matching_policy_rule"],
        ),
        "insufficient_group_members": (
            "catalogue_coverage",
            EDITION_REASON_NAMES["insufficient_group_members"],
        ),
        "no-photometry": (
            "physical_detectability",
            EDITION_REASON_NAMES["no-photometry"],
        ),
        "too-faint": ("physical_detectability", EDITION_REASON_NAMES["too-faint"]),
        "below-minimum-size": (
            "physical_detectability",
            EDITION_REASON_NAMES["below-minimum-size"],
        ),
        "below-catalogue-minimum-extent": (
            "catalogue_coverage",
            EDITION_REASON_NAMES["below-catalogue-minimum-extent"],
        ),
    }
    for code in selected.visibility_reasons:
        if code in reason_categories:
            category, explanation = reason_categories[code]
            add(code, category, explanation)
    if selected.forced and not assessment.visible:
        add(
            "forced_visibility_override",
            "edition_policy",
            "the object is included despite failing ordinary visibility evaluation",
        )
    if (
        selected.visible
        and catalogue_allowed
        and not (uncertain_match and not policy.include_uncertain_catalogue_matches)
    ):
        add("edition_selected", "decision", "included by the current edition rules")
    elif selected.forced:
        add("edition_selected_forced", "decision", "included through a forced rule")
    else:
        add("edition_excluded", "decision", "not selected by the current edition rules")

    missing = sorted(name for name, available in _field_values(obj).items() if not available)
    visibility = None
    if obj.object_type == DsoType.GALAXY:
        estimate = estimate_galaxy_visibility(obj)
        visibility = {
            "class": estimate.contour_class.value,
            "confidence": estimate.confidence,
            "confidence_reasons": list(estimate.confidence_reasons),
            "by_aperture": {
                str(aperture): {
                    "score": value.score,
                    "best_fraction": value.best_fraction,
                    "exit_pupil_mm": value.best_exit_pupil_mm,
                }
                for aperture, value in sorted(estimate.by_aperture.items())
            },
        }
    return {
        "edition": edition,
        "selected": bool(selected.visible or selected.forced),
        "status": (
            "forced"
            if selected.forced
            else "conditionally_included"
            if selected.visible and uncertain_match
            else "included"
            if selected.visible
            else "excluded"
        ),
        "reasons": reasons,
        "dimensions": {
            "semantic_importance": {
                "list_memberships": sorted(selected.list_memberships),
                "forced_lists": forced_lists,
            },
            "physical_detectability": {
                "evaluator_visible": assessment.visible,
                "score": assessment.score,
                "reason_codes": list(assessment.reasons),
            },
            "catalogue_coverage": {
                "source_catalogues": list(sources),
                "allowed": catalogue_allowed,
                "forced_catalogues": forced_sources,
                "uncertain_match": uncertain_match,
                "uncertain_match_allowed": policy.include_uncertain_catalogue_matches,
            },
            "edition_policy": {
                "integrated_magnitude_limit": policy.visibility.integrated_magnitude_limit,
                "surface_brightness_limit": policy.visibility.surface_brightness_limit,
                "minimum_axis_arcmin": policy.visibility.min_axis_arcmin,
                "include_all": policy.visibility.include_all,
                "minimum_catalogue_extent_arcmin": dict(policy.catalogue_minimum_extent_arcmin).get(
                    obj.provenance.catalogue
                ),
            },
        },
        "visibility": visibility,
        "missing_selection_metadata": missing,
    }


def _quantile(sorted_values: list[float], proportion: float) -> float | None:
    if not sorted_values:
        return None
    position = (len(sorted_values) - 1) * proportion
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return round(sorted_values[lower], 4)
    weight = position - lower
    return round(sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight, 4)


def _distribution(values: list[float]) -> dict[str, float | int | None]:
    clean = sorted(value for value in values if math.isfinite(value))
    return {
        "count": len(clean),
        "min": round(clean[0], 4) if clean else None,
        "q1": _quantile(clean, 0.25),
        "median": _quantile(clean, 0.5),
        "q3": _quantile(clean, 0.75),
        "max": round(clean[-1], 4) if clean else None,
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _bins(
    values: list[float], boundaries: tuple[float, ...], labels: tuple[str, ...]
) -> dict[str, int]:
    bins = Counter({label: 0 for label in labels})
    for value in values:
        index = next(
            (i for i, boundary in enumerate(boundaries) if value < boundary), len(labels) - 1
        )
        bins[labels[index]] += 1
    return dict(bins)


def _type_metadata(objects: list[DeepSkyObject]) -> dict[str, Any]:
    grouped: dict[str, list[DeepSkyObject]] = defaultdict(list)
    for obj in objects:
        grouped[_type_name(obj)].append(obj)
    metadata: dict[str, Any] = {}
    for type_name, values in sorted(grouped.items()):
        field_rows = [_field_values(obj) for obj in values]
        fields = sorted({field for row in field_rows for field in row})
        metadata[type_name] = {
            "total": len(values),
            "fields": {
                field: {
                    "available": sum(row.get(field, False) for row in field_rows),
                    "missing": sum(not row.get(field, False) for row in field_rows),
                }
                for field in fields
            },
        }
    return metadata


def _numeric_distributions(objects: list[DeepSkyObject]) -> dict[str, Any]:
    groups = {
        "galaxy": [obj for obj in objects if obj.object_type == DsoType.GALAXY],
        "open_cluster": [obj for obj in objects if obj.object_type == DsoType.OPEN_CLUSTER],
        "globular_cluster": [obj for obj in objects if obj.object_type == DsoType.GLOBULAR_CLUSTER],
        "planetary_nebula": [obj for obj in objects if obj.object_type == DsoType.PLANETARY_NEBULA],
        "bright_nebula": [obj for obj in objects if obj.object_type == DsoType.BRIGHT_NEBULA],
        "dark_nebula": [obj for obj in objects if obj.object_type == DsoType.DARK_NEBULA],
    }
    distributions: dict[str, Any] = {}
    for type_name, values in groups.items():
        distributions[type_name] = {
            "magnitude": _distribution(
                [obj.magnitude for obj in values if obj.magnitude is not None]
            ),
            "surface_brightness_mag_arcsec2": _distribution(
                [
                    brightness
                    for obj in values
                    if (brightness := obj.surface_brightness_mag_arcsec2()) is not None
                ]
            ),
            "major_axis_arcmin": _distribution(
                [obj.major_axis_arcmin for obj in values if obj.major_axis_arcmin is not None]
            ),
            "major_axis_bins_arcmin": _bins(
                [obj.major_axis_arcmin for obj in values if obj.major_axis_arcmin is not None],
                (1.0, 3.0, 10.0, 30.0),
                ("<1'", "1–3'", "3–10'", "10–30'", ">=30'"),
            ),
        }
    galaxy_scores: dict[str, list[float]] = {str(aperture): [] for aperture in (100, 200, 400)}
    galaxy_classes: Counter[str] = Counter({entry.value: 0 for entry in GalaxyContourClass})
    for galaxy in groups["galaxy"]:
        result = estimate_galaxy_visibility(galaxy)
        galaxy_classes[result.contour_class.value] += 1
        for aperture, value in result.by_aperture.items():
            galaxy_scores[str(aperture)].append(value.score)
    distributions["galaxy_visibility"] = {
        "classes": dict(sorted(galaxy_classes.items())),
        "score_by_aperture": {
            aperture: _distribution(scores) for aperture, scores in galaxy_scores.items()
        },
        "magnitude_bins": _bins(
            [obj.magnitude for obj in groups["galaxy"] if obj.magnitude is not None],
            (10.0, 12.0, 13.0, 14.0, 15.0),
            ("<10", "10–12", "12–13", "13–14", "14–15", ">15"),
        ),
    }
    return distributions


def _source_inventory(
    objects: list[DeepSkyObject], inventory: dict[str, Any], selected: dict[str, set[str]]
) -> list[dict[str, Any]]:
    source_ids: dict[str, set[str]] = defaultdict(set)
    record_counts: Counter[str] = Counter()
    for obj in objects:
        source_ids[obj.provenance.catalogue].add(obj.id)
        record_counts[obj.provenance.catalogue] += 1
        for record in obj.catalogue_records:
            source_ids[record.catalogue_id].add(obj.id)
            record_counts[record.catalogue_id] += 1
    inventory_rows = {row["catalogue"]: row for row in inventory["source_rows"]}
    report = []
    for source in sorted(set(source_ids) | set(inventory_rows)):
        row = inventory_rows.get(source, {})
        ids = source_ids.get(source, set())
        report.append(
            {
                "source": source,
                "catalogue_entries": row.get("raw_rows", record_counts[source]),
                "normalized_catalogue_records": record_counts[source],
                "unique_physical_objects_contributed": len(ids),
                "selected_unique_physical_objects": {
                    edition: len(ids & selected[edition]) for edition in EDITIONS
                },
                "new_physical_objects": row.get("new_physical_objects", 0),
                "matched_aliases": row.get("matched_aliases", 0),
                "uncertain_matches": row.get("uncertain_matches", 0),
                "unmatched_aliases": row.get("unmatched_aliases", 0),
            }
        )
    return report


def _selection_warnings(
    objects: list[DeepSkyObject], decisions: dict[str, dict[str, dict[str, Any]]]
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    selected = {
        edition: {obj_id for obj_id, choices in decisions.items() if choices[edition]["selected"]}
        for edition in EDITIONS
    }
    standard = len(selected["standard"])
    deep = len(selected["deep"])
    growth = 100.0 * (deep - standard) / standard if standard else 0.0
    if standard and growth < 20:
        warnings.append(
            {
                "code": "deep_close_to_standard",
                "severity": "notice",
                "count": None,
                "message": f"Deep selects only {growth:.1f}% more objects than Standard.",
            }
        )
    standard_not_deep = sorted(selected["standard"] - selected["deep"])
    deep_not_reference = sorted(selected["deep"] - selected["reference"])
    reference_not_deep = sorted(selected["reference"] - selected["deep"])

    def exclusion_reasons(object_ids: list[str], edition: str) -> dict[str, int]:
        counts: Counter[str] = Counter()
        for obj_id in object_ids:
            counts.update(reason["code"] for reason in decisions[obj_id][edition]["reasons"])
        return dict(sorted(counts.items()))

    for code, ids, message in (
        (
            "standard_not_deep",
            standard_not_deep,
            "Objects selected in Standard but not Deep violate the expected edition hierarchy.",
        ),
        (
            "deep_not_reference",
            deep_not_reference,
            "Objects selected in Deep but not Reference violate the expected edition hierarchy.",
        ),
        (
            "reference_not_deep",
            reference_not_deep,
            "Reference-only coverage is expected; review the count for coverage context.",
        ),
    ):
        if ids:
            failed_edition = "reference" if code == "deep_not_reference" else "deep"
            warnings.append(
                {
                    "code": code,
                    "severity": "notice" if code == "reference_not_deep" else "warning",
                    "count": len(ids),
                    "examples": ids[:20],
                    "reason_code_counts": exclusion_reasons(ids, failed_edition),
                    "message": message,
                }
            )
    obj_by_id = {obj.id: obj for obj in objects}
    type_totals = Counter(_type_name(obj) for obj in objects)
    type_selected = Counter(_type_name(obj_by_id[obj_id]) for obj_id in selected["deep"])
    for type_name, total in sorted(type_totals.items()):
        if total and not type_selected[type_name]:
            warnings.append(
                {
                    "code": "type_unrepresented_in_deep",
                    "severity": "notice",
                    "count": total,
                    "message": f"Deep has no selected {type_name} objects.",
                }
            )
        elif total >= 20 and type_selected[type_name] / total < 0.01:
            warnings.append(
                {
                    "code": "type_very_lightly_represented_in_deep",
                    "severity": "notice",
                    "count": type_selected[type_name],
                    "message": (
                        f"Deep selects less than 1% of {type_name} "
                        f"({type_selected[type_name]} of {total})."
                    ),
                }
            )
    bright_galaxies = [
        obj.id
        for obj in objects
        if obj.object_type == DsoType.GALAXY
        and estimate_galaxy_visibility(obj).contour_class == GalaxyContourClass.BOLD
        and not any(decisions[obj.id][edition]["selected"] for edition in EDITIONS)
    ]
    if bright_galaxies:
        warnings.append(
            {
                "code": "bold_visibility_galaxy_excluded",
                "severity": "notice",
                "count": len(bright_galaxies),
                "examples": sorted(bright_galaxies)[:20],
                "message": "High Crumey visibility classes are excluded by current edition rules.",
            }
        )
    missing_size_types = {
        DsoType.GALAXY,
        DsoType.GALAXY_CLUSTER,
        DsoType.PLANETARY_NEBULA,
        DsoType.BRIGHT_NEBULA,
        DsoType.DARK_NEBULA,
        DsoType.SUPERNOVA_REMNANT,
    }
    selected_without_size = sorted(
        obj_id
        for obj_id in selected["deep"]
        if obj_by_id[obj_id].object_type in missing_size_types
        and obj_by_id[obj_id].major_axis_arcmin is None
    )
    if selected_without_size:
        warnings.append(
            {
                "code": "selected_without_angular_size",
                "severity": "notice",
                "count": len(selected_without_size),
                "examples": selected_without_size[:20],
                "message": "Selected extended objects lack a catalogued major angular extent.",
            }
        )
    source_selected: dict[str, set[str]] = defaultdict(set)
    source_objects: dict[str, set[str]] = defaultdict(set)
    for obj in objects:
        for source in _source_catalogues(obj):
            source_objects[source].add(obj.id)
            if obj.id in selected["reference"]:
                source_selected[source].add(obj.id)
    for source, ids in sorted(source_objects.items()):
        if len(ids) >= 30 and len(source_selected[source]) / len(ids) < 0.5:
            excluded_ids = sorted(ids - source_selected[source])
            reason_counts: Counter[str] = Counter()
            for obj_id in excluded_ids:
                reason_counts.update(
                    reason["code"] for reason in decisions[obj_id]["reference"]["reasons"]
                )
            warnings.append(
                {
                    "code": "reference_excludes_majority_of_source",
                    "severity": "notice",
                    "count": len(ids) - len(source_selected[source]),
                    "source": source,
                    "reason_code_counts": dict(sorted(reason_counts.items())),
                    "message": (
                        f"Reference selects {len(source_selected[source])} of {len(ids)} "
                        f"objects attributed to {source}; inspect its exclusions."
                    ),
                }
            )
    return warnings


def build_selection_report(
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
    """Build a deterministic edition-selection audit report."""
    objects = load_dso_catalog(catalogue_path)
    dsos = [obj for obj in objects if obj.object_type not in {DsoType.STAR, DsoType.DOUBLE_STAR}]
    config = load_observing_lists_config(observing_config_path)
    index = build_membership_index(load_observing_lists(observing_lists_dir))
    policies = {edition: resolve_edition(config, edition) for edition in EDITIONS}
    decisions = {
        obj.id: {
            edition: explain_selection(obj, edition=edition, policy=policies[edition], index=index)
            for edition in EDITIONS
        }
        for obj in sorted(dsos, key=lambda item: item.id)
    }
    selected = {
        edition: {obj_id for obj_id, choices in decisions.items() if choices[edition]["selected"]}
        for edition in EDITIONS
    }
    type_rows = []
    names = sorted({_type_name(obj) for obj in dsos})
    for name in names:
        ids = {obj.id for obj in dsos if _type_name(obj) == name}
        type_rows.append(
            {
                "type": name,
                "total": len(ids),
                **{edition: len(ids & selected[edition]) for edition in EDITIONS},
            }
        )
    inventory = build_catalogue_inventory(
        catalogue_path=catalogue_path,
        catalogue_manifest_path=catalogue_manifest_path,
        openngc_path=openngc_path,
        openngc_manifest_path=openngc_manifest_path,
        openngc_raw_dir=openngc_raw_dir,
        vizier_raw_dir=vizier_raw_dir,
        crossmatch_report_path=crossmatch_report_path,
        observing_config_path=observing_config_path,
        observing_lists_dir=observing_lists_dir,
    )
    dso_decisions = {obj_id: choices for obj_id, choices in decisions.items()}
    object_index = {obj.id: obj for obj in dsos}
    report = {
        "physical_dso_count": len(dsos),
        "normalized_record_count_including_stars": len(objects),
        "edition_policies": {
            edition: {
                "visibility_limits": asdict(policies[edition].visibility),
                "forced_lists": sorted(policies[edition].forced_lists),
                "list_weights": [list(item) for item in policies[edition].list_weights],
                "included_catalogues": (
                    sorted(policies[edition].included_catalogues)
                    if policies[edition].included_catalogues is not None
                    else None
                ),
                "forced_catalogues": sorted(policies[edition].forced_catalogues),
                "catalogue_minimum_extent_arcmin": dict(
                    policies[edition].catalogue_minimum_extent_arcmin
                ),
                "include_uncertain_catalogue_matches": (
                    policies[edition].include_uncertain_catalogue_matches
                ),
                "type_selection_rules": {
                    type_name: asdict(rule) for type_name, rule in policies[edition].type_rules
                },
            }
            for edition in EDITIONS
        },
        "edition_totals": {edition: len(selected[edition]) for edition in EDITIONS},
        "type_counts": type_rows,
        "source_counts": _source_inventory(dsos, inventory, selected),
        "metadata_availability": _type_metadata(dsos),
        "numeric_distributions": _numeric_distributions(dsos),
        "hierarchy_warnings": _selection_warnings(dsos, dso_decisions),
        "objects": {
            obj.id: {
                "type": _type_name(obj),
                "aliases": sorted(obj.cross_ids),
                "source_catalogues": list(_source_catalogues(obj)),
                "magnitude": obj.magnitude,
                "surface_brightness_mag_arcsec2": obj.surface_brightness_mag_arcsec2(),
                "major_axis_arcmin": obj.major_axis_arcmin,
                "minor_axis_arcmin": obj.minor_axis_arcmin,
                "semantic_subtype": obj.semantic_subtype,
                "visibility": choices["deep"]["visibility"],
                "decisions": {
                    edition: {
                        "selected": choice["selected"],
                        "status": choice["status"],
                        "reasons": choice["reasons"],
                    }
                    for edition, choice in choices.items()
                },
                "missing_selection_metadata": {
                    edition: choices[edition]["missing_selection_metadata"] for edition in EDITIONS
                },
            }
            for obj_id, choices in dso_decisions.items()
            for obj in [object_index[obj_id]]
        },
        "report_notes": [
            (
                "Source contribution counts overlap: aliases keep one physical object linked "
                "to multiple sources."
            ),
            (
                "Selection status is exactly the current selector result; report diagnostics "
                "do not change it."
            ),
            "Deep/Reference hierarchy notices are audit warnings, not selection rules.",
        ],
    }
    return _json_safe(report)


def write_selection_csv(report: dict[str, Any], path: str | Path) -> None:
    """Write one deterministic row per physical DSO, with edition reasons as JSON."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as stream:
        fields = (
            "canonical_id",
            "type",
            "source_catalogues",
            "Standard",
            "Deep",
            "Reference",
            "selection_reasons_json",
        )
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for obj_id, data in sorted(report["objects"].items()):
            writer.writerow(
                {
                    "canonical_id": obj_id,
                    "type": data["type"],
                    "source_catalogues": ";".join(data["source_catalogues"]),
                    **{
                        edition.title(): data["decisions"][edition]["status"]
                        for edition in EDITIONS
                    },
                    "selection_reasons_json": json.dumps(
                        {edition: data["decisions"][edition]["reasons"] for edition in EDITIONS},
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                }
            )


def summarize_selection_report(report: dict[str, Any]) -> str:
    """Return the concise human-readable selection tables."""
    lines = [
        f"physical DSOs: {report['physical_dso_count']}",
        f"edition totals: {report['edition_totals']}",
        "",
        "type                              total  Standard   Deep  Reference",
    ]
    for row in report["type_counts"]:
        lines.append(
            f"{row['type']:<32} {row['total']:>6} {row['standard']:>9}"
            f" {row['deep']:>6} {row['reference']:>10}"
        )
    lines.extend(
        (
            "",
            "source                          entries  records  physical  "
            "Standard   Deep  Reference",
        )
    )
    for row in report["source_counts"]:
        lines.append(
            f"{row['source']:<31} {row['catalogue_entries']:>7}"
            f" {row['normalized_catalogue_records']:>8}"
            f" {row['unique_physical_objects_contributed']:>9}"
            f" {row['selected_unique_physical_objects']['standard']:>9}"
            f" {row['selected_unique_physical_objects']['deep']:>6}"
            f" {row['selected_unique_physical_objects']['reference']:>10}"
        )
    lines.extend(("", "warnings:"))
    if not report["hierarchy_warnings"]:
        lines.append("  none")
    else:
        lines.extend(
            f"  [{warning['severity']}] {warning['code']}: {warning['message']}"
            + (
                f" (reasons: {warning['reason_code_counts']})"
                if warning.get("reason_code_counts")
                else ""
            )
            for warning in report["hierarchy_warnings"]
        )
    galaxy_count = next((row for row in report["type_counts"] if row["type"] == "galaxy"), None)
    if galaxy_count:
        lines.extend(
            (
                "",
                "galaxy edition comparison: "
                + ", ".join(f"{edition} {galaxy_count[edition]}" for edition in EDITIONS),
            )
        )
    return "\n".join(lines)


def find_object(objects: list[DeepSkyObject], designation: str) -> DeepSkyObject | None:
    query = _normalize_designation(designation)
    for obj in objects:
        names = (obj.id, *obj.cross_ids, *(record.designation for record in obj.catalogue_records))
        if query in {_normalize_designation(name) for name in names}:
            return obj
    return None
