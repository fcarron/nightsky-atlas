"""Complete atlas build orchestration.

Pipeline: chart definitions -> scenes -> deterministic layouts -> validation
-> optional AI review -> per-page artifacts and a combined vector PDF, plus a
build manifest (``AGENTS.md`` M15).
"""

from __future__ import annotations

import datetime
import json
import math
import os
import subprocess
import tempfile
import time
from collections import deque
from collections.abc import Iterator
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, replace
from itertools import islice
from multiprocessing import get_context
from pathlib import Path
from typing import Any

import cairo

from nightsky_atlas.atlas.config import (
    AtlasConfig,
    DetailChartConfig,
    EditionConfig,
    StyleConfig,
    load_atlas_config,
    load_style_config,
)
from nightsky_atlas.atlas.directory import build_chart_directory, build_detail_chart_directory
from nightsky_atlas.atlas.index import build_atlas_index
from nightsky_atlas.atlas.observing_config import DEFAULT_CONFIG_PATH as OBSERVING_CONFIG_PATH
from nightsky_atlas.atlas.overview import OverviewMap, build_overview, hemisphere_for
from nightsky_atlas.atlas.report import build_draft_report, render_text_summary
from nightsky_atlas.atlas.tiling import (
    TilingSpec,
    chart_definitions,
    resolve_ring_counts,
)
from nightsky_atlas.build.chart import (
    DEFAULT_DOUBLE_STAR_PATH,
    OPENNGC_OUTLINE_DIR,
    ChartContext,
    ChartInputs,
    build_chart_context,
    default_dso_path,
    load_chart_inputs,
    load_star_systems,
)
from nightsky_atlas.build.preflight import (
    collect_build_inputs,
    collect_data_sources,
    validate_atlas_output,
    validate_publication_inputs,
)
from nightsky_atlas.build.progress import Progress, null_progress
from nightsky_atlas.catalog.manifest import file_sha256
from nightsky_atlas.catalog.models import DeepSkyObject, DsoType, Star
from nightsky_atlas.catalog.observing_lists import (
    DEFAULT_FIXTURE_DIR as OBSERVING_LISTS_FIXTURE_DIR,
)
from nightsky_atlas.catalog.observing_lists import build_membership_index
from nightsky_atlas.catalog.sample import load_sample_stars
from nightsky_atlas.catalog.selection import select_dso
from nightsky_atlas.catalog.star_names import (
    DEFAULT_FIXTURE_DIR as STAR_NAMES_FIXTURE_DIR,
)
from nightsky_atlas.catalog.star_names import (
    StarName,
    load_star_names,
)
from nightsky_atlas.catalog.store import QueryBox, StarStore
from nightsky_atlas.catalog.systems import StarSystem
from nightsky_atlas.chart.models import ChartDefinition
from nightsky_atlas.chart.page import PageTransform
from nightsky_atlas.chart.presentation import (
    ChartPresentation,
    presentation_from_edition,
)
from nightsky_atlas.layout.collision import LayoutIssue
from nightsky_atlas.layout.labels import build_labels
from nightsky_atlas.layout.models import Label
from nightsky_atlas.layout.optimizer import layout_cost, layout_hash, optimize_labels
from nightsky_atlas.layout.overrides import (
    OverridesLibrary,
    apply_overrides,
    load_override_library,
)
from nightsky_atlas.layout.selection import select_labels
from nightsky_atlas.layout.validation import ValidationResult, validate_layout
from nightsky_atlas.render.atlas_index import draw_atlas_index_pages
from nightsky_atlas.render.cairo import draw_chart_page, render_chart
from nightsky_atlas.render.chart_directory import (
    draw_chart_directory_pages,
    draw_detail_chart_directory_pages,
)
from nightsky_atlas.render.detail_markers import DetailMapMarker, build_detail_marker
from nightsky_atlas.render.front_matter import (
    draw_credits_page,
    draw_field_guide,
    draw_introduction,
)
from nightsky_atlas.render.furniture import furniture_obstacles
from nightsky_atlas.render.overview import (
    LocatorInset,
    draw_overview_page,
    draw_overview_spread_page,
)
from nightsky_atlas.render.pdf_navigation import PdfNavigation
from nightsky_atlas.scene.models import ChartScene, SceneDso
from nightsky_atlas.units import mm_to_pt

__all__ = [
    "AtlasBuildResult",
    "ChartPageResult",
    "build_atlas",
    "chart_definitions",
]


def _style_with_star_profile(base_style: StyleConfig, star_profile: StyleConfig) -> StyleConfig:
    """Use one edition's star appearance while preserving the base DSO style."""
    return base_style.model_copy(
        update={
            "star": star_profile.star,
            "double_stars": star_profile.double_stars,
            "label": base_style.label.model_copy(
                update={"star_labels": star_profile.label.star_labels}
            ),
        }
    )


def _detail_presentation(
    detail: DetailChartConfig,
    *,
    edition: EditionConfig,
    main_charts: tuple[ChartDefinition, ...],
    stellar_limit_magnitude: float,
) -> ChartPresentation:
    parents = {chart.id: chart for chart in main_charts}
    parent = parents[detail.parent_chart_id]
    parent_code = presentation_from_edition(parent, edition).chart_code
    field = f"{detail.width_deg:g}° × {detail.height_deg:g}°"
    return ChartPresentation(
        edition_name=edition.name,
        edition_code=edition.code,
        chart_index=None,
        internal_chart_id=detail.code,
        page_heading=f"{detail.code} · {detail.name}",
        page_footer=(
            f"{edition.name} · {detail.code} · {detail.mm_per_degree:g} mm/° · "
            f"stars to {stellar_limit_magnitude:g} · {field} · Main chart {parent_code}"
        ),
        page_footer_target=parent_code,
    )


@dataclass(frozen=True, slots=True)
class _PreparedDetail:
    context: ChartContext
    style: StyleConfig
    labels: tuple[Label, ...]
    cost_before: float
    cost_after: float
    validation: ValidationResult


@dataclass(frozen=True, slots=True)
class ChartPageResult:
    """Per-page diagnostics for an atlas build."""

    chart_id: str
    star_count: int
    dso_count: int
    star_system_count: int
    label_count: int
    placed_count: int
    hidden_count: int
    overrides_applied: int
    hard_issues: int
    cost_before: float
    cost_after: float
    layout_hash: str
    neighbours: tuple[tuple[str, str], ...] = ()
    fallback_label_ids: tuple[tuple[str, tuple[str, ...]], ...] = ()
    layout_issues: tuple[dict[str, Any], ...] = ()
    permitted_suppressions: tuple[dict[str, Any], ...] = ()
    fallback_candidate_label_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        primary_neighbours: dict[str, str] = {}
        for direction, neighbour in self.neighbours:
            primary_neighbours.setdefault(direction, neighbour)
        return {
            "chart_id": self.chart_id,
            "star_count": self.star_count,
            "dso_count": self.dso_count,
            "star_system_count": self.star_system_count,
            "label_count": self.label_count,
            "placed_count": self.placed_count,
            "hidden_count": self.hidden_count,
            "overrides_applied": self.overrides_applied,
            "hard_issues": self.hard_issues,
            "cost_before": self.cost_before,
            "cost_after": self.cost_after,
            "layout_hash": self.layout_hash,
            "fallback_label_ids": {
                code: list(label_ids) for code, label_ids in self.fallback_label_ids
            },
            "fallback_label_count": sum(len(label_ids) for _, label_ids in self.fallback_label_ids),
            "layout_issues": list(self.layout_issues),
            "permitted_suppressions": list(self.permitted_suppressions),
            "fallback_candidate_label_ids": list(self.fallback_candidate_label_ids),
            "neighbours": primary_neighbours,
            "navigation": [
                {"direction": direction, "chart_id": neighbour}
                for direction, neighbour in self.neighbours
            ],
        }


@dataclass(frozen=True, slots=True)
class AtlasBuildResult:
    """Result of an atlas build."""

    atlas_id: str
    pages: tuple[ChartPageResult, ...]
    combined_pdf: Path
    manifest_path: Path
    draft_report_path: Path | None = None
    index_page_count: int = 0
    front_matter_page_count: int = 0
    credits_page_count: int = 0
    chart_directory_page_count: int = 0

    @property
    def total_hard_issues(self) -> int:
        return sum(page.hard_issues for page in self.pages)


