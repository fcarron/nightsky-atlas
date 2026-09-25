"""Visible and collision geometry for measured label text."""

from __future__ import annotations

from nightsky_atlas.chart.page import PageRect
from nightsky_atlas.layout.geometry import expand_rect
from nightsky_atlas.layout.models import Label, LabelCandidate

__all__ = ["candidate_ink_bounds", "dso_collision_bounds", "label_collision_bounds"]


def candidate_ink_bounds(candidate: LabelCandidate) -> PageRect:
    """Return the measured glyph-ink envelope, falling back to the logical box."""
    if not candidate.glyph_bounds:
        return candidate.bounds
    left = min(rect.left_mm for rect in candidate.glyph_bounds)
    top = min(rect.top_mm for rect in candidate.glyph_bounds)
    right = max(rect.right_mm for rect in candidate.glyph_bounds)
    bottom = max(rect.bottom_mm for rect in candidate.glyph_bounds)
    return PageRect(left, top, right - left, bottom - top)


def label_collision_bounds(
    label: Label,
    candidate: LabelCandidate,
    *,
    ink_clearance_mm: float | None,
) -> PageRect:
    """Return interaction geometry without changing safe/rendering bounds.

    ``None`` retains the historical logical-box collision behavior. A numeric
    value applies a half-clearance to the actual ink envelope; two labels then
    need at least that total edge-to-edge gap to remain non-colliding.
    """
    if not label.id.startswith("label:dso:"):
        return candidate.bounds
    return dso_collision_bounds(candidate, ink_clearance_mm)


def dso_collision_bounds(
    candidate: LabelCandidate,
    ink_clearance_mm: float | None,
) -> PageRect:
    """Return DSO ink-envelope collision geometry for the configured gap."""
    if ink_clearance_mm is None:
        return candidate.bounds
    return expand_rect(candidate_ink_bounds(candidate), ink_clearance_mm / 2.0)
