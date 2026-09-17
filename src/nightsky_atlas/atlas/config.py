"""Typed loading for atlas and style configuration.

Configuration is external, human-edited input, so it is validated strictly:

- unknown keys fail fast;
- physical quantities carry explicit units in their field names;
- type errors are reported before any rendering or layout work happens.

The models here describe *configuration*, not the mutable layout document
(see ``AGENTS.md`` section 5).  Chart geometry is intentionally minimal at this
milestone; atlas tiling is not implemented yet.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeFloat,
    PositiveFloat,
    ValidationError,
    field_validator,
    model_validator,
)

from nightsky_atlas.catalog.models import DsoType
from nightsky_atlas.catalog.visibility import VisibilityLimits
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry

__all__ = [
    "AtlasConfig",
    "ChartConfig",
    "ConfigError",
    "ConstellationBoundaryStyle",
    "ConstellationLineStyle",
    "ConstellationStyle",
    "DoubleStarStyle",
    "DsoExtentStyle",
    "DsoLabelStyle",
    "DsoLabelTierStyle",
    "DsoStyle",
    "EditionConfig",
    "FurnitureStyle",
    "GridStyle",
    "MagnitudeLegendStyle",
    "NavigationStyle",
    "OverlapTargetConfig",
    "PageConfig",
    "ScaleBarStyle",
    "StyleConfig",
    "TilingConfig",
    "VisibilityConfig",
    "load_atlas_config",
    "load_style_config",
]


class ConfigError(ValueError):
    """Raised when a configuration file is missing, malformed or invalid."""


class _StrictModel(BaseModel):
    """Base model that rejects unknown keys and is immutable."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class PageConfig(_StrictModel):
    """Printable page geometry, in millimetres."""

    width_mm: PositiveFloat
    height_mm: PositiveFloat
    margin_mm: PositiveFloat = 10.0

    def to_geometry(self) -> PageGeometry:
        """Convert this validated configuration to a domain geometry object."""
        return PageGeometry(
            width_mm=self.width_mm,
            height_mm=self.height_mm,
            margin_mm=self.margin_mm,
        )


class ChartConfig(_StrictModel):
    """A single manually specified chart area.

    This is deliberately *not* a tiling definition.  It only names the part of
    the sky a chart covers so the geometry prototype can consume it later.
    """

    id: str
    center_ra_deg: float
    center_dec_deg: float
    width_deg: PositiveFloat
    height_deg: PositiveFloat
    projection: Literal["stereographic"] = "stereographic"
    rotation_deg: float = 0.0
    neighbours: dict[str, str] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def _id_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("chart id must not be blank")
        return value

    def to_definition(self, *, atlas_id: str) -> ChartDefinition:
        """Convert this configuration to a domain chart definition."""
        return ChartDefinition(
            id=self.id,
            center_ra_deg=self.center_ra_deg,
            center_dec_deg=self.center_dec_deg,
            width_deg=self.width_deg,
            height_deg=self.height_deg,
            projection=self.projection,
            rotation_deg=self.rotation_deg,
            atlas_id=atlas_id,
            neighbours=tuple(self.neighbours.items()),
        )


class OverlapTargetConfig(_StrictModel):
    """Desired overlap between neighbouring charts, in degrees.

    ``vertical_deg`` is the nominal overlap between charts in adjacent
    declination rings; ``horizontal_min_deg`` is the smallest acceptable
    overlap between charts within a ring, measured at the ring's centre
    declination.  These are design targets used for reporting and count
    resolution, not hard geometry.
    """

    vertical_deg: PositiveFloat = 2.0
    horizontal_min_deg: PositiveFloat = 1.5


