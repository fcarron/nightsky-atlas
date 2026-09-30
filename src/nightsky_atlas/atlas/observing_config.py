"""Typed loading for observing-list selection policy.

The membership data itself lives in vendored fixtures (see
:mod:`nightsky_atlas.catalog.observing_lists`); this module describes *how* the
atlas uses that membership.  Rules are configuration, never scattered through
the selection code (``AGENTS.md`` section 29):

- ``lists`` names the known observing lists for diagnostics;
- each edition declares ``forced_lists`` (always rendered) and ``list_weights``
  (priority bonus for members);
- an edition may ``inherit`` another edition so Deep builds on Standard.

Unknown keys fail fast.  A missing configuration file yields an empty policy so
the atlas still builds with observing lists disabled.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from nightsky_atlas.atlas.config import ConfigError
from nightsky_atlas.catalog.models import DsoType
from nightsky_atlas.catalog.selection import (
    RegionalDesignationAllowlist,
    SelectionPolicy,
    TypeSelectionRule,
    VisibilityClassRule,
)

__all__ = [
    "DEFAULT_CONFIG_PATH",
    "EditionPolicy",
    "ObservingListEntry",
    "ObservingListsConfig",
    "RegionalDesignationAllowlistConfig",
    "TypeSelectionPolicyConfig",
    "VisibilityClassPolicyConfig",
    "load_observing_lists_config",
    "resolve_edition",
]

DEFAULT_CONFIG_PATH = Path("config/observing_lists.yaml")


class _StrictModel(BaseModel):
    """Base model that rejects unknown keys and is immutable."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ObservingListEntry(_StrictModel):
    """A named observing list known to the atlas."""

    name: str

    @field_validator("name")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("observing list name must not be blank")
        return value


class VisibilityClassPolicyConfig(_StrictModel):
    contour_class: str
    minimum_major_axis_arcmin: float = 0.0
    bright_magnitude_fallback: float | None = None
    minimum_score_400: float | None = None


class RegionalDesignationAllowlistConfig(_StrictModel):
    id: str = Field(min_length=1)
    center_ra_deg: float = Field(ge=0, lt=360)
    center_dec_deg: float = Field(ge=-90, le=90)
    radius_deg: float = Field(gt=0, le=180)
    allowed_designations: tuple[str, ...] = Field(min_length=1)


class TypeSelectionPolicyConfig(_StrictModel):
    use_visibility: bool = True
    visibility_classes: tuple[str, ...] = ()
    visibility_class_rules: tuple[VisibilityClassPolicyConfig, ...] = ()
    regional_allowlists: tuple[RegionalDesignationAllowlistConfig, ...] = ()
    curated_designations: tuple[str, ...] = ()
    minimum_visibility_score_400: float | None = None
    minimum_visibility_score_by_aperture: dict[int, float] = Field(default_factory=dict)
    minimum_major_axis_arcmin: float | None = None
    bright_magnitude_fallback: float | None = None
    maximum_magnitude: float | None = None
    maximum_surface_brightness: float | None = None
    qualifying_catalogues: tuple[str, ...] = ()
    visibility_catalogues: tuple[str, ...] = ()
    catalogue_minimum_major_axis_arcmin: float | None = None
    catalogue_maximum_magnitude: float | None = None
    catalogue_maximum_surface_brightness: float | None = None
    catalogue_minimum_member_count: int | None = None
    catalogue_require_major_axis: bool = False
    qualifying_memberships: tuple[str, ...] = ()
    minimum_member_count: int | None = None
    require_major_axis: bool = False
    require_photometry_or_size: bool = False
    include_all_valid: bool = False
    selection_reason_code: str | None = None
    exclusion_reason_code: str | None = None

    @model_validator(mode="after")
    def _validate_thresholds(self) -> TypeSelectionPolicyConfig:
        for key in (
            "minimum_major_axis_arcmin",
            "catalogue_minimum_major_axis_arcmin",
        ):
            value = getattr(self, key)
            if value is not None and value < 0:
                raise ValueError(f"{key} must be >= 0")
        for item in self.visibility_class_rules:
            if item.minimum_major_axis_arcmin < 0:
                raise ValueError("visibility class minimum size must be >= 0")
        if self.minimum_member_count is not None and self.minimum_member_count < 0:
            raise ValueError("minimum_member_count must be >= 0")
        return self


class EditionPolicy(_StrictModel):
    """Selection rules for one atlas edition."""

    inherit: str | None = None
    forced_lists: tuple[str, ...] = ()
    forced_list_reason_codes: dict[str, str] = Field(default_factory=dict)
    list_weights: dict[str, int] = Field(default_factory=dict)
    included_catalogues: tuple[str, ...] | None = None
    excluded_designations: tuple[str, ...] = ()
    forced_catalogues: tuple[str, ...] = ()
    catalogue_minimum_extent_arcmin: dict[str, float] = Field(default_factory=dict)
    include_uncertain_catalogue_matches: bool | None = None
    selection_rules: dict[str, TypeSelectionPolicyConfig] = Field(default_factory=dict)

    @field_validator("selection_rules")
    @classmethod
    def _known_selection_types(
        cls, value: dict[str, TypeSelectionPolicyConfig]
    ) -> dict[str, TypeSelectionPolicyConfig]:
        known = {item.value for item in DsoType} | {"bright_nebula_unspecified"}
        unknown = set(value) - known
        if unknown:
            raise ValueError(f"unknown DSO selection-rule types: {sorted(unknown)}")
        return value

    @field_validator("list_weights")
    @classmethod
    def _weights_non_negative(cls, value: dict[str, int]) -> dict[str, int]:
        for list_id, weight in value.items():
            if not list_id.strip():
                raise ValueError("list weight key must not be blank")
            if weight < 0:
                raise ValueError(f"list weight for {list_id!r} must be >= 0")
        return value

    @field_validator("catalogue_minimum_extent_arcmin")
    @classmethod
    def _valid_catalogue_minimum_extents(cls, value: dict[str, float]) -> dict[str, float]:
        for catalogue, extent in value.items():
            if not catalogue.strip() or extent < 0:
                raise ValueError("catalogue extent thresholds need a name and value >= 0")
        return value


