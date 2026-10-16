"""Catalogue import and inspection commands for the NightSky Atlas CLI."""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path

from nightsky_atlas.atlas.config import (
    ConfigError,
    load_style_config,
)
from nightsky_atlas.catalog.dso_store import load_dso_catalog, write_dso_catalog
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
from nightsky_atlas.catalog.selection_analysis import (
    build_selection_report,
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
from nightsky_atlas.catalog.ucc import (
    UCC_VERSION,
    crossmatch_ucc_objects,
    download_ucc,
    iter_ucc_objects,
)
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

_DEFAULT_STYLE = Path("styles/standard.yaml")
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
_DEFAULT_STAR_NAMES = STAR_NAMES_FIXTURE_DIR
_DEFAULT_OBSERVING_LISTS = Path("data/fixtures/observing_lists")
_DEFAULT_OBSERVING_CONFIG = Path("config/observing_lists.yaml")


def _add_catalogue_report_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--catalogue", type=Path, default=_DEFAULT_COMBINED_DSO_OUT)
    parser.add_argument("--manifest", type=Path, default=_DEFAULT_COMBINED_DSO_MANIFEST)
    parser.add_argument("--openngc", type=Path, default=_DEFAULT_DSO_OUT)
    parser.add_argument("--openngc-manifest", type=Path, default=_DEFAULT_DSO_MANIFEST)
    parser.add_argument("--openngc-raw", type=Path, default=_DEFAULT_OPENNGC_RAW)
    parser.add_argument("--vizier-raw", type=Path, default=_DEFAULT_VIZIER_RAW)
    parser.add_argument(
        "--crossmatch-report", type=Path, default=Path("data/processed/dso/vizier-crossmatch.json")
    )
    parser.add_argument(
        "--observing-config", type=Path, default=_DEFAULT_OBSERVING_CONFIG
    )
    parser.add_argument("--observing-lists", type=Path, default=_DEFAULT_OBSERVING_LISTS)


def add_data_commands(subparsers: argparse._SubParsersAction) -> None:
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

    labels = data_subparsers.add_parser(
        "star-label-report", help="count eligible stellar label types for an edition"
    )
    labels.add_argument(
        "--edition", choices=("pocket", "standard", "deep"),
        help="select matching atlas and style presets (Pocket, Standard or Deep)",
    )
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

    ucc_fetch = data_subparsers.add_parser(
        "fetch-ucc", help="download the pinned Unified Cluster Catalogue release"
    )
    ucc_fetch.add_argument("--dest", type=Path, default=Path("data/raw/ucc/260615"))
    ucc_fetch.set_defaults(handler=_command_fetch_ucc)

    ucc_import = data_subparsers.add_parser(
        "import-ucc", help="conservatively merge cached UCC clusters into the DSO catalogue"
    )
    ucc_import.add_argument("--raw", type=Path, default=Path("data/raw/ucc/260615"))
    ucc_import.add_argument("--base", type=Path, default=_DEFAULT_COMBINED_DSO_OUT)
    ucc_import.add_argument("--out", type=Path, default=_DEFAULT_COMBINED_DSO_OUT)
    ucc_import.add_argument("--manifest", type=Path, default=_DEFAULT_COMBINED_DSO_MANIFEST)
    ucc_import.add_argument(
        "--report", type=Path, default=Path("data/processed/dso/ucc-crossmatch.json")
    )
    ucc_import.set_defaults(handler=_command_import_ucc)

    dso_info = data_subparsers.add_parser(
        "dso-info",
        help="inspect a canonical DSO, aliases and source decisions",
    )
    dso_info.add_argument("--catalogue", type=Path, default=_DEFAULT_COMBINED_DSO_OUT)
    dso_info.add_argument("designation", help="canonical designation or known alias")
    dso_info.set_defaults(handler=_command_dso_info)

    catalogue_report = data_subparsers.add_parser(
        "catalogue-report", help="report normalized physical-object and edition catalogue counts"
    )
    _add_catalogue_report_arguments(catalogue_report)
    catalogue_report.add_argument(
        "--out", type=Path, default=Path("data/processed/dso/catalogue-inventory.json")
    )
    catalogue_report.set_defaults(handler=_command_catalogue_report)

    selection_report = data_subparsers.add_parser(
        "selection-report", help="audit current DSO selection by edition, type and source"
    )
    _add_catalogue_report_arguments(selection_report)
    selection_report.add_argument("--json", type=Path, default=None, help="write full JSON report")
    selection_report.add_argument("--csv", type=Path, default=None, help="write per-object CSV")
    selection_report.set_defaults(handler=_command_selection_report)

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
            canonical = name.canonical_display_variant()
            if canonical and name.display_variant_enabled(
                canonical[1],
                style.label.star_labels,
                magnitude,
                proper_magnitude_limit=style.star.label_magnitude_limit,
            ):
                kind = canonical[1]
                if kind == "combined" or kind.startswith("proper_"):
                    counts["proper"] += 1
                    tier = (
                        name.proper_name_tier
                        if kind == "combined"
                        else kind.removeprefix("proper_")
                    )
                    if tier:
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


def _command_fetch_ucc(args: argparse.Namespace) -> int:
    path = download_ucc(args.dest)
    print(f"downloaded and checksum-verified UCC {UCC_VERSION} -> {path}")
    print(f"source manifest -> {args.dest / 'manifest.json'}")
    return 0


def _command_import_ucc(args: argparse.Namespace) -> int:
    if not args.base.exists():
        raise ConfigError(
            f"missing base DSO catalogue {args.base}; run 'nightsky data import-vizier-dsos' first"
        )
    base_sha256 = file_sha256(args.base)
    prior_manifest = (
        json.loads(args.manifest.read_text(encoding="utf-8")) if args.manifest.exists() else {}
    )
    prior_ucc_import = prior_manifest.get("ucc_import", {})
    if (
        args.base.resolve() == args.out.resolve()
        and prior_ucc_import.get("version") == UCC_VERSION
        and prior_ucc_import.get("base_file") == str(args.base)
    ):
        base_sha256 = prior_ucc_import.get("base_sha256", base_sha256)
    base_objects = load_dso_catalog(args.base)
    source_objects = tuple(iter_ucc_objects(args.raw))
    result = crossmatch_ucc_objects(base_objects, source_objects)
    count = write_dso_catalog(args.out, result.objects)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(
            {
                "catalogue": "Unified Cluster Catalogue",
                "version": UCC_VERSION,
                "counts": result.summary,
                "decisions": list(result.decisions),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    source_manifest = json.loads((args.raw / "manifest.json").read_text(encoding="utf-8"))
    manifest = prior_manifest
    manifest.update(
        {
            "source": "OpenNGC, selected VizieR catalogues, and Unified Cluster Catalogue",
            "license": "Mixed per source; no blanket redistribution licence asserted",
            "ucc_source": source_manifest,
            "ucc_import": {
                "base_file": str(args.base),
                "base_sha256": base_sha256,
                "version": UCC_VERSION,
                "raw_rows": result.summary["raw"],
                "matched_existing": result.summary["matched"],
                "new_objects": result.summary["new"],
                "uncertain_or_rejected": (
                    result.summary["uncertain"]
                    + result.summary["rejected_bad_oc"]
                    + result.summary["rejected_duplicate_risk"]
                ),
                "selection_policy_changed": False,
                "crossmatch_report": str(args.report),
            },
            "object_count": count,
            "processed_file": args.out.name,
            "processed_sha256": file_sha256(args.out),
        }
    )
    write_manifest(args.manifest, manifest)
    print(
        f"UCC rows {result.summary['raw']}; matched {result.summary['matched']}; "
        f"new {result.summary['new']}; uncertain {result.summary['uncertain']}; "
        f"bad_oc rejected {result.summary['rejected_bad_oc']}; "
        f"duplicate-risk held {result.summary['rejected_duplicate_risk']}"
    )
    print(f"merged {count} physical-object records -> {args.out}")
    print(f"cross-match report -> {args.report}")
    print(f"manifest -> {args.manifest}")
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
        "license": "No explicit reuse licence identified; USNO acknowledgement requested",
        "source_url": "https://crf.usno.navy.mil/wds",
        "acknowledgement": (
            "This research has made use of the Washington Double Star Catalog "
            "maintained at the U.S. Naval Observatory."
        ),
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
