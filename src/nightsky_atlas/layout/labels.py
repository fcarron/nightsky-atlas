"""Label construction from a scene.

Labels are built here, never inside the renderer (``AGENTS.md`` section 16).
Priority and mandatory status follow the conceptual ordering in section 14.3.
"""

from __future__ import annotations

from collections import defaultdict

from nightsky_atlas.atlas.config import StyleConfig
from nightsky_atlas.catalog.constellations import constellation_name
from nightsky_atlas.catalog.models import DeepSkyObject, Star
from nightsky_atlas.catalog.priority import (
    base_label_priority,
    star_label_priority,
)
from nightsky_atlas.catalog.star_names import StarName, hip_number
from nightsky_atlas.chart.page import PagePoint, PageTransform
from nightsky_atlas.layout.candidates import compass_candidates
from nightsky_atlas.layout.dso_labels import format_dso_label
from nightsky_atlas.layout.models import Label
from nightsky_atlas.render.double_stars import printed_star_obstacles
from nightsky_atlas.render.symbols import StarSizeModel, dso_symbol_extent
from nightsky_atlas.render.text import TextMeasurer
from nightsky_atlas.scene.models import ChartScene

__all__ = [
    "build_dso_labels",
    "build_labels",
    "build_star_labels",
    "build_constellation_labels",
    "constellation_label_anchors",
    "label_priority",
]


def label_priority(dso: DeepSkyObject) -> tuple[int, bool]:
    """Return the catalogue-only ``(priority, mandatory)`` for a DSO label."""
    return base_label_priority(dso)


def _exclusion_radius_mm(
    dso: DeepSkyObject, transform: PageTransform, style: StyleConfig
) -> float:
    """Return the label exclusion radius from the central symbol extent.

    This is exactly the same geometry the renderer draws and collision detects,
    so a label can never be placed inside a symbol it thinks is smaller.
    """
    extent = dso_symbol_extent(dso, mm_per_deg=transform.mm_per_deg, style=style)
    return extent.collision_radius_mm


def build_dso_labels(
    scene: ChartScene,
    transform: PageTransform,
    style: StyleConfig,
) -> tuple[Label, ...]:
    """Build one label per labelled deep-sky object in the scene.

    Label text is produced by :func:`~nightsky_atlas.layout.dso_labels.format_dso_label`
    and carries its own tier typography.  Faint objects beyond
    ``style.label.dso_label_magnitude_limit`` are still rendered but receive no
    label unless they are mandatory (Messier, common name, bright DSO), belong
    to an observing list, or their type is configured to always request one.
    """
    dso_labels = style.label.dso_labels
    measurers: dict[tuple[float, str], TextMeasurer] = {}

    def measurer_for(size_pt: float, weight: str) -> TextMeasurer:
        key = (round(size_pt, 4), weight)
        measurer = measurers.get(key)
        if measurer is None:
            measurer = TextMeasurer(style.label.font_family, size_pt, weight)
            measurers[key] = measurer
        return measurer

    limit = style.label.dso_label_magnitude_limit
    labels: list[Label] = []
    for scene_dso in scene.deep_sky_objects:
        dso = scene_dso.dso
        always_label = dso.object_type in style.label.selection.always_label_object_types
        memberships: frozenset[str] = frozenset()
        if scene_dso.metadata is not None:
            priority = scene_dso.metadata.label_priority
            mandatory = scene_dso.metadata.label_mandatory
            memberships = scene_dso.metadata.list_memberships
            has_membership = bool(memberships)
        else:
            priority, mandatory = label_priority(dso)
            has_membership = False
        if (
            limit is not None
            and not mandatory
            and not has_membership
            and not always_label
            and dso.magnitude is not None
            and dso.magnitude > limit
        ):
            continue
        formatted = format_dso_label(dso, dso_labels, memberships=memberships)
        size_pt = dso_labels.normal_size_pt * formatted.size_factor
        label_id = f"label:dso:{dso.id}"
        metrics = measurer_for(size_pt, formatted.weight).measure_mm(formatted.text)
        anchor = transform.to_page(scene_dso.chart_point)
        candidates = compass_candidates(
            label_id=label_id,
            metrics=metrics,
            anchor=anchor,
            exclusion_radius_mm=_exclusion_radius_mm(dso, transform, style),
            ring_count=style.label.candidate_rings,
            ring_gap_mm=style.label.ring_gap_mm,
        )
        labels.append(
            Label(
                id=label_id,
                target_id=dso.id,
                text=formatted.text,
                priority=priority,
                mandatory=mandatory,
                candidates=candidates,
                selected_candidate_id=candidates[0].id if candidates else None,
                font_size_pt=size_pt,
                font_weight=formatted.weight,
            )
        )
    return tuple(labels)


def _star_label_priority(star: Star, star_name: StarName) -> tuple[int, bool]:
    """Return ``(priority, mandatory)`` for a named/designated star.

    Delegates to the central priority scale so the star and deep-sky orderings
    cannot diverge.
    """
    return star_label_priority(star, star_name)


