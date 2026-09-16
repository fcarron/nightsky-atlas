"""Command-line entry point for NightSky Atlas."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from nightsky_atlas import __version__
from nightsky_atlas.ai.base import MockReviewer
from nightsky_atlas.ai.benchmark import load_cases, run_benchmark
from nightsky_atlas.ai.config import load_ai_config
from nightsky_atlas.ai.credentials import load_env_file
from nightsky_atlas.ai.openrouter import OpenRouterReviewer
from nightsky_atlas.ai.recorded import RecordedReviewer
from nightsky_atlas.atlas.config import (
    AtlasConfig,
    ConfigError,
    StyleConfig,
    load_atlas_config,
    load_style_config,
)
from nightsky_atlas.atlas.tiling import (
    TilingSpec,
    coverage_report,
    tile_sky,
    with_neighbours,
)
from nightsky_atlas.build.atlas import build_atlas
from nightsky_atlas.build.chart import build_chart_context
from nightsky_atlas.catalog.dso_store import write_dso_catalog
from nightsky_atlas.catalog.hipparcos import (
    CATALOGUE as HIPPARCOS_CATALOGUE,
)
from nightsky_atlas.catalog.hipparcos import (
    VERSION as HIPPARCOS_VERSION,
)
from nightsky_atlas.catalog.hipparcos import (
    download_hipparcos,
    iter_hipparcos_stars,
)
from nightsky_atlas.catalog.hipparcos import (
    raw_path as hipparcos_raw_path,
)
from nightsky_atlas.catalog.manifest import write_manifest
from nightsky_atlas.catalog.merge import merge_stars
from nightsky_atlas.catalog.openngc import (
    CATALOGUE as OPENNGC_CATALOGUE,
)
from nightsky_atlas.catalog.openngc import (
    download_openngc,
    iter_openngc_objects,
)
from nightsky_atlas.catalog.sample import StarCatalogueError
from nightsky_atlas.catalog.store import StarStore, build_star_store
from nightsky_atlas.catalog.tycho import (
    CATALOGUE,
    CDS_BASE_URL,
    VERSION,
    download_tycho2,
    iter_tycho2_stars,
    raw_part_paths,
)
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.chart.page import PageTransform
from nightsky_atlas.layout.labels import build_dso_labels
from nightsky_atlas.layout.optimizer import OptimizationResult, optimize_labels
from nightsky_atlas.layout.overrides import apply_overrides, load_override_library
from nightsky_atlas.layout.validation import validate_layout
from nightsky_atlas.render.cairo import DebugOptions, render_chart, render_magnitude_scale
from nightsky_atlas.render.review import render_review_png
from nightsky_atlas.review.build import build_review_request
from nightsky_atlas.review.models import ReviewRequest
from nightsky_atlas.scene.models import ChartScene

_DEFAULT_ATLAS = Path("atlas/standard.yaml")
_DEFAULT_STYLE = Path("styles/standard.yaml")
_DEFAULT_STARS = Path("data/fixtures/stars/test_virgo.csv")
_DEFAULT_RAW = Path("data/raw/tycho2")
_DEFAULT_STORE = Path("data/processed/stars/tycho2.sqlite")
_DEFAULT_MANIFEST = Path("data/processed/stars/tycho2.manifest.json")
_DEFAULT_HIP_RAW = Path("data/raw/hipparcos")
_DEFAULT_OPENNGC_RAW = Path("data/raw/openngc")
_DEFAULT_DSO_OUT = Path("data/processed/dso/openngc.json")
_DEFAULT_DSO_MANIFEST = Path("data/processed/dso/openngc.manifest.json")
_DEFAULT_CONSTELLATIONS = Path("data/fixtures/constellations")
_DEFAULT_OUTLINES = Path("data/fixtures/outlines")
_DEFAULT_CASES = Path("benchmarks/ai_review/cases.yaml")
_DEFAULT_BENCH_OUT = Path("benchmarks/ai_review/results")
_DEFAULT_OUTDIR = Path("build")


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser."""
    parser = argparse.ArgumentParser(
        prog="nightsky",
        description="Generate publication-quality printable star atlases.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command")
    _add_chart_commands(subparsers)
    _add_data_commands(subparsers)
    _add_benchmark_commands(subparsers)
    _add_atlas_commands(subparsers)
    return parser


