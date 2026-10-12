"""Label construction from a scene.

Labels are built here, never inside the renderer (``AGENTS.md`` section 16).
Priority and mandatory status follow the conceptual ordering in section 14.3.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import replace
from math import hypot

from nightsky_atlas.atlas.config import StyleConfig
from nightsky_atlas.catalog.common_names import curated_common_name
from nightsky_atlas.catalog.constellations import constellation_name
from nightsky_atlas.catalog.models import DeepSkyObject, Star
from nightsky_atlas.catalog.priority import (
    base_label_priority,
    star_label_priority,
)
from nightsky_atlas.catalog.star_names import StarName, hip_number
from nightsky_atlas.chart.page import PagePoint, PageRect, PageTransform
from nightsky_atlas.layout.association import (
    dso_source_geometries,
    source_edge_distance,
    source_extent_edge_distance,
)
from nightsky_atlas.layout.candidates import (
    CANDIDATE_DIRECTIONS_16,
    CANDIDATE_PREFERENCE,
    compass_candidates,
)
from nightsky_atlas.layout.dso_labels import format_dso_label
from nightsky_atlas.layout.models import Label
from nightsky_atlas.layout.scoring import star_rect_edge_distance_mm
from nightsky_atlas.render.double_stars import printed_star_obstacles
from nightsky_atlas.render.symbols import StarSizeModel, dso_symbol_extent
from nightsky_atlas.render.text import TextMeasurer
from nightsky_atlas.scene.models import ChartScene, SceneConstellationRegion

__all__ = [
    "build_dso_labels",
    "build_labels",
    "build_star_labels",
    "build_constellation_labels",
    "constellation_label_anchors",
    "constellation_visible_area_fractions",
    "label_priority",
]

_CONSTELLATION_LABEL_AREA_FRACTION = 0.15


def label_priority(dso: DeepSkyObject) -> tuple[int, bool]:
    """Return the catalogue-only ``(priority, mandatory)`` for a DSO label."""
    return base_label_priority(dso)


def _exclusion_radius_mm(dso: DeepSkyObject, transform: PageTransform, style: StyleConfig) -> float:
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
    placement_style = style.label.dso_placement
    positions = (
        CANDIDATE_DIRECTIONS_16
        if placement_style.candidate_directions == 16
        else CANDIDATE_PREFERENCE
    )
    outer_positions = (
        CANDIDATE_DIRECTIONS_16
        if placement_style.outer_candidate_directions == 16
        else CANDIDATE_PREFERENCE
    )
    positions_by_gap = tuple(
        positions if gap < placement_style.outer_candidate_start_gap_mm else outer_positions
        for gap in placement_style.candidate_edge_gaps_mm
    )
    sources = {source.id: source for source in dso_source_geometries(scene, transform, style)}
    anchors = {item.dso.id: transform.to_page(item.chart_point) for item in scene.deep_sky_objects}
    for scene_dso in scene.deep_sky_objects:
        dso = scene_dso.dso
        if scene_dso.label_visible is False:
            continue
        always_label = dso.object_type in style.label.selection.always_label_object_types
        always_label = always_label or scene_dso.label_visible is True
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
        anchor = anchors[dso.id]
        curated = curated_common_name(dso)
        include_common_name = bool(
            curated
            and (
                curated.show_in_all_editions
                or (dso_labels.common_name_display == "iconic" and curated.pocket_label)
            )
        )
        if include_common_name and not curated.show_in_all_editions:
            radius = dso_labels.common_name_neighbor_radius_mm
            nearby = sum(
                other_id != dso.id
                and hypot(other.x_mm - anchor.x_mm, other.y_mm - anchor.y_mm) < radius
                for other_id, other in anchors.items()
            )
            include_common_name = nearby <= dso_labels.common_name_max_neighbors
        formatted = format_dso_label(
            dso,
            dso_labels,
            memberships=memberships,
            include_common_name=include_common_name,
        )
        size_pt = dso_labels.normal_size_pt * formatted.size_factor
        label_id = f"label:dso:{dso.id}"
        metrics = measurer_for(size_pt, formatted.weight).measure_mm(formatted.text)
        source = sources.get(dso.id)
        exact_edge_distance = None
        approximate_edge_distance = None
        if source is not None:

            def edge_distance(bounds, glyphs, geometry=source):
                visible_bounds = _ink_envelope(glyphs, bounds)
                return source_edge_distance(geometry, visible_bounds)

            exact_edge_distance = edge_distance
            if not source.outline_paths:

                def approximate_distance(bounds, glyphs, geometry=source):
                    visible_bounds = _ink_envelope(glyphs, bounds)
                    return source_extent_edge_distance(geometry, visible_bounds)

                approximate_edge_distance = approximate_distance
        candidate_kwargs = dict(
            label_id=label_id,
            metrics=metrics,
            anchor=anchor,
            exclusion_radius_mm=_exclusion_radius_mm(dso, transform, style),
            exact_edge_gap_mm=(
                placement_style.candidate_edge_gaps_mm[0] if source is not None else None
            ),
            exact_edge_distance=exact_edge_distance,
            approximate_edge_distance=approximate_edge_distance,
            exact_edge_gaps_mm=(
                placement_style.candidate_edge_gaps_mm if source is not None else None
            ),
            positions=positions,
            positions_by_ring=positions_by_gap if source is not None else None,
            allowed_rect=transform.chart_rect,
            ring_count=1 if source is not None else style.label.candidate_rings,
            ring_gap_mm=style.label.ring_gap_mm,
        )
        candidates = compass_candidates(**candidate_kwargs)
        if not candidates:
            candidate_kwargs["allowed_rect"] = None
            candidates = tuple(
                replace(candidate, id=f"{candidate.id}:fallback")
                for candidate in compass_candidates(**candidate_kwargs)
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


def _ink_envelope(glyphs: tuple[PageRect, ...], fallback: PageRect) -> PageRect:
    if not glyphs:
        return fallback
    left = min(rect.left_mm for rect in glyphs)
    top = min(rect.top_mm for rect in glyphs)
    right = max(rect.right_mm for rect in glyphs)
    bottom = max(rect.bottom_mm for rect in glyphs)
    return PageRect(left, top, right - left, bottom - top)


def _star_label_priority(star: Star, star_name: StarName, kind: str) -> tuple[int, bool]:
    """Return ``(priority, mandatory)`` for a named/designated star.

    Delegates to the central priority scale so the star and deep-sky orderings
    cannot diverge.
    """
    return star_label_priority(star, star_name, kind)


def _star_semantic_key(star_name: StarName, text: str, kind: str) -> str:
    if kind.startswith("proper_") or kind == "combined":
        return f"star:name:{star_name.curated_name}"
    if kind == "bayer":
        return f"star:bayer:{star_name.full_bayer_designation}"
    if kind == "flamsteed":
        return f"star:flamsteed:{star_name.full_flamsteed_designation}"
    return f"star:variable:{text}"


def build_star_labels(
    scene: ChartScene,
    transform: PageTransform,
    style: StyleConfig,
    star_names: dict[int, StarName],
    required_hip_ids: Iterable[int] = (),
) -> tuple[Label, ...]:
    """Build one label per named or designated bright star in the scene.

    Only stars brighter than ``style.star.label_magnitude_limit`` that resolve to
    a common name or a Bayer/Flamsteed/variable designation are labelled; stars
    without a human-readable designation are skipped (their stable ID is used
    elsewhere, not printed). Selected labels are mandatory; collisions are
    reported rather than silently hiding a selected designation.
    """
    required = frozenset(required_hip_ids)
    if not star_names:
        if required:
            raise ValueError("required named-star labels need a star-name catalogue")
        return ()
    model = StarSizeModel.from_style(style.star)
    printed_obstacle_by_star = {
        star_id: obstacle
        for obstacle in printed_star_obstacles(scene, transform, style)
        for star_id in obstacle.star_ids
    }
    measurer = TextMeasurer(style.label.font_family, style.label.font_size_pt)
    policy = style.label.star_labels
    limit = max(
        style.star.label_magnitude_limit,
        policy.bayer.max_magnitude if policy.bayer.enabled else 0.0,
        policy.flamsteed.max_magnitude if policy.flamsteed.enabled else 0.0,
        policy.variables.max_magnitude if policy.variables.enabled else 0.0,
    )
    labels: list[Label] = []
    seen_hips: set[int] = set()
    found_required: set[int] = set()
    for scene_star in sorted(scene.stars, key=lambda item: (item.star.magnitude, item.star.id)):
        star = scene_star.star
        if not isinstance(star, Star):
            continue
        number = hip_number(star.hip_id)
        if number is None or number in seen_hips:
            continue
        star_name = star_names.get(number)
        if star_name is None:
            continue
        if number in required and star_name.name:
            text, kind = star_name.name, "proper_standard"
            found_required.add(number)
        else:
            if star.magnitude > limit:
                continue
            canonical = star_name.canonical_display_variant()
            if canonical is None:
                continue
            text, kind = canonical
            if not star_name.display_variant_enabled(
                kind,
                policy,
                star.magnitude,
                proper_magnitude_limit=style.star.label_magnitude_limit,
            ):
                continue
        seen_hips.add(number)
        semantic_key = (
            f"star:name:{star_name.name}"
            if number in required and star_name.name
            else _star_semantic_key(star_name, text, kind)
        )
        label_id = f"label:star:{star.id}"
        obstacle = printed_obstacle_by_star.get(star.id)
        anchor = (
            obstacle.page_point
            if obstacle is not None
            else transform.to_page(scene_star.chart_point)
        )
        candidate_kwargs = dict(
            label_id=label_id,
            metrics=measurer.measure_mm(text),
            anchor=anchor,
            exclusion_radius_mm=(
                obstacle.collision_radius_mm
                if obstacle is not None
                else model.radius_mm(star.magnitude)
            ),
            exact_edge_gap_mm=style.label.star_clearance.associated.preferred_min_mm,
            exact_edge_distance=(
                lambda bounds, glyph_bounds, source=obstacle: (
                    min(
                        star_rect_edge_distance_mm(source, rect)
                        for rect in (glyph_bounds or (bounds,))
                    )
                    if source is not None
                    else 0.0
                )
            ),
            allowed_rect=transform.chart_rect,
            ring_count=(
                policy.proper_name_candidate_rings
                if kind == "combined" or kind.startswith("proper_")
                else style.label.candidate_rings
            ),
            ring_gap_mm=(
                policy.candidate_ring_gap_mm
                if kind == "combined" or kind.startswith("proper_")
                else style.label.ring_gap_mm
            ),
        )
        candidates = compass_candidates(**candidate_kwargs)
        if not candidates:
            candidate_kwargs["allowed_rect"] = None
            candidates = tuple(
                replace(candidate, id=f"{candidate.id}:fallback")
                for candidate in compass_candidates(**candidate_kwargs)
            )
        priority, mandatory = _star_label_priority(star, star_name, kind)
        has_proper_name = kind == "combined" or kind.startswith("proper_")
        labels.append(
            Label(
                id=label_id,
                target_id=star.id,
                text=text,
                priority=priority,
                mandatory=(
                    number in required
                    or mandatory
                    or (has_proper_name and policy.proper_names_always_visible)
                ),
                candidates=candidates,
                selected_candidate_id=candidates[0].id if candidates else None,
                semantic_key=semantic_key,
            )
        )
    missing_required = sorted(required - found_required)
    if missing_required:
        missing_text = ", ".join(str(number) for number in missing_required)
        raise ValueError(
            f"required named-star HIP IDs are unavailable in the chart: {missing_text}"
        )
    return tuple(labels)


def constellation_visible_area_fractions(scene: ChartScene) -> dict[str, float]:
    """Return the projected sky-area fraction occupied by each constellation."""
    fractions: dict[str, float] = {}
    for region in scene.constellation_regions:
        fractions[region.constellation_id] = (
            fractions.get(region.constellation_id, 0.0) + region.visible_area_fraction
        )
    return fractions


def _constellation_ids_for_area(scene: ChartScene, minimum_fraction: float) -> set[str]:
    fractions = constellation_visible_area_fractions(scene)
    if not fractions:
        return set()
    largest = min(fractions, key=lambda item: (-fractions[item], item))
    return {
        constellation_id
        for constellation_id, fraction in fractions.items()
        if fraction >= minimum_fraction
    } | {largest}


def _forced_constellation_ids(scene: ChartScene) -> set[str]:
    return _constellation_ids_for_area(scene, _CONSTELLATION_LABEL_AREA_FRACTION)


def constellation_label_anchors(
    scene: ChartScene, transform: PageTransform, style: StyleConfig
) -> dict[str, PagePoint]:
    """Return deterministic anchors for significant visible constellation regions."""
    config = style.constellation.names
    if not config.enabled:
        return {}
    if scene.constellation_regions:
        eligible = _constellation_ids_for_area(scene, config.min_visible_area_fraction)
        regions = {
            region.constellation_id: region
            for region in scene.constellation_regions
            if region.constellation_id in eligible
        }
        return {
            f"constellation:{constellation_id}": transform.to_page(region.centroid)
            for constellation_id, region in sorted(regions.items())
        }
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
    forced = _forced_constellation_ids(scene)
    regions = {region.constellation_id: region for region in scene.constellation_regions}
    for target_id, anchor in constellation_label_anchors(scene, transform, style).items():
        constellation_id = target_id.removeprefix("constellation:")
        label_id = f"label:constellation:{constellation_id}"
        metrics = measurer.measure_mm(constellation_name(constellation_id).upper())
        candidates = compass_candidates(
            label_id=label_id,
            metrics=metrics,
            anchor=anchor,
            exclusion_radius_mm=0.0,
            allowed_rect=transform.chart_rect,
            ring_count=style.label.candidate_rings,
            ring_gap_mm=style.label.ring_gap_mm,
        )
        region = regions.get(constellation_id)
        if region is not None:
            interior = tuple(
                candidate
                for candidate in candidates
                if _candidate_center_inside_region(candidate.bounds.center, region, transform)
            )
            if interior:
                candidates = interior
        is_forced = constellation_id in forced
        labels.append(
            Label(
                id=label_id,
                target_id=target_id,
                text=constellation_name(constellation_id).upper(),
                priority=75 if is_forced else 10,
                mandatory=is_forced,
                candidates=candidates,
                selected_candidate_id=candidates[0].id if candidates else None,
                font_size_pt=config.font_size_pt,
            )
        )
    return tuple(labels)


def _candidate_center_inside_region(
    point: PagePoint,
    region: SceneConstellationRegion,
    transform: PageTransform,
) -> bool:
    chart_point = (
        (transform.center_page.x_mm - point.x_mm) / transform.mm_per_deg,
        (transform.center_page.y_mm - point.y_mm) / transform.mm_per_deg,
    )
    rings = [
        tuple((vertex.xi_deg, vertex.eta_deg) for vertex in ring)
        for ring in region.rings
    ]
    inside_outer = _point_in_ring(chart_point, rings[0])
    if region.complement:
        return not inside_outer
    return inside_outer and not any(_point_in_ring(chart_point, ring) for ring in rings[1:])


def _point_in_ring(point: tuple[float, float], ring: tuple[tuple[float, float], ...]) -> bool:
    x, y = point
    inside = False
    previous = ring[-1]
    for current in ring:
        x1, y1 = previous
        x2, y2 = current
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
        previous = current
    return inside


def build_labels(
    scene: ChartScene,
    transform: PageTransform,
    style: StyleConfig,
    star_names: dict[int, StarName] | None = None,
    required_star_hips: Iterable[int] = (),
) -> tuple[Label, ...]:
    """Build deep-sky, constellation and star labels for a scene.

    Deep-sky labels come first, then star labels; the optimizer reorders by
    priority, so the input order only aids deterministic tie-breaking.
    """
    dso_labels = build_dso_labels(scene, transform, style)
    constellation_labels = build_constellation_labels(scene, transform, style)
    if star_names is None:
        if tuple(required_star_hips):
            raise ValueError("required named-star labels need a star-name catalogue")
        return dso_labels + constellation_labels
    return (
        dso_labels
        + constellation_labels
        + build_star_labels(
            scene, transform, style, star_names, required_hip_ids=required_star_hips
        )
    )
