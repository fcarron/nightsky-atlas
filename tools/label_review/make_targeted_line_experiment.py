from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import shutil
from collections import Counter
from dataclasses import asdict, replace
from pathlib import Path

import make_long_label_line_experiment as long_lines
import make_ownership_experiment as experiment
import server

from nightsky_atlas.layout.leader_lines import (
    leader_line_for,
    prepare_leader_routing_context,
    resolve_leader_lines,
)
from nightsky_atlas.layout.models import Label
from nightsky_atlas.layout.text_geometry import candidate_ink_bounds
from nightsky_atlas.layout.validation import validate_layout

ROOT = experiment.ROOT
DEFAULT_OUTPUT = ROOT / "build/label-review/targeted-lines-2026-10-07"
CHARTS = {
    "pocket": ["pocket-022", "pocket-017", "pocket-045", "pocket-039"],
    "standard": ["standard-063", "standard-031", "standard-103", "standard-083"],
    "deep": ["deep-223", "deep-081", "deep-393", "deep-318"],
}
ADDITIONAL_BATCHES = {
    "southern-standard": {"edition": "standard", "charts": ["standard-081"]},
    "southern-deep": {"edition": "deep", "charts": ["deep-314"]},
}
RULE = {
    "min_ink_width_mm": 8.0,
    "min_ink_aspect_ratio": 4.0,
    "min_competing_owner_cost": 1.0,
    "max_line_length_mm": 3.0,
    "ambiguity": "competing_owner_cost >= 1 OR corridor > 0 OR weak ownership margin",
    "order": "priority descending, stable label id ascending",
    "scope": "visible unlocked DSO labels without an existing leader; no movement",
    "status": "Exploratory thresholds fixed before rendering; not production defaults.",
}


def signals(label: Label, diagnostic: dict) -> dict:
    candidate = label.effective_candidate()
    if candidate is None:
        return {"long": False, "ambiguous": False}
    ink = candidate_ink_bounds(candidate)
    ratio = ink.width_mm / max(ink.height_mm, 0.001)
    return {
        "width_mm": ink.width_mm,
        "aspect_ratio": ratio,
        "long": ink.width_mm >= RULE["min_ink_width_mm"] and ratio >= RULE["min_ink_aspect_ratio"],
        "ambiguous": (
            diagnostic.get("competing_owner_cost", 0.0) >= RULE["min_competing_owner_cost"]
            or diagnostic.get("association_corridor_cost", 0.0) > 0.0
            or diagnostic.get("ownership_margin_weak", False)
        ),
    }


