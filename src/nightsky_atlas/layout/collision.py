"""Hard label collision checks.

Every issue carries a stable ID so it can be referenced by layout diffs,
reviews and regression tests (``AGENTS.md`` section 14.4).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from nightsky_atlas.atlas.config import StyleConfig
from nightsky_atlas.chart.page import PageRect, PageTransform
from nightsky_atlas.layout.geometry import (
    circle_intersects_rect,
    circle_rect_edge_distance_mm,
    rects_overlap,
)
from nightsky_atlas.layout.leader_lines import resolve_leader_lines
from nightsky_atlas.layout.models import Label, LabelCandidate
from nightsky_atlas.layout.scoring import foreign_star_hard_min_mm
from nightsky_atlas.render.double_stars import printed_star_obstacles
from nightsky_atlas.render.symbols import dso_symbol_extent
from nightsky_atlas.scene.models import ChartScene

__all__ = [
    "IssueType",
    "LayoutIssue",
    "find_hard_violations",
    "placed_candidates",
]

class IssueType(StrEnum):
    """Categories of hard layout violation."""

    LABEL_LABEL = "label_label"
    LABEL_PAGE = "label_page"
    LABEL_STAR = "label_star"
    LABEL_DSO = "label_dso"
    FURNITURE_OVERLAP = "furniture_overlap"
    INVALID_SELECTION = "invalid_selection"
    MISSING_CANDIDATE = "missing_candidate"
    DUPLICATE_LABEL_ID = "duplicate_label_id"
    UNKNOWN_TARGET = "unknown_target"
    INVALID_LEADER_LINE = "invalid_leader_line"


@dataclass(frozen=True, slots=True)
class LayoutIssue:
    """A single hard layout violation with a stable ID."""

    id: str
    issue_type: IssueType
    element_ids: tuple[str, ...]
    message: str


def placed_candidates(labels: tuple[Label, ...]) -> list[tuple[Label, LabelCandidate]]:
    """Return the effectively placed candidate for every label.

    Uses :meth:`Label.effective_candidate`, the same definition the renderer
    and optimizer use, so validation checks exactly what would be printed.
    """
    placed: list[tuple[Label, LabelCandidate]] = []
    for label in labels:
        if label.hidden:
            continue
        candidate = label.effective_candidate()
        if candidate is not None:
            placed.append((label, candidate))
    return placed


def _issue(
    issue_type: IssueType, element_ids: tuple[str, ...], message: str
) -> LayoutIssue:
    return LayoutIssue(
        id=f"issue:{issue_type.value}:{':'.join(sorted(element_ids))}",
        issue_type=issue_type,
        element_ids=element_ids,
        message=message,
    )


def find_hard_violations(
    labels: tuple[Label, ...],
    scene: ChartScene,
    transform: PageTransform,
    style: StyleConfig,
    *,
    furniture: Iterable[PageRect] = (),
) -> tuple[LayoutIssue, ...]:
    """Return all hard label violations for a layout.

    ``furniture`` holds the mandatory page-furniture rectangles (title,
    navigation, scale bar, legend) that a label must never overlap
    (``AGENTS.md`` sections 14.4 and 15.1).  It defaults to empty so callers
    that only exercise sky collisions can omit it.
    """
    issues: list[LayoutIssue] = []
    furniture_rects = tuple(furniture)

    known_targets = {entry.star.id for entry in scene.stars}
    known_targets.update(entry.dso.id for entry in scene.deep_sky_objects)
    known_targets.update(entry.system.id for entry in scene.star_systems)
    known_targets.update(
        f"constellation:{segment.constellation_id}"
        for segment in scene.constellation_lines
        if segment.constellation_id
    )

    id_counts = Counter(label.id for label in labels)
    first_by_id: dict[str, Label] = {}
    for label in labels:
        first_by_id.setdefault(label.id, label)
    for label_id, label in sorted(first_by_id.items()):
        if id_counts[label_id] > 1:
            issues.append(
                _issue(
                    IssueType.DUPLICATE_LABEL_ID,
                    (label_id,),
                    f"label id {label_id} appears {id_counts[label_id]} times",
                )
            )
        if label.target_id not in known_targets:
            issues.append(
                _issue(
                    IssueType.UNKNOWN_TARGET,
                    (label.id,),
                    f"{label.id} references unknown target {label.target_id!r}",
                )
            )

    for label in labels:
        if label.hidden:
            continue
        if label.selected_candidate_id is not None and label.selected_candidate() is None:
            issues.append(
                _issue(
                    IssueType.INVALID_SELECTION,
                    (label.id,),
                    f"{label.id} selects unknown candidate {label.selected_candidate_id!r}",
                )
            )
        if not label.candidates and label.mandatory:
            issues.append(
                _issue(
                    IssueType.MISSING_CANDIDATE,
                    (label.id,),
                    f"mandatory label {label.id} has no candidates",
                )
            )

    placed = placed_candidates(labels)
    legal_lines = {
        line.label_id for line in resolve_leader_lines(labels, scene, transform, style)
    }
    for label in labels:
        if label.leader_line and label.id not in legal_lines:
            issues.append(
                _issue(
                    IssueType.INVALID_LEADER_LINE,
                    (label.id,),
                    f"{label.id} has no legal leader-line route",
                )
            )
    printable = PageRect(
        left_mm=transform.page.margin_mm,
        top_mm=transform.page.margin_mm,
        width_mm=transform.page.printable_width_mm,
        height_mm=transform.page.printable_height_mm,
    )

    for label, candidate in placed:
        bounds = candidate.bounds
        if (
            bounds.left_mm < printable.left_mm
            or bounds.top_mm < printable.top_mm
            or bounds.right_mm > printable.right_mm
            or bounds.bottom_mm > printable.bottom_mm
        ):
            issues.append(
                _issue(
                    IssueType.LABEL_PAGE,
                    (label.id, candidate.id),
                    f"{label.id} at {candidate.position.value} falls outside the printable area",
                )
            )

    for label, candidate in placed:
        for index, obstacle in enumerate(furniture_rects):
            if rects_overlap(candidate.bounds, obstacle):
                issues.append(
                    _issue(
                        IssueType.FURNITURE_OVERLAP,
                        (label.id, f"furniture:{index}"),
                        f"{label.id} overlaps mandatory page furniture",
                    )
                )

    for index, (label_a, candidate_a) in enumerate(placed):
        for label_b, candidate_b in placed[index + 1 :]:
            if rects_overlap(candidate_a.bounds, candidate_b.bounds):
                issues.append(
                    _issue(
                        IssueType.LABEL_LABEL,
                        (label_a.id, label_b.id),
                        f"labels {label_a.id} and {label_b.id} overlap",
                    )
                )

    star_obstacles = printed_star_obstacles(scene, transform, style)
    for label, candidate in placed:
        for star in star_obstacles:
            associated = label.target_id in star.star_ids
            hard_min = (
                style.label.star_clearance.associated.hard_min_mm
                if associated
                else foreign_star_hard_min_mm(star.collision_radius_mm, style.label.star_clearance)
            )
            clearance = circle_rect_edge_distance_mm(
                star.page_point, star.collision_radius_mm, candidate.bounds
            )
            if clearance < hard_min:
                issues.append(
                    _issue(
                        IssueType.LABEL_STAR,
                        (label.id, star.id),
                        f"{label.id} clears star {star.id} by only {clearance:.2f} mm",
                    )
                )

        for scene_dso in scene.deep_sky_objects:
            if not scene_dso.symbol_visible:
                continue
            dso = scene_dso.dso
            extent = dso_symbol_extent(
                dso, mm_per_deg=transform.mm_per_deg, style=style
            )
            dso_point = transform.to_page(scene_dso.chart_point)
            if circle_intersects_rect(
                dso_point, extent.collision_radius_mm, candidate.bounds
            ):
                issues.append(
                    _issue(
                        IssueType.LABEL_DSO,
                        (label.id, dso.id),
                        f"{label.id} overlaps deep-sky object {dso.id}",
                    )
                )

    return tuple(sorted(issues, key=lambda issue: issue.id))
