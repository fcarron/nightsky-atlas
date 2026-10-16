"""Command-line entry point for NightSky Atlas."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from nightsky_atlas import __version__
from nightsky_atlas.ai.config import load_ai_config
from nightsky_atlas.ai.credentials import load_env_file
from nightsky_atlas.ai.openrouter import OpenRouterReviewer
from nightsky_atlas.atlas.config import (
    AtlasConfig,
    ConfigError,
    StyleConfig,
    load_atlas_config,
    load_style_config,
)
from nightsky_atlas.atlas.overview import build_overview, hemisphere_for
from nightsky_atlas.atlas.report import build_draft_report, render_text_summary
from nightsky_atlas.atlas.tiling import (
    TilingSpec,
    chart_definitions,
    coverage_report,
    tile_sky,
    with_neighbours,
)
from nightsky_atlas.build.atlas import build_atlas
from nightsky_atlas.build.chart import build_chart_context
from nightsky_atlas.build.preflight import validate_atlas_output
from nightsky_atlas.build.progress import Progress
from nightsky_atlas.catalog.constellations import load_constellations
from nightsky_atlas.catalog.dso_store import load_dso_catalog
from nightsky_atlas.catalog.sample import StarCatalogueError
from nightsky_atlas.catalog.selection_analysis import (
    explain_selection,
    find_object,
)
from nightsky_atlas.catalog.star_names import (
    DEFAULT_FIXTURE_DIR as STAR_NAMES_FIXTURE_DIR,
)
from nightsky_atlas.catalog.star_names import (
    load_star_names,
)
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.chart.page import PageTransform
from nightsky_atlas.chart.presentation import presentation_from_edition
from nightsky_atlas.cli_data import add_data_commands
from nightsky_atlas.layout.labels import build_labels
from nightsky_atlas.layout.optimizer import OptimizationResult, optimize_labels
from nightsky_atlas.layout.overrides import (
    ChartOverrides,
    apply_overrides,
    load_override_library,
)
from nightsky_atlas.layout.selection import select_labels
from nightsky_atlas.layout.validation import validate_layout
from nightsky_atlas.render.cairo import (
    DebugOptions,
    render_chart,
    render_edition_magnitude_scale,
    render_magnitude_scale,
)
from nightsky_atlas.render.furniture import furniture_obstacles
from nightsky_atlas.render.overview import LocatorInset
from nightsky_atlas.render.review import render_review_png
from nightsky_atlas.review.build import build_review_request
from nightsky_atlas.review.models import ReviewRequest
from nightsky_atlas.scene.models import ChartScene

_DEFAULT_ATLAS = Path("atlas/standard.yaml")
_DEFAULT_STYLE = Path("styles/standard.yaml")
_DEFAULT_STARS = Path("data/fixtures/stars/test_virgo.csv")
_DEFAULT_STORE = Path("data/processed/stars/tycho2.sqlite")
_DEFAULT_COMBINED_DSO_OUT = Path("data/processed/dso/catalogue.json")
_DEFAULT_CONSTELLATIONS = Path("data/fixtures/constellations")
_DEFAULT_OUTLINES = Path("data/fixtures/outlines")
_DEFAULT_STAR_NAMES = STAR_NAMES_FIXTURE_DIR
_DEFAULT_OBSERVING_LISTS = Path("data/fixtures/observing_lists")
_DEFAULT_OBSERVING_CONFIG = Path("config/observing_lists.yaml")
_DEFAULT_OUTDIR = Path("build")
_EDITIONS = ("pocket", "standard", "deep")


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
    add_data_commands(subparsers)
    _add_review_commands(subparsers)
    _add_atlas_commands(subparsers)
    return parser


def _option_was_supplied(arguments: Sequence[str], option: str) -> bool:
    return any(argument == option or argument.startswith(f"{option}=") for argument in arguments)


def _apply_edition_preset(args: argparse.Namespace, arguments: Sequence[str]) -> None:
    """Resolve an edition to matching preset paths without overriding explicit paths."""
    edition = getattr(args, "edition", None)
    if edition is None:
        return
    if hasattr(args, "atlas") and not _option_was_supplied(arguments, "--atlas"):
        args.atlas = Path("atlas") / f"{edition}.yaml"
    if hasattr(args, "style") and not _option_was_supplied(arguments, "--style"):
        args.style = Path("styles") / f"{edition}.yaml"


def _apply_disabled_inputs(args: argparse.Namespace) -> None:
    """Turn explicit CLI opt-outs into the false sentinel understood by builders."""
    for flag, attribute in (
        ("no_constellations", "constellations"),
        ("no_outlines", "outlines"),
        ("no_star_names", "star_names"),
        ("no_observing_lists", "observing_lists"),
        ("no_double_stars", "double_stars"),
    ):
        if getattr(args, flag, False):
            setattr(args, attribute, False)


def _add_scene_arguments(
    parser: argparse.ArgumentParser, *, single_chart: bool = True
) -> None:
    _add_edition_argument(parser)
    parser.add_argument("--atlas", type=Path, default=_DEFAULT_ATLAS)
    parser.add_argument("--style", type=Path, default=_DEFAULT_STYLE)
    parser.add_argument("--stars", type=Path, default=_DEFAULT_STARS)
    parser.add_argument(
        "--star-store",
        type=Path,
        default=None if single_chart else _DEFAULT_STORE,
        help="processed SQLite store; takes precedence over --stars",
    )
    if single_chart:
        parser.add_argument(
            "--magnitude-limit",
            type=float,
            default=None,
            help="faintest magnitude to render (default: atlas setting)",
        )
    parser.add_argument(
        "--faint-star-store",
        type=Path,
        default=None,
        help="optional UCAC4 faint-star store; disabled by default",
    )
    parser.add_argument(
        "--faint-star-limit",
        type=float,
        default=None,
        help="required magnitude limit when faint-star store is enabled",
    )
    parser.add_argument(
        "--dsos",
        type=Path,
        default=None,
        help=(
            "processed deep-sky catalogue JSON (default: merged catalogue if present, "
            "otherwise OpenNGC)"
        ),
    )
    parser.add_argument(
        "--constellations",
        type=Path,
        default=_DEFAULT_CONSTELLATIONS,
        help="directory of constellation geometry fixtures",
    )
    parser.add_argument(
        "--no-constellations", action="store_true", help="omit constellation geometry"
    )
    parser.add_argument(
        "--outlines",
        type=Path,
        default=_DEFAULT_OUTLINES,
        help="directory of schematic nebula outline fixtures",
    )
    parser.add_argument("--no-outlines", action="store_true", help="omit nebula outlines")
    parser.add_argument(
        "--star-names",
        type=Path,
        default=_DEFAULT_STAR_NAMES,
        help="directory of star-name fixtures for bright-star labels",
    )
    parser.add_argument("--no-star-names", action="store_true", help="omit star-name labels")
    parser.add_argument(
        "--observing-lists",
        type=Path,
        default=_DEFAULT_OBSERVING_LISTS,
        help="directory of observing-list fixtures for DSO selection",
    )
    parser.add_argument(
        "--no-observing-lists", action="store_true", help="disable observing-list selection"
    )
    parser.add_argument(
        "--observing-config",
        type=Path,
        default=_DEFAULT_OBSERVING_CONFIG,
        help="observing-list selection policy YAML",
    )
    parser.add_argument(
        "--double-stars",
        type=Path,
        default=None,
        help="processed WDS double/multiple star overlay JSON (default: processed WDS if present)",
    )
    parser.add_argument("--no-double-stars", action="store_true", help="omit the WDS overlay")
    if single_chart:
        parser.add_argument(
            "--double-star-match-tolerance-arcsec",
            type=float,
            default=2.0,
            help="positional tolerance when linking WDS systems to stars",
        )
    parser.add_argument("--outdir", type=Path, default=_DEFAULT_OUTDIR)
    parser.add_argument("--png-dpi", type=float, default=300.0 if single_chart else 150.0)
    parser.add_argument(
        "--overrides",
        type=Path,
        default=None,
        help="manual override file or directory (stable-ID label overrides)",
    )


def _add_edition_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--edition",
        choices=_EDITIONS,
        default=None,
        help="select matching atlas and style presets (Pocket, Standard or Deep)",
    )


def _load_chart_overrides(
    args: argparse.Namespace, definition: ChartDefinition
) -> ChartOverrides | None:
    """Load explicit chart overrides, if any, for this chart."""
    path = getattr(args, "overrides", None)
    if path is None:
        return None
    overrides = load_override_library(path).for_chart(definition.id)
    if overrides is None:
        raise ConfigError(f"no overrides found for chart {definition.id!r} in {path}")
    return overrides


def _protected_label_ids(overrides: ChartOverrides | None) -> frozenset[str]:
    """Return label IDs a manual override refers to, so selection keeps them.

    A hidden override may be dropped; every other override (a moved candidate,
    a lock, an explicit un-hide) must survive the density selection pass so the
    override contract is not silently broken.
    """
    if overrides is None:
        return frozenset()
    return frozenset(
        label_id for label_id, spec in overrides.labels.items() if spec.hidden is not True
    )


def _apply_chart_overrides(
    args: argparse.Namespace, definition: ChartDefinition, labels: tuple
) -> tuple:
    """Apply explicit chart overrides, if given, after initial label layout."""
    overrides = _load_chart_overrides(args, definition)
    if overrides is None:
        return labels
    return apply_overrides(labels, overrides)


def _select_labels(
    args: argparse.Namespace,
    definition: ChartDefinition,
    labels: tuple,
    scene: ChartScene,
    transform: PageTransform,
    style,
) -> tuple:
    """Run deterministic label selection, protecting overridden labels."""
    overrides = _load_chart_overrides(args, definition)
    return select_labels(
        labels,
        scene,
        transform,
        style,
        protected_ids=_protected_label_ids(overrides),
    )


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
        "--placement-diagnostics",
        action="store_true",
        help="include detailed DSO alternative-candidate diagnostics in chart.json",
    )
    render.add_argument(
        "--debug",
        default="",
        help=(
            "comma-separated overlays: label_boxes,exclusion_zones,element_ids,"
            "candidate_points,line_knockouts"
        ),
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
    _add_edition_argument(scale)
    scale.add_argument("--atlas", type=Path, default=_DEFAULT_ATLAS)
    scale.add_argument("--style", type=Path, default=_DEFAULT_STYLE)
    scale.add_argument("--outdir", type=Path, default=_DEFAULT_OUTDIR)
    scale.add_argument("--png-dpi", type=float, default=300.0)
    scale.add_argument(
        "--edition-comparison",
        action="store_true",
        help="render Pocket, Standard and Deep star curves on one A4 test sheet",
    )
    scale.set_defaults(handler=_command_magnitude_scale)


def _add_review_commands(subparsers: argparse._SubParsersAction) -> None:
    review = subparsers.add_parser("review", help="review and edit chart layouts")
    review_subparsers = review.add_subparsers(dest="review_command")
    editor = review_subparsers.add_parser(
        "editor", help="open a local browser-based label editor for one chart"
    )
    editor.add_argument("--edition", choices=("pocket", "standard", "deep"), default="pocket")
    editor.add_argument("--atlas", type=Path, default=Path("atlas/pocket.yaml"))
    editor.add_argument("--style", type=Path, default=Path("styles/pocket.yaml"))
    editor.add_argument("--chart", required=True, help="chart code or ID, e.g. P11 or pocket-011")
    editor.add_argument("--star-store", type=Path, default=_DEFAULT_STORE)
    editor.add_argument("--dsos", type=Path, default=None)
    editor.add_argument(
        "--overrides", type=Path, default=None, help="existing override file or directory"
    )
    editor.add_argument("--outdir", type=Path, default=None, help="editor state directory")
    editor.add_argument("--ai-config", type=Path, default=Path("ai.yaml"))
    editor.add_argument("--port", type=int, default=8765)
    editor.add_argument("--png-dpi", type=float, default=150.0)
    editor.set_defaults(handler=_command_review_editor)


def _add_atlas_commands(subparsers: argparse._SubParsersAction) -> None:
    atlas = subparsers.add_parser("atlas", help="tile and validate complete atlases")
    atlas_subparsers = atlas.add_subparsers(dest="atlas_command")
    why_object = atlas_subparsers.add_parser(
        "why-object", help="explain current edition selection for an object"
    )
    why_object.add_argument("--catalogue", type=Path, default=_DEFAULT_COMBINED_DSO_OUT)
    why_object.add_argument("--observing-config", type=Path, default=_DEFAULT_OBSERVING_CONFIG)
    why_object.add_argument("--observing-lists", type=Path, default=_DEFAULT_OBSERVING_LISTS)
    why_object.add_argument(
        "--edition",
        choices=("pocket", "standard", "deep", "eyepiece", "reference"),
        default=None,
    )
    why_object.add_argument("--atlas", type=Path, default=Path("atlas/pocket.yaml"))
    why_object.add_argument("designation", help="canonical designation or known alias")
    why_object.set_defaults(handler=_command_why_object)

    tile = atlas_subparsers.add_parser("tile", help="generate chart definitions")
    _add_edition_argument(tile)
    tile.add_argument("--atlas", type=Path, default=_DEFAULT_ATLAS)
    tile.add_argument("--out", type=Path, default=None)
    tile.add_argument("--no-neighbours", action="store_true")
    tile.set_defaults(handler=_command_atlas_tile)

    coverage = atlas_subparsers.add_parser("coverage", help="check sky coverage of the tiling")
    _add_edition_argument(coverage)
    coverage.add_argument("--atlas", type=Path, default=_DEFAULT_ATLAS)
    coverage.add_argument("--step", type=float, default=2.0)
    coverage.set_defaults(handler=_command_atlas_coverage)

    report = atlas_subparsers.add_parser(
        "report", help="summarize a tiled atlas draft (coverage, density, review list)"
    )
    _add_edition_argument(report)
    report.add_argument("--atlas", type=Path, default=_DEFAULT_ATLAS)
    report.add_argument("--outdir", type=Path, default=_DEFAULT_OUTDIR)
    report.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="built manifest for per-page density (default: <outdir>/<atlas>/manifest.json)",
    )
    report.add_argument("--coverage-step", type=float, default=None)
    report.add_argument("--out", type=Path, default=None)
    report.set_defaults(handler=_command_atlas_report)

    validate = atlas_subparsers.add_parser(
        "validate", help="check a built atlas and its recorded input fingerprints"
    )
    _add_edition_argument(validate)
    validate.add_argument("--atlas", type=Path, default=_DEFAULT_ATLAS)
    validate.add_argument("--outdir", type=Path, default=_DEFAULT_OUTDIR)
    validate.add_argument("--publication", action="store_true")
    validate.set_defaults(handler=_command_atlas_validate)

    build = atlas_subparsers.add_parser("build", help="build pages and a combined PDF")
    _add_scene_arguments(build, single_chart=False)
    build.add_argument("--limit", type=int, default=None)
    build.add_argument("--charts", default=None, help="comma-separated chart ids")
    build.add_argument("--jobs", type=int, default=2, help="parallel chart workers (default: 2)")
    build.add_argument("--no-png", action="store_true")
    build.add_argument("--no-optimize", action="store_true")
    build.add_argument("--no-front-matter", action="store_true")
    build.add_argument(
        "--no-overviews",
        action="store_true",
        help="omit the front-of-atlas north/south overview pages",
    )
    build.add_argument("--no-draft-report", action="store_true")
    build.add_argument(
        "--publication",
        action="store_true",
        help="require complete coverage, core catalogues and matching provenance manifests",
    )
    build.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="log per-stage timings for every chart (where the time goes)",
    )
    build.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="suppress progress output (final summary only)",
    )
    build.set_defaults(handler=_command_atlas_build)


def _chart_context(
    args: argparse.Namespace,
) -> tuple[AtlasConfig, StyleConfig, ChartDefinition, PageGeometry, ChartScene, PageTransform]:
    context = build_chart_context(
        atlas_path=args.atlas,
        style_path=args.style,
        chart_id=args.chart,
        star_store=args.star_store,
        faint_star_store=args.faint_star_store,
        faint_star_limit=args.faint_star_limit,
        stars_csv=args.stars,
        dsos_path=args.dsos,
        constellations_dir=args.constellations,
        outlines_dir=args.outlines,
        observing_lists_dir=args.observing_lists,
        observing_config_path=args.observing_config,
        double_stars_path=args.double_stars,
        double_star_match_tolerance_arcsec=args.double_star_match_tolerance_arcsec,
        magnitude_limit=args.magnitude_limit,
    )
    return (
        context.atlas,
        context.style,
        context.definition,
        context.page,
        context.scene,
        context.transform,
    )


_DEBUG_FLAGS = (
    "label_boxes",
    "exclusion_zones",
    "element_ids",
    "candidate_points",
    "line_knockouts",
)


def _parse_debug(value: str) -> DebugOptions | None:
    flags = {flag.strip() for flag in value.split(",") if flag.strip()}
    if not flags:
        return None
    unknown = flags - set(_DEBUG_FLAGS)
    if unknown:
        raise ConfigError(f"unknown debug flag(s): {', '.join(sorted(unknown))}")
    return DebugOptions(**{flag: flag in flags for flag in _DEBUG_FLAGS})


def _star_names(args: argparse.Namespace) -> dict:
    """Load the bright-star label lookup for a command, if configured."""
    if getattr(args, "no_star_names", False):
        return {}
    directory = getattr(args, "star_names", None)
    return load_star_names(directory if directory is not None else STAR_NAMES_FIXTURE_DIR)


def _locator_inset(
    args: argparse.Namespace,
    atlas: AtlasConfig,
    style: StyleConfig,
    definition: ChartDefinition,
) -> LocatorInset | None:
    """Build the per-chart locator inset when the style enables it."""
    if not style.locator.enabled:
        return None
    directory = getattr(args, "constellations", None)
    if directory is False:
        return None
    constellations = load_constellations(
        directory if directory is not None else _DEFAULT_CONSTELLATIONS
    )
    overview = build_overview(
        chart_definitions(atlas),
        hemisphere=hemisphere_for(definition.center_dec_deg),
        constellations=constellations,
        edition=atlas.resolved_edition(),
        equatorial_extension_deg=style.overview.equatorial_extension_deg,
    )
    return LocatorInset(
        overview=overview,
        current_chart_id=definition.id,
        neighbour_ids=frozenset(neighbour for _, neighbour in definition.neighbours),
    )


def _command_chart_render(args: argparse.Namespace) -> int:
    atlas, style, definition, _page, scene, transform = _chart_context(args)
    star_names = _star_names(args)
    variable_star_hips = frozenset(
        hip for hip, entry in star_names.items() if entry.variable_marker
    )

    has_labels = bool(args.labels or args.optimize or args.overrides)
    if has_labels:
        labels = build_labels(scene, transform, style, star_names)
        labels = _select_labels(args, definition, labels, scene, transform, style)
        labels = _apply_chart_overrides(args, definition, labels)
    else:
        labels = ()
    presentation = presentation_from_edition(definition, atlas.resolved_edition(), scene=scene)
    furniture = furniture_obstacles(transform, definition, style, presentation)
    result: OptimizationResult | None = None
    if args.optimize:
        result = optimize_labels(
            labels,
            scene,
            transform,
            style,
            furniture=furniture,
            detailed_diagnostics=args.placement_diagnostics,
        )
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
        presentation=presentation,
        locator=_locator_inset(args, atlas, style, definition),
        variable_star_hips=variable_star_hips,
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
    labels = build_labels(scene, transform, style, _star_names(args))
    labels = _select_labels(args, definition, labels, scene, transform, style)
    labels = _apply_chart_overrides(args, definition, labels)
    presentation = presentation_from_edition(definition, atlas.resolved_edition(), scene=scene)
    furniture = furniture_obstacles(transform, definition, style, presentation)
    if args.optimize:
        result = optimize_labels(labels, scene, transform, style, furniture=furniture)
        labels = result.labels
    validation = validate_layout(labels, scene, transform, style, furniture=furniture)

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


def _command_review_editor(args: argparse.Namespace) -> int:
    from nightsky_atlas.review.editor import EditorSession, serve_editor

    if not args.star_store.is_file():
        raise SystemExit(
            f"star store not found: {args.star_store}; build it with `nightsky data import-stars` "
            "or pass --star-store PATH"
        )
    atlas = load_atlas_config(args.atlas)
    chart_id = args.chart
    if chart_id not in {item.id for item in atlas.detail_charts}:
        from nightsky_atlas.atlas.tiling import chart_definitions
        from nightsky_atlas.chart.presentation import presentation_from_edition

        matched = next(
            (
                item
                for item in chart_definitions(atlas)
                if chart_id
                in {
                    item.id,
                    presentation_from_edition(item, atlas.resolved_edition()).chart_code,
                }
            ),
            None,
        )
        if matched is not None:
            chart_id = matched.id
    output = args.outdir or (Path("build/label-editor") / args.edition / chart_id)
    session = EditorSession(
        atlas_path=args.atlas,
        style_path=args.style,
        chart_id=chart_id,
        outdir=output,
        star_store=args.star_store,
        dsos_path=args.dsos,
        overrides_path=args.overrides,
        ai_config_path=args.ai_config,
        png_dpi=args.png_dpi,
    )
    serve_editor(session, port=args.port)
    return 0


def _run_one_step_review(args: argparse.Namespace, request: ReviewRequest, outdir: Path) -> None:
    timeout_s = 60.0
    max_retries = 3
    if args.ai_config.exists():
        config = load_ai_config(args.ai_config)
        timeout_s = config.timeout_s
        max_retries = config.max_retries
    reviewer = OpenRouterReviewer(model=args.model, timeout_s=timeout_s, max_retries=max_retries)
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
            "star_system_count": scene.star_system_count,
            "star_systems": [scene_system.system.to_dict() for scene_system in scene.star_systems],
            "deep_sky_objects": [
                {"id": scene_dso.dso.id, **scene_dso.metadata.to_dict()}
                for scene_dso in scene.deep_sky_objects
                if scene_dso.metadata is not None
            ],
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
            "label_diagnostics": result.label_diagnostics,
            "metrics": result.metrics,
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _command_chart_validate(args: argparse.Namespace) -> int:
    atlas, style, definition, _page, scene, transform = _chart_context(args)
    labels = build_labels(scene, transform, style, _star_names(args))
    labels = _select_labels(args, definition, labels, scene, transform, style)
    labels = _apply_chart_overrides(args, definition, labels)
    presentation = presentation_from_edition(definition, atlas.resolved_edition(), scene=scene)
    furniture = furniture_obstacles(transform, definition, style, presentation)
    if args.optimize:
        result = optimize_labels(labels, scene, transform, style, furniture=furniture)
        labels = result.labels
        print(
            f"optimized: cost {result.cost_before:.1f} -> {result.cost_after:.1f}, "
            f"{result.placed_count} placed, {result.hidden_count} hidden"
        )
    result_validation = validate_layout(labels, scene, transform, style, furniture=furniture)

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
    if args.edition_comparison:
        styles = {
            edition: load_style_config(Path("styles") / f"{edition}.yaml")
            for edition in ("pocket", "standard", "deep")
        }
        pdf_path = outdir / "edition-star-curves.pdf"
        render_edition_magnitude_scale(
            page,
            styles,
            pdf_path=pdf_path,
            png_path=outdir / "edition-star-curves.png",
            png_dpi=args.png_dpi,
        )
    else:
        pdf_path = outdir / "magnitude-scale.pdf"
        render_magnitude_scale(
            page,
            style,
            pdf_path=pdf_path,
            png_path=outdir / "magnitude-scale.png",
            png_dpi=args.png_dpi,
        )
    print(f"magnitude scale -> {pdf_path}")
    return 0


def _command_why_object(args: argparse.Namespace) -> int:
    from nightsky_atlas.atlas.observing_config import (
        load_observing_lists_config,
        resolve_edition_hierarchy,
    )
    from nightsky_atlas.catalog.common_names import curated_common_name
    from nightsky_atlas.catalog.observing_lists import (
        build_membership_index,
        load_observing_lists,
    )
    from nightsky_atlas.layout.dso_labels import primary_designation

    objects = load_dso_catalog(args.catalogue)
    obj = find_object(
        objects,
        args.designation,
        observing_lists_dir=args.observing_lists,
    )
    if obj is None:
        print(f"no catalogue object found for {args.designation!r}")
        return 1
    index = build_membership_index(load_observing_lists(args.observing_lists), objects)
    config = load_observing_lists_config(args.observing_config)
    sources = sorted(
        {obj.provenance.catalogue} | {record.catalogue_id for record in obj.catalogue_records}
    )
    editions = (
        (args.edition,) if args.edition else ("pocket", "standard", "deep", "eyepiece", "reference")
    )
    visibility_by_edition = {
        edition: load_atlas_config(Path("atlas") / f"{edition}.yaml").visibility.to_limits()
        for edition in ("pocket", "standard", "deep", "eyepiece")
    }
    if "pocket" in editions:
        visibility_by_edition["pocket"] = load_atlas_config(args.atlas).visibility.to_limits()
    policies = {
        edition: resolve_edition_hierarchy(
            config, edition, visibility_by_edition=visibility_by_edition
        )
        for edition in editions
    }
    output = {
        "canonical_designation": obj.id,
        "display_designation": primary_designation(obj),
        "curated_common_name": (
            curated.name if (curated := curated_common_name(obj)) is not None else None
        ),
        "aliases": sorted(obj.cross_ids),
        "object_type": obj.object_type.value,
        "semantic_subtype": obj.semantic_subtype,
        "source_catalogues": sources,
        "catalogue_records": [record.to_dict() for record in obj.catalogue_records],
        "metadata": {
            "ra_deg": obj.ra_deg,
            "dec_deg": obj.dec_deg,
            "magnitude": obj.magnitude,
            "magnitude_band": obj.magnitude_band,
            "surface_brightness_mag_arcsec2": obj.surface_brightness_mag_arcsec2(),
            "major_axis_arcmin": obj.major_axis_arcmin,
            "minor_axis_arcmin": obj.minor_axis_arcmin,
            "hubble_type": obj.hubble_type,
            "member_count": obj.member_count,
            "member_designations": list(obj.member_designations),
        },
        "selection": {
            edition: explain_selection(
                obj,
                edition=edition,
                policy=policies[edition],
                index=index,
            )
            for edition in editions
        },
    }
    print(json.dumps(output, indent=2, sort_keys=True, allow_nan=False), flush=True)
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
        f"overlap={report.min_overlap}..{report.max_overlap}"
    )
    print(f"overlap histogram: {dict(report.overlap_histogram)}")
    for ra, dec in report.gaps[:10]:
        print(f"  gap ra={ra:.1f} dec={dec:.1f}")
    return 0 if report.covers_all else 1


def _command_atlas_report(args: argparse.Namespace) -> int:
    atlas = load_atlas_config(args.atlas)
    manifest_path = (
        args.manifest if args.manifest is not None else args.outdir / atlas.id / "manifest.json"
    )
    pages = None
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        pages = manifest.get("pages", [])
    report = build_draft_report(
        atlas_path=args.atlas,
        pages=pages,
        coverage_step_deg=args.coverage_step,
    )
    out = args.out if args.out is not None else args.outdir / atlas.id / "draft-report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(render_text_summary(report))
    print(f"-> {out}")
    return 0


def _command_atlas_validate(args: argparse.Namespace) -> int:
    atlas = load_atlas_config(args.atlas)
    outroot = args.outdir / atlas.id
    issues = validate_atlas_output(outroot, publication=args.publication)
    if issues:
        for issue in issues:
            print(f"issue: {issue}")
        return 1
    print(f"{atlas.id}: atlas output valid -> {outroot}")
    return 0


def _command_atlas_build(args: argparse.Namespace) -> int:
    chart_ids = None
    if args.charts:
        chart_ids = tuple(part.strip() for part in args.charts.split(",") if part.strip())
    progress = Progress(verbose=args.verbose, enabled=not args.quiet)
    result = build_atlas(
        atlas_path=args.atlas,
        style_path=args.style,
        outdir=args.outdir,
        star_store=args.star_store,
        faint_star_store=args.faint_star_store,
        faint_star_limit=args.faint_star_limit,
        stars_csv=args.stars,
        dsos_path=args.dsos,
        constellations_dir=args.constellations,
        outlines_dir=args.outlines,
        star_names_dir=args.star_names,
        observing_lists_dir=args.observing_lists,
        observing_config_path=args.observing_config,
        double_stars_path=args.double_stars,
        overrides_path=args.overrides,
        chart_ids=chart_ids,
        limit=args.limit,
        optimize=not args.no_optimize,
        render_png=not args.no_png,
        png_dpi=args.png_dpi,
        jobs=args.jobs,
        write_front_matter=not args.no_front_matter,
        write_overviews=not args.no_overviews,
        write_draft_report=not args.no_draft_report,
        publication=args.publication,
        progress=progress,
    )
    print(
        f"{result.atlas_id}: {len(result.pages)} charts, "
        f"{result.total_hard_issues} hard issues -> {result.combined_pdf}"
    )
    print(f"manifest -> {result.manifest_path}")
    return 0 if result.total_hard_issues == 0 else 1


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface and return a process exit code."""
    load_env_file()
    parser = build_parser()
    argument_list = tuple(sys.argv[1:] if argv is None else argv)
    args = parser.parse_args(argument_list)
    _apply_edition_preset(args, argument_list)
    _apply_disabled_inputs(args)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 0
    try:
        return handler(args)
    except (ConfigError, StarCatalogueError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
