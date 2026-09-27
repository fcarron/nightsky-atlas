"""Deep-sky object selection metadata and priorities.

Whether an object is *drawn* and whether it is *labelled* are separate
decisions (``AGENTS.md`` sections 14 and 15): a chart may render an object
without ever placing its label.  This module derives, for one
:class:`~nightsky_atlas.catalog.models.DeepSkyObject`, an explicit
:class:`DsoMetadata` carrying both a ``render_priority`` and a
``label_priority``.

The base scores mirror the label ordering in ``AGENTS.md`` section 14.3
(Messier, common name, bright DSO, ordinary DSO).  Observing-list membership
from :mod:`nightsky_atlas.catalog.observing_lists` adds a configurable bonus,
and objects on a forced list are always rendered regardless of magnitude.

Nothing here is a scientifically exact visibility prediction: these are atlas
selection values, combining type-specific edition rules with observing-list
semantics and catalogue availability.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace

from nightsky_atlas.catalog.galaxy_visibility import (
    GalaxyContourClass,
    estimate_galaxy_visibility,
)
from nightsky_atlas.catalog.models import DeepSkyObject, DsoType
from nightsky_atlas.catalog.observing_lists import dso_memberships
from nightsky_atlas.catalog.priority import (
    base_label_priority,
    dso_label_priority,
    messier_id,
)
from nightsky_atlas.catalog.visibility import (
    VisibilityLimits,
    evaluate_visibility,
)

__all__ = [
    "DsoMetadata",
    "VisibilityClassRule",
    "TypeSelectionRule",
    "SelectionPolicy",
    "base_label_priority",
    "messier_id",
    "select_dso",
]

_DEFAULT_RENDER_BASE_PRIORITY = 20
_DEFAULT_FORCED_RENDER_PRIORITY = 100


def _membership_bonus(memberships: frozenset[str], policy: SelectionPolicy) -> int:
    return sum(weight for list_id, weight in policy.list_weights if list_id in memberships)


@dataclass(frozen=True, slots=True)
class SelectionPolicy:
    """Atlas-metadata selection rules resolved for one edition.

    ``forced_lists`` always render.  ``list_weights`` add to both priorities for
    non-forced members.  Priority bases are deliberately small so membership
    bonuses can outrank them without hiding the catalogue-only ordering.
    ``visibility`` holds the per-type render rules used to decide whether an
    object is drawn at all.
    """

    forced_lists: frozenset[str] = frozenset()
    list_weights: tuple[tuple[str, int], ...] = ()
    forced_render_priority: int = _DEFAULT_FORCED_RENDER_PRIORITY
    render_base_priority: int = _DEFAULT_RENDER_BASE_PRIORITY
    visibility: VisibilityLimits = field(default_factory=VisibilityLimits)
    included_catalogues: frozenset[str] | None = None
    forced_catalogues: frozenset[str] = frozenset()
    catalogue_minimum_extent_arcmin: tuple[tuple[str, float], ...] = ()
    include_uncertain_catalogue_matches: bool = False
    type_rules: tuple[tuple[str, TypeSelectionRule], ...] = ()
    edition_id: str | None = None


@dataclass(frozen=True, slots=True)
class VisibilityClassRule:
    contour_class: str
    minimum_major_axis_arcmin: float = 0.0
    bright_magnitude_fallback: float | None = None
    minimum_score_400: float | None = None


@dataclass(frozen=True, slots=True)
class TypeSelectionRule:
    """Configurable, object-type-specific inclusion gates for one edition."""

    use_visibility: bool = True
    visibility_classes: tuple[str, ...] = ()
    visibility_class_rules: tuple[VisibilityClassRule, ...] = ()
    minimum_visibility_score_400: float | None = None
    minimum_major_axis_arcmin: float | None = None
    bright_magnitude_fallback: float | None = None
    maximum_magnitude: float | None = None
    maximum_surface_brightness: float | None = None
    qualifying_catalogues: tuple[str, ...] = ()
    visibility_catalogues: tuple[str, ...] = ()
    catalogue_minimum_major_axis_arcmin: float | None = None
    catalogue_maximum_magnitude: float | None = None
    catalogue_maximum_surface_brightness: float | None = None
    catalogue_minimum_member_count: int | None = None
    catalogue_require_major_axis: bool = False
    qualifying_memberships: tuple[str, ...] = ()
    minimum_member_count: int | None = None
    require_major_axis: bool = False
    require_photometry_or_size: bool = False
    include_all_valid: bool = False
    selection_reason_code: str | None = None
    exclusion_reason_code: str | None = None


@dataclass(frozen=True, slots=True)
class DsoMetadata:
    """Atlas metadata attached to one deep-sky object.

    Memberships and scores are derived from observing lists and catalogue
    values; they are never persisted back onto the astronomical model.
    ``visible`` is the per-type selection decision; an object on a forced list
    renders even when this is ``False``.
    """

    dso_id: str
    list_memberships: frozenset[str] = frozenset()
    visual_score: float = 0.0
    importance_score: float = 0.0
    render_priority: int = 0
    label_priority: int = 0
    label_mandatory: bool = False
    forced: bool = False
    visible: bool = True
    visibility_reasons: tuple[str, ...] = ()
    galaxy_contour_class: GalaxyContourClass | None = None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable mapping of this metadata."""
        return {
            "dso_id": self.dso_id,
            "list_memberships": sorted(self.list_memberships),
            "visual_score": self.visual_score,
            "importance_score": self.importance_score,
            "render_priority": self.render_priority,
            "label_priority": self.label_priority,
            "label_mandatory": self.label_mandatory,
            "forced": self.forced,
            "visible": self.visible,
            "visibility_reasons": list(self.visibility_reasons),
            "galaxy_contour_class": (
                self.galaxy_contour_class.value if self.galaxy_contour_class is not None else None
            ),
        }


