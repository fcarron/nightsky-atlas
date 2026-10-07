from __future__ import annotations

import argparse
import importlib
import json
import shutil
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import make_ownership_experiment as experiment

from nightsky_atlas.layout.validation import validate_layout


def traced_optimize(original, output: Path):
    optimizer = importlib.import_module("nightsky_atlas.layout.optimizer")

    def optimize(labels, scene, transform, style, **kwargs):
        if transform.chart.id not in {"pocket-012", "pocket-025"}:
            return original(labels, scene, transform, style, **kwargs)
        stages = []
        furniture = tuple(kwargs.get("furniture", ()))

        def record(name, placed):
            verdict = validate_layout(placed, scene, transform, style, furniture=furniture)
            stages.append(
                {
                    "stage": name,
                    "issues": [asdict(issue) for issue in verdict.issues],
                    "placements": {
                        label.id: label.selected_candidate_id
                        for label in placed
                        if not label.hidden
                    },
                }
            )

        def wrap(name, function):
            def run(*args, **stage_kwargs):
                stage_labels = args[0]
                before = args[1]
                record(
                    name + ":before",
                    tuple(
                        label.with_placement(
                            before.get(label.id), hidden=before.get(label.id) is None
                        )
                        for label in stage_labels
                    ),
                )
                result = function(*args, **stage_kwargs)
                placements = result if name == "_local_repair" else result[0]
                record(
                    name + ":after",
                    tuple(
                        label.with_placement(
                            placements.get(label.id), hidden=placements.get(label.id) is None
                        )
                        for label in stage_labels
                    ),
                )
                return result

            return run

        originals = {
            name: getattr(optimizer, name)
            for name in ("_local_repair", "_joint_dso_optimize", "_repair_dso_hard_conflicts")
        }
        try:
            for name, function in originals.items():
                setattr(optimizer, name, wrap(name, function))
            result = original(labels, scene, transform, style, **kwargs)
        finally:
            for name, function in originals.items():
                setattr(optimizer, name, function)
        record("optimizer:final", result.labels)
        sources = optimizer.dso_source_geometries(scene, transform, style)
        symbols = optimizer._build_symbol_index(optimizer._symbol_circles(scene, transform, style))
        stars = optimizer._star_circles(scene, transform, style)
        stars_index = optimizer._build_star_index(stars)
        occupied = optimizer._build_placed_index(result.labels, style)
        empty = optimizer._build_placed_index((), style)
        involved = {
            element
            for issue in stages[-1]["issues"]
            for element in issue["element_ids"]
            if element.startswith("label:")
        }
        candidates = {}
        for label in result.labels:
            if label.id not in involved:
                continue
            rows = []
            for candidate in label.candidates:

                def rejection(index, label=label, candidate=candidate):
                    return optimizer._candidate_rejection_reason(
                        label,
                        candidate,
                        index,
                        symbols,
                        stars_index,
                        stars,
                        optimizer._printable(transform),
                        style,
                        furniture=furniture,
                        source_geometries=sources,
                    )

                rows.append(
                    {
                        "id": candidate.id,
                        "selected": candidate.id == label.selected_candidate_id,
                        "static_rejection": rejection(empty),
                        "rejection_with_neighbours": rejection(occupied),
                    }
                )
            candidates[label.id] = {
                "candidate_count": len(rows),
                "static_rejections": dict(
                    Counter(row["static_rejection"] or "valid" for row in rows)
                ),
                "with_neighbour_rejections": dict(
                    Counter(row["rejection_with_neighbours"] or "valid" for row in rows)
                ),
                "candidates": rows,
            }
        experiment.write_json(
            output / f"{transform.chart.id}-trace.json",
            {
                "chart_id": transform.chart.id,
                "weight": style.label.source_association.ambiguity_weight,
                "stages": stages,
                "unresolved_candidate_audit": candidates,
                "repair_limits": style.label.dso_placement.model_dump(mode="json"),
            },
        )
        return result

    return optimize


def main() -> None:
    parser = argparse.ArgumentParser(description="Research-only optimizer stage trace")
    parser.add_argument("--from-experiment", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    if args.outdir.exists():
        raise ValueError("Use a fresh diagnostic directory")
    shutil.copytree(args.from_experiment / "config", args.outdir / "config")
    metadata = json.loads((args.from_experiment / "experiment.json").read_text())
    metadata.update(
        {
            "charts": {"pocket": ["pocket-012", "pocket-025"]},
            "additional_batches": {},
            "diagnostic_parent": str(args.from_experiment),
            "source_sha256": experiment.source_fingerprints(),
        }
    )
    experiment.write_json(args.outdir / "experiment.json", metadata)
    atlas = importlib.import_module("nightsky_atlas.build.atlas")
    original = atlas.optimize_labels
    try:
        for variant in ("baseline", "trial"):
            atlas.optimize_labels = traced_optimize(original, args.outdir / "traces" / variant)
            experiment.build(args.outdir, "pocket", variant)
    finally:
        atlas.optimize_labels = original


if __name__ == "__main__":
    main()