class TilingConfig(_StrictModel):
    """Sky tiling parameters for a complete atlas.

    Two modes are supported:

    - **declination-ring mode** (``declination_centers`` non-empty): explicit
      ring centre declinations, optionally with per-ring start counts, polar
      caps and right-ascension staggering.  This is the Standard v0.1 layout.
    - **legacy band mode**: a single ``overlap_deg`` and a fixed declination
      step derived from the chart height.  Kept for the original tiling and
      small test atlases.

    In ring mode, ``chart_counts`` are *start* values: when
    ``auto_adjust_counts`` is true they are raised as needed until each ring
    covers its declination slice at every right ascension (validated by
    :func:`nightsky_atlas.atlas.tiling.coverage_report`).  A count of ``None``
    lets the tiler derive it entirely from the geometry.
    """

    width_deg: PositiveFloat
    height_deg: PositiveFloat
    overlap_deg: PositiveFloat | None = None
    coverage_step_deg: PositiveFloat = 1.0

    declination_centers: tuple[float, ...] = ()
    chart_counts: tuple[int, ...] = ()
    polar_caps: bool = False
    target_overlap: OverlapTargetConfig = Field(default_factory=OverlapTargetConfig)
    stagger_ra_centers: bool = False
    auto_adjust_counts: bool = True

    @model_validator(mode="after")
    def _validate_tiling(self) -> TilingConfig:
        if self.overlap_deg is None and not self.declination_centers:
            raise ValueError(
                "tiling requires either overlap_deg (band mode) or "
                "declination_centers (ring mode)"
            )
        if self.overlap_deg is not None and self.declination_centers:
            raise ValueError(
                "specify either overlap_deg (band mode) or declination_centers "
                "(ring mode), not both"
            )
        if self.overlap_deg is not None and self.overlap_deg >= min(
            self.width_deg, self.height_deg
        ):
            raise ValueError("overlap_deg must be smaller than the chart field")
        for center in self.declination_centers:
            if not -90.0 < center < 90.0:
                raise ValueError(
                    "declination_centers must lie strictly inside (-90, 90); "
                    "use polar_caps for the poles"
                )
        if len(set(self.declination_centers)) != len(self.declination_centers):
            raise ValueError("declination_centers must be unique")
        if self.chart_counts and len(self.chart_counts) != len(self.declination_centers):
            raise ValueError(
                "chart_counts must have one entry per declination_center"
            )
        if any(count < 1 for count in self.chart_counts):
            raise ValueError("chart_counts entries must be positive")
        if self.polar_caps and not self.declination_centers:
            raise ValueError("polar_caps requires declination_centers")
        return self


class VisibilityConfig(_StrictModel):
    """Per-type deep-sky selection limits for one edition.

    Defaults describe the Standard target (an 8-10 inch instrument under a dark
    sky).  ``reference_*`` values are the comfortably-visible ends of the
    scoring ramps.
    """

    integrated_magnitude_limit: float = 13.5
    surface_brightness_limit: float = 23.5
    min_axis_arcmin: PositiveFloat = 1.5
    bright_magnitude_limit: float = 10.5
    reference_magnitude: float = 8.0
    reference_surface_brightness: float = 21.0
    reference_axis_arcmin: PositiveFloat = 10.0

    @model_validator(mode="after")
    def _references_sit_inside_limits(self) -> VisibilityConfig:
        if self.reference_magnitude >= self.integrated_magnitude_limit:
            raise ValueError(
                "reference_magnitude must be brighter than integrated_magnitude_limit"
            )
        if self.reference_surface_brightness >= self.surface_brightness_limit:
            raise ValueError(
                "reference_surface_brightness must be darker than "
                "surface_brightness_limit"
            )
        if self.reference_axis_arcmin <= self.min_axis_arcmin:
            raise ValueError("reference_axis_arcmin must exceed min_axis_arcmin")
        return self

    def to_limits(self) -> VisibilityLimits:
        """Convert this validated configuration to domain limits."""
        return VisibilityLimits(
            integrated_magnitude_limit=self.integrated_magnitude_limit,
            surface_brightness_limit=self.surface_brightness_limit,
            min_axis_arcmin=self.min_axis_arcmin,
            bright_magnitude_limit=self.bright_magnitude_limit,
            reference_magnitude=self.reference_magnitude,
            reference_surface_brightness=self.reference_surface_brightness,
            reference_axis_arcmin=self.reference_axis_arcmin,
        )


