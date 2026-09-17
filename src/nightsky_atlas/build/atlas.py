"""Complete atlas build orchestration.

Pipeline: chart definitions -> scenes -> deterministic layouts -> validation
-> optional AI review -> per-page artifacts and a combined vector PDF, plus a
build manifest (``AGENTS.md`` M15).
"""

from __future__ import annotations

import datetime
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cairo

from nightsky_atlas.atlas.config import (
    AtlasConfig,
    StyleConfig,
    load_atlas_config,
    load_style_config,
)
from nightsky_atlas.atlas.tiling import TilingSpec, tile_sky, with_neighbours
from nightsky_atlas.build.chart import build_chart_context
from nightsky_atlas.catalog.star_names import (
    DEFAULT_FIXTURE_DIR as STAR_NAMES_FIXTURE_DIR,
)
from nightsky_atlas.catalog.star_names import (
    load_star_names,
)
from nightsky_atlas.chart.models import ChartDefinition
from nightsky_atlas.layout.labels import build_labels
from nightsky_atlas.layout.optimizer import layout_cost, layout_hash, optimize_labels
from nightsky_atlas.layout.overrides import (
    OverridesLibrary,
    apply_overrides,
    load_override_library,
)
from nightsky_atlas.layout.validation import validate_layout
from nightsky_atlas.render.cairo import draw_chart_page, render_chart
from nightsky_atlas.render.text import draw_centered_text, draw_text
from nightsky_atlas.units import mm_to_pt

__all__ = [
    "AtlasBuildResult",
    "ChartPageResult",
    "build_atlas",
    "chart_definitions",
]


@dataclass(frozen=True, slots=True)
class ChartPageResult:
    """Per-page diagnostics for an atlas build."""

    chart_id: str
    star_count: int
    dso_count: int
    label_count: int
    placed_count: int
    hidden_count: int
    overrides_applied: int
    hard_issues: int
    cost_before: float
    cost_after: float
    layout_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "chart_id": self.chart_id,
            "star_count": self.star_count,
            "dso_count": self.dso_count,
            "label_count": self.label_count,
            "placed_count": self.placed_count,
            "hidden_count": self.hidden_count,
            "overrides_applied": self.overrides_applied,
            "hard_issues": self.hard_issues,
            "cost_before": self.cost_before,
            "cost_after": self.cost_after,
            "layout_hash": self.layout_hash,
        }


@dataclass(frozen=True, slots=True)
class AtlasBuildResult:
    """Result of an atlas build."""

    atlas_id: str
    pages: tuple[ChartPageResult, ...]
    combined_pdf: Path
    manifest_path: Path

    @property
    def total_hard_issues(self) -> int:
        return sum(page.hard_issues for page in self.pages)


def chart_definitions(atlas: AtlasConfig) -> tuple[ChartDefinition, ...]:
    """Return the chart definitions for an atlas edition."""
    if atlas.tiling is not None:
        charts = tile_sky(atlas.id, TilingSpec.from_config(atlas.tiling))
        return with_neighbours(charts)
    return tuple(chart.to_definition(atlas_id=atlas.id) for chart in atlas.charts)


def _git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _data_sources() -> list[dict[str, Any]]:
    manifest_paths = [
        Path("data/processed/stars/tycho2.manifest.json"),
        Path("data/processed/dso/openngc.manifest.json"),
    ]
    sources = []
    for path in manifest_paths:
        if path.exists():
            sources.append(json.loads(path.read_text(encoding="utf-8")))
    return sources


def _draw_front_matter(
    cr: cairo.Context[cairo.Surface],
    atlas: AtlasConfig,
    style: StyleConfig,
    chart_count: int,
) -> None:
    page = atlas.page.to_geometry()
    family = style.label.font_family
    draw_centered_text(
        cr,
        f"NightSky Atlas - {atlas.id}",
        mm_to_pt(page.width_mm / 2.0),
        mm_to_pt(page.margin_mm + 12.0),
        family,
        16.0,
    )
    lines = [
        f"{chart_count} charts",
        f"Stellar limit: magnitude {atlas.stellar_limit_magnitude}",
    ]
    for index, line in enumerate(lines):
        draw_text(
            cr,
            line,
            mm_to_pt(page.margin_mm + 8.0),
            mm_to_pt(page.margin_mm + 30.0 + index * 5.0),
            family,
            9.0,
        )
    legend = (
        "Symbols: solid dot = star; ellipse = galaxy; "
        "dashed circle = open cluster; circle+cross = globular cluster; "
        "circle+spokes = planetary nebula; dashed square = nebula."
    )
    draw_text(
        cr,
        legend,
        mm_to_pt(page.margin_mm + 8.0),
        mm_to_pt(page.height_mm - page.margin_mm - 10.0),
        family,
        7.0,
    )


