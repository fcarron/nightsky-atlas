"""Reusable, deterministic page-space label placement operations."""

from __future__ import annotations

from dataclasses import replace

from nightsky_atlas.chart.page import PagePoint, PageRect
from nightsky_atlas.layout.models import Label, LabelCandidate

__all__ = ["offset_label_placement", "translate_candidate"]


def translate_candidate(
    candidate: LabelCandidate,
    dx_mm: float,
    dy_mm: float,
    *,
    candidate_id: str | None = None,
) -> LabelCandidate:
    """Translate all measured placement geometry by a page-space offset."""
    return replace(
        candidate,
        id=candidate.id if candidate_id is None else candidate_id,
        anchor=PagePoint(candidate.anchor.x_mm + dx_mm, candidate.anchor.y_mm + dy_mm),
        bounds=_translate_rect(candidate.bounds, dx_mm, dy_mm),
        glyph_bounds=tuple(_translate_rect(rect, dx_mm, dy_mm) for rect in candidate.glyph_bounds),
        whitespace_bounds=tuple(
            _translate_rect(rect, dx_mm, dy_mm) for rect in candidate.whitespace_bounds
        ),
    )


def offset_label_placement(
    label: Label,
    candidate_id: str,
    dx_mm: float,
    dy_mm: float,
) -> Label:
    """Select a candidate translated by a reproducible physical page offset."""
    base = label.candidate(candidate_id)
    if base is None:
        raise ValueError(f"{label.id}: unknown base candidate {candidate_id!r}")
    if dx_mm == 0.0 and dy_mm == 0.0:
        return label.with_placement(candidate_id)
    adjusted_id = f"{candidate_id}:offset:{dx_mm:+.4f}:{dy_mm:+.4f}"
    adjusted = translate_candidate(base, dx_mm, dy_mm, candidate_id=adjusted_id)
    candidates = tuple(item for item in label.candidates if item.id != adjusted_id)
    return replace(
        label,
        candidates=(*candidates, adjusted),
        selected_candidate_id=adjusted_id,
        hidden=False,
    )


def _translate_rect(rect: PageRect, dx_mm: float, dy_mm: float) -> PageRect:
    return PageRect(
        rect.left_mm + dx_mm,
        rect.top_mm + dy_mm,
        rect.width_mm,
        rect.height_mm,
    )