class EditionConfig(_StrictModel):
    """Visible identity of an atlas edition.

    ``name`` is printed on the page footer (``Standard``) and ``code`` is the
    short visible prefix used for chart codes and navigation (``S``).  Internal
    identifiers keep the full lowercase edition id (``standard-068``); this block
    only affects what the printed atlas shows.
    """

    name: str
    code: str

    @field_validator("name", "code")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("edition name and code must not be blank")
        return value


_EDITION_DEFAULTS: dict[str, EditionConfig] = {
    "pocket": EditionConfig(name="Pocket", code="P"),
    "standard": EditionConfig(name="Standard", code="S"),
    "deep": EditionConfig(name="Deep", code="D"),
}


class AtlasConfig(_StrictModel):
    """An atlas edition: page geometry plus explicit chart definitions."""

    id: str
    page: PageConfig
    edition: EditionConfig | None = None
    charts: list[ChartConfig] = Field(default_factory=list)
    tiling: TilingConfig | None = None
    stellar_limit_magnitude: PositiveFloat | None = None
    dso_limit_magnitude: PositiveFloat | None = None
    visibility: VisibilityConfig = Field(default_factory=VisibilityConfig)

    def resolved_edition(self) -> EditionConfig:
        """Return the visible edition identity, falling back to the registry."""
        if self.edition is not None:
            return self.edition
        return _EDITION_DEFAULTS.get(
            self.id, EditionConfig(name=self.id.title(), code=self.id[:1].upper() or "?")
        )


class StarStyle(_StrictModel):
    """Star symbol sizing, in millimetres of printed diameter.

    ``bright_magnitude`` is the magnitude at which the maximum diameter is
    reached; ``faint_magnitude`` is the magnitude at which the minimum diameter
    is reached.  Stars between the two are sized linearly.  ``bright_magnitude``
    must be numerically smaller than ``faint_magnitude``.  ``label_magnitude_limit``
    is the faintest magnitude at which a named/designated star receives a label.
    """

    min_diameter_mm: PositiveFloat
    max_diameter_mm: PositiveFloat
    bright_magnitude: float
    faint_magnitude: float
    label_magnitude_limit: float = 4.0

    @field_validator("max_diameter_mm")
    @classmethod
    def _max_not_below_min(cls, value: float, info: object) -> float:
        min_value = getattr(info, "data", {}).get("min_diameter_mm")
        if min_value is not None and value < min_value:
            raise ValueError("max_diameter_mm must be >= min_diameter_mm")
        return value

    @field_validator("faint_magnitude")
    @classmethod
    def _faint_larger_than_bright(cls, value: float, info: object) -> float:
        bright = getattr(info, "data", {}).get("bright_magnitude")
        if bright is not None and value <= bright:
            raise ValueError("faint_magnitude must be larger than bright_magnitude")
        return value


class DsoLabelTierStyle(_StrictModel):
    """Typography for one deep-sky label tier.

    ``size_factor`` multiplies the normal DSO label size; ``weight`` is
    ``normal`` or ``bold`` (``regular`` is accepted as an alias for ``normal``).
    Tiers express the visual hierarchy (Messier, Herschel 400, ordinary object)
    without changing label text.
    """

    size_factor: PositiveFloat = 1.0
    weight: Literal["normal", "bold", "regular"] = "normal"

    @field_validator("weight")
    @classmethod
    def _normalise_weight(cls, value: str) -> str:
        return "normal" if value == "regular" else value


