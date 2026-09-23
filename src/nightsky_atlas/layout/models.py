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
    schema. Star-label candidates may also carry their measured display variant.
    """

    id: str
    position: CompassPosition
    anchor: PagePoint
    bounds: PageRect
    ring: int = 0
    display_text: str | None = None
    variant_rank: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable mapping of this candidate."""
        data = {
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
        if self.display_text is not None:
            data["display_text"] = self.display_text
            data["variant_rank"] = self.variant_rank
        return data

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
            display_text=data.get("display_text"),
            variant_rank=int(data.get("variant_rank", 0)),
        )


@dataclass(frozen=True, slots=True)
class Label:
    """A label with a stable ID, candidate placements and a selection.

    ``selected_candidate_id`` is ``None`` until an optimizer or the renderer
    picks a candidate.  ``mandatory`` labels must be placed; optional labels may
    remain hidden if no candidate is acceptable.  ``locked`` labels come from a
    manual override and must not be moved by later optimizers (``AGENTS.md``
    section 22).  ``font_size_pt`` and ``font_weight`` carry the per-label
    typography; ``None``/``normal`` fall back to the style default.
    ``text`` is canonical presentation text and never changes during placement.
    """

    id: str
    target_id: str
    text: str
    priority: int
    mandatory: bool
    candidates: tuple[LabelCandidate, ...]
    selected_candidate_id: str | None = None
    hidden: bool = False
    locked: bool = False
    font_size_pt: float | None = None
    font_weight: str = "normal"
    leader_line: bool = False
    semantic_key: str | None = None

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

    def effective_candidate(self) -> LabelCandidate | None:
        """Return the placement actually printed for this label.

        The explicit selection wins; a label that has not been through the
        optimizer falls back to its preferred (first) candidate.  This is the
        single definition shared by the renderer, the collision system and the
        optimizer, so a serialized layout and the printed page cannot disagree.
        """
        candidate = self.selected_candidate()
        if candidate is not None:
            return candidate
        return self.candidates[0] if self.candidates else None

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
            locked=self.locked,
            font_size_pt=self.font_size_pt,
            font_weight=self.font_weight,
            leader_line=self.leader_line and candidate_id == self.selected_candidate_id,
            semantic_key=self.semantic_key,
        )

    def with_placement(
        self, candidate_id: str | None, *, hidden: bool = False, locked: bool | None = None
    ) -> Label:
        """Return a copy with an explicit selection and visibility.

        ``locked`` is preserved when omitted, so optimizer passes never unlock a
        manual override.
        """
        return Label(
            id=self.id,
            target_id=self.target_id,
            text=self.text,
            priority=self.priority,
            mandatory=self.mandatory,
            candidates=self.candidates,
            selected_candidate_id=candidate_id,
            hidden=hidden,
            locked=self.locked if locked is None else locked,
            font_size_pt=self.font_size_pt,
            font_weight=self.font_weight,
            leader_line=(
                self.leader_line and not hidden and candidate_id == self.selected_candidate_id
            ),
            semantic_key=self.semantic_key,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable mapping of this label."""
        data = {
            "id": self.id,
            "target_id": self.target_id,
            "text": self.text,
            "priority": self.priority,
            "mandatory": self.mandatory,
            "hidden": self.hidden,
            "locked": self.locked,
            "font_size_pt": self.font_size_pt,
            "font_weight": self.font_weight,
            "leader_line": self.leader_line,
            "selected_candidate_id": self.selected_candidate_id,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }
        if self.semantic_key is not None:
            data["semantic_key"] = self.semantic_key
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Label:
        """Reconstruct a label from a mapping produced by :meth:`to_dict`."""
        return cls(
            id=data["id"],
            target_id=data["target_id"],
            text=data["text"],
            priority=int(data["priority"]),
            mandatory=bool(data["mandatory"]),
            candidates=tuple(LabelCandidate.from_dict(item) for item in data["candidates"]),
            selected_candidate_id=data.get("selected_candidate_id"),
            hidden=bool(data.get("hidden", False)),
            locked=bool(data.get("locked", False)),
            font_size_pt=(
                None if data.get("font_size_pt") is None else float(data["font_size_pt"])
            ),
            font_weight=str(data.get("font_weight", "normal")),
            leader_line=bool(data.get("leader_line", False)),
            semantic_key=data.get("semantic_key"),
        )
