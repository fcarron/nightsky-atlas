"""Command-line entry point for NightSky Atlas."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import replace
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
from nightsky_atlas.catalog.dso_store import load_dso_catalog, write_dso_catalog
from nightsky_atlas.catalog.faint_density import (
    build_faint_density_report,
    build_faint_query_performance_report,
)
from nightsky_atlas.catalog.faint_stars import (
    FaintStarStore,
    download_ucac4_zones,
    import_ucac4_faint,
)
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
from nightsky_atlas.catalog.inventory import build_catalogue_inventory
from nightsky_atlas.catalog.manifest import file_sha256, write_manifest
from nightsky_atlas.catalog.merge import merge_stars
from nightsky_atlas.catalog.openngc import (
    CATALOGUE as OPENNGC_CATALOGUE,
)
from nightsky_atlas.catalog.openngc import (
    download_openngc,
    iter_openngc_objects,
)
from nightsky_atlas.catalog.sample import StarCatalogueError
from nightsky_atlas.catalog.selection_analysis import (
    build_selection_report,
    explain_selection,
    find_object,
    summarize_selection_report,
    write_selection_csv,
)
from nightsky_atlas.catalog.star_names import (
    DEFAULT_FIXTURE_DIR as STAR_NAMES_FIXTURE_DIR,
)
from nightsky_atlas.catalog.star_names import (
    load_star_names,
)
from nightsky_atlas.catalog.stellarium_figures import (
    REVISION as STELLARIUM_FIGURES_REVISION,
)
from nightsky_atlas.catalog.stellarium_figures import (
    SHA256 as STELLARIUM_FIGURES_SHA256,
)
from nightsky_atlas.catalog.stellarium_figures import (
    SOURCE_URL as STELLARIUM_FIGURES_URL,
)
from nightsky_atlas.catalog.stellarium_figures import (
    fetch_stellarium_figures,
    import_stellarium_figures,
)
from nightsky_atlas.catalog.store import StarStore, build_star_store
from nightsky_atlas.catalog.systems import write_system_catalog
from nightsky_atlas.catalog.tycho import (
    CATALOGUE,
    CDS_BASE_URL,
    VERSION,
    download_tycho2,
    iter_tycho2_stars,
    raw_part_paths,
)
from nightsky_atlas.catalog.tycho_density import build_report as build_tycho_density_report
from nightsky_atlas.catalog.tycho_density import write_csv as write_tycho_density_csv
from nightsky_atlas.catalog.tycho_density import write_json as write_tycho_density_json
from nightsky_atlas.catalog.vizier_dso import (
    VIZIER_ACKNOWLEDGEMENT,
    VIZIER_CATALOGUES,
    download_vizier_catalogues,
    import_vizier_catalogues,
    iter_vizier_objects,
)
from nightsky_atlas.catalog.wds import (
    CATALOGUE as WDS_CATALOGUE,
)
from nightsky_atlas.catalog.wds import (
    EDITION as WDS_EDITION,
)
from nightsky_atlas.catalog.wds import (
    download_wds,
    iter_wds_systems,
)
from nightsky_atlas.catalog.wds import (
    raw_path as wds_raw_path,
)
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.chart.page import PageTransform
from nightsky_atlas.chart.presentation import presentation_from_edition
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
_DEFAULT_RAW = Path("data/raw/tycho2")
_DEFAULT_STORE = Path("data/processed/stars/tycho2.sqlite")
_DEFAULT_MANIFEST = Path("data/processed/stars/tycho2.manifest.json")
_DEFAULT_HIP_RAW = Path("data/raw/hipparcos")
_DEFAULT_OPENNGC_RAW = Path("data/raw/openngc")
_DEFAULT_DSO_OUT = Path("data/processed/dso/openngc.json")
_DEFAULT_DSO_MANIFEST = Path("data/processed/dso/openngc.manifest.json")
_DEFAULT_VIZIER_RAW = Path("data/raw/vizier_dso")
_DEFAULT_COMBINED_DSO_OUT = Path("data/processed/dso/catalogue.json")
_DEFAULT_COMBINED_DSO_MANIFEST = Path("data/processed/dso/catalogue.manifest.json")
_DEFAULT_WDS_RAW = Path("data/raw/wds")
_DEFAULT_WDS_OUT = Path("data/processed/double_stars/wds.json")
_DEFAULT_WDS_MANIFEST = Path("data/processed/double_stars/wds.manifest.json")
_DEFAULT_CONSTELLATIONS = Path("data/fixtures/constellations")
_DEFAULT_STELLARIUM_RAW = Path("data/raw/stellarium/western_SnT/index.json")
_DEFAULT_OUTLINES = Path("data/fixtures/outlines")
_DEFAULT_STAR_NAMES = STAR_NAMES_FIXTURE_DIR
_DEFAULT_OBSERVING_LISTS = Path("data/fixtures/observing_lists")
_DEFAULT_OBSERVING_CONFIG = Path("config/observing_lists.yaml")
_DEFAULT_CASES = Path("benchmarks/ai_review/cases.yaml")
_DEFAULT_BENCH_OUT = Path("benchmarks/ai_review/results")
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
    _add_data_commands(subparsers)
    _add_benchmark_commands(subparsers)
    _add_atlas_commands(subparsers)
    _add_research_commands(subparsers)
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


def _add_scene_arguments(parser: argparse.ArgumentParser) -> None:
    _add_edition_argument(parser)
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
    parser.add_argument(
        "--double-star-match-tolerance-arcsec",
        type=float,
        default=2.0,
        help="positional tolerance when linking WDS systems to stars",
    )
    parser.add_argument("--outdir", type=Path, default=_DEFAULT_OUTDIR)
    parser.add_argument("--png-dpi", type=float, default=300.0)
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


def _add_data_commands(subparsers: argparse._SubParsersAction) -> None:
    data = subparsers.add_parser("data", help="fetch and import catalogue data")
    data_subparsers = data.add_subparsers(dest="data_command")

    figure_fetch = data_subparsers.add_parser(
        "fetch-stellarium-figures", help="download pinned Western (Sky & Telescope) figures"
    )
    figure_fetch.add_argument("--dest", type=Path, default=_DEFAULT_STELLARIUM_RAW)
    figure_fetch.set_defaults(handler=_command_fetch_stellarium_figures)

    figure_import = data_subparsers.add_parser(
        "import-stellarium-figures", help="normalize pinned HIP stick figures and line weights"
    )
    figure_import.add_argument("--source", type=Path, default=_DEFAULT_STELLARIUM_RAW)
    figure_import.add_argument("--store", type=Path, default=_DEFAULT_STORE)
    figure_import.add_argument(
        "--hipparcos-raw", type=Path, default=_DEFAULT_HIP_RAW / "hip_main.dat"
    )
    figure_import.add_argument("--dest", type=Path, default=_DEFAULT_CONSTELLATIONS)
    figure_import.set_defaults(handler=_command_import_stellarium_figures)

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

    density = data_subparsers.add_parser(
        "tycho-density-report", help="measure Tycho-2 stellar density by magnitude and sky region"
    )
    density.add_argument("--store", type=Path, default=_DEFAULT_STORE)
    density.add_argument("--json", type=Path, default=None, help="write the full report as JSON")
    density.add_argument(
        "--csv", type=Path, default=None, help="write count and density tables as CSV"
    )
    density.set_defaults(handler=_command_tycho_density_report)

    labels = data_subparsers.add_parser(
        "star-label-report", help="count eligible stellar label types for an edition"
    )
    _add_edition_argument(labels)
    labels.add_argument("--style", type=Path, default=_DEFAULT_STYLE)
    labels.add_argument("--store", type=Path, default=_DEFAULT_STORE)
    labels.add_argument("--star-names", type=Path, default=_DEFAULT_STAR_NAMES)
    labels.set_defaults(handler=_command_star_label_report)

    reindex = data_subparsers.add_parser(
        "reindex-stars", help="rebuild star-store indexes in place (safe to re-run)"
    )
    reindex.add_argument("--store", type=Path, default=_DEFAULT_STORE)
    reindex.set_defaults(handler=_command_reindex_stars)

    ucac_fetch = data_subparsers.add_parser(
        "fetch-ucac4", help="download UCAC4 binary zones from CDS (all-sky is several GB)"
    )
    ucac_fetch.add_argument("--dest", type=Path, default=Path("data/raw/ucac4/u4b"))
    ucac_fetch.add_argument("--zones", default="1-900", help="zones/ranges, e.g. 1-20,450,900")
    ucac_fetch.set_defaults(handler=_command_fetch_ucac4)

    ucac_import = data_subparsers.add_parser(
        "import-ucac4-faint", help="build the separate UCAC4 faint-star store"
    )
    ucac_import.add_argument("--raw", type=Path, default=Path("data/raw/ucac4/u4b"))
    ucac_import.add_argument("--primary-star-store", type=Path, default=_DEFAULT_STORE)
    ucac_import.add_argument(
        "--out", type=Path, default=Path("data/processed/stars/faint_stars.sqlite")
    )
    ucac_import.add_argument("--manifest", type=Path, default=None)
    ucac_import.add_argument("--limit", type=float, default=14.0)
    ucac_import.set_defaults(handler=_command_import_ucac4_faint)

    faint_count = data_subparsers.add_parser(
        "faint-star-count", help="report faint-star counts and SQLite size"
    )
    faint_count.add_argument(
        "--store", type=Path, default=Path("data/processed/stars/faint_stars.sqlite")
    )
    faint_count.set_defaults(handler=_command_faint_star_count)

    faint_density = data_subparsers.add_parser(
        "faint-star-density-report",
        help="compare primary plus faint-star paper density by sky region",
    )
    faint_density.add_argument(
        "--store", type=Path, default=Path("data/processed/stars/faint_stars.sqlite")
    )
    faint_density.add_argument("--primary-star-store", type=Path, default=_DEFAULT_STORE)
    faint_density.set_defaults(handler=_command_faint_star_density_report)

    faint_perf = data_subparsers.add_parser(
        "faint-star-performance-report",
        help="measure faint-star chart-query time and returned-memory by region",
    )
    faint_perf.add_argument(
        "--store", type=Path, default=Path("data/processed/stars/faint_stars.sqlite")
    )
    faint_perf.set_defaults(handler=_command_faint_star_performance_report)

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

    vizier_fetch = data_subparsers.add_parser(
        "fetch-vizier-dsos",
        help="download selected VizieR DSO catalogue tables for offline import",
    )
    vizier_fetch.add_argument("--dest", type=Path, default=_DEFAULT_VIZIER_RAW)
    vizier_fetch.add_argument(
        "--catalogues",
        nargs="+",
        choices=[item.catalogue_id for item in VIZIER_CATALOGUES],
        help="catalogue IDs to fetch (default: all configured catalogues)",
    )
    vizier_fetch.set_defaults(handler=_command_fetch_vizier_dsos)

    vizier_import = data_subparsers.add_parser(
        "import-vizier-dsos",
        help="merge cached VizieR catalogues into the canonical DSO catalogue",
    )
    vizier_import.add_argument("--raw", type=Path, default=_DEFAULT_VIZIER_RAW)
    vizier_import.add_argument("--openngc", type=Path, default=_DEFAULT_DSO_OUT)
    vizier_import.add_argument("--out", type=Path, default=_DEFAULT_COMBINED_DSO_OUT)
    vizier_import.add_argument("--manifest", type=Path, default=_DEFAULT_COMBINED_DSO_MANIFEST)
    vizier_import.add_argument(
        "--report", type=Path, default=Path("data/processed/dso/vizier-crossmatch.json")
    )
    vizier_import.set_defaults(handler=_command_import_vizier_dsos)

    dso_info = data_subparsers.add_parser(
        "dso-info",
        aliases=["catalog-object"],
        help="inspect a canonical DSO, aliases and source decisions",
    )
    dso_info.add_argument("--catalogue", type=Path, default=_DEFAULT_COMBINED_DSO_OUT)
    dso_info.add_argument("designation", help="canonical designation or known alias")
    dso_info.set_defaults(handler=_command_dso_info)

    catalogue_report = data_subparsers.add_parser(
        "catalogue-report", help="report normalized physical-object and edition catalogue counts"
    )
    catalogue_report.add_argument("--catalogue", type=Path, default=_DEFAULT_COMBINED_DSO_OUT)
    catalogue_report.add_argument("--manifest", type=Path, default=_DEFAULT_COMBINED_DSO_MANIFEST)
    catalogue_report.add_argument("--openngc", type=Path, default=_DEFAULT_DSO_OUT)
    catalogue_report.add_argument("--openngc-manifest", type=Path, default=_DEFAULT_DSO_MANIFEST)
    catalogue_report.add_argument("--openngc-raw", type=Path, default=_DEFAULT_OPENNGC_RAW)
    catalogue_report.add_argument("--vizier-raw", type=Path, default=_DEFAULT_VIZIER_RAW)
    catalogue_report.add_argument(
        "--crossmatch-report", type=Path, default=Path("data/processed/dso/vizier-crossmatch.json")
    )
    catalogue_report.add_argument(
        "--observing-config", type=Path, default=_DEFAULT_OBSERVING_CONFIG
    )
    catalogue_report.add_argument("--observing-lists", type=Path, default=_DEFAULT_OBSERVING_LISTS)
    catalogue_report.add_argument(
        "--out", type=Path, default=Path("data/processed/dso/catalogue-inventory.json")
    )
    catalogue_report.set_defaults(handler=_command_catalogue_report)

    selection_report = data_subparsers.add_parser(
        "selection-report", help="audit current DSO selection by edition, type and source"
    )
    selection_report.add_argument("--catalogue", type=Path, default=_DEFAULT_COMBINED_DSO_OUT)
    selection_report.add_argument("--manifest", type=Path, default=_DEFAULT_COMBINED_DSO_MANIFEST)
    selection_report.add_argument("--openngc", type=Path, default=_DEFAULT_DSO_OUT)
    selection_report.add_argument("--openngc-manifest", type=Path, default=_DEFAULT_DSO_MANIFEST)
    selection_report.add_argument("--openngc-raw", type=Path, default=_DEFAULT_OPENNGC_RAW)
    selection_report.add_argument("--vizier-raw", type=Path, default=_DEFAULT_VIZIER_RAW)
    selection_report.add_argument(
        "--crossmatch-report", type=Path, default=Path("data/processed/dso/vizier-crossmatch.json")
    )
    selection_report.add_argument(
        "--observing-config", type=Path, default=_DEFAULT_OBSERVING_CONFIG
    )
    selection_report.add_argument("--observing-lists", type=Path, default=_DEFAULT_OBSERVING_LISTS)
    selection_report.add_argument("--json", type=Path, default=None, help="write full JSON report")
    selection_report.add_argument("--csv", type=Path, default=None, help="write per-object CSV")
    selection_report.set_defaults(handler=_command_selection_report)

    pocket_report = data_subparsers.add_parser(
        "pocket-selection-report",
        help="audit Pocket mandatory-list membership and 100 mm fill selection",
    )
    pocket_report.add_argument("--catalogue", type=Path, default=_DEFAULT_COMBINED_DSO_OUT)
    pocket_report.add_argument("--observing-config", type=Path, default=_DEFAULT_OBSERVING_CONFIG)
    pocket_report.add_argument("--observing-lists", type=Path, default=_DEFAULT_OBSERVING_LISTS)
    pocket_report.add_argument("--atlas", type=Path, default=Path("atlas/pocket.yaml"))
    pocket_report.add_argument("--json", type=Path, default=None, help="write full JSON report")
    pocket_report.set_defaults(handler=_command_pocket_selection_report)

    wds_fetch = data_subparsers.add_parser(
        "fetch-wds",
        help="download the raw Washington Double Star Catalog (network access)",
    )
    wds_fetch.add_argument("--dest", type=Path, default=_DEFAULT_WDS_RAW)
    wds_fetch.set_defaults(handler=_command_fetch_wds)

    wds_import = data_subparsers.add_parser(
        "import-wds",
        help="normalize the raw WDS into a processed double-star overlay",
    )
    wds_import.add_argument("--raw", type=Path, default=_DEFAULT_WDS_RAW)
    wds_import.add_argument("--out", type=Path, default=_DEFAULT_WDS_OUT)
    wds_import.add_argument("--manifest", type=Path, default=_DEFAULT_WDS_MANIFEST)
    wds_import.set_defaults(handler=_command_import_wds)


def _add_benchmark_commands(subparsers: argparse._SubParsersAction) -> None:
    benchmark = subparsers.add_parser("benchmark", help="run AI review benchmarks")
    benchmark_subparsers = benchmark.add_subparsers(dest="benchmark_command")

    run = benchmark_subparsers.add_parser(
        "ai-review", help="run benchmark cases against a reviewer"
    )
    _add_edition_argument(run)
    run.add_argument("--cases", type=Path, default=_DEFAULT_CASES)
    run.add_argument("--atlas", type=Path, default=_DEFAULT_ATLAS)
    run.add_argument("--style", type=Path, default=_DEFAULT_STYLE)
    run.add_argument("--star-store", type=Path, default=_DEFAULT_STORE)
    run.add_argument("--stars", type=Path, default=_DEFAULT_STARS)
    run.add_argument("--dsos", type=Path, default=None)
    run.add_argument("--outdir", type=Path, default=_DEFAULT_BENCH_OUT)
    run.add_argument("--model", default=None, help="OpenRouter model to benchmark")
    run.add_argument("--ai-config", type=Path, default=Path("ai.yaml"))
    run.add_argument("--recorded", type=Path, default=None, help="replay recorded review results")
    run.set_defaults(handler=_command_benchmark_ai_review)


def _add_research_commands(subparsers: argparse._SubParsersAction) -> None:
    research = subparsers.add_parser(
        "research", help="audit local external observing lists without changing atlas policy"
    )
    research_subparsers = research.add_subparsers(dest="research_command")
    coverage = research_subparsers.add_parser(
        "observing-list-coverage", help="measure database and edition coverage for a local list"
    )
    coverage.add_argument(
        "--source",
        choices=("astroplanner", "astronomical-league"),
        required=True,
        help="source adapter for user-supplied files",
    )
    coverage.add_argument(
        "--input",
        type=Path,
        action="append",
        required=True,
        help="local file or directory (repeat for multiple inputs)",
    )
    coverage.add_argument("--list-name", default=None, help="override the report list name")
    coverage.add_argument("--catalogue", type=Path, default=_DEFAULT_COMBINED_DSO_OUT)
    coverage.add_argument("--observing-config", type=Path, default=_DEFAULT_OBSERVING_CONFIG)
    coverage.add_argument("--observing-lists", type=Path, default=_DEFAULT_OBSERVING_LISTS)
    coverage.add_argument("--pocket-atlas", type=Path, default=Path("atlas/pocket.yaml"))
    coverage.add_argument("--overrides", type=Path, default=None, help="local YAML match overrides")
    coverage.add_argument(
        "--coordinate-tolerance-arcmin",
        type=float,
        default=2.0,
        help="maximum separation for coordinate fallback matching",
    )
    coverage.add_argument("--json", type=Path, default=None, help="write deterministic JSON report")
    coverage.add_argument("--csv", type=Path, default=None, help="write per-entry CSV report")
    coverage.set_defaults(handler=_command_observing_list_coverage)

    nebula_analysis = research_subparsers.add_parser(
        "nsog-nebula-analysis",
        help="analyze local NSOG nebula ratings, catalogue identity and Deep coverage",
    )
    nebula_analysis.add_argument(
        "--input",
        type=Path,
        action="append",
        required=True,
        help="local AstroPlanner NSOG plan file or directory (repeatable)",
    )
    nebula_analysis.add_argument("--list-name", default="NSOG local AstroPlanner export")
    nebula_analysis.add_argument("--catalogue", type=Path, default=_DEFAULT_COMBINED_DSO_OUT)
    nebula_analysis.add_argument("--observing-config", type=Path, default=_DEFAULT_OBSERVING_CONFIG)
    nebula_analysis.add_argument("--observing-lists", type=Path, default=_DEFAULT_OBSERVING_LISTS)
    nebula_analysis.add_argument("--pocket-atlas", type=Path, default=Path("atlas/pocket.yaml"))
    nebula_analysis.add_argument("--overrides", type=Path, default=None)
    nebula_analysis.add_argument("--coordinate-tolerance-arcmin", type=float, default=2.0)
    nebula_analysis.add_argument(
        "--markdown",
        type=Path,
        default=Path("build/research/nsog_nebula_analysis.md"),
        help="private human-readable output (default: build/research)",
    )
    nebula_analysis.add_argument(
        "--json",
        type=Path,
        default=Path("build/research/nsog_nebula_analysis.json"),
    )
    nebula_analysis.add_argument(
        "--csv",
        type=Path,
        default=Path("build/research/nsog_nebula_targets.csv"),
        help="private per-target detail; keep this generated file local",
    )
    nebula_analysis.set_defaults(handler=_command_nsog_nebula_analysis)

    compare = research_subparsers.add_parser(
        "observing-list-compare", help="compare physical-object membership across coverage reports"
    )
    compare.add_argument("reports", nargs="+", type=Path)
    compare.add_argument("--minimum-lists", type=int, default=1)
    compare.add_argument("--json", type=Path, default=None, help="write comparison report")
    compare.set_defaults(handler=_command_observing_list_compare)


def _add_atlas_commands(subparsers: argparse._SubParsersAction) -> None:
    atlas = subparsers.add_parser("atlas", help="tile and validate complete atlases")
    atlas_subparsers = atlas.add_subparsers(dest="atlas_command")
    atlas_object = atlas_subparsers.add_parser(
        "catalog-object", help="inspect a canonical DSO, aliases and source decisions"
    )
    atlas_object.add_argument("--catalogue", type=Path, default=_DEFAULT_COMBINED_DSO_OUT)
    atlas_object.add_argument("--observing-config", type=Path, default=_DEFAULT_OBSERVING_CONFIG)
    atlas_object.add_argument("--observing-lists", type=Path, default=_DEFAULT_OBSERVING_LISTS)
    atlas_object.add_argument(
        "--edition", choices=("standard", "deep", "reference"), default="deep"
    )
    atlas_object.add_argument("designation", help="canonical designation or known alias")
    atlas_object.set_defaults(handler=_command_dso_info)

    why_object = atlas_subparsers.add_parser(
        "why-object", help="explain current Standard, Deep and Reference selection for an object"
    )
    why_object.add_argument("--catalogue", type=Path, default=_DEFAULT_COMBINED_DSO_OUT)
    why_object.add_argument("--observing-config", type=Path, default=_DEFAULT_OBSERVING_CONFIG)
    why_object.add_argument("--observing-lists", type=Path, default=_DEFAULT_OBSERVING_LISTS)
    why_object.add_argument(
        "--edition", choices=("pocket", "standard", "deep", "reference"), default=None
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
    _add_edition_argument(build)
    build.add_argument("--atlas", type=Path, default=_DEFAULT_ATLAS)
    build.add_argument("--style", type=Path, default=_DEFAULT_STYLE)
    build.add_argument("--star-store", type=Path, default=_DEFAULT_STORE)
    build.add_argument(
        "--faint-star-store",
        type=Path,
        default=None,
        help="optional UCAC4 supplement, disabled by default",
    )
    build.add_argument(
        "--faint-star-limit",
        type=float,
        default=None,
        help="required faint-star cutoff when supplement is enabled",
    )
    build.add_argument("--stars", type=Path, default=_DEFAULT_STARS)
    build.add_argument("--dsos", type=Path, default=None)
    build.add_argument(
        "--constellations",
        type=Path,
        default=_DEFAULT_CONSTELLATIONS,
        help="directory of constellation geometry fixtures",
    )
    build.add_argument(
        "--no-constellations", action="store_true", help="omit constellation geometry"
    )
    build.add_argument(
        "--outlines",
        type=Path,
        default=_DEFAULT_OUTLINES,
        help="directory of schematic nebula outline fixtures",
    )
    build.add_argument("--no-outlines", action="store_true", help="omit nebula outlines")
    build.add_argument(
        "--star-names",
        type=Path,
        default=_DEFAULT_STAR_NAMES,
        help="directory of star-name fixtures for bright-star labels",
    )
    build.add_argument("--no-star-names", action="store_true", help="omit star-name labels")
    build.add_argument(
        "--observing-lists",
        type=Path,
        default=_DEFAULT_OBSERVING_LISTS,
        help="directory of observing-list fixtures for DSO selection",
    )
    build.add_argument(
        "--no-observing-lists", action="store_true", help="disable observing-list selection"
    )
    build.add_argument(
        "--observing-config",
        type=Path,
        default=_DEFAULT_OBSERVING_CONFIG,
        help="observing-list selection policy YAML",
    )
    build.add_argument(
        "--double-stars",
        type=Path,
        default=None,
        help="processed WDS double/multiple star overlay JSON (default: processed WDS if present)",
    )
    build.add_argument("--no-double-stars", action="store_true", help="omit the WDS overlay")
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
    presentation = presentation_from_edition(definition, atlas.resolved_edition())
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
    presentation = presentation_from_edition(definition, atlas.resolved_edition())
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
    presentation = presentation_from_edition(definition, atlas.resolved_edition())
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


def _command_fetch_stars(args: argparse.Namespace) -> int:
    paths = download_tycho2(args.dest, base_url=args.base_url)
    print(f"downloaded {len(paths)} parts -> {args.dest}")
    return 0


def _parse_ucac4_zones(value: str) -> list[int]:
    zones: set[int] = set()
    for part in value.split(","):
        start, separator, end = part.strip().partition("-")
        zones.update(range(int(start), int(end) + 1) if separator else (int(start),))
    if not zones or min(zones) < 1 or max(zones) > 900:
        raise ValueError("UCAC4 zones must be between 1 and 900")
    return sorted(zones)


def _command_fetch_ucac4(args: argparse.Namespace) -> int:
    paths = download_ucac4_zones(args.dest, zones=_parse_ucac4_zones(args.zones))
    print(f"downloaded/available {len(paths)} zones -> {args.dest}")
    return 0


def _command_import_ucac4_faint(args: argparse.Namespace) -> int:
    manifest = import_ucac4_faint(
        args.raw,
        args.out,
        magnitude_limit=args.limit,
        primary_store=args.primary_star_store,
        manifest_path=args.manifest,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


def _command_faint_star_count(args: argparse.Namespace) -> int:
    with FaintStarStore.open(args.store) as store:
        total = store.count()
        print(f"{total:,} faint stars in {args.store}")
        for limit, count in store.cumulative_counts((11.5, 12.0, 12.5, 13.0, 13.5, 14.0)).items():
            print(f"<= {limit:.1f}: {count:,}")
        size = args.store.stat().st_size
        print(f"SQLite size: {size:,} bytes; {size / max(1, total):.2f} bytes/star")
        print(f"table/index storage: {json.dumps(store.storage_stats(), sort_keys=True)}")
    return 0


def _command_faint_star_density_report(args: argparse.Namespace) -> int:
    report = build_faint_density_report(args.store, args.primary_star_store)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def _command_faint_star_performance_report(args: argparse.Namespace) -> int:
    report = build_faint_query_performance_report(args.store)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def _command_fetch_stellarium_figures(args: argparse.Namespace) -> int:
    path = fetch_stellarium_figures(args.dest)
    print(f"Pinned Stellarium Western (Sky & Telescope): {path}")
    return 0


def _command_import_stellarium_figures(args: argparse.Namespace) -> int:
    counts = import_stellarium_figures(
        args.source,
        args.store,
        args.dest,
        hipparcos_raw=args.hipparcos_raw if args.hipparcos_raw.exists() else None,
    )
    write_manifest(
        args.dest / "constellations.lines.manifest.json",
        {
            "source": "Stellarium Western (Sky & Telescope)",
            "url": STELLARIUM_FIGURES_URL,
            "revision": STELLARIUM_FIGURES_REVISION,
            "sha256": STELLARIUM_FIGURES_SHA256,
            "license": "CC BY-SA 2.0",
            "counts": counts,
        },
    )
    print(f"Imported Stellarium figures: {json.dumps(counts, sort_keys=True)}")
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
        "coordinate_rule": (
            "ICRS mean J2000 position; pflag=P component observed position propagated "
            "to J2000; observed position fallback"
        ),
        "raw_files": [path.name for path in parts],
        "star_count": count,
        "processed_file": args.out.name,
        "processed_sha256": file_sha256(args.out),
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


def _command_tycho_density_report(args: argparse.Namespace) -> int:
    report = build_tycho_density_report(args.store)
    print(f"Tycho-2 rows: {report['measured_catalogue_rows']:,} (from {args.store})")
    print(f"Magnitude: {report['magnitude_field']}")
    print("\nAll-sky cumulative counts / 0.5-mag increments")
    previous = 0
    for magnitude, count in report["all_sky_cumulative_counts"].items():
        print(f"  <= {magnitude:>4}: {count:>10,}  (+{count - previous:,})")
        previous = count
    print("\nGrowth intervals")
    for row in report["growth_intervals"]:
        print(f"  {row['interval']:>11}: {row['factor']:.4f}x  alpha={row['alpha']:.4f}")
    print("\nEdition paper densities (stars/cm²)")
    for edition, row in report["edition_densities"].items():
        vals = row["stars_per_cm2"]
        ratios = row["density_ratio_to_standard"]
        print(
            f"  {edition:<15} all-sky={vals['all_sky']:.3f} sparse={vals['sparse']:.3f} "
            f"Virgo={vals['virgo']:.3f} Cygnus={vals['cygnus']:.3f} "
            f"Sagittarius={vals['sagittarius']:.3f} south={vals['southern_milky_way']:.3f}; "
            f"ratios all/sparse/Cyg/Sag="
            f"{ratios['all_sky']:.2f}/{ratios['sparse']:.2f}/"
            f"{ratios['cygnus']:.2f}/{ratios['sagittarius']:.2f}x"
        )
    recommendation = report["recommendation"]
    print(f"\nRecommended official limits: {recommendation['official_defaults']}")
    print(f"Optional deeper modes: {recommendation['optional_deeper_modes']}")
    print(f"\nCompleteness: {report['completeness_note']}")
    if args.json:
        write_tycho_density_json(report, args.json)
        print(f"JSON -> {args.json}")
    if args.csv:
        write_tycho_density_csv(report, args.csv)
        print(f"CSV -> {args.csv}")
    return 0


def _command_star_label_report(args: argparse.Namespace) -> int:
    style = load_style_config(args.style)
    names = load_star_names(args.star_names)
    if not args.store.exists():
        raise FileNotFoundError(f"star store not found: {args.store}")
    connection = sqlite3.connect(f"file:{args.store.resolve()}?mode=ro", uri=True)
    counts: Counter[str] = Counter()
    tiers: Counter[str] = Counter()
    try:
        total = int(
            connection.execute(
                "SELECT COUNT(*) FROM stars WHERE magnitude <= ?",
                (style.star.faint_magnitude,),
            ).fetchone()[0]
        )
        rows = connection.execute(
            "SELECT hip_id, MIN(magnitude) FROM stars "
            "WHERE hip_id IS NOT NULL AND magnitude <= ? GROUP BY hip_id",
            (style.star.faint_magnitude,),
        )
        for hip_id, magnitude in rows:
            from nightsky_atlas.catalog.star_names import hip_number

            name = names.get(hip_number(hip_id))
            if name is None:
                continue
            variants = name.display_variants(
                style.label.star_labels,
                magnitude,
                proper_magnitude_limit=style.star.label_magnitude_limit,
            )
            if variants:
                kind = variants[0][1]
                if kind == "combined" or kind.startswith("proper_"):
                    counts["proper"] += 1
                    tier = (
                        name.proper_name_tier
                        if kind == "combined"
                        else kind.removeprefix("proper_")
                    )
                    if tier is not None:
                        tiers[tier] += 1
                else:
                    counts[kind] += 1
    finally:
        connection.close()
    counts["unlabeled"] = total - sum(counts.values())
    print(f"{style.id}: {total} rendered stars; eligible labels before layout")
    for kind in ("proper", "bayer", "flamsteed", "variable", "unlabeled"):
        print(f"  {kind}: {counts[kind]}")
    print(
        "  proper-name tiers: "
        + ", ".join(f"{tier}={tiers[tier]}" for tier in ("core", "standard", "extended"))
    )
    return 0


def _command_reindex_stars(args: argparse.Namespace) -> int:
    with StarStore.open(args.store) as store:
        store.reindex()
    print(f"reindexed star store -> {args.store}")
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
        "processed_sha256": file_sha256(args.out),
    }
    write_manifest(args.manifest, manifest)
    print(f"imported {count} deep-sky objects -> {args.out}")
    print(f"manifest -> {args.manifest}")
    return 0


def _command_fetch_vizier_dsos(args: argparse.Namespace) -> int:
    paths = download_vizier_catalogues(args.dest, catalogue_ids=args.catalogues)
    print(f"downloaded {len(paths)} VizieR catalogue tables -> {args.dest}")
    print(f"source manifest -> {args.dest / 'manifest.json'}")
    return 0


def _command_import_vizier_dsos(args: argparse.Namespace) -> int:
    if not args.openngc.exists():
        raise ConfigError(
            f"missing OpenNGC catalogue {args.openngc}; run 'nightsky data import-openngc' first"
        )
    openngc_objects = load_dso_catalog(args.openngc)
    vizier_objects = tuple(iter_vizier_objects(args.raw))
    result = import_vizier_catalogues(openngc_objects, vizier_objects)
    count = write_dso_catalog(args.out, result.objects)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(
            {
                "catalogue_counts": result.counts,
                "decisions": list(result.decisions),
                "summary": {
                    status: sum(row[status] for row in result.counts.values())
                    for status in ("raw", "new_objects", "matched_aliases", "uncertain")
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    raw_manifest_path = args.raw / "manifest.json"
    raw_manifest = (
        json.loads(raw_manifest_path.read_text(encoding="utf-8"))
        if raw_manifest_path.exists()
        else {}
    )
    source_entries = []
    raw_entries = {item["catalogue_id"]: item for item in raw_manifest.get("catalogues", [])}
    for spec in VIZIER_CATALOGUES:
        source_entries.append(
            {
                "catalogue_id": spec.catalogue_id,
                "table": spec.table,
                "name": spec.name,
                "reference": spec.reference,
                "version_note": spec.version_note,
                "license_or_usage": spec.license_or_usage,
                "source_url": spec.source_url,
                "coordinate_frame": spec.coordinate_frame,
                "row_count": result.counts[spec.catalogue_id]["raw"],
                "retrieved": raw_entries.get(spec.catalogue_id, {}).get("retrieved"),
                "raw_sha256": raw_entries.get(spec.catalogue_id, {}).get("sha256"),
                "query_filters": dict(spec.query_filters),
                "row_filter": {
                    "field": spec.row_filter_field,
                    "values": list(spec.row_filter_values),
                    "designation_pattern": spec.designation_pattern,
                    "prefix": spec.prefix_filter,
                },
                "fields_used": {
                    "designation": spec.designation_field,
                    "source_ra": spec.ra_field,
                    "source_dec": spec.dec_field,
                    "normalized_ra": spec.normalized_ra_field,
                    "normalized_dec": spec.normalized_dec_field,
                    "major_extent": spec.major_field,
                    "minor_extent": spec.minor_field,
                    "position_angle": spec.position_angle_field,
                    "area": spec.area_field_deg2,
                    "magnitude": spec.magnitude_field,
                    "member_count": spec.member_count_field,
                    "aliases": list(spec.raw_alias_fields),
                    "catalogue_metadata": list(spec.metadata_fields),
                    "member_table": spec.members_table,
                    "member_designations": spec.member_designation_field,
                    "member_component": spec.member_component_field,
                },
            }
        )
    manifest = {
        "catalogue": "NightSkyAtlas merged DSO catalogue",
        "source": "OpenNGC plus selected VizieR catalogues",
        "license": "Mixed per source; no blanket redistribution licence asserted",
        "coordinate_system": "J2000/ICRS degrees",
        "coordinate_rule": (
            "Historical VizieR table coordinates retained as raw fields; normalized positions "
            "use the VizieR computed ICRS columns included in the archived TSV snapshots."
        ),
        "acknowledgement": VIZIER_ACKNOWLEDGEMENT,
        "openngc_file": str(args.openngc),
        "openngc_sha256": file_sha256(args.openngc),
        "sources": source_entries,
        "crossmatch_report": str(args.report),
        "object_count": count,
        "processed_file": args.out.name,
        "processed_sha256": file_sha256(args.out),
    }
    write_manifest(args.manifest, manifest)
    print(f"merged {count} physical-object records -> {args.out}")
    print(f"cross-match report -> {args.report}")
    for catalogue_id, counts in result.counts.items():
        print(
            f"{catalogue_id:8} raw {counts['raw']:4}  new {counts['new_objects']:4}  "
            f"aliases {counts['matched_aliases']:4}  uncertain {counts['uncertain']:4}"
        )
    return 0


def _command_dso_info(args: argparse.Namespace) -> int:
    from nightsky_atlas.catalog.common_names import curated_common_name

    objects = load_dso_catalog(args.catalogue)
    query = args.designation.casefold().strip()
    matches = [
        obj
        for obj in objects
        if query == obj.id.casefold()
        or any(query == alias.casefold() for alias in obj.cross_ids)
        or any(query == record.designation.casefold() for record in obj.catalogue_records)
        or ((curated := curated_common_name(obj)) is not None and query == curated.name.casefold())
    ]
    if getattr(args, "observing_config", None) and getattr(args, "observing_lists", None):
        from nightsky_atlas.atlas.observing_config import (
            load_observing_lists_config,
            resolve_edition,
        )
        from nightsky_atlas.catalog.observing_lists import (
            build_membership_index,
            load_observing_lists,
        )
        from nightsky_atlas.catalog.selection import select_dso

        config = load_observing_lists_config(args.observing_config)
        index = build_membership_index(load_observing_lists(args.observing_lists), objects)
        policy = resolve_edition(config, getattr(args, "edition", "deep"))
        payload = []
        for obj in matches:
            selected = select_dso(obj, index=index, policy=policy)
            item = obj.to_dict()
            item["curated_common_name"] = (
                curated.name if (curated := curated_common_name(obj)) is not None else None
            )
            item["edition_eligibility"] = {
                "edition": getattr(args, "edition", "deep"),
                "visible": selected.visible,
                "forced": selected.forced,
                "reasons": list(selected.visibility_reasons),
            }
            payload.append(item)
    else:
        payload = [
            {
                **obj.to_dict(),
                "curated_common_name": (
                    curated.name if (curated := curated_common_name(obj)) is not None else None
                ),
            }
            for obj in matches
        ]
    print(json.dumps(payload, indent=2, sort_keys=True), flush=True)
    return 0 if matches else 1


def _command_catalogue_report(args: argparse.Namespace) -> int:
    report = build_catalogue_inventory(
        catalogue_path=args.catalogue,
        catalogue_manifest_path=args.manifest,
        openngc_path=args.openngc,
        openngc_manifest_path=args.openngc_manifest,
        openngc_raw_dir=args.openngc_raw,
        vizier_raw_dir=args.vizier_raw,
        crossmatch_report_path=args.crossmatch_report,
        observing_config_path=args.observing_config,
        observing_lists_dir=args.observing_lists,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "catalogue       raw  parsed  new physical  aliases  uncertain  unmatched  rejected  "
        "Standard  Deep  Reference"
    )
    for row in report["source_rows"]:
        eligible = row["eligible"]
        print(
            f"{row['catalogue']:<14} {row['raw_rows']:>5} {row['parsed_rows']:>7}"
            f" {row['new_physical_objects']:>13} {row['matched_aliases']:>8}"
            f" {row['uncertain_matches']:>10} {row['unmatched_aliases']:>9}"
            f" {row['rejected_or_invalid']:>9}"
            f" {eligible['standard']:>9} {eligible['deep']:>5} {eligible['reference']:>10}"
        )
    print(f"physical objects: {report['physical_object_count']}")
    print(f"unique deep-sky objects: {report['physical_dso_count']}")
    print(f"unique eligible: {report['unique_eligible_by_edition']}")
    print(f"types: {report['physical_objects_by_type']}")
    print(f"report -> {args.out}")
    return 0


def _command_selection_report(args: argparse.Namespace) -> int:
    report = build_selection_report(
        catalogue_path=args.catalogue,
        catalogue_manifest_path=args.manifest,
        openngc_path=args.openngc,
        openngc_manifest_path=args.openngc_manifest,
        openngc_raw_dir=args.openngc_raw,
        vizier_raw_dir=args.vizier_raw,
        crossmatch_report_path=args.crossmatch_report,
        observing_config_path=args.observing_config,
        observing_lists_dir=args.observing_lists,
    )
    print(summarize_selection_report(report))
    print("\nmetadata availability (available / type total):")
    for type_name, type_report in report["metadata_availability"].items():
        fields = ", ".join(
            f"{name} {values['available']}/{type_report['total']}"
            for name, values in type_report["fields"].items()
        )
        print(f"  {type_name}: {fields}")
    visibility = report["numeric_distributions"]["galaxy_visibility"]
    print(f"\ngalaxy visibility classes: {visibility['classes']}")
    print(f"galaxy magnitude bins: {visibility['magnitude_bins']}")
    print(f"galaxy score distributions by aperture: {visibility['score_by_aperture']}")
    print("numeric distributions (count, min, median, max; sizes in arcmin):")
    for type_name, values in report["numeric_distributions"].items():
        if type_name == "galaxy_visibility":
            continue
        magnitude = values["magnitude"]
        size = values["major_axis_arcmin"]
        print(
            f"  {type_name}: mag n={magnitude['count']} "
            f"{magnitude['min']}/{magnitude['q1']}/{magnitude['median']}/"
            f"{magnitude['q3']}/{magnitude['max']}; "
            f"size n={size['count']} "
            f"{size['min']}/{size['q1']}/{size['median']}/{size['q3']}/{size['max']} "
            f"bins={values['major_axis_bins_arcmin']}"
        )
    for warning in report["hierarchy_warnings"]:
        if warning.get("examples"):
            print(f"  examples for {warning['code']}: {', '.join(warning['examples'][:10])}")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        print(f"JSON -> {args.json}")
    if args.csv:
        write_selection_csv(report, args.csv)
        print(f"CSV -> {args.csv}")
    return 0


def _command_observing_list_coverage(args: argparse.Namespace) -> int:
    from nightsky_atlas.research.observing_lists.coverage import (
        build_coverage_report,
        discover_input_files,
        load_external_list,
        load_manual_overrides,
        summarize_report,
        write_csv_report,
        write_json_report,
    )

    paths = tuple(path for input_path in args.input for path in discover_input_files(input_path))
    external_list = load_external_list(
        source=args.source,
        input_path=paths,
        list_name=args.list_name,
    )
    report = build_coverage_report(
        external_list,
        catalogue_path=args.catalogue,
        observing_config_path=args.observing_config,
        observing_lists_dir=args.observing_lists,
        pocket_atlas_path=args.pocket_atlas,
        coordinate_tolerance_arcmin=args.coordinate_tolerance_arcmin,
        overrides=load_manual_overrides(args.overrides),
    )
    print(summarize_report(report))
    print("\ncoverage by object type:")
    for type_name, values in report.type_coverage.items():
        selected = ", ".join(
            f"{edition} {count}" for edition, count in values["selected_by_edition"].items()
        )
        print(
            f"  {type_name}: {values['unique_external_designations']} external designations, "
            f"{values['unique_matched_physical_targets']} matched targets; {selected}"
        )
    if report.nebula_source_analysis["matched_nebula_target_count"]:
        print("\nnebula source coverage (unique matched targets):")
        for type_name, values in report.nebula_source_analysis["by_type"].items():
            if not values["unique_matched_external_targets"]:
                continue
            counts = values["catalogue_coverage_counts"]
            counts_text = ", ".join(
                f"{name} {counts[name]}"
                for name in ("OpenNGC / NGC / IC", "Barnard", "Sharpless", "vdB", "LDN", "LBN")
                if counts[name]
            )
            print(f"  {type_name}: {counts_text or 'no mapped source-family records'}")
            if "dark" in type_name:
                print(
                    f"    without LDN: {len(values['dark_targets_without_ldn'])}; "
                    f"LDN-only: {len(values['ldn_only_targets'])}"
                )
            if "bright" in type_name or "reflection" in type_name:
                print(
                    f"    without LBN: {len(values['bright_targets_without_lbn'])}; "
                    f"LBN-only: {len(values['lbn_only_targets'])}"
                )
    if args.json:
        write_json_report(report, args.json)
        print(f"JSON -> {args.json}")
    if args.csv:
        write_csv_report(report, args.csv)
        print(f"CSV -> {args.csv}")
    if report.manual_review_queue:
        print(f"manual review queue: {len(report.manual_review_queue)} entries")
    return 0


def _command_nsog_nebula_analysis(args: argparse.Namespace) -> int:
    from nightsky_atlas.catalog.dso_store import load_dso_catalog
    from nightsky_atlas.catalog.selection_analysis import build_selection_report
    from nightsky_atlas.research.nsog_nebula_analysis import (
        build_nsog_nebula_analysis,
        read_nsog_annotations,
        write_analysis_json,
        write_markdown,
        write_target_csv,
    )
    from nightsky_atlas.research.observing_lists.coverage import (
        build_coverage_report,
        discover_input_files,
        load_external_list,
        load_manual_overrides,
    )

    paths = tuple(path for input_path in args.input for path in discover_input_files(input_path))
    external_list = load_external_list(
        source="astroplanner",
        input_path=paths,
        list_name=args.list_name,
    )
    coverage = build_coverage_report(
        external_list,
        catalogue_path=args.catalogue,
        observing_config_path=args.observing_config,
        observing_lists_dir=args.observing_lists,
        pocket_atlas_path=args.pocket_atlas,
        coordinate_tolerance_arcmin=args.coordinate_tolerance_arcmin,
        overrides=load_manual_overrides(args.overrides),
    )
    annotations = read_nsog_annotations(paths)
    selection_report = build_selection_report(
        catalogue_path=args.catalogue,
        observing_config_path=args.observing_config,
        observing_lists_dir=args.observing_lists,
    )
    analysis = build_nsog_nebula_analysis(
        coverage,
        annotations=annotations,
        all_catalogue_objects=load_dso_catalog(args.catalogue),
        selection_decisions=selection_report["objects"],
    )
    write_markdown(analysis, args.markdown)
    write_analysis_json(analysis, args.json)
    write_target_csv(analysis, args.csv)
    summary = analysis["coverage_summary"]
    ratings = analysis["rating_aggregation"]
    dark = analysis["dark_nebula_catalogue_contribution"]
    bright = analysis["bright_nebula_catalogue_contribution"]
    nebula_count = sum(
        item["unique_matched_targets"] for item in summary["nebula_category_summaries"].values()
    )
    lbn_only = next(
        (
            row["targets"]
            for row in bright["by_identity_class"]
            if row["identity_class"] == "LBN-only"
        ),
        0,
    )
    print(
        f"NSOG nebula analysis: {nebula_count} matched nebula targets; "
        f"dark Barnard {dark['barnard_backed_including_overlap']}, "
        f"LDN-only {dark['ldn_only_count']}; bright LBN-only {lbn_only}"
    )
    print(
        f"ratings: {ratings['unique_target_count']} unique estimated targets; "
        f"{ratings['unrated_target_count']} unrated; "
        f"{ratings['conflicting_target_count']} conflicts"
    )
    print(f"Markdown -> {args.markdown}\nJSON -> {args.json}\nCSV -> {args.csv}")
    return 0


def _command_observing_list_compare(args: argparse.Namespace) -> int:
    from nightsky_atlas.research.observing_lists.coverage import compare_reports

    report = compare_reports(args.reports, minimum_lists=args.minimum_lists)
    print(
        f"Lists: {len(report['lists'])}; union: {report['unique_physical_targets_union']}; "
        f"intersection: {report['intersection_count']}; "
        f"in at least {args.minimum_lists}: {len(report['targets_in_at_least_minimum_lists'])}"
    )
    for target in report["targets"]:
        print(f"  {target['physical_object_id']}: {', '.join(target['lists'])}")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        print(f"JSON -> {args.json}")
    return 0


def _command_pocket_selection_report(args: argparse.Namespace) -> int:
    from nightsky_atlas.catalog.pocket_selection import (
        build_pocket_selection_report,
        summarize_pocket_selection_report,
    )

    report = build_pocket_selection_report(
        catalogue_path=args.catalogue,
        observing_config_path=args.observing_config,
        observing_lists_dir=args.observing_lists,
        atlas_path=args.atlas,
    )
    print(summarize_pocket_selection_report(report))
    print("\nlist overlap counts: " + json.dumps(report["list_overlaps"], sort_keys=True))
    print("source contribution counts:")
    for source, counts in report["source_counts"].items():
        print(
            f"  {source:28} {counts['pool_physical_objects']:6} pool, "
            f"{counts['selected_physical_objects']:6} selected"
        )
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        print(f"JSON -> {args.json}")
    return 0


def _command_why_object(args: argparse.Namespace) -> int:
    from nightsky_atlas.atlas.observing_config import (
        load_observing_lists_config,
        resolve_edition,
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
    editions = (args.edition,) if args.edition else ("pocket", "standard", "deep", "reference")
    policies = {edition: resolve_edition(config, edition) for edition in editions}
    if "pocket" in policies:
        pocket_atlas = load_atlas_config(args.atlas)
        policies["pocket"] = replace(
            policies["pocket"], visibility=pocket_atlas.visibility.to_limits()
        )
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


def _command_fetch_wds(args: argparse.Namespace) -> int:
    path = download_wds(args.dest)
    print(f"downloaded WDS -> {path}")
    return 0


def _command_import_wds(args: argparse.Namespace) -> int:
    raw = wds_raw_path(args.raw)
    if not raw.exists():
        raise ConfigError(f"missing raw WDS {raw}; run 'nightsky data fetch-wds' first")
    systems = list(iter_wds_systems(raw))
    count = write_system_catalog(args.out, systems)
    manifest = {
        "catalogue": WDS_CATALOGUE,
        "edition": WDS_EDITION,
        "source": "The Washington Visual Double Star Catalog (Mason et al.), CDS B/wds",
        "license": "Public domain (U.S. Naval Observatory); acknowledgement requested",
        "epoch": "J2000",
        "coordinate_rule": "sexagesimal RA/Dec converted to degrees",
        "separation_rule": (
            "latest-epoch separation/position angle where present, first-epoch fallback"
        ),
        "magnitude_rule": (
            "component magnitudes mag1/mag2; combined via -2.5 * log10(sum(10 ** (-0.4 * m_i)))"
        ),
        "raw_file": raw.name,
        "system_count": count,
        "processed_file": args.out.name,
        "processed_sha256": file_sha256(args.out),
        "match_note": ("linked to Tycho-2 stars per chart; WDS never overwrites the star base"),
    }
    write_manifest(args.manifest, manifest)
    print(f"imported {count} star systems -> {args.out}")
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
    out.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
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