class DsoLabelStyle(_StrictModel):
    """Deep-sky label hierarchy and base size.

    ``normal_size_pt`` is the base size for ordinary deep-sky labels; the
    per-tier ``size_factor`` values scale from it.  The tier is chosen by the
    label formatter from the object's designations and observing-list
    membership; this model only describes appearance.
    """

    normal_size_pt: PositiveFloat = 6.0
    messier: DsoLabelTierStyle = Field(
        default_factory=lambda: DsoLabelTierStyle(size_factor=1.15, weight="bold")
    )
    herschel400: DsoLabelTierStyle = Field(
        default_factory=lambda: DsoLabelTierStyle(size_factor=1.0, weight="bold")
    )
    normal: DsoLabelTierStyle = Field(default_factory=DsoLabelTierStyle)


class LabelStyle(_StrictModel):
    """Label typography and candidate generation.

    ``dso_label_magnitude_limit`` omits labels for faint deep-sky objects that
    are still rendered; ``None`` labels every selected object.  Mandatory labels
    (Messier, common name, bright DSO) and observing-list members are exempt.
    ``dso_labels`` carries the deep-sky label size/weight hierarchy.
    """

    font_family: str
    font_size_pt: PositiveFloat
    candidate_rings: int = Field(default=2, ge=1)
    ring_gap_mm: PositiveFloat = 2.5
    dso_label_magnitude_limit: float | None = None
    dso_labels: DsoLabelStyle = Field(default_factory=DsoLabelStyle)


class DsoExtentStyle(_StrictModel):
    """Symbol extent rules for one deep-sky object class, in millimetres.

    ``use_angular_size`` opts the class into true-scale symbols: when the
    catalogue carries a usable angular size it is scaled by the chart's
    ``mm_per_deg``; otherwise ``fallback_diameter_mm`` is used.  Every symbol is
    floored at ``min_diameter_mm`` for printability and, when set, capped at
    ``max_diameter_mm``.  For galaxies the diameters act on the major axis and
    the minor axis follows proportionally, preserving the catalogue position
    angle.
    """

    use_angular_size: bool = False
    fallback_diameter_mm: PositiveFloat
    min_diameter_mm: PositiveFloat
    max_diameter_mm: PositiveFloat | None = None

    @model_validator(mode="after")
    def _limits_are_consistent(self) -> DsoExtentStyle:
        if self.min_diameter_mm > self.fallback_diameter_mm:
            raise ValueError("min_diameter_mm must be <= fallback_diameter_mm")
        if self.max_diameter_mm is not None and self.max_diameter_mm < self.min_diameter_mm:
            raise ValueError("max_diameter_mm must be >= min_diameter_mm")
        return self


def _extent(
    *,
    fallback_diameter_mm: float,
    min_diameter_mm: float,
    max_diameter_mm: float | None = None,
    use_angular_size: bool = False,
) -> DsoExtentStyle:
    return DsoExtentStyle(
        use_angular_size=use_angular_size,
        fallback_diameter_mm=fallback_diameter_mm,
        min_diameter_mm=min_diameter_mm,
        max_diameter_mm=max_diameter_mm,
    )


