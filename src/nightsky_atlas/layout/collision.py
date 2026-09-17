"""Hard label collision checks.

Every issue carries a stable ID so it can be referenced by layout diffs,
reviews and regression tests (``AGENTS.md`` section 14.4).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from nightsky_atlas.atlas.config import StyleConfig
from nightsky_atlas.chart.page import PageRect, PageTransform
from nightsky_atlas.layout.geometry import circle_intersects_rect, rects_overlap
from nightsky_atlas.layout.models import Label, LabelCandidate
from nightsky_atlas.render.symbols import StarSizeModel, dso_symbol_extent
from nightsky_atlas.scene.models import ChartScene

__all__ = [
    "IssueType",
    "LayoutIssue",
    "find_hard_violations",
    "placed_candidates",
]

_IMPORTANT_STAR_MAGNITUDE = 6.0


class IssueType(StrEnum):
    """Categories of hard layout violation."""

    LABEL_LABEL = "label_label"
    LABEL_PAGE = "label_page"
    LABEL_STAR = "label_star"
    LABEL_DSO = "label_dso"
    INVALID_SELECTION = "invalid_selection"
    MISSING_CANDIDATE = "missing_candidate"


@dataclass(frozen=True, slots=True)
class LayoutIssue:
    """A single hard layout violation with a stable ID."""

    id: str
    issue_type: IssueType
    element_ids: tuple[str, ...]
    message: str


def placed_candidates(labels: tuple[Label, ...]) -> list[tuple[Label, LabelCandidate]]:
    """Return the effectively placed candidate for every label.

    Uses the explicit selection when present, otherwise the fixed preference
    order (the first candidate), matching the renderer's default.
    """
    placed: list[tuple[Label, LabelCandidate]] = []
    for label in labels:
        if label.hidden:
            continue
        candidate = label.selected_candidate()
        if candidate is None and label.candidates:
            candidate = label.candidates[0]
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
    important_magnitude: float = _IMPORTANT_STAR_MAGNITUDE,
) -> tuple[LayoutIssue, ...]:
    """Return all hard label violations for a layout."""
    issues: list[LayoutIssue] = []

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

    size_model = StarSizeModel.from_style(style.star)
    for label, candidate in placed:
        for scene_star in scene.stars:
            if scene_star.star.magnitude > important_magnitude:
                continue
            star_point = transform.to_page(scene_star.chart_point)
            radius = size_model.radius_mm(scene_star.star.magnitude)
            if circle_intersects_rect(star_point, radius, candidate.bounds):
                issues.append(
                    _issue(
                        IssueType.LABEL_STAR,
                        (label.id, scene_star.star.id),
                        f"{label.id} overlaps star {scene_star.star.id}",
                    )
                )

        for scene_dso in scene.deep_sky_objects:
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