from __future__ import annotations

import argparse
import hashlib
import importlib
import io
import json
import math
import random
import subprocess
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import cairo
import yaml

from nightsky_atlas.atlas.config import load_atlas_config, load_style_config
from nightsky_atlas.build.progress import Progress
from nightsky_atlas.layout.association import dso_source_geometries
from nightsky_atlas.layout.models import Label
from nightsky_atlas.layout.optimizer import _star_circles, layout_hash
from nightsky_atlas.layout.validation import validate_layout
from nightsky_atlas.render.furniture import furniture_obstacles

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "build/label-review/ownership-2026-10-06-v1"
SEED = 20261006
CHARTS = {
    "pocket": ("pocket-012", "pocket-022", "pocket-025", "pocket-039"),
    "standard": ("standard-026", "standard-053", "standard-081", "standard-089"),
    "deep": ("deep-097", "deep-172", "deep-174", "deep-201"),
}
ADDITIONAL_BATCHES = {
    "pocket-extra": {
        "edition": "pocket",
        "charts": ["pocket-011", "pocket-013", "pocket-024", "pocket-040"],
        "reason": "Expand eligible Pocket sample after isolation and hard-constraint filtering.",
    }
}
VALIDATION_CHARTS = {
    "pocket": (
        "pocket-007",
        "pocket-009",
        "pocket-016",
        "pocket-021",
        "pocket-027",
        "pocket-029",
        "pocket-035",
        "pocket-037",
    ),
    "standard": ("standard-083", "standard-094"),
    "deep": ("deep-120", "deep-260"),
}


def source_fingerprints() -> dict[str, str]:
    files = set((ROOT / "src/nightsky_atlas").rglob("*.py"))
    files.update(
        path
        for path in (ROOT / "src/nightsky_atlas/assets/fonts").rglob("*")
        if path.suffix.lower() in {".ttf", ".otf"}
    )
    files.add(Path(__file__).resolve())
    return {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(files)
    }


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def save_crop(path: Path, crop: cairo.ImageSurface) -> None:
    buffer = io.BytesIO()
    crop.write_to_png(buffer)
    content = buffer.getvalue()
    if path.exists():
        if path.read_bytes() != content:
            raise ValueError(f"Refusing to change an existing review image: {path}")
        return
    path.write_bytes(content)


def changed_paths(left: object, right: object, prefix: str = "") -> list[str]:
    if isinstance(left, dict) and isinstance(right, dict):
        result = []
        for key in sorted(left.keys() | right.keys()):
            name = f"{prefix}.{key}" if prefix else key
            result.extend(changed_paths(left.get(key), right.get(key), name))
        return result
    return [] if left == right else [prefix]


def prepare(output: Path, preset: str = "initial") -> None:
    if output.exists():
        raise ValueError(f"Experiment directory already exists: {output}")
    config = output / "config"
    config.mkdir(parents=True)
    for edition in (*CHARTS, "deep_detail", "deep_detail_40"):
        atlas = load_atlas_config(ROOT / "atlas" / f"{edition}.yaml")
        style = load_style_config(ROOT / "styles" / f"{edition}.yaml")
        baseline = style.model_dump(mode="json")
        trial = json.loads(json.dumps(baseline))
        if edition in CHARTS:
            assert baseline["label"]["source_association"]["ambiguity_weight"] == 20.0
            trial["label"]["source_association"]["ambiguity_weight"] = 60.0
            assert changed_paths(baseline, trial) == ["label.source_association.ambiguity_weight"]
        for variant, mapping in (("baseline", baseline), ("trial", trial)):
            path = config / "styles" / variant / f"{edition}.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(yaml.safe_dump(mapping, sort_keys=False))
            load_style_config(path)
        atlas_path = config / "atlas" / f"{edition}.yaml"
        atlas_path.parent.mkdir(parents=True, exist_ok=True)
        atlas_path.write_text(yaml.safe_dump(atlas.model_dump(mode="json"), sort_keys=False))
    write_json(
        output / "experiment.json",
        {
            "experiment_id": (
                "ownership-validation-2026-10-07"
                if preset == "validation"
                else "ownership-single-weight-2026-10-06"
            ),
            "seed": 20261007 if preset == "validation" else SEED,
            "case_prefix": "own2" if preset == "validation" else "own",
            "charts": VALIDATION_CHARTS if preset == "validation" else CHARTS,
            "additional_batches": {} if preset == "validation" else ADDITIONAL_BATCHES,
            "changed_case_quotas": (
                {"pocket": 4, "standard": 2, "deep": 2}
                if preset == "validation"
                else {edition: 3 for edition in CHARTS}
            ),
            "minimum_changed_cases": 6 if preset == "validation" else 8,
            "changed_parameter": "label.source_association.ambiguity_weight",
            "baseline": 20.0,
            "trial": 60.0,
            "git_commit": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "selection": "Changed target placement; clear target symbol; no score-gain filter.",
            "holdout_charts": (
                []
                if preset == "validation"
                else ["standard-083", "standard-094", "deep-120", "deep-260"]
            ),
            "source_sha256": source_fingerprints(),
        },
    )
    print(output, flush=True)


