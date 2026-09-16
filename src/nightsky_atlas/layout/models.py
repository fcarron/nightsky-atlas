"""Layout document models.

A :class:`Label` is a first-class, stable-ID presentation object.  It is
separate from the astronomical object it annotates and from the renderer
(``AGENTS.md`` sections 5 and 6.4).  Layout models serialise for layout JSON.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from nightsky_atlas.chart.page import PagePoint, PageRect

__all__ = ["CompassPosition", "Label", "LabelCandidate"]


class CompassPosition(StrEnum):
    """Standard eight-way compass placement of a label around its anchor."""

    N = "N"
    NE = "NE"
    E = "E"
    SE = "SE"
    S = "S"
    SW = "SW"
    W = "W"
    NW = "NW"


@dataclass(frozen=True, slots=True)
class LabelCandidate:
    """One permitted placement of a label, with measured page bounds.

    ``ring`` identifies concentric candidate rings; ring 0 is the nearest
    legal placement and is the only ring referenced by the compass action
    schema.
    """

    id: str
    position: CompassPosition
    anchor: PagePoint
    bounds: PageRect
    ring: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable mapping of this candidate."""
        return {
            "id": self.id,
            "position": self.position.value,
            "ring": self.ring,
            "anchor": {"x_mm": self.anchor.x_mm, "y_mm": self.anchor.y_mm},
            "bounds": {
                "left_mm": self.bounds.left_mm,
                "top_mm": self.bounds.top_mm,
                "width_mm": self.bounds.width_mm,
                "height_mm": self.bounds.height_mm,
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LabelCandidate:
        """Reconstruct a candidate from a mapping produced by :meth:`to_dict`."""
        anchor = data["anchor"]
        bounds = data["bounds"]
        return cls(
            id=data["id"],
            position=CompassPosition(data["position"]),
            anchor=PagePoint(x_mm=float(anchor["x_mm"]), y_mm=float(anchor["y_mm"])),
            bounds=PageRect(
                left_mm=float(bounds["left_mm"]),
                top_mm=float(bounds["top_mm"]),
                width_mm=float(bounds["width_mm"]),
                height_mm=float(bounds["height_mm"]),
            ),
            ring=int(data.get("ring", 0)),
        )


@dataclass(frozen=True, slots=True)
class Label:
    """A label with a stable ID, candidate placements and a selection.

    ``selected_candidate_id`` is ``None`` until an optimizer or the renderer
    picks a candidate.  ``mandatory`` labels must be placed; optional labels may
    remain hidden if no candidate is acceptable.
    """

    id: str
    target_id: str
    text: str
    priority: int
    mandatory: bool
    candidates: tuple[LabelCandidate, ...]
    selected_candidate_id: str | None = None
    hidden: bool = False

    def candidate(self, candidate_id: str) -> LabelCandidate | None:
        """Return the candidate with the given ID, if present."""
        for item in self.candidates:
            if item.id == candidate_id:
                return item
        return None

    def selected_candidate(self) -> LabelCandidate | None:
        """Return the selected candidate, if any."""
        if self.selected_candidate_id is None:
            return None
        return self.candidate(self.selected_candidate_id)

    def with_selection(self, candidate_id: str | None) -> Label:
        """Return a copy with a different selected candidate."""
        return Label(
            id=self.id,
            target_id=self.target_id,
            text=self.text,
            priority=self.priority,
            mandatory=self.mandatory,
            candidates=self.candidates,
            selected_candidate_id=candidate_id,
            hidden=self.hidden,
        )

    def with_placement(self, candidate_id: str | None, *, hidden: bool = False) -> Label:
        """Return a copy with an explicit selection and visibility."""
        return Label(
            id=self.id,
            target_id=self.target_id,
            text=self.text,
            priority=self.priority,
            mandatory=self.mandatory,
            candidates=self.candidates,
            selected_candidate_id=candidate_id,
            hidden=hidden,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable mapping of this label."""
        return {
            "id": self.id,
            "target_id": self.target_id,
            "text": self.text,
            "priority": self.priority,
            "mandatory": self.mandatory,
            "hidden": self.hidden,
            "selected_candidate_id": self.selected_candidate_id,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Label:
        """Reconstruct a label from a mapping produced by :meth:`to_dict`."""
        return cls(
            id=data["id"],
            target_id=data["target_id"],
            text=data["text"],
            priority=int(data["priority"]),
            mandatory=bool(data["mandatory"]),
            candidates=tuple(
                LabelCandidate.from_dict(item) for item in data["candidates"]
            ),
            selected_candidate_id=data.get("selected_candidate_id"),
            hidden=bool(data.get("hidden", False)),
        )