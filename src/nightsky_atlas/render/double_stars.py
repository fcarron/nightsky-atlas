"""Map-scale representation of selected WDS overlay pairs."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from nightsky_atlas.atlas.config import StyleConfig
from nightsky_atlas.catalog.wds_selection import pair_passes_profile
from nightsky_atlas.chart.page import PagePoint, PageTransform
from nightsky_atlas.render.symbols import StarSizeModel
from nightsky_atlas.scene.models import ChartScene

__all__ = [
    "DoubleStarMark",
    "MapResolution",
    "PrintedStarObstacle",
    "classify_map_resolution",
    "printed_star_obstacles",
    "related_member_star_ids",
    "resolve_double_stars",
    "source_member_star_ids",
]


class _SystemLinkedStar(Protocol):
    star_ids: frozenset[str]
    system_ids: frozenset[str]


class MapResolution(StrEnum):
    UNRESOLVED = "unresolved_on_map"
    MARGINAL = "marginally_resolved_on_map"
    RESOLVED = "clearly_resolved_on_map"


@dataclass(frozen=True, slots=True)
class DoubleStarMark:
    """One horizontal overlay marker attached to an existing base-catalogue star."""

    system_id: str
    page_point: PagePoint
    magnitude: float
    marker_length_mm: float
    marker_line_width_mm: float
    star_id: str | None = None
    system_ids: frozenset[str] = frozenset()
    pair_ids: tuple[str, ...] = ()
    suppress_star_ids: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class PrintedStarObstacle:
    id: str
    star_ids: frozenset[str]
    page_point: PagePoint
    magnitude: float
    collision_radius_mm: float
    disk_radius_mm: float | None = None
    system_ids: frozenset[str] = frozenset()
    marker_length_mm: float = 0.0
    marker_line_width_mm: float = 0.0

    @property
    def center(self) -> PagePoint:
        return self.page_point

    @property
    def radius_mm(self) -> float:
        return self.disk_radius_mm if self.disk_radius_mm is not None else self.collision_radius_mm


def classify_map_resolution(
    center_distance_mm: float,
    primary_radius_mm: float,
    secondary_radius_mm: float,
    style: StyleConfig,
) -> MapResolution:
    """Classify components from projected centre distance minus real glyph radii."""
    clearance = center_distance_mm - primary_radius_mm - secondary_radius_mm
    config = style.double_stars
    if clearance <= config.unresolved_clearance_mm:
        return MapResolution.UNRESOLVED
    if clearance <= config.marginal_clearance_mm:
        return MapResolution.MARGINAL
    return MapResolution.RESOLVED


def source_member_star_ids(
    target_id: str, obstacles: Iterable[_SystemLinkedStar]
) -> frozenset[str]:
    entries = tuple(obstacles)
    direct = tuple(entry for entry in entries if target_id in entry.star_ids)
    if direct:
        return frozenset(star_id for entry in direct for star_id in entry.star_ids)
    return frozenset(
        star_id for entry in entries if target_id in entry.system_ids for star_id in entry.star_ids
    )


def related_member_star_ids(
    target_id: str, obstacles: Iterable[_SystemLinkedStar]
) -> frozenset[str]:
    entries = tuple(obstacles)
    direct = tuple(entry for entry in entries if target_id in entry.star_ids)
    system_ids = (
        frozenset((target_id,))
        if any(target_id in entry.system_ids for entry in entries)
        else frozenset(system_id for entry in direct for system_id in entry.system_ids)
    )
    related = frozenset(
        star_id for entry in entries if system_ids & entry.system_ids for star_id in entry.star_ids
    )
    return related or source_member_star_ids(target_id, entries)


def _page_distance_mm(a: PagePoint, b: PagePoint) -> float:
    return math.hypot(a.x_mm - b.x_mm, a.y_mm - b.y_mm)


def resolve_double_stars(
    scene: ChartScene,
    transform: PageTransform,
    style: StyleConfig,
) -> tuple[DoubleStarMark, ...]:
    """Select WDS pairs, classify their printed separation, and aggregate markers.

    Astronomical selection is delegated to :mod:`catalog.wds_selection`. WDS
    never supplies a plotted component position: absent base stars remain absent.
    A selected unresolved pair marks its rendered primary; resolved and marginal
    pairs do not mark either component by virtue of that pair alone.
    """
    config = style.double_stars
    if not config.enabled or not scene.star_systems:
        return ()

    size_model = StarSizeModel.from_style(style.star)
    stars = {entry.star.id: entry for entry in scene.stars}
    page_by_star = {
        star_id: transform.to_page(entry.chart_point) for star_id, entry in stars.items()
    }
    systems_by_star: dict[str, set[str]] = defaultdict(set)
    marked_pairs: dict[str, list[str]] = defaultdict(list)

    for scene_system in scene.star_systems:
        system = scene_system.system
        if not system.is_safe_match or not pair_passes_profile(system, config):
            continue
        primary_id = system.primary_star_id
        if primary_id is None or primary_id not in stars:
            continue

        for linked_id in system.linked_star_ids():
            systems_by_star[linked_id].add(system.id)

        primary_page = page_by_star[primary_id]
        companion_id = system.component_star_ids[0] if system.component_star_ids else None
        companion_entry = stars.get(companion_id or "")
        if companion_entry is not None:
            companion_page = page_by_star[companion_entry.star.id]
            separation_mm = _page_distance_mm(primary_page, companion_page)
            secondary_magnitude = companion_entry.star.magnitude
        else:
            if system.separation_arcsec is None:
                continue
            separation_mm = system.separation_arcsec / 3600.0 * transform.mm_per_deg
            secondary_magnitude = system.secondary_magnitude
        if secondary_magnitude is None:
            continue

        resolution = classify_map_resolution(
            separation_mm,
            size_model.radius_mm(stars[primary_id].star.magnitude),
            size_model.radius_mm(secondary_magnitude),
            style,
        )
        if resolution is MapResolution.UNRESOLVED:
            marked_pairs[primary_id].append(system.id)

    marks = []
    for star_id, pairs in sorted(marked_pairs.items()):
        star = stars[star_id].star
        marker_length = max(
            config.min_marker_length_mm,
            config.marker_length_factor * size_model.diameter_mm(star.magnitude),
        )
        pair_ids = tuple(sorted(set(pairs)))
        marks.append(
            DoubleStarMark(
                system_id=pair_ids[0],
                star_id=star_id,
                page_point=page_by_star[star_id],
                magnitude=star.magnitude,
                marker_length_mm=marker_length,
                marker_line_width_mm=config.marker_line_width_mm,
                system_ids=frozenset(systems_by_star[star_id]),
                pair_ids=pair_ids,
            )
        )
    return tuple(marks)


def printed_star_obstacles(
    scene: ChartScene,
    transform: PageTransform,
    style: StyleConfig,
) -> tuple[PrintedStarObstacle, ...]:
    size_model = StarSizeModel.from_style(style.star)
    marks = {mark.star_id: mark for mark in resolve_double_stars(scene, transform, style)}
    systems_by_star: dict[str, set[str]] = defaultdict(set)
    for scene_system in scene.star_systems:
        system = scene_system.system
        if system.is_safe_match:
            for star_id in system.linked_star_ids():
                systems_by_star[star_id].add(system.id)

    obstacles = []
    for entry in scene.stars:
        star = entry.star
        page_point = transform.to_page(entry.chart_point)
        disk_radius = size_model.radius_mm(star.magnitude)
        mark = marks.get(star.id)
        marker_length = mark.marker_length_mm if mark else 0.0
        marker_width = mark.marker_line_width_mm if mark else 0.0
        obstacles.append(
            PrintedStarObstacle(
                id=star.id,
                star_ids=frozenset((star.id,)),
                system_ids=frozenset(systems_by_star[star.id]),
                page_point=page_point,
                magnitude=star.magnitude,
                collision_radius_mm=max(
                    disk_radius, (marker_length + marker_width) / 2.0
                ),
                disk_radius_mm=disk_radius,
                marker_length_mm=marker_length,
                marker_line_width_mm=marker_width,
            )
        )
    return tuple(obstacles)
