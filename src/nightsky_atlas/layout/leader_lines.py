"""Deterministic geometry for exceptional source-to-label callouts."""

from __future__ import annotations

import math
from dataclasses import dataclass

from nightsky_atlas.atlas.config import StyleConfig
from nightsky_atlas.chart.page import PagePoint, PageTransform
from nightsky_atlas.layout.association import (
    SourceGeometry,
    dso_source_geometries,
    source_facing_point,
)
from nightsky_atlas.layout.geometry import (
    clamp_point_to_rect,
    expand_rect,
    segment_intersects_rect,
    segments_intersect,
)
from nightsky_atlas.layout.models import Label
from nightsky_atlas.layout.scoring import star_rect_edge_distance_mm, star_source_facing_point
from nightsky_atlas.layout.text_geometry import candidate_ink_bounds
from nightsky_atlas.render.double_stars import (
    PrintedStarObstacle,
    printed_star_obstacles,
    related_member_star_ids,
)
from nightsky_atlas.render.symbols import dso_symbol_extent
from nightsky_atlas.scene.models import ChartScene

__all__ = [
    "LeaderLine",
    "LeaderRoutingContext",
    "leader_line_for",
    "prepare_leader_routing_context",
    "resolve_leader_lines",
]


@dataclass(frozen=True, slots=True)
class LeaderLine:
    label_id: str
    start: PagePoint
    end: PagePoint


@dataclass(frozen=True, slots=True)
class LeaderRoutingContext:
    dso_sources: tuple[SourceGeometry, ...]
    star_obstacles: tuple[PrintedStarObstacle, ...]
    dso_obstacles: tuple[tuple[str, PagePoint, float], ...]


def prepare_leader_routing_context(
    scene: ChartScene,
    transform: PageTransform,
    style: StyleConfig,
) -> LeaderRoutingContext:
    return LeaderRoutingContext(
        dso_sources=dso_source_geometries(scene, transform, style),
        star_obstacles=printed_star_obstacles(scene, transform, style),
        dso_obstacles=tuple(
            (
                other.dso.id,
                transform.to_page(other.chart_point),
                dso_symbol_extent(
                    other.dso,
                    mm_per_deg=transform.mm_per_deg,
                    style=style,
                ).collision_radius_mm,
            )
            for other in scene.deep_sky_objects
        ),
    )


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
    *,
    context: LeaderRoutingContext | None = None,
) -> LeaderLine | None:
    """Return a legal symbol-to-label segment, or ``None`` if routing is unsafe."""
    config = style.label.leader_lines
    candidate = label.effective_candidate()
    if not config.enabled or label.hidden or candidate is None:
        return None
    if context is None:
        context = prepare_leader_routing_context(scene, transform, style)
    dso_target = next(
        (
            source
            for source in context.dso_sources
            if source.id == label.target_id
        ),
        None,
    )
    star_obstacles = context.star_obstacles
    star_targets = tuple(
        obstacle
        for obstacle in star_obstacles
        if label.target_id in obstacle.star_ids or label.target_id in obstacle.system_ids
    )
    star_target = min(
        star_targets,
        key=lambda obstacle: star_rect_edge_distance_mm(obstacle, candidate.bounds),
        default=None,
    )
    label_bounds = (
        candidate_ink_bounds(candidate)
        if label.id.startswith("label:dso:")
        else candidate.bounds
    )
    if dso_target is not None:
        source_point = source_facing_point(dso_target, label_bounds)
        anchor = source_point
        source_offset = config.symbol_gap_mm
    elif star_target is not None:
        anchor = star_source_facing_point(star_target, candidate.bounds)
        source_offset = config.symbol_gap_mm
    else:
        return None
    near = clamp_point_to_rect(anchor, label_bounds)
    dx = near.x_mm - anchor.x_mm
    dy = near.y_mm - anchor.y_mm
    distance = math.hypot(dx, dy)
    if distance == 0.0:
        return None
    ux, uy = dx / distance, dy / distance
    start_offset = source_offset
    end_offset = distance - config.label_gap_mm
    length = end_offset - start_offset
    minimum_length = config.dso_min_length_mm if dso_target is not None else config.min_length_mm
    if length < minimum_length or length > config.max_length_mm:
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
    related_star_ids = related_member_star_ids(label.target_id, star_obstacles)
    for star in star_obstacles:
        if related_star_ids & star.star_ids:
            continue
        if star.magnitude <= 6.0 and _distance_to_segment(
            star.page_point, start, end
        ) <= star.collision_radius_mm + 0.25:
            return None
    for other_id, point, radius in context.dso_obstacles:
        if other_id == label.target_id:
            continue
        if _distance_to_segment(point, start, end) <= radius + 0.25:
            return None
    return LeaderLine(label.id, start, end)


def resolve_leader_lines(
    labels: tuple[Label, ...],
    scene: ChartScene,
    transform: PageTransform,
    style: StyleConfig,
    *,
    context: LeaderRoutingContext | None = None,
) -> tuple[LeaderLine, ...]:
    """Resolve only lines explicitly enabled in the serializable layout."""
    accepted: list[LeaderLine] = []
    if context is None and any(label.leader_line for label in labels):
        context = prepare_leader_routing_context(scene, transform, style)
    for label in sorted(labels, key=lambda item: item.id):
        if not label.leader_line:
            continue
        line = leader_line_for(label, labels, scene, transform, style, context=context)
        if line is None or any(
            segments_intersect(line.start, line.end, other.start, other.end)
            for other in accepted
        ):
            continue
        accepted.append(line)
    return tuple(accepted)
