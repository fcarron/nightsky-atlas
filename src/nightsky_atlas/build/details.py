"""Resolve and prepare detail charts before main-chart label fallback."""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from nightsky_atlas.atlas.config import (
    DetailChartConfig,
    EditionConfig,
    StyleConfig,
    load_atlas_config,
    load_style_config,
)
from nightsky_atlas.build.chart import (
    ChartContext,
    ChartInputs,
    _require_mandatory_labels,
    build_chart_context,
)
from nightsky_atlas.build.progress import Progress
from nightsky_atlas.catalog.models import Star
from nightsky_atlas.catalog.star_names import (
    StarName,
    hip_number,
)
from nightsky_atlas.catalog.systems import StarSystem
from nightsky_atlas.chart.models import ChartDefinition
from nightsky_atlas.chart.presentation import (
    ChartPresentation,
    presentation_from_edition,
)
from nightsky_atlas.layout.labels import build_labels
from nightsky_atlas.layout.models import Label
from nightsky_atlas.layout.optimizer import layout_cost, optimize_labels
from nightsky_atlas.layout.overrides import (
    OverridesLibrary,
    apply_overrides,
)
from nightsky_atlas.layout.selection import select_labels
from nightsky_atlas.layout.validation import ValidationResult, validate_layout
from nightsky_atlas.render.furniture import furniture_obstacles
from nightsky_atlas.scene.models import ChartScene

DEFAULT_FAINT_STAR_STORE = Path("data/processed/stars/faint_stars.sqlite")


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


def _profile_config_path(source_path: str | Path, profile_name: str) -> Path:
    source = Path(source_path)
    sibling = source.with_name(f"{profile_name}.yaml")
    if sibling.is_file():
        return sibling
    config_family = "atlas" if source.parent.name == "atlas" else "styles"
    shared = Path(__file__).resolve().parents[3] / config_family / f"{profile_name}.yaml"
    if shared.is_file():
        return shared
    return sibling


def _detail_style(
    detail: DetailChartConfig,
    style: StyleConfig,
    dso_profile: StyleConfig | None = None,
) -> StyleConfig:
    if dso_profile is not None:
        style = style.model_copy(update={"dso": dso_profile.dso})
    constellation = {}
    for key, value in (
        ("names", detail.show_constellation_names),
        ("lines", detail.show_constellation_figures),
        ("boundaries", detail.show_constellation_boundaries),
    ):
        if value is not None:
            current = getattr(style.constellation, key)
            constellation[key] = current.model_copy(update={"enabled": value})
    if not constellation:
        return style
    return style.model_copy(
        update={"constellation": style.constellation.model_copy(update=constellation)}
    )


def _detail_scene(detail: DetailChartConfig, scene: ChartScene) -> ChartScene:
    if not detail.objects:
        return scene
    dsos = []
    for scene_dso in scene.deep_sky_objects:
        config = detail.objects.get(scene_dso.dso.id)
        if config is None:
            dsos.append(scene_dso)
            continue
        updates = {}
        if config.show_symbol is not None:
            updates["symbol_visible"] = config.show_symbol
        if config.show_label is not None:
            updates["label_visible"] = config.show_label
        if updates:
            scene_dso = replace(scene_dso, **updates)
        dsos.append(scene_dso)
    return replace(scene, deep_sky_objects=tuple(dsos))


def _detail_faint_star_inputs(
    detail: DetailChartConfig,
    *,
    profile_limit: float,
    faint_star_store: str | Path | None,
    faint_star_limit: float | None,
) -> tuple[str | Path | None, float | None]:
    include_ucac4 = (
        faint_star_store is not None
        if detail.stars.include_ucac4 is None
        else detail.stars.include_ucac4
    )
    if not include_ucac4:
        return None, None
    store = faint_star_store if faint_star_store is not None else DEFAULT_FAINT_STAR_STORE
    if not Path(store).is_file():
        raise FileNotFoundError(
            f"detail chart {detail.code} requests UCAC4 stars, but {store} is missing; "
            "provide --faint-star-store or create the local UCAC4 supplement"
        )
    limit = detail.stars.magnitude_limit or profile_limit
    if faint_star_limit is not None:
        limit = min(limit, faint_star_limit)
    return store, limit


def _detail_presentation(
    detail: DetailChartConfig,
    *,
    edition: EditionConfig,
    main_charts: tuple[ChartDefinition, ...],
    parent_chart_ids: tuple[str, ...],
    stellar_limit_magnitude: float,
) -> ChartPresentation:
    parents = {chart.id: chart for chart in main_charts}
    parent_codes = tuple(
        presentation_from_edition(parents[chart_id], edition).chart_code
        for chart_id in parent_chart_ids
    )
    parent_code = parent_codes[0] if parent_codes else None
    field = f"{detail.width_deg:g}° × {detail.height_deg:g}°"
    parent_text = ", ".join(parent_codes) if parent_codes else "none"
    return ChartPresentation(
        edition_name=edition.name,
        edition_code=edition.code,
        chart_index=None,
        internal_chart_id=detail.code,
        page_heading=f"{detail.code} · {detail.name}",
        page_footer=(
            f"{edition.name} · {detail.code} · {detail.mm_per_degree:g} mm/° · "
            f"stars to {stellar_limit_magnitude:g} · {field} · Main charts {parent_text}"
        ),
        page_footer_target=parent_code,
    )


@dataclass(frozen=True, slots=True)
class _PreparedDetail:
    """One validated detail layout; a None override count means no override document."""

    context: ChartContext
    presentation: ChartPresentation
    stellar_limit_magnitude: float
    faint_star_limit: float | None
    overrides_applied: int | None
    style: StyleConfig
    labels: tuple[Label, ...]
    cost_before: float
    cost_after: float
    validation: ValidationResult
    label_diagnostics: dict[str, dict[str, Any]] = field(default_factory=dict)


