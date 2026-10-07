from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import shutil
from dataclasses import asdict, replace
from pathlib import Path

import cairo
import make_ownership_experiment as experiment
import server

from nightsky_atlas.layout.leader_lines import resolve_leader_lines
from nightsky_atlas.layout.validation import validate_layout

ROOT = experiment.ROOT
DEFAULT_OUTPUT = ROOT / "build/label-review/long-label-lines-2026-10-07"
TARGETS = {
    "pocket": ("pocket-037", "label:dso:NGC5128"),
    "standard": ("standard-094", "label:dso:ESO274-001"),
}


def prepare(output: Path, source: Path) -> None:
    if output.exists():
        raise ValueError(f"Experiment directory already exists: {output}")
    for edition in TARGETS:
        atlas = output / "config/atlas" / f"{edition}.yaml"
        atlas.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / "config/atlas" / atlas.name, atlas)
        for variant in ("baseline", "trial"):
            style = output / "config/styles" / variant / atlas.name
            style.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / "config/styles/baseline" / atlas.name, style)
            config = experiment.load_style_config(style)
            if config.label.source_association.ambiguity_weight != 20.0:
                raise ValueError("This experiment requires unchanged ownership weight 20")
    fingerprints = experiment.source_fingerprints()
    fingerprints[str(Path(__file__).relative_to(ROOT))] = hashlib.sha256(
        Path(__file__).read_bytes()
    ).hexdigest()
    experiment.write_json(
        output / "experiment.json",
        {
            "experiment_id": "long-label-lines-2026-10-07",
            "seed": 20261009,
            "case_prefix": "long1",
            "charts": {edition: [target[0]] for edition, target in TARGETS.items()},
            "targets": {edition: target[1] for edition, target in TARGETS.items()},
            "source_experiment": str(source.relative_to(ROOT)),
            "changed_state": ["leader_line", "leader_line_reason"],
            "ownership_weight": 20.0,
            "source_sha256": fingerprints,
            "exposure": "Targets already viewed; a focused line experiment, not unseen validation.",
        },
    )
    print(output, flush=True)


def build(output: Path, edition: str, variant: str) -> None:
    atlas = importlib.import_module("nightsky_atlas.build.atlas")
    original = atlas.optimize_labels
    target_chart, target_label = TARGETS[edition]

    def add_line(labels, scene, transform, style, **kwargs):
        result = original(labels, scene, transform, style, **kwargs)
        if transform.chart.id != target_chart:
            raise ValueError(f"Unexpected chart: {transform.chart.id}")
        label = next(label for label in result.labels if label.id == target_label)
        if label.hidden or label.leader_line:
            raise ValueError("Expected a visible target without an existing leader line")
        modified = tuple(
            replace(item, leader_line=True, leader_line_reason="research_long_label")
            if item.id == target_label
            else item
            for item in result.labels
        )
        before = resolve_leader_lines(result.labels, scene, transform, style)
        after = resolve_leader_lines(modified, scene, transform, style)
        route = next((line for line in after if line.label_id == target_label), None)
        if route is None or tuple(line for line in after if line != route) != before:
            raise ValueError("New line is unsafe or changes an existing line route")
        if len(after) != sum(item.leader_line for item in modified):
            raise ValueError("Some requested leader lines could not be resolved")
        verdict = validate_layout(
            modified, scene, transform, style, furniture=kwargs.get("furniture", ())
        )
        if verdict.issues:
            raise ValueError(f"Line variant has layout issues: {verdict.issues}")
        length = math.hypot(route.end.x_mm - route.start.x_mm, route.end.y_mm - route.start.y_mm)
        experiment.write_json(
            output / f"{edition}-line-check.json",
            {
                "chart_id": target_chart,
                "label_id": target_label,
                "route": asdict(route),
                "length_mm": length,
                "unchanged_existing_routes": True,
                "hard_issues": 0,
                "position_changed": False,
            },
        )
        diagnostics = {key: dict(value) for key, value in result.label_diagnostics.items()}
        diagnostics[target_label].update(
            {
                "leader_line_used": True,
                "leader_line_reason": "research_long_label",
                "leader_line_length_mm": length,
                "research_note": (
                    "Line added after optimization; other costs describe original placement."
                ),
            }
        )
        metrics = dict(result.metrics)
        metrics["research_post_optimization_line"] = target_label
        return replace(result, labels=modified, label_diagnostics=diagnostics, metrics=metrics)

    try:
        if variant == "trial":
            atlas.optimize_labels = add_line
        experiment.build(output, edition, variant)
    finally:
        atlas.optimize_labels = original


