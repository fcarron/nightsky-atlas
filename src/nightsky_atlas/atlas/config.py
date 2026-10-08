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

import math
from pathlib import Path
from typing import Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeFloat,
    PositiveFloat,
    PositiveInt,
    ValidationError,
    field_validator,
    model_validator,
)

from nightsky_atlas.catalog.galaxy_visibility import GalaxyContourClass
from nightsky_atlas.catalog.models import DsoType
from nightsky_atlas.catalog.visibility import VisibilityLimits
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry

__all__ = [
    "AtlasConfig",
    "ChartConfig",
    "ConfigError",
    "ConstellationBoundaryStyle",
    "ConstellationLineStyle",
    "ConstellationNameStyle",
    "ConstellationStyle",
    "DoubleStarStyle",
    "DoubleStarPairLimit",
    "DsoExtentStyle",
    "DsoLabelPlacementStyle",
    "DsoLabelStyle",
    "DsoLabelTierStyle",
    "DetailChartConfig",
    "DsoStyle",
    "EditionConfig",
    "FurnitureStyle",
    "GalaxyContourSet",
    "GalaxyContourStyle",
    "GridStyle",
    "EclipticStyle",
    "LabelSelectionStyle",
    "LabelStyle",
    "LocatorStyle",
    "MagnitudeLegendStyle",
    "MilkyWayStyle",
    "NavigationStyle",
    "OverlapTargetConfig",
    "OverviewStyle",
    "PageConfig",
    "ScaleBarStyle",
    "StyleConfig",
    "TilingConfig",
    "TypographyStyle",
    "VisibilityConfig",
    "VariableStarStyle",
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


class DetailChartConfig(_StrictModel):
    """A supplementary zoom chart with its own scale and edition star profile."""

    id: str
    code: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    name: str
    parent_chart_id: str
    center_ra_deg: float
    center_dec_deg: float
    width_deg: PositiveFloat
    height_deg: PositiveFloat
    mm_per_degree: PositiveFloat
    star_profile: Literal["pocket", "standard", "deep", "deep_detail", "deep_detail_40"] = "deep"
    fallback_parent_galaxy_labels: bool = False
    fallback_parent_min_magnitude: float | None = None
    fallback_parent_min_nearby_galaxies: int = Field(default=0, ge=0)
    parent_marker_label: str | None = None

    @field_validator("id", "name", "parent_chart_id")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("detail-chart id, name and parent chart must not be blank")
        return value

    @field_validator("center_ra_deg", "center_dec_deg")
    @classmethod
    def _finite_coordinates(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("detail-chart coordinates must be finite")
        return value

    @field_validator("center_dec_deg")
    @classmethod
    def _declination_range(cls, value: float) -> float:
        if not -90.0 <= value <= 90.0:
            raise ValueError("detail-chart declination must lie in [-90, 90]")
        return value

    def to_definition(self, *, atlas_id: str) -> ChartDefinition:
        return ChartDefinition(
            id=self.id,
            center_ra_deg=self.center_ra_deg,
            center_dec_deg=self.center_dec_deg,
            width_deg=self.width_deg,
            height_deg=self.height_deg,
            atlas_id=atlas_id,
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
    target_overlap_mm: PositiveFloat | None = None
    mm_per_degree: PositiveFloat | None = None
    coverage_step_deg: PositiveFloat = 1.0

    declination_centers: tuple[float, ...] = ()
    chart_counts: tuple[int, ...] = ()
    polar_caps: bool = False
    target_overlap: OverlapTargetConfig = Field(default_factory=OverlapTargetConfig)
    stagger_ra_centers: bool = False
    auto_adjust_counts: bool = True

    @model_validator(mode="after")
    def _validate_tiling(self) -> TilingConfig:
        if (self.target_overlap_mm is None) != (self.mm_per_degree is None):
            raise ValueError("target_overlap_mm and mm_per_degree must be specified together")
        if self.target_overlap_mm is not None and self.overlap_deg is not None:
            raise ValueError("use either overlap_deg or target_overlap_mm, not both")
        if (
            self.target_overlap_mm is not None
            and self.target_overlap_mm / self.mm_per_degree >= min(self.width_deg, self.height_deg)
        ):
            raise ValueError("physical overlap must be smaller than the chart field")
        if (
            self.overlap_deg is None
            and self.target_overlap_mm is None
            and not self.declination_centers
        ):
            raise ValueError(
                "tiling requires either overlap_deg (band mode) or declination_centers (ring mode)"
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
            raise ValueError("chart_counts must have one entry per declination_center")
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
    # Render every genuine deep-sky object in the catalogue, ignoring the
    # per-type limits above.  ``star``/``double_star`` entries stay excluded.
    include_all: bool = False

    @model_validator(mode="after")
    def _references_sit_inside_limits(self) -> VisibilityConfig:
        if self.reference_magnitude >= self.integrated_magnitude_limit:
            raise ValueError("reference_magnitude must be brighter than integrated_magnitude_limit")
        if self.reference_surface_brightness >= self.surface_brightness_limit:
            raise ValueError(
                "reference_surface_brightness must be darker than surface_brightness_limit"
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
            include_all=self.include_all,
        )


class EditionConfig(_StrictModel):
    """Visible identity of an atlas edition.

    ``name`` is used on edition-level pages and ``code`` is the short visible
    prefix used for chart codes and navigation (``S``). Internal identifiers
    keep the full lowercase edition id (``standard-068``).
    """

    name: str
    code: str
    chart_index_width: PositiveInt = 3

    @field_validator("name", "code")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("edition name and code must not be blank")
        return value


_EDITION_DEFAULTS: dict[str, EditionConfig] = {
    "pocket": EditionConfig(name="Pocket", code="P", chart_index_width=2),
    "standard": EditionConfig(name="Standard", code="S"),
    "deep": EditionConfig(name="Deep", code="D"),
}


def default_edition(edition_id: str) -> EditionConfig:
    """Return the built-in visible edition identity for an atlas id.

    This is the single edition registry: both :meth:`AtlasConfig.resolved_edition`
    and the chart presentation layer read it, so the printed names and codes
    cannot drift apart.
    """
    return _EDITION_DEFAULTS.get(
        edition_id,
        EditionConfig(name=edition_id.title(), code=edition_id[:1].upper() or "?"),
    )


class AtlasConfig(_StrictModel):
    """An atlas edition: page geometry plus explicit chart definitions."""

    id: str
    page: PageConfig
    edition: EditionConfig | None = None
    charts: list[ChartConfig] = Field(default_factory=list)
    detail_charts: tuple[DetailChartConfig, ...] = ()
    tiling: TilingConfig | None = None
    chart_directory_position: Literal["front", "back"] = "front"
    mm_per_degree: PositiveFloat | None = None
    stellar_limit_magnitude: PositiveFloat | None = None
    visibility: VisibilityConfig = Field(default_factory=VisibilityConfig)

    @model_validator(mode="after")
    def _configured_scale_fits_page(self) -> AtlasConfig:
        page = self.page.to_geometry()
        if self.mm_per_degree is not None:
            fields = [(chart.width_deg, chart.height_deg) for chart in self.charts]
            if self.tiling is not None:
                fields.append((self.tiling.width_deg, self.tiling.height_deg))
            for width_deg, height_deg in fields:
                if (
                    width_deg * self.mm_per_degree > page.printable_width_mm + 1e-9
                    or height_deg * self.mm_per_degree > page.printable_height_mm + 1e-9
                ):
                    raise ValueError("mm_per_degree makes a chart field exceed the printable page")
        detail_ids = [detail.id for detail in self.detail_charts]
        detail_codes = [detail.code for detail in self.detail_charts]
        if len(detail_ids) != len(set(detail_ids)):
            raise ValueError("detail chart IDs must be unique")
        if len(detail_codes) != len(set(detail_codes)):
            raise ValueError("detail chart PDF codes must be unique")
        for detail in self.detail_charts:
            if (
                detail.width_deg * detail.mm_per_degree > page.printable_width_mm + 1e-9
                or detail.height_deg * detail.mm_per_degree > page.printable_height_mm + 1e-9
            ):
                raise ValueError(
                    f"detail chart {detail.id!r} scale makes its field exceed the printable page"
                )
        return self

    def resolved_edition(self) -> EditionConfig:
        """Return the visible edition identity, falling back to the registry."""
        if self.edition is not None:
            return self.edition
        return default_edition(self.id)


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
    close_overlap_halo_mm: NonNegativeFloat = 0.12
    diameter_curve: tuple[tuple[float, PositiveFloat], ...] = ()

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

    @model_validator(mode="after")
    def _validate_diameter_curve(self) -> StarStyle:
        if not self.diameter_curve:
            return self
        magnitudes = [point[0] for point in self.diameter_curve]
        diameters = [point[1] for point in self.diameter_curve]
        if any(right <= left for left, right in zip(magnitudes, magnitudes[1:], strict=False)):
            raise ValueError("star diameter_curve magnitudes must be strictly ascending")
        if any(right > left for left, right in zip(diameters, diameters[1:], strict=False)):
            raise ValueError("star diameter_curve diameters must be monotonically non-increasing")
        if magnitudes[-1] < self.faint_magnitude:
            raise ValueError("star diameter_curve must reach faint_magnitude")
        return self


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
    common_name_display: Literal["none", "iconic"] = "none"
    common_name_neighbor_radius_mm: PositiveFloat = 8.0
    common_name_max_neighbors: int = Field(default=5, ge=0)
    messier: DsoLabelTierStyle = Field(
        default_factory=lambda: DsoLabelTierStyle(size_factor=1.0, weight="bold")
    )
    herschel400: DsoLabelTierStyle = Field(
        default_factory=lambda: DsoLabelTierStyle(size_factor=1.0, weight="bold")
    )
    normal: DsoLabelTierStyle = Field(default_factory=DsoLabelTierStyle)


class LabelSelectionStyle(_StrictModel):
    """Deterministic label selection before placement.

    Candidate labels are ranked by priority and thinned only where local
    printed-label density exceeds the configured budget. DSO budgets are more
    permissive than stellar-label budgets. Messier and Herschel 400 labels are
    mandatory regardless of density. This is a local rule, not a global quota.
    """

    enabled: bool = True
    density_radius_mm: PositiveFloat = 15.0
    medium_density_budget: PositiveFloat = 0.12
    low_density_budget: PositiveFloat = 0.05
    dso_medium_density_budget: PositiveFloat = 0.35
    dso_low_density_budget: PositiveFloat = 0.25
    dso_dense_start_neighbors: int = Field(default=6, ge=0)
    dso_dense_full_neighbors: int = Field(default=12, ge=1)
    always_label_object_types: tuple[DsoType, ...] = ()

    @model_validator(mode="after")
    def _validate_dso_density_transition(self) -> LabelSelectionStyle:
        if self.dso_dense_full_neighbors <= self.dso_dense_start_neighbors:
            raise ValueError("dso_dense_full_neighbors must exceed dso_dense_start_neighbors")
        return self


class StarDesignationStyle(_StrictModel):
    enabled: bool = True
    max_magnitude: float = 5.5


class ProperNameTierStyle(_StrictModel):
    core: bool = True
    standard: bool = True
    extended: bool = False


class ConstellationSuffixStyle(_StrictModel):
    default: bool = True
    allow_ambiguity_fallback: bool = False
    ambiguity_radius_mm: PositiveFloat = 18.0


class StarLabelStyle(_StrictModel):
    proper_names: ProperNameTierStyle = Field(default_factory=ProperNameTierStyle)
    bayer: StarDesignationStyle = Field(default_factory=StarDesignationStyle)
    flamsteed: StarDesignationStyle = Field(
        default_factory=lambda: StarDesignationStyle(max_magnitude=5.0)
    )
    variables: StarDesignationStyle = Field(
        default_factory=lambda: StarDesignationStyle(max_magnitude=6.5)
    )
    combined_names: bool = False
    proper_names_always_visible: bool = False
    proper_name_candidate_rings: int = Field(default=3, ge=1)
    candidate_ring_gap_mm: PositiveFloat = 1.25
    constellation_suffix: ConstellationSuffixStyle = Field(default_factory=ConstellationSuffixStyle)


class TargetedDsoLeaderStyle(_StrictModel):
    enabled: bool = False
    min_ink_width_mm: PositiveFloat = 8.0
    min_ink_aspect_ratio: PositiveFloat = 4.0
    min_competing_owner_cost: PositiveFloat = 1.0
    max_length_mm: PositiveFloat = 3.0


class LeaderLineStyle(_StrictModel):
    """Physical drawing and eligibility rules for exceptional DSO callouts."""

    enabled: bool = True
    auto_min_ring: int = Field(default=2, ge=1)
    star_ambiguity_threshold: PositiveFloat = 4.0
    dso_ambiguity_threshold: PositiveFloat = 2.5
    dso_min_length_mm: PositiveFloat = 0.75
    dso_preferred_gap_mm: PositiveFloat = 2.5
    dso_candidate_max_gap_mm: PositiveFloat = 2.5
    dso_length_weight: NonNegativeFloat = 4.0
    dso_association_residual_factor: float = Field(default=0.10, ge=0.0, le=1.0)
    min_length_mm: PositiveFloat = 2.5
    max_length_mm: PositiveFloat = 12.0
    symbol_gap_mm: PositiveFloat = 0.25
    label_gap_mm: PositiveFloat = 0.4
    width_mm: PositiveFloat = 0.12
    gray: float = Field(default=0.4, ge=0.0, le=1.0)
    targeted_dso: TargetedDsoLeaderStyle = Field(default_factory=TargetedDsoLeaderStyle)


class ForeignStarClearanceStyle(_StrictModel):
    """Optical text clearance for stars unrelated to a label target."""

    hard_min_mm: NonNegativeFloat = 0.05
    hard_radius_mm: PositiveFloat = 0.75
    soft_clear_mm: PositiveFloat = 0.35
    radius_clearance_factor: NonNegativeFloat = 1.0
    importance_reference_radius_mm: PositiveFloat = 0.6
    maximum_importance: PositiveFloat = 2.0
    weight: NonNegativeFloat = 10.0

    @model_validator(mode="after")
    def _soft_clear_not_below_hard_minimum(self) -> ForeignStarClearanceStyle:
        maximum_soft_clearance = (
            self.soft_clear_mm + self.hard_radius_mm * self.radius_clearance_factor
        )
        if self.hard_min_mm > maximum_soft_clearance:
            raise ValueError("hard_min_mm exceeds the bright-star soft clearance")
        return self


class AssociatedStarClearanceStyle(_StrictModel):
    """Clearance and association-distance rules for a star's own label."""

    hard_min_mm: NonNegativeFloat = 0.35
    soft_clear_mm: PositiveFloat = 0.45
    preferred_min_mm: PositiveFloat = 0.45
    clearance_weight: NonNegativeFloat = 8.0
    preferred_max_mm: PositiveFloat = 0.75
    distance_weight: NonNegativeFloat = 9.0

    @model_validator(mode="after")
    def _associated_soft_clear_not_below_hard_minimum(self) -> AssociatedStarClearanceStyle:
        if self.soft_clear_mm < self.hard_min_mm:
            raise ValueError("soft_clear_mm must be >= hard_min_mm")
        if not self.soft_clear_mm <= self.preferred_min_mm <= self.preferred_max_mm:
            raise ValueError("preferred own-star range must begin after the clean clearance")
        return self


class StarLabelClearanceStyle(_StrictModel):
    """Physical optical-clearance policy for labels around rendered stars."""

    foreign: ForeignStarClearanceStyle = Field(default_factory=ForeignStarClearanceStyle)
    associated: AssociatedStarClearanceStyle = Field(default_factory=AssociatedStarClearanceStyle)


class SourceAssociationStyle(_StrictModel):
    """Physical scoring for visually unambiguous source-to-label ownership."""

    preferred_min_gap_mm: NonNegativeFloat = 0.35
    preferred_max_gap_mm: PositiveFloat = 1.0
    distance_weight: NonNegativeFloat = 12.0
    corridor_margin_mm: NonNegativeFloat = 0.25
    corridor_weight: NonNegativeFloat = 18.0
    ambiguity_margin_mm: NonNegativeFloat = 0.75
    ambiguity_weight: NonNegativeFloat = 20.0
    competing_owner_weight: NonNegativeFloat = 26.0
    foreign_object_clear_mm: PositiveFloat = 0.8
    foreign_object_weight: NonNegativeFloat = 8.0
    glyph_clear_mm: PositiveFloat = 0.75
    glyph_inline_factor: PositiveFloat = 5.0
    whitespace_factor: PositiveFloat = 1.5
    glyph_weight: NonNegativeFloat = 120.0
    compact_label_factor: PositiveFloat = 1.35

    @model_validator(mode="after")
    def _preferred_gap_is_ordered(self) -> SourceAssociationStyle:
        if self.preferred_min_gap_mm > self.preferred_max_gap_mm:
            raise ValueError("preferred source gap minimum must not exceed maximum")
        return self


class DsoLabelPlacementStyle(_StrictModel):
    """Dense-field DSO candidate sampling and bounded local search policy."""

    candidate_edge_gaps_mm: tuple[PositiveFloat, ...] = (
        0.35,
        0.55,
        0.80,
        1.10,
        1.50,
        2.00,
        3.00,
        4.50,
        6.00,
    )
    candidate_directions: Literal[8, 16] = 16
    outer_candidate_directions: Literal[8, 16] = 8
    outer_candidate_start_gap_mm: PositiveFloat = 3.00
    preferred_max_gap_mm: PositiveFloat = 0.80
    long_gap_knee_mm: PositiveFloat = 1.20
    long_gap_curve_factor: NonNegativeFloat = 2.50
    direct_gap_expensive_mm: PositiveFloat = 1.8
    direct_gap_extra_weight: NonNegativeFloat = 8.0
    ownership_margin_preferred_mm: PositiveFloat = 0.75
    ownership_margin_hard_limit_mm: float = Field(default=0.0, le=0.0)
    ownership_margin_weight: NonNegativeFloat = 48.0
    compact_label_factor: PositiveFloat = 1.35
    label_label_ink_clearance_mm: NonNegativeFloat | None = 0.20
    joint_max_component_labels: int = Field(default=8, ge=2)
    joint_beam_width: int = Field(default=24, ge=1)
    joint_node_budget: int = Field(default=24000, ge=1)
    hard_repair_neighborhood_labels: int = Field(default=6, ge=2, le=8)
    hard_repair_search_limit: int = Field(default=45, ge=1)

    @field_validator("candidate_edge_gaps_mm")
    @classmethod
    def _candidate_gaps_are_ascending(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        if not value or any(right <= left for left, right in zip(value, value[1:], strict=False)):
            raise ValueError("candidate_edge_gaps_mm must be strictly ascending")
        return value

    @model_validator(mode="after")
    def _outer_candidate_start_is_present(self) -> DsoLabelPlacementStyle:
        if self.outer_candidate_start_gap_mm not in self.candidate_edge_gaps_mm:
            raise ValueError("outer_candidate_start_gap_mm must occur in candidate_edge_gaps_mm")
        return self


class LabelStyle(_StrictModel):
    """Label typography and candidate generation.

    ``dso_label_magnitude_limit`` omits labels for faint deep-sky objects that
    are still rendered; ``None`` labels every selected object.  Mandatory labels
    (Messier, common name, bright DSO) and observing-list members are exempt.
    ``dso_labels`` carries the deep-sky label size/weight hierarchy.
    ``selection`` controls which candidate labels survive to placement,
    including object types that must request a label whenever rendered.
    """

    font_family: str
    font_size_pt: PositiveFloat
    candidate_rings: int = Field(default=2, ge=1)
    ring_gap_mm: PositiveFloat = 2.5
    star_clearance: StarLabelClearanceStyle = Field(default_factory=StarLabelClearanceStyle)
    source_association: SourceAssociationStyle = Field(default_factory=SourceAssociationStyle)
    dso_placement: DsoLabelPlacementStyle = Field(default_factory=DsoLabelPlacementStyle)
    leader_lines: LeaderLineStyle = Field(default_factory=LeaderLineStyle)
    dso_label_magnitude_limit: float | None = None
    dso_labels: DsoLabelStyle = Field(default_factory=DsoLabelStyle)
    star_labels: StarLabelStyle = Field(default_factory=StarLabelStyle)
    selection: LabelSelectionStyle = Field(default_factory=LabelSelectionStyle)


class DsoExtentStyle(_StrictModel):
    """Symbol extent rules for one deep-sky object class, in millimetres.

    ``use_angular_size`` opts the class into true-scale symbols: when the
    catalogue carries a usable angular size it is scaled by the chart's
    ``mm_per_deg``; otherwise ``fallback_diameter_mm`` is used.  Every symbol is
    floored at ``min_diameter_mm`` for printability and, when set, capped at
    ``max_diameter_mm``. For galaxies ``min_angular_major_axis_arcmin`` is a
    cartographic angular floor; the minor axis retains the catalogue axis
    ratio rather than inflating the whole ellipse to meet a minor-axis floor.
    """

    use_angular_size: bool = False
    fallback_diameter_mm: PositiveFloat
    min_diameter_mm: PositiveFloat
    max_diameter_mm: PositiveFloat | None = None
    min_angular_major_axis_arcmin: PositiveFloat | None = None
    min_angular_size_arcmin: PositiveFloat | None = None

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
    min_angular_major_axis_arcmin: float | None = None,
    min_angular_size_arcmin: float | None = None,
    use_angular_size: bool = False,
) -> DsoExtentStyle:
    return DsoExtentStyle(
        use_angular_size=use_angular_size,
        fallback_diameter_mm=fallback_diameter_mm,
        min_diameter_mm=min_diameter_mm,
        max_diameter_mm=max_diameter_mm,
        min_angular_major_axis_arcmin=min_angular_major_axis_arcmin,
        min_angular_size_arcmin=min_angular_size_arcmin,
    )


class GalaxyContourStyle(_StrictModel):
    """Stroke of a galaxy contour for one visibility class, in millimetres.

    ``dash_mm`` of ``0`` draws a solid contour; a positive value draws a short
    dash pattern and ``gap_mm`` defaults to ``dash_mm``.  These are print
    defaults for the Crumey-based galaxy classification: ``dotted`` uses a short
    dash rather than isolated dots so small galaxy symbols stay visible in the
    PDF.  ``unclassified`` galaxies keep the neutral deep-sky fallback stroke.
    """

    line_width_mm: PositiveFloat
    dash_mm: NonNegativeFloat = 0.0
    gap_mm: PositiveFloat | None = None

    @model_validator(mode="after")
    def _gap_requires_dash(self) -> GalaxyContourStyle:
        if self.gap_mm is not None and self.dash_mm <= 0.0:
            raise ValueError("gap_mm requires a positive dash_mm")
        return self


class GalaxyContourSet(_StrictModel):
    """Per-class galaxy contour strokes for the Crumey visibility classes."""

    bold: GalaxyContourStyle = Field(
        default_factory=lambda: GalaxyContourStyle(line_width_mm=0.176)
    )
    normal: GalaxyContourStyle = Field(
        default_factory=lambda: GalaxyContourStyle(line_width_mm=0.106)
    )
    fine: GalaxyContourStyle = Field(
        default_factory=lambda: GalaxyContourStyle(line_width_mm=0.071)
    )
    dotted: GalaxyContourStyle = Field(
        default_factory=lambda: GalaxyContourStyle(line_width_mm=0.088, dash_mm=0.4, gap_mm=0.35)
    )

    def for_class(self, contour_class: GalaxyContourClass | None) -> GalaxyContourStyle | None:
        """Return the stroke for a contour class, or ``None`` for the fallback."""
        if contour_class is None or contour_class == GalaxyContourClass.UNCLASSIFIED:
            return None
        return {
            GalaxyContourClass.BOLD: self.bold,
            GalaxyContourClass.NORMAL: self.normal,
            GalaxyContourClass.FINE: self.fine,
            GalaxyContourClass.DOTTED: self.dotted,
        }[contour_class]


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
    star_overlap_halo_mm: PositiveFloat = 0.12
    star_overlap_magnitude_limit: float = 4.5
    star_overlap_knockout_max_diameter_mm: PositiveFloat = 3.0

    galaxy: DsoExtentStyle = Field(
        default_factory=lambda: _extent(
            fallback_diameter_mm=1.4,
            min_diameter_mm=0.7,
            max_diameter_mm=12.0,
            min_angular_major_axis_arcmin=10.0,
            use_angular_size=True,
        )
    )
    globular_cluster: DsoExtentStyle = Field(
        default_factory=lambda: _extent(
            fallback_diameter_mm=1.5,
            min_diameter_mm=1.2,
            max_diameter_mm=20.0,
            min_angular_size_arcmin=10.0,
            use_angular_size=True,
        )
    )
    open_cluster: DsoExtentStyle = Field(
        default_factory=lambda: _extent(
            fallback_diameter_mm=2.0,
            min_diameter_mm=1.4,
            max_diameter_mm=30.0,
            min_angular_size_arcmin=10.0,
            use_angular_size=True,
        )
    )
    planetary_nebula: DsoExtentStyle = Field(
        default_factory=lambda: _extent(
            fallback_diameter_mm=1.4,
            min_diameter_mm=1.0,
            min_angular_size_arcmin=10.0,
        )
    )
    bright_nebula: DsoExtentStyle = Field(
        default_factory=lambda: _extent(
            fallback_diameter_mm=1.6,
            min_diameter_mm=1.2,
            min_angular_size_arcmin=10.0,
        )
    )
    dark_nebula: DsoExtentStyle = Field(
        default_factory=lambda: _extent(
            fallback_diameter_mm=1.6,
            min_diameter_mm=1.2,
            min_angular_size_arcmin=10.0,
        )
    )
    galaxy_cluster: DsoExtentStyle = Field(
        default_factory=lambda: _extent(
            fallback_diameter_mm=1.6,
            min_diameter_mm=1.2,
            min_angular_size_arcmin=10.0,
        )
    )
    other: DsoExtentStyle = Field(
        default_factory=lambda: _extent(fallback_diameter_mm=1.4, min_diameter_mm=1.0)
    )
    galaxy_contours: GalaxyContourSet = Field(default_factory=GalaxyContourSet)

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
        if object_type == DsoType.SUPERNOVA_REMNANT:
            return self.bright_nebula
        if object_type == DsoType.DARK_NEBULA:
            return self.dark_nebula
        if object_type == DsoType.GALAXY_CLUSTER:
            return self.galaxy_cluster
        return self.other


class DoubleStarPairLimit(_StrictModel):
    max_sep_arcsec: PositiveFloat
    max_secondary_mag: float


class DoubleStarStyle(_StrictModel):
    """Profile selection and page-scale representation of WDS pairs."""

    enabled: bool = True
    limits: tuple[DoubleStarPairLimit, ...] = (
        DoubleStarPairLimit(max_sep_arcsec=30.0, max_secondary_mag=11.5),
        DoubleStarPairLimit(max_sep_arcsec=120.0, max_secondary_mag=10.0),
        DoubleStarPairLimit(max_sep_arcsec=200.0, max_secondary_mag=9.0),
    )
    minimum_separation_arcsec: NonNegativeFloat = 0.5
    unresolved_clearance_mm: NonNegativeFloat = 0.15
    marginal_clearance_mm: PositiveFloat = 0.8
    marker_length_factor: PositiveFloat = 1.8
    min_marker_length_mm: PositiveFloat = 0.8
    marker_line_width_mm: PositiveFloat = 0.15

    @model_validator(mode="after")
    def _validate_limits(self) -> DoubleStarStyle:
        separations = [float(limit.max_sep_arcsec) for limit in self.limits]
        if not separations or any(
            right <= left for left, right in zip(separations, separations[1:], strict=False)
        ):
            raise ValueError("double-star limits must have strictly ascending separation bounds")
        if self.marginal_clearance_mm <= self.unresolved_clearance_mm:
            raise ValueError("marginal_clearance_mm must exceed unresolved_clearance_mm")
        return self


class VariableStarStyle(_StrictModel):
    """Printed marker for the atlas's curated, strongly variable stars."""

    enabled: bool = True
    ring_gap_mm: NonNegativeFloat = 0.22
    line_width_mm: PositiveFloat = 0.12
    gray: float = Field(default=0.0, ge=0.0, le=1.0)


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

    Optional ticks subdivide the grid along the outside of the chart frame.
    Their steps must divide the corresponding grid-line steps; polar RA ticks
    can use their own interval. Crowded ticks are thinned in physical millimetres.
    """

    enabled: bool = True
    ra_step_deg: PositiveFloat = 2.0
    dec_step_deg: PositiveFloat = 2.0
    polar_ra_step_deg: PositiveFloat = 10.0
    line_width_mm: PositiveFloat = 0.1
    gray: float = 0.8
    polar_ra_line_width_mm: PositiveFloat | None = None
    polar_ra_gray: float | None = None
    labels_enabled: bool = True
    label_placement: Literal["inside", "outside"] = "inside"
    label_font_size_pt: PositiveFloat = 5.0
    label_gray: float = 0.35
    label_padding_mm: PositiveFloat = 1.5
    label_min_spacing_mm: NonNegativeFloat = 13.0
    label_ra_step_deg: PositiveFloat | None = None
    label_dec_step_deg: PositiveFloat | None = None
    label_polar_ra_step_deg: PositiveFloat | None = 30.0
    ticks_enabled: bool = False
    tick_ra_step_deg: PositiveFloat | None = None
    tick_dec_step_deg: PositiveFloat | None = None
    tick_polar_ra_step_deg: PositiveFloat | None = None
    tick_length_mm: PositiveFloat = 0.8
    tick_major_length_mm: PositiveFloat = 1.2
    tick_line_width_mm: PositiveFloat = 0.12
    tick_gray: float = Field(default=0.45, ge=0.0, le=1.0)
    tick_min_spacing_mm: NonNegativeFloat = 4.0

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
        for tick_name, line_name in (
            ("tick_ra_step_deg", "ra_step_deg"),
            ("tick_dec_step_deg", "dec_step_deg"),
            ("tick_polar_ra_step_deg", "polar_ra_step_deg"),
        ):
            tick_step = getattr(self, tick_name)
            if tick_step is None:
                continue
            line_step = getattr(self, line_name)
            ratio = line_step / tick_step
            if ratio < 1.0 or abs(ratio - round(ratio)) > 1e-6:
                raise ValueError(
                    f"{tick_name} ({tick_step:g}) must divide {line_name} ({line_step:g})"
                )
        return self


class EclipticStyle(_StrictModel):
    """Fine J2000 ecliptic reference curve."""

    enabled: bool = True
    line_width_mm: PositiveFloat = 0.12
    gray: float = 0.62
    dash_mm: PositiveFloat = 0.8
    gap_mm: PositiveFloat = 0.8


class MilkyWayStyle(_StrictModel):
    """Subtle stroke-only brightness contours from the Milky Way outline data."""

    enabled: bool = False
    levels: tuple[Literal[1, 2, 3, 4, 5], ...] = ()
    line_width_mm: PositiveFloat = 0.07
    level_gray: dict[int, float] = Field(
        default_factory=lambda: {1: 0.85, 2: 0.83, 3: 0.82, 4: 0.80, 5: 0.79}
    )

    @field_validator("levels")
    @classmethod
    def _levels_are_unique_and_ordered(
        cls, value: tuple[int, ...]
    ) -> tuple[int, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("Milky Way levels must be unique and sorted ascending")
        return value

    @field_validator("level_gray")
    @classmethod
    def _level_gray_values_are_valid(cls, value: dict[int, float]) -> dict[int, float]:
        if any(level not in range(1, 6) for level in value):
            raise ValueError("Milky Way gray keys must be levels 1 through 5")
        if any(not math.isfinite(gray) or not 0.0 <= gray <= 1.0 for gray in value.values()):
            raise ValueError("Milky Way gray values must be within [0, 1]")
        return value

    @model_validator(mode="after")
    def _enabled_levels_have_gray_values(self) -> MilkyWayStyle:
        if self.enabled and not set(self.levels).issubset(self.level_gray):
            raise ValueError("each selected Milky Way level needs a gray value")
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
    bold_width_mm: PositiveFloat = 0.25
    normal_width_mm: PositiveFloat = 0.16
    thin_width_mm: PositiveFloat = 0.10
    star_gap_extra_mm: NonNegativeFloat = 0.2
    star_match_tolerance_mm: PositiveFloat = 0.6

    def width_mm_for(self, weight: str) -> float:
        widths = {
            "bold": self.bold_width_mm,
            "normal": self.normal_width_mm,
            "thin": self.thin_width_mm,
        }
        return widths[weight]


class ConstellationBoundaryStyle(_StrictModel):
    """Dotted constellation boundary appearance."""

    enabled: bool = True
    gray: float = 0.82
    line_width_mm: PositiveFloat = 0.1
    dash_mm: PositiveFloat = 1.0
    gap_mm: PositiveFloat = 1.2


class ConstellationNameStyle(_StrictModel):
    """Quiet full constellation names placed beneath chart content."""

    enabled: bool = True
    font_size_pt: PositiveFloat = 10.2
    gray: float = 0.66
    min_segments: int = Field(default=2, ge=1)


class ConstellationStyle(_StrictModel):
    """Constellation line and boundary appearance."""

    lines: ConstellationLineStyle = Field(default_factory=ConstellationLineStyle)
    boundaries: ConstellationBoundaryStyle = Field(default_factory=ConstellationBoundaryStyle)
    names: ConstellationNameStyle = Field(default_factory=ConstellationNameStyle)


class ScaleBarStyle(_StrictModel):
    """Optional linear angular scale drawn in the page footer."""

    enabled: bool = True
    length_deg: PositiveFloat = 5.0
    thickness_mm: PositiveFloat = 0.15
    gray: float = 0.5
    font_size_pt: PositiveFloat = 6.5
    tick_mm: PositiveFloat = 1.2


class NavigationStyle(_StrictModel):
    """Adjacent-chart navigation references.

    Navigation sits outside the chart frame and always prints short chart
    codes.  It is deliberately larger than the coordinate labels so it can be
    found at a glance while flipping pages, but mid-grey so it still reads as
    subordinate to sky content.  ``frame_gap_mm`` is the gap to the chart frame
    for the N/S references; ``side_inset_mm`` is the distance of the E/W
    references from the paper edge and must stay clear of the printer's
    unprintable margin (a few millimetres), not just the chart frame, which on a
    full-width field nearly touches the page edge.  The side references are
    rotated to read along the narrow margin.
    """

    enabled: bool = True
    font_size_pt: PositiveFloat = 7.5
    gray: float = 0.5
    frame_gap_mm: PositiveFloat = 4.2
    side_inset_mm: PositiveFloat = 5.0


class MagnitudeLegendStyle(_StrictModel):
    """Compact star-magnitude reference for the footer.

    The reference dots use the same :class:`StarSizeModel` as the chart, so the
    legend shows the real printed symbol sizes rather than a symbolic redraw.
    ``spacing_mm`` is the clear edge-to-edge gap between neighbouring dots.
    """

    enabled: bool = False
    font_size_pt: PositiveFloat = 6.0
    gray: float = 0.0
    spacing_mm: PositiveFloat = 3.5
    label: str = "stars to mag"


class FurnitureStyle(_StrictModel):
    """Chart title/footer, scale bar, magnitude legend and navigation styling."""

    title_font_size_pt: PositiveFloat = 8.5
    title_gray: float = 0.15
    footer_layout: Literal["inline", "split"] = "inline"
    footer_code_font_size_pt: PositiveFloat = 11.0
    footer_brand_font_size_pt: PositiveFloat = 6.0
    footer_brand_gray: float = 0.6
    chart_border_width_mm: PositiveFloat = 0.25
    scale_bar: ScaleBarStyle = Field(default_factory=ScaleBarStyle)
    navigation: NavigationStyle = Field(default_factory=NavigationStyle)
    magnitude_legend: MagnitudeLegendStyle = Field(default_factory=MagnitudeLegendStyle)


class OverviewStyle(_StrictModel):
    """Appearance of the whole-sky overview pages at the front of the atlas.

    The overview is a pole-centred azimuthal equidistant disk: constellation
    geometry and bright stars as a quiet background, one trapezoidal
    ring/RA-sector cell per chart (so overlapping chart fields never tangle),
    and a chart code at each cell centre.  Colours are deliberately quiet so
    the cell grid and the codes are the readable layer.
    """

    enabled: bool = True
    hemispheres_per_page: Literal[1, 2] = 1
    equatorial_extension_deg: NonNegativeFloat = 0.0
    radius_mm: PositiveFloat = 76.0
    title_font_size_pt: PositiveFloat = 15.0
    subtitle_font_size_pt: PositiveFloat = 9.0
    rim_line_width_mm: PositiveFloat = 0.3
    rim_gray: float = 0.25
    show_grid: bool = True
    grid_gray: float = 0.9
    grid_line_width_mm: PositiveFloat = 0.08
    constellation_gray: float = 0.78
    constellation_line_width_mm: PositiveFloat = 0.2
    boundary_gray: float = 0.86
    boundary_line_width_mm: PositiveFloat = 0.1
    name_font_size_pt: PositiveFloat = 5.5
    name_gray: float = 0.3
    show_constellation_names: bool = True
    show_pole_label: bool = True
    footprint_gray: float = 0.45
    footprint_line_width_mm: PositiveFloat = 0.2
    code_font_size_pt: PositiveFloat = 5.25
    code_gray: float = 0.1
    # Bright-star foreground.  The overview is an index, so only stars down to
    # ``star_limit_magnitude`` are projected; sizes use the same monotonic
    # magnitude model as the charts but stay deliberately small.
    show_stars: bool = True
    star_limit_magnitude: float = 5.0
    star_min_diameter_mm: PositiveFloat = 0.3
    star_max_diameter_mm: PositiveFloat = 1.4
    star_bright_magnitude: float = 0.0
    star_faint_magnitude: float = 5.0
    star_gray: float = 0.0


class LocatorStyle(_StrictModel):
    """Optional compact per-chart locator inset.

    A small pole-centred overview disk drawn inside the chart field, with the
    current chart footprint emphasized and, optionally, its immediate
    neighbours shown.  Disabled by default so existing pages are unchanged.
    """

    enabled: bool = False
    diameter_mm: PositiveFloat = 42.0
    corner: Literal["bottom_left", "bottom_right", "top_left", "top_right"] = "bottom_left"
    inset_margin_mm: PositiveFloat = 3.0
    show_neighbours: bool = True
    border_gray: float = 0.4
    border_line_width_mm: PositiveFloat = 0.15
    constellation_gray: float = 0.9
    constellation_line_width_mm: PositiveFloat = 0.08
    footprint_gray: float = 0.78
    footprint_line_width_mm: PositiveFloat = 0.1
    neighbour_gray: float = 0.4
    neighbour_line_width_mm: PositiveFloat = 0.22
    current_gray: float = 0.0
    current_line_width_mm: PositiveFloat = 0.35


class TypographyStyle(_StrictModel):
    """Font families reserved for non-chart editorial pages."""

    sans_family: str = "Source Sans 3"


class StyleConfig(_StrictModel):
    """Visual appearance configuration for one style."""

    id: str
    star: StarStyle
    label: LabelStyle
    dso: DsoStyle = Field(default_factory=DsoStyle)
    double_stars: DoubleStarStyle = Field(default_factory=DoubleStarStyle)
    variable_stars: VariableStarStyle = Field(default_factory=VariableStarStyle)
    grid: GridStyle = Field(default_factory=GridStyle)
    ecliptic: EclipticStyle = Field(default_factory=EclipticStyle)
    milky_way: MilkyWayStyle = Field(default_factory=MilkyWayStyle)
    constellation: ConstellationStyle = Field(default_factory=ConstellationStyle)
    furniture: FurnitureStyle = Field(default_factory=FurnitureStyle)
    overview: OverviewStyle = Field(default_factory=OverviewStyle)
    locator: LocatorStyle = Field(default_factory=LocatorStyle)
    typography: TypographyStyle = Field(default_factory=TypographyStyle)


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


def _merge_mapping(base: dict[str, object], override: dict[str, object]) -> dict[str, object]:
    """Recursively merge a small edition override onto a shared YAML base."""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_mapping(merged[key], value)  # type: ignore[arg-type]
        else:
            merged[key] = value
    return merged


def _load_inherited_mapping(path: Path) -> dict[str, object]:
    mapping = _load_yaml_mapping(path)
    parent = mapping.pop("extends", None)
    if parent is None:
        return mapping
    if not isinstance(parent, str) or not parent:
        raise ConfigError(f"extends must be a non-empty relative path: {path}")
    parent_path = (path.parent / parent).resolve()
    if parent_path == path.resolve():
        raise ConfigError(f"configuration cannot extend itself: {path}")
    return _merge_mapping(_load_inherited_mapping(parent_path), mapping)


def load_atlas_config(path: str | Path) -> AtlasConfig:
    """Load and validate an atlas edition definition from a YAML file."""
    mapping = _load_inherited_mapping(Path(path))
    try:
        return AtlasConfig.model_validate(mapping)
    except ValidationError as exc:
        raise ConfigError(f"invalid atlas configuration {path}:\n{exc}") from exc


def load_style_config(path: str | Path) -> StyleConfig:
    """Load and validate a rendering style definition from a YAML file."""
    mapping = _load_inherited_mapping(Path(path))
    try:
        return StyleConfig.model_validate(mapping)
    except ValidationError as exc:
        raise ConfigError(f"invalid style configuration {path}:\n{exc}") from exc
