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
    preferred_designation: str | None = None

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
        """Legal text variants for this one physical star, in preferred order."""
        variants: list[tuple[str, str]] = []
        tier = self.proper_name_tier
        has_proper = bool(
            self.curated_name
            and tier in {"core", "standard", "extended"}
            and getattr(policy.proper_names, tier)
            and (proper_magnitude_limit is None or magnitude <= proper_magnitude_limit)
        )
        if has_proper:
            variants.append((self.curated_name, f"proper_{tier}"))
        bayer = (
            self.full_bayer_designation
            if policy.bayer.enabled and magnitude <= policy.bayer.max_magnitude
            else None
        )
        flamsteed = (
            self.full_flamsteed_designation
            if policy.flamsteed.enabled and magnitude <= policy.flamsteed.max_magnitude
            else None
        )
        selected_kind = (
            "flamsteed"
            if self.preferred_designation == "flamsteed" and flamsteed
            else "bayer" if bayer else "flamsteed" if flamsteed else None
        )
        if selected_kind is not None:
            full = bayer if selected_kind == "bayer" else flamsteed
            compact = self.bayer if selected_kind == "bayer" else self.flamsteed
            prefer_full = policy.constellation_suffix.default or (
                ambiguous and policy.constellation_suffix.allow_ambiguity_fallback
            )
            systematic = full if prefer_full else compact
            variants.append((systematic, selected_kind))
            if has_proper and policy.combined_names:
                variants.append((f"{self.curated_name} {systematic}", "combined"))
            if policy.constellation_suffix.allow_ambiguity_fallback and prefer_full:
                variants.append((compact, "compact_designation"))
        if (
            not has_proper
            and selected_kind is None
            and policy.variables.enabled
            and magnitude <= policy.variables.max_magnitude
            and self.curated_variable
        ):
            variants.append((self.curated_variable, "variable"))
        ranks = {
            "proper_core": 100,
            "proper_standard": 80,
            "proper_extended": 30,
            "bayer": 90 if magnitude <= 3.0 else 65,
            "flamsteed": 45,
            "variable": 70,
            "combined": 105 if tier in {"core", "standard"} else 10,
            "compact_designation": 5,
        }
        if self.preferred_designation:
            ranks[self.preferred_designation] = 110
        if (
            selected_kind is not None
            and ambiguous
            and policy.constellation_suffix.allow_ambiguity_fallback
        ):
            ranks[selected_kind] = 115
        variants.sort(key=lambda item: -ranks[item[1]])
        return tuple(variants)

    def display_components(
        self,
        policy: StarLabelStyle,
        magnitude: float,
        *,
        proper_magnitude_limit: float | None = None,
        ambiguous: bool = False,
    ) -> tuple[tuple[str, str], ...]:
        """Return the independently placeable labels selected by presentation policy."""
        variants = self.display_variants(
            policy,
            magnitude,
            proper_magnitude_limit=proper_magnitude_limit,
            ambiguous=ambiguous,
        )
        proper = next((item for item in variants if item[1].startswith("proper_")), None)
        systematic = next(
            (item for item in variants if item[1] in {"bayer", "flamsteed", "variable"}),
            None,
        )
        return tuple(item for item in (proper, systematic) if item is not None)

    def display_text(self) -> str | None:
        """Return the raw legacy fallback; map labels use ``display_variants``."""
        if self.name:
            return self.name
        if self.constellation:
            for designation in (self.bayer, self.flamsteed, self.variable):
                if designation:
                    return f"{designation} {self.constellation}"
        return self.bayer or self.flamsteed or self.variable or None


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
