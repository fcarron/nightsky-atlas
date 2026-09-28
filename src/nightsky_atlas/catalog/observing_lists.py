"""Observing-list membership for deep-sky objects.

Visual observers rely on curated best-of lists (Messier, Herschel 400, Caldwell
and similar) rather than on an integrated magnitude limit.  Membership is atlas
metadata, not an astronomical fact (``AGENTS.md`` section 5), so it lives in
vendored fixtures keyed by catalogue designation and never mutates
:class:`~nightsky_atlas.catalog.models.DeepSkyObject`.

Each fixture is a JSON object with ``id``, ``name``, optional provenance fields
(``source``, ``url``, ``license``, ``retrieved``) and an ``objects`` list of
designations.  Designations are normalized before matching so that OpenNGC's
zero-padded identifiers (``NGC0869``), the fixtures' plain form (``NGC 869``)
and Messier numbers (``M 42``) all compare equal.
"""

from __future__ import annotations

import functools
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nightsky_atlas.catalog.models import DeepSkyObject

__all__ = [
    "DEFAULT_FIXTURE_DIR",
    "FILENAME",
    "ObservingList",
    "ObservingMembershipIndex",
    "build_membership_index",
    "canonical_designation",
    "dso_memberships",
    "load_observing_lists",
]

DEFAULT_FIXTURE_DIR = Path("data/fixtures/observing_lists")
FILENAME = "*.json"

_NGC_IC = re.compile(r"^(NGC|IC)0*(\d+)([A-Z]?)$")
_MESSIER = re.compile(r"^M0*(\d+)")
_PGC = re.compile(r"^PGC0*(\d+)$")
_MELOTTE = re.compile(r"^(?:MEL|MELOTTE)0*(\d+)$")
_COLLINDER = re.compile(r"^(?:CR|CL|COLLINDER)0*(\d+)$")


@functools.lru_cache(maxsize=65536)
def canonical_designation(designation: str) -> str:
    """Return a comparable form of a catalogue designation.

    Whitespace is removed, NGC/IC/PGC numbers lose leading zeros while NGC/IC
    component suffixes are retained, and a Messier number becomes ``M<n>``.
    Anything unrecognized is returned upper-cased so
    that non-catalogue designations still compare consistently.  Cached because
    the same designations are canonicalized for every chart in a build.
    """
    cleaned = re.sub(r"\s+", "", designation).upper()
    if not cleaned:
        return ""
    ngc = _NGC_IC.match(cleaned)
    if ngc is not None:
        return f"{ngc.group(1)}{int(ngc.group(2))}{ngc.group(3)}"
    messier = _MESSIER.match(cleaned)
    if messier is not None:
        return f"M{int(messier.group(1))}"
    pgc = _PGC.match(cleaned)
    if pgc is not None:
        return f"PGC{int(pgc.group(1))}"
    melotte = _MELOTTE.match(cleaned)
    if melotte is not None:
        return f"MEL{int(melotte.group(1))}"
    collinder = _COLLINDER.match(cleaned)
    if collinder is not None:
        return f"CR{int(collinder.group(1))}"
    return cleaned


@dataclass(frozen=True, slots=True)
class ObservingList:
    """A curated visual observing list and its normalized members."""

    id: str
    name: str
    objects: frozenset[str]
    source: str | None = None
    url: str | None = None
    license: str | None = None
    retrieved: str | None = None
    raw_entry_count: int | None = None
    object_aliases: tuple[tuple[str, str], ...] = ()
    non_dso_entries: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("observing list id must not be blank")
        if not self.name.strip():
            raise ValueError("observing list name must not be blank")


@dataclass(frozen=True, slots=True)
class ObservingMembershipIndex(Mapping[str, frozenset[str]]):
    """Designation memberships plus known canonical physical-object IDs."""

    by_designation: Mapping[str, frozenset[str]]
    canonical_object_ids: frozenset[str] = frozenset()

    def __getitem__(self, key: str) -> frozenset[str]:
        return self.by_designation[key]

    def __iter__(self):
        return iter(self.by_designation)

    def __len__(self) -> int:
        return len(self.by_designation)


