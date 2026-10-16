"""Assemble a local alpha PDF download with notices and exact contour data."""

from __future__ import annotations

import argparse
import json
import platform
import shutil
from importlib.metadata import version
from pathlib import Path

import cairo
import gi

from nightsky_atlas.build.preflight import collect_build_inputs, validate_atlas_output
from nightsky_atlas.catalog.manifest import file_sha256, write_manifest

ROOT = Path(__file__).resolve().parents[1]
NOTICES = (
    "LICENSE",
    "THIRD_PARTY_LICENSES.md",
    "docs/ATLAS_DISTRIBUTION.md",
    "docs/DATA_SOURCES.md",
    "data/fixtures/constellations/SOURCE.md",
    "data/fixtures/constellations/LICENSE",
    "data/fixtures/starnames/SOURCE.md",
    "data/fixtures/starnames/LICENSE",
    "data/fixtures/observing_lists/SOURCE.md",
    "data/fixtures/outlines/SOURCE.md",
    "data/fixtures/double_stars/SOURCE.md",
    "data/third_party/d3-celestial/SOURCE.md",
    "data/third_party/d3-celestial/LICENSE",
    "src/nightsky_atlas/assets/fonts/OFL-Lato.txt",
    "src/nightsky_atlas/assets/fonts/OFL-SourceSans3.txt",
)


def prepare_alpha_download(atlas_dir: Path, output: Path) -> Path:
    gi.require_version("Pango", "1.0")
    from gi.repository import Pango

    issues = validate_atlas_output(atlas_dir)
    if issues:
        raise ValueError("invalid atlas output: " + "; ".join(issues))
    manifest = json.loads((atlas_dir / "manifest.json").read_text(encoding="utf-8"))
    fingerprints = manifest.get("input_fingerprints")
    if not isinstance(fingerprints, dict) or not fingerprints:
        raise ValueError("build has no input fingerprints")
    paths = {key: entry["path"] if entry else None for key, entry in fingerprints.items()}
    if collect_build_inputs(paths) != fingerprints:
        raise ValueError("build inputs have changed; rebuild before packaging")
    sources = manifest.get("data_sources", [])
    for source in sources:
        if not isinstance(source.get("manifest"), dict):
            raise ValueError(f"missing catalogue metadata: {source['kind']}")
        if file_sha256(source["path"]) != source["sha256"]:
            raise ValueError(f"catalogue changed: {source['kind']}")
        if source.get("manifest_path"):
            current = json.loads(Path(source["manifest_path"]).read_text(encoding="utf-8"))
            if current != source.get("manifest"):
                raise ValueError(f"catalogue metadata changed: {source['kind']}")
    files = {name: ROOT / name for name in NOTICES}
    for entry in fingerprints.values():
        if entry and entry["kind"] == "file":
            path = Path(entry["path"]).resolve()
            if path.is_relative_to(ROOT) and path.suffix == ".yaml":
                files[path.relative_to(ROOT).as_posix()] = path
    if manifest.get("geometry_catalogues", {}).get("magellanic_clouds"):
        entry = fingerprints.get("magellanic_clouds")
        if not entry or entry.get("kind") != "file":
            raise ValueError("missing exact Gaia contour input")
        relative = "data/third_party/gaia_dr3_magellanic/"
        if entry["sha256"] != file_sha256(ROOT / relative / "contours.geojson"):
            raise ValueError("Gaia contours differ from the documented source; review notices")
        files[relative + "contours.geojson"] = Path(entry["path"])
        for name in ("SOURCE.md", "LICENSE"):
            files[relative + name] = ROOT / relative / name
        files["scripts/generate_magellanic_cloud_contours.py"] = (
            ROOT / "scripts/generate_magellanic_cloud_contours.py"
        )
    for path in files.values():
        if not path.is_file():
            raise ValueError(f"missing distribution notice/input: {path.name}")
    records = [
        {"chart_id": page["chart_id"], **issue}
        for page in manifest["pages"]
        for issue in page.get("layout_issues", [])
    ]
    inventory = {
        "atlas_id": manifest["atlas_id"],
        "source_commit": manifest.get("git_commit"),
        "source_snapshot": "Match the code fingerprint; a commit alone may omit local changes.",
        "input_fingerprints": {
            key: {field: value for field, value in entry.items() if field != "path"}
            if entry else None
            for key, entry in fingerprints.items()
        },
        "catalogues": [
            {
                "kind": source["kind"],
                "sha256": source["sha256"],
                "provenance_sha256": file_sha256(source["manifest_path"])
                if source.get("manifest_path") else None,
                "metadata": {
                    key: source.get("manifest", {}).get(key)
                    for key in ("catalogue", "source", "version", "edition", "license")
                },
                "raw_sources": [
                    {key: entry.get(key) for key in (
                        "catalogue_id", "table", "source_url", "raw_sha256", "reference"
                    )}
                    for entry in source["manifest"].get("sources", [])
                ],
                "ucc_source": source["manifest"].get("ucc_source"),
            }
            for source in sources
        ],
        "main_chart_count": manifest.get("main_chart_count"),
        "detail_chart_count": manifest.get("detail_chart_count"),
        "hard_issues": manifest["total_hard_issues"],
        "publication_preflight": manifest.get("publication_preflight"),
        "packaging_environment": {
            "python": platform.python_version(),
            "os": platform.freedesktop_os_release().get("PRETTY_NAME", "unknown"),
            "cairo": cairo.cairo_version_string(),
            "pango": Pango.version_string(),
            "packages": {
                name: version(name)
                for name in ("nightsky-atlas", "numpy", "scipy", "pycairo", "pydantic",
                             "httpx", "pyyaml")
            },
        },
    }
    output.mkdir(parents=True, exist_ok=False)
    for name, source in files.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    shutil.copyfile(atlas_dir / "atlas.pdf", output / "atlas.pdf")
    write_manifest(output / "release.json", inventory)
    write_manifest(output / "layout-issues.json", records)
    (output / "README.txt").write_text(
        f"NightSky Atlas {manifest['atlas_id']} — experimental alpha\n\n"
        f"Known hard layout findings: {manifest['total_hard_issues']}. "
        "See layout-issues.json.\n"
        "This download is not publication or telescope-field approval.\n"
        "Print atlas.pdf on A4 landscape at 100% / actual size.\n"
        "Read docs/ATLAS_DISTRIBUTION.md and THIRD_PARTY_LICENSES.md.\n"
        "Keep these notices and the data/third_party/gaia_dr3_magellanic files "
        "with shared copies.\n"
        "release.json records build input hashes and the packaging environment; "
        "it does not assert that older PDFs were built in that environment.\n",
        encoding="utf-8",
    )
    checksums = {
        path.relative_to(output).as_posix(): file_sha256(path)
        for path in sorted(output.rglob("*")) if path.is_file()
    }
    write_manifest(output / "checksums.json", checksums)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--atlas-dir", required=True, type=Path)
    parser.add_argument("--outdir", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = prepare_alpha_download(args.atlas_dir, args.outdir)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Cannot prepare download: {exc}\n")
    print(f"Local alpha download prepared: {result}")


if __name__ == "__main__":
    main()
