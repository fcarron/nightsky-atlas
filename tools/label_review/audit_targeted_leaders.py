from __future__ import annotations

import argparse
import importlib
import json
import subprocess
from dataclasses import asdict, replace
from pathlib import Path

import cairo
import make_ownership_experiment as experiment

from nightsky_atlas.build.progress import Progress
from nightsky_atlas.layout.leader_lines import resolve_leader_lines
from nightsky_atlas.layout.optimizer import layout_hash
from nightsky_atlas.layout.validation import validate_layout

ROOT = experiment.ROOT
DEFAULT_OUTPUT = ROOT / "build/targeted-leaders-2026-10-07"
ATLAS = importlib.import_module("nightsky_atlas.build.atlas")
ORIGINAL_INIT = ATLAS._init_chart_worker


def install_hooks(output: Path) -> None:
    optimizer = importlib.import_module("nightsky_atlas.layout.optimizer")
    original = optimizer.add_targeted_dso_leaders
    original_render = ATLAS.render_chart
    pending = {}

    def render_with_comparison(scene, transform, style, **kwargs):
        original_render(scene, transform, style, **kwargs)
        before = pending.pop(transform.chart.id, None)
        if before is None:
            return
        directory = output / "line-audit" / transform.chart.id
        for variant, placed in (("before", before), ("after", kwargs["labels"])):
            options = {**kwargs, "labels": placed, "pdf_path": directory / f"{variant}.pdf"}
            options["png_path"] = None
            original_render(scene, transform, style, **options)
        path = directory / "audit.json"
        data = json.loads(path.read_text())
        data["comparison_render_context"] = "atlas_page"
        experiment.write_json(path, data)

    def audit(labels, diagnostics, scene, transform, style, *, furniture=()):
        result = original(labels, diagnostics, scene, transform, style, furniture=furniture)
        baseline = validate_layout(labels, scene, transform, style, furniture=furniture)
        after = validate_layout(result.labels, scene, transform, style, furniture=furniture)
        old_issues = {issue.id for issue in baseline.issues}
        new_issues = {issue.id for issue in after.issues}
        if new_issues - old_issues:
            raise ValueError(f"New hard issues on {transform.chart.id}")
        changed = []
        for before, updated in zip(labels, result.labels, strict=True):
            normalized = replace(
                updated,
                leader_line=before.leader_line,
                leader_line_reason=before.leader_line_reason,
            )
            if normalized != before:
                raise ValueError(f"Position/content changed on {transform.chart.id}: {before.id}")
            if before != updated:
                changed.append(updated.id)
        directory = output / "line-audit" / transform.chart.id
        experiment.write_json(
            directory / "audit.json",
            {
                "chart_id": transform.chart.id,
                "baseline_hard_issue_ids": sorted(old_issues),
                "final_hard_issue_ids": sorted(new_issues),
                "new_hard_issue_ids": sorted(new_issues - old_issues),
                "baseline_hash": layout_hash(labels),
                "final_hash": layout_hash(result.labels),
                "changed_ids": changed,
                "counts": result.counts,
                "decisions": result.decisions,
                "page": asdict(transform.page),
            },
        )
        if changed:
            routes = {
                route.label_id: route
                for route in resolve_leader_lines(result.labels, scene, transform, style)
            }
            experiment.write_json(
                directory / "changed-labels.json",
                [
                    {
                        "label_id": label.id,
                        "text": label.text,
                        "bounds": asdict(label.effective_candidate().bounds),
                        "route": asdict(routes[label.id]),
                    }
                    for label in result.labels
                    if label.id in changed
                ],
            )
            pending[transform.chart.id] = labels
        return result

    optimizer.add_targeted_dso_leaders = audit
    ATLAS.render_chart = render_with_comparison


def init_worker(shared) -> None:
    ORIGINAL_INIT(shared)
    install_hooks(shared.outroot)


def build(output: Path, edition: str, jobs: int) -> None:
    if (output / edition / "manifest.json").exists():
        raise ValueError("Completed atlas exists; choose a new output directory")
    ATLAS._init_chart_worker = init_worker
    install_hooks(output / edition)
    result = ATLAS.build_atlas(
        atlas_path=ROOT / "atlas" / f"{edition}.yaml",
        style_path=ROOT / "styles" / f"{edition}.yaml",
        outdir=output,
        star_store=ROOT / "data/processed/stars/tycho2.sqlite",
        optimize=True,
        jobs=jobs,
        render_png=False,
        write_front_matter=False,
        write_overviews=False,
        write_draft_report=True,
        progress=Progress(),
    )
    print(result.combined_pdf, flush=True)