def build(output: Path, edition: str, variant: str, batch: str | None = None) -> None:
    atlas_module = importlib.import_module("nightsky_atlas.build.atlas")
    original_optimize = atlas_module.optimize_labels
    original_build = atlas_module._build_main_chart
    optimization_results = {}

    def record_optimization(*args, **kwargs):
        result = original_optimize(*args, **kwargs)
        optimization_results[layout_hash(result.labels)] = result
        return result

    def record_page(definition, shared, progress=None):
        built = original_build(definition, shared, progress)
        result = optimization_results.pop(layout_hash(built.labels))
        labels = []
        for label in built.labels:
            data = label.to_dict()
            candidate = label.effective_candidate()
            data["candidates"] = [candidate.to_dict()] if candidate is not None else []
            labels.append(data)
        sources = dso_source_geometries(built.scene, built.transform, built.style)
        stars = _star_circles(built.scene, built.transform, built.style)
        validation = validate_layout(
            built.labels,
            built.scene,
            built.transform,
            built.style,
            furniture=furniture_obstacles(
                built.transform, definition, built.style, built.presentation
            ),
        )
        write_json(
            shared.outroot / "charts" / definition.id / "research-layout.json",
            {
                "chart": definition.to_dict(),
                "chart_code": built.presentation.chart_code,
                "page": asdict(built.transform.page),
                "mm_per_degree": built.transform.mm_per_deg,
                "labels": labels,
                "source_geometries": [asdict(source) for source in sources],
                "printed_stars": [
                    {
                        "id": star.id,
                        "center": asdict(star.center),
                        "radius_mm": star.radius_mm,
                        "marker_length_mm": star.marker_length_mm,
                    }
                    for star in stars
                ],
                "issues": [asdict(issue) for issue in validation.issues],
                "fallback_label_ids": dict(built.page_result.fallback_label_ids),
                "label_diagnostics": result.label_diagnostics,
                "metrics": result.metrics,
            },
        )
        print(f"Captured {definition.id}: {len(built.labels)} labels", flush=True)
        return built

    atlas_module.optimize_labels = record_optimization
    atlas_module._build_main_chart = record_page
    try:
        experiment = json.loads((output / "experiment.json").read_text())
        chart_ids = experiment["charts"][edition]
        render_root = output
        if batch is not None:
            chart_ids = experiment["additional_batches"][batch]["charts"]
            render_root = output / batch
        result = atlas_module.build_atlas(
            atlas_path=output / "config/atlas" / f"{edition}.yaml",
            style_path=output / "config/styles" / variant / f"{edition}.yaml",
            outdir=render_root / variant,
            star_store=ROOT / "data/processed/stars/tycho2.sqlite",
            chart_ids=tuple(chart_ids),
            optimize=True,
            jobs=1,
            render_png=False,
            write_front_matter=False,
            write_overviews=False,
            write_draft_report=True,
            progress=Progress(),
        )
        print(f"Built {variant}/{edition}: {result.combined_pdf}", flush=True)
    finally:
        atlas_module.optimize_labels = original_optimize
        atlas_module._build_main_chart = original_build


def source_radius(source: dict) -> float:
    rx, ry = source["radius_x_mm"], source["radius_y_mm"]
    return math.hypot(rx, ry) if "square" in source["shape"] else max(rx, ry)


