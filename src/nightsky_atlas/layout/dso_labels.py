"""Deep-sky label text and typographic tier.

This is a presentation layer, deliberately separate from the astronomical
model: catalogue identifiers are never rewritten, only rendered compactly
(``AGENTS.md`` sections 5 and 14.5).  The rules are:

- a bare number means NGC (``NGC 4565`` renders as ``4565``);
- Messier designations take priority and are bold at the normal size;
- non-Messier Herschel 400 objects are bold;
- IC numbers render as ``I3476``; other catalogues use short abbreviations.

Tier choice depends only on the object's designations and observing-list
membership, so the same object always formats identically.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from nightsky_atlas.atlas.config import DsoLabelStyle
from nightsky_atlas.catalog.models import DeepSkyObject
from nightsky_atlas.catalog.priority import HERSCHEL_400, messier_id

__all__ = [
    "HERSCHEL_400_LIST",
    "DsoLabelText",
    "DsoLabelTier",
    "format_catalog_designation",
    "format_dso_label",
    "label_tier",
    "primary_designation",
]

HERSCHEL_400_LIST = HERSCHEL_400

_WHITESPACE = re.compile(r"\s+")

_COMPACT_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^NGC0*(\d+)([A-Z]?)$"), r"\1\2"),
    (re.compile(r"^IC0*(\d+)([A-Z]?)$"), r"I\1\2"),
    (re.compile(r"^M(?:ESSIER)?0*(\d+)$"), r"M\1"),
    (re.compile(r"^SHARPLESS(?:2-?)?0*(\d+)$"), r"Sh2-\1"),
    (re.compile(r"^SH2-?0*(\d+)$"), r"Sh2-\1"),
    (re.compile(r"^LDN0*(\d+)([A-Z]?)$"), r"LDN \1\2"),
    (re.compile(r"^LBN0*(\d+)([A-Z]?)$"), r"LBN \1\2"),
    (re.compile(r"^VDB0*(\d+)([A-Z]?)$"), r"vdB \1\2"),
    (re.compile(r"^(?:CR|CL|COLLINDER)0*(\d+)$"), r"Cr \1"),
    (re.compile(r"^(?:BARNARD|B)0*(\d+)$"), r"B\1"),
    (re.compile(r"^(?:MELOTTE|MEL)0*(\d+)$"), r"Mel \1"),
    (re.compile(r"^STOCK0*(\d+)$"), r"Stock \1"),
    (re.compile(r"^ABELLPN0*(\d+)$"), r"Abell \1"),
    (re.compile(r"^ABELL0*(\d+)$"), r"Abell \1"),
    (re.compile(r"^(?:HICKSON(?:COMPACTGROUP)?|HCG)0*(\d+)$"), r"HCG \1"),
    (re.compile(r"^ARP0*(\d+)$"), r"Arp \1"),
)


class DsoLabelTier(StrEnum):
    """Visual tier of a deep-sky label."""

    MESSIER = "messier"
    HERSCHEL400 = "herschel400"
    NORMAL = "normal"


@dataclass(frozen=True, slots=True)
class DsoLabelText:
    """Formatted deep-sky label text plus its typographic tier."""

    text: str
    tier: DsoLabelTier
    size_factor: float
    weight: str


def format_catalog_designation(raw: str | None) -> str | None:
    """Render one catalogue identifier compactly.

    Recognised catalogues are abbreviated and zero-padded numbers reduced
    (``NGC 0456`` -> ``456``, ``IC 3476`` -> ``I3476``, ``Barnard 168`` ->
    ``B168``).  Unknown designations are returned stripped and unchanged so no
    information is lost.
    """
    if raw is None:
        return None
    token = raw.strip()
    if not token:
        return None
    compact = _WHITESPACE.sub("", token).upper()
    for pattern, replacement in _COMPACT_RULES:
        match = pattern.match(compact)
        if match is not None:
            return match.expand(replacement)
    return token


def primary_designation(dso: DeepSkyObject) -> str:
    """Choose the primary label designation: Messier, then NGC, then IC, then id."""
    messier = messier_id(dso)
    if messier is not None:
        return format_catalog_designation(messier) or messier
    candidates = (dso.id, *dso.cross_ids)
    for prefix in ("NGC", "IC"):
        for candidate in candidates:
            if _WHITESPACE.sub("", candidate).upper().startswith(prefix):
                formatted = format_catalog_designation(candidate)
                if formatted is not None:
                    return formatted
    if re.fullmatch(r"C0*\d+", dso.id, re.IGNORECASE):
        for candidate in sorted(dso.cross_ids):
            if re.fullmatch(r"(?:MEL|MELOTTE)\s*0*\d+", candidate, re.IGNORECASE):
                formatted = format_catalog_designation(candidate)
                if formatted is not None:
                    return formatted
        for candidate in sorted(dso.cross_ids):
            if re.fullmatch(r"C0*\d+", candidate, re.IGNORECASE):
                continue
            formatted = format_catalog_designation(candidate)
            if formatted is not None:
                return formatted
        if dso.common_name:
            return dso.common_name
    return format_catalog_designation(dso.id) or dso.id


def label_tier(dso: DeepSkyObject, memberships: frozenset[str] = frozenset()) -> DsoLabelTier:
    """Return the visual tier for an object; Messier always wins."""
    if messier_id(dso) is not None:
        return DsoLabelTier.MESSIER
    if HERSCHEL_400_LIST in memberships:
        return DsoLabelTier.HERSCHEL400
    return DsoLabelTier.NORMAL


def format_dso_label(
    dso: DeepSkyObject,
    style: DsoLabelStyle | None = None,
    *,
    memberships: frozenset[str] = frozenset(),
    include_common_name: bool = False,
) -> DsoLabelText:
    """Format a deep-sky label and resolve its typography from ``style``."""
    resolved = style if style is not None else DsoLabelStyle()
    tier = label_tier(dso, memberships)
    tier_style = getattr(resolved, tier.value)
    text = primary_designation(dso)
    if include_common_name:
        from nightsky_atlas.catalog.common_names import curated_common_name

        curated = curated_common_name(dso)
        if curated is not None and curated.name.casefold() != text.casefold():
            text = f"{text} · {curated.name}"
    return DsoLabelText(
        text=text,
        tier=tier,
        size_factor=tier_style.size_factor,
        weight=tier_style.weight,
    )
