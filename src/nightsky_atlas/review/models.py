"""Review models and schemas.

Review artifacts let a vision model reason about a rendered page without seeing
the whole layout document (``AGENTS.md`` sections 17 and 18).  The
:class:`ReviewRequest` is built from a scene; :mod:`nightsky_atlas.review.schema`
validates model responses before they can affect anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nightsky_atlas.chart.page import PageRect

__all__ = ["ReviewElement", "ReviewRequest"]


@dataclass(frozen=True, slots=True)
class ReviewElement:
    """A visible element a reviewer may refer to, with its page geometry.

    ``candidates`` lists the compass positions a label may actually be moved to
    (ring-0 placements); ``display_name_variants`` lists the alternative printed
    names the label supports.  Both are empty for non-label elements.  Exposing
    them stops the reviewer from inventing candidates or name variants that the
    layout model cannot honour.
    """

    id: str
    kind: str
    text: str | None = None
    page_x_mm: float | None = None
    page_y_mm: float | None = None
    bounds: PageRect | None = None
    candidates: tuple[str, ...] = ()
    display_name_variants: tuple[str, ...] = ()
    current_candidate: str | None = None
    allowed_distances: tuple[str, ...] = ()
    fine_adjust_radius_mm: float | None = None
    constellation_line_conflict: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"id": self.id, "kind": self.kind}
        if self.text is not None:
            payload["text"] = self.text
        if self.page_x_mm is not None:
            payload["page_x_mm"] = self.page_x_mm
        if self.page_y_mm is not None:
            payload["page_y_mm"] = self.page_y_mm
        if self.bounds is not None:
            payload["bounds"] = {
                "left_mm": self.bounds.left_mm,
                "top_mm": self.bounds.top_mm,
                "width_mm": self.bounds.width_mm,
                "height_mm": self.bounds.height_mm,
            }
        if self.candidates:
            payload["candidates"] = list(self.candidates)
        if self.display_name_variants:
            payload["display_name_variants"] = list(self.display_name_variants)
        if self.current_candidate is not None:
            payload["current_candidate"] = self.current_candidate
        if self.allowed_distances:
            payload["allowed_distances"] = list(self.allowed_distances)
        if self.fine_adjust_radius_mm is not None:
            payload["fine_adjust_radius_mm"] = self.fine_adjust_radius_mm
        if self.constellation_line_conflict:
            payload["constellation_line_conflict"] = True
        return payload


@dataclass(frozen=True, slots=True)
class ReviewRequest:
    """Everything a reviewer needs for one page."""

    page_id: str
    prompt_version: str
    schema_version: str
    images: tuple[str, ...]
    permitted_actions: tuple[str, ...]
    elements: tuple[ReviewElement, ...] = ()
    diagnostics: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable mapping of this request."""
        return {
            "page_id": self.page_id,
            "prompt_version": self.prompt_version,
            "schema_version": self.schema_version,
            "images": list(self.images),
            "permitted_actions": list(self.permitted_actions),
            "elements": [element.to_dict() for element in self.elements],
            "diagnostics": dict(self.diagnostics),
        }
