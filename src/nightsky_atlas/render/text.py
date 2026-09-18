"""Exact text measurement and layout using Pango.

Pango is given an explicit resolution of 72 dpi so that font sizes and measured
extents are in PostScript points, identical for the measuring context and the
rendering context.  The renderer and the collision system therefore agree on
text bounds (``AGENTS.md`` section 13).
"""

from __future__ import annotations

from dataclasses import dataclass

import cairo
import gi

gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")

from gi.repository import Pango, PangoCairo  # noqa: E402

from nightsky_atlas.units import pt_to_mm  # noqa: E402

__all__ = [
    "FontWeight",
    "TextMetrics",
    "TextMeasurer",
    "draw_centered_text",
    "draw_markup_centered_text",
    "draw_markup_text",
    "draw_rotated_markup_centered_text",
    "draw_text",
    "escape_markup",
    "make_layout",
    "make_markup_layout",
    "measure_point_size",
]

_RESOLUTION_DPI = 72.0

FontWeight = str

_WEIGHTS: dict[str, Pango.Weight] = {
    "normal": Pango.Weight.NORMAL,
    "bold": Pango.Weight.BOLD,
}


def _pango_weight(weight: FontWeight) -> Pango.Weight:
    try:
        return _WEIGHTS[weight]
    except KeyError:
        raise ValueError(f"unknown font weight {weight!r}; expected normal or bold") from None


@dataclass(frozen=True, slots=True)
class TextMetrics:
    """Measured text extent in millimetres."""

    width_mm: float
    height_mm: float


def make_layout(
    cr: cairo.Context[cairo.Surface],
    font_family: str,
    font_size_pt: float,
    font_weight: FontWeight = "normal",
) -> Pango.Layout:
    """Create a Pango layout configured for physical point sizes."""
    layout = PangoCairo.create_layout(cr)
    PangoCairo.context_set_resolution(layout.get_context(), _RESOLUTION_DPI)
    description = Pango.FontDescription()
    description.set_family(font_family)
    description.set_size(int(round(font_size_pt * Pango.SCALE)))
    description.set_weight(_pango_weight(font_weight))
    layout.set_font_description(description)
    return layout


