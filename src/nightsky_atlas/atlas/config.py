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
    PositiveFloat,
    ValidationError,
    field_validator,
    model_validator,
)

from nightsky_atlas.chart.models import ChartDefinition, PageGeometry

__all__ = [
    "AtlasConfig",
    "ChartConfig",
    "ConfigError",
    "ConstellationBoundaryStyle",
    "ConstellationLineStyle",
    "ConstellationStyle",
    "DsoStyle",
    "FurnitureStyle",
    "GridStyle",
    "PageConfig",
    "StyleConfig",
    "TilingConfig",
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


class TilingConfig(_StrictModel):
    """Declination-band tiling parameters for a complete atlas."""

    width_deg: PositiveFloat
    height_deg: PositiveFloat
    overlap_deg: PositiveFloat = 3.0
    coverage_step_deg: PositiveFloat = 2.0


class AtlasConfig(_StrictModel):
    """An atlas edition: page geometry plus explicit chart definitions."""

    id: str
    page: PageConfig
    charts: list[ChartConfig] = Field(default_factory=list)
    tiling: TilingConfig | None = None
    stellar_limit_magnitude: PositiveFloat | None = None
    dso_limit_magnitude: PositiveFloat | None = None


class StarStyle(_StrictModel):
    """Star symbol sizing, in millimetres of printed diameter.

    ``bright_magnitude`` is the magnitude at which the maximum diameter is
    reached; ``faint_magnitude`` is the magnitude at which the minimum diameter
    is reached.  Stars between the two are sized linearly.  ``bright_magnitude``
    must be numerically smaller than ``faint_magnitude``.
    """

    min_diameter_mm: PositiveFloat
    max_diameter_mm: PositiveFloat
    bright_magnitude: float
    faint_magnitude: float

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


class LabelStyle(_StrictModel):
    """Label typography and candidate generation."""

    font_family: str
    font_size_pt: PositiveFloat
    candidate_rings: int = Field(default=2, ge=1)
    ring_gap_mm: PositiveFloat = 2.5


class DsoStyle(_StrictModel):
    """Deep-sky symbol sizing, in millimetres.

    ``size_mm`` is the default symbol diameter for non-galaxy classes.
    ``min_axis_mm`` is the smallest printable galaxy axis; ``max_axis_mm`` caps
    very large objects so they do not swamp a page.  Outline fields control the
    schematic stroke drawn around extended objects that have an authored
    outline.
    """

    size_mm: PositiveFloat = 1.4
    min_axis_mm: PositiveFloat = 0.7
    max_axis_mm: PositiveFloat = 12.0
    line_width_mm: PositiveFloat = 0.15
    dash_mm: PositiveFloat = 0.4
    outline_line_width_mm: PositiveFloat = 0.18
    outline_dash_mm: PositiveFloat = 0.8
    outline_gray: float = 0.45


class GridStyle(_StrictModel):
    """Coordinate grid appearance and spacing.

    The grid is furniture, not sky content: it has lower visual priority than
    labels and may be clipped (``AGENTS.md`` sections 14.4 and 16).

    Grid *lines* use ``ra_step_deg`` / ``dec_step_deg``.  Edge *labels* are
    independent furniture drawn just inside the chart frame; ``label_ra_step_deg``
    and ``label_dec_step_deg`` select which grid lines carry a label.  A label
    step must be a whole multiple of the corresponding line step so that a
    labelled value is always an actual grid line; ``None`` labels every line.
    """

    enabled: bool = True
    ra_step_deg: PositiveFloat = 2.0
    dec_step_deg: PositiveFloat = 2.0
    line_width_mm: PositiveFloat = 0.1
    gray: float = 0.6
    labels_enabled: bool = True
    label_font_size_pt: PositiveFloat = 5.0
    label_gray: float = 0.35
    label_padding_mm: PositiveFloat = 1.5
    label_ra_step_deg: PositiveFloat | None = None
    label_dec_step_deg: PositiveFloat | None = None

    @model_validator(mode="after")
    def _label_steps_align_with_lines(self) -> GridStyle:
        for label_name, line_name in (
            ("label_ra_step_deg", "ra_step_deg"),
            ("label_dec_step_deg", "dec_step_deg"),
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
    """Stick-figure constellation line appearance."""

    enabled: bool = True
    gray: float = 0.55
    line_width_mm: PositiveFloat = 0.15


class ConstellationBoundaryStyle(_StrictModel):
    """Dotted constellation boundary appearance."""

    enabled: bool = True
    gray: float = 0.6
    line_width_mm: PositiveFloat = 0.12
    dash_mm: PositiveFloat = 1.0
    gap_mm: PositiveFloat = 1.2


class ConstellationStyle(_StrictModel):
    """Constellation line and boundary appearance."""

    lines: ConstellationLineStyle = Field(default_factory=ConstellationLineStyle)
    boundaries: ConstellationBoundaryStyle = Field(default_factory=ConstellationBoundaryStyle)


class FurnitureStyle(_StrictModel):
    """Chart title, scale bar and neighbour navigation styling."""

    title_font_size_pt: PositiveFloat = 9.0
    scale_font_size_pt: PositiveFloat = 6.0
    scale_bar_length_deg: PositiveFloat = 5.0
    scale_bar_thickness_mm: PositiveFloat = 0.4
    chart_border_width_mm: PositiveFloat = 0.25


class StyleConfig(_StrictModel):
    """Visual appearance configuration for one style."""

    id: str
    star: StarStyle
    label: LabelStyle
    dso: DsoStyle = Field(default_factory=DsoStyle)
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