def _verified_detail_dso_label_ids(
    scene: ChartScene,
    labels: tuple[Label, ...],
    validation: ValidationResult,
) -> frozenset[str]:
    """Return visible DSO IDs whose detail labels are placed and hard-clean."""
    placed_label_ids = {
        label.id for label in labels if not label.hidden and label.effective_candidate() is not None
    }
    problematic_label_ids = {
        element_id for issue in validation.issues for element_id in issue.element_ids
    }
    return frozenset(
        scene_dso.dso.id
        for scene_dso in scene.deep_sky_objects
        if scene_dso.symbol_visible
        and f"label:dso:{scene_dso.dso.id}" in placed_label_ids
        and f"label:dso:{scene_dso.dso.id}" not in problematic_label_ids
    )


def resolve_detail_profiles(
    details: tuple[DetailChartConfig, ...],
    atlas_path: str | Path,
    style_path: str | Path,
    style: StyleConfig,
) -> tuple[dict[str, tuple[float, StyleConfig]], dict[str, StyleConfig]]:
    """Resolve distinct stellar and DSO profiles before taking input fingerprints."""
    detail_star_profiles: dict[str, tuple[float, StyleConfig]] = {}
    profile_styles: dict[str, StyleConfig] = {}
    for profile_name in sorted({detail.star_profile for detail in details}):
        profile_atlas_path = _profile_config_path(atlas_path, profile_name)
        profile_style_path = _profile_config_path(style_path, profile_name)
        profile_atlas = load_atlas_config(profile_atlas_path)
        profile_style = load_style_config(profile_style_path)
        profile_styles[profile_name] = profile_style
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
    detail_dso_profiles = {
        profile_name: (
            profile_styles[profile_name]
            if profile_name in profile_styles
            else load_style_config(_profile_config_path(style_path, profile_name))
        )
        for profile_name in sorted(
            {detail.dso_profile for detail in details if detail.dso_profile is not None}
        )
    }
    return detail_star_profiles, detail_dso_profiles


def prepare_detail_charts(
    details: tuple[DetailChartConfig, ...],
    *,
    atlas_path: str | Path,
    style_path: str | Path,
    inputs: ChartInputs,
    all_charts: tuple[ChartDefinition, ...],
    parent_chart_ids: dict[str, tuple[str, ...]],
    star_profiles: dict[str, tuple[float, StyleConfig]],
    dso_profiles: dict[str, StyleConfig],
    star_store: str | Path | None,
    faint_star_store: str | Path | None,
    faint_star_limit: float | None,
    stars_csv: str | Path | None,
    double_stars_path: str | Path | bool | None,
    star_systems: tuple[StarSystem, ...],
    star_names: dict[int, StarName],
    library: OverridesLibrary | None,
    optimize: bool,
    progress: Progress,
) -> dict[str, _PreparedDetail]:
    """Prepare each detail once, retaining its resolved rendering settings."""
    atlas = inputs.atlas
    edition = atlas.resolved_edition()
    detail_star_profiles = star_profiles
    detail_dso_profiles = dso_profiles
    selected_detail_parent_chart_ids = parent_chart_ids
    prepared_details: dict[str, _PreparedDetail] = {}
    for detail in details:
        definition = detail.to_definition(atlas_id=atlas.id)
        profile_limit, profile_style = detail_star_profiles[detail.star_profile]
        stellar_limit_magnitude = detail.stars.magnitude_limit or profile_limit
        detail_style = _detail_style(
            detail,
            profile_style,
            detail_dso_profiles.get(detail.dso_profile),
        )
        detail_faint_star_store, detail_faint_limit = _detail_faint_star_inputs(
            detail,
            profile_limit=stellar_limit_magnitude,
            faint_star_store=faint_star_store,
            faint_star_limit=faint_star_limit,
        )
        detail_context = build_chart_context(
            atlas_path=atlas_path,
            style_path=style_path,
            definition=definition,
            star_store=star_store,
            faint_star_store=detail_faint_star_store,
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
        detail_context = replace(detail_context, scene=_detail_scene(detail, detail_context.scene))
        detail_labels = build_labels(
            detail_context.scene,
            detail_context.transform,
            detail_style,
            star_names,
            required_star_hips=detail.stars.named_labels,
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
        detail_presentation = _detail_presentation(
            detail,
            edition=edition,
            main_charts=all_charts,
            parent_chart_ids=selected_detail_parent_chart_ids[detail.id],
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
            presentation=detail_presentation,
            stellar_limit_magnitude=stellar_limit_magnitude,
            faint_star_limit=detail_faint_limit,
            overrides_applied=(len(detail_overrides) if detail_overrides is not None else None),
            style=detail_style,
            labels=detail_labels,
            cost_before=detail_cost_before,
            cost_after=detail_cost_after,
            validation=detail_validation,
            label_diagnostics=optimized.label_diagnostics if optimize else {},
        )
    return prepared_details


def verified_detail_star_hips(
    prepared: _PreparedDetail, excluded_hips: tuple[int, ...]
) -> frozenset[int]:
    """Verify intentionally excluded main-chart stars against the actual detail layout."""
    problematic_label_ids = {
        element_id for issue in prepared.validation.issues for element_id in issue.element_ids
    }
    placed_targets = {
        label.target_id
        for label in prepared.labels
        if not label.hidden and label.effective_candidate() is not None
    }
    return frozenset(
        hip
        for scene_star in prepared.context.scene.stars
        if isinstance(scene_star.star, Star)
        and (hip := hip_number(scene_star.star.hip_id)) in excluded_hips
        and scene_star.star.id in placed_targets
        and f"label:star:{scene_star.star.id}" not in problematic_label_ids
    )
