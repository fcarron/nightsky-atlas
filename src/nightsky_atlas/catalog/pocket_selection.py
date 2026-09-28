"""Auditable simulation and report for the Pocket DSO selection policy."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path
from typing import Any

from nightsky_atlas.atlas.config import load_atlas_config
from nightsky_atlas.atlas.observing_config import (
    load_observing_lists_config,
    resolve_edition,
)
from nightsky_atlas.catalog.dso_store import load_dso_catalog
from nightsky_atlas.catalog.galaxy_visibility import estimate_galaxy_visibility
from nightsky_atlas.catalog.models import DsoType
from nightsky_atlas.catalog.observing_lists import (
    build_membership_index,
    canonical_designation,
    load_observing_lists,
)
from nightsky_atlas.catalog.selection import select_dso
from nightsky_atlas.layout.dso_labels import primary_designation

POCKET_LISTS = ("messier", "caldwell", "herschel400")
_NON_DSO_TYPES = {DsoType.STAR, DsoType.DOUBLE_STAR}
_SKY_BANDS = (
    (60.0, 90.0, "+60 to +90"),
    (30.0, 60.0, "+30 to +60"),
    (0.0, 30.0, "0 to +30"),
    (-30.0, 0.0, "-30 to 0"),
    (-60.0, -30.0, "-60 to -30"),
    (-90.0, -60.0, "-90 to -60"),
)


def _source_catalogues(obj: Any) -> set[str]:
    return {obj.provenance.catalogue} | {item.catalogue_id for item in obj.catalogue_records}


def _sky_band(dec_deg: float) -> str:
    for low, high, name in _SKY_BANDS:
        if low <= dec_deg <= high and (dec_deg != low or high == 90.0):
            return name
    return "unassigned"


def _equal_area_sin_dec_band(dec_deg: float) -> str:
    """Return one of six equal-area declination strips."""
    value = math.sin(math.radians(dec_deg))
    index = min(5, max(0, int((value + 1.0) * 3.0)))
    low = -1.0 + index / 3.0
    high = low + 1.0 / 3.0
    return f"sin_dec[{low:.3f},{high:.3f}{']' if index == 5 else ')'}"


def build_pocket_selection_report(
    *,
    catalogue_path: str | Path = "data/processed/dso/catalogue.json",
    observing_config_path: str | Path = "config/observing_lists.yaml",
    observing_lists_dir: str | Path = "data/fixtures/observing_lists",
    atlas_path: str | Path = "atlas/pocket.yaml",
) -> dict[str, Any]:
    """Simulate Pocket using the exact production selector and atlas limits."""
    objects = [
        obj
        for obj in load_dso_catalog(catalogue_path)
        if obj.object_type not in _NON_DSO_TYPES
    ]
    lists = load_observing_lists(observing_lists_dir)
    membership_index = build_membership_index(lists, objects)
    config = load_observing_lists_config(observing_config_path)
    policy = resolve_edition(config, "pocket")
    atlas = load_atlas_config(atlas_path)
    policy = replace(policy, visibility=atlas.visibility.to_limits())

    decisions = {
        obj.id: select_dso(obj, index=membership_index, policy=policy) for obj in objects
    }
    by_id = {obj.id: obj for obj in objects}
    membership_sets = {
        list_id: {
            obj.id for obj in objects if list_id in decisions[obj.id].list_memberships
        }
        for list_id in POCKET_LISTS
    }
    mandatory_ids = set().union(*membership_sets.values())
    selected_ids = {object_id for object_id, decision in decisions.items() if decision.visible}
    ordinary_ids = selected_ids - mandatory_ids
    selected_galaxies = {
        object_id for object_id in selected_ids if by_id[object_id].object_type == DsoType.GALAXY
    }
    mandatory_galaxies = {
        object_id for object_id in mandatory_ids if by_id[object_id].object_type == DsoType.GALAXY
    }
    galaxy_rule = dict(policy.type_rules).get("galaxy")
    minimum_score = dict(galaxy_rule.minimum_visibility_score_by_aperture).get(100, -0.25)
    minimum_size = galaxy_rule.minimum_major_axis_arcmin if galaxy_rule else None

    canonical_target_index: dict[str, set[str]] = defaultdict(set)
    alias_target_index: dict[str, set[str]] = defaultdict(set)
    for obj in objects:
        canonical_target_index[canonical_designation(obj.id)].add(obj.id)
        for designation in obj.cross_ids:
            alias_target_index[canonical_designation(designation)].add(obj.id)
    unresolved: dict[str, list[str]] = {}
    ambiguous: dict[str, dict[str, list[str]]] = {}
    raw_counts: dict[str, int] = {}
    list_rows: dict[str, dict[str, Any]] = {}
    for list_id in POCKET_LISTS:
        observing_list = lists.get(list_id)
        if observing_list is None:
            unresolved[list_id] = ["missing_fixture"]
            raw_counts[list_id] = 0
            list_rows[list_id] = {"raw_entries": 0, "resolved_physical_objects": 0}
            continue
        aliases = dict(observing_list.object_aliases)
        missing: list[str] = []
        non_dso_entries: list[str] = []
        duplicate_targets: dict[str, list[str]] = {}
        resolved_ids: set[str] = set()
        for designation in sorted(observing_list.objects):
            target = aliases.get(designation, designation)
            matches = canonical_target_index.get(target) or alias_target_index.get(target, set())
            if not matches:
                if designation in observing_list.non_dso_entries:
                    non_dso_entries.append(designation)
                else:
                    missing.append(designation)
            elif len(matches) > 1:
                duplicate_targets[designation] = sorted(matches)
                resolved_ids.update(matches)
            else:
                resolved_ids.update(matches)
        unresolved[list_id] = missing
        ambiguous[list_id] = duplicate_targets
        raw_count = observing_list.raw_entry_count or len(observing_list.objects)
        raw_counts[list_id] = raw_count
        list_rows[list_id] = {
            "raw_entries": raw_count,
            "fixture_target_designations": len(observing_list.objects),
            "resolved_physical_objects": len(resolved_ids),
            "unresolved_designations": missing,
            "non_dso_entries": non_dso_entries,
            "ambiguous_designations": duplicate_targets,
        }

    overlap = {
        "messier_herschel400": len(membership_sets["messier"] & membership_sets["herschel400"]),
        "messier_caldwell": len(membership_sets["messier"] & membership_sets["caldwell"]),
        "caldwell_herschel400": len(membership_sets["caldwell"] & membership_sets["herschel400"]),
        "all_three": len(set.intersection(*(membership_sets[item] for item in POCKET_LISTS))),
    }

    type_counts: dict[str, dict[str, int]] = {}
    for object_type in sorted({obj.object_type.value for obj in objects}):
        ids = {obj.id for obj in objects if obj.object_type.value == object_type}
        type_counts[object_type] = {
            "pool": len(ids),
            "mandatory": len(ids & mandatory_ids),
            "selected": len(ids & selected_ids),
            "ordinary_fill": len(ids & ordinary_ids),
        }

    source_ids: dict[str, set[str]] = defaultdict(set)
    for obj in objects:
        for source in _source_catalogues(obj):
            source_ids[source].add(obj.id)
    source_counts = {
        source: {
            "pool_physical_objects": len(ids),
            "selected_physical_objects": len(ids & selected_ids),
        }
        for source, ids in sorted(source_ids.items())
    }

    band_counts: dict[str, dict[str, int]] = {}
    for _, _, band in _SKY_BANDS:
        band_objects = [obj for obj in objects if _sky_band(obj.dec_deg) == band]
        band_counts[band] = {
            "mandatory": sum(obj.id in mandatory_ids for obj in band_objects),
            "selected": sum(obj.id in selected_ids for obj in band_objects),
            "by_type": dict(sorted(Counter(
                obj.object_type.value for obj in band_objects if obj.id in mandatory_ids
            ).items())),
        }
    equal_area_counts: dict[str, dict[str, Any]] = {}
    for index in range(6):
        low = -1.0 + index / 3.0
        high = low + 1.0 / 3.0
        band = f"sin_dec[{low:.3f},{high:.3f}{']' if index == 5 else ')'}"
        band_objects = [obj for obj in objects if _equal_area_sin_dec_band(obj.dec_deg) == band]
        equal_area_counts[band] = {
            "mandatory": sum(obj.id in mandatory_ids for obj in band_objects),
            "selected": sum(obj.id in selected_ids for obj in band_objects),
            "mandatory_by_type": dict(sorted(Counter(
                obj.object_type.value for obj in band_objects if obj.id in mandatory_ids
            ).items())),
        }

    visibility_bins = Counter()
    near_threshold: list[dict[str, Any]] = []
    for obj in objects:
        if obj.object_type != DsoType.GALAXY or obj.id in mandatory_ids:
            continue
        estimate = estimate_galaxy_visibility(obj)
        result = estimate.by_aperture.get(100)
        if result is None:
            visibility_bins["unclassified_or_missing"] += 1
            continue
        score = result.score
        if score < -1.0:
            key = "< -1.00"
        elif score < minimum_score:
            key = "-1.00 to -0.25"
        elif score < 0.0:
            key = "-0.25 to 0"
        elif score < 0.75:
            key = "0 to 0.75"
        else:
            key = ">= 0.75"
        visibility_bins[key] += 1
        if abs(score - minimum_score) <= 0.5:
            near_threshold.append(
                {
                    "designation": obj.id,
                    "score_100mm": score,
                    "contour_class": estimate.contour_class.value,
                    "major_axis_arcmin": obj.major_axis_arcmin,
                    "selected": obj.id in selected_ids,
                    "meets_size_floor": (
                        minimum_size is None
                        or (
                            obj.major_axis_arcmin is not None
                            and obj.major_axis_arcmin >= minimum_size
                        )
                    ),
                }
            )

    near_threshold.sort(
        key=lambda row: (abs(row["score_100mm"] - minimum_score), row["designation"])
    )
    def representative_record(obj: Any) -> dict[str, Any]:
        visibility = decisions[obj.id]
        score = None
        if obj.object_type == DsoType.GALAXY:
            result = estimate_galaxy_visibility(obj).by_aperture.get(100)
            score = result.score if result is not None else None
        return {
            "canonical_designation": obj.id,
            "display_designation": primary_designation(obj),
            "aliases": sorted(obj.cross_ids),
            "object_type": obj.object_type.value,
            "memberships": sorted(visibility.list_memberships),
            "selected": visibility.visible,
            "reasons": list(visibility.visibility_reasons),
            "major_axis_arcmin": obj.major_axis_arcmin,
            "magnitude": obj.magnitude,
            "score_100mm": score,
        }

    ordinary_candidates = [
        obj for obj in objects
        if not decisions[obj.id].forced
        and obj.provenance.catalogue == "OpenNGC"
        and not (decisions[obj.id].list_memberships & set(POCKET_LISTS))
    ]
    ordinary_bright_pn = sorted(
        (
            obj for obj in ordinary_candidates
            if obj.object_type == DsoType.PLANETARY_NEBULA
            and decisions[obj.id].visible
            and obj.magnitude is not None
        ),
        key=lambda obj: (obj.magnitude, obj.id),
    )
    ordinary_bright_clusters = sorted(
        (
            obj for obj in ordinary_candidates
            if obj.object_type == DsoType.OPEN_CLUSTER
            and decisions[obj.id].visible
            and obj.magnitude is not None
        ),
        key=lambda obj: (obj.magnitude, obj.id),
    )
    score_candidates = [
        (obj, estimate_galaxy_visibility(obj).by_aperture.get(100))
        for obj in ordinary_candidates
        if obj.object_type == DsoType.GALAXY
        and obj.major_axis_arcmin is not None
        and obj.major_axis_arcmin >= (minimum_size or 0.0)
    ]
    nearest_pass = sorted(
        (
            (obj, result) for obj, result in score_candidates
            if result is not None and result.score >= minimum_score
        ),
        key=lambda item: (item[1].score - minimum_score, item[0].id),
    )
    nearest_fail = sorted(
        (
            (obj, result) for obj, result in score_candidates
            if result is not None and result.score < minimum_score
        ),
        key=lambda item: (minimum_score - item[1].score, item[0].id),
    )
    representative = [
        {
            "canonical_designation": obj.id,
            "display_designation": primary_designation(obj),
            "aliases": sorted(obj.cross_ids),
            "object_type": obj.object_type.value,
            "memberships": sorted(decisions[obj.id].list_memberships),
            "selected": obj.id in selected_ids,
            "reasons": list(decisions[obj.id].visibility_reasons),
            "major_axis_arcmin": obj.major_axis_arcmin,
            "magnitude": obj.magnitude,
            "score_100mm": (
                estimate_galaxy_visibility(obj).by_aperture[100].score
                if obj.object_type == DsoType.GALAXY
                and 100 in estimate_galaxy_visibility(obj).by_aperture
                else None
            ),
        }
        for obj in objects
        if obj.id in {
            "NGC0224", "NGC0221", "NGC1952", "NGC6205", "NGC6720", "NGC5194",
            "NGC0891", "NGC4565", "NGC7331", "NGC0104", "NGC0253", "NGC0300",
            "NGC3372", "NGC4755", "NGC5128", "NGC5139", "NGC4945", "NGC6744",
            "NGC6752", "NGC1976", "NGC4486",
            "NGC6207", "Cl399", "C041", "C099", "C014",
            "NGC2239", "NGC6882",
        }
    ]
    representative_candidates = {
        "bright_nonmandatory_planetary_nebula": (
            representative_record(ordinary_bright_pn[0]) if ordinary_bright_pn else None
        ),
        "bright_nonmandatory_open_cluster": (
            representative_record(ordinary_bright_clusters[0])
            if ordinary_bright_clusters else None
        ),
        "ordinary_galaxy_just_above_100mm_cutoff": (
            representative_record(nearest_pass[0][0]) if nearest_pass else None
        ),
        "ordinary_galaxy_just_below_100mm_cutoff": (
            representative_record(nearest_fail[0][0]) if nearest_fail else None
        ),
    }
    caldwell_display_violations = sorted(
        obj.id
        for obj in objects
        if decisions[obj.id].visible
        and "caldwell" in decisions[obj.id].list_memberships
        and primary_designation(obj).upper().startswith("C")
        and primary_designation(obj)[1:2].isdigit()
    )

    return {
        "policy": {
            "edition": "pocket",
            "atlas_scale_mm_per_degree": atlas.tiling.mm_per_degree,
            "mandatory_lists": list(POCKET_LISTS),
            "galaxy_aperture_mm": 100,
            "galaxy_score_threshold": minimum_score,
            "galaxy_minimum_major_axis_arcmin": minimum_size,
            "ordinary_non_galaxy_policy": (
                "OpenNGC plus Pocket-enabled sources; non-galaxies use the existing type evaluator"
            ),
            "ordinary_eligible_catalogues": sorted(policy.included_catalogues or ()),
        },
        "physical_dso_pool": len(by_id),
        "list_counts": list_rows,
        "mandatory_union_physical_objects": len(mandatory_ids),
        "list_overlaps": overlap,
        "unresolved_list_mappings": unresolved,
        "ambiguous_list_mappings": ambiguous,
        "selected_pocket_physical_objects": len(selected_ids),
        "ordinary_fill_total": len(ordinary_ids),
        "ordinary_100mm_galaxies": len(selected_galaxies - mandatory_galaxies),
        "ordinary_non_galaxy_objects": len(ordinary_ids - selected_galaxies),
        "type_counts": type_counts,
        "source_counts": source_counts,
        "mandatory_sky_distribution": {
            "declination_bands_not_equal_area": band_counts,
            "equal_area_sin_declination_bands": equal_area_counts,
            "mandatory_north": sum(
                obj.id in mandatory_ids and obj.dec_deg >= 0 for obj in objects
            ),
            "mandatory_south": sum(
                obj.id in mandatory_ids and obj.dec_deg < 0 for obj in objects
            ),
            "selected_north": sum(
                obj.id in selected_ids and obj.dec_deg >= 0 for obj in objects
            ),
            "selected_south": sum(
                obj.id in selected_ids and obj.dec_deg < 0 for obj in objects
            ),
        },
        "non_mandatory_galaxy_score_100mm_bins": dict(sorted(visibility_bins.items())),
        "galaxies_within_0_5_mag_of_cutoff": near_threshold,
        "representative_objects": representative,
        "representative_candidates": representative_candidates,
        "caldwell_display_violations": caldwell_display_violations,
        "excluded_aggregate_designations": ["C014"],
        "selection_hierarchy_note": (
            "Pocket is intentionally separate; other edition policies are unchanged."
        ),
    }


def summarize_pocket_selection_report(report: dict[str, Any]) -> str:
    """Return a concise deterministic human-readable Pocket report."""
    lines = [
        f"physical DSO pool: {report['physical_dso_pool']}",
        "mandatory physical objects: "
        f"Messier {report['list_counts']['messier']['resolved_physical_objects']}, "
        f"Caldwell {report['list_counts']['caldwell']['resolved_physical_objects']}, "
        f"Herschel 400 {report['list_counts']['herschel400']['resolved_physical_objects']}",
        f"unique mandatory union: {report['mandatory_union_physical_objects']}",
        f"ordinary fill: {report['ordinary_fill_total']} "
        f"({report['ordinary_100mm_galaxies']} galaxies, "
        f"{report['ordinary_non_galaxy_objects']} non-galaxies)",
        f"Pocket total: {report['selected_pocket_physical_objects']}",
        f"galaxy rule: S100 >= {report['policy']['galaxy_score_threshold']} and "
        f"major axis >= {report['policy']['galaxy_minimum_major_axis_arcmin']} arcmin",
        "\ntype                         pool mandatory selected fill",
    ]
    for name, counts in sorted(report["type_counts"].items()):
        lines.append(
            f"{name:28} {counts['pool']:5} {counts['mandatory']:9} "
            f"{counts['selected']:8} {counts['ordinary_fill']:4}"
        )
    lines.append("\nmandatory list overlaps: " + str(report["list_overlaps"]))
    lines.append("mandatory sky distribution (declination bands; not equal-area):")
    for band, values in report["mandatory_sky_distribution"][
        "declination_bands_not_equal_area"
    ].items():
        lines.append(f"  {band:12} {values['mandatory']:4}  {values['by_type']}")
    lines.append(
        "  mandatory hemispheres: north "
        f"{report['mandatory_sky_distribution']['mandatory_north']}, south "
        f"{report['mandatory_sky_distribution']['mandatory_south']}"
    )
    lines.append(
        "  selected hemispheres: north "
        f"{report['mandatory_sky_distribution']['selected_north']}, south "
        f"{report['mandatory_sky_distribution']['selected_south']}"
    )
    lines.append("mandatory equal-area sin(dec) bands:")
    for band, values in report["mandatory_sky_distribution"][
        "equal_area_sin_declination_bands"
    ].items():
        lines.append(f"  {band:28} {values['mandatory']:4}")
    for list_id, missing in report["unresolved_list_mappings"].items():
        lines.append(f"unresolved {list_id}: {', '.join(missing) if missing else 'none'}")
        non_dso = report["list_counts"][list_id].get("non_dso_entries", [])
        if non_dso:
            lines.append(f"non-DSO {list_id}: {', '.join(non_dso)}")
    lines.append(
        "100 mm non-mandatory galaxy score bins: "
        + str(report["non_mandatory_galaxy_score_100mm_bins"])
    )
    return "\n".join(lines)