def _importance_score(
    dso: DeepSkyObject,
    memberships: frozenset[str],
    forced: bool,
    visual_score: float,
) -> float:
    score = 1.0
    if messier_id(dso) is not None:
        score += 3.0
    score += 2.0 * len(memberships)
    if forced:
        score += 2.0
    score += visual_score / 50.0
    if dso.magnitude is not None:
        score += max(0.0, (10.0 - dso.magnitude) / 5.0)
    return round(score, 3)


def _selection_rule_key(dso: DeepSkyObject) -> str:
    if dso.object_type == DsoType.BRIGHT_NEBULA:
        subtype = (dso.semantic_subtype or "").casefold()
        if not any(token in subtype for token in ("hii", "bright nebula", "reflection")):
            return "bright_nebula_unspecified"
    return dso.object_type.value


def _size_or_brightness(
    dso: DeepSkyObject,
    *,
    minimum_size: float | None,
    maximum_magnitude: float | None,
    maximum_surface_brightness: float | None,
) -> bool:
    checks = []
    if minimum_size is not None:
        checks.append(dso.major_axis_arcmin is not None and dso.major_axis_arcmin >= minimum_size)
    if maximum_magnitude is not None:
        checks.append(dso.magnitude is not None and dso.magnitude <= maximum_magnitude)
    if maximum_surface_brightness is not None:
        surface_brightness = dso.surface_brightness_mag_arcsec2()
        checks.append(
            surface_brightness is not None and surface_brightness <= maximum_surface_brightness
        )
    return any(checks)


