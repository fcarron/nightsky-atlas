"""Build review requests from a rendered page's scene and labels."""

from __future__ import annotations

from nightsky_atlas.chart.page import PageTransform
from nightsky_atlas.layout.geometry import expand_rect, segment_intersects_rect
from nightsky_atlas.layout.models import Label
from nightsky_atlas.review.models import ReviewElement, ReviewRequest
from nightsky_atlas.review.schema import ReviewActionType
from nightsky_atlas.scene.models import ChartScene

__all__ = ["build_review_request"]

PROMPT_VERSION = "m10-3"
SCHEMA_VERSION = "m10-2"
_IMPORTANT_STAR_MAGNITUDE = 6.0

# Actions the reviewer is told about.  Display-name variants remain unavailable
# until the layout document carries a selected variant through replay.
_ADVERTISED_ACTIONS: tuple[ReviewActionType, ...] = (
    ReviewActionType.SELECT_CANDIDATE,
    ReviewActionType.SHOW_OPTIONAL_LABEL,
    ReviewActionType.HIDE_OPTIONAL_LABEL,
    ReviewActionType.MOVE_LABEL,
    ReviewActionType.FINE_ADJUST_LABEL,
    ReviewActionType.REQUEST_LINE_KNOCKOUT,
    ReviewActionType.ENABLE_LEADER_LINE,
    ReviewActionType.REMOVE_LEADER_LINE,
)


def _permitted_actions(elements: list[ReviewElement]) -> tuple[str, ...]:
    # Display-name variants remain intentionally unavailable until the layout
    # document can carry a selected variant through rendering and replay.
    del elements
    return tuple(action.value for action in _ADVERTISED_ACTIONS)


def build_review_request(
    *,
    page_id: str,
    scene: ChartScene,
    labels: tuple[Label, ...],
    transform: PageTransform,
    diagnostics: dict[str, float],
    images: tuple[str, ...],
) -> ReviewRequest:
    """Assemble a review request with only the elements a reviewer needs.

    Includes bright stars, deep-sky objects, visible labels and hidden optional
    labels that the reviewer may ask to show. Faint stars are omitted.
    """
    elements: list[ReviewElement] = []

    for scene_star in scene.stars:
        if scene_star.star.magnitude > _IMPORTANT_STAR_MAGNITUDE:
            continue
        point = transform.to_page(scene_star.chart_point)
        elements.append(
            ReviewElement(
                id=f"star:{scene_star.star.id}",
                kind="star",
                page_x_mm=point.x_mm,
                page_y_mm=point.y_mm,
            )
        )

    for scene_dso in scene.deep_sky_objects:
        point = transform.to_page(scene_dso.chart_point)
        elements.append(
            ReviewElement(
                id=f"dso:{scene_dso.dso.id}",
                kind="dso",
                text=scene_dso.dso.id,
                page_x_mm=point.x_mm,
                page_y_mm=point.y_mm,
            )
        )

    for label in labels:
        candidate = label.effective_candidate()
        if candidate is None or (label.hidden and label.mandatory):
            continue
        line_conflict = not label.hidden and any(
            segment_intersects_rect(
                transform.to_page(line.points[0]),
                transform.to_page(line.points[-1]),
                expand_rect(candidate.bounds, 0.4),
            )
            for line in scene.constellation_lines
        )
        elements.append(
            ReviewElement(
                id=label.id,
                kind="label",
                text=label.text,
                bounds=candidate.bounds,
                candidates=tuple(
                    item.position.value for item in label.candidates if item.ring == 0
                ),
                current_candidate=candidate.position.value,
                allowed_distances=("near", "medium", "far"),
                fine_adjust_radius_mm=3.0,
                constellation_line_conflict=line_conflict,
                leader_line_capable=any(
                    item.dso.id == label.target_id for item in scene.deep_sky_objects
                ),
                leader_line_enabled=label.leader_line,
                hidden=label.hidden,
            )
        )

    return ReviewRequest(
        page_id=page_id,
        prompt_version=PROMPT_VERSION,
        schema_version=SCHEMA_VERSION,
        images=images,
        permitted_actions=_permitted_actions(elements),
        elements=tuple(elements),
        diagnostics=diagnostics,
    )