def curate(output: Path) -> None:
    if (output / "cases.json").exists():
        raise ValueError("Case set already frozen; use a new experiment directory")
    metadata = json.loads((output / "experiment.json").read_text())
    cases, checks = [], []
    source_root = ROOT / metadata["source_experiment"]
    for edition, (chart_id, target_label) in TARGETS.items():
        pages = []
        for variant in ("baseline", "trial"):
            directory = output / variant / edition
            page = json.loads(
                (directory / "charts" / chart_id / "research-layout.json").read_text()
            )
            page["atlas_directory"] = str(directory)
            pages.append(page)
        left, right = pages
        original = json.loads(
            (
                source_root / "baseline" / edition / "charts" / chart_id / "research-layout.json"
            ).read_text()
        )
        for key in ("labels", "source_geometries", "printed_stars", "issues"):
            if left[key] != original[key]:
                raise ValueError(f"Baseline changed from previous round: {chart_id}/{key}")
        for key in ("chart", "page", "mm_per_degree", "source_geometries", "printed_stars"):
            if left[key] != right[key]:
                raise ValueError(f"Chart content changed: {chart_id}/{key}")
        differences = []
        for a, b in zip(left["labels"], right["labels"], strict=True):
            changed = experiment.changed_paths(a, b)
            if changed:
                if a["id"] != target_label or changed != ["leader_line", "leader_line_reason"]:
                    raise ValueError(f"Unexpected label change: {a['id']}/{changed}")
                differences.append(a["id"])
        if differences != [target_label] or left["issues"] or right["issues"]:
            raise ValueError(f"Invalid chart comparison: {chart_id}")
        source = next(
            item
            for item in left["source_geometries"]
            if item["id"] == target_label.removeprefix("label:dso:")
        )
        if not experiment.isolated_target(source, left):
            raise ValueError(f"Target is not safely clickable: {target_label}")
        changed_case = experiment.make_case(output, edition, left, right, target_label, False)
        if changed_case is None:
            raise ValueError(f"Cannot create changed crop: {target_label}")
        cases.append(changed_case)
        for label in sorted(left["labels"], key=lambda item: item["id"]):
            if not label["id"].startswith("label:dso:") or label["id"] == target_label:
                continue
            source = next(
                (item for item in left["source_geometries"] if item["id"] == label["target_id"]),
                None,
            )
            if label["hidden"] or source is None or not experiment.isolated_target(source, left):
                continue
            control = experiment.make_case(output, edition, left, right, label["id"], True)
            if control is not None:
                cases.append(control)
                break
        else:
            raise ValueError(f"No pixel-identical control available: {chart_id}")
        checks.append(json.loads((output / f"{edition}-line-check.json").read_text()))
    manifest = {key: metadata[key] for key in ("experiment_id", "seed")}
    manifest.update(dpi=300, require_calibration=True, cases=cases)
    experiment.write_json(output / "cases.json", manifest)
    server.load_manifest(output / "cases.json")
    experiment.write_json(
        output / "curation.json",
        {
            "page_checks": checks,
            "case_count": len(cases),
            "changed_count": sum(not case["control"] for case in cases),
            "asset_sha256": {
                variant["image"]: hashlib.sha256(
                    (Path(__file__).parent / variant["image"]).read_bytes()
                ).hexdigest()
                for case in cases
                for variant in case["variants"]
            },
        },
    )
    contact_sheet(output, cases)
    lines = [
        "# Short leaders for long labels",
        "",
        "Two changed crops and two pixel-identical controls. Only a leader line is added; "
        "all positions, visible labels, astronomical content and weight 20 remain unchanged.",
        "",
        "The baseline exactly reproduces the previous round's baseline layouts. "
        "All four source pages have zero hard layout issues. Existing routes remain unchanged.",
        "",
        "| Chart | Target | Visible line length |",
        "| --- | --- | ---: |",
    ]
    lines.extend(
        f"| {check['chart_id']} | {check['label_id']} | {check['length_mm']:.3f} mm |"
        for check in checks
    )
    lines.extend(
        [
            "",
            "These targets are already familiar to the observer. This focused comparison "
            "does not establish a general rule for long names. There is no score-gain filter; "
            "stored optimizer costs describe the original placement before the intervention.",
            "",
            "Responses are stored separately in responses.jsonl. No production changes.",
            "",
        ]
    )
    (output / "report.md").write_text("\n".join(lines))
    print(f"Ready: {len(cases)} cases -> {output / 'cases.json'}", flush=True)


def contact_sheet(output: Path, cases: list[dict]) -> None:
    width, height = 1360, len(cases) * 580
    sheet = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    context = cairo.Context(sheet)
    context.set_source_rgb(1, 1, 1)
    context.paint()
    context.set_font_size(18)
    for row, case in enumerate(cases):
        context.set_source_rgb(0, 0, 0)
        context.move_to(15, row * 580 + 26)
        context.show_text(f"{case['chart_code']}: {case['label_text']} / control={case['control']}")
        for column, variant in enumerate(case["variants"]):
            surface = cairo.ImageSurface.create_from_png(
                str(Path(__file__).parent / variant["image"])
            )
            context.set_source_surface(surface, 15 + column * 670, row * 580 + 40)
            context.paint()
    sheet.write_to_png(str(output / "contact-sheet.png"))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Research-only fixed-position leader-line comparison"
    )
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTPUT)
    commands = parser.add_subparsers(dest="command", required=True)
    preparation = commands.add_parser("prepare")
    preparation.add_argument(
        "--source", type=Path, default=ROOT / "build/label-review/ownership-validation-2026-10-07"
    )
    render = commands.add_parser("build")
    render.add_argument("--edition", choices=tuple(TARGETS), required=True)
    render.add_argument("--variant", choices=("baseline", "trial"), required=True)
    commands.add_parser("curate")
    args = parser.parse_args()
    output = args.outdir.resolve()
    if args.command == "prepare":
        prepare(output, args.source.resolve())
    elif args.command == "build":
        build(output, args.edition, args.variant)
    else:
        curate(output)


if __name__ == "__main__":
    main()