def escape_markup(text: str) -> str:
    """Escape text so it can be embedded verbatim in a Pango markup string."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def make_markup_layout(
    cr: cairo.Context[cairo.Surface],
    markup: str,
    font_family: str,
    font_size_pt: float,
    font_weight: FontWeight = "normal",
) -> Pango.Layout:
    """Create a Pango layout from markup, keeping the base font description.

    Markup is the single source of mixed-weight furniture (a regular title
    prefix with a bold chart code): one layout carries both weights, so the
    measured width and the drawn glyphs cannot disagree.
    """
    layout = make_layout(cr, font_family, font_size_pt, font_weight)
    layout.set_markup(markup, -1)
    return layout


def measure_point_size(
    cr: cairo.Context[cairo.Surface],
    text: str,
    font_family: str,
    font_size_pt: float,
    font_weight: FontWeight = "normal",
) -> tuple[float, float]:
    """Measure text and return its logical size in points."""
    layout = make_layout(cr, font_family, font_size_pt, font_weight)
    layout.set_text(text, -1)
    width, height = layout.get_pixel_size()
    return float(width), float(height)


def draw_centered_text(
    cr: cairo.Context[cairo.Surface],
    text: str,
    center_x_pt: float,
    center_y_pt: float,
    font_family: str,
    font_size_pt: float,
    font_weight: FontWeight = "normal",
) -> None:
    """Draw text centred on a point using the same metrics as :class:`TextMeasurer`."""
    layout = make_layout(cr, font_family, font_size_pt, font_weight)
    layout.set_text(text, -1)
    width, height = layout.get_pixel_size()
    cr.move_to(center_x_pt - width / 2.0, center_y_pt - height / 2.0)
    PangoCairo.show_layout(cr, layout)


def draw_text(
    cr: cairo.Context[cairo.Surface],
    text: str,
    x_pt: float,
    y_pt: float,
    font_family: str,
    font_size_pt: float,
    font_weight: FontWeight = "normal",
) -> None:
    """Draw text with its logical box top-left at ``(x_pt, y_pt)``."""
    layout = make_layout(cr, font_family, font_size_pt, font_weight)
    layout.set_text(text, -1)
    cr.move_to(x_pt, y_pt)
    PangoCairo.show_layout(cr, layout)


def draw_markup_centered_text(
    cr: cairo.Context[cairo.Surface],
    markup: str,
    center_x_pt: float,
    center_y_pt: float,
    font_family: str,
    font_size_pt: float,
    font_weight: FontWeight = "normal",
) -> None:
    """Draw Pango markup centred on a point."""
    layout = make_markup_layout(cr, markup, font_family, font_size_pt, font_weight)
    width, height = layout.get_pixel_size()
    cr.move_to(center_x_pt - width / 2.0, center_y_pt - height / 2.0)
    PangoCairo.show_layout(cr, layout)


def draw_markup_text(
    cr: cairo.Context[cairo.Surface],
    markup: str,
    x_pt: float,
    y_pt: float,
    font_family: str,
    font_size_pt: float,
    font_weight: FontWeight = "normal",
) -> None:
    """Draw Pango markup with its logical box top-left at ``(x_pt, y_pt)``."""
    layout = make_markup_layout(cr, markup, font_family, font_size_pt, font_weight)
    cr.move_to(x_pt, y_pt)
    PangoCairo.show_layout(cr, layout)


def draw_rotated_markup_centered_text(
    cr: cairo.Context[cairo.Surface],
    markup: str,
    center_x_pt: float,
    center_y_pt: float,
    font_family: str,
    font_size_pt: float,
    angle_rad: float,
    font_weight: FontWeight = "normal",
) -> None:
    """Draw Pango markup rotated about its centre by ``angle_rad``.

    Used for side-margin navigation, where the printable side band is too
    narrow for horizontal text once it is enlarged.
    """
    layout = make_markup_layout(cr, markup, font_family, font_size_pt, font_weight)
    width, height = layout.get_pixel_size()
    cr.save()
    cr.translate(center_x_pt, center_y_pt)
    cr.rotate(angle_rad)
    cr.move_to(-width / 2.0, -height / 2.0)
    PangoCairo.show_layout(cr, layout)
    cr.restore()


class TextMeasurer:
    """Measure label text in physical page millimetres.

    The surface is a scratch surface; only metrics are used.  The same
    :func:`make_layout` configuration is used by the renderer, so measured
    bounds match rendered text.
    """

    def __init__(
        self,
        font_family: str,
        font_size_pt: float,
        font_weight: FontWeight = "normal",
    ) -> None:
        self.font_family = font_family
        self.font_size_pt = font_size_pt
        self.font_weight = font_weight
        self._surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 4, 4)
        self._context = cairo.Context(self._surface)
        self._layout = make_layout(self._context, font_family, font_size_pt, font_weight)

    def measure_pt(self, text: str) -> tuple[float, float]:
        """Return the logical text extent in points."""
        self._layout.set_text(text, -1)
        width, height = self._layout.get_pixel_size()
        return float(width), float(height)

    def measure_mm(self, text: str) -> TextMetrics:
        """Return the logical text extent in millimetres."""
        width_pt, height_pt = self.measure_pt(text)
        return TextMetrics(width_mm=pt_to_mm(width_pt), height_mm=pt_to_mm(height_pt))

    def measure_markup_mm(self, markup: str) -> TextMetrics:
        """Return the extent of a Pango markup string in millimetres.

        Mixed-weight furniture (a regular prefix and a bold chart code) must be
        measured exactly as it is drawn, so the obstacle and the printed glyphs
        use the same layout.
        """
        self._layout.set_markup(markup, -1)
        width, height = self._layout.get_pixel_size()
        return TextMetrics(width_mm=pt_to_mm(width), height_mm=pt_to_mm(height))