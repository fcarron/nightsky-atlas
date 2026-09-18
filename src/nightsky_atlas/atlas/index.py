"""Deterministic, edition-independent data for the printed atlas index."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from dataclasses import dataclass

from nightsky_atlas.atlas.config import EditionConfig
from nightsky_atlas.catalog.constellations import constellation_name
from nightsky_atlas.catalog.models import DeepSkyObject
from nightsky_atlas.catalog.priority import messier_id
from nightsky_atlas.chart.models import ChartDefinition
from nightsky_atlas.chart.presentation import presentation_from_edition
from nightsky_atlas.scene.models import SceneDso

__all__ = [
    "AtlasIndex",
    "ConstellationIndexEntry",
    "DsoIndexEntry",
    "build_atlas_index",
    "is_indexable_dso",
    "natural_designation_key",
]


@dataclass(frozen=True, slots=True)
class DsoIndexEntry:
    canonical_id: str
    designation: str
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
class AtlasIndex:
    dso_entries: tuple[DsoIndexEntry, ...]
    constellation_entries: tuple[ConstellationIndexEntry, ...]
    aliases: tuple[tuple[str, str], ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "dso_entries": [entry.to_dict() for entry in self.dso_entries],
            "constellation_entries": [entry.to_dict() for entry in self.constellation_entries],
            "aliases": [
                {"alias": alias, "canonical_id": canonical} for alias, canonical in self.aliases
            ],
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
    match = re.fullmatch(r"([A-Za-z]+)\s*(\d+)", dso.id)
    return f"{match.group(1).upper()} {int(match.group(2))}" if match else dso.id


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
    return dso.object_type.value.replace("_", " ").title()


def _angular_distance(chart: ChartDefinition, dso: DeepSkyObject) -> float:
    ra1, dec1, ra2, dec2 = map(
        math.radians, (chart.center_ra_deg, chart.center_dec_deg, dso.ra_deg, dso.dec_deg)
    )
    cosine = math.sin(dec1) * math.sin(dec2) + math.cos(dec1) * math.cos(dec2) * math.cos(ra1 - ra2)
    return math.acos(max(-1.0, min(1.0, cosine)))


def build_atlas_index(
    chart_dsos: dict[str, Iterable[SceneDso]],
    chart_constellations: dict[str, frozenset[str]],
    charts: tuple[ChartDefinition, ...],
    edition: EditionConfig,
) -> AtlasIndex:
    """Build all index content from the exact set of charts being published."""
    definitions = {chart.id: chart for chart in charts}
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
    for dso_id, dso in objects.items():
        chart_ids = sorted(
            locations[dso_id],
            key=lambda chart_id: (_angular_distance(definitions[chart_id], dso), chart_id),
        )
        chart_codes = tuple(
            presentation_from_edition(definitions[item], edition).chart_code for item in chart_ids
        )
        entries.append(
            DsoIndexEntry(
                dso_id,
                _canonical_designation(dso),
                _type_name(dso),
                dso.constellation or "",
                chart_codes[0],
                chart_codes[1:],
                (dso.common_name,) if dso.common_name else (),
                tuple(sorted(memberships.get(dso_id, set()))),
            )
        )
    constellation_entries = []
    abbreviations = {item for items in chart_constellations.values() for item in items if item}
    for abbreviation in sorted(abbreviations, key=lambda item: constellation_name(item).casefold()):
        codes = tuple(
            presentation_from_edition(chart, edition).chart_code
            for chart in charts
            if abbreviation in chart_constellations.get(chart.id, frozenset())
        )
        constellation_entries.append(
            ConstellationIndexEntry(constellation_name(abbreviation), abbreviation, codes)
        )
    return AtlasIndex(
        tuple(sorted(entries, key=lambda item: natural_designation_key(item.designation))),
        tuple(constellation_entries),
    )