class DsoStyle(_StrictModel):
    """Deep-sky symbol appearance, in millimetres.

    Symbol size is centralised in
    :func:`nightsky_atlas.render.symbols.dso_symbol_extent`, which reads the
    per-class :class:`DsoExtentStyle` blocks below.  ``use_angular_size`` is
    enabled for galaxies, globular clusters and open clusters; the remaining
    classes are semantic fixed-size symbols until individually reviewed, but
    already carry their own fallback/minimum sizes.  ``bold_line_width_mm`` is
    the heavier stroke used for emphasized symbols (Messier, Herschel 400), so
    the map mark is bold whenever the label is.  Outline fields control the
    schematic stroke drawn around extended objects that have an authored
    outline.
    """

    line_width_mm: PositiveFloat = 0.15
    bold_line_width_mm: PositiveFloat = 0.3
    dash_mm: PositiveFloat = 0.4
    outline_line_width_mm: PositiveFloat = 0.18
    outline_dash_mm: PositiveFloat = 0.8
    outline_gray: float = 0.45

    galaxy: DsoExtentStyle = Field(
        default_factory=lambda: _extent(
            fallback_diameter_mm=1.4,
            min_diameter_mm=0.7,
            max_diameter_mm=12.0,
            use_angular_size=True,
        )
    )
    globular_cluster: DsoExtentStyle = Field(
        default_factory=lambda: _extent(
            fallback_diameter_mm=1.5,
            min_diameter_mm=1.2,
            max_diameter_mm=20.0,
            use_angular_size=True,
        )
    )
    open_cluster: DsoExtentStyle = Field(
        default_factory=lambda: _extent(
            fallback_diameter_mm=2.0,
            min_diameter_mm=1.4,
            max_diameter_mm=30.0,
            use_angular_size=True,
        )
    )
    planetary_nebula: DsoExtentStyle = Field(
        default_factory=lambda: _extent(fallback_diameter_mm=1.4, min_diameter_mm=1.0)
    )
    bright_nebula: DsoExtentStyle = Field(
        default_factory=lambda: _extent(fallback_diameter_mm=1.6, min_diameter_mm=1.2)
    )
    dark_nebula: DsoExtentStyle = Field(
        default_factory=lambda: _extent(fallback_diameter_mm=1.6, min_diameter_mm=1.2)
    )
    galaxy_cluster: DsoExtentStyle = Field(
        default_factory=lambda: _extent(fallback_diameter_mm=1.6, min_diameter_mm=1.2)
    )
    other: DsoExtentStyle = Field(
        default_factory=lambda: _extent(fallback_diameter_mm=1.4, min_diameter_mm=1.0)
    )

    @field_validator("bold_line_width_mm")
    @classmethod
    def _bold_not_thinner_than_normal(cls, value: float, info: object) -> float:
        normal = getattr(info, "data", {}).get("line_width_mm")
        if normal is not None and value < normal:
            raise ValueError("bold_line_width_mm must be >= line_width_mm")
        return value

    def extent_style(self, object_type: DsoType) -> DsoExtentStyle:
        """Return the extent rules for a deep-sky object class.

        Classes without a dedicated block (stars, double stars, unknown types)
        fall back to ``other``.
        """
        if object_type == DsoType.GALAXY:
            return self.galaxy
        if object_type == DsoType.GLOBULAR_CLUSTER:
            return self.globular_cluster
        if object_type == DsoType.OPEN_CLUSTER:
            return self.open_cluster
        if object_type == DsoType.PLANETARY_NEBULA:
            return self.planetary_nebula
        if object_type == DsoType.BRIGHT_NEBULA:
            return self.bright_nebula
        if object_type == DsoType.DARK_NEBULA:
            return self.dark_nebula
        if object_type == DsoType.GALAXY_CLUSTER:
            return self.galaxy_cluster
        return self.other


class DoubleStarStyle(_StrictModel):
    """Visual double/multiple star symbol behaviour.

    Whether a pair is drawn as one symbol plus a marker or as two separate
    components is decided by its separation **on the printed page**, not by a
    fixed angular distance.  ``min_component_separation_mm`` is the page
    distance above which the two components are plotted separately; below it
    the pair collapses to one symbol carrying the combined magnitude and a
    short horizontal marker.

    The marker scales with the printed star: its length is
    ``marker_length_factor`` times the symbol diameter, never shorter than
    ``min_marker_length_mm``.  ``companion_magnitude_limit`` keeps the chart
    selective: a system is only marked when a companion star is actually
    plotted or the catalogued companion is bright enough to observe.  The
    marker is a cartographic symbol only and does **not** encode the real
    position angle.
    """

    enabled: bool = True
    min_component_separation_mm: PositiveFloat = 0.7
    marker_length_factor: PositiveFloat = 1.8
    min_marker_length_mm: PositiveFloat = 0.8
    marker_line_width_mm: PositiveFloat = 0.15
    companion_magnitude_limit: float = 9.0