def prepare(output: Path) -> None:
    if output.exists():
        raise ValueError(f"Experiment already exists: {output}")
    source = ROOT / "build/label-review/ownership-validation-2026-10-07/config"
    for edition in (*CHARTS, "deep_detail", "deep_detail_40"):
        for destination, original in (
            (output / "config/atlas", source / "atlas"),
            (output / "config/styles/baseline", source / "styles/baseline"),
            (output / "config/styles/trial", source / "styles/baseline"),
        ):
            destination.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original / f"{edition}.yaml", destination / f"{edition}.yaml")
    fingerprints = experiment.source_fingerprints()
    for path in (Path(__file__), Path(long_lines.__file__)):
        fingerprints[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    experiment.write_json(
        output / "experiment.json",
        {
            "experiment_id": "targeted-lines-2026-10-07",
            "seed": 20261010,
            "case_prefix": "target1",
            "charts": CHARTS,
            "additional_batches": ADDITIONAL_BATCHES,
            "rule": RULE,
            "ownership_weight": 20.0,
            "source_sha256": fingerprints,
            "curation": "Up to two changed crops per edition from different charts, plus controls; "
            "exclude previously evaluated physical targets; no score-gain filter.",
            "exposure": (
                "Some source charts were viewed before; individual target exposure is checked."
            ),
        },
    )
    print(output, flush=True)


def build(output: Path, edition: str, variant: str, batch: str | None = None) -> None:
    atlas = importlib.import_module("nightsky_atlas.build.atlas")
    original = atlas.optimize_labels

    def apply_rule(labels, scene, transform, style, **kwargs):
        result = original(labels, scene, transform, style, **kwargs)
        charts = CHARTS[edition] if batch is None else ADDITIONAL_BATCHES[batch]["charts"]
        if transform.chart.id not in charts:
            return result
        if style.label.source_association.ambiguity_weight != 20.0:
            raise ValueError("Ownership weight must remain 20")
        context = prepare_leader_routing_context(scene, transform, style)
        output_labels = result.labels
        baseline_issues = {
            issue.id
            for issue in validate_layout(
                output_labels, scene, transform, style, furniture=kwargs.get("furniture", ())
            ).issues
        }
        diagnostics = {key: dict(value) for key, value in result.label_diagnostics.items()}
        decisions = []
        for label in sorted(result.labels, key=lambda item: (-item.priority, item.id)):
            if (
                not label.id.startswith("label:dso:")
                or label.hidden
                or label.locked
                or label.leader_line
            ):
                continue
            signal = signals(label, diagnostics.get(label.id, {}))
            decision = {"label_id": label.id, "text": label.text, **signal}
            decisions.append(decision)
            if not signal["long"] or not signal["ambiguous"]:
                decision["result"] = "short_label" if not signal["long"] else "clear_association"
                continue
            proposed = tuple(
                replace(item, leader_line=True, leader_line_reason="research_targeted_long_label")
                if item.id == label.id
                else item
                for item in output_labels
            )
            updated = next(item for item in proposed if item.id == label.id)
            route = leader_line_for(updated, proposed, scene, transform, style, context=context)
            if route is None:
                decision["result"] = "no_safe_route_at_current_position"
                continue
            length = math.hypot(
                route.end.x_mm - route.start.x_mm, route.end.y_mm - route.start.y_mm
            )
            decision["length_mm"] = length
            if length > RULE["max_line_length_mm"]:
                decision["result"] = "line_too_long"
                continue
            before = resolve_leader_lines(output_labels, scene, transform, style, context=context)
            after = resolve_leader_lines(proposed, scene, transform, style, context=context)
            if (
                len(after) != sum(item.leader_line for item in proposed)
                or tuple(item for item in after if item.label_id != label.id) != before
            ):
                decision["result"] = "crossing_or_existing_route_changed"
                continue
            issues = {
                issue.id
                for issue in validate_layout(
                    proposed, scene, transform, style, furniture=kwargs.get("furniture", ())
                ).issues
            }
            if issues - baseline_issues:
                decision["result"] = "new_hard_issue"
                continue
            output_labels = proposed
            decision.update(result="added", route=asdict(route))
            diagnostics[label.id].update(
                leader_line_used=True,
                leader_line_length_mm=length,
                leader_line_reason="research_targeted_long_label",
                research_note=(
                    "Line added after optimization; other costs describe original placement."
                ),
            )
        experiment.write_json(
            output / "decisions" / f"{transform.chart.id}.json",
            {
                "chart_id": transform.chart.id,
                "decisions": decisions,
                "counts": dict(Counter(item["result"] for item in decisions)),
                "baseline_hard_issue_ids": sorted(baseline_issues),
            },
        )
        metrics = dict(result.metrics)
        metrics["research_post_optimization"] = "targeted_lines; original optimizer costs retained"
        return replace(result, labels=output_labels, label_diagnostics=diagnostics, metrics=metrics)

    try:
        if variant == "trial":
            atlas.optimize_labels = apply_rule
        experiment.build(output, edition, variant, batch=batch)
    finally:
        atlas.optimize_labels = original


def previously_reviewed_targets() -> set[str]:
    paths = list((ROOT / "tools/label_review").glob("cases*.json"))
    paths += list((ROOT / "build/label-review").glob("*/cases.json"))
    return {
        case["object_id"]
        for path in paths
        for case in json.loads(path.read_text()).get("cases", [])
    }


def curate(output: Path) -> None:
    if (output / "cases.json").exists():
        raise ValueError("Case set is already frozen")
    exposed = previously_reviewed_targets()
    cases, page_checks, rejected = [], [], Counter()
    for edition, charts in CHARTS.items():
        changed, controls = [], []
        batch_charts = [(output, chart) for chart in charts]
        batch_charts += [
            (output / name, chart)
            for name, batch in ADDITIONAL_BATCHES.items()
            if batch["edition"] == edition
            for chart in batch["charts"]
        ]
        for render_root, chart in batch_charts:
            pages = []
            for variant in ("baseline", "trial"):
                directory = render_root / variant / edition
                page = json.loads(
                    (directory / "charts" / chart / "research-layout.json").read_text()
                )
                page["atlas_directory"] = str(directory)
                pages.append(page)
            left, right = pages
            for key in ("chart", "page", "mm_per_degree", "source_geometries", "printed_stars"):
                if left[key] != right[key]:
                    raise ValueError(f"Chart content changed: {chart}/{key}")
            new_issues = {i["id"] for i in right["issues"]} - {i["id"] for i in left["issues"]}
            if new_issues:
                raise ValueError(f"New hard issues: {chart}/{new_issues}")
            changed_ids = []
            for a, b in zip(left["labels"], right["labels"], strict=True):
                differences = experiment.changed_paths(a, b)
                if differences:
                    if differences != ["leader_line", "leader_line_reason"]:
                        raise ValueError(f"Unexpected change: {chart}/{a['id']}/{differences}")
                    changed_ids.append(a["id"])
            page_checks.append(
                {
                    "chart_id": chart,
                    "baseline_hard_issues": len(left["issues"]),
                    "trial_hard_issues": len(right["issues"]),
                    "added_line_ids": changed_ids,
                    "new_hard_issues": [],
                }
            )
            for item in left["labels"]:
                if not item["id"].startswith("label:dso:") or item["hidden"]:
                    continue
                source = next(
                    (s for s in left["source_geometries"] if s["id"] == item["target_id"]), None
                )
                if source is None:
                    continue
                if not experiment.isolated_target(source, left) and item["id"] not in changed_ids:
                    continue
                if item["target_id"] in exposed:
                    rejected["previously_presented_target"] += 1
                    continue
                label = Label.from_dict(item)
                signal = signals(label, left["label_diagnostics"].get(label.id, {}))
                entry = (chart, label.id, left, right, signal)
                if label.id in changed_ids:
                    changed.append(entry)
                elif not signal["long"] or not signal["ambiguous"]:
                    controls.append(entry)
        used_charts = set()
        for chart, label_id, left, right, signal in sorted(
            changed, key=lambda row: (row[0], row[1])
        ):
            if chart in used_charts or label_id.removeprefix("label:dso:") in exposed:
                continue
            case = experiment.make_case(output, edition, left, right, label_id, False)
            if case is not None:
                source = next(s for s in left["source_geometries"] if s["id"] == case["object_id"])
                case["accuracy_evaluable"] = experiment.isolated_target(source, left)
                if not case["accuracy_evaluable"]:
                    case["research"]["accuracy_note"] = (
                        "Large symbol or nearby/interior stars: preference only, no click scoring."
                    )
                case["research"]["rule_signals"] = signal
                cases.append(case)
                exposed.add(case["object_id"])
                used_charts.add(chart)
            if len(used_charts) == 2:
                break
        for _chart, label_id, left, right, signal in sorted(
            controls, key=lambda row: (not row[4]["long"], row[0], row[1])
        ):
            if label_id.removeprefix("label:dso:") in exposed:
                continue
            case = experiment.make_case(output, edition, left, right, label_id, True)
            if case is not None:
                case["research"]["rule_signals"] = signal
                cases.append(case)
                exposed.add(case["object_id"])
                break
    experiment.write_json(
        output / "curation.json",
        {
            "page_checks": page_checks,
            "rejections": dict(rejected),
            "case_count": len(cases),
            "changed_count": sum(not case["control"] for case in cases),
            "cases": [{"id": case["case_id"], "control": case["control"]} for case in cases],
        },
    )
    if sum(not case["control"] for case in cases) < 2:
        raise ValueError("Too few safely clickable changed cases; report the limitation")
    meta = json.loads((output / "experiment.json").read_text())
    experiment.write_json(
        output / "cases.json",
        {
            "experiment_id": meta["experiment_id"],
            "seed": meta["seed"],
            "dpi": 300,
            "require_calibration": True,
            "cases": cases,
        },
    )
    server.load_manifest(output / "cases.json")
    long_lines.contact_sheet(output, cases)
    checksums = {
        variant["image"]: hashlib.sha256(
            (Path(__file__).parent / variant["image"]).read_bytes()
        ).hexdigest()
        for case in cases
        for variant in case["variants"]
    }
    experiment.write_json(output / "image-sha256.json", checksums)
    print(
        f"Ready: {len(cases)} cases, {sum(not case['control'] for case in cases)} changes",
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Research-only deterministic targeted leader rule")
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTPUT)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("prepare")
    render = commands.add_parser("build")
    render.add_argument("--edition", choices=tuple(CHARTS), required=True)
    render.add_argument("--variant", choices=("baseline", "trial"), required=True)
    render.add_argument("--batch", choices=tuple(ADDITIONAL_BATCHES))
    commands.add_parser("curate")
    args = parser.parse_args()
    output = args.outdir.resolve()
    if args.command == "prepare":
        prepare(output)
    elif args.command == "build":
        build(output, args.edition, args.variant, args.batch)
    else:
        curate(output)


if __name__ == "__main__":
    main()
