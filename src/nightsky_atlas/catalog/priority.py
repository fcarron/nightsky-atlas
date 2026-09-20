"""Central label-priority tiers.

Whether an object is *drawn* and whether its label is *placed* are separate
decisions (``AGENTS.md`` sections 5 and 14).  Label importance is defined once
here so the label builder, the deterministic selection pass and the deep-sky
selection metadata cannot drift apart.

The numeric priorities form one shared scale; :func:`tier_for` maps any value
onto the three behavioural tiers used by local density selection:

- **HIGH** -- Messier objects, common-name objects, the visually significant
  Herschel 400 members, prominent bright deep-sky objects, proper-named stars
  and the bright Bayer "main" stars of a constellation.
- **MEDIUM** -- the remaining Herschel 400 members, important NGC/IC objects,
  other Bayer/Flamsteed stars.
- **LOW** -- ordinary NGC/IC objects, weaker star designations, minor
  catalogue labels.

Membership in an observing list may raise priority but never mutates the
astronomical object (``AGENTS.md`` sections 5 and 21); the membership flags are
passed in by the caller.
"""

from __future__ import annotations

from enum import StrEnum

from nightsky_atlas.catalog.models import DeepSkyObject, Star
from nightsky_atlas.catalog.star_names import StarName

__all__ = [
    "BRIGHT_DSO_PRIORITY",
    "CATALOGUE_LABEL_PRIORITY",
    "COMMON_NAME_PRIORITY",
    "HERSCHEL_400",
    "HERSCHEL_PRIORITY",
    "HIGH_TIER_MIN",
    "IMPORTANT_HERSCHEL_PRIORITY",
    "IMPORTANT_NGC_PRIORITY",
    "LabelPriorityTier",
    "MEDIUM_TIER_MIN",
    "MESSIER_PRIORITY",
    "ORDINARY_DSO_PRIORITY",
    "PROMINENT_DSO_PRIORITY",
    "STAR_BAYER_PRIORITY",
    "STAR_DESIGNATION_PRIORITY",
    "STAR_FLAMSTEED_PRIORITY",
    "STAR_MAIN_BAYER_PRIORITY",
    "STAR_NAME_PRIORITY",
    "base_label_priority",
    "dso_label_priority",
    "messier_id",
    "star_label_priority",
    "tier_for",
]

HERSCHEL_400 = "herschel400"

# Deep-sky anchors.
MESSIER_PRIORITY = 100
COMMON_NAME_PRIORITY = 90
PROMINENT_DSO_PRIORITY = 85
IMPORTANT_HERSCHEL_PRIORITY = 80
BRIGHT_DSO_PRIORITY = 60
HERSCHEL_PRIORITY = 60
IMPORTANT_NGC_PRIORITY = 55
ORDINARY_DSO_PRIORITY = 30
CATALOGUE_LABEL_PRIORITY = 15

# Star anchors.
STAR_NAME_PRIORITY = 85
STAR_MAIN_BAYER_PRIORITY = 75
STAR_BAYER_PRIORITY = 55
STAR_FLAMSTEED_PRIORITY = 50
STAR_DESIGNATION_PRIORITY = 20

# Tier boundaries on the shared numeric scale.
HIGH_TIER_MIN = 70
MEDIUM_TIER_MIN = 40

_MESSIER_PRIORITY = MESSIER_PRIORITY
_BRIGHT_MAGNITUDE = 9.0
_MAIN_STAR_MAGNITUDE = 3.0
_STAR_MANDATORY_MAGNITUDE = 2.0
_IMPORTANT_VISUAL_SCORE = 60.0
_PROMINENT_VISUAL_SCORE = 75.0


