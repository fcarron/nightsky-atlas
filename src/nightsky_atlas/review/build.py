"""Build review requests from a rendered page's scene and labels."""

from __future__ import annotations

from nightsky_atlas.chart.page import PageTransform
from nightsky_atlas.layout.collision import placed_candidates
from nightsky_atlas.layout.models import Label
from nightsky_atlas.review.models import ReviewElement, ReviewRequest
from nightsky_atlas.review.schema import PERMITTED_ACTIONS
from nightsky_atlas.scene.models import ChartScene

__all__ = ["build_review_request"]

PROMPT_VERSION = "m10-1"
SCHEMA_VERSION = "m10-1"
_IMPORTANT_STAR_MAGNITUDE = 6.0


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
            )
        )

    return ReviewRequest(
        page_id=page_id,
        prompt_version=PROMPT_VERSION,
        schema_version=SCHEMA_VERSION,
        images=images,
        permitted_actions=PERMITTED_ACTIONS,
        elements=tuple(elements),
        diagnostics=diagnostics,
    )