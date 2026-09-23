"""Deterministic geometry for exceptional source-to-label callouts."""

from __future__ import annotations

import math
from dataclasses import dataclass

from nightsky_atlas.atlas.config import StyleConfig
from nightsky_atlas.chart.page import PagePoint, PageTransform
from nightsky_atlas.layout.geometry import (
    clamp_point_to_rect,
    expand_rect,
    segment_intersects_rect,
    segments_intersect,
)
from nightsky_atlas.layout.models import Label
from nightsky_atlas.render.double_stars import printed_star_obstacles
from nightsky_atlas.render.symbols import dso_symbol_extent
from nightsky_atlas.scene.models import ChartScene

__all__ = ["LeaderLine", "leader_line_for", "resolve_leader_lines"]


@dataclass(frozen=True, slots=True)
class LeaderLine:
    label_id: str
    start: PagePoint
    end: PagePoint


def _distance_to_segment(point: PagePoint, start: PagePoint, end: PagePoint) -> float:
    dx = end.x_mm - start.x_mm
    dy = end.y_mm - start.y_mm
    length_sq = dx * dx + dy * dy
    if length_sq == 0.0:
        return math.hypot(point.x_mm - start.x_mm, point.y_mm - start.y_mm)
    along = max(
        0.0,
        min(1.0, ((point.x_mm - start.x_mm) * dx + (point.y_mm - start.y_mm) * dy) / length_sq),
    )
    return math.hypot(point.x_mm - start.x_mm - along * dx, point.y_mm - start.y_mm - along * dy)


def leader_line_for(
    label: Label,
    labels: tuple[Label, ...],
    scene: ChartScene,
    transform: PageTransform,
    style: StyleConfig,
) -> LeaderLine | None:
    """Return a legal symbol-to-label segment, or ``None`` if routing is unsafe."""
    config = style.label.leader_lines
    candidate = label.effective_candidate()
    if not config.enabled or label.hidden or candidate is None:
        return None
    dso_target = next(
        (item for item in scene.deep_sky_objects if item.dso.id == label.target_id), None
    )
    star_target = next(
        (
            obstacle
            for obstacle in printed_star_obstacles(scene, transform, style)
            if label.target_id in obstacle.star_ids
        ),
        None,
    )
    if dso_target is not None:
        anchor = transform.to_page(dso_target.chart_point)
        extent = dso_symbol_extent(
            dso_target.dso, mm_per_deg=transform.mm_per_deg, style=style
        )
        source_radius = extent.collision_radius_mm
    elif star_target is not None:
        anchor = star_target.page_point
        source_radius = star_target.collision_radius_mm
    else:
        return None
    near = clamp_point_to_rect(anchor, candidate.bounds)
    dx = near.x_mm - anchor.x_mm
    dy = near.y_mm - anchor.y_mm
    distance = math.hypot(dx, dy)
    if distance == 0.0:
        return None
    ux, uy = dx / distance, dy / distance
    start_offset = source_radius + config.symbol_gap_mm
    end_offset = distance - config.label_gap_mm
    length = end_offset - start_offset
    if length < config.min_length_mm or length > config.max_length_mm:
        return None
    start = PagePoint(anchor.x_mm + ux * start_offset, anchor.y_mm + uy * start_offset)
    end = PagePoint(anchor.x_mm + ux * end_offset, anchor.y_mm + uy * end_offset)

    for other in labels:
        if other.id == label.id or other.hidden:
            continue
        other_candidate = other.effective_candidate()
        if other_candidate is not None and segment_intersects_rect(
            start, end, expand_rect(other_candidate.bounds, 0.25)
        ):
            return None
    for star in printed_star_obstacles(scene, transform, style):
        if label.target_id in star.star_ids:
            continue
        if star.magnitude <= 6.0 and _distance_to_segment(
            star.page_point, start, end
        ) <= star.collision_radius_mm + 0.25:
            return None
    for other in scene.deep_sky_objects:
        if other.dso.id == label.target_id:
            continue
        point = transform.to_page(other.chart_point)
        other_extent = dso_symbol_extent(other.dso, mm_per_deg=transform.mm_per_deg, style=style)
        if _distance_to_segment(point, start, end) <= other_extent.collision_radius_mm + 0.25:
            return None
    return LeaderLine(label.id, start, end)


def resolve_leader_lines(
    labels: tuple[Label, ...],
    scene: ChartScene,
    transform: PageTransform,
    style: StyleConfig,
) -> tuple[LeaderLine, ...]:
    """Resolve only lines explicitly enabled in the serializable layout."""
    accepted: list[LeaderLine] = []
    for label in sorted(labels, key=lambda item: item.id):
        if not label.leader_line:
            continue
        line = leader_line_for(label, labels, scene, transform, style)
        if line is None or any(
            segments_intersect(line.start, line.end, other.start, other.end)
            for other in accepted
        ):
            continue
        accepted.append(line)
    return tuple(accepted)
