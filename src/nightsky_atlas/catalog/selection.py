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
selection values.  Per-type visual evaluators are a later milestone.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

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
    "SelectionPolicy",
    "base_label_priority",
    "messier_id",
    "select_dso",
]

_DEFAULT_RENDER_BASE_PRIORITY = 20
_DEFAULT_FORCED_RENDER_PRIORITY = 100


def _membership_bonus(
    memberships: frozenset[str], policy: SelectionPolicy
) -> int:
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
                self.galaxy_contour_class.value
                if self.galaxy_contour_class is not None
                else None
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
    forced = bool(memberships & effective_policy.forced_lists)
    bonus = _membership_bonus(memberships, effective_policy)
    assessment = evaluate_visibility(dso, effective_policy.visibility)

    galaxy_contour_class = (
        estimate_galaxy_visibility(dso).contour_class
        if dso.object_type == DsoType.GALAXY
        else None
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
        importance_score=_importance_score(
            dso, memberships, forced, assessment.score
        ),
        render_priority=render_priority,
        label_priority=label_priority,
        label_mandatory=base_mandatory,
        forced=forced,
        visible=assessment.visible,
        visibility_reasons=assessment.reasons,
        galaxy_contour_class=galaxy_contour_class,
    )
