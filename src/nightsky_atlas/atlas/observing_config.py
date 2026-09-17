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
from nightsky_atlas.catalog.selection import SelectionPolicy

__all__ = [
    "DEFAULT_CONFIG_PATH",
    "EditionPolicy",
    "ObservingListEntry",
    "ObservingListsConfig",
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


class EditionPolicy(_StrictModel):
    """Selection rules for one atlas edition."""

    inherit: str | None = None
    forced_lists: tuple[str, ...] = ()
    list_weights: dict[str, int] = Field(default_factory=dict)

    @field_validator("list_weights")
    @classmethod
    def _weights_non_negative(cls, value: dict[str, int]) -> dict[str, int]:
        for list_id, weight in value.items():
            if not list_id.strip():
                raise ValueError("list weight key must not be blank")
            if weight < 0:
                raise ValueError(f"list weight for {list_id!r} must be >= 0")
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
                    f"edition {edition_id!r} references unknown observing lists: "
                    f"{sorted(unknown)}"
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


def resolve_edition(
    config: ObservingListsConfig, edition_id: str
) -> SelectionPolicy:
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
            raise ConfigError(
                f"observing-list edition {current!r} inherits unknown edition"
            )
        chain.append(policy)
        current = policy.inherit

    forced: list[str] = []
    weights: dict[str, int] = {}
    for policy in reversed(chain):
        for list_id in policy.forced_lists:
            if list_id not in forced:
                forced.append(list_id)
        weights.update(policy.list_weights)
    return SelectionPolicy(forced_lists=frozenset(forced), list_weights=tuple(weights.items()))