def build_star_labels(
    scene: ChartScene,
    transform: PageTransform,
    style: StyleConfig,
    star_names: dict[int, StarName],
) -> tuple[Label, ...]:
    """Build one label per named or designated bright star in the scene.

    Only stars brighter than ``style.star.label_magnitude_limit`` that resolve to
    a common name or a Bayer/Flamsteed/variable designation are labelled; stars
    without a human-readable designation are skipped (their stable ID is used
    elsewhere, not printed).  Star labels are optional except for the brightest
    named stars, so the optimizer may hide them in crowded fields.
    """
    if not star_names:
        return ()
    model = StarSizeModel.from_style(style.star)
    printed_obstacle_by_star = {
        star_id: obstacle
        for obstacle in printed_star_obstacles(scene, transform, style)
        for star_id in obstacle.star_ids
    }
    measurer = TextMeasurer(style.label.font_family, style.label.font_size_pt)
    limit = style.star.label_magnitude_limit
    labels: list[Label] = []
    for scene_star in scene.stars:
        star = scene_star.star
        if star.magnitude > limit:
            continue
        star_name = star_names.get(hip_number(star.hip_id))
        if star_name is None:
            continue
        text = star_name.display_text()
        if not text:
            continue
        label_id = f"label:star:{star.id}"
        metrics = measurer.measure_mm(text)
        obstacle = printed_obstacle_by_star.get(star.id)
        anchor = (
            obstacle.page_point
            if obstacle is not None
            else transform.to_page(scene_star.chart_point)
        )
        candidates = compass_candidates(
            label_id=label_id,
            metrics=metrics,
            anchor=anchor,
            exclusion_radius_mm=(
                obstacle.collision_radius_mm
                if obstacle is not None
                else model.radius_mm(star.magnitude)
            ),
            ring_count=style.label.candidate_rings,
            ring_gap_mm=style.label.ring_gap_mm,
        )
        priority, mandatory = _star_label_priority(star, star_name)
        labels.append(
            Label(
                id=label_id,
                target_id=star.id,
                text=text,
                priority=priority,
                mandatory=mandatory,
                candidates=candidates,
                selected_candidate_id=candidates[0].id if candidates else None,
            )
        )
    return tuple(labels)


def constellation_label_anchors(
    scene: ChartScene, transform: PageTransform, style: StyleConfig
) -> dict[str, PagePoint]:
    """Return deterministic printable anchors for visible constellation names.

    The anchor is derived solely from the projected stick-figure geometry.  It
    is intentionally shared by construction, selection and optimization so a
    constellation name is one normal layout element rather than a renderer
    decoration with separate placement rules.
    """
    config = style.constellation.names
    if not config.enabled:
        return {}
    points_by_constellation: dict[str, list[PagePoint]] = defaultdict(list)
    for segment in scene.constellation_lines:
        if segment.constellation_id:
            points_by_constellation[segment.constellation_id].extend(
                transform.to_page(point) for point in segment.points
            )

    rect = transform.chart_rect
    anchors: dict[str, PagePoint] = {}
    for constellation_id, points in sorted(points_by_constellation.items()):
        if len(points) < config.min_segments * 2:
            continue
        x_mm = sum(point.x_mm for point in points) / len(points)
        y_mm = sum(point.y_mm for point in points) / len(points)
        if rect.left_mm <= x_mm <= rect.right_mm and rect.top_mm <= y_mm <= rect.bottom_mm:
            anchors[f"constellation:{constellation_id}"] = PagePoint(x_mm=x_mm, y_mm=y_mm)
    return anchors


def build_constellation_labels(
    scene: ChartScene,
    transform: PageTransform,
    style: StyleConfig,
) -> tuple[Label, ...]:
    """Build optional, collision-aware labels for visible stick figures."""
    config = style.constellation.names
    if not config.enabled:
        return ()
    measurer = TextMeasurer(style.label.font_family, config.font_size_pt)
    labels: list[Label] = []
    for target_id, anchor in constellation_label_anchors(scene, transform, style).items():
        constellation_id = target_id.removeprefix("constellation:")
        label_id = f"label:constellation:{constellation_id}"
        metrics = measurer.measure_mm(constellation_name(constellation_id).upper())
        candidates = compass_candidates(
            label_id=label_id,
            metrics=metrics,
            anchor=anchor,
            exclusion_radius_mm=0.0,
            ring_count=style.label.candidate_rings,
            ring_gap_mm=style.label.ring_gap_mm,
        )
        labels.append(
            Label(
                id=label_id,
                target_id=target_id,
                text=constellation_name(constellation_id).upper(),
                priority=10,
                mandatory=False,
                candidates=candidates,
                selected_candidate_id=candidates[0].id if candidates else None,
                font_size_pt=config.font_size_pt,
            )
        )
    return tuple(labels)


def build_labels(
    scene: ChartScene,
    transform: PageTransform,
    style: StyleConfig,
    star_names: dict[int, StarName] | None = None,
) -> tuple[Label, ...]:
    """Build deep-sky, constellation and star labels for a scene.

    Deep-sky labels come first, then star labels; the optimizer reorders by
    priority, so the input order only aids deterministic tie-breaking.
    """
    dso_labels = build_dso_labels(scene, transform, style)
    constellation_labels = build_constellation_labels(scene, transform, style)
    if star_names is None:
        return dso_labels + constellation_labels
    return (
        dso_labels
        + constellation_labels
        + build_star_labels(scene, transform, style, star_names)
    )