def _add_scene_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--atlas", type=Path, default=_DEFAULT_ATLAS)
    parser.add_argument("--style", type=Path, default=_DEFAULT_STYLE)
    parser.add_argument("--stars", type=Path, default=_DEFAULT_STARS)
    parser.add_argument(
        "--star-store",
        type=Path,
        default=None,
        help="processed SQLite store; takes precedence over --stars",
    )
    parser.add_argument(
        "--magnitude-limit",
        type=float,
        default=None,
        help="faintest magnitude to render (default: atlas setting)",
    )
    parser.add_argument(
        "--dsos",
        type=Path,
        default=None,
        help="processed deep-sky catalogue JSON (default: processed OpenNGC if present)",
    )
    parser.add_argument(
        "--dso-magnitude-limit",
        type=float,
        default=None,
        help="faintest deep-sky magnitude to render (default: atlas setting)",
    )
    parser.add_argument(
        "--constellations",
        type=Path,
        default=_DEFAULT_CONSTELLATIONS,
        help="directory of constellation geometry fixtures (empty to omit)",
    )
    parser.add_argument(
        "--outlines",
        type=Path,
        default=_DEFAULT_OUTLINES,
        help="directory of schematic nebula outline fixtures (empty to omit)",
    )
    parser.add_argument("--outdir", type=Path, default=_DEFAULT_OUTDIR)
    parser.add_argument("--png-dpi", type=float, default=300.0)
    parser.add_argument(
        "--overrides",
        type=Path,
        default=None,
        help="manual override file or directory (stable-ID label overrides)",
    )


def _apply_chart_overrides(
    args: argparse.Namespace, definition: ChartDefinition, labels: tuple
) -> tuple:
    """Apply explicit chart overrides, if given, after initial label layout."""
    path = getattr(args, "overrides", None)
    if path is None:
        return labels
    overrides = load_override_library(path).for_chart(definition.id)
    if overrides is None:
        raise ConfigError(f"no overrides found for chart {definition.id!r} in {path}")
    return apply_overrides(labels, overrides)


def _add_chart_commands(subparsers: argparse._SubParsersAction) -> None:
    chart = subparsers.add_parser("chart", help="build and inspect single charts")
    chart_subparsers = chart.add_subparsers(dest="chart_command")

    render = chart_subparsers.add_parser("render", help="render a chart page")
    render.add_argument("--chart", required=True, help="chart id from the atlas file")
    _add_scene_arguments(render)
    render.add_argument(
        "--labels",
        action="store_true",
        help="draw unoptimized labels using the fixed candidate preference",
    )
    render.add_argument(
        "--optimize",
        action="store_true",
        help="run deterministic label optimization before rendering",
    )
    render.add_argument(
        "--write-layout",
        action="store_true",
        help="write the serialized layout document to chart.json",
    )
    render.add_argument(
        "--debug",
        default="",
        help="comma-separated overlays: label_boxes,exclusion_zones,element_ids,candidate_points",
    )
    render.set_defaults(handler=_command_chart_render)

    validate = chart_subparsers.add_parser(
        "validate", help="validate a chart's hard label constraints"
    )
    validate.add_argument("--chart", required=True, help="chart id from the atlas file")
    _add_scene_arguments(validate)
    validate.add_argument(
        "--optimize",
        action="store_true",
        help="validate the deterministically optimized layout instead of the raw one",
    )
    validate.set_defaults(handler=_command_chart_validate)

    review = chart_subparsers.add_parser(
        "review", help="generate review artifacts (annotated PNG + request JSON)"
    )
    review.add_argument("--chart", required=True, help="chart id from the atlas file")
    _add_scene_arguments(review)
    review.add_argument(
        "--optimize",
        action="store_true",
        help="review the deterministically optimized layout",
    )
    review.add_argument(
        "--model",
        default=None,
        help="OpenRouter model to review with (one step, no iteration)",
    )
    review.add_argument("--ai-config", type=Path, default=Path("ai.yaml"))
    review.set_defaults(handler=_command_chart_review)

    scale = chart_subparsers.add_parser(
        "magnitude-scale", help="render a star magnitude diagnostic page"
    )
    scale.add_argument("--atlas", type=Path, default=_DEFAULT_ATLAS)
    scale.add_argument("--style", type=Path, default=_DEFAULT_STYLE)
    scale.add_argument("--outdir", type=Path, default=_DEFAULT_OUTDIR)
    scale.add_argument("--png-dpi", type=float, default=300.0)
    scale.set_defaults(handler=_command_magnitude_scale)


