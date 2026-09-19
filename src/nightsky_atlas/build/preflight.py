"""Input provenance and strict publication checks for atlas builds."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from nightsky_atlas.atlas.config import AtlasConfig
from nightsky_atlas.atlas.tiling import TilingSpec, coverage_report
from nightsky_atlas.catalog.manifest import file_sha256
from nightsky_atlas.catalog.store import StarStore
from nightsky_atlas.chart.models import ChartDefinition

__all__ = ["collect_build_inputs", "collect_data_sources", "validate_publication_inputs"]


def collect_build_inputs(
    paths: Mapping[str, str | Path | None],
) -> dict[str, dict[str, Any] | None]:
    fingerprints: dict[str, dict[str, Any] | None] = {}
    for name, selected in sorted(paths.items()):
        if selected is None:
            fingerprints[name] = None
            continue
        path = Path(selected)
        if path.is_file():
            fingerprints[name] = {
                "path": str(path), "kind": "file", "sha256": file_sha256(path)
            }
        elif path.is_dir():
            files = sorted(
                item for item in path.rglob("*")
                if item.is_file() and "__pycache__" not in item.parts and item.suffix != ".pyc"
            )
            digest = hashlib.sha256()
            for item in files:
                relative = item.relative_to(path).as_posix()
                digest.update(relative.encode("utf-8"))
                digest.update(b"\0")
                digest.update(file_sha256(item).encode("ascii"))
                digest.update(b"\0")
            fingerprints[name] = {
                "path": str(path), "kind": "directory", "sha256": digest.hexdigest(),
                "file_count": len(files),
            }
        else:
            fingerprints[name] = {"path": str(path), "kind": "missing", "sha256": None}
    return fingerprints


def collect_data_sources(
    *,
    star_store: str | Path | None,
    stars_csv: str | Path | None,
    dsos_path: str | Path,
    double_stars_path: str | Path | bool | None,
) -> list[dict[str, Any]]:
    """Record only the catalogue files actually selected for this build."""
    selected = (
        ("stars", star_store if star_store is not None else stars_csv),
        ("deep_sky", dsos_path),
        ("double_stars", double_stars_path if double_stars_path is not False else None),
    )
    sources: list[dict[str, Any]] = []
    for kind, selected_path in selected:
        if selected_path is None:
            continue
        path = Path(selected_path)
        if not path.is_file():
            continue
        manifest_path = path.with_suffix(".manifest.json")
        manifest = None
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(manifest, dict):
                raise ValueError(f"source manifest must be a JSON object: {manifest_path}")
        sources.append(
            {
                "kind": kind,
                "path": str(path),
                "sha256": file_sha256(path),
                "manifest_path": str(manifest_path) if manifest is not None else None,
                "manifest": manifest,
            }
        )
    return sources


def validate_publication_inputs(
    atlas: AtlasConfig,
    all_charts: tuple[ChartDefinition, ...],
    selected_charts: tuple[ChartDefinition, ...],
    *,
    star_store: str | Path | None,
    dso_count: int,
    data_sources: list[dict[str, Any]],
) -> None:
    """Reject incomplete or untraceable inputs before writing a release PDF."""
    issues: list[str] = []
    if not all_charts or len(selected_charts) != len(all_charts):
        issues.append("publication requires every chart in the atlas definition")
    if atlas.tiling is None:
        issues.append("publication requires a full-sky tiling definition")
    else:
        spec = TilingSpec.from_config(atlas.tiling)
        coverage = coverage_report(all_charts, step_deg=spec.coverage_step_deg)
        if not coverage.covers_all:
            issues.append(f"chart tiling has {coverage.gap_count} sampled coverage gaps")
    if star_store is None:
        issues.append("publication requires a processed star store, not a sample CSV")
    elif Path(star_store).is_file():
        with StarStore.open(star_store) as store:
            if store.count() == 0:
                issues.append("processed star store is empty")
    if dso_count == 0:
        issues.append("deep-sky catalogue is empty")
    by_kind = {source["kind"]: source for source in data_sources}
    for kind in ("stars", "deep_sky"):
        if kind not in by_kind:
            issues.append(f"missing {kind} catalogue")
    for source in data_sources:
        manifest = source["manifest"]
        if not isinstance(manifest, dict):
            issues.append(f"missing provenance manifest for {source['path']}")
            continue
        if manifest.get("processed_file") != Path(source["path"]).name:
            issues.append(f"provenance manifest does not match {source['path']}")
        if manifest.get("processed_sha256") != source["sha256"]:
            issues.append(f"processed catalogue checksum does not match {source['path']}")
        if not manifest.get("source") or not manifest.get("license"):
            issues.append(f"incomplete source or license metadata for {source['path']}")
    if issues:
        raise ValueError("publication preflight failed: " + "; ".join(issues))