def isolated_target(source: dict, page: dict) -> bool:
    if source.get("outline_paths") or source_radius(source) > 1.2:
        return False
    point = source["center"]
    for other in page["source_geometries"]:
        if other["id"] == source["id"]:
            continue
        other_point = other["center"]
        distance = math.hypot(
            point["x_mm"] - other_point["x_mm"], point["y_mm"] - other_point["y_mm"]
        )
        if distance < max(2.25, source_radius(source) + source_radius(other) + 0.3):
            return False
        points = [p for path in other.get("outline_paths", ()) for p in path]
        if points and (
            min(p["x_mm"] for p in points) <= point["x_mm"] <= max(p["x_mm"] for p in points)
            and min(p["y_mm"] for p in points) <= point["y_mm"] <= max(p["y_mm"] for p in points)
        ):
            return False
    for star in page["printed_stars"]:
        center = star["center"]
        radius = max(star["radius_mm"], star["marker_length_mm"] / 2.0)
        if (
            math.hypot(point["x_mm"] - center["x_mm"], point["y_mm"] - center["y_mm"])
            < radius + 1.1
        ):
            return False
    return True


def intersects(a: tuple[float, ...], b: tuple[float, ...]) -> bool:
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and (a[1] < b[1] + b[3] and b[1] < a[1] + a[3])


def crop_has_issue(page: dict, box_mm: tuple[float, ...]) -> bool:
    bounds = {}
    for item in page["labels"]:
        label = Label.from_dict(item)
        candidate = label.effective_candidate()
        if candidate is not None and not label.hidden:
            rect = candidate.bounds
            bounds[label.id] = (rect.left_mm, rect.top_mm, rect.width_mm, rect.height_mm)
    for source in page["source_geometries"]:
        center, radius = source["center"], source_radius(source)
        bounds[source["id"]] = (
            center["x_mm"] - radius,
            center["y_mm"] - radius,
            2 * radius,
            2 * radius,
        )
    for star in page["printed_stars"]:
        center = star["center"]
        radius = max(star["radius_mm"], star["marker_length_mm"] / 2.0)
        bounds[star["id"]] = (
            center["x_mm"] - radius,
            center["y_mm"] - radius,
            2 * radius,
            2 * radius,
        )
    return any(
        element in bounds and intersects(bounds[element], box_mm)
        for issue in page["issues"]
        for element in issue["element_ids"]
    )


def raster_page(output: Path, edition: str, variant: str, chart_id: str, page: dict) -> Path:
    atlas_dir = Path(page["atlas_directory"])
    manifest = json.loads((atlas_dir / "manifest.json").read_text())
    assert manifest["front_matter_page_count"] == 0
    assert not manifest["overview_pages"]
    page_number = manifest["main_chart_ids"].index(chart_id) + 1
    target = output / "rasters" / variant / edition / chart_id
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.with_suffix(".png").exists():
        subprocess.run(
            [
                "pdftoppm",
                "-f",
                str(page_number),
                "-l",
                str(page_number),
                "-singlefile",
                "-png",
                "-r",
                "300",
                str(atlas_dir / "atlas.pdf"),
                str(target),
            ],
            check=True,
        )
    return target.with_suffix(".png")


