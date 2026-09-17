"""Reusable single-chart build context.

Loads configuration and catalogue inputs and assembles the scene, page and
page transform for one chart.  Both the CLI and the AI benchmark use this so
they cannot drift apart.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from pathlib import Path

from nightsky_atlas.atlas.config import (
    AtlasConfig,
    ConfigError,
    StyleConfig,
    load_atlas_config,
    load_style_config,
)
from nightsky_atlas.atlas.observing_config import (
    DEFAULT_CONFIG_PATH as OBSERVING_CONFIG_PATH,
)
from nightsky_atlas.atlas.observing_config import (
    ObservingListsConfig,
    load_observing_lists_config,
    resolve_edition,
)
from nightsky_atlas.catalog.constellations import (
    DEFAULT_FIXTURE_DIR as CONSTELLATION_FIXTURE_DIR,
)
from nightsky_atlas.catalog.constellations import (
    load_constellations,
)
from nightsky_atlas.catalog.dso_store import load_dso_catalog
from nightsky_atlas.catalog.models import DeepSkyObject, Star
from nightsky_atlas.catalog.observing_lists import (
    DEFAULT_FIXTURE_DIR as OBSERVING_LISTS_FIXTURE_DIR,
)
from nightsky_atlas.catalog.observing_lists import (
    ObservingList,
    build_membership_index,
    load_observing_lists,
)
from nightsky_atlas.catalog.outlines import (
    DEFAULT_FIXTURE_DIR as OUTLINE_FIXTURE_DIR,
)
from nightsky_atlas.catalog.outlines import (
    load_outlines,
)
from nightsky_atlas.catalog.sample import load_sample_stars
from nightsky_atlas.catalog.selection import SelectionPolicy
from nightsky_atlas.catalog.store import StarStore, chart_query_box
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.chart.page import PageTransform
from nightsky_atlas.scene.builder import build_scene
from nightsky_atlas.scene.models import ChartScene

__all__ = [
    "ChartContext",
    "build_chart_context",
    "find_chart",
    "load_chart_stars",
]

DEFAULT_DSO_PATH = Path("data/processed/dso/openngc.json")


def find_chart(atlas: AtlasConfig, chart_id: str) -> ChartDefinition:
    """Return the named chart definition from an atlas."""
    for chart in atlas.charts:
        if chart.id == chart_id:
            return chart.to_definition(atlas_id=atlas.id)
    raise ConfigError(f"chart {chart_id!r} not found in atlas {atlas.id!r}")


def load_chart_stars(
    definition: ChartDefinition,
    *,
    star_store: str | Path | None = None,
    stars_csv: str | Path | None = None,
    magnitude_limit: float | None = None,
) -> list[Star]:
    """Load stars for a chart from a processed store or a sample CSV."""
    if star_store is not None:
        with StarStore.open(star_store) as store:
            box = chart_query_box(definition)
            return store.query_box(
                box, magnitude_limit=math.inf if magnitude_limit is None else magnitude_limit
            )
    if stars_csv is None:
        return []
    stars = load_sample_stars(stars_csv)
    if magnitude_limit is not None:
        stars = [star for star in stars if star.magnitude <= magnitude_limit]
    return stars


def load_dsos(dsos_path: str | Path | None = None) -> list[DeepSkyObject]:
    """Load deep-sky objects from a processed catalogue, or none."""
    path = Path(dsos_path) if dsos_path is not None else DEFAULT_DSO_PATH
    if not path.exists():
        if dsos_path is not None:
            raise FileNotFoundError(f"deep-sky catalogue not found: {path}")
        return []
    return load_dso_catalog(path)


@dataclass(frozen=True, slots=True)
class ChartContext:
    """Everything needed to render or review one chart."""

    atlas: AtlasConfig
    style: StyleConfig
    definition: ChartDefinition
    page: PageGeometry
    scene: ChartScene
    transform: PageTransform
    observing_lists: dict[str, ObservingList] | None = None
    selection_policy: SelectionPolicy | None = None


def build_chart_context(
    *,
    atlas_path: str | Path,
    style_path: str | Path,
    chart_id: str | None = None,
    definition: ChartDefinition | None = None,
    star_store: str | Path | None = None,
    stars_csv: str | Path | None = None,
    dsos_path: str | Path | None = None,
    constellations_dir: str | Path | None = None,
    outlines_dir: str | Path | None = None,
    observing_lists_dir: str | Path | None = None,
    observing_config_path: str | Path | None = None,
    magnitude_limit: float | None = None,
    dso_magnitude_limit: float | None = None,
) -> ChartContext:
    """Assemble a chart context from configuration and catalogue inputs.

    Provide either ``chart_id`` (looked up in the atlas file) or an explicit
    ``definition`` (e.g. a generated tiling chart).  Observing-list membership
    and the edition's selection policy drive which deep-sky objects are forced
    into the scene; a missing fixture directory or policy file simply disables
    that behaviour.
    """
    atlas = load_atlas_config(atlas_path)
    style = load_style_config(style_path)
    if definition is None:
        if chart_id is None:
            raise ConfigError("either chart_id or definition is required")
        definition = find_chart(atlas, chart_id)
    page = atlas.page.to_geometry()

    star_limit = (
        magnitude_limit if magnitude_limit is not None else atlas.stellar_limit_magnitude
    )
    stars = load_chart_stars(
        definition,
        star_store=star_store,
        stars_csv=stars_csv,
        magnitude_limit=star_limit,
    )
    dsos = load_dsos(dsos_path)
    dso_limit = (
        dso_magnitude_limit
        if dso_magnitude_limit is not None
        else atlas.dso_limit_magnitude
    )
    constellations = load_constellations(
        constellations_dir
        if constellations_dir is not None
        else CONSTELLATION_FIXTURE_DIR
    )
    outlines = load_outlines(
        outlines_dir if outlines_dir is not None else OUTLINE_FIXTURE_DIR
    )

    observing_lists = load_observing_lists(
        observing_lists_dir
        if observing_lists_dir is not None
        else OBSERVING_LISTS_FIXTURE_DIR
    )
    selection_policy = _selection_policy(
        atlas,
        observing_config_path
        if observing_config_path is not None
        else OBSERVING_CONFIG_PATH,
    )

    scene = build_scene(
        definition,
        stars,
        dsos,
        dso_magnitude_limit=dso_limit,
        constellation_lines=constellations.lines,
        constellation_boundaries=constellations.boundaries,
        nebula_outlines=outlines,
        observing_index=build_membership_index(observing_lists),
        selection_policy=selection_policy,
    )
    transform = PageTransform(chart=definition, page=page)
    return ChartContext(
        atlas=atlas,
        style=style,
        definition=definition,
        page=page,
        scene=scene,
        transform=transform,
        observing_lists=observing_lists,
        selection_policy=selection_policy,
    )


def _selection_policy(atlas: AtlasConfig, config_path: str | Path) -> SelectionPolicy:
    """Resolve the selection policy for an atlas edition.

    Observing-list rules come from ``config_path`` (an absent file simply yields
    no forced lists).  The edition's per-type visibility limits always apply, so
    deep-sky selection is never a single global magnitude cut.
    """
    config: ObservingListsConfig = load_observing_lists_config(config_path)
    policy = resolve_edition(config, atlas.id)
    return replace(policy, visibility=atlas.visibility.to_limits())