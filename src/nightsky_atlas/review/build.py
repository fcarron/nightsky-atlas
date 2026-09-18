"""Build review requests from a rendered page's scene and labels."""

from __future__ import annotations

from nightsky_atlas.chart.page import PageTransform
from nightsky_atlas.layout.collision import placed_candidates
from nightsky_atlas.layout.models import Label
from nightsky_atlas.review.models import ReviewElement, ReviewRequest
from nightsky_atlas.review.schema import ReviewActionType
from nightsky_atlas.scene.models import ChartScene

__all__ = ["build_review_request"]

PROMPT_VERSION = "m10-2"
SCHEMA_VERSION = "m10-1"
_IMPORTANT_STAR_MAGNITUDE = 6.0

# Actions the reviewer is told about.  ``select_display_name_variant`` is only
# advertised when an element actually lists variants; leader-line actions are
# omitted until the layout model carries leader-line state, so the reviewer is
# never invited to request something the action engine cannot apply.
_ADVERTISED_ACTIONS: tuple[ReviewActionType, ...] = (
    ReviewActionType.SELECT_CANDIDATE,
    ReviewActionType.SHOW_OPTIONAL_LABEL,
    ReviewActionType.HIDE_OPTIONAL_LABEL,
)


def _permitted_actions(elements: list[ReviewElement]) -> tuple[str, ...]:
    actions = [action.value for action in _ADVERTISED_ACTIONS]
    if any(element.display_name_variants for element in elements):
        actions.append(ReviewActionType.SELECT_DISPLAY_NAME_VARIANT.value)
    return tuple(actions)


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

    Includes bright stars, deep-sky objects and visible labels; omits faint
    stars and hidden labels to keep the payload focused.
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

    for label, candidate in placed_candidates(labels):
        elements.append(
            ReviewElement(
                id=label.id,
                kind="label",
                text=label.text,
                bounds=candidate.bounds,
                candidates=tuple(
                    item.position.value for item in label.candidates if item.ring == 0
                ),
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