from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from nightsky_atlas.build.chart import build_chart_context
from nightsky_atlas.chart.presentation import presentation_from_edition
from nightsky_atlas.layout.leader_lines import resolve_leader_lines
from nightsky_atlas.layout.models import Label
from nightsky_atlas.layout.validation import validate_layout
from nightsky_atlas.render.cairo import render_chart
from nightsky_atlas.render.furniture import furniture_obstacles

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "build" / "leader-followup-2026-10-01"
CHANGES = {
    ("deep", "deep-201"): {
        "label:dso:NGC4266": "label:dso:NGC4266:WNW:4",
    },
    ("standard", "standard-027"): {
        "label:dso:IC3668": "label:dso:IC3668:WSW:4",
        "label:dso:IC3669": "label:dso:IC3669:ESE:4",
    },
}


def main() -> None:
    for (edition, chart_id), changes in CHANGES.items():
        source = OUTPUT / f"diagnostic-{edition}" / edition / "charts" / chart_id / "chart.json"
        layout = json.loads(source.read_text(encoding="utf-8"))
        labels = tuple(Label.from_dict(item) for item in layout["labels"])
        context = build_chart_context(
            atlas_path=ROOT / "atlas" / f"{edition}.yaml",
            style_path=ROOT / "styles" / f"{edition}.yaml",
            chart_id=chart_id,
            star_store=ROOT / "data" / "processed" / "stars" / "tycho2.sqlite",
        )
        presentation = presentation_from_edition(
            context.definition, context.atlas.resolved_edition()
        )
        furniture = furniture_obstacles(
            context.transform, context.definition, context.style, presentation
        )
        baseline_issues = validate_layout(
            labels, context.scene, context.transform, context.style, furniture=furniture
        ).issues
        if baseline_issues:
            raise ValueError(f"{chart_id}: baseline has {len(baseline_issues)} hard issues")
        found: set[str] = set()
        updated = []
        for label in labels:
            candidate_id = changes.get(label.id)
            if candidate_id is None:
                updated.append(label)
                continue
            if label.candidate(candidate_id) is None:
                raise ValueError(f"{chart_id}: invalid candidate {candidate_id}")
            found.add(label.id)
            updated.append(
                replace(
                    label,
                    selected_candidate_id=candidate_id,
                    leader_line=True,
                    leader_line_reason="local_blind_experiment",
                )
            )
        if found != set(changes):
            raise ValueError(f"{chart_id}: missing labels {sorted(set(changes) - found)}")
        variant = tuple(updated)
        variant_issues = validate_layout(
            variant, context.scene, context.transform, context.style, furniture=furniture
        ).issues
        if variant_issues:
            raise ValueError(f"{chart_id}: variant has {len(variant_issues)} hard issues")
        resolved_count = len(
            resolve_leader_lines(variant, context.scene, context.transform, context.style)
        )
        if resolved_count != sum(label.leader_line for label in variant):
            raise ValueError(f"{chart_id}: one or more leader lines cannot be routed")
        target = OUTPUT / "pages" / edition / chart_id
        target.mkdir(parents=True, exist_ok=True)
        for name, current in (("baseline", labels), ("local-lines", variant)):
            render_chart(
                context.scene,
                context.transform,
                context.style,
                labels=current,
                presentation=presentation,
                pdf_path=target / f"{name}.pdf",
                png_path=target / f"{name}.png",
                png_dpi=300,
            )
        report = {
            "chart_id": chart_id,
            "source_layout": str(source.relative_to(ROOT)),
            "baseline_hard_issues": len(baseline_issues),
            "variant_hard_issues": len(variant_issues),
            "changed_labels": {
                label_id: {
                    "baseline_candidate": next(
                        label.selected_candidate_id for label in labels if label.id == label_id
                    ),
                    "variant_candidate": candidate_id,
                    "leader_line": True,
                }
                for label_id, candidate_id in changes.items()
            },
        }
        (target / "changes.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"{chart_id}: {len(changes)} labels changed, hard issues 0 -> {target}")


if __name__ == "__main__":
    main()
