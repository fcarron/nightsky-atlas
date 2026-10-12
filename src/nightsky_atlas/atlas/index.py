"""Deterministic, edition-independent data for the printed atlas index."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from dataclasses import dataclass

from nightsky_atlas.atlas.config import EditionConfig
from nightsky_atlas.catalog.common_names import curated_common_name
from nightsky_atlas.catalog.constellations import constellation_name
from nightsky_atlas.catalog.faint_stars import FaintStar
from nightsky_atlas.catalog.models import DeepSkyObject, DsoType, Star
from nightsky_atlas.catalog.priority import messier_id
from nightsky_atlas.catalog.star_names import StarName, hip_number
from nightsky_atlas.chart.models import ChartDefinition
from nightsky_atlas.chart.presentation import presentation_from_edition
from nightsky_atlas.layout.dso_labels import preferred_catalogue_designation
from nightsky_atlas.scene.models import SceneDso

__all__ = [
    "AtlasIndex",
    "ConstellationIndexEntry",
    "DsoIndexEntry",
    "NamedStarIndexEntry",
    "build_atlas_index",
    "is_indexable_dso",
    "natural_designation_key",
]


@dataclass(frozen=True, slots=True)
class DsoIndexEntry:
    canonical_id: str
    designation: str
    ra_deg: float
    dec_deg: float
    object_type: str
    constellation: str
    primary_chart: str
    secondary_charts: tuple[str, ...] = ()
    common_names: tuple[str, ...] = ()
    list_memberships: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "canonical_id": self.canonical_id,
            "designation": self.designation,
            "ra_deg": self.ra_deg,
            "dec_deg": self.dec_deg,
            "object_type": self.object_type,
            "constellation": self.constellation,
            "primary_chart": self.primary_chart,
            "secondary_charts": list(self.secondary_charts),
            "common_names": list(self.common_names),
            "list_memberships": list(self.list_memberships),
        }


@dataclass(frozen=True, slots=True)
class ConstellationIndexEntry:
    name: str
    abbreviation: str
    chart_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "abbreviation": self.abbreviation,
            "chart_ids": list(self.chart_ids),
        }


@dataclass(frozen=True, slots=True)
class NamedStarIndexEntry:
    """A proper star name occurring in the exact atlas chart set."""

    canonical_id: str
    name: str
    designation: str
    constellation: str
    primary_chart: str
    secondary_charts: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "canonical_id": self.canonical_id,
            "name": self.name,
            "designation": self.designation,
            "constellation": self.constellation,
            "primary_chart": self.primary_chart,
            "secondary_charts": list(self.secondary_charts),
        }


@dataclass(frozen=True, slots=True)
class AtlasIndex:
    dso_entries: tuple[DsoIndexEntry, ...]
    constellation_entries: tuple[ConstellationIndexEntry, ...]
    aliases: tuple[tuple[str, str], ...] = ()
    named_star_entries: tuple[NamedStarIndexEntry, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "dso_entries": [entry.to_dict() for entry in self.dso_entries],
            "constellation_entries": [entry.to_dict() for entry in self.constellation_entries],
            "aliases": [
                {"alias": alias, "canonical_id": canonical} for alias, canonical in self.aliases
            ],
            "named_star_entries": [entry.to_dict() for entry in self.named_star_entries],
        }


def is_indexable_dso(scene_dso: SceneDso) -> bool:
    """Whether a rendered DSO belongs in this edition's index.

    The scene is the edition's selected render set.  This central gate keeps a
    later edition-specific reduction policy from diverging from render logic.
    """
    metadata = scene_dso.metadata
    return metadata is None or metadata.visible or metadata.forced


def _canonical_designation(dso: DeepSkyObject) -> str:
    if (messier := messier_id(dso)) is not None:
        return messier
    designation = preferred_catalogue_designation(dso)
    match = re.fullmatch(r"([A-Za-z]+)\s*(\d+)([A-Z]?)", designation)
    return (
        f"{match.group(1).upper()} {int(match.group(2))}{match.group(3)}" if match else designation
    )


def natural_designation_key(value: str) -> tuple[int, str, int, str]:
    """Order catalogue identifiers by catalogue, then numeric component."""
    match = re.fullmatch(r"([A-Za-z]+)\s*(\d+)", value)
    if match is None:
        return (9, value.casefold(), 0, value.casefold())
    catalogue = match.group(1).upper()
    return (
        {"M": 0, "NGC": 1, "IC": 2, "C": 3}.get(catalogue, 8),
        catalogue,
        int(match.group(2)),
        value.casefold(),
    )


def _type_name(dso: DeepSkyObject) -> str:
    if dso.object_type == DsoType.OTHER and dso.semantic_subtype == "star cloud":
        return "Star Cloud"
    if dso.object_type == DsoType.GALAXY_CLUSTER:
        subtype = (dso.semantic_subtype or "").lower()
        if subtype == "galaxy pair":
            return "Galaxy Pair"
        if subtype == "galaxy triplet" or "group" in subtype:
            return "Galaxy Group"
    return dso.object_type.value.replace("_", " ").title()


def _constellation_abbreviation(dso: DeepSkyObject) -> str:
    if dso.constellation in {"Se1", "Se2"}:
        return "Ser"
    return dso.constellation or ""


def _angular_distance(chart: ChartDefinition, ra_deg: float, dec_deg: float) -> float:
    ra1, dec1, ra2, dec2 = map(
        math.radians, (chart.center_ra_deg, chart.center_dec_deg, ra_deg, dec_deg)
    )
    cosine = math.sin(dec1) * math.sin(dec2) + math.cos(dec1) * math.cos(dec2) * math.cos(ra1 - ra2)
    return math.acos(max(-1.0, min(1.0, cosine)))


def _star_designation(entry: StarName) -> str:
    """Return a compact, stable companion designation for a proper name."""
    if entry.constellation:
        for value in (entry.bayer, entry.flamsteed, entry.variable):
            if value:
                return f"{value} {entry.constellation}"
    return entry.bayer or entry.flamsteed or entry.variable or ""


def _angular_distance_to_star(chart: ChartDefinition, star: Star) -> float:
    return _angular_distance(chart, star.ra_deg, star.dec_deg)


def build_atlas_index(
    chart_dsos: dict[str, Iterable[SceneDso]],
    chart_constellations: dict[str, frozenset[str]],
    charts: tuple[ChartDefinition, ...],
    edition: EditionConfig,
    chart_stars: dict[str, Iterable[Star | FaintStar]] | None = None,
    star_names: dict[int, StarName] | None = None,
    chart_label_targets: dict[str, frozenset[str]] | None = None,
    chart_code_by_id: dict[str, str] | None = None,
) -> AtlasIndex:
    """Build all index content from the exact set of charts being published."""
    definitions = {chart.id: chart for chart in charts}
    printed_labels = chart_label_targets or {}
    codes = chart_code_by_id or {}
    objects: dict[str, DeepSkyObject] = {}
    memberships: dict[str, set[str]] = {}
    locations: dict[str, set[str]] = {}
    for chart_id, scene_dsos in chart_dsos.items():
        for scene_dso in scene_dsos:
            if not is_indexable_dso(scene_dso):
                continue
            dso = scene_dso.dso
            objects.setdefault(dso.id, dso)
            locations.setdefault(dso.id, set()).add(chart_id)
            if scene_dso.metadata is not None:
                memberships.setdefault(dso.id, set()).update(scene_dso.metadata.list_memberships)
    entries: list[DsoIndexEntry] = []
    common_name_references: list[tuple[str, str]] = []
    for dso_id, dso in objects.items():
        curated = curated_common_name(dso)
        if curated is not None:
            common_name_references.append((curated.name, _canonical_designation(dso)))
        chart_ids = sorted(
            locations[dso_id],
            key=lambda chart_id: (
                dso_id not in printed_labels.get(chart_id, frozenset()),
                _angular_distance(definitions[chart_id], dso.ra_deg, dso.dec_deg),
                chart_id,
            ),
        )
        object_chart_codes = tuple(
            codes.get(item, presentation_from_edition(definitions[item], edition).chart_code)
            for item in chart_ids
        )
        entries.append(
            DsoIndexEntry(
                dso_id,
                _canonical_designation(dso),
                dso.ra_deg,
                dso.dec_deg,
                _type_name(dso),
                _constellation_abbreviation(dso),
                object_chart_codes[0],
                object_chart_codes[1:],
                (curated.name,) if curated is not None else (),
                tuple(sorted(memberships.get(dso_id, set()))),
            )
        )
    constellation_entries = []
    abbreviations = {item for items in chart_constellations.values() for item in items if item}
    for abbreviation in sorted(abbreviations, key=lambda item: constellation_name(item).casefold()):
        constellation_codes = tuple(
            presentation_from_edition(chart, edition).chart_code
            for chart in charts
            if abbreviation in chart_constellations.get(chart.id, frozenset())
        )
        constellation_entries.append(
            ConstellationIndexEntry(
                constellation_name(abbreviation), abbreviation, constellation_codes
            )
        )
    named_star_entries: list[NamedStarIndexEntry] = []
    if chart_stars and star_names:
        stars: dict[int, Star] = {}
        star_locations: dict[int, set[str]] = {}
        for chart_id, scene_stars in chart_stars.items():
            for star in scene_stars:
                if not isinstance(star, Star):
                    continue
                number = hip_number(star.hip_id)
                if number is None or number not in star_names or not star_names[number].name:
                    continue
                stars.setdefault(number, star)
                star_locations.setdefault(number, set()).add(chart_id)
        for number, star in stars.items():
            name = star_names[number]
            chart_ids = sorted(
                star_locations[number],
                key=lambda chart_id: (
                    star.id not in printed_labels.get(chart_id, frozenset()),
                    _angular_distance_to_star(definitions[chart_id], star),
                    chart_id,
                ),
            )
            star_chart_codes = tuple(
                codes.get(
                    item, presentation_from_edition(definitions[item], edition).chart_code
                )
                for item in chart_ids
            )
            named_star_entries.append(
                NamedStarIndexEntry(
                    f"HIP {number}",
                    name.name or "",
                    _star_designation(name),
                    name.constellation or "",
                    star_chart_codes[0],
                    star_chart_codes[1:],
                )
            )

    return AtlasIndex(
        tuple(sorted(entries, key=lambda item: natural_designation_key(item.designation))),
        tuple(constellation_entries),
        aliases=tuple(sorted(common_name_references, key=lambda item: item[0].casefold())),
        named_star_entries=tuple(
            sorted(named_star_entries, key=lambda item: (item.name.casefold(), item.canonical_id))
        ),
    )