def _rule_inclusion(
    dso: DeepSkyObject,
    rule: TypeSelectionRule,
    *,
    sources: set[str],
    memberships: frozenset[str],
    assessment_visible: bool,
) -> tuple[bool, str | None]:
    if (
        rule.use_visibility
        and assessment_visible
        and (
            not rule.visibility_catalogues or bool(sources.intersection(rule.visibility_catalogues))
        )
    ):
        return True, "type_visibility_passed"

    estimate = None
    if (
        rule.visibility_classes
        or rule.visibility_class_rules
        or rule.minimum_visibility_score_400 is not None
    ):
        estimate = estimate_galaxy_visibility(dso) if dso.object_type == DsoType.GALAXY else None
    if estimate is not None:
        if rule.visibility_class_rules:
            for class_rule in rule.visibility_class_rules:
                if estimate.contour_class.value != class_rule.contour_class:
                    continue
                score = estimate.by_aperture.get(400)
                if class_rule.minimum_score_400 is not None and (
                    score is None or score.score < class_rule.minimum_score_400
                ):
                    continue
                size_ok = (
                    dso.major_axis_arcmin is not None
                    and dso.major_axis_arcmin >= class_rule.minimum_major_axis_arcmin
                )
                bright_ok = (
                    class_rule.bright_magnitude_fallback is not None
                    and dso.magnitude is not None
                    and dso.magnitude <= class_rule.bright_magnitude_fallback
                )
                if size_ok or bright_ok:
                    return True, "galaxy_visibility_policy"
        elif (
            estimate.contour_class.value in rule.visibility_classes
            and (
                rule.minimum_visibility_score_400 is None
                or (
                    (score := estimate.by_aperture.get(400)) is not None
                    and score.score >= rule.minimum_visibility_score_400
                )
            )
            and (
                rule.minimum_major_axis_arcmin is None
                or _size_or_brightness(
                    dso,
                    minimum_size=rule.minimum_major_axis_arcmin,
                    maximum_magnitude=rule.bright_magnitude_fallback,
                    maximum_surface_brightness=None,
                )
            )
            and (not rule.require_major_axis or dso.major_axis_arcmin is not None)
        ):
            return True, "galaxy_visibility_policy"

    if rule.include_all_valid:
        if rule.visibility_classes:
            if dso.object_type != DsoType.GALAXY or estimate is None:
                return False, "visibility_class_unavailable"
            if estimate.contour_class.value not in rule.visibility_classes:
                return False, "visibility_class_unclassified"
        if rule.require_major_axis and dso.major_axis_arcmin is None:
            return False, "missing_size"
        has_photometry_or_size = (
            dso.magnitude is not None
            or dso.surface_brightness_mag_arcsec2() is not None
            or dso.major_axis_arcmin is not None
        )
        if rule.require_photometry_or_size and not has_photometry_or_size:
            return False, "missing_photometry"
        if rule.minimum_member_count is not None and (
            dso.member_count is None or dso.member_count < rule.minimum_member_count
        ):
            return False, "insufficient_group_members"
        return True, "reference_catalogue_complete"

    if rule.qualifying_memberships and memberships.intersection(rule.qualifying_memberships):
        return True, "curated_catalogue_policy"

    if rule.qualifying_catalogues and sources.intersection(rule.qualifying_catalogues):
        catalogue_metadata_ok = (
            not rule.catalogue_require_major_axis or dso.major_axis_arcmin is not None
        ) and (
            rule.catalogue_minimum_member_count is None
            or (
                dso.member_count is not None
                and dso.member_count >= rule.catalogue_minimum_member_count
            )
        )
        if catalogue_metadata_ok and (
            not any(
                threshold is not None
                for threshold in (
                    rule.catalogue_minimum_major_axis_arcmin,
                    rule.catalogue_maximum_magnitude,
                    rule.catalogue_maximum_surface_brightness,
                )
            )
            or _size_or_brightness(
                dso,
                minimum_size=rule.catalogue_minimum_major_axis_arcmin,
                maximum_magnitude=rule.catalogue_maximum_magnitude,
                maximum_surface_brightness=rule.catalogue_maximum_surface_brightness,
            )
        ):
            return True, "catalogue_policy"
        if not catalogue_metadata_ok:
            if rule.catalogue_require_major_axis and dso.major_axis_arcmin is None:
                return False, "missing_size"
            if rule.catalogue_minimum_member_count is not None and (
                dso.member_count is None or dso.member_count < rule.catalogue_minimum_member_count
            ):
                return False, "insufficient_group_members"
        if (
            rule.catalogue_minimum_major_axis_arcmin is not None
            and dso.major_axis_arcmin is not None
            and dso.major_axis_arcmin < rule.catalogue_minimum_major_axis_arcmin
            and (
                rule.catalogue_maximum_magnitude is None
                or dso.magnitude is None
                or dso.magnitude > rule.catalogue_maximum_magnitude
            )
        ):
            return False, "below_minimum_size"

    if _size_or_brightness(
        dso,
        minimum_size=rule.minimum_major_axis_arcmin,
        maximum_magnitude=rule.maximum_magnitude,
        maximum_surface_brightness=rule.maximum_surface_brightness,
    ):
        return True, "size_or_brightness_policy"

    if rule.include_all_valid:
        if rule.visibility_classes:
            if dso.object_type != DsoType.GALAXY or estimate is None:
                return False, "visibility_class_unavailable"
            if estimate.contour_class.value not in rule.visibility_classes:
                return False, "visibility_class_unclassified"
        if rule.require_major_axis and dso.major_axis_arcmin is None:
            return False, "missing_size"
        has_photometry_or_size = (
            dso.magnitude is not None
            or dso.surface_brightness_mag_arcsec2() is not None
            or dso.major_axis_arcmin is not None
        )
        if rule.require_photometry_or_size and not has_photometry_or_size:
            return False, "missing_photometry"
        if rule.minimum_member_count is not None and (
            dso.member_count is None or dso.member_count < rule.minimum_member_count
        ):
            return False, "insufficient_group_members"
        if rule.catalogue_require_major_axis and dso.major_axis_arcmin is None:
            return False, "missing_size"
        if rule.catalogue_minimum_member_count is not None and (
            dso.member_count is None or dso.member_count < rule.catalogue_minimum_member_count
        ):
            return False, "insufficient_group_members"
        return True, "reference_catalogue_complete"

    if rule.require_photometry_or_size and not (
        dso.magnitude is not None
        or dso.surface_brightness_mag_arcsec2() is not None
        or dso.major_axis_arcmin is not None
    ):
        return False, "missing_photometry"
    return False, None