def _add_data_commands(subparsers: argparse._SubParsersAction) -> None:
    data = subparsers.add_parser("data", help="fetch and import catalogue data")
    data_subparsers = data.add_subparsers(dest="data_command")

    fetch = data_subparsers.add_parser(
        "fetch-stars", help="download raw Tycho-2 parts (network access)"
    )
    fetch.add_argument("--dest", type=Path, default=_DEFAULT_RAW)
    fetch.add_argument("--base-url", default=CDS_BASE_URL)
    fetch.set_defaults(handler=_command_fetch_stars)

    hip_fetch = data_subparsers.add_parser(
        "fetch-hipparcos",
        help="download the raw Hipparcos main catalogue (network access)",
    )
    hip_fetch.add_argument("--dest", type=Path, default=_DEFAULT_HIP_RAW)
    hip_fetch.set_defaults(handler=_command_fetch_hipparcos)

    importer = data_subparsers.add_parser(
        "import-stars",
        help="import Tycho-2 plus the Hipparcos bright-star supplement into a SQLite store",
    )
    importer.add_argument("--raw", type=Path, default=_DEFAULT_RAW)
    importer.add_argument(
        "--bright-raw",
        type=Path,
        default=_DEFAULT_HIP_RAW,
        help="directory containing the raw Hipparcos main catalogue",
    )
    importer.add_argument("--out", type=Path, default=_DEFAULT_STORE)
    importer.add_argument("--manifest", type=Path, default=_DEFAULT_MANIFEST)
    importer.set_defaults(handler=_command_import_stars)

    counter = data_subparsers.add_parser("star-count", help="report stored star count")
    counter.add_argument("--store", type=Path, default=_DEFAULT_STORE)
    counter.set_defaults(handler=_command_star_count)

    dso_fetch = data_subparsers.add_parser(
        "fetch-openngc", help="download raw OpenNGC CSVs (network access)"
    )
    dso_fetch.add_argument("--dest", type=Path, default=_DEFAULT_OPENNGC_RAW)
    dso_fetch.set_defaults(handler=_command_fetch_openngc)

    dso_import = data_subparsers.add_parser(
        "import-openngc", help="import raw OpenNGC CSVs into a processed catalogue"
    )
    dso_import.add_argument("--raw", type=Path, default=_DEFAULT_OPENNGC_RAW)
    dso_import.add_argument("--out", type=Path, default=_DEFAULT_DSO_OUT)
    dso_import.add_argument("--manifest", type=Path, default=_DEFAULT_DSO_MANIFEST)
    dso_import.set_defaults(handler=_command_import_openngc)


def _add_benchmark_commands(subparsers: argparse._SubParsersAction) -> None:
    benchmark = subparsers.add_parser("benchmark", help="run AI review benchmarks")
    benchmark_subparsers = benchmark.add_subparsers(dest="benchmark_command")

    run = benchmark_subparsers.add_parser(
        "ai-review", help="run benchmark cases against a reviewer"
    )
    run.add_argument("--cases", type=Path, default=_DEFAULT_CASES)
    run.add_argument("--atlas", type=Path, default=_DEFAULT_ATLAS)
    run.add_argument("--style", type=Path, default=_DEFAULT_STYLE)
    run.add_argument("--star-store", type=Path, default=_DEFAULT_STORE)
    run.add_argument("--stars", type=Path, default=_DEFAULT_STARS)
    run.add_argument("--dsos", type=Path, default=None)
    run.add_argument("--outdir", type=Path, default=_DEFAULT_BENCH_OUT)
    run.add_argument("--model", default=None, help="OpenRouter model to benchmark")
    run.add_argument("--ai-config", type=Path, default=Path("ai.yaml"))
    run.add_argument(
        "--recorded", type=Path, default=None, help="replay recorded review results"
    )
    run.set_defaults(handler=_command_benchmark_ai_review)