@dataclass(frozen=True, slots=True)
class _MainChartShared:
    atlas_path: str | Path
    style_path: str | Path
    star_store: str | Path | None
    faint_star_store: str | Path | None
    faint_star_limit: float | None
    stars_csv: str | Path | None
    double_stars_path: str | Path | bool | None
    inputs: ChartInputs
    star_systems: tuple[StarSystem, ...]
    star_names: dict[int, StarName]
    library: OverridesLibrary | None
    detail_charts: tuple[DetailChartConfig, ...]
    fallback_ids_by_detail: dict[str, frozenset[str]]
    edition: EditionConfig
    overviews: dict[str, OverviewMap]
    variable_star_hips: frozenset[int]
    outroot: Path
    optimize: bool
    render_png: bool
    png_dpi: float


@dataclass(frozen=True, slots=True)
class _BuiltMainChart:
    scene: ChartScene
    transform: PageTransform
    style: StyleConfig
    labels: tuple[Label, ...]
    presentation: ChartPresentation
    locator: LocatorInset | None
    detail_markers: tuple[DetailMapMarker, ...]
    page_result: ChartPageResult
    observing_list_names: tuple[str, ...]
    forced_lists: tuple[str, ...]
    applied_overrides: bool
    timings: tuple[float, float, float, float, float, float, float]


def _require_mandatory_labels(chart_id: str, labels: tuple[Label, ...]) -> None:
    missing = sorted(
        label.id
        for label in labels
        if label.mandatory
        and (label.hidden or label.effective_candidate() is None)
    )
    if missing:
        raise ValueError(
            f"chart {chart_id} has missing mandatory labels: {', '.join(missing)}"
        )


def _layout_issue_records(issues: tuple[LayoutIssue, ...]) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "issue_id": issue.id,
            "type": issue.issue_type.value,
            "severity": "hard",
            "affected_ids": list(issue.element_ids),
            "message": issue.message,
        }
        for issue in issues
    )


def _detail_fallback_suppression_candidate(
    labels: tuple[Label, ...],
    validation: ValidationResult,
    detail_by_label: dict[str, str],
) -> tuple[Label, str, tuple[LayoutIssue, ...]] | None:
    suppressible_types = {
        "label_label",
        "label_page",
        "label_star",
        "label_dso",
        "furniture_overlap",
        "invalid_leader_line",
    }
    label_by_id = {label.id: label for label in labels}
    issues_by_label: dict[str, list[LayoutIssue]] = {}
    for issue in validation.issues:
        if issue.issue_type.value not in suppressible_types:
            continue
        for element_id in issue.element_ids:
            if element_id in detail_by_label:
                issues_by_label.setdefault(element_id, []).append(issue)
    if not issues_by_label:
        return None
    label_id = min(
        issues_by_label,
        key=lambda item: (
            label_by_id[item].priority,
            -len(issues_by_label[item]),
            len(label_by_id[item].candidates),
            item,
        ),
    )
    return (
        label_by_id[label_id],
        detail_by_label[label_id],
        tuple(issues_by_label[label_id]),
    )


_CHART_WORKER_SHARED: _MainChartShared | None = None


def _init_chart_worker(shared: _MainChartShared) -> None:
    global _CHART_WORKER_SHARED
    _CHART_WORKER_SHARED = shared


def _build_chart_in_worker(definition: ChartDefinition) -> _BuiltMainChart:
    if _CHART_WORKER_SHARED is None:
        raise RuntimeError("chart worker was not initialized")
    return _build_main_chart(definition, _CHART_WORKER_SHARED)


def _iter_parallel_charts(
    pool: ProcessPoolExecutor,
    charts: tuple[ChartDefinition, ...],
    jobs: int,
) -> Iterator[_BuiltMainChart]:
    definitions = iter(charts)
    pending = deque(
        pool.submit(_build_chart_in_worker, definition)
        for definition in islice(definitions, 2 * jobs)
    )
    while pending:
        built = pending.popleft().result()
        next_definition = next(definitions, None)
        if next_definition is not None:
            pending.append(pool.submit(_build_chart_in_worker, next_definition))
        yield built