def _load_list(path: Path) -> ObservingList:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid observing-list JSON {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"observing-list JSON root must be an object: {path}")

    list_id = str(data.get("id", "")).strip()
    name = str(data.get("name", "")).strip()
    if not list_id:
        raise ValueError(f"observing-list fixture without id: {path}")
    if not name:
        raise ValueError(f"observing-list fixture without name: {path}")

    raw_objects = data.get("objects")
    if not isinstance(raw_objects, list):
        raise ValueError(f"observing-list 'objects' must be a list: {path}")
    objects = frozenset(
        canonical_designation(str(entry)) for entry in raw_objects if str(entry).strip()
    )
    if not objects:
        raise ValueError(f"observing-list fixture has no objects: {path}")

    raw_aliases = data.get("object_aliases", {})
    if not isinstance(raw_aliases, dict):
        raise ValueError(f"observing-list 'object_aliases' must be an object: {path}")
    object_aliases = tuple(
        sorted(
            (canonical_designation(str(source)), canonical_designation(str(target)))
            for source, target in raw_aliases.items()
        )
    )
    raw_non_dso_entries = data.get("non_dso_entries", [])
    if not isinstance(raw_non_dso_entries, list):
        raise ValueError(f"observing-list 'non_dso_entries' must be a list: {path}")
    return ObservingList(
        id=list_id,
        name=name,
        objects=objects,
        source=_optional_str(data.get("source")),
        url=_optional_str(data.get("url")),
        license=_optional_str(data.get("license")),
        retrieved=_optional_str(data.get("retrieved")),
        raw_entry_count=(
            int(data["raw_entry_count"]) if data.get("raw_entry_count") is not None else None
        ),
        object_aliases=object_aliases,
        non_dso_entries=frozenset(
            canonical_designation(str(entry)) for entry in raw_non_dso_entries
        ),
    )


def load_observing_lists(
    directory: str | Path | None = DEFAULT_FIXTURE_DIR,
) -> dict[str, ObservingList]:
    """Load every ``*.json`` observing-list fixture in ``directory``.

    A missing or explicitly empty directory yields an empty mapping; malformed
    fixtures fail loudly so pointing the build at a broken list is never
    silently ignored.
    """
    if directory is None or not str(directory).strip():
        return {}
    root = Path(directory)
    if not root.exists() or str(root) == ".":
        return {}
    lists: dict[str, ObservingList] = {}
    for path in sorted(root.glob(FILENAME)):
        observing_list = _load_list(path)
        if observing_list.id in lists:
            raise ValueError(f"duplicate observing-list id {observing_list.id!r}: {path}")
        lists[observing_list.id] = observing_list
    return lists


def build_membership_index(
    lists: Mapping[str, ObservingList],
    objects: tuple[DeepSkyObject, ...] | list[DeepSkyObject] | None = None,
) -> ObservingMembershipIndex:
    """Build an alias-aware designation index over all observing lists.

    If the physical-object pool is provided, a list match against a canonical
    object ID is not also propagated to a different object that merely carries
    that ID as a cross-reference. This avoids assigning a list membership to,
    for example, a nearby NED subcomponent because it references its host's
    NGC designation.
    """
    index: dict[str, frozenset[str]] = {}
    for list_id, observing_list in lists.items():
        alias_targets = dict(observing_list.object_aliases)
        for designation in observing_list.objects:
            target = alias_targets.get(designation, designation)
            index[target] = index.get(target, frozenset()) | {list_id}
    return ObservingMembershipIndex(
        by_designation=index,
        canonical_object_ids=frozenset(
            canonical_designation(obj.id) for obj in objects or ()
        ),
    )


def dso_memberships(
    dso: DeepSkyObject, index: Mapping[str, frozenset[str]]
) -> frozenset[str]:
    """Return the observing lists that contain ``dso``.

    The object's own identifier and all cross identifiers are considered, so a
    Messier alias (``M87``) or a plain NGC designation (``NGC 4486``) matches
    even though OpenNGC stores the zero-padded form (``NGC4486``).
    """
    memberships: set[str] = set()
    own_id = canonical_designation(dso.id)
    canonical_ids = (
        index.canonical_object_ids if isinstance(index, ObservingMembershipIndex) else frozenset()
    )
    for designation in (dso.id, *dso.cross_ids):
        key = canonical_designation(designation)
        if key != own_id and key in canonical_ids:
            continue
        memberships |= index.get(key, frozenset())
    return frozenset(memberships)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