def _add_atlas_commands(subparsers: argparse._SubParsersAction) -> None:
    atlas = subparsers.add_parser("atlas", help="tile and validate complete atlases")
    atlas_subparsers = atlas.add_subparsers(dest="atlas_command")

    tile = atlas_subparsers.add_parser("tile", help="generate chart definitions")
    tile.add_argument("--atlas", type=Path, default=_DEFAULT_ATLAS)
    tile.add_argument("--out", type=Path, default=None)
    tile.add_argument("--no-neighbours", action="store_true")
    tile.set_defaults(handler=_command_atlas_tile)

    coverage = atlas_subparsers.add_parser(
        "coverage", help="check sky coverage of the tiling"
    )
    coverage.add_argument("--atlas", type=Path, default=_DEFAULT_ATLAS)
    coverage.add_argument("--step", type=float, default=2.0)
    coverage.set_defaults(handler=_command_atlas_coverage)

    build = atlas_subparsers.add_parser("build", help="build pages and a combined PDF")
    build.add_argument("--atlas", type=Path, default=_DEFAULT_ATLAS)
    build.add_argument("--style", type=Path, default=_DEFAULT_STYLE)
    build.add_argument("--star-store", type=Path, default=_DEFAULT_STORE)
    build.add_argument("--stars", type=Path, default=_DEFAULT_STARS)
    build.add_argument("--dsos", type=Path, default=None)
    build.add_argument(
        "--constellations",
        type=Path,
        default=_DEFAULT_CONSTELLATIONS,
        help="directory of constellation geometry fixtures (empty to omit)",
    )
    build.add_argument(
        "--outlines",
        type=Path,
        default=_DEFAULT_OUTLINES,
        help="directory of schematic nebula outline fixtures (empty to omit)",
    )
    build.add_argument(
        "--overrides",
        type=Path,
        default=None,
        help="manual override file or directory (stable-ID label overrides)",
    )
    build.add_argument("--outdir", type=Path, default=_DEFAULT_OUTDIR)
    build.add_argument("--limit", type=int, default=None)
    build.add_argument("--charts", default=None, help="comma-separated chart ids")
    build.add_argument("--png-dpi", type=float, default=150.0)
    build.add_argument("--no-png", action="store_true")
    build.add_argument("--no-optimize", action="store_true")
    build.add_argument("--no-front-matter", action="store_true")
    build.set_defaults(handler=_command_atlas_build)


def _chart_context(
    args: argparse.Namespace,
) -> tuple[AtlasConfig, StyleConfig, ChartDefinition, PageGeometry, ChartScene, PageTransform]:
    context = build_chart_context(
        atlas_path=args.atlas,
        style_path=args.style,
        chart_id=args.chart,
        star_store=args.star_store,
        stars_csv=args.stars,
        dsos_path=args.dsos,
        constellations_dir=args.constellations,
        outlines_dir=args.outlines,
        magnitude_limit=args.magnitude_limit,
        dso_magnitude_limit=args.dso_magnitude_limit,
    )
    return (
        context.atlas,
        context.style,
        context.definition,
        context.page,
        context.scene,
        context.transform,
    )


_DEBUG_FLAGS = ("label_boxes", "exclusion_zones", "element_ids", "candidate_points")


def _parse_debug(value: str) -> DebugOptions | None:
    flags = {flag.strip() for flag in value.split(",") if flag.strip()}
    if not flags:
        return None
    unknown = flags - set(_DEBUG_FLAGS)
    if unknown:
        raise ConfigError(f"unknown debug flag(s): {', '.join(sorted(unknown))}")
    return DebugOptions(**{flag: flag in flags for flag in _DEBUG_FLAGS})


def _command_chart_render(args: argparse.Namespace) -> int:
    atlas, style, definition, _page, scene, transform = _chart_context(args)

    has_labels = bool(args.labels or args.optimize or args.overrides)
    labels = build_dso_labels(scene, transform, style) if has_labels else ()
    labels = _apply_chart_overrides(args, definition, labels)
    result: OptimizationResult | None = None
    if args.optimize:
        result = optimize_labels(labels, scene, transform, style)
        labels = result.labels
        print(
            f"optimized: cost {result.cost_before:.1f} -> {result.cost_after:.1f}, "
            f"{result.placed_count} placed, {result.hidden_count} hidden"
        )

    outdir = args.outdir / atlas.id / "charts" / definition.id
    render_chart(
        scene,
        transform,
        style,
        labels=labels,
        debug=_parse_debug(args.debug),
        pdf_path=outdir / "chart.pdf",
        png_path=outdir / "preview.png",
        png_dpi=args.png_dpi,
    )
    if args.write_layout:
        _write_layout_json(outdir / "chart.json", definition, scene, labels, result)
    print(
        f"{definition.id}: {scene.star_count} stars, {scene.dso_count} DSOs, "
        f"{len(labels)} labels -> {outdir / 'chart.pdf'}"
    )
    return 0


