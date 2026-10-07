"""Star names and designations used for star labels.

Labels for bright stars need human-readable designations, not catalogue
numbers. This module joins d3-celestial cross-identifications (BSD-3-Clause)
and an editorial IAU-checked name selection by stable Hipparcos number.

Names are presentation state, not astronomical facts (``AGENTS.md`` section 5),
so they live in a lookup here rather than on the immutable :class:`Star`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from nightsky_atlas.atlas.config import StarLabelStyle

__all__ = ["CATALOGUE", "VERSION", "DEFAULT_FIXTURE_DIR", "FILENAME", "StarName", "load_star_names"]

CATALOGUE = "d3-celestial"
VERSION = "master"
DEFAULT_FIXTURE_DIR = Path("data/fixtures/starnames")
FILENAME = "starnames.json"
CURATED_FILENAME = "curated.yaml"
_BAYER = re.compile(r"^[α-ω][0-9]?$", re.UNICODE)
_FLAMSTEED = re.compile(r"^[1-9][0-9]{0,2}$")


@dataclass(frozen=True, slots=True)
class StarName:
    """Named/designated identity of a Hipparcos star."""

    hip_number: int
    name: str | None = None
    bayer: str | None = None
    flamsteed: str | None = None
    variable: str | None = None
    constellation: str | None = None
    curated_name: str | None = None
    proper_name_tier: str | None = None
    curated_variable: str | None = None
    variable_marker: bool = False
    preferred_designation: str | None = None

    def canonical_display_variant(self) -> tuple[str, str] | None:
        """Return this star's edition-independent chart label and category."""
        if self.curated_name and self.proper_name_tier in {"core", "standard"}:
            return self.curated_name, f"proper_{self.proper_name_tier}"
        if self.bayer and _BAYER.fullmatch(self.bayer):
            return self.bayer, "bayer"
        if self.flamsteed and _FLAMSTEED.fullmatch(self.flamsteed):
            return self.flamsteed, "flamsteed"
        variable = self.curated_variable or self.variable
        if variable:
            return variable, "variable"
        return None

    def display_variant_enabled(
        self,
        kind: str,
        policy: StarLabelStyle,
        magnitude: float,
        *,
        proper_magnitude_limit: float,
    ) -> bool:
        """Return whether an edition permits this canonical label category."""
        if kind.startswith("proper_"):
            tier = kind.removeprefix("proper_")
            return getattr(policy.proper_names, tier, False) and magnitude <= proper_magnitude_limit
        designation = {
            "bayer": policy.bayer,
            "flamsteed": policy.flamsteed,
            "variable": policy.variables,
        }.get(kind)
        return (
            designation is not None
            and designation.enabled
            and magnitude <= designation.max_magnitude
        )

    @property
    def full_bayer_designation(self) -> str | None:
        if self.bayer and self.constellation and _BAYER.fullmatch(self.bayer):
            return f"{self.bayer} {self.constellation}"
        return None

    @property
    def full_flamsteed_designation(self) -> str | None:
        if self.flamsteed and self.constellation and _FLAMSTEED.fullmatch(self.flamsteed):
            return f"{self.flamsteed} {self.constellation}"
        return None

    def display_variants(
        self,
        policy: StarLabelStyle,
        magnitude: float,
        *,
        proper_magnitude_limit: float | None = None,
        ambiguous: bool = False,
    ) -> tuple[tuple[str, str], ...]:
        """Compatibility wrapper around the canonical, edition-independent label."""
        canonical = self.canonical_display_variant()
        if canonical is None:
            return ()
        allowed = self.display_variant_enabled(
            canonical[1],
            policy,
            magnitude,
            proper_magnitude_limit=(
                float("inf") if proper_magnitude_limit is None else proper_magnitude_limit
            ),
        )
        return (canonical,) if allowed else ()

    def display_text(self) -> str | None:
        """Return the same canonical text used by chart labels."""
        variant = self.canonical_display_variant()
        return variant[0] if variant is not None else None


def hip_number(hip_id: str | None) -> int | None:
    """Parse ``"HIP 102098"`` into its numeric Hipparcos number."""
    if not hip_id:
        return None
    parts = hip_id.replace("\u2009", " ").split()
    for part in reversed(parts):
        if part.isdigit():
            return int(part)
    return None


def load_star_names(
    directory: str | Path = DEFAULT_FIXTURE_DIR,
) -> dict[int, StarName]:
    """Load the vendored star-name fixture as a Hipparcos-number lookup."""
    path = Path(directory) / FILENAME
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid star name JSON {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"star name JSON root must be an object: {path}")

    names: dict[int, StarName] = {}
    for key, entry in data.items():
        if not isinstance(entry, dict):
            raise ValueError(f"malformed star name entry for {key!r} in {path}")
        number = _parse_key(key, path)
        names[number] = StarName(
            hip_number=number,
            name=_optional_str(entry.get("name")),
            bayer=_optional_str(entry.get("bayer")),
            flamsteed=_optional_str(entry.get("flam")),
            variable=_optional_str(entry.get("var")),
            constellation=_optional_str(entry.get("c")),
        )
    curated_path = Path(directory) / CURATED_FILENAME
    if curated_path.exists():
        _merge_curation(names, curated_path)
    return names


def _merge_curation(names: dict[int, StarName], path: Path) -> None:
    from dataclasses import replace

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) != {
        "source",
        "proper_names",
        "variables",
        "variable_markers",
        "preferred_designations",
    }:
        raise ValueError(f"invalid curated star-label root: {path}")
    tiers = data["proper_names"]
    if not isinstance(tiers, dict) or set(tiers) != {"core", "standard", "extended"}:
        raise ValueError(f"invalid proper-name tiers: {path}")
    seen_names: set[str] = set()
    seen_hips: set[int] = set()
    for tier, entries in tiers.items():
        for entry in entries:
            hip, name = int(entry["hip"]), str(entry["name"])
            if hip in seen_hips or name.casefold() in seen_names:
                raise ValueError(f"duplicate curated name or HIP: {name} ({hip})")
            seen_hips.add(hip)
            seen_names.add(name.casefold())
            if hip not in names:
                raise ValueError(f"curated HIP {hip} absent from star-name fixture")
            names[hip] = replace(names[hip], curated_name=name, proper_name_tier=tier)
    for entry in data["variables"]:
        hip, designation = int(entry["hip"]), str(entry["designation"])
        if hip not in names or not re.fullmatch(r"[A-Z]{1,2} [A-Za-z]{3}", designation):
            raise ValueError(f"invalid curated variable: {entry}")
        names[hip] = replace(names[hip], curated_variable=designation)
    seen_variable_markers: set[int] = set()
    for entry in data["variable_markers"]:
        hip = int(entry["hip"])
        designation = str(entry["designation"]).strip()
        if hip in seen_variable_markers:
            raise ValueError(f"duplicate curated variable marker HIP: {hip}")
        if not designation:
            raise ValueError(f"invalid curated variable marker: {entry}")
        seen_variable_markers.add(hip)
        names.setdefault(hip, StarName(hip_number=hip))
        names[hip] = replace(names[hip], variable_marker=True)
    for entry in data["preferred_designations"]:
        hip, kind = int(entry["hip"]), str(entry["kind"])
        if hip not in names or kind not in {"bayer", "flamsteed", "variable"}:
            raise ValueError(f"invalid preferred designation: {entry}")
        names[hip] = replace(names[hip], preferred_designation=kind)


def _parse_key(key: Any, path: Path) -> int:
    try:
        return int(str(key))
    except ValueError as exc:
        raise ValueError(f"non-numeric Hipparcos key {key!r} in {path}") from exc


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
