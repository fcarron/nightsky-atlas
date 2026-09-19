"""Page-space resolution of double/multiple star systems.

The astronomical overlay (WDS systems) and the star base are separate.  This
module is the single place where a system is turned into a **printed** decision:
a pair whose components are far enough apart on the paper is drawn as two real
star positions; a pair that would blend collapses to one star symbol carrying
the combined magnitude plus a short horizontal marker.

The decision is made on ``distance_on_page_mm`` (via the page transform), never
on a fixed angular separation, so the same systems behave consistently across
the Pocket, Standard and Deep scales (``AGENTS.md`` section 12).  The marker is a
cartographic symbol only and does not represent the real position angle.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from nightsky_atlas.atlas.config import StyleConfig
from nightsky_atlas.chart.page import PagePoint, PageTransform
from nightsky_atlas.render.symbols import StarSizeModel
from nightsky_atlas.scene.models import ChartScene

__all__ = [
    "DoubleStarMark",
    "PrintedStarObstacle",
    "printed_star_obstacles",
    "resolve_double_stars",
]


@dataclass(frozen=True, slots=True)
class DoubleStarMark:
    """A collapsed double/multiple star to be drawn as one symbol plus marker.

    ``suppress_star_ids`` are the stars the renderer must not draw normally
    (they are represented by this mark instead).  ``magnitude`` is the combined
    magnitude when known, otherwise the primary star's magnitude.
    """

    system_id: str
    page_point: PagePoint
    magnitude: float
    suppress_star_ids: frozenset[str]
    marker_length_mm: float
    marker_line_width_mm: float


@dataclass(frozen=True, slots=True)
class PrintedStarObstacle:
    id: str
    star_ids: frozenset[str]
    page_point: PagePoint
    magnitude: float
    collision_radius_mm: float


@dataclass(frozen=True, slots=True)
class _CollapsedRecord:
    """One WDS relation whose components are unresolvable on paper."""

    system_id: str
    member_star_ids: frozenset[str]
    combined_magnitude: float | None


def _page_distance_mm(a: PagePoint, b: PagePoint) -> float:
    return math.hypot(a.x_mm - b.x_mm, a.y_mm - b.y_mm)


def _connected_records(records: list[_CollapsedRecord]) -> tuple[tuple[_CollapsedRecord, ...], ...]:
    """Group records sharing any printed component into one visual system."""
    groups: list[list[_CollapsedRecord]] = []
    for record in sorted(records, key=lambda item: item.system_id):
        matching = [
            index
            for index, group in enumerate(groups)
            if record.member_star_ids & set().union(*(item.member_star_ids for item in group))
        ]
        if not matching:
            groups.append([record])
            continue
        merged = [record]
        for index in reversed(matching):
            merged.extend(groups.pop(index))
        groups.append(merged)
    return tuple(tuple(sorted(group, key=lambda item: item.system_id)) for group in groups)


def _group_magnitude(
    records: tuple[_CollapsedRecord, ...],
    member_star_ids: frozenset[str],
    magnitude_by_star: dict[str, float],
) -> float:
    """Return a combined magnitude without losing known unlinked companions."""
    flux = sum(10.0 ** (-0.4 * magnitude_by_star[star_id]) for star_id in member_star_ids)
    physical_magnitude = -2.5 * math.log10(flux)
    recorded = [
        record.combined_magnitude for record in records if record.combined_magnitude is not None
    ]
    return min((physical_magnitude, *recorded))


def resolve_double_stars(
    scene: ChartScene,
    transform: PageTransform,
    style: StyleConfig,
) -> tuple[DoubleStarMark, ...]:
    """Return the systems that must collapse to one symbol plus a marker.

    The decision is made **per pair**, not per system: a companion whose printed
    separation is below ``min_component_separation_mm`` collapses into the
    primary's marker, while a companion that is separable on the page is left at
    its real position.  Several WDS records can share one primary (A-B, A-C);
    every unseparable companion of that primary is folded into a single marker,
    so a close A-B pair is never printed as two stars just because A-C is wide
    (``AGENTS.md`` section 12).

    Only safe matches influence the chart.  A system is left alone when none of
    its components are unseparable or when the marking is disabled by style.
    """
    config = style.double_stars
    if not config.enabled or not scene.star_systems:
        return ()

    size_model = StarSizeModel.from_style(style.star)
    magnitude_by_star = {entry.star.id: entry.star.magnitude for entry in scene.stars}
    page_by_star = {
        entry.star.id: transform.to_page(entry.chart_point) for entry in scene.stars
    }

    records: list[_CollapsedRecord] = []
    for scene_system in scene.star_systems:
        system = scene_system.system
        if not system.is_safe_match:
            continue
        primary_id = system.primary_star_id
        if primary_id is None or primary_id not in magnitude_by_star:
            continue
        # Keep the chart selective: a system is worth a marker only when a
        # companion is actually plotted or its catalogued magnitude says it is
        # observable.  Unknown/faint companions are not marked.
        companion_observable = bool(scene_system.component_points) or (
            len(system.component_magnitudes) >= 2
            and system.component_magnitudes[1] <= config.companion_magnitude_limit
        )
        if not companion_observable:
            continue

        primary_page = page_by_star.get(primary_id)
        if primary_page is None:
            primary_page = transform.to_page(scene_system.chart_point)

        unseparable: set[str] = set()
        widest_unseparable_mm = 0.0
        for index, star_id in enumerate(system.component_star_ids):
            point = page_by_star.get(star_id)
            if point is not None:
                separation_mm = _page_distance_mm(primary_page, point)
            elif index == 0 and system.separation_arcsec is not None:
                separation_mm = system.separation_arcsec / 3600.0 * transform.mm_per_deg
            else:
                continue
            if separation_mm < config.min_component_separation_mm:
                # A WDS component may be just outside this chart or omitted by
                # the edition's magnitude limit.  It contributes semantic
                # double-star information, but cannot be suppressed or used as
                # a marker anchor because no printed star exists for it.
                if star_id in magnitude_by_star:
                    unseparable.add(star_id)
                widest_unseparable_mm = max(widest_unseparable_mm, separation_mm)

        if not unseparable and not system.component_star_ids:
            # The companion is not in the plotted star base; the catalogue
            # separation is all we have to decide whether to mark the primary.
            if system.separation_arcsec is None:
                continue
            separation_mm = system.separation_arcsec / 3600.0 * transform.mm_per_deg
            if separation_mm >= config.min_component_separation_mm:
                continue
            widest_unseparable_mm = separation_mm

        if not unseparable and widest_unseparable_mm == 0.0:
            continue

        records.append(
            _CollapsedRecord(
                system_id=system.id,
                member_star_ids=frozenset({primary_id, *unseparable}),
                combined_magnitude=system.combined_magnitude,
            )
        )

    marks: list[DoubleStarMark] = []
    for entries in _connected_records(records):
        suppress = frozenset(
            star_id
            for entry in entries
            for star_id in entry.member_star_ids
            if star_id in magnitude_by_star
        )
        if not suppress:
            continue
        anchor_id = min(
            suppress,
            key=lambda star_id: (magnitude_by_star[star_id], star_id),
        )
        magnitude = _group_magnitude(entries, suppress, magnitude_by_star)
        marker_length_mm = max(
            config.min_marker_length_mm,
            config.marker_length_factor * size_model.diameter_mm(magnitude),
        )
        marks.append(
            DoubleStarMark(
                system_id=entries[0].system_id,
                page_point=page_by_star[anchor_id],
                magnitude=magnitude,
                suppress_star_ids=suppress,
                marker_length_mm=marker_length_mm,
                marker_line_width_mm=config.marker_line_width_mm,
            )
        )
    return tuple(
        sorted(marks, key=lambda mark: (mark.page_point.x_mm, mark.page_point.y_mm, mark.system_id))
    )


def printed_star_obstacles(
    scene: ChartScene,
    transform: PageTransform,
    style: StyleConfig,
) -> tuple[PrintedStarObstacle, ...]:
    size_model = StarSizeModel.from_style(style.star)
    marks = resolve_double_stars(scene, transform, style)
    suppressed = frozenset(star_id for mark in marks for star_id in mark.suppress_star_ids)
    obstacles = [
        PrintedStarObstacle(
            id=entry.star.id,
            star_ids=frozenset((entry.star.id,)),
            page_point=transform.to_page(entry.chart_point),
            magnitude=entry.star.magnitude,
            collision_radius_mm=size_model.radius_mm(entry.star.magnitude),
        )
        for entry in scene.stars
        if entry.star.id not in suppressed
    ]
    obstacles.extend(
        PrintedStarObstacle(
            id=mark.system_id,
            star_ids=mark.suppress_star_ids,
            page_point=mark.page_point,
            magnitude=mark.magnitude,
            collision_radius_mm=max(
                size_model.radius_mm(mark.magnitude),
                (mark.marker_length_mm + mark.marker_line_width_mm) / 2.0,
            ),
        )
        for mark in marks
    )
    return tuple(obstacles)
