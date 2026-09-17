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

__all__ = ["DoubleStarMark", "resolve_double_stars"]


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


def _page_distance_mm(a: PagePoint, b: PagePoint) -> float:
    return math.hypot(a.x_mm - b.x_mm, a.y_mm - b.y_mm)


def resolve_double_stars(
    scene: ChartScene,
    transform: PageTransform,
    style: StyleConfig,
) -> tuple[DoubleStarMark, ...]:
    """Return the systems that must collapse to one symbol plus a marker.

    Only safe matches influence the chart.  A system is left alone when its
    components are already separable on the page (they are plotted as normal
    stars at their real positions) or when the marking is disabled by style.
    """
    config = style.double_stars
    if not config.enabled or not scene.star_systems:
        return ()

    size_model = StarSizeModel.from_style(style.star)
    magnitude_by_star = {entry.star.id: entry.star.magnitude for entry in scene.stars}
    candidates: list[tuple[int, float, str, DoubleStarMark]] = []
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

        primary_page = transform.to_page(scene_system.chart_point)
        if scene_system.component_points:
            separation_mm = max(
                _page_distance_mm(primary_page, transform.to_page(point))
                for point in scene_system.component_points
            )
        elif system.separation_arcsec is not None:
            separation_mm = system.separation_arcsec / 3600.0 * transform.mm_per_deg
        else:
            separation_mm = 0.0

        if separation_mm >= config.min_component_separation_mm:
            continue

        magnitude = system.combined_magnitude
        if magnitude is None:
            magnitude = magnitude_by_star[primary_id]
        marker_length_mm = max(
            config.min_marker_length_mm,
            config.marker_length_factor * size_model.diameter_mm(magnitude),
        )
        mark = DoubleStarMark(
            system_id=system.id,
            page_point=primary_page,
            magnitude=magnitude,
            suppress_star_ids=frozenset(system.linked_star_ids()),
            marker_length_mm=marker_length_mm,
            marker_line_width_mm=config.marker_line_width_mm,
        )
        candidates.append(
            (len(system.component_star_ids), separation_mm, system.id, mark)
        )

    # A star can appear in several WDS records (A-B, A-C, Aa,Ab, ...).  Draw one
    # marker per star: prefer the record that links the most catalogued
    # companions, then the widest still-unseparable one, then the lowest ID.
    candidates.sort(key=lambda item: (-item[0], -item[1], item[2]))
    suppressed: set[str] = set()
    marks: list[DoubleStarMark] = []
    for _companion_count, _separation_mm, _system_id, mark in candidates:
        if mark.suppress_star_ids & suppressed:
            continue
        suppressed |= mark.suppress_star_ids
        marks.append(mark)
    return tuple(marks)