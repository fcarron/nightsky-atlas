"""Physical unit conversions.

The atlas reasons in physical page units, never in screen pixels
(``AGENTS.md`` section 16.2).  Millimetres are the primary page unit; PDF and
Cairo work in PostScript points.
"""

from __future__ import annotations

__all__ = [
    "MM_PER_INCH",
    "POINTS_PER_INCH",
    "mm_to_pt",
    "pt_to_mm",
]

MM_PER_INCH = 25.4
POINTS_PER_INCH = 72.0


def mm_to_pt(value_mm: float) -> float:
    """Convert a length from millimetres to PostScript points."""
    return value_mm / MM_PER_INCH * POINTS_PER_INCH


def pt_to_mm(value_pt: float) -> float:
    """Convert a length from PostScript points to millimetres."""
    return value_pt / POINTS_PER_INCH * MM_PER_INCH