def make_case(
    output: Path, edition: str, left: dict, right: dict, label_id: str, control: bool
) -> dict | None:
    chart_id = left["chart"]["id"]
    experiment = json.loads((output / "experiment.json").read_text())
    seed = experiment["seed"]
    labels = [
        next(Label.from_dict(x) for x in page["labels"] if x["id"] == label_id)
        for page in (left, right)
    ]
    source = next(x for x in left["source_geometries"] if x["id"] == labels[0].target_id)
    prefix = experiment.get("case_prefix", "own")
    case_id = f"{prefix}-{left['chart_code'].lower()}-{labels[0].target_id.lower()}"
    case_id = "".join(c if c.isalnum() or c == "-" else "-" for c in case_id)
    rng = random.Random(f"{seed}:{case_id}")
    width_mm, height_mm = 55.0, 45.0
    x_mm = source["center"]["x_mm"] - width_mm / 2.0 + rng.uniform(-9.0, 9.0)
    y_mm = source["center"]["y_mm"] - height_mm / 2.0 + rng.uniform(-7.0, 7.0)
    x_mm = max(0.0, min(x_mm, left["page"]["width_mm"] - width_mm))
    y_mm = max(0.0, min(y_mm, left["page"]["height_mm"] - height_mm))
    box_mm = (x_mm, y_mm, width_mm, height_mm)
    if any(crop_has_issue(page, box_mm) for page in (left, right)):
        return None
    for label in labels:
        bounds = label.effective_candidate().bounds
        if not (
            x_mm + 3 < bounds.left_mm
            and bounds.right_mm < x_mm + width_mm - 3
            and y_mm + 3 < bounds.top_mm
            and bounds.bottom_mm < y_mm + height_mm - 3
        ):
            return None
    factor = 300 / 25.4
    box = [round(value * factor) for value in box_mm]
    x, y, width, height = box
    paths = [
        raster_page(output, edition, variant, chart_id, page)
        for variant, page in zip(("baseline", "trial"), (left, right), strict=True)
    ]
    surfaces = [cairo.ImageSurface.create_from_png(str(path)) for path in paths]
    page_size = [surfaces[0].get_width(), surfaces[0].get_height()]
    assert page_size == [surfaces[1].get_width(), surfaces[1].get_height()]
    crops = []
    for surface in surfaces:
        crop = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        context = cairo.Context(crop)
        context.set_source_surface(surface, -x, -y)
        context.paint()
        crop.flush()
        crops.append(crop)
    identical = bytes(crops[0].get_data()) == bytes(crops[1].get_data())
    if identical != control:
        return None
    manifest = json.loads((Path(left["atlas_directory"]) / "manifest.json").read_text())
    page_number = manifest["main_chart_ids"].index(chart_id) + 1
    variants = []
    for variant, crop in zip(("baseline", "trial"), crops, strict=True):
        page = left if variant == "baseline" else right
        source_pdf = (Path(page["atlas_directory"]) / "atlas.pdf").resolve().relative_to(ROOT)
        image = Path("cases/assets") / f"{case_id}-{variant}.png"
        save_crop(Path(__file__).parent / image, crop)
        variants.append(
            {
                "variant_id": (
                    f"ownership-{variant}-2026-10-06"
                    if experiment["experiment_id"] == "ownership-single-weight-2026-10-06"
                    else f"{experiment['experiment_id']}-{variant}"
                ),
                "image": str(image),
                "source_page": f"{source_pdf}#page={page_number}",
                "target_px": [
                    source["center"]["x_mm"] * factor - x,
                    source["center"]["y_mm"] * factor - y,
                ],
                "crop_box_px": box,
                "source_page_size_px": page_size,
                "registration_id": f"{chart_id}-{experiment['experiment_id']}-300dpi",
            }
        )
    return {
        "case_id": case_id,
        "chart_id": chart_id,
        "chart_code": left["chart_code"],
        "label_id": label_id,
        "object_id": labels[0].target_id,
        "label_text": labels[0].text,
        "question": f"Welches Symbol gehört zur Beschriftung {labels[0].text}?",
        "control": control,
        "accuracy_evaluable": True,
        "crop": {
            "page_size_px": page_size,
            "box_px": box,
            "print_size_mm": [width / factor, height / factor],
        },
        "variants": variants,
        "research": {
            "baseline_diagnostic": left["label_diagnostics"][label_id],
            "trial_diagnostic": right["label_diagnostics"][label_id],
            "crop_hard_issues": 0,
        },
    }