def _build_main_chart(
    definition: ChartDefinition,
    shared: _MainChartShared,
    progress: Progress | None = None,
) -> _BuiltMainChart:
    chart_start = time.perf_counter()
    stage_start = chart_start
    chart_context = build_chart_context(
        atlas_path=shared.atlas_path,
        style_path=shared.style_path,
        definition=definition,
        star_store=shared.star_store,
        faint_star_store=shared.faint_star_store,
        faint_star_limit=shared.faint_star_limit,
        stars_csv=shared.stars_csv,
        double_stars_path=shared.double_stars_path,
        star_systems=shared.star_systems,
        progress=progress,
        inputs=shared.inputs,
    )
    detail_markers = tuple(
        build_detail_marker(detail, definition, chart_context.transform)
        for detail in shared.detail_charts
        if detail.parent_chart_id == definition.id
    )
    context_s = time.perf_counter() - stage_start
    stage_start = time.perf_counter()
    labels = build_labels(
        chart_context.scene, chart_context.transform, chart_context.style, shared.star_names
    )
    labels_s = time.perf_counter() - stage_start
    chart_overrides = shared.library.for_chart(definition.id) if shared.library else None
    protected_ids = (
        frozenset(
            label_id for label_id, spec in chart_overrides.labels.items() if spec.hidden is not True
        )
        if chart_overrides is not None
        else frozenset()
    )
    parent_dsos = {
        scene_dso.dso.id: scene_dso
        for scene_dso in chart_context.scene.deep_sky_objects
        if scene_dso.symbol_visible
    }
    parent_galaxies = tuple(
        scene_dso
        for scene_dso in chart_context.scene.deep_sky_objects
        if scene_dso.dso.object_type == DsoType.GALAXY and scene_dso.symbol_visible
    )
    fallback_eligible: list[tuple[str, tuple[str, ...]]] = []
    for detail in shared.detail_charts:
        if detail.parent_chart_id != definition.id or not detail.fallback_parent_galaxy_labels:
            continue
        detail_ids = (
            shared.fallback_ids_by_detail.get(detail.id, frozenset()) & parent_dsos.keys()
        )
        if detail.fallback_parent_min_magnitude is not None:
            detail_ids = {
                item
                for item in detail_ids
                if parent_dsos[item].dso.magnitude is not None
                and parent_dsos[item].dso.magnitude
                >= detail.fallback_parent_min_magnitude
            }
        if detail.fallback_parent_min_nearby_galaxies:
            galaxy_positions = {
                scene_dso.dso.id: chart_context.transform.to_page(scene_dso.chart_point)
                for scene_dso in parent_galaxies
            }
            radius_sq = chart_context.style.label.selection.density_radius_mm**2
            detail_ids = {
                item
                for item in detail_ids
                if item in galaxy_positions
                and sum(
                    other_id != item
                    and (galaxy_positions[item].x_mm - position.x_mm) ** 2
                    + (galaxy_positions[item].y_mm - position.y_mm) ** 2
                    <= radius_sq
                    for other_id, position in galaxy_positions.items()
                )
                >= detail.fallback_parent_min_nearby_galaxies
            }
        available_parent_label_ids = {label.id for label in labels}
        detail_ids = {
            item for item in detail_ids if f"label:dso:{item}" in available_parent_label_ids
        }
        if detail_ids:
            fallback_eligible.append(
                (detail.code, tuple(sorted(f"label:dso:{item}" for item in detail_ids)))
            )
    labels = select_labels(
        labels,
        chart_context.scene,
        chart_context.transform,
        chart_context.style,
        protected_ids=protected_ids,
    )
    if chart_overrides is not None:
        labels = apply_overrides(labels, chart_overrides)
    presentation = presentation_from_edition(
        definition, shared.edition, scene=chart_context.scene
    )
    locator: LocatorInset | None = None
    if shared.inputs.style.locator.enabled and shared.overviews:
        locator = LocatorInset(
            overview=shared.overviews[hemisphere_for(definition.center_dec_deg)],
            current_chart_id=definition.id,
            neighbour_ids=frozenset(neighbour for _, neighbour in definition.neighbours),
        )
    furniture = furniture_obstacles(
        chart_context.transform, definition, chart_context.style, presentation
    )
    optimize_s = 0.0
    cost_s = 0.0
    if shared.optimize:
        stage_start = time.perf_counter()
        optimized = optimize_labels(
            labels,
            chart_context.scene,
            chart_context.transform,
            chart_context.style,
            furniture=furniture,
        )
        labels = optimized.labels
        optimize_s = time.perf_counter() - stage_start
        cost_before = optimized.cost_before
        cost_after = optimized.cost_after
    else:
        stage_start = time.perf_counter()
        cost_before = layout_cost(
            labels, chart_context.scene, chart_context.transform, chart_context.style
        )[0]
        cost_after = cost_before
        cost_s = time.perf_counter() - stage_start
    stage_start = time.perf_counter()
    validation = validate_layout(
        labels,
        chart_context.scene,
        chart_context.transform,
        chart_context.style,
        furniture=furniture,
    )
    _require_mandatory_labels(definition.id, labels)
    permitted_suppressions: list[dict[str, Any]] = []
    fallback_detail_by_label = {
        label_id: detail_code
        for detail_code, label_ids in fallback_eligible
        for label_id in label_ids
    }
    while shared.optimize and fallback_detail_by_label:
        choice = _detail_fallback_suppression_candidate(
            labels, validation, fallback_detail_by_label
        )
        if choice is None:
            break
        suppressed_label, detail_code, suppressed_issues = choice
        suppressed_id = suppressed_label.id
        permitted_suppressions.append(
            {
                "label_id": suppressed_id,
                "text": suppressed_label.text,
                "priority": suppressed_label.priority,
                "detail_chart": detail_code,
                "reason": "remaining_geometric_issue_after_optimization",
                "issues": [issue.id for issue in suppressed_issues],
            }
        )
        labels = tuple(label for label in labels if label.id != suppressed_id)
        fallback_detail_by_label.pop(suppressed_id)
        optimized = optimize_labels(
            labels,
            chart_context.scene,
            chart_context.transform,
            chart_context.style,
            furniture=furniture,
        )
        labels = optimized.labels
        cost_after = optimized.cost_after
        validation = validate_layout(
            labels,
            chart_context.scene,
            chart_context.transform,
            chart_context.style,
            furniture=furniture,
        )
        _require_mandatory_labels(definition.id, labels)
    validate_s = time.perf_counter() - stage_start
    stage_start = time.perf_counter()
    page_dir = shared.outroot / "charts" / definition.id
    render_chart(
        chart_context.scene,
        chart_context.transform,
        chart_context.style,
        labels=labels,
        presentation=presentation,
        locator=locator,
        detail_markers=detail_markers,
        variable_star_hips=shared.variable_star_hips,
        pdf_path=page_dir / "chart.pdf",
        png_path=page_dir / "preview.png" if shared.render_png else None,
        png_dpi=shared.png_dpi,
    )
    render_s = time.perf_counter() - stage_start
    placed = sum(1 for label in labels if not label.hidden and label.candidates)
    page_result = ChartPageResult(
        chart_id=definition.id,
        star_count=chart_context.scene.star_count,
        dso_count=chart_context.scene.dso_count,
        star_system_count=chart_context.scene.star_system_count,
        label_count=len(labels),
        placed_count=placed,
        hidden_count=len(labels) - placed,
        overrides_applied=len(chart_overrides) if chart_overrides is not None else 0,
        hard_issues=len(validation.issues),
        cost_before=cost_before,
        cost_after=cost_after,
        layout_hash=layout_hash(labels),
        neighbours=definition.neighbours,
        fallback_label_ids=tuple(
            (
                code,
                tuple(
                    item["label_id"]
                    for item in permitted_suppressions
                    if item["detail_chart"] == code
                ),
            )
            for code, _label_ids in fallback_eligible
            if any(item["detail_chart"] == code for item in permitted_suppressions)
        ),
        layout_issues=(
            *_layout_issue_records(validation.issues),
            *(
                {
                    "issue_id": f"issue:fallback_candidate:{label.id}",
                    "type": "fallback_candidate",
                    "severity": "warning",
                    "affected_ids": [label.id],
                    "message": (
                        "No candidate fit inside the chart field; unrestricted candidates "
                        "were generated."
                    ),
                }
                for label in labels
                if any(candidate.id.endswith(":fallback") for candidate in label.candidates)
            ),
        ),
        permitted_suppressions=tuple(permitted_suppressions),
        fallback_candidate_label_ids=tuple(
            label.id
            for label in labels
            if any(candidate.id.endswith(":fallback") for candidate in label.candidates)
        ),
    )
    return _BuiltMainChart(
        scene=chart_context.scene,
        transform=chart_context.transform,
        style=chart_context.style,
        labels=labels,
        presentation=presentation,
        locator=locator,
        detail_markers=detail_markers,
        page_result=page_result,
        observing_list_names=tuple(chart_context.observing_lists or ()),
        forced_lists=(
            tuple(sorted(chart_context.selection_policy.forced_lists))
            if chart_context.selection_policy is not None
            else ()
        ),
        applied_overrides=chart_overrides is not None,
        timings=(
            time.perf_counter() - chart_start,
            context_s,
            labels_s,
            cost_s,
            optimize_s,
            validate_s,
            render_s,
        ),
    )


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


def _tiling_manifest(atlas: AtlasConfig) -> dict[str, Any] | None:
    """Describe the tiling actually used, including resolved ring counts."""
    if atlas.tiling is None:
        return None
    spec = TilingSpec.from_config(atlas.tiling)
    payload: dict[str, Any] = {
        "mode": "declination_rings" if spec.is_ring_mode else "declination_bands",
        "width_deg": spec.width_deg,
        "height_deg": spec.height_deg,
        "coverage_step_deg": spec.coverage_step_deg,
    }
    if spec.is_ring_mode:
        payload.update(
            {
                "declination_centers": list(spec.declination_centers),
                "resolved_chart_counts": list(resolve_ring_counts(spec)),
                "polar_caps": spec.polar_caps,
                "stagger_ra_centers": spec.stagger_ra_centers,
                "auto_adjust_counts": spec.auto_adjust_counts,
                "target_overlap": {
                    "vertical_deg": spec.vertical_overlap_deg,
                    "horizontal_min_deg": spec.horizontal_overlap_min_deg,
                },
            }
        )
    else:
        payload["overlap_deg"] = spec.overlap_deg
    return payload


def _load_overview_stars(
    star_store: str | Path | None,
    stars_csv: str | Path | None,
    magnitude_limit: float,
) -> tuple[Star, ...]:
    """Load the bright-star foreground for the overview pages.

    The overview needs the whole sky, not one chart, so it queries the store
    with a full-sky box instead of the per-chart path.
    """
    if star_store is not None:
        with StarStore.open(star_store) as store:
            stars = store.query_box(
                QueryBox(0.0, 360.0, -90.0, 90.0), magnitude_limit=magnitude_limit
            )
        return tuple(stars)
    if stars_csv is not None:
        return tuple(
            star for star in load_sample_stars(stars_csv) if star.magnitude <= magnitude_limit
        )
    return ()


def _draw_front_matter_pages(
    cr: cairo.Context[cairo.Surface],
    surface: cairo.Surface,
    atlas: AtlasConfig,
    style: StyleConfig,
    main_charts: tuple[ChartDefinition, ...],
    scale_chart: ChartDefinition,
) -> int:
    """Write the two opening pages shared by all editions."""
    page = atlas.page.to_geometry()
    mm_per_degree = PageTransform(
        scale_chart,
        page,
        scale_mm_per_degree=atlas.mm_per_degree,
    ).mm_per_deg
    draw_introduction(cr, atlas, style, main_charts)
    surface.show_page()

    draw_field_guide(cr, atlas, style, len(main_charts), mm_per_degree)
    surface.show_page()
    return 2


def _draw_build_credits_page(
    cr: cairo.Context[cairo.Surface],
    surface: cairo.Surface,
    atlas: AtlasConfig,
    style: StyleConfig,
    data_sources: list[dict[str, Any]],
    geometry_inputs: dict[str, str | None],
    geometry_catalogues: dict[str, list[str]],
    inputs: ChartInputs,
    star_names: dict[int, StarName],
) -> None:
    """Append credits derived from the data and geometry used in this build."""
    page = atlas.page.to_geometry()
    family = style.typography.sans_family
    selected_dsos = _selected_dsos(inputs)
    left_sections, right_sections = _credits_columns(
        data_sources=data_sources,
        geometry_catalogues=geometry_catalogues,
        used_dso_catalogues=frozenset(
            catalogue
            for dso in selected_dsos
            for catalogue in (
                dso.provenance.catalogue,
                *(record.catalogue_id for record in dso.catalogue_records),
            )
        ),
        star_name_source=geometry_inputs["star_names"] if star_names else None,
        has_iau_star_names=any(name.curated_name for name in star_names.values()),
        has_galaxies=any(dso.object_type == DsoType.GALAXY for dso in selected_dsos),
    )
    draw_credits_page(
        cr,
        page,
        family,
        left_sections,
        right_sections,
        edition=atlas.resolved_edition().name,
        catalogue_data_label="source-specific dates in the build manifest",
    )
    surface.show_page()


