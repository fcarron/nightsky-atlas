"""Deterministic label selection before placement.

Whether an object is *drawn* and whether its label is *placed* are separate
decisions (``AGENTS.md`` sections 5 and 14).  This module implements the
selection stage of the pipeline:

    candidate labels -> priority scoring -> local density selection
        -> deterministic placement -> collision rejection

It does two things, in order, without any AI:

1. **Semantic de-duplication** -- the same physical object or the same printed
   name must not appear twice.  Catalogue aliases and duplicated star names are
   collapsed to one primary label, preferring the higher priority, then the
   brighter target, then the stable id.
2. **Local density selection** -- high-priority labels (Messier, prominent
   Herschel 400, proper-named and bright Bayer stars) are always kept; medium
   and low labels are kept only while the printed label area within a local
   neighbourhood stays under a tier budget.  This is a local rule, so sparse
   fields keep their labels and dense fields (Virgo) lose ordinary ones.

Selection is deterministic: candidates are ordered by ``(-priority, id)`` and
every comparison is total.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

from nightsky_atlas.atlas.config import StyleConfig
from nightsky_atlas.catalog.priority import LabelPriorityTier, tier_for
from nightsky_atlas.chart.page import PagePoint, PageTransform
from nightsky_atlas.layout.labels import constellation_label_anchors
from nightsky_atlas.layout.models import Label
from nightsky_atlas.scene.models import ChartScene

__all__ = ["select_labels"]


def select_labels(
    labels: Sequence[Label],
    scene: ChartScene,
    transform: PageTransform,
    style: StyleConfig,
    *,
    protected_ids: Iterable[str] = (),
) -> tuple[Label, ...]:
    """Return the subset of candidate labels that should be placed.

    ``protected_ids`` are labels a manual override refers to; they are always
    kept so the override contract (``AGENTS.md`` section 22) survives the
    selection pass.  The order of the input is preserved in the output.
    """
    selection = style.label.selection
    if not selection.enabled:
        return tuple(labels)

    anchors = _anchors(scene, transform, style)
    magnitudes = _magnitudes(scene)
    deduplicated = _remove_duplicates(labels, anchors, magnitudes)
    protected = set(protected_ids)
    # A constellation name is a single low-priority presentation element for a
    # whole stick figure, not one of the dense catalogue labels this stage is
    # intended to thin.  It still remains optional for the collision-aware
    # optimizer and AI action gate below.
    protected.update(
        label.id for label in labels if label.id.startswith("label:constellation:")
    )
    protected.update(
        f"label:dso:{scene_dso.dso.id}"
        for scene_dso in scene.deep_sky_objects
        if scene_dso.dso.object_type in selection.always_label_object_types
    )
    kept = _thin_by_density(deduplicated, anchors, style, protected_ids=protected)
    kept_ids = {label.id for label in kept}
    return tuple(label for label in labels if label.id in kept_ids)


def _anchors(
    scene: ChartScene, transform: PageTransform, style: StyleConfig
) -> dict[str, PagePoint]:
    anchors: dict[str, PagePoint] = {}
    for scene_star in scene.stars:
        anchors[scene_star.star.id] = transform.to_page(scene_star.chart_point)
    for scene_dso in scene.deep_sky_objects:
        anchors[scene_dso.dso.id] = transform.to_page(scene_dso.chart_point)
    for scene_system in scene.star_systems:
        anchors[scene_system.system.id] = transform.to_page(scene_system.chart_point)
    anchors.update(constellation_label_anchors(scene, transform, style))
    return anchors


def _magnitudes(scene: ChartScene) -> dict[str, float]:
    magnitudes: dict[str, float] = {}
    for scene_star in scene.stars:
        magnitudes[scene_star.star.id] = scene_star.star.magnitude
    for scene_dso in scene.deep_sky_objects:
        if scene_dso.dso.magnitude is not None:
            magnitudes[scene_dso.dso.id] = scene_dso.dso.magnitude
    return magnitudes


def _normalise_text(text: str) -> str:
    return " ".join(text.split()).casefold()


def _anchor_for(
    label: Label, anchors: dict[str, PagePoint]
) -> PagePoint:
    anchor = anchors.get(label.target_id)
    if anchor is not None:
        return anchor
    if label.candidates:
        return label.candidates[0].bounds.center
    return PagePoint(x_mm=0.0, y_mm=0.0)


def _label_area_mm2(label: Label) -> float:
    if not label.candidates:
        return 0.0
    bounds = label.candidates[0].bounds
    return max(0.0, bounds.width_mm) * max(0.0, bounds.height_mm)


def _prefer(candidate: Label, current: Label, magnitudes: dict[str, float]) -> bool:
    """Return whether ``candidate`` should replace ``current`` as the primary."""
    if candidate.priority != current.priority:
        return candidate.priority > current.priority
    candidate_mag = magnitudes.get(candidate.target_id, math.inf)
    current_mag = magnitudes.get(current.target_id, math.inf)
    if candidate_mag != current_mag:
        return candidate_mag < current_mag
    return candidate.id < current.id


def _remove_duplicates(
    labels: Sequence[Label],
    anchors: dict[str, PagePoint],
    magnitudes: dict[str, float],
) -> tuple[Label, ...]:
    """Collapse labels that print the same name onto one primary label."""
    chosen: dict[str, Label] = {}
    for label in labels:
        key = _normalise_text(label.text)
        if not key:
            continue
        current = chosen.get(key)
        if current is None or _prefer(label, current, magnitudes):
            chosen[key] = label
    kept_ids = {label.id for label in chosen.values()}
    return tuple(label for label in labels if label.id in kept_ids)


def _thin_by_density(
    labels: Sequence[Label],
    anchors: dict[str, PagePoint],
    style: StyleConfig,
    *,
    protected_ids: set[str],
) -> tuple[Label, ...]:
    """Keep high-tier labels and thin lower tiers by local printed density."""
    selection = style.label.selection
    radius_mm = selection.density_radius_mm
    radius_sq = radius_mm * radius_mm
    neighbourhood_area = math.pi * radius_sq
    budgets = {
        LabelPriorityTier.MEDIUM: selection.medium_density_budget,
        LabelPriorityTier.LOW: selection.low_density_budget,
    }

    ordered = sorted(labels, key=lambda label: (-label.priority, label.id))
    accepted: list[Label] = []
    accepted_anchors: list[PagePoint] = []
    accepted_areas: list[float] = []
    for label in ordered:
        anchor = _anchor_for(label, anchors)
        tier = tier_for(label.priority)
        if (
            tier is LabelPriorityTier.HIGH
            or label.mandatory
            or label.locked
            or label.id in protected_ids
        ):
            accepted.append(label)
            accepted_anchors.append(anchor)
            accepted_areas.append(_label_area_mm2(label))
            continue
        occupied = sum(
            area
            for area, other in zip(accepted_areas, accepted_anchors, strict=True)
            if _distance_sq(anchor, other) <= radius_sq
        )
        projected = (occupied + _label_area_mm2(label)) / neighbourhood_area
        if projected <= budgets[tier]:
            accepted.append(label)
            accepted_anchors.append(anchor)
            accepted_areas.append(_label_area_mm2(label))
    return tuple(accepted)


def _distance_sq(first: PagePoint, second: PagePoint) -> float:
    dx = first.x_mm - second.x_mm
    dy = first.y_mm - second.y_mm
    return dx * dx + dy * dy
