"""Visible atlas/chart naming, centralised in one place.

Internal chart identifiers stay long and explicit (``standard-068``), but the
printed atlas uses a short, consistent notation (``S068``).  Every visible
string -- page title, navigation reference -- is built from the structures here
so the same conventions are never hand-written in more than one renderer.
"""

from __future__ import annotations

from dataclasses import dataclass

from nightsky_atlas.atlas.config import EditionConfig, default_edition
from nightsky_atlas.chart.models import ChartDefinition

__all__ = [
    "PRODUCT_NAME",
    "ChartPresentation",
    "chart_index",
    "chart_title",
    "format_dec_deg",
    "format_ra_deg",
    "neighbour_code",
    "neighbour_markup",
    "presentation_for",
    "product_edition_title",
]


def _escape_markup(text: str) -> str:
    """Escape text for Pango markup without depending on the render layer."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


PRODUCT_NAME = "NightSky Atlas"


def format_ra_deg(ra_deg: float) -> str:
    """Format right ascension as ``HHhMMm`` on the 0–24 hour clock."""
    total_minutes = int(round((ra_deg % 360.0) * 4.0)) % (24 * 60)
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours:02d}h{minutes:02d}m"


def format_dec_deg(dec_deg: float) -> str:
    """Format declination as a signed degree value for chart furniture."""
    value = round(dec_deg, 3)
    sign = "+" if value >= 0.0 else "-"
    magnitude = abs(value)
    if abs(magnitude - round(magnitude)) < 1e-6:
        body = f"{magnitude:.0f}"
    else:
        body = f"{magnitude:.1f}"
    return f"{sign}{body}\N{DEGREE SIGN}"


def chart_index(chart_id: str) -> int | None:
    """Return the trailing numeric chart index, or ``None``.

    Tiled charts are named ``<atlas>-068``; manually specified fixtures such as
    ``test-virgo`` have no index and fall back to their internal id.
    """
    head, separator, tail = chart_id.rpartition("-")
    if separator and head and tail.isdigit():
        return int(tail)
    return None


@dataclass(frozen=True, slots=True)
class ChartPresentation:
    """Visible naming for one chart page.

    ``chart_index`` is the numeric page position within the edition; when it is
    absent (manual test charts) the visible code falls back to the internal
    chart id.
    """

    edition_name: str
    edition_code: str
    chart_index: int | None
    internal_chart_id: str = ""
    product_name: str = PRODUCT_NAME
    chart_index_width: int = 3

    @property
    def chart_code(self) -> str:
        """Short visible chart code, e.g. ``S068``."""
        if self.chart_index is None:
            return self.internal_chart_id
        return f"{self.edition_code}{self.chart_index:0{self.chart_index_width}d}"

    @property
    def title(self) -> str:
        """Full visible page title, e.g. ``NightSky Atlas — Standard · S068``."""
        if not self.chart_code:
            return product_edition_title(self.edition_name, product_name=self.product_name)
        return (
            f"{self.product_name} \N{EM DASH} {self.edition_name} \N{MIDDLE DOT} {self.chart_code}"
        )

    @property
    def title_prefix(self) -> str:
        """Visible title without the chart code, including the separator."""
        if not self.chart_code:
            return ""
        return f"{self.product_name} \N{EM DASH} {self.edition_name} \N{MIDDLE DOT} "

    @property
    def title_markup(self) -> str:
        """Title as Pango markup: regular prefix, emphasized chart code.

        The chart code is the one string an observer hunts for while flipping
        pages, so it is the only part rendered bold (``AGENTS.md`` section 16:
        the renderer draws exactly what the presentation specifies).
        """
        if not self.chart_code:
            return _escape_markup(self.title)
        return f"{_escape_markup(self.title_prefix)}<b>{_escape_markup(self.chart_code)}</b>"


def product_edition_title(edition_name: str, *, product_name: str = PRODUCT_NAME) -> str:
    """Product and edition name without a chart code, e.g. front matter."""
    return f"{product_name} \N{EM DASH} {edition_name}"


def presentation_for(
    definition: ChartDefinition,
    *,
    edition_name: str | None = None,
    edition_code: str | None = None,
    chart_index_width: int | None = None,
) -> ChartPresentation:
    """Build the visible presentation for a chart definition.

    ``edition_name``/``edition_code`` come from the atlas edition configuration;
    when omitted they fall back to the built-in edition registry so a renderer
    can be driven by a bare :class:`ChartDefinition`.
    """
    default = default_edition(definition.atlas_id)
    resolved_name = edition_name if edition_name is not None else default.name
    resolved_code = edition_code if edition_code is not None else default.code
    return ChartPresentation(
        edition_name=resolved_name,
        edition_code=resolved_code,
        chart_index=chart_index(definition.id),
        internal_chart_id=definition.id,
        chart_index_width=(
            chart_index_width if chart_index_width is not None else default.chart_index_width
        ),
    )


def presentation_from_edition(
    definition: ChartDefinition, edition: EditionConfig
) -> ChartPresentation:
    """Build the visible presentation from an edition configuration block."""
    return presentation_for(
        definition,
        edition_name=edition.name,
        edition_code=edition.code,
        chart_index_width=edition.chart_index_width,
    )


def neighbour_code(
    neighbour_id: str, edition_code: str, chart_index_width: int = 3
) -> str:
    """Return the short visible code for a neighbouring chart."""
    index = chart_index(neighbour_id)
    if index is None:
        return neighbour_id
    return f"{edition_code}{index:0{chart_index_width}d}"


def neighbour_markup(
    direction: str,
    neighbour_id: str,
    edition_code: str,
    chart_index_width: int = 3,
) -> str:
    """Return a neighbour reference as Pango markup.

    The direction stays regular and the chart code is bold, so the code -- not
    the compass letter -- is what catches the eye while flipping pages.
    """
    code = neighbour_code(neighbour_id, edition_code, chart_index_width)
    return f"{_escape_markup(direction)}: <b>{_escape_markup(code)}</b>"


def chart_title(definition: ChartDefinition) -> str:
    """Convenience: visible title for a bare chart definition."""
    return presentation_for(definition).title