def _selected_dsos(inputs: ChartInputs) -> tuple[DeepSkyObject, ...]:
    """Return physical targets selected by the edition policy for attribution."""
    membership_index = build_membership_index(inputs.observing_lists, inputs.dsos)
    if inputs.selection_policy is None:
        return inputs.dsos
    selected = []
    for dso in inputs.dsos:
        decision = select_dso(
            dso,
            index=membership_index,
            policy=inputs.selection_policy,
        )
        if decision.visible or decision.forced:
            selected.append(dso)
    return tuple(selected)


def _credits_columns(
    *,
    data_sources: list[dict[str, Any]],
    geometry_catalogues: dict[str, list[str]],
    used_dso_catalogues: frozenset[str],
    star_name_source: str | None,
    has_iau_star_names: bool,
    has_galaxies: bool,
) -> tuple[
    tuple[tuple[str, tuple[str, ...]], ...],
    tuple[tuple[str, tuple[str, ...]], ...],
]:
    """Prepare concise, build-specific source credits from the input manifests."""
    by_kind = {item["kind"]: item for item in data_sources}
    left: list[tuple[str, tuple[str, ...]]] = []
    right: list[tuple[str, tuple[str, ...]]] = []

    star_entries: list[str] = []
    star_source = by_kind.get("stars", {}).get("manifest") or {}
    if star_source.get("catalogue") == "TYC2":
        star_entries.append("Tycho-2 — Høg et al. (2000), ESA")
        supplement = star_source.get("bright_star_supplement") or {}
        if supplement.get("catalogue") == "HIP":
            star_entries.append("Hipparcos — ESA (1997)")
    elif star_source.get("source"):
        star_entries.append(f"Stars — {star_source['source']}")
    faint_source = by_kind.get("faint_stars", {}).get("manifest") or {}
    if faint_source.get("catalogue") == "UCAC4":
        star_entries.append("UCAC4 — Zacharias et al. (2013), USNO; APASS V where available")
    elif faint_source.get("source"):
        star_entries.append(f"Faint-star supplement — {faint_source['source']}")
    if star_entries:
        left.append(("Star catalogues", tuple(star_entries)))

    dso_source = by_kind.get("deep_sky", {}).get("manifest") or {}
    manifest_sources = {
        str(item.get("catalogue_id")): item
        for item in dso_source.get("sources", ())
        if isinstance(item, dict) and item.get("catalogue_id")
    }
    active_ids = set(used_dso_catalogues)
    dso_entries: list[str] = []
    if "OpenNGC" in active_ids:
        dso_entries.append("OpenNGC — Mattia Verga & contributors")

    group_specs = (
        (
            ("VII/20", "VII/7A", "VII/9", "VII/21", "VII/220A"),
            {
                "VII/20": "Sharpless (1959)",
                "VII/7A": "Lynds LDN (1962)",
                "VII/9": "Lynds LBN (1965)",
                "VII/21": "van den Bergh (1966)",
                "VII/220A": "Barnard (1927)",
            },
            "Nebula catalogues",
        ),
        (
            ("VII/92A:Collinder", "VII/92A:Melotte", "VII/92A:Stock"),
            {
                "VII/92A:Collinder": "Collinder",
                "VII/92A:Melotte": "Melotte",
                "VII/92A:Stock": "Stock",
            },
            "Open clusters — Lyngå",
        ),
        (
            ("IV/24:AbellPN", "IV/24:CuratedPN"),
            {
                "IV/24:AbellPN": "Kohoutek (2001)",
                "IV/24:CuratedPN": "Kohoutek (2001)",
            },
            "Planetary nebulae",
        ),
        (
            ("VII/202:Palomar", "VII/202:Terzan"),
            {"VII/202:Palomar": "Palomar", "VII/202:Terzan": "Terzan"},
            "Globular clusters — Harris",
        ),
        (
            ("VII/213", "VII/74A", "VII/155"),
            {
                "VII/213": "Hickson (1982)",
                "VII/74A": "Arp (1966)",
                "VII/155": "de Vaucouleurs et al. (1991)",
            },
            "Galaxy catalogues",
        ),
    )
    grouped_ids: set[str] = set()
    for ids, labels, heading in group_specs:
        grouped_ids.update(ids)
        included = [labels[item] for item in ids if item in active_ids]
        if included:
            citation = "; ".join(included)
            if " — " in heading:
                citation = f"{', '.join(included)} — {heading.split(' — ')[-1]}"
            dso_entries.append(citation)
    for catalogue_id in sorted(active_ids - grouped_ids - {"OpenNGC"}):
        metadata = manifest_sources.get(catalogue_id, {})
        name = metadata.get("name") or catalogue_id
        dso_entries.append(str(name))
    if not dso_entries and dso_source.get("source"):
        dso_entries.append(f"Deep-sky catalogue — {dso_source['source']}")
    if dso_entries:
        left.append(("Deep-sky catalogues", tuple(dso_entries)))
    if has_galaxies:
        left.append(
            (
                "Galaxy visibility",
                (
                    "Classification informed by Crumey (2014); the atlas applies documented "
                    "visual-observing assumptions and heuristics.",
                ),
            )
        )

    wds = by_kind.get("double_stars", {}).get("manifest") or {}
    if wds:
        left.append(
            (
                "Double stars",
                (
                    "Washington Double Star Catalog — Mason et al., USNO",
                    "This research has made use of the Washington Double Star Catalog "
                    "maintained at the U.S. Naval Observatory.",
                ),
            )
        )

    line_sources = set(geometry_catalogues.get("constellation_lines", ()))
    boundary_sources = set(geometry_catalogues.get("constellation_boundaries", ()))
    outline_sources = set(geometry_catalogues.get("outlines", ()))
    milky_way_sources = set(geometry_catalogues.get("milky_way", ()))
    cartography: list[str] = []
    if "Stellarium Western (Sky & Telescope)" in line_sources:
        cartography.append(
            "Constellation figures — Stellarium Western (Sky & Telescope); "
            "Krizak, Piskor & Stellarium Team"
        )
    elif line_sources:
        cartography.extend(f"Constellation figures — {item}" for item in sorted(line_sources))
    if "d3-celestial" in boundary_sources:
        cartography.append(
            "Constellation boundaries — IAU definitions; d3-celestial data, Olaf Frohn"
        )
    elif boundary_sources:
        cartography.extend(
            f"Constellation boundaries — {item}" for item in sorted(boundary_sources)
        )
    if "nightsky-atlas-authored" in outline_sources:
        cartography.append("Schematic nebula outlines — NightSky Atlas")
    if milky_way_sources:
        cartography.append("Milky Way contours — José R. Vieira, via d3-celestial")
    if cartography:
        right.append(("Constellations & cartography", tuple(cartography)))

    if (
        star_name_source is not None
        and Path(star_name_source).resolve() == STAR_NAMES_FIXTURE_DIR.resolve()
    ):
        name_sources = ["d3-celestial"]
        if has_iau_star_names:
            name_sources.append("IAU Catalog of Star Names")
        right.append(("Star names", ("; ".join(name_sources),)))
    elif star_name_source:
        right.append(("Star names", (f"Star-name input — {Path(star_name_source).name}",)))

    service_entries: list[str] = []
    if manifest_sources and active_ids.intersection(manifest_sources):
        source_url = dso_source.get("acknowledgement")
        service_entries.append("VizieR — CDS, Strasbourg, France")
        if source_url:
            service_entries.append(str(source_url))
    if service_entries:
        right.append(("Catalogue services", tuple(service_entries)))

    return tuple(left), tuple(right)


