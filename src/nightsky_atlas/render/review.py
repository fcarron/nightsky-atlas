"""Annotated review image rendering.

The review image adds short element IDs and subtle bounding boxes while keeping
the underlying chart legible.  Review annotations are never part of final PDFs
(``AGENTS.md`` section 17).
"""

from __future__ import annotations

from pathlib import Path

from nightsky_atlas.atlas.config import StyleConfig
from nightsky_atlas.chart.page import PageTransform
from nightsky_atlas.layout.models import Label
from nightsky_atlas.render.cairo import DebugOptions, render_chart
from nightsky_atlas.scene.models import ChartScene

__all__ = ["render_review_png"]

_REVIEW_DEBUG = DebugOptions(
    label_boxes=True,
    exclusion_zones=True,
    element_ids=True,
    candidate_points=False,
)


def render_review_png(
    scene: ChartScene,
    transform: PageTransform,
    style: StyleConfig,
    labels: tuple[Label, ...],
    path: str | Path,
    *,
    png_dpi: float = 300.0,
) -> None:
    """Render an annotated review PNG."""
    render_chart(
        scene,
        transform,
        style,
        labels=labels,
        debug=_REVIEW_DEBUG,
        png_path=path,
        png_dpi=png_dpi,
    )