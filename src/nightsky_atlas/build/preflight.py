"""Input provenance and strict publication checks for atlas builds."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from nightsky_atlas.atlas.config import AtlasConfig, load_atlas_config
from nightsky_atlas.atlas.tiling import TilingSpec, chart_definitions, coverage_report
from nightsky_atlas.catalog.manifest import file_sha256
from nightsky_atlas.catalog.store import StarStore
from nightsky_atlas.chart.models import ChartDefinition

__all__ = [
    "collect_build_inputs",
    "collect_data_sources",
    "validate_atlas_output",
    "validate_publication_inputs",
]


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
            fingerprints[name] = {"path": str(path), "kind": "file", "sha256": file_sha256(path)}
        elif path.is_dir():
            files = sorted(
                item
                for item in path.rglob("*")
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
                "path": str(path),
                "kind": "directory",
                "sha256": digest.hexdigest(),
                "file_count": len(files),
            }
        else:
            fingerprints[name] = {"path": str(path), "kind": "missing", "sha256": None}
    return fingerprints


def collect_data_sources(
    *,
    star_store: str | Path | None,
    faint_star_store: str | Path | None = None,
    stars_csv: str | Path | None,
    dsos_path: str | Path,
    double_stars_path: str | Path | bool | None,
) -> list[dict[str, Any]]:
    """Record only the catalogue files actually selected for this build."""
    selected = (
        ("stars", star_store if star_store is not None else stars_csv),
        ("faint_stars", faint_star_store),
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
        if source["kind"] == "faint_stars" and manifest.get("all_sky_complete") is not True:
            issues.append("publication faint-star supplement does not contain all UCAC4 sky zones")
    if issues:
        raise ValueError("publication preflight failed: " + "; ".join(issues))


def validate_atlas_output(outroot: str | Path, *, publication: bool = False) -> tuple[str, ...]:
    root = Path(outroot)
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        return (f"missing atlas manifest: {manifest_path}",)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return (f"invalid atlas manifest: {exc}",)
    if not isinstance(manifest, dict):
        return ("atlas manifest must be a JSON object",)

    issues: list[str] = []
    pages = manifest.get("pages")
    if not isinstance(pages, list) or not all(isinstance(page, dict) for page in pages):
        return ("atlas manifest has no valid page list",)
    chart_ids = [page.get("chart_id") for page in pages]
    valid_chart_ids = all(isinstance(chart_id, str) for chart_id in chart_ids)
    if not valid_chart_ids:
        issues.append("atlas manifest contains invalid chart IDs")
    elif len(set(chart_ids)) != len(chart_ids):
        issues.append("atlas manifest contains duplicate chart IDs")
    if manifest.get("chart_count") != len(pages):
        issues.append("atlas manifest chart count does not match page list")
    main_chart_ids = manifest.get("main_chart_ids", chart_ids)
    detail_chart_ids = manifest.get("detail_chart_ids", [])
    if not isinstance(main_chart_ids, list) or not isinstance(detail_chart_ids, list):
        issues.append("atlas manifest has invalid main/detail chart ID lists")
    elif [*main_chart_ids, *detail_chart_ids] != chart_ids:
        issues.append("atlas page list does not match its main/detail chart ID lists")
    hard_counts = [page.get("hard_issues") for page in pages]
    if not all(isinstance(count, int) and count >= 0 for count in hard_counts):
        issues.append("atlas manifest contains invalid hard-issue counts")
    elif manifest.get("total_hard_issues") != sum(hard_counts):
        issues.append("atlas manifest hard-issue total does not match pages")

    expected_artifacts = {"atlas.pdf"}
    for chart_id in chart_ids:
        if isinstance(chart_id, str):
            expected_artifacts.add(f"charts/{chart_id}/chart.pdf")
            if manifest.get("render_png") is True:
                expected_artifacts.add(f"charts/{chart_id}/preview.png")
    if manifest.get("draft_report_written") is True:
        expected_artifacts.add("draft-report.json")
    artifacts = manifest.get("output_artifacts")
    if not isinstance(artifacts, dict):
        issues.append("atlas manifest has no output checksums")
        artifacts = {}
    for relative in sorted(expected_artifacts - artifacts.keys()):
        issues.append(f"missing output checksum: {relative}")
    for relative, checksum in sorted(artifacts.items()):
        path = PurePosixPath(relative)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            issues.append(f"unsafe output path: {relative}")
            continue
        target = root.joinpath(*path.parts)
        if not target.resolve().is_relative_to(root.resolve()):
            issues.append(f"unsafe output path: {relative}")
            continue
        if not target.is_file():
            issues.append(f"missing output file: {relative}")
        elif not isinstance(checksum, str) or file_sha256(target) != checksum:
            issues.append(f"output checksum mismatch: {relative}")

    if publication:
        publication_state = manifest.get("publication_preflight")
        if (
            not isinstance(publication_state, dict)
            or publication_state.get("requested") is not True
        ):
            issues.append("atlas was not built in publication mode")
        elif publication_state.get("output_passed") is not True:
            issues.append("publication build did not pass output validation")
        if manifest.get("total_hard_issues") != 0:
            issues.append("atlas contains hard layout issues")
        fingerprints = manifest.get("input_fingerprints")
        if not isinstance(fingerprints, dict) or not fingerprints:
            issues.append("atlas manifest has no input fingerprints")
        else:
            paths = {
                name: entry.get("path") if isinstance(entry, dict) else None
                for name, entry in fingerprints.items()
            }
            if collect_build_inputs(paths) != fingerprints:
                issues.append("atlas input fingerprints are stale")
        sources = manifest.get("data_sources")
        if not isinstance(sources, list) or not sources:
            issues.append("atlas manifest has no catalogue sources")
        else:
            for source in sources:
                if not isinstance(source, dict):
                    issues.append("invalid catalogue source entry")
                    continue
                selected = source.get("path")
                if not isinstance(selected, str) or not Path(selected).is_file():
                    issues.append(f"missing catalogue source: {selected}")
                    continue
                if file_sha256(selected) != source.get("sha256"):
                    issues.append(f"catalogue source changed: {selected}")
                source_manifest = source.get("manifest_path")
                if source_manifest is not None:
                    try:
                        current = json.loads(Path(source_manifest).read_text(encoding="utf-8"))
                    except (OSError, ValueError):
                        current = None
                    if current != source.get("manifest"):
                        issues.append(f"catalogue provenance changed: {selected}")
        config = manifest.get("config")
        atlas_config = config.get("atlas") if isinstance(config, dict) else None
        if isinstance(atlas_config, str) and Path(atlas_config).is_file():
            atlas = load_atlas_config(atlas_config)
            charts = chart_definitions(atlas)
            expected_main_ids = [chart.id for chart in charts]
            expected_detail_ids = [detail.id for detail in atlas.detail_charts]
            if main_chart_ids != expected_main_ids or detail_chart_ids != expected_detail_ids:
                issues.append("atlas chart set differs from the current definition")
            if atlas.tiling is None:
                issues.append("atlas has no full-sky tiling")
            else:
                spec = TilingSpec.from_config(atlas.tiling)
                if not coverage_report(charts, step_deg=spec.coverage_step_deg).covers_all:
                    issues.append("atlas chart tiling has coverage gaps")
        else:
            issues.append("missing atlas definition for publication validation")
    return tuple(issues)