def select_dso(
    dso: DeepSkyObject,
    *,
    index: Mapping[str, frozenset[str]] | None = None,
    policy: SelectionPolicy | None = None,
) -> DsoMetadata:
    """Derive render/label priorities for one deep-sky object.

    With no ``policy`` the catalogue-only ordering is returned, which keeps the
    pre-observing-list behaviour for callers that do not opt in.
    """
    effective_policy = policy if policy is not None else SelectionPolicy()
    memberships = dso_memberships(dso, index) if index is not None else frozenset()
    base_priority, base_mandatory = base_label_priority(dso)
    source_catalogues = {dso.provenance.catalogue}
    source_catalogues.update(record.catalogue_id for record in dso.catalogue_records)
    catalogue_allowed = effective_policy.included_catalogues is None or bool(
        source_catalogues & effective_policy.included_catalogues
    )
    catalogue_forced = bool(source_catalogues & effective_policy.forced_catalogues)
    forced = bool(memberships & effective_policy.forced_lists) or catalogue_forced
    bonus = _membership_bonus(memberships, effective_policy)
    primary_is_openngc = dso.provenance.catalogue == "OpenNGC"
    if effective_policy.visibility.include_all and not primary_is_openngc:
        # Deep's include-all flag preserves the full primary OpenNGC catalogue;
        # auxiliary catalogues have their own edition selection below.
        visibility_limits = replace(effective_policy.visibility, include_all=False)
    else:
        visibility_limits = effective_policy.visibility
    assessment = evaluate_visibility(dso, visibility_limits)
    catalogue_extent_limit = dict(effective_policy.catalogue_minimum_extent_arcmin).get(
        dso.provenance.catalogue
    )
    catalogue_extent_eligible = (
        catalogue_extent_limit is None
        or catalogue_extent_limit <= 0.0
        or (dso.major_axis_arcmin is not None and dso.major_axis_arcmin >= catalogue_extent_limit)
    )
    if catalogue_extent_limit is not None:
        assessment = replace(
            assessment,
            visible=catalogue_extent_eligible,
            reasons=(
                ("catalogue-extent-threshold",)
                if catalogue_extent_eligible
                else ("below-catalogue-minimum-extent",)
            ),
        )
    uncertain_external_match = not primary_is_openngc and any(
        record.crossmatch_decision == "uncertain" for record in dso.catalogue_records
    )
    uncertain_match_allowed = (
        effective_policy.include_uncertain_catalogue_matches or not uncertain_external_match
    )
    rule_map = dict(effective_policy.type_rules)
    rule = rule_map.get(_selection_rule_key(dso))
    assessment_visible = assessment.visible and catalogue_extent_eligible
    policy_reason: str | None = None
    if rule is None:
        type_policy_visible = assessment_visible
    else:
        type_policy_visible, policy_reason = _rule_inclusion(
            dso,
            rule,
            sources=source_catalogues,
            memberships=memberships,
            assessment_visible=assessment_visible,
        )
    visibility_reasons: list[str] = []
    if rule is None or (not type_policy_visible and policy_reason is None):
        visibility_reasons.extend(assessment.reasons)
    if rule is None and type_policy_visible:
        visibility_reasons.append("type_visibility_passed")
    if forced:
        visibility_reasons.append("observing_list_override")
    if policy_reason is not None:
        reason_code = (
            rule.selection_reason_code if type_policy_visible and rule is not None else None
        )
        reason_code = reason_code or {
            "galaxy_visibility_policy": (
                f"galaxy_visibility_{effective_policy.edition_id or 'edition'}"
            ),
            "catalogue_policy": "catalogue_policy_inclusion",
            "curated_catalogue_policy": "curated_object_policy",
            "size_or_brightness_policy": "size_or_brightness_inclusion",
            "reference_catalogue_complete": "reference_catalogue_complete",
            "type_visibility_passed": "type_visibility_passed",
            "below_minimum_size": "below_minimum_size",
            "missing_photometry": "missing_photometry",
            "missing_size": "missing_size",
            "insufficient_group_members": "insufficient_group_members",
        }.get(policy_reason, policy_reason)
        visibility_reasons.append(reason_code)
    elif not type_policy_visible:
        if rule is not None and rule.exclusion_reason_code:
            visibility_reasons.append(rule.exclusion_reason_code)
        elif policy_reason is None and not visibility_reasons:
            visibility_reasons.append("no_matching_policy_rule")
        if rule is not None and rule.include_all_valid:
            if rule.require_photometry_or_size and not (
                dso.magnitude is not None
                or dso.surface_brightness_mag_arcsec2() is not None
                or dso.major_axis_arcmin is not None
            ):
                visibility_reasons.append("missing_photometry")
            if rule.require_major_axis and dso.major_axis_arcmin is None:
                visibility_reasons.append("missing_size")
        if rule is not None and rule.visibility_class_rules:
            visibility_reasons.append("galaxy_visibility_below_edition_policy")
    if not uncertain_match_allowed:
        visibility_reasons.append("uncertain-catalogue-match")
        visibility_reasons.append("uncertain_crossmatch_excluded")
    elif not catalogue_allowed:
        visibility_reasons.append("catalogue-not-enabled-for-edition")
        visibility_reasons.append("catalogue_not_allowed_for_edition")

    galaxy_contour_class = (
        estimate_galaxy_visibility(dso).contour_class if dso.object_type == DsoType.GALAXY else None
    )

    if forced:
        render_priority = effective_policy.forced_render_priority
        label_priority = dso_label_priority(
            dso,
            memberships=memberships,
            forced=True,
            visual_score=assessment.score,
        )
    else:
        render_priority = effective_policy.render_base_priority + bonus
        label_priority = base_priority + bonus

    return DsoMetadata(
        dso_id=dso.id,
        list_memberships=memberships,
        visual_score=assessment.score,
        importance_score=_importance_score(dso, memberships, forced, assessment.score),
        render_priority=render_priority,
        label_priority=label_priority,
        label_mandatory=base_mandatory,
        forced=forced,
        visible=type_policy_visible and catalogue_allowed and uncertain_match_allowed,
        visibility_reasons=tuple(dict.fromkeys(visibility_reasons)),
        galaxy_contour_class=galaxy_contour_class,
    )