def curate(output: Path) -> None:
    manifest_path = output / "cases.json"
    if manifest_path.exists():
        raise ValueError("Case set already frozen; use a new experiment directory")
    experiment = json.loads((output / "experiment.json").read_text())
    chosen = []
    page_checks = []
    rejections = Counter()
    for edition, chart_ids in experiment["charts"].items():
        quota = experiment.get("changed_case_quotas", {}).get(edition, 3)
        changed = []
        unchanged = []
        batches = [(output, chart_ids)] + [
            (output / name, entry["charts"])
            for name, entry in experiment.get("additional_batches", {}).items()
            if entry["edition"] == edition
        ]
        for render_root, chart_id in (
            (root, chart_id) for root, ids in batches for chart_id in ids
        ):
            pages = [
                json.loads(
                    (
                        render_root
                        / variant
                        / edition
                        / "charts"
                        / chart_id
                        / "research-layout.json"
                    ).read_text()
                )
                for variant in ("baseline", "trial")
            ]
            for variant, page in zip(("baseline", "trial"), pages, strict=True):
                page["atlas_directory"] = str(render_root / variant / edition)
            left, right = pages
            assert left["source_geometries"] == right["source_geometries"]
            assert left["printed_stars"] == right["printed_stars"]
            baseline_issues = {i["id"] for i in left["issues"]}
            added_issues = {i["id"] for i in right["issues"]} - baseline_issues
            by_id = [{x["id"]: Label.from_dict(x) for x in page["labels"]} for page in pages]
            visible = [
                {(x.id, x.text) for x in labels.values() if not x.hidden} for labels in by_id
            ]
            page_checks.append(
                {
                    "chart_id": chart_id,
                    "baseline_hard_issues": len(left["issues"]),
                    "trial_hard_issues": len(right["issues"]),
                    "added_issue_ids": sorted(added_issues),
                    "same_visible_labels": visible[0] == visible[1],
                }
            )
            if added_issues or visible[0] != visible[1]:
                rejections["new_page_issue_or_changed_visible_content"] += 1
                continue
            for source in left["source_geometries"]:
                label_id = f"label:dso:{source['id']}"
                if label_id not in by_id[0] or label_id not in by_id[1]:
                    continue
                a, b = by_id[0][label_id], by_id[1][label_id]
                if (
                    a.hidden
                    or b.hidden
                    or not a.effective_candidate()
                    or not b.effective_candidate()
                ):
                    continue
                if not isolated_target(source, left):
                    rejections["overlapping_or_large_target"] += 1
                    continue
                ac, bc = a.effective_candidate(), b.effective_candidate()
                movement = math.hypot(
                    ac.bounds.left_mm - bc.bounds.left_mm,
                    ac.bounds.top_mm - bc.bounds.top_mm,
                )
                line_changed = a.leader_line != b.leader_line
                baseline_ambiguity = left["label_diagnostics"][label_id][
                    "competing_source_ambiguity_cost"
                ]
                entry = (baseline_ambiguity, movement, chart_id, label_id, left, right)
                if (movement >= 0.3 or line_changed) and baseline_ambiguity > 0:
                    changed.append(entry)
                elif movement < 1e-9 and not line_changed:
                    unchanged.append(entry)
        used_charts = set()
        changed_count = 0
        for entry in sorted(changed, key=lambda x: (-x[0], -x[1], x[2], x[3])):
            _, _, chart_id, label_id, left, right = entry
            if chart_id in used_charts:
                continue
            case = make_case(output, edition, left, right, label_id, False)
            if case is None:
                rejections["changed_crop_issue_or_no_pixel_change"] += 1
                continue
            chosen.append(case)
            used_charts.add(chart_id)
            changed_count += 1
            if changed_count == quota:
                break
        for entry in sorted(unchanged, key=lambda x: (x[2], x[3])):
            _, _, _, label_id, left, right = entry
            case = make_case(output, edition, left, right, label_id, True)
            if case is None:
                continue
            chosen.append(case)
            break
        print(f"{edition}: {changed_count} changed cases", flush=True)
    if sum(not case["control"] for case in chosen) < experiment.get("minimum_changed_cases", 8):
        write_json(
            output / "curation-diagnostics.json",
            {
                "page_checks": page_checks,
                "rejections": dict(rejections),
                "partial_cases": chosen,
            },
        )
        raise ValueError("Too few eligible changed cases; inspect diagnostics before expanding")
    write_json(
        manifest_path,
        {
            "experiment_id": experiment["experiment_id"],
            "seed": experiment["seed"],
            "dpi": 300,
            "require_calibration": True,
            "cases": chosen,
        },
    )
    review_server = importlib.import_module("server")
    review_server.load_manifest(manifest_path)
    checksums = {
        v["image"]: hashlib.sha256((Path(__file__).parent / v["image"]).read_bytes()).hexdigest()
        for case in chosen
        for v in case["variants"]
    }
    write_json(
        output / "curation.json",
        {
            "page_checks": page_checks,
            "rejections": dict(rejections),
            "case_count": len(chosen),
            "changed_count": sum(not c["control"] for c in chosen),
            "asset_sha256": checksums,
        },
    )
    print(f"Ready: {len(chosen)} cases -> {manifest_path}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Single-parameter ownership experiment")
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTPUT)
    commands = parser.add_subparsers(dest="command", required=True)
    preparation = commands.add_parser("prepare")
    preparation.add_argument("--preset", choices=("initial", "validation"), default="initial")
    commands.add_parser("curate")
    render = commands.add_parser("build")
    render.add_argument("--edition", choices=tuple(CHARTS), required=True)
    render.add_argument("--variant", choices=("baseline", "trial", "both"), default="both")
    render.add_argument("--batch")
    args = parser.parse_args()
    args.outdir = args.outdir.resolve()
    if args.command == "prepare":
        prepare(args.outdir, args.preset)
    elif args.command == "curate":
        curate(args.outdir)
    else:
        variants = ("baseline", "trial") if args.variant == "both" else (args.variant,)
        for variant in variants:
            build(args.outdir, args.edition, variant, args.batch)


if __name__ == "__main__":
    main()