def _build_atlas_impl(
    *,
    atlas_path: str | Path,
    style_path: str | Path,
    outdir: str | Path,
    star_store: str | Path | None = None,
    faint_star_store: str | Path | None = None,
    faint_star_limit: float | None = None,
    stars_csv: str | Path | None = None,
    dsos_path: str | Path | None = None,
    constellations_dir: str | Path | bool | None = None,
    outlines_dir: str | Path | bool | None = None,
    star_names_dir: str | Path | bool | None = None,
    observing_lists_dir: str | Path | bool | None = None,
    observing_config_path: str | Path | None = None,
    double_stars_path: str | Path | bool | None = None,
    overrides_path: str | Path | None = None,
    chart_ids: tuple[str, ...] | None = None,
    limit: int | None = None,
    optimize: bool = True,
    render_png: bool = True,
    png_dpi: float = 150.0,
    jobs: int = 1,
    write_front_matter: bool = True,
    write_overviews: bool = True,
    write_draft_report: bool = True,
    publication: bool = False,
    progress: Progress | None = None,
) -> AtlasBuildResult:
    """Build an atlas subset or the whole atlas and write a manifest."""
    progress = progress if progress is not None else null_progress()
    with progress.step("load config and shared catalogues"):
        inputs = load_chart_inputs(
            atlas_path=atlas_path,
            style_path=style_path,
            dsos_path=dsos_path,
            constellations_dir=constellations_dir,
            outlines_dir=outlines_dir,
            observing_lists_dir=observing_lists_dir,
            observing_config_path=observing_config_path,
            progress=progress,
        )
    atlas = inputs.atlas
    style = inputs.style
    edition = atlas.resolved_edition()
    with progress.step("resolve chart definitions"):
        all_charts = chart_definitions(atlas)
    if not all_charts:
        raise ValueError(f"atlas {atlas.id!r} contains no charts")
    if chart_ids is not None:
        unknown = set(chart_ids) - {chart.id for chart in all_charts}
        if unknown:
            raise ValueError(f"unknown chart IDs: {', '.join(sorted(unknown))}")
    if limit is not None and limit <= 0:
        raise ValueError("limit must be positive")
    if jobs <= 0:
        raise ValueError("jobs must be positive")
    charts = all_charts
    if chart_ids is not None:
        wanted = set(chart_ids)
        charts = tuple(chart for chart in charts if chart.id in wanted)
    if limit is not None:
        charts = charts[:limit]
    if not charts:
        raise ValueError("no charts selected")
    missing_detail_parents = {detail.parent_chart_id for detail in atlas.detail_charts} - {
        chart.id for chart in all_charts
    }
    if missing_detail_parents:
        raise ValueError(
            "detail charts reference unknown parent chart(s): "
            + ", ".join(sorted(missing_detail_parents))
        )
    main_codes = {presentation_from_edition(chart, edition).chart_code for chart in all_charts}
    duplicate_detail_codes = main_codes & {detail.code for detail in atlas.detail_charts}
    if duplicate_detail_codes:
        raise ValueError(
            "detail chart codes collide with atlas chart codes: "
            + ", ".join(sorted(duplicate_detail_codes))
        )
    detail_charts = tuple(
        detail
        for detail in atlas.detail_charts
        if detail.parent_chart_id in {chart.id for chart in charts}
    )
    detail_star_profiles: dict[str, tuple[float, StyleConfig]] = {}
    for profile_name in sorted({detail.star_profile for detail in detail_charts}):
        profile_atlas_path = Path(atlas_path).with_name(f"{profile_name}.yaml")
        profile_style_path = Path(style_path).with_name(f"{profile_name}.yaml")
        profile_atlas = load_atlas_config(profile_atlas_path)
        profile_style = load_style_config(profile_style_path)
        if not math.isclose(
            profile_atlas.stellar_limit_magnitude,
            profile_style.star.faint_magnitude,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ValueError(
                f"{profile_name} atlas stellar limit does not match its star-style faint limit"
            )
        detail_star_profiles[profile_name] = (
            profile_atlas.stellar_limit_magnitude,
            _style_with_star_profile(style, profile_style),
        )
    main_faint_star_store = (
        faint_star_store if atlas.id in {"eyepiece", "eyepieceDeep"} else None
    )
    main_faint_star_limit = faint_star_limit if main_faint_star_store is not None else None
    if publication:
        if not optimize:
            raise ValueError("publication requires deterministic layout optimization")
        if not write_front_matter or not write_overviews or not style.overview.enabled:
            raise ValueError("publication requires front matter and overview maps")
    selected_sources = collect_data_sources(
        star_store=star_store,
        faint_star_store=faint_star_store,
        stars_csv=stars_csv,
        dsos_path=dsos_path if dsos_path is not None else default_dso_path(),
        double_stars_path=(
            DEFAULT_DOUBLE_STAR_PATH if double_stars_path is None else double_stars_path
        ),
    )
    geometry_inputs = {
        "constellations": (
            None
            if constellations_dir is False
            else str(constellations_dir or "data/fixtures/constellations")
        ),
        "outlines": (
            None if outlines_dir is False else str(outlines_dir or "data/fixtures/outlines")
        ),
        "star_names": (
            None if star_names_dir is False else str(star_names_dir or STAR_NAMES_FIXTURE_DIR)
        ),
        "milky_way": (
            "data/third_party/d3-celestial/mw.json" if style.milky_way.enabled else None
        ),
    }
    input_paths = {
        "atlas_config": atlas_path,
        "style_config": style_path,
        "code": Path(__file__).resolve().parents[1],
        "constellations": geometry_inputs["constellations"],
        "outlines": geometry_inputs["outlines"],
        "openngc_outlines": (
            str(OPENNGC_OUTLINE_DIR)
            if geometry_inputs["outlines"] == "data/fixtures/outlines"
            else None
        ),
        "star_names": geometry_inputs["star_names"],
        "milky_way": geometry_inputs["milky_way"],
        "faint_star_store": faint_star_store,
        "observing_lists": (
            None
            if observing_lists_dir is False
            else str(observing_lists_dir or OBSERVING_LISTS_FIXTURE_DIR)
        ),
        "observing_config": str(observing_config_path or OBSERVING_CONFIG_PATH),
        "overrides": overrides_path,
    }
    for profile_name in detail_star_profiles:
        input_paths[f"detail_star_profile_{profile_name}_atlas"] = Path(atlas_path).with_name(
            f"{profile_name}.yaml"
        )
        input_paths[f"detail_star_profile_{profile_name}_style"] = Path(style_path).with_name(
            f"{profile_name}.yaml"
        )
    input_fingerprints = collect_build_inputs(input_paths)
    geometry_catalogues = {
        "constellation_lines": sorted(
            {item.provenance.catalogue for item in inputs.constellations.lines}
        ),
        "constellation_boundaries": sorted(
            {item.provenance.catalogue for item in inputs.constellations.boundaries}
        ),
        "outlines": sorted({item.provenance.catalogue for item in inputs.outlines}),
        "milky_way": ["d3-celestial"] if inputs.milky_way_contours else [],
    }
    if publication:
        validate_publication_inputs(
            atlas,
            all_charts,
            charts,
            star_store=star_store,
            dso_count=len(inputs.dsos),
            data_sources=selected_sources,
        )

    library: OverridesLibrary | None = (
        load_override_library(overrides_path) if overrides_path is not None else None
    )
    applied_chart_ids: set[str] = set()

    with progress.step("load shared fixtures"):
        star_names = (
            {}
            if star_names_dir is False
            else load_star_names(
                star_names_dir if star_names_dir is not None else STAR_NAMES_FIXTURE_DIR
            )
        )
        variable_star_hips = frozenset(
            hip for hip, entry in star_names.items() if entry.variable_marker
        )
        star_systems = load_star_systems(double_stars_path)

    prepared_details: dict[str, _PreparedDetail] = {}
    fallback_ids_by_detail: dict[str, frozenset[str]] = {}
    for detail in detail_charts:
        if not detail.fallback_parent_galaxy_labels:
            continue
        definition = detail.to_definition(atlas_id=atlas.id)
        stellar_limit_magnitude, detail_style = detail_star_profiles[detail.star_profile]
        detail_faint_limit = (
            min(faint_star_limit, stellar_limit_magnitude)
            if faint_star_limit is not None
            else None
        )
        detail_context = build_chart_context(
            atlas_path=atlas_path,
            style_path=style_path,
            definition=definition,
            star_store=star_store,
            faint_star_store=faint_star_store,
            faint_star_limit=detail_faint_limit,
            stars_csv=stars_csv,
            double_stars_path=double_stars_path,
            star_systems=star_systems,
            magnitude_limit=stellar_limit_magnitude,
            scale_mm_per_degree=detail.mm_per_degree,
            allow_faint_star_supplement=True,
            progress=progress,
            inputs=inputs,
        )
        detail_labels = build_labels(
            detail_context.scene,
            detail_context.transform,
            detail_style,
            star_names,
        )
        detail_labels = select_labels(
            detail_labels,
            detail_context.scene,
            detail_context.transform,
            detail_style,
        )
        detail_overrides = library.for_chart(definition.id) if library is not None else None
        if detail_overrides is not None:
            detail_labels = apply_overrides(detail_labels, detail_overrides)
            applied_chart_ids.add(definition.id)
        detail_presentation = _detail_presentation(
            detail,
            edition=edition,
            main_charts=all_charts,
            stellar_limit_magnitude=stellar_limit_magnitude,
        )
        detail_furniture = furniture_obstacles(
            detail_context.transform,
            definition,
            detail_style,
            detail_presentation,
        )
        if optimize:
            optimized = optimize_labels(
                detail_labels,
                detail_context.scene,
                detail_context.transform,
                detail_style,
                furniture=detail_furniture,
            )
            detail_labels = optimized.labels
            detail_cost_before = optimized.cost_before
            detail_cost_after = optimized.cost_after
        else:
            detail_cost_before = layout_cost(
                detail_labels,
                detail_context.scene,
                detail_context.transform,
                detail_style,
            )[0]
            detail_cost_after = detail_cost_before
        detail_validation = validate_layout(
            detail_labels,
            detail_context.scene,
            detail_context.transform,
            detail_style,
            furniture=detail_furniture,
        )
        _require_mandatory_labels(definition.id, detail_labels)
        prepared_details[detail.id] = _PreparedDetail(
            context=detail_context,
            style=detail_style,
            labels=detail_labels,
            cost_before=detail_cost_before,
            cost_after=detail_cost_after,
            validation=detail_validation,
        )
        placed_label_ids = {
            label.id
            for label in detail_labels
            if not label.hidden and label.effective_candidate() is not None
        }
        problematic_detail_labels = {
            element_id
            for issue in detail_validation.issues
            for element_id in issue.element_ids
            if element_id.startswith("label:dso:")
        }
        fallback_ids_by_detail[detail.id] = frozenset(
            scene_dso.dso.id
            for scene_dso in detail_context.scene.deep_sky_objects
            if scene_dso.symbol_visible
            and f"label:dso:{scene_dso.dso.id}" in placed_label_ids
            and f"label:dso:{scene_dso.dso.id}" not in problematic_detail_labels
        )

    page = atlas.page.to_geometry()
    outroot = Path(outdir) / atlas.id
    outroot.mkdir(parents=True, exist_ok=True)
    combined_pdf = outroot / "atlas.pdf"
    effective_jobs = min(jobs, len(charts))
    progress.info(f"atlas {atlas.id!r}: {len(charts)} charts, {effective_jobs} jobs -> {outroot}")

    surface = cairo.PDFSurface(str(combined_pdf), mm_to_pt(page.width_mm), mm_to_pt(page.height_mm))
    context = cairo.Context(surface)
    chart_codes = {
        chart.id: presentation_from_edition(chart, edition).chart_code for chart in charts
    }
    pdf_navigation = PdfNavigation(
        frozenset((*chart_codes.values(), *(detail.code for detail in detail_charts)))
    )
    outline_root = pdf_navigation.add_outline(
        surface,
        cairo.PDF_OUTLINE_ROOT,
        edition.name,
        chart_codes[charts[0].id],
        open_item=True,
    )
    assert outline_root is not None
    front_matter_pages = 0
    if write_front_matter:
        with progress.step("front matter", detail=True):
            front_matter_pages = _draw_front_matter_pages(
                context,
                surface,
                atlas,
                style,
                tuple(charts),
                charts[0],
            )

    chart_directory = ()
    detail_chart_directory = ()
    chart_directory_pages = 0
    if write_front_matter:
        chart_directory = build_chart_directory(charts, edition)
        detail_chart_directory = build_detail_chart_directory(detail_charts, all_charts, edition)
        if atlas.chart_directory_position == "front":
            with progress.step("chart directory", detail=True):
                chart_directory_pages = draw_chart_directory_pages(
                    context,
                    surface,
                    chart_directory,
                    page,
                    style,
                    edition,
                    pdf_navigation,
                )
                chart_directory_pages += draw_detail_chart_directory_pages(
                    context,
                    surface,
                    detail_chart_directory,
                    page,
                    style,
                    edition,
                    pdf_navigation,
                )

    overviews: dict[str, OverviewMap] = {}
    overview_page_info: list[dict[str, Any]] = []
    write_overview_pages = write_overviews and style.overview.enabled and atlas.tiling is not None
    if write_overview_pages or style.locator.enabled:
        with progress.step("build overview maps"):
            overview_stars: tuple[Star, ...] = ()
            if write_overview_pages and style.overview.show_stars:
                overview_stars = _load_overview_stars(
                    star_store,
                    stars_csv,
                    style.overview.star_limit_magnitude,
                )
            for hemisphere in ("north", "south"):
                overviews[hemisphere] = build_overview(
                    all_charts,
                    hemisphere=hemisphere,
                    constellations=inputs.constellations,
                    edition=edition,
                    bright_stars=overview_stars,
                    equatorial_extension_deg=style.overview.equatorial_extension_deg,
                )
    if write_overview_pages:
        with progress.step("overview pages", detail=True):
            if style.overview.hemispheres_per_page == 2:
                draw_overview_spread_page(
                    context,
                    overviews["north"],
                    overviews["south"],
                    page,
                    style,
                    pdf_navigation,
                )
                surface.show_page()
                overview_page_info.append(
                    {
                        "hemisphere": "both",
                        "title": "Northern and southern sky",
                        "chart_count": overviews["north"].chart_count
                        + overviews["south"].chart_count,
                        "star_count": len(overviews["north"].stars) + len(overviews["south"].stars),
                    }
                )
            else:
                for hemisphere in ("north", "south"):
                    overview = overviews[hemisphere]
                    draw_overview_page(context, overview, page, style, pdf_navigation)
                    surface.show_page()
                    overview_page_info.append(
                        {
                            "hemisphere": hemisphere,
                            "title": overview.title,
                            "chart_count": overview.chart_count,
                            "star_count": len(overview.stars),
                        }
                    )

    results: list[ChartPageResult] = []
    index_dsos: dict[str, tuple[SceneDso, ...]] = {}
    index_stars: dict[str, tuple[Star, ...]] = {}
    index_constellations: dict[str, frozenset[str]] = {}
    boundary_constellations = {
        segment.id: segment.constellation_id
        for segment in inputs.constellations.boundaries
        if segment.constellation_id
    }
    observing_lists: dict[str, object] = {}
    forced_lists: list[str] = []
    shared = _MainChartShared(
        atlas_path=atlas_path,
        style_path=style_path,
        star_store=star_store,
        faint_star_store=main_faint_star_store,
        faint_star_limit=main_faint_star_limit,
        stars_csv=stars_csv,
        double_stars_path=double_stars_path,
        inputs=inputs,
        star_systems=tuple(star_systems),
        star_names=star_names,
        library=library,
        detail_charts=detail_charts,
        fallback_ids_by_detail=fallback_ids_by_detail,
        edition=edition,
        overviews=overviews if style.locator.enabled else {},
        variable_star_hips=variable_star_hips,
        outroot=outroot,
        optimize=optimize,
        render_png=render_png,
        png_dpi=png_dpi,
    )
    pool = (
        ProcessPoolExecutor(
            max_workers=effective_jobs,
            mp_context=get_context("spawn"),
            initializer=_init_chart_worker,
            initargs=(shared,),
        )
        if effective_jobs > 1
        else None
    )
    try:
        built_pages = (
            _iter_parallel_charts(pool, charts, effective_jobs)
            if pool is not None
            else (_build_main_chart(definition, shared, progress) for definition in charts)
        )
        for index, (definition, built) in enumerate(zip(charts, built_pages, strict=True), start=1):
            progress.detail(f"[{index}/{len(charts)}] {definition.id}: compose")
            if built.applied_overrides:
                applied_chart_ids.add(definition.id)
            if built.observing_list_names:
                observing_lists = dict.fromkeys(built.observing_list_names)
            if built.forced_lists:
                forced_lists = list(built.forced_lists)
            index_dsos[definition.id] = tuple(built.scene.deep_sky_objects)
            index_stars[definition.id] = tuple(item.star for item in built.scene.stars)
            index_constellations[definition.id] = frozenset(
                boundary_constellations[segment.source_id]
                for segment in built.scene.constellation_boundaries
                if segment.source_id in boundary_constellations
            )
            stage_start = time.perf_counter()
            draw_chart_page(
                context,
                built.scene,
                built.transform,
                built.style,
                labels=built.labels,
                presentation=built.presentation,
                locator=built.locator,
                pdf_navigation=pdf_navigation,
                detail_markers=built.detail_markers,
                variable_star_hips=variable_star_hips,
            )
            pdf_navigation.mark_chart_page(surface, context, built.presentation.chart_code)
            pdf_navigation.add_outline(
                surface,
                outline_root,
                built.presentation.chart_code,
                built.presentation.chart_code,
            )
            surface.show_page()
            compose_s = time.perf_counter() - stage_start
            page_result = built.page_result
            progress.info(
                f"[{index}/{len(charts)}] {definition.id}: "
                f"{page_result.star_count} stars, "
                f"{page_result.dso_count} DSOs, "
                f"{page_result.star_system_count} systems, "
                f"{page_result.placed_count}/{page_result.label_count} labels, "
                f"{page_result.hard_issues} hard issues "
                f"({built.timings[0] + compose_s:.2f}s work)"
            )
            _, context_s, labels_s, cost_s, optimize_s, validate_s, render_s = built.timings
            progress.detail(
                f"context {context_s:.2f}s | labels {labels_s:.2f}s | "
                f"cost {cost_s:.2f}s | optimize {optimize_s:.2f}s | "
                f"validate {validate_s:.2f}s | render {render_s:.2f}s | "
                f"compose {compose_s:.2f}s"
            )
            results.append(page_result)
    finally:
        if pool is not None:
            pool.shutdown(cancel_futures=True)

    atlas_index = build_atlas_index(
        index_dsos,
        index_constellations,
        charts,
        edition,
        chart_stars=index_stars,
        star_names=star_names,
    )
    detail_outline = None
    if detail_charts:
        detail_outline = pdf_navigation.add_outline(
            surface,
            outline_root,
            "Close-up maps",
            detail_charts[0].code,
        )

    for detail_index, detail in enumerate(detail_charts, start=1):
        detail_start = time.perf_counter()
        definition = detail.to_definition(atlas_id=atlas.id)
        stellar_limit_magnitude, detail_style = detail_star_profiles[detail.star_profile]
        progress.detail(f"[{detail_index}/{len(detail_charts)}] {detail.id}: detail chart start")
        chart_overrides = library.for_chart(definition.id) if library is not None else None
        prepared = prepared_details.get(detail.id)
        if prepared is None:
            chart_context = build_chart_context(
                atlas_path=atlas_path,
                style_path=style_path,
                definition=definition,
                star_store=star_store,
                faint_star_store=faint_star_store,
                faint_star_limit=(
                    min(faint_star_limit, stellar_limit_magnitude)
                    if faint_star_limit is not None
                    else None
                ),
                stars_csv=stars_csv,
                double_stars_path=double_stars_path,
                star_systems=star_systems,
                magnitude_limit=stellar_limit_magnitude,
                scale_mm_per_degree=detail.mm_per_degree,
                allow_faint_star_supplement=True,
                progress=progress,
                inputs=inputs,
            )
            labels = build_labels(
                chart_context.scene, chart_context.transform, detail_style, star_names
            )
            labels = select_labels(
                labels,
                chart_context.scene,
                chart_context.transform,
                detail_style,
            )
            if chart_overrides is not None:
                labels = apply_overrides(labels, chart_overrides)
                applied_chart_ids.add(definition.id)
            presentation = _detail_presentation(
                detail,
                edition=edition,
                main_charts=all_charts,
                stellar_limit_magnitude=stellar_limit_magnitude,
            )
            furniture = furniture_obstacles(
                chart_context.transform,
                definition,
                detail_style,
                presentation,
            )
            if optimize:
                optimized = optimize_labels(
                    labels,
                    chart_context.scene,
                    chart_context.transform,
                    detail_style,
                    furniture=furniture,
                )
                labels = optimized.labels
                cost_before = optimized.cost_before
                cost_after = optimized.cost_after
            else:
                cost_before = layout_cost(
                    labels, chart_context.scene, chart_context.transform, detail_style
                )[0]
                cost_after = cost_before
            validation = validate_layout(
                labels,
                chart_context.scene,
                chart_context.transform,
                detail_style,
                furniture=furniture,
            )
            _require_mandatory_labels(definition.id, labels)
        else:
            chart_context = prepared.context
            detail_style = prepared.style
            labels = prepared.labels
            cost_before = prepared.cost_before
            cost_after = prepared.cost_after
            validation = prepared.validation
            presentation = _detail_presentation(
                detail,
                edition=edition,
                main_charts=all_charts,
                stellar_limit_magnitude=stellar_limit_magnitude,
            )
        _require_mandatory_labels(definition.id, labels)
        page_dir = outroot / "charts" / definition.id
        render_chart(
            chart_context.scene,
            chart_context.transform,
            detail_style,
            labels=labels,
            presentation=presentation,
            variable_star_hips=variable_star_hips,
            pdf_path=page_dir / "chart.pdf",
            png_path=page_dir / "preview.png" if render_png else None,
            png_dpi=png_dpi,
        )
        draw_chart_page(
            context,
            chart_context.scene,
            chart_context.transform,
            detail_style,
            labels=labels,
            presentation=presentation,
            variable_star_hips=variable_star_hips,
            pdf_navigation=pdf_navigation,
        )
        pdf_navigation.mark_chart_page(surface, context, detail.code)
        if detail_outline is not None:
            pdf_navigation.add_outline(
                surface,
                detail_outline,
                f"{detail.name} · {detail.code}",
                detail.code,
            )
        surface.show_page()
        placed = sum(1 for label in labels if not label.hidden and label.candidates)
        results.append(
            ChartPageResult(
                chart_id=definition.id,
                star_count=chart_context.scene.star_count,
                dso_count=chart_context.scene.dso_count,
                star_system_count=chart_context.scene.star_system_count,
                label_count=len(labels),
                placed_count=placed,
                hidden_count=len(labels) - placed,
                overrides_applied=len(chart_overrides) if chart_overrides is not None else 0,
                hard_issues=len(validation.issues),
                cost_before=cost_before,
                cost_after=cost_after,
                layout_hash=layout_hash(labels),
                neighbours=definition.neighbours,
                layout_issues=(
                    *_layout_issue_records(validation.issues),
                    *(
                        {
                            "issue_id": f"issue:fallback_candidate:{label.id}",
                            "type": "fallback_candidate",
                            "severity": "warning",
                            "affected_ids": [label.id],
                            "message": (
                                "No candidate fit inside the chart field; unrestricted "
                                "candidates were generated."
                            ),
                        }
                        for label in labels
                        if any(candidate.id.endswith(":fallback") for candidate in label.candidates)
                    ),
                ),
                fallback_candidate_label_ids=tuple(
                    label.id
                    for label in labels
                    if any(candidate.id.endswith(":fallback") for candidate in label.candidates)
                ),
            )
        )
        progress.info(
            f"detail {detail.code} ({detail.name}): {chart_context.scene.star_count} stars, "
            f"{chart_context.scene.dso_count} DSOs, {placed}/{len(labels)} labels, "
            f"{len(validation.issues)} hard issues ({time.perf_counter() - detail_start:.2f}s)"
        )

    credits_page_count = 0
    if write_front_matter:
        with progress.step("append data sources and credits", detail=True):
            _draw_build_credits_page(
                context,
                surface,
                atlas,
                style,
                selected_sources,
                geometry_inputs,
                geometry_catalogues,
                inputs,
                star_names,
            )
            credits_page_count = 1

    with progress.step("append atlas index", detail=True):
        index_pages = draw_atlas_index_pages(
            context,
            surface,
            atlas_index,
            page,
            style,
            edition,
            pdf_navigation,
        )

    if write_front_matter and atlas.chart_directory_position == "back":
        with progress.step("append chart directory", detail=True):
            chart_directory_pages = draw_chart_directory_pages(
                context,
                surface,
                chart_directory,
                page,
                style,
                edition,
                pdf_navigation,
            )
            chart_directory_pages += draw_detail_chart_directory_pages(
                context,
                surface,
                detail_chart_directory,
                page,
                style,
                edition,
                pdf_navigation,
            )

    with progress.step("finish combined PDF"):
        surface.finish()

    if publication:
        if collect_build_inputs(input_paths) != input_fingerprints:
            raise ValueError("publication inputs changed during the build")
        if (
            collect_data_sources(
                star_store=star_store,
                faint_star_store=faint_star_store,
                stars_csv=stars_csv,
                dsos_path=dsos_path if dsos_path is not None else default_dso_path(),
                double_stars_path=(
                    DEFAULT_DOUBLE_STAR_PATH if double_stars_path is None else double_stars_path
                ),
            )
            != selected_sources
        ):
            raise ValueError("publication catalogues changed during the build")

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
        "faint_star_layer": {
            "enabled": faint_star_store is not None,
            "store": str(faint_star_store) if faint_star_store is not None else None,
            "magnitude_limit": faint_star_limit,
        },
        "visibility": atlas.visibility.model_dump(),
        "tiling": _tiling_manifest(atlas),
        "observing_lists": {
            "lists": sorted(observing_lists),
            "forced": forced_lists,
        },
        "chart_count": len(results),
        "parallel_jobs": effective_jobs,
        "main_chart_count": len(charts),
        "detail_chart_count": len(detail_charts),
        "main_chart_ids": [chart.id for chart in charts],
        "detail_chart_ids": [detail.id for detail in detail_charts],
        "detail_charts": [
            {
                "id": detail.id,
                "code": detail.code,
                "name": detail.name,
                "parent_chart_id": detail.parent_chart_id,
                "parent_chart_code": presentation_from_edition(
                    next(chart for chart in all_charts if chart.id == detail.parent_chart_id),
                    edition,
                ).chart_code,
                "center_ra_deg": detail.center_ra_deg,
                "center_dec_deg": detail.center_dec_deg,
                "width_deg": detail.width_deg,
                "height_deg": detail.height_deg,
                "mm_per_degree": detail.mm_per_degree,
                "star_profile": detail.star_profile,
                "faint_star_limit": (
                    min(faint_star_limit, detail_star_profiles[detail.star_profile][0])
                    if faint_star_store is not None and faint_star_limit is not None
                    else None
                ),
                "fallback_parent_galaxy_labels": detail.fallback_parent_galaxy_labels,
                "fallback_parent_min_magnitude": detail.fallback_parent_min_magnitude,
                "fallback_parent_min_nearby_galaxies": detail.fallback_parent_min_nearby_galaxies,
                "parent_marker_label": detail.parent_marker_label,
                "stellar_limit_magnitude": detail_star_profiles[detail.star_profile][0],
            }
            for detail in detail_charts
        ],
        "render_png": render_png,
        "front_matter_page_count": front_matter_pages,
        "credits_page_count": credits_page_count,
        "chart_directory": {
            "page_count": chart_directory_pages,
            "entries": [entry.to_dict() for entry in chart_directory],
            "detail_entries": [entry.to_dict() for entry in detail_chart_directory],
        },
        "total_hard_issues": sum(page_result.hard_issues for page_result in results),
        "overview_pages": overview_page_info,
        "index": {"page_count": index_pages, **atlas_index.to_dict()},
        "data_sources": selected_sources,
        "input_fingerprints": input_fingerprints,
        "geometry_inputs": geometry_inputs,
        "geometry_catalogues": geometry_catalogues,
        "publication_preflight": {
            "requested": publication,
            "inputs_passed": True if publication else None,
            "output_passed": (
                not any(page.hard_issues for page in results) if publication else None
            ),
        },
        "pages": [page_result.to_dict() for page_result in results],
    }
    draft_report_path: Path | None = None
    if write_draft_report and atlas.tiling is not None:
        with progress.step("write draft report", detail=True):
            draft_report = build_draft_report(
                atlas_path=atlas_path,
                pages=[page_result.to_dict() for page_result in results],
            )
            draft_report_path = outroot / "draft-report.json"
            draft_report_path.write_text(
                json.dumps(draft_report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        progress.info(f"draft report -> {draft_report_path}")
        print(render_text_summary(draft_report))

    artifact_paths = ["atlas.pdf"]
    for page_result in results:
        artifact_paths.append(f"charts/{page_result.chart_id}/chart.pdf")
        if render_png:
            artifact_paths.append(f"charts/{page_result.chart_id}/preview.png")
    if draft_report_path is not None:
        artifact_paths.append("draft-report.json")
    manifest["draft_report_written"] = draft_report_path is not None
    manifest["output_artifacts"] = {
        relative: file_sha256(outroot / relative) for relative in artifact_paths
    }
    manifest_path = outroot / "manifest.json"
    with progress.step("write manifest", detail=True):
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    if publication:
        output_issues = validate_atlas_output(outroot, publication=True)
        if output_issues:
            raise ValueError("publication output validation failed: " + "; ".join(output_issues))

    if publication and any(page.hard_issues for page in results):
        raise ValueError(
            f"publication failed: {sum(page.hard_issues for page in results)} hard layout issues; "
            f"see {manifest_path}"
        )

    return AtlasBuildResult(
        atlas_id=atlas.id,
        pages=tuple(results),
        combined_pdf=combined_pdf,
        manifest_path=manifest_path,
        draft_report_path=draft_report_path,
        index_page_count=index_pages,
        front_matter_page_count=front_matter_pages,
        credits_page_count=credits_page_count,
        chart_directory_page_count=chart_directory_pages,
    )


def _publish_staged_atlas(staged: Path, destination: Path) -> Path | None:
    backup: Path | None = None
    if destination.exists():
        candidate = destination.with_name(f".{destination.name}-previous")
        suffix = 2
        while candidate.exists():
            candidate = destination.with_name(f".{destination.name}-previous-{suffix}")
            suffix += 1
        os.replace(destination, candidate)
        backup = candidate
    try:
        os.replace(staged, destination)
    except OSError:
        if backup is not None:
            os.replace(backup, destination)
        raise
    return backup


def build_atlas(
    *,
    atlas_path: str | Path,
    style_path: str | Path,
    outdir: str | Path,
    star_store: str | Path | None = None,
    faint_star_store: str | Path | None = None,
    faint_star_limit: float | None = None,
    stars_csv: str | Path | None = None,
    dsos_path: str | Path | None = None,
    constellations_dir: str | Path | bool | None = None,
    outlines_dir: str | Path | bool | None = None,
    star_names_dir: str | Path | bool | None = None,
    observing_lists_dir: str | Path | bool | None = None,
    observing_config_path: str | Path | None = None,
    double_stars_path: str | Path | bool | None = None,
    overrides_path: str | Path | None = None,
    chart_ids: tuple[str, ...] | None = None,
    limit: int | None = None,
    optimize: bool = True,
    render_png: bool = True,
    png_dpi: float = 150.0,
    jobs: int = 1,
    write_front_matter: bool = True,
    write_overviews: bool = True,
    write_draft_report: bool = True,
    publication: bool = False,
    progress: Progress | None = None,
) -> AtlasBuildResult:
    options = dict(
        atlas_path=atlas_path,
        style_path=style_path,
        outdir=outdir,
        star_store=star_store,
        faint_star_store=faint_star_store,
        faint_star_limit=faint_star_limit,
        stars_csv=stars_csv,
        dsos_path=dsos_path,
        constellations_dir=constellations_dir,
        outlines_dir=outlines_dir,
        star_names_dir=star_names_dir,
        observing_lists_dir=observing_lists_dir,
        observing_config_path=observing_config_path,
        double_stars_path=double_stars_path,
        overrides_path=overrides_path,
        chart_ids=chart_ids,
        limit=limit,
        optimize=optimize,
        render_png=render_png,
        png_dpi=png_dpi,
        jobs=jobs,
        write_front_matter=write_front_matter,
        write_overviews=write_overviews,
        write_draft_report=write_draft_report,
        publication=publication,
        progress=progress,
    )
    if not publication:
        return _build_atlas_impl(**options)
    atlas_id = load_atlas_config(atlas_path).id
    if atlas_id in (".", "..") or Path(atlas_id).name != atlas_id:
        raise ValueError("publication atlas id must be a single directory name")
    output_parent = Path(outdir)
    output_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".{atlas_id}-staging-", dir=output_parent
    ) as temporary:
        result = _build_atlas_impl(**{**options, "outdir": temporary})
        destination = output_parent / atlas_id
        backup = _publish_staged_atlas(Path(temporary) / atlas_id, destination)
        if backup is not None and progress is not None:
            progress.info(f"previous publication retained -> {backup}")
        return replace(
            result,
            combined_pdf=destination / "atlas.pdf",
            manifest_path=destination / "manifest.json",
            draft_report_path=(
                destination / "draft-report.json" if result.draft_report_path is not None else None
            ),
        )