def build_atlas(
    *,
    atlas_path: str | Path,
    style_path: str | Path,
    outdir: str | Path,
    star_store: str | Path | None = None,
    stars_csv: str | Path | None = None,
    dsos_path: str | Path | None = None,
    constellations_dir: str | Path | None = None,
    outlines_dir: str | Path | None = None,
    star_names_dir: str | Path | None = None,
    observing_lists_dir: str | Path | None = None,
    observing_config_path: str | Path | None = None,
    overrides_path: str | Path | None = None,
    chart_ids: tuple[str, ...] | None = None,
    limit: int | None = None,
    optimize: bool = True,
    render_png: bool = True,
    png_dpi: float = 150.0,
    write_front_matter: bool = True,
) -> AtlasBuildResult:
    """Build an atlas subset or the whole atlas and write a manifest."""
    atlas = load_atlas_config(atlas_path)
    style = load_style_config(style_path)
    charts = chart_definitions(atlas)
    if chart_ids is not None:
        wanted = set(chart_ids)
        charts = tuple(chart for chart in charts if chart.id in wanted)
    if limit is not None:
        charts = charts[:limit]

    library: OverridesLibrary | None = (
        load_override_library(overrides_path) if overrides_path is not None else None
    )
    applied_chart_ids: set[str] = set()

    star_names = load_star_names(
        star_names_dir if star_names_dir is not None else STAR_NAMES_FIXTURE_DIR
    )

    page = atlas.page.to_geometry()
    outroot = Path(outdir) / atlas.id
    outroot.mkdir(parents=True, exist_ok=True)
    combined_pdf = outroot / "atlas.pdf"

    surface = cairo.PDFSurface(
        str(combined_pdf), mm_to_pt(page.width_mm), mm_to_pt(page.height_mm)
    )
    context = cairo.Context(surface)
    if write_front_matter:
        _draw_front_matter(context, atlas, style, len(charts))
        surface.show_page()

    results: list[ChartPageResult] = []
    observing_lists: dict[str, object] = {}
    forced_lists: list[str] = []
    for definition in charts:
        chart_context = build_chart_context(
            atlas_path=atlas_path,
            style_path=style_path,
            definition=definition,
            star_store=star_store,
            stars_csv=stars_csv,
            dsos_path=dsos_path,
            constellations_dir=constellations_dir,
            outlines_dir=outlines_dir,
            observing_lists_dir=observing_lists_dir,
            observing_config_path=observing_config_path,
        )
        labels = build_labels(
            chart_context.scene, chart_context.transform, chart_context.style, star_names
        )
        chart_overrides = library.for_chart(definition.id) if library is not None else None
        if chart_context.observing_lists:
            observing_lists = chart_context.observing_lists
        if chart_context.selection_policy is not None:
            forced_lists = sorted(chart_context.selection_policy.forced_lists)
        if chart_overrides is not None:
            labels = apply_overrides(labels, chart_overrides)
            applied_chart_ids.add(definition.id)
        overrides_applied = len(chart_overrides) if chart_overrides is not None else 0
        cost_before = layout_cost(
            labels, chart_context.scene, chart_context.transform, chart_context.style
        )[0]
        if optimize:
            optimized = optimize_labels(
                labels, chart_context.scene, chart_context.transform, chart_context.style
            )
            labels = optimized.labels
        cost_after = layout_cost(
            labels, chart_context.scene, chart_context.transform, chart_context.style
        )[0]
        validation = validate_layout(
            labels, chart_context.scene, chart_context.transform, chart_context.style
        )

        page_dir = outroot / "charts" / definition.id
        render_chart(
            chart_context.scene,
            chart_context.transform,
            chart_context.style,
            labels=labels,
            pdf_path=page_dir / "chart.pdf",
            png_path=page_dir / "preview.png" if render_png else None,
            png_dpi=png_dpi,
        )
        draw_chart_page(
            context,
            chart_context.scene,
            chart_context.transform,
            chart_context.style,
            labels=labels,
        )
        surface.show_page()

        placed = sum(1 for label in labels if not label.hidden and label.candidates)
        results.append(
            ChartPageResult(
                chart_id=definition.id,
                star_count=chart_context.scene.star_count,
                dso_count=chart_context.scene.dso_count,
                label_count=len(labels),
                placed_count=placed,
                hidden_count=len(labels) - placed,
                overrides_applied=overrides_applied,
                hard_issues=len(validation.issues),
                cost_before=cost_before,
                cost_after=cost_after,
                layout_hash=layout_hash(labels),
            )
        )

    surface.finish()

    unused_chart_ids = (
        sorted(set(library.chart_ids()) - applied_chart_ids) if library is not None else []
    )
    manifest = {
        "atlas_id": atlas.id,
        "generated_utc": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
        "git_commit": _git_commit(),
        "config": {"atlas": str(atlas_path), "style": str(style_path)},
        "overrides": {
            "path": str(overrides_path) if overrides_path is not None else None,
            "applied_charts": sorted(applied_chart_ids),
            "unused_charts": unused_chart_ids,
        },
        "page": {
            "width_mm": page.width_mm,
            "height_mm": page.height_mm,
            "margin_mm": page.margin_mm,
        },
        "stellar_limit_magnitude": atlas.stellar_limit_magnitude,
        "dso_limit_magnitude": atlas.dso_limit_magnitude,
        "visibility": atlas.visibility.model_dump(),
        "observing_lists": {
            "lists": sorted(observing_lists),
            "forced": forced_lists,
        },
        "chart_count": len(results),
        "total_hard_issues": sum(page_result.hard_issues for page_result in results),
        "data_sources": _data_sources(),
        "pages": [page_result.to_dict() for page_result in results],
    }
    manifest_path = outroot / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    return AtlasBuildResult(
        atlas_id=atlas.id,
        pages=tuple(results),
        combined_pdf=combined_pdf,
        manifest_path=manifest_path,
    )