"""Reusable single-chart build context.

Loads configuration and catalogue inputs and assembles the scene, page and
page transform for one chart.  Both the CLI and the AI benchmark use this so
they cannot drift apart.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
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
from nightsky_atlas.atlas.tiling import chart_definitions
from nightsky_atlas.build.progress import Progress, null_progress
from nightsky_atlas.catalog.constellations import (
    DEFAULT_FIXTURE_DIR as CONSTELLATION_FIXTURE_DIR,
)
from nightsky_atlas.catalog.constellations import (
    ConstellationCatalogue,
    load_constellations,
)
from nightsky_atlas.catalog.dso_store import load_dso_catalog
from nightsky_atlas.catalog.models import DeepSkyObject, DsoType, Star
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
    NebulaOutline,
    load_outlines,
)
from nightsky_atlas.catalog.sample import load_sample_stars
from nightsky_atlas.catalog.selection import SelectionPolicy
from nightsky_atlas.catalog.store import QueryBox, StarStore, chart_query_box
from nightsky_atlas.catalog.systems import (
    DEFAULT_AMBIGUOUS_RADIUS_ARCSEC,
    DEFAULT_COMPANION_TOLERANCE_ARCSEC,
    DEFAULT_MATCH_TOLERANCE_ARCSEC,
    StarSystem,
    load_system_catalog,
    match_star_systems,
)
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.chart.page import PageTransform
from nightsky_atlas.scene.builder import build_scene
from nightsky_atlas.scene.models import ChartScene

__all__ = [
    "ChartContext",
    "ChartInputs",
    "build_chart_context",
    "find_chart",
    "load_chart_inputs",
    "load_chart_stars",
]

OPENNGC_OUTLINE_DIR = Path("data/processed/outlines")

DEFAULT_DSO_PATH = Path("data/processed/dso/openngc.json")
DEFAULT_DOUBLE_STAR_PATH = Path("data/processed/double_stars/wds.json")


def find_chart(atlas: AtlasConfig, chart_id: str) -> ChartDefinition:
    """Return the named chart definition from an atlas.

    Explicit ``charts`` are checked first; atlases defined by tiling fall back
    to the generated chart set, so per-chart commands work on tiled ids such as
    ``standard-068``.
    """
    for chart in atlas.charts:
        if chart.id == chart_id:
            return chart.to_definition(atlas_id=atlas.id)
    for chart in chart_definitions(atlas):
        if chart.id == chart_id:
            return chart
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
        if not Path(star_store).exists():
            raise FileNotFoundError(
                f"star store not found: {star_store}; run 'nightsky data import-stars' "
                "or pass --stars for a small fixture"
            )
        with StarStore.open(star_store) as store:
            box = chart_query_box(definition)
            return store.query_box(
                box, magnitude_limit=math.inf if magnitude_limit is None else magnitude_limit
            )
    if stars_csv is None:
        return []
    if not Path(stars_csv).exists():
        raise FileNotFoundError(f"star CSV not found: {stars_csv}")
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


def load_star_systems(systems_path: str | Path | bool | None = None) -> list[StarSystem]:
    """Load the processed double/multiple star overlay, or none."""
    if systems_path is False:
        return []
    path = Path(systems_path) if systems_path is not None else DEFAULT_DOUBLE_STAR_PATH
    if not path.exists():
        if systems_path is not None:
            raise FileNotFoundError(f"double-star catalogue not found: {path}")
        return []
    return load_system_catalog(path)


@dataclass(frozen=True, slots=True)
class ChartInputs:
    """Configuration and catalogue fixtures shared by every chart in a build.

    Loading these once avoids re-parsing large catalogue files per chart; the
    per-chart work (star query, double-star match, scene) is still done by
    :func:`build_chart_context`.
    """

    atlas: AtlasConfig
    style: StyleConfig
    dsos: tuple[DeepSkyObject, ...]
    constellations: ConstellationCatalogue
    outlines: tuple[NebulaOutline, ...]
    observing_lists: dict[str, ObservingList]
    selection_policy: SelectionPolicy


def load_chart_inputs(
    *,
    atlas_path: str | Path,
    style_path: str | Path,
    dsos_path: str | Path | None = None,
    constellations_dir: str | Path | bool | None = None,
    outlines_dir: str | Path | bool | None = None,
    observing_lists_dir: str | Path | bool | None = None,
    observing_config_path: str | Path | None = None,
    atlas: AtlasConfig | None = None,
    style: StyleConfig | None = None,
    progress: Progress | None = None,
) -> ChartInputs:
    """Load the configuration and catalogue fixtures shared by all charts."""
    progress = progress if progress is not None else null_progress()
    with progress.step("config load", detail=True):
        if atlas is None:
            atlas = load_atlas_config(atlas_path)
        if style is None:
            style = load_style_config(style_path)
    with progress.step("dso load", detail=True):
        dsos = tuple(load_dsos(dsos_path))
    with progress.step("constellation/outline load", detail=True):
        constellations = (
            ConstellationCatalogue()
            if constellations_dir is False
            else load_constellations(
                constellations_dir
                if constellations_dir is not None
                else CONSTELLATION_FIXTURE_DIR
            )
        )
        if outlines_dir is False:
            fallback_outlines = ()
            openngc_outlines = ()
        else:
            selected_outline_dir = (
                Path(outlines_dir) if outlines_dir is not None else OUTLINE_FIXTURE_DIR
            )
            fallback_outlines = load_outlines(selected_outline_dir)
            openngc_outlines = (
                load_outlines(OPENNGC_OUTLINE_DIR)
                if selected_outline_dir == OUTLINE_FIXTURE_DIR
                else ()
            )
        outlines = _prefer_openngc_outlines(dsos, fallback_outlines, openngc_outlines)
    with progress.step("observing-list load", detail=True):
        observing_lists = (
            {}
            if observing_lists_dir is False
            else load_observing_lists(
                observing_lists_dir
                if observing_lists_dir is not None
                else OBSERVING_LISTS_FIXTURE_DIR
            )
        )
        selection_policy = _selection_policy(
            atlas,
            observing_config_path if observing_config_path is not None else OBSERVING_CONFIG_PATH,
        )
    return ChartInputs(
        atlas=atlas,
        style=style,
        dsos=dsos,
        constellations=constellations,
        outlines=outlines,
        observing_lists=observing_lists,
        selection_policy=selection_policy,
    )


def _prefer_openngc_outlines(
    dsos: tuple[DeepSkyObject, ...],
    fallback: tuple[NebulaOutline, ...],
    openngc: tuple[NebulaOutline, ...],
) -> tuple[NebulaOutline, ...]:
    """Prefer OpenNGC contours only for large diffuse nebulae."""
    eligible_ids = {
        dso.id
        for dso in dsos
        if dso.object_type
        in (DsoType.BRIGHT_NEBULA, DsoType.SUPERNOVA_REMNANT, DsoType.DARK_NEBULA)
    }
    preferred = tuple(outline for outline in openngc if outline.dso_id in eligible_ids)
    preferred_ids = {outline.dso_id for outline in preferred}
    return tuple(outline for outline in fallback if outline.dso_id not in preferred_ids) + preferred


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
    star_systems: tuple[StarSystem, ...] = ()


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
    double_stars_path: str | Path | bool | None = None,
    star_systems: Sequence[StarSystem] | None = None,
    double_star_match_tolerance_arcsec: float = DEFAULT_MATCH_TOLERANCE_ARCSEC,
    double_star_companion_tolerance_arcsec: float = DEFAULT_COMPANION_TOLERANCE_ARCSEC,
    double_star_ambiguous_radius_arcsec: float = DEFAULT_AMBIGUOUS_RADIUS_ARCSEC,
    magnitude_limit: float | None = None,
    scale_mm_per_degree: float | None = None,
    progress: Progress | None = None,
    inputs: ChartInputs | None = None,
) -> ChartContext:
    """Assemble a chart context from configuration and catalogue inputs.

    Provide either ``chart_id`` (looked up in the atlas file) or an explicit
    ``definition`` (e.g. a generated tiling chart).  Observing-list membership
    and the edition's selection policy drive which deep-sky objects are forced
    into the scene; a missing fixture directory or policy file simply disables
    that behaviour.
    """
    progress = progress if progress is not None else null_progress()
    if inputs is None:
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
    if definition is None:
        if chart_id is None:
            raise ConfigError("either chart_id or definition is required")
        definition = find_chart(atlas, chart_id)
    page = atlas.page.to_geometry()

    star_limit = magnitude_limit if magnitude_limit is not None else atlas.stellar_limit_magnitude
    with progress.step("star query", detail=True):
        stars = load_chart_stars(
            definition,
            star_store=star_store,
            stars_csv=stars_csv,
            magnitude_limit=star_limit,
        )
    # Keep outlined objects available even when their centres lie beyond the
    # field query box: their projected polygons can still cross this chart.
    dso_box = field_query_box(definition, padding_deg=2.0)
    outlined_dso_ids = {outline.dso_id for outline in inputs.outlines}
    dsos = tuple(
        dso for dso in inputs.dsos
        if dso.id in outlined_dso_ids
        or _coordinates_in_box(dso.ra_deg, dso.dec_deg, dso_box)
    )
    # Deep-sky selection is governed entirely by the edition's per-type
    # visibility rules; there is no global magnitude cut in the atlas config.
    constellations = inputs.constellations
    outlines = inputs.outlines
    observing_lists = inputs.observing_lists
    selection_policy = inputs.selection_policy

    with progress.step("double-star match", detail=True):
        all_systems = (
            list(star_systems) if star_systems is not None else load_star_systems(double_stars_path)
        )
        box = chart_query_box(definition, padding_deg=1.0)
        nearby_systems = [system for system in all_systems if _system_in_box(system, box)]
        matched_systems = match_star_systems(
            nearby_systems,
            stars,
            tolerance_arcsec=double_star_match_tolerance_arcsec,
            companion_tolerance_arcsec=double_star_companion_tolerance_arcsec,
            ambiguous_radius_arcsec=double_star_ambiguous_radius_arcsec,
        )

    with progress.step("scene build", detail=True):
        scene = build_scene(
            definition,
            stars,
            dsos,
            constellation_lines=constellations.lines,
            constellation_boundaries=constellations.boundaries,
            nebula_outlines=outlines,
            star_systems=matched_systems,
            observing_index=build_membership_index(observing_lists),
            selection_policy=selection_policy,
        )
    transform = PageTransform(
        chart=definition,
        page=page,
        scale_mm_per_degree=(
            scale_mm_per_degree if scale_mm_per_degree is not None else atlas.mm_per_degree
        ),
    )
    return ChartContext(
        atlas=atlas,
        style=style,
        definition=definition,
        page=page,
        scene=scene,
        transform=transform,
        observing_lists=observing_lists,
        selection_policy=selection_policy,
        star_systems=matched_systems,
    )


def field_query_box(definition: ChartDefinition, *, padding_deg: float = 2.0) -> QueryBox:
    """Return a radial query box that reaches the projected field corners.

    :func:`nightsky_atlas.catalog.store.chart_query_box` sizes the declination
    range from half the chart height, but the projected field reaches further
    at its corners.  Using the corner radius as both half-extents yields a
    superset of the field, so pre-filtering a catalogue never drops an object
    the scene builder would keep.
    """
    radius = math.hypot(definition.width_deg / 2.0, definition.height_deg / 2.0) + padding_deg
    dec_min = max(-90.0, definition.center_dec_deg - radius)
    dec_max = min(90.0, definition.center_dec_deg + radius)
    worst_dec = min(89.9, max(abs(dec_min), abs(dec_max)))
    cos_dec = math.cos(math.radians(worst_dec))
    if cos_dec < 0.02:
        return QueryBox(0.0, 360.0, dec_min, dec_max)
    half_width = radius / cos_dec
    if half_width >= 180.0:
        return QueryBox(0.0, 360.0, dec_min, dec_max)
    ra_min = (definition.center_ra_deg - half_width) % 360.0
    ra_max = (definition.center_ra_deg + half_width) % 360.0
    return QueryBox(ra_min, ra_max, dec_min, dec_max)


def _coordinates_in_box(ra_deg: float, dec_deg: float, box: QueryBox) -> bool:
    """Return whether a position falls inside a catalogue query box."""
    if not box.dec_min_deg <= dec_deg <= box.dec_max_deg:
        return False
    if box.wraps_ra:
        return ra_deg >= box.ra_min_deg or ra_deg <= box.ra_max_deg
    return box.ra_min_deg <= ra_deg <= box.ra_max_deg


def _system_in_box(system: StarSystem, box: QueryBox) -> bool:
    """Return whether a system position falls inside a catalogue query box."""
    if system.ra_deg is None or system.dec_deg is None:
        return False
    return _coordinates_in_box(system.ra_deg, system.dec_deg, box)


def _selection_policy(atlas: AtlasConfig, config_path: str | Path) -> SelectionPolicy:
    """Resolve the selection policy for an atlas edition.

    Observing-list rules come from ``config_path`` (an absent file simply yields
    no forced lists).  The edition's per-type visibility limits always apply, so
    deep-sky selection is never a single global magnitude cut.
    """
    config: ObservingListsConfig = load_observing_lists_config(config_path)
    policy = resolve_edition(config, atlas.id)
    return replace(policy, visibility=atlas.visibility.to_limits())