class LabelPriorityTier(StrEnum):
    """Behavioural tier of a label, derived from its numeric priority."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


def tier_for(priority: int) -> LabelPriorityTier:
    """Map a numeric label priority onto its behavioural tier."""
    if priority >= HIGH_TIER_MIN:
        return LabelPriorityTier.HIGH
    if priority >= MEDIUM_TIER_MIN:
        return LabelPriorityTier.MEDIUM
    return LabelPriorityTier.LOW


def messier_id(dso: DeepSkyObject) -> str | None:
    """Return the Messier designation of an object, if any."""
    for cross_id in dso.cross_ids:
        if cross_id.startswith("M") and cross_id[1:].isdigit():
            return cross_id
    return None


def base_label_priority(dso: DeepSkyObject) -> tuple[int, bool]:
    """Return the catalogue-only ``(priority, mandatory)`` for a DSO label.

    Only Messier objects and common-name objects are *mandatory*; a merely
    bright object is high priority but optional, so the optimizer may hide it
    rather than force an overlapping placement (``object visible != label
    visible``).
    """
    if messier_id(dso) is not None:
        return _MESSIER_PRIORITY, True
    if dso.common_name:
        return COMMON_NAME_PRIORITY, True
    if dso.magnitude is not None and dso.magnitude <= _BRIGHT_MAGNITUDE:
        return BRIGHT_DSO_PRIORITY, False
    return ORDINARY_DSO_PRIORITY, False


def dso_label_priority(
    dso: DeepSkyObject,
    *,
    memberships: frozenset[str] = frozenset(),
    forced: bool = False,
    visual_score: float = 0.0,
) -> int:
    """Return the label priority of a deep-sky object.

    ``visual_score`` is the 0-100 per-type visibility score.  Forced
    observing-list members and Herschel 400 objects are split by that score so
    the genuinely prominent ones outrank the merely catalogued ones, which is
    the central change from the earlier "all Herschel 400 are equal" rule.
    """
    if messier_id(dso) is not None:
        return MESSIER_PRIORITY
    if dso.common_name:
        return COMMON_NAME_PRIORITY
    if forced or HERSCHEL_400 in memberships:
        if visual_score >= _IMPORTANT_VISUAL_SCORE:
            return IMPORTANT_HERSCHEL_PRIORITY
        return HERSCHEL_PRIORITY
    if visual_score >= _PROMINENT_VISUAL_SCORE:
        return PROMINENT_DSO_PRIORITY
    if dso.magnitude is not None and dso.magnitude <= _BRIGHT_MAGNITUDE:
        return BRIGHT_DSO_PRIORITY
    if visual_score >= _IMPORTANT_VISUAL_SCORE:
        return IMPORTANT_NGC_PRIORITY
    return ORDINARY_DSO_PRIORITY


def star_label_priority(
    star: Star, star_name: StarName, designation_kind: str | None = None
) -> tuple[int, bool]:
    """Return ``(priority, mandatory)`` for a named/designated star.

    A proper name outranks a Bayer designation, which outranks Flamsteed and
    finally any other designation.  Only bright Bayer stars count as
    constellation main stars; a faint Bayer star is a medium-priority label.
    """
    if designation_kind == "combined" and star_name.proper_name_tier == "core":
        priority = 95
    elif designation_kind == "combined" and star_name.proper_name_tier == "standard":
        priority = 80
    elif designation_kind == "proper_core":
        priority = 95
    elif designation_kind == "proper_standard":
        priority = 80
    elif designation_kind == "proper_extended":
        priority = 30
    elif designation_kind == "variable":
        priority = 70
    elif designation_kind == "flamsteed":
        priority = 70 if star_name.preferred_designation == "flamsteed" else STAR_FLAMSTEED_PRIORITY
    elif designation_kind == "bayer":
        priority = 90 if star.magnitude <= _MAIN_STAR_MAGNITUDE else 65
    elif star_name.name:
        priority = STAR_NAME_PRIORITY
    elif star_name.bayer:
        if star.magnitude <= _MAIN_STAR_MAGNITUDE:
            priority = STAR_MAIN_BAYER_PRIORITY
        else:
            priority = STAR_BAYER_PRIORITY
    elif star_name.flamsteed:
        priority = STAR_FLAMSTEED_PRIORITY
    else:
        priority = STAR_DESIGNATION_PRIORITY
    mandatory = star.magnitude <= _STAR_MANDATORY_MAGNITUDE
    return priority, mandatory