class ObservingListsConfig(_StrictModel):
    """Observing-list registry plus per-edition selection policies."""

    lists: dict[str, ObservingListEntry] = Field(default_factory=dict)
    editions: dict[str, EditionPolicy] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _editions_reference_known_lists(self) -> ObservingListsConfig:
        if not self.lists:
            return self
        known = set(self.lists)
        for edition_id, policy in self.editions.items():
            referenced = set(policy.forced_lists) | set(policy.list_weights)
            unknown = referenced - known
            if unknown:
                raise ValueError(
                    f"edition {edition_id!r} references unknown observing lists: {sorted(unknown)}"
                )
        return self


def load_observing_lists_config(
    path: str | Path | None = DEFAULT_CONFIG_PATH,
) -> ObservingListsConfig:
    """Load the observing-list policy, or an empty policy when absent."""
    if path is None or not str(path).strip():
        return ObservingListsConfig()
    target = Path(path)
    if str(target) == "." or not target.exists():
        return ObservingListsConfig()
    try:
        raw = yaml.safe_load(target.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {target}: {exc}") from exc
    if raw is None:
        return ObservingListsConfig()
    if not isinstance(raw, dict):
        raise ConfigError(f"configuration root must be a mapping: {target}")
    try:
        return ObservingListsConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"invalid observing-list configuration {target}:\n{exc}") from exc


def resolve_edition(config: ObservingListsConfig, edition_id: str) -> SelectionPolicy:
    """Resolve one edition's policy, merging any inherited edition.

    An unknown edition is not an error: it simply selects nothing, so a
    development atlas with an ad-hoc id keeps building.
    """
    if edition_id not in config.editions:
        return SelectionPolicy()

    chain: list[EditionPolicy] = []
    seen: set[str] = set()
    current: str | None = edition_id
    while current is not None:
        if current in seen:
            raise ConfigError(f"observing-list edition inheritance cycle at {current!r}")
        seen.add(current)
        policy = config.editions.get(current)
        if policy is None:
            raise ConfigError(f"observing-list edition {current!r} inherits unknown edition")
        chain.append(policy)
        current = policy.inherit

    forced: list[str] = []
    forced_reason_codes: dict[str, str] = {}
    weights: dict[str, int] = {}
    included_catalogues: tuple[str, ...] | None = None
    excluded_designations: list[str] = []
    forced_catalogues: list[str] = []
    catalogue_minimum_extent_arcmin: dict[str, float] = {}
    selection_rules: dict[str, dict[str, object]] = {}
    include_uncertain_catalogue_matches = False
    for policy in reversed(chain):
        for list_id in policy.forced_lists:
            if list_id not in forced:
                forced.append(list_id)
        forced_reason_codes.update(policy.forced_list_reason_codes)
        weights.update(policy.list_weights)
        if policy.included_catalogues is not None:
            included_catalogues = policy.included_catalogues
        excluded_designations.extend(
            item for item in policy.excluded_designations if item not in excluded_designations
        )
        for catalogue in policy.forced_catalogues:
            if catalogue not in forced_catalogues:
                forced_catalogues.append(catalogue)
        catalogue_minimum_extent_arcmin.update(policy.catalogue_minimum_extent_arcmin)
        for type_name, type_rule in policy.selection_rules.items():
            selection_rules.setdefault(type_name, {}).update(
                type_rule.model_dump(exclude_unset=True)
            )
        if policy.include_uncertain_catalogue_matches is not None:
            include_uncertain_catalogue_matches = policy.include_uncertain_catalogue_matches
    return SelectionPolicy(
        forced_lists=frozenset(forced),
        forced_list_reason_codes=tuple(sorted(forced_reason_codes.items())),
        list_weights=tuple(weights.items()),
        included_catalogues=(
            frozenset(included_catalogues) if included_catalogues is not None else None
        ),
        excluded_designations=tuple(excluded_designations),
        forced_catalogues=frozenset(forced_catalogues),
        catalogue_minimum_extent_arcmin=tuple(catalogue_minimum_extent_arcmin.items()),
        include_uncertain_catalogue_matches=include_uncertain_catalogue_matches,
        type_rules=tuple(
            (
                type_name,
                TypeSelectionRule(
                    **{
                        **values,
                        "minimum_visibility_score_by_aperture": tuple(
                            sorted(values.get("minimum_visibility_score_by_aperture", {}).items())
                        ),
                        "visibility_class_rules": tuple(
                            VisibilityClassRule(**item)
                            for item in values.get("visibility_class_rules", ())
                        ),
                        "regional_allowlists": tuple(
                            RegionalDesignationAllowlist(**item)
                            for item in values.get("regional_allowlists", ())
                        ),
                    }
                ),
            )
            for type_name, values in sorted(selection_rules.items())
        ),
        edition_id=edition_id,
    )