def _command_chart_review(args: argparse.Namespace) -> int:
    atlas, style, definition, _page, scene, transform = _chart_context(args)
    labels = build_dso_labels(scene, transform, style)
    labels = _apply_chart_overrides(args, definition, labels)
    if args.optimize:
        result = optimize_labels(labels, scene, transform, style)
        labels = result.labels
    validation = validate_layout(labels, scene, transform, style)

    placed = sum(1 for label in labels if not label.hidden and label.candidates)
    diagnostics = {
        "label_count": float(len(labels)),
        "placed_count": float(placed),
        "hidden_count": float(len(labels) - placed),
        "hard_issue_count": float(len(validation.issues)),
    }

    outdir = args.outdir / atlas.id / "charts" / definition.id
    review_png = outdir / "review.png"
    render_review_png(scene, transform, style, labels, review_png, png_dpi=args.png_dpi)
    request = build_review_request(
        page_id=f"{atlas.id}:{definition.id}",
        scene=scene,
        labels=labels,
        transform=transform,
        diagnostics=diagnostics,
        images=(str(review_png),),
    )
    request_path = outdir / "review.json"
    request_path.parent.mkdir(parents=True, exist_ok=True)
    request_path.write_text(
        json.dumps(request.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"{definition.id}: review with {len(request.elements)} elements, "
        f"{int(diagnostics['hard_issue_count'])} hard issues -> {review_png}"
    )

    if args.model is not None:
        _run_one_step_review(args, request, outdir)
    return 0


def _run_one_step_review(
    args: argparse.Namespace, request: ReviewRequest, outdir: Path
) -> None:
    timeout_s = 60.0
    max_retries = 3
    if args.ai_config.exists():
        config = load_ai_config(args.ai_config)
        timeout_s = config.timeout_s
        max_retries = config.max_retries
    reviewer = OpenRouterReviewer(
        model=args.model, timeout_s=timeout_s, max_retries=max_retries
    )
    result = reviewer.review(request)
    (outdir / "review-result.json").write_text(
        json.dumps(result.model_dump(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    usage = reviewer.last_usage
    print(
        f"AI review: score {result.page_score:g}, {len(result.issues)} issues"
        + (f", cost ${usage.cost_usd:.4f}" if usage and usage.cost_usd is not None else "")
    )


def _write_layout_json(
    path: Path,
    definition: ChartDefinition,
    scene: ChartScene,
    labels: tuple,
    result: OptimizationResult | None,
) -> None:
    document: dict = {
        "chart": definition.to_dict(),
        "scene": {
            "star_count": scene.star_count,
            "dso_count": scene.dso_count,
        },
        "labels": [label.to_dict() for label in labels],
    }
    if result is not None:
        document["optimization"] = {
            "cost_before": result.cost_before,
            "cost_after": result.cost_after,
            "placed_count": result.placed_count,
            "hidden_count": result.hidden_count,
            "component_totals_before": result.component_totals_before,
            "component_totals_after": result.component_totals_after,
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _command_chart_validate(args: argparse.Namespace) -> int:
    _atlas, style, definition, _page, scene, transform = _chart_context(args)
    labels = build_dso_labels(scene, transform, style)
    labels = _apply_chart_overrides(args, definition, labels)
    if args.optimize:
        result = optimize_labels(labels, scene, transform, style)
        labels = result.labels
        print(
            f"optimized: cost {result.cost_before:.1f} -> {result.cost_after:.1f}, "
            f"{result.placed_count} placed, {result.hidden_count} hidden"
        )
    result_validation = validate_layout(labels, scene, transform, style)

    print(f"{definition.id}: {len(labels)} labels")
    if result_validation.is_valid:
        print("no hard violations")
        return 0
    for issue_type, count in result_validation.count_by_type().items():
        print(f"  {issue_type}: {count}")
    for issue in result_validation.issues[:20]:
        print(f"  {issue.id}: {issue.message}")
    if len(result_validation.issues) > 20:
        print(f"  ... and {len(result_validation.issues) - 20} more")
    return 1


def _command_magnitude_scale(args: argparse.Namespace) -> int:
    atlas = load_atlas_config(args.atlas)
    style = load_style_config(args.style)
    page = atlas.page.to_geometry()

    outdir = args.outdir / atlas.id / "diagnostics"
    render_magnitude_scale(
        page,
        style,
        pdf_path=outdir / "magnitude-scale.pdf",
        png_path=outdir / "magnitude-scale.png",
        png_dpi=args.png_dpi,
    )
    print(f"magnitude scale -> {outdir / 'magnitude-scale.pdf'}")
    return 0


def _command_fetch_stars(args: argparse.Namespace) -> int:
    paths = download_tycho2(args.dest, base_url=args.base_url)
    print(f"downloaded {len(paths)} parts -> {args.dest}")
    return 0


def _command_fetch_hipparcos(args: argparse.Namespace) -> int:
    path = download_hipparcos(args.dest)
    print(f"downloaded Hipparcos main catalogue -> {path}")
    return 0


def _command_import_stars(args: argparse.Namespace) -> int:
    parts = raw_part_paths(args.raw)
    missing = [path for path in parts if not path.exists()]
    if missing:
        raise ConfigError(
            f"missing {len(missing)} raw part(s) under {args.raw}; "
            "run 'nightsky data fetch-stars' first"
        )
    bright_path = hipparcos_raw_path(args.bright_raw)
    if not bright_path.exists():
        raise ConfigError(
            f"missing bright-star catalogue {bright_path}; "
            "run 'nightsky data fetch-hipparcos' first"
        )
    tycho = iter_tycho2_stars(parts)
    bright = iter_hipparcos_stars(bright_path)
    count = build_star_store(args.out, merge_stars(tycho, bright))
    manifest = {
        "catalogue": CATALOGUE,
        "version": VERSION,
        "source": "The Tycho-2 Catalogue (Hog et al. 2000), CDS I/259",
        "license": "CC-BY-NC-3.0 IGO",
        "epoch": "J2000",
        "magnitude_rule": "V = VT - 0.090 * (BT - VT); VT or BT fallback",
        "coordinate_rule": "ICRS mean J2000 position; observed position fallback",
        "raw_files": [path.name for path in parts],
        "star_count": count,
        "processed_file": args.out.name,
        "bright_star_supplement": {
            "catalogue": HIPPARCOS_CATALOGUE,
            "version": HIPPARCOS_VERSION,
            "source": "The Hipparcos and Tycho Catalogues (ESA 1997), CDS I/239",
            "license": "CC-BY-NC-3.0 IGO",
            "magnitude_rule": "Johnson V (Vmag); Hpmag fallback",
            "coordinate_rule": (
                "ICRS position at J1991.25 propagated to J2000 with catalogue proper motion"
            ),
            "match_rule": "Hipparcos star dropped when a Tycho-2 star lies within 3 arcsec",
            "raw_file": bright_path.name,
        },
    }
    write_manifest(args.manifest, manifest)
    print(f"imported {count} stars -> {args.out}")
    print(f"manifest -> {args.manifest}")
    return 0


def _command_star_count(args: argparse.Namespace) -> int:
    with StarStore.open(args.store) as store:
        print(f"{store.count()} stars in {args.store}")
    return 0


def _command_fetch_openngc(args: argparse.Namespace) -> int:
    paths = download_openngc(args.dest)
    print(f"downloaded {len(paths)} files -> {args.dest}")
    return 0


def _command_import_openngc(args: argparse.Namespace) -> int:
    files = [args.raw / "NGC.csv", args.raw / "addendum.csv"]
    missing = [path for path in files if not path.exists()]
    if missing:
        raise ConfigError(
            f"missing {len(missing)} raw file(s) under {args.raw}; "
            "run 'nightsky data fetch-openngc' first"
        )
    objects = list(iter_openngc_objects(files))
    count = write_dso_catalog(args.out, objects)
    manifest = {
        "catalogue": OPENNGC_CATALOGUE,
        "source": "OpenNGC (mattiaverga/OpenNGC)",
        "license": "CC-BY-SA-4.0",
        "epoch": "J2000",
        "magnitude_rule": "V-Mag preferred, B-Mag fallback",
        "coordinate_rule": "sexagesimal RA/Dec converted to degrees",
        "raw_files": [path.name for path in files],
        "object_count": count,
        "processed_file": args.out.name,
    }
    write_manifest(args.manifest, manifest)
    print(f"imported {count} deep-sky objects -> {args.out}")
    print(f"manifest -> {args.manifest}")
    return 0


def _command_atlas_tile(args: argparse.Namespace) -> int:
    atlas = load_atlas_config(args.atlas)
    if atlas.tiling is None:
        raise ConfigError(f"atlas {atlas.id!r} has no tiling section")
    charts = tile_sky(atlas.id, TilingSpec.from_config(atlas.tiling))
    if not args.no_neighbours:
        charts = with_neighbours(charts)
    out = args.out if args.out is not None else Path("build") / atlas.id / "tiles" / "charts.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps([chart.to_dict() for chart in charts], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"{len(charts)} charts -> {out}")
    return 0


def _command_atlas_coverage(args: argparse.Namespace) -> int:
    atlas = load_atlas_config(args.atlas)
    if atlas.tiling is None:
        raise ConfigError(f"atlas {atlas.id!r} has no tiling section")
    charts = tile_sky(atlas.id, TilingSpec.from_config(atlas.tiling))
    report = coverage_report(charts, step_deg=args.step)
    print(
        f"samples={report.sample_count} gaps={report.gap_count} "
        f"max_overlap={report.max_overlap}"
    )
    for ra, dec in report.gaps[:10]:
        print(f"  gap ra={ra:.1f} dec={dec:.1f}")
    return 0 if report.covers_all else 1


def _command_atlas_build(args: argparse.Namespace) -> int:
    chart_ids = None
    if args.charts:
        chart_ids = tuple(part.strip() for part in args.charts.split(",") if part.strip())
    result = build_atlas(
        atlas_path=args.atlas,
        style_path=args.style,
        outdir=args.outdir,
        star_store=args.star_store,
        stars_csv=args.stars,
        dsos_path=args.dsos,
        constellations_dir=args.constellations,
        outlines_dir=args.outlines,
        overrides_path=args.overrides,
        chart_ids=chart_ids,
        limit=args.limit,
        optimize=not args.no_optimize,
        render_png=not args.no_png,
        png_dpi=args.png_dpi,
        write_front_matter=not args.no_front_matter,
    )
    print(
        f"{result.atlas_id}: {len(result.pages)} charts, "
        f"{result.total_hard_issues} hard issues -> {result.combined_pdf}"
    )
    print(f"manifest -> {result.manifest_path}")
    return 0 if result.total_hard_issues == 0 else 1


def _command_benchmark_ai_review(args: argparse.Namespace) -> int:
    cases = load_cases(args.cases)
    if args.recorded is not None:
        reviewer = RecordedReviewer.from_file(args.recorded)
    elif args.model is not None:
        timeout_s = 60.0
        max_retries = 3
        if args.ai_config.exists():
            config = load_ai_config(args.ai_config)
            timeout_s = config.timeout_s
            max_retries = config.max_retries
        reviewer = OpenRouterReviewer(
            model=args.model, timeout_s=timeout_s, max_retries=max_retries
        )
    else:
        reviewer = MockReviewer()

    report = run_benchmark(
        cases,
        reviewer,
        atlas_path=args.atlas,
        style_path=args.style,
        star_store=args.star_store,
        stars_csv=args.stars,
        dsos_path=args.dsos,
        outdir=args.outdir,
    )
    out = Path(args.outdir) / "report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    summary = report.to_dict()["summary"]
    print(
        f"cases={summary['cases']} schema={summary['schema_compliance']:.2f} "
        f"detected={summary['detected']}/{summary['known_problems']} "
        f"false_positives={summary['false_positives']} cost=${summary['total_cost_usd']:.4f}"
        f" -> {out}"
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface and return a process exit code."""
    load_env_file()
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 0
    try:
        return handler(args)
    except (ConfigError, StarCatalogueError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1