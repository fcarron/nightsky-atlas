"""Manual, stable-ID label overrides.

Overrides are the deterministic human escape hatch described in ``AGENTS.md``
section 22: they are reviewable YAML, reference labels by stable ID, apply after
initial layout generation, and may lock a placement so later optimizers respect
it.  They are never allowed to change astronomical data.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from nightsky_atlas.layout.models import CompassPosition, Label
from nightsky_atlas.layout.placement import offset_label_placement

__all__ = [
    "ChartOverrides",
    "LabelOverride",
    "OverrideError",
    "OverridesLibrary",
    "apply_overrides",
    "load_override_library",
    "load_overrides",
    "load_overrides_dir",
]


class OverrideError(ValueError):
    """Raised when an override document is malformed or cannot be applied."""


class _OffsetOverrideModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    x: float = Field(allow_inf_nan=False)
    y: float = Field(allow_inf_nan=False)


class _LabelOverrideModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate: str | None = None
    locked: bool | None = None
    hidden: bool | None = None
    offset_mm: _OffsetOverrideModel | None = None
    leader_line: bool | None = None

    @field_validator("candidate")
    @classmethod
    def _candidate_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("candidate must not be blank")
        return value

    @model_validator(mode="after")
    def _validate_combination(self) -> _LabelOverrideModel:
        if self.offset_mm is not None and self.candidate is None:
            raise ValueError("offset_mm requires an explicit candidate")
        if self.hidden is True and self.leader_line is True:
            raise ValueError("a hidden label cannot have a leader line")
        return self


class _OverrideFileModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    chart: str
    labels: dict[str, _LabelOverrideModel] = {}

    @field_validator("chart")
    @classmethod
    def _chart_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("chart must not be blank")
        return value


@dataclass(frozen=True, slots=True)
class LabelOverride:
    """Override for a single label, referenced by its stable ID.

    ``locked`` and ``hidden`` are tri-state: ``None`` leaves the current value
    untouched, so an override that only moves a candidate never silently
    unlocks a manually locked label (``AGENTS.md`` section 22).
    """

    candidate: str | None = None
    locked: bool | None = None
    hidden: bool | None = None
    offset_mm: tuple[float, float] | None = None
    leader_line: bool | None = None


@dataclass(frozen=True, slots=True)
class ChartOverrides:
    """All label overrides for one chart."""

    chart: str
    labels: Mapping[str, LabelOverride]

    def __len__(self) -> int:
        return len(self.labels)


@dataclass(frozen=True, slots=True)
class OverridesLibrary:
    """Overrides for one or more charts, keyed by chart ID."""

    by_chart: Mapping[str, ChartOverrides]

    def for_chart(self, chart_id: str) -> ChartOverrides | None:
        """Return the overrides for a chart, if any."""
        return self.by_chart.get(chart_id)

    def chart_ids(self) -> tuple[str, ...]:
        """Return the chart IDs that have overrides, sorted."""
        return tuple(sorted(self.by_chart))


def _read_mapping(path: Path) -> dict[str, object]:
    if not path.exists():
        raise OverrideError(f"override file not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise OverrideError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise OverrideError(f"override root must be a mapping: {path}")
    return raw


def _parse(path: Path) -> ChartOverrides:
    mapping = _read_mapping(path)
    try:
        model = _OverrideFileModel.model_validate(mapping)
    except ValidationError as exc:
        raise OverrideError(f"invalid override file {path}:\n{exc}") from exc
    labels = {
        label_id: LabelOverride(
            candidate=item.candidate,
            locked=item.locked,
            hidden=item.hidden,
            offset_mm=(None if item.offset_mm is None else (item.offset_mm.x, item.offset_mm.y)),
            leader_line=item.leader_line,
        )
        for label_id, item in model.labels.items()
    }
    return ChartOverrides(chart=model.chart, labels=labels)


def load_overrides(path: str | Path) -> ChartOverrides:
    """Load a single-chart override document."""
    return _parse(Path(path))


def load_overrides_dir(path: str | Path) -> OverridesLibrary:
    """Load every ``*.yaml``/``*.yml`` override file in a directory."""
    directory = Path(path)
    if not directory.is_dir():
        raise OverrideError(f"override directory not found: {directory}")
    by_chart: dict[str, ChartOverrides] = {}
    paths = sorted(
        [*directory.glob("*.yaml"), *directory.glob("*.yml")],
        key=lambda item: item.name,
    )
    for file_path in paths:
        overrides = _parse(file_path)
        if overrides.chart in by_chart:
            raise OverrideError(
                f"duplicate overrides for chart {overrides.chart!r}: "
                f"{file_path.name} conflicts with an earlier file"
            )
        by_chart[overrides.chart] = overrides
    return OverridesLibrary(by_chart=by_chart)


def load_override_library(path: str | Path) -> OverridesLibrary:
    """Load overrides from either a single file or a directory of files."""
    candidate = Path(path)
    if candidate.is_dir():
        return load_overrides_dir(candidate)
    overrides = load_overrides(candidate)
    return OverridesLibrary(by_chart={overrides.chart: overrides})


def _resolve_candidate_id(label: Label, candidate: str | None) -> str | None:
    if candidate is None:
        return None
    for position in CompassPosition:
        if candidate == position.value:
            for item in label.candidates:
                if item.position == position and item.ring == 0:
                    return item.id
            raise OverrideError(f"{label.id}: override candidate {candidate!r} has no candidate")
    if label.candidate(candidate) is not None:
        return candidate
    raise OverrideError(f"{label.id}: override candidate {candidate!r} is not a valid candidate")


def apply_overrides(labels: tuple[Label, ...], overrides: ChartOverrides) -> tuple[Label, ...]:
    """Apply a chart's overrides to its labels.

    Unknown label IDs and invalid candidates are hard errors: an override that
    cannot be honoured must never be silently ignored (``AGENTS.md`` sections
    22 and 29).
    """
    known = {label.id for label in labels}
    unknown = sorted(set(overrides.labels) - known)
    if unknown:
        raise OverrideError(
            f"override for chart {overrides.chart!r} references unknown label(s): "
            f"{', '.join(unknown)}"
        )

    updated: list[Label] = []
    for label in labels:
        spec = overrides.labels.get(label.id)
        if spec is None:
            updated.append(label)
            continue
        if spec.hidden is True:
            updated.append(label.with_placement(None, hidden=True, locked=spec.locked))
            continue
        candidate_id = _resolve_candidate_id(label, spec.candidate)
        if candidate_id is None:
            if spec.locked is True:
                raise OverrideError(f"{label.id}: locked override must specify a candidate")
            updated_label = label.with_placement(
                label.selected_candidate_id,
                hidden=label.hidden if spec.hidden is None else spec.hidden,
                locked=spec.locked,
            )
            if spec.leader_line is not None:
                updated_label = _with_leader_line(updated_label, spec.leader_line)
            updated.append(updated_label)
            continue
        if spec.offset_mm is not None:
            updated_label = offset_label_placement(
                label, candidate_id, spec.offset_mm[0], spec.offset_mm[1]
            )
        else:
            updated_label = label.with_placement(candidate_id)
        updated_label = updated_label.with_placement(
            updated_label.selected_candidate_id,
            hidden=False if spec.hidden is None else spec.hidden,
            locked=spec.locked,
        )
        if spec.leader_line is not None:
            updated_label = _with_leader_line(updated_label, spec.leader_line)
        updated.append(updated_label)
    return tuple(updated)


def _with_leader_line(label: Label, enabled: bool) -> Label:
    return replace(label, leader_line=enabled, leader_line_reason="manual" if enabled else None)