class GridStyle(_StrictModel):
    """Coordinate grid appearance and spacing.

    The grid is furniture, not sky content: it has lower visual priority than
    labels and may be clipped (``AGENTS.md`` sections 14.4 and 16).

    Grid *lines* use ``ra_step_deg`` / ``dec_step_deg``.  On a polar field,
    where the celestial pole lies at or just outside the frame and every
    meridian crosses the chart, ``polar_ra_step_deg`` replaces ``ra_step_deg``
    for the meridians so the converging fan stays legible.  Edge *labels* are
    independent furniture; ``label_ra_step_deg`` and ``label_dec_step_deg``
    select which grid lines carry a label.  A label step must be a whole
    multiple of the corresponding line step so that a labelled value is always
    an actual grid line; ``None`` labels every line.

    ``label_placement`` controls where those labels sit relative to the chart
    frame: ``inside`` places them in the margin band within the frame,
    ``outside`` places them beyond the frame (RA against the top/bottom page
    margin, Dec against the left/right page margin).

    Grid *lines* and coordinate *labels* are independent: a fine grid may carry
    a much sparser label set.  ``label_min_spacing_mm`` is the smallest physical
    distance two labels may have along the same page edge; when grid lines
    crowd together (meridians converging toward a pole, or a field far from the
    inner chart) the renderer automatically skips every second/third/... line so
    the printed labels keep breathing room.  A value of ``0`` disables the rule.
    """

    enabled: bool = True
    ra_step_deg: PositiveFloat = 2.0
    dec_step_deg: PositiveFloat = 2.0
    polar_ra_step_deg: PositiveFloat = 10.0
    line_width_mm: PositiveFloat = 0.1
    gray: float = 0.8
    labels_enabled: bool = True
    label_placement: Literal["inside", "outside"] = "inside"
    label_font_size_pt: PositiveFloat = 5.0
    label_gray: float = 0.35
    label_padding_mm: PositiveFloat = 1.5
    label_min_spacing_mm: NonNegativeFloat = 13.0
    label_ra_step_deg: PositiveFloat | None = None
    label_dec_step_deg: PositiveFloat | None = None
    label_polar_ra_step_deg: PositiveFloat | None = 30.0

    @model_validator(mode="after")
    def _label_steps_align_with_lines(self) -> GridStyle:
        for label_name, line_name in (
            ("label_ra_step_deg", "ra_step_deg"),
            ("label_dec_step_deg", "dec_step_deg"),
            ("label_polar_ra_step_deg", "polar_ra_step_deg"),
        ):
            label_step = getattr(self, label_name)
            if label_step is None:
                continue
            line_step = getattr(self, line_name)
            ratio = label_step / line_step
            if ratio < 1.0 or abs(ratio - round(ratio)) > 1e-6:
                raise ValueError(
                    f"{label_name} ({label_step:g}) must be a whole multiple of "
                    f"{line_name} ({line_step:g})"
                )
        return self


class ConstellationLineStyle(_StrictModel):
    """Stick-figure constellation line appearance.

    Lines are drawn straight in the two-dimensional chart plane (symbolic
    connections, not great circles).  At a segment endpoint the line is
    shortened by the plotted star's radius plus ``star_gap_extra_mm`` so it does
    not run under the symbol to its centre; ``star_match_tolerance_mm`` is the
    page distance within which an endpoint is treated as that star.
    """

    enabled: bool = True
    gray: float = 0.5
    line_width_mm: PositiveFloat = 0.22
    star_gap_extra_mm: NonNegativeFloat = 0.2
    star_match_tolerance_mm: PositiveFloat = 0.6


class ConstellationBoundaryStyle(_StrictModel):
    """Dotted constellation boundary appearance."""

    enabled: bool = True
    gray: float = 0.82
    line_width_mm: PositiveFloat = 0.1
    dash_mm: PositiveFloat = 1.0
    gap_mm: PositiveFloat = 1.2


class ConstellationStyle(_StrictModel):
    """Constellation line and boundary appearance."""

    lines: ConstellationLineStyle = Field(default_factory=ConstellationLineStyle)
    boundaries: ConstellationBoundaryStyle = Field(default_factory=ConstellationBoundaryStyle)