def summarize(output: Path) -> None:
    rows, totals, crops = [], {}, []
    for edition in ("pocket", "standard", "deep"):
        manifest = json.loads((output / edition / "manifest.json").read_text())
        audits = [
            json.loads(path.read_text())
            for path in sorted((output / edition / "line-audit").glob("*/audit.json"))
        ]
        expected = set(manifest["main_chart_ids"]) | set(manifest["detail_chart_ids"])
        actual = {row["chart_id"] for row in audits}
        if expected != actual:
            raise ValueError(
                f"Audit coverage mismatch: {edition}: {expected - actual}, {actual - expected}"
            )
        totals[edition] = {
            "main_charts": manifest["main_chart_count"],
            "detail_charts": manifest["detail_chart_count"],
            "added_lines": sum(len(row["changed_ids"]) for row in audits),
            "changed_pages": sum(bool(row["changed_ids"]) for row in audits),
            "baseline_hard_issues": sum(len(row["baseline_hard_issue_ids"]) for row in audits),
            "new_hard_issues": sum(len(row["new_hard_issue_ids"]) for row in audits),
        }
        for row in audits:
            if not row["changed_ids"]:
                continue
            if row.get("comparison_render_context") != "atlas_page":
                raise ValueError(f"Comparison is missing atlas context: {row['chart_id']}")
            directory = output / edition / "line-audit" / row["chart_id"]
            changes = json.loads((directory / "changed-labels.json").read_text())
            factor = 200 / 25.4
            images = []
            for variant in ("before", "after"):
                target = directory / variant
                subprocess.run(
                    [
                        "pdftoppm",
                        "-singlefile",
                        "-png",
                        "-r",
                        "200",
                        str(target.with_suffix(".pdf")),
                        str(target),
                    ],
                    check=True,
                )
                images.append(cairo.ImageSurface.create_from_png(str(target.with_suffix(".png"))))
            for change in changes:
                bounds = change["bounds"]
                route = change["route"]
                center_x = (bounds["left_mm"] + bounds["width_mm"] / 2 + route["start"]["x_mm"]) / 2
                center_y = (bounds["top_mm"] + bounds["height_mm"] / 2 + route["start"]["y_mm"]) / 2
                width_mm = max(60.0, bounds["width_mm"] + 14.0)
                height_mm = 45.0
                x = round(
                    max(0.0, min(center_x - width_mm / 2, row["page"]["width_mm"] - width_mm))
                    * factor
                )
                y = round(
                    max(0.0, min(center_y - height_mm / 2, row["page"]["height_mm"] - height_mm))
                    * factor
                )
                width, height = round(width_mm * factor), round(height_mm * factor)
                paths = []
                for variant, image in zip(("before", "after"), images, strict=True):
                    crop = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
                    cr = cairo.Context(crop)
                    cr.set_source_surface(image, -x, -y)
                    cr.paint()
                    name = change["label_id"].replace(":", "-").replace("/", "-")
                    path = directory / f"{name}-{variant}-crop.png"
                    crop.write_to_png(str(path))
                    paths.append(str(path.relative_to(output)))
                crops.append(
                    {
                        "edition": edition,
                        "chart_id": row["chart_id"],
                        "text": change["text"],
                        "images": paths,
                        "print_size_mm": [width_mm, height_mm],
                    }
                )
            rows.append({"edition": edition, **row})
    experiment.write_json(
        output / "audit-summary.json", {"editions": totals, "changed_pages": rows, "crops": crops}
    )
    write_overview(output, totals, crops)
    print(json.dumps(totals, indent=2), flush=True)


def write_overview(output: Path, totals: dict, crops: list[dict]) -> None:
    import html

    parts = [
        "<!doctype html><meta charset='utf-8'><title>Neue Führungslinien</title>",
        "<style>body{font-family:sans-serif;margin:2em}section{break-inside:avoid;margin:2em 0}"
        "img{max-width:46%;height:auto;border:1px solid #ddd}pre{white-space:pre-wrap}</style>",
        "<h1>Neue gezielte Führungslinien</h1><p>Links bisher, rechts mit neuer Regel. "
        "Identische Positionen und Karteninhalte. Ausschnitte verwenden die reguläre "
        "Atlas-Seitenrenderung einschließlich Navigation und Symbolüberlagerungen.</p>",
        "<pre>" + html.escape(json.dumps(totals, indent=2)) + "</pre>",
    ]
    for crop in crops:
        parts.append(
            "<section><h2>"
            + html.escape(crop["chart_id"] + " / " + crop["text"])
            + "</h2>"
            + "".join(
                "<img src='" + html.escape(path, quote=True) + "'>" for path in crop["images"]
            )
            + "</section>"
        )
    (output / "new-lines.html").write_text("\n".join(parts))
    pdf = cairo.PDFSurface(str(output / "new-lines.pdf"), 297 * 72 / 25.4, 210 * 72 / 25.4)
    cr = cairo.Context(pdf)
    for crop in crops:
        cr.set_source_rgb(0, 0, 0)
        cr.set_font_size(12)
        cr.move_to(30, 30)
        cr.show_text(crop["chart_id"] + " / " + crop["text"] + " — before / after")
        for column, path in enumerate(crop["images"]):
            image = cairo.ImageSurface.create_from_png(str(output / path))
            cr.save()
            cr.translate(30 + column * 380, 70)
            scale = crop["print_size_mm"][0] * 72 / 25.4 / image.get_width()
            cr.scale(scale, scale)
            cr.set_source_surface(image, 0, 0)
            cr.paint()
            cr.restore()
        pdf.show_page()
    pdf.finish()


def main() -> None:
    parser = argparse.ArgumentParser(description="Atlas-wide targeted leader audit")
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTPUT)
    commands = parser.add_subparsers(dest="command", required=True)
    render = commands.add_parser("build")
    render.add_argument("--edition", choices=("pocket", "standard", "deep"), required=True)
    render.add_argument("--jobs", type=int, default=4)
    commands.add_parser("summarize")
    args = parser.parse_args()
    output = args.outdir.resolve()
    if args.command == "build":
        build(output, args.edition, args.jobs)
    else:
        summarize(output)


if __name__ == "__main__":
    main()