class ScaleBarStyle(_StrictModel):
    """Subtle linear angular scale drawn in the page footer.

    The bar is deliberately quiet: a thin mid-grey line with short end ticks and
    a compact ``5°`` label, sized so that its physical length stays roughly
    constant across editions even though the angular value differs.
    """

    enabled: bool = True
    length_deg: PositiveFloat = 5.0
    thickness_mm: PositiveFloat = 0.15
    gray: float = 0.5
    font_size_pt: PositiveFloat = 6.5
    tick_mm: PositiveFloat = 1.2


class NavigationStyle(_StrictModel):
    """Adjacent-chart navigation references.

    Navigation sits outside the chart frame, further out than the coordinate
    labels, is smaller and mid-grey, and always prints short chart codes.  It is
    purely navigational furniture and is drawn beneath nothing sky-related.
    """

    enabled: bool = True
    font_size_pt: PositiveFloat = 5.0
    gray: float = 0.5
    frame_gap_mm: PositiveFloat = 4.2
    side_inset_mm: PositiveFloat = 2.0


class MagnitudeLegendStyle(_StrictModel):
    """Compact star-magnitude reference for the footer.

    The reference dots use the same :class:`StarSizeModel` as the chart, so the
    legend shows the real printed symbol sizes rather than a symbolic redraw.
    """

    enabled: bool = True
    magnitudes: tuple[float, ...] = (2.0, 4.0, 6.0, 8.0)
    font_size_pt: PositiveFloat = 6.0
    gray: float = 0.55
    spacing_mm: PositiveFloat = 6.0
    label: str = "mag"

    @field_validator("magnitudes")
    @classmethod
    def _at_least_one(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        if not value:
            raise ValueError("magnitude legend needs at least one reference value")
        return value


class FurnitureStyle(_StrictModel):
    """Chart title/footer, scale bar, magnitude legend and navigation styling."""

    title_font_size_pt: PositiveFloat = 8.0
    title_gray: float = 0.15
    chart_border_width_mm: PositiveFloat = 0.25
    scale_bar: ScaleBarStyle = Field(default_factory=ScaleBarStyle)
    navigation: NavigationStyle = Field(default_factory=NavigationStyle)
    magnitude_legend: MagnitudeLegendStyle = Field(default_factory=MagnitudeLegendStyle)


class StyleConfig(_StrictModel):
    """Visual appearance configuration for one style."""

    id: str
    star: StarStyle
    label: LabelStyle
    dso: DsoStyle = Field(default_factory=DsoStyle)
    double_stars: DoubleStarStyle = Field(default_factory=DoubleStarStyle)
    grid: GridStyle = Field(default_factory=GridStyle)
    constellation: ConstellationStyle = Field(default_factory=ConstellationStyle)
    furniture: FurnitureStyle = Field(default_factory=FurnitureStyle)


def _load_yaml_mapping(path: Path) -> dict[str, object]:
    if not path.exists():
        raise ConfigError(f"configuration file not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {path}: {exc}") from exc
    if raw is None:
        raise ConfigError(f"configuration file is empty: {path}")
    if not isinstance(raw, dict):
        raise ConfigError(f"configuration root must be a mapping: {path}")
    return raw


def load_atlas_config(path: str | Path) -> AtlasConfig:
    """Load and validate an atlas edition definition from a YAML file."""
    mapping = _load_yaml_mapping(Path(path))
    try:
        return AtlasConfig.model_validate(mapping)
    except ValidationError as exc:
        raise ConfigError(f"invalid atlas configuration {path}:\n{exc}") from exc


def load_style_config(path: str | Path) -> StyleConfig:
    """Load and validate a rendering style definition from a YAML file."""
    mapping = _load_yaml_mapping(Path(path))
    try:
        return StyleConfig.model_validate(mapping)
    except ValidationError as exc:
        raise ConfigError(f"invalid style configuration {path}:\n{exc}") from exc
