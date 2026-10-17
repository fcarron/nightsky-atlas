"""Candidate scoring, validity and spatial geometry shared by optimizer phases."""

from __future__ import annotations

from dataclasses import replace

from nightsky_atlas.atlas.config import StyleConfig
from nightsky_atlas.catalog.models import DsoType
from nightsky_atlas.chart.page import PagePoint, PageRect, PageTransform
from nightsky_atlas.layout.association import (
    SourceGeometry,
    nearest_source_geometry,
    source_edge_distance,
    source_geometries_overlap,
    source_intersects_rect,
    source_outline_edge_distance,
)
from nightsky_atlas.layout.geometry import (
    circle_intersects_rect,
    rects_overlap,
)
from nightsky_atlas.layout.labels import constellation_label_anchors
from nightsky_atlas.layout.models import Label, LabelCandidate
from nightsky_atlas.layout.scoring import (
    CostBreakdown,
    CostWeights,
    StarCircle,
    SymbolCircle,
    candidate_star_edge_distance_mm,
    foreign_star_hard_min_mm,
    rescore_candidate_interactions,
    score_candidate,
    star_source_bounds,
)
from nightsky_atlas.layout.spatial import RectIndex
from nightsky_atlas.layout.text_geometry import (
    candidate_ink_bounds,
    label_collision_bounds,
)
from nightsky_atlas.render.double_stars import (
    printed_star_obstacles,
    related_member_star_ids,
    source_member_star_ids,
)
from nightsky_atlas.render.symbols import dso_symbol_extent
from nightsky_atlas.scene.models import ChartScene

_CROWDING_RADIUS_MM = 6.0
_EDGE_MARGIN_MM = 8.0
_GRID_CELL_MM = 8.0
_SOURCE_INDEX_CACHE: dict[
    int, tuple[tuple[SourceGeometry, ...], RectIndex[SourceGeometry]]
] = {}


class _CandidateScoreCache:
    def __init__(
        self,
        anchors: dict[str, PagePoint],
        printable: PageRect,
        symbols_index: RectIndex[SymbolCircle],
        sources: tuple[SourceGeometry, ...],
        stars_index: RectIndex[StarCircle],
        stars: tuple[StarCircle, ...],
        style: StyleConfig,
        weights: CostWeights,
        constellation_lines: tuple[tuple[PagePoint, PagePoint], ...],
        furniture: tuple[PageRect, ...] = (),
        *,
        max_entries: int = 65536,
    ) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        self.anchors = anchors
        self.printable = printable
        self.symbols_index = symbols_index
        self.sources = sources
        self.source_by_id = {source.id: source for source in sources}
        self.stars_index = stars_index
        self.stars = stars
        self.style = style
        self.weights = weights
        self.constellation_lines = constellation_lines
        self.furniture = furniture
        self.max_entries = max_entries
        self._versions: dict[str, Label] = {}
        self._hits = dict.fromkeys(("static", "geometry", "validity", "rejection"), 0)
        self._misses = self._hits.copy()
        self._evictions = self._hits.copy()
        self._retained = self._hits.copy()
        self._static: dict[tuple[str, str], CostBreakdown] = {}
        self._geometry: dict[
            tuple[str, str], tuple[tuple[SymbolCircle, ...], tuple[StarCircle, ...]]
        ] = {}
        self._validity: dict[tuple[str, str], tuple[bool, PageRect]] = {}
        self._rejection: dict[tuple[str, str], str | None] = {}

    def prepare_labels(self, labels: tuple[Label, ...]) -> None:
        """Retain only entries whose complete non-placement label state matches."""
        versions = {
            label.id: replace(label, selected_candidate_id=None, hidden=False)
            for label in labels[:self.max_entries]
        }
        unchanged = {
            label_id for label_id, label in versions.items()
            if self._versions.get(label_id) == label
        }
        for name in self._hits:
            entries = getattr(self, f"_{name}")
            for key in list(entries):
                if key[0] not in unchanged:
                    del entries[key]
            self._retained[name] = len(entries)
        self._versions = versions

    def statistics(self) -> dict[str, dict[str, int]]:
        return {
            name: {
                "hits": self._hits[name], "misses": self._misses[name],
                "evictions": self._evictions[name], "retained": self._retained[name],
                "entries": len(getattr(self, f"_{name}")),
            }
            for name in self._hits
        }

    def _remember(self, name: str, key: tuple[str, str], value: object) -> None:
        entries = getattr(self, f"_{name}")
        if key not in entries and len(entries) >= self.max_entries:
            del entries[next(iter(entries))]
            self._evictions[name] += 1
        entries[key] = value

    def geometry(
        self,
        label: Label,
        candidate: LabelCandidate,
    ) -> tuple[tuple[SymbolCircle, ...], tuple[StarCircle, ...]]:
        key = (label.id, candidate.id)
        geometry = self._geometry.get(key)
        self._hits["geometry"] += geometry is not None
        self._misses["geometry"] += geometry is None
        if geometry is None:
            geometry = (
                tuple(self.symbols_index.query(candidate.bounds)),
                _nearby_stars(
                    label, candidate.bounds, self.stars_index, self.stars, self.style
                ),
            )
            self._remember("geometry", key, geometry)
        return geometry

    def valid(
        self,
        label: Label,
        candidate: LabelCandidate,
        placed_bounds: tuple[PageRect, ...],
    ) -> bool:
        key = (label.id, candidate.id)
        validity = self._validity.get(key)
        if validity is not None and not validity[0]:
            self._hits["validity"] += 1
            return False
        collision_bounds = validity[1] if validity is not None else _collision_bounds(
            label, candidate, self.style
        )
        if any(rects_overlap(collision_bounds, other) for other in placed_bounds):
            return False
        self._hits["validity"] += validity is not None
        self._misses["validity"] += validity is None
        if validity is None:
            symbols, stars = self.geometry(label, candidate)
            validity = (
                _is_valid(
                    label,
                    candidate,
                    (),
                    self.printable,
                    symbols,
                    stars,
                    self.style,
                    self.furniture,
                    self.sources,
                    self.source_by_id,
                ),
                collision_bounds,
            )
            self._remember("validity", key, validity)
        return validity[0]

    def source_rejection(self, label: Label, candidate: LabelCandidate) -> str | None:
        """Reuse source/star rejection reasons, independently of placed labels."""
        key = (label.id, candidate.id)
        present = key in self._rejection
        self._hits["rejection"] += present
        self._misses["rejection"] += not present
        if not present:
            self._remember(
                "rejection", key,
                _source_candidate_rejection_reason(
                    label, candidate, self.symbols_index, self.stars_index,
                    self.stars, self.style, self.sources,
                ),
            )
        return self._rejection[key]

    def cost(
        self,
        label: Label,
        candidate: LabelCandidate,
        placed_bounds: tuple[PageRect, ...],
        *,
        nearby_symbols: tuple[SymbolCircle, ...] | None = None,
        nearby_stars: tuple[StarCircle, ...] | None = None,
    ) -> float:
        return self.breakdown(
            label,
            candidate,
            placed_bounds,
            nearby_symbols=nearby_symbols,
            nearby_stars=nearby_stars,
        ).total(self.weights)

    def breakdown(
        self,
        label: Label,
        candidate: LabelCandidate,
        placed_bounds: tuple[PageRect, ...],
        *,
        nearby_symbols: tuple[SymbolCircle, ...] | None = None,
        nearby_stars: tuple[StarCircle, ...] | None = None,
    ) -> CostBreakdown:
        key = (label.id, candidate.id)
        static = self._static.get(key)
        self._hits["static"] += static is not None
        self._misses["static"] += static is None
        if static is None:
            if nearby_symbols is None or nearby_stars is None:
                symbols, stars = self.geometry(label, candidate)
            else:
                symbols, stars = nearby_symbols, nearby_stars
                if key not in self._geometry:
                    self._remember("geometry", key, (symbols, stars))
            static = score_candidate(
                candidate,
                target_anchor=_anchor_for(label, self.anchors, candidate),
                placed_bounds=(),
                symbols=symbols,
                stars=stars,
                associated_star_ids=_associated_star_ids(label, stars),
                related_star_ids=_related_star_ids(label, stars),
                star_clearance=self.style.label.star_clearance,
                target_source_id=_association_source_id(label),
                source_association=self.style.label.source_association,
                dso_placement=self.style.label.dso_placement,
                is_dso_label=label.id.startswith("label:dso:"),
                source_symbols=_nearby_sources(label, candidate.bounds, self.sources, self.style),
                association_scale=_association_scale(label, self.style),
                printable=self.printable,
                crowding_radius_mm=_CROWDING_RADIUS_MM,
                weights=self.weights,
                edge_margin_mm=_EDGE_MARGIN_MM,
                constellation_lines=self.constellation_lines,
            )
            self._remember("static", key, static)
        return rescore_candidate_interactions(
            static,
            candidate,
            placed_bounds,
            crowding_radius_mm=_CROWDING_RADIUS_MM,
            dso_placement=self.style.label.dso_placement,
            is_dso_label=label.id.startswith("label:dso:"),
        )


def _symbol_circles(
    scene: ChartScene, transform: PageTransform, style: StyleConfig
) -> tuple[SymbolCircle, ...]:
    symbols: list[SymbolCircle] = []
    for scene_dso in scene.deep_sky_objects:
        if not scene_dso.symbol_visible:
            continue
        extent = dso_symbol_extent(scene_dso.dso, mm_per_deg=transform.mm_per_deg, style=style)
        symbols.append(
            SymbolCircle(
                center=transform.to_page(scene_dso.chart_point),
                radius_mm=extent.collision_radius_mm,
                id=scene_dso.dso.id,
            )
        )
    return tuple(symbols)


def _star_circles(
    scene: ChartScene, transform: PageTransform, style: StyleConfig
) -> tuple[StarCircle, ...]:
    """Return every actual printed stellar disk for label-clearance geometry."""
    return tuple(
        StarCircle(
            id=star.id,
            star_ids=star.star_ids,
            center=star.page_point,
            radius_mm=star.radius_mm,
            system_ids=star.system_ids,
            marker_length_mm=star.marker_length_mm,
            marker_line_width_mm=star.marker_line_width_mm,
        )
        for star in printed_star_obstacles(scene, transform, style)
    )


def _target_anchors(
    scene: ChartScene, transform: PageTransform, style: StyleConfig
) -> dict[str, PagePoint]:
    anchors: dict[str, PagePoint] = {}
    for scene_star in scene.stars:
        anchors[scene_star.star.id] = transform.to_page(scene_star.chart_point)
    system_points: dict[str, list[PagePoint]] = {}
    for obstacle in printed_star_obstacles(scene, transform, style):
        for star_id in obstacle.star_ids:
            anchors[star_id] = obstacle.page_point
        for system_id in obstacle.system_ids:
            system_points.setdefault(system_id, []).append(obstacle.page_point)
    for system_id, points in system_points.items():
        anchors[system_id] = PagePoint(
            sum(point.x_mm for point in points) / len(points),
            sum(point.y_mm for point in points) / len(points),
        )
    for scene_dso in scene.deep_sky_objects:
        anchors[scene_dso.dso.id] = transform.to_page(scene_dso.chart_point)
    anchors.update(constellation_label_anchors(scene, transform, style))
    return anchors


def _printable(transform: PageTransform) -> PageRect:
    return PageRect(
        left_mm=transform.page.margin_mm,
        top_mm=transform.page.margin_mm,
        width_mm=transform.page.printable_width_mm,
        height_mm=transform.page.printable_height_mm,
    )


def _anchor_for(
    label: Label, anchors: dict[str, PagePoint], candidate: LabelCandidate
) -> PagePoint:
    anchor = anchors.get(label.target_id)
    if anchor is not None:
        return anchor
    return candidate.bounds.center


def _symbol_bounds(symbol: SymbolCircle) -> PageRect:
    return PageRect(
        left_mm=symbol.center.x_mm - symbol.radius_mm,
        top_mm=symbol.center.y_mm - symbol.radius_mm,
        width_mm=2.0 * symbol.radius_mm,
        height_mm=2.0 * symbol.radius_mm,
    )


def _collision_bounds(
    label: Label, candidate: LabelCandidate, style: StyleConfig
) -> PageRect:
    return label_collision_bounds(
        label,
        candidate,
        ink_clearance_mm=style.label.dso_placement.label_label_ink_clearance_mm,
    )


def _labels_overlap(
    first: Label,
    first_candidate: LabelCandidate,
    second: Label,
    second_candidate: LabelCandidate,
    style: StyleConfig,
) -> bool:
    first_bounds = _collision_bounds(first, first_candidate, style)
    second_bounds = _collision_bounds(second, second_candidate, style)
    return rects_overlap(first_bounds, second_bounds)


def _build_symbol_index(symbols: tuple[SymbolCircle, ...]) -> RectIndex[SymbolCircle]:
    index: RectIndex[SymbolCircle] = RectIndex(_GRID_CELL_MM)
    for position, symbol in enumerate(symbols):
        index.set(f"symbol:{position}", _symbol_bounds(symbol), symbol)
    return index


def _nearby_sources(
    label: Label,
    bounds: PageRect,
    sources: tuple[SourceGeometry, ...],
    style: StyleConfig,
) -> tuple[SourceGeometry, ...]:
    """Limit DSO association scoring to the local source neighborhood."""
    owner_id = _association_source_id(label)
    placement = style.label.dso_placement
    association = style.label.source_association
    margin = max(placement.candidate_edge_gaps_mm) + association.corridor_margin_mm + 1.0
    margin_sq = margin**2
    source_index = _source_spatial_index(sources)
    nearby = []
    for source in source_index.query(bounds, margin_mm=margin):
        radius = source.collision_radius_mm
        dx = max(
            bounds.left_mm - (source.center.x_mm + radius),
            0.0,
            source.center.x_mm - radius - bounds.right_mm,
        )
        dy = max(
            bounds.top_mm - (source.center.y_mm + radius),
            0.0,
            source.center.y_mm - radius - bounds.bottom_mm,
        )
        if source.id == owner_id or dx * dx + dy * dy <= margin_sq:
            nearby.append(source)
    return tuple(nearby)


def _source_spatial_index(
    sources: tuple[SourceGeometry, ...],
) -> RectIndex[SourceGeometry]:
    key = id(sources)
    cached = _SOURCE_INDEX_CACHE.get(key)
    if cached is not None and cached[0] is sources:
        return cached[1]
    index: RectIndex[SourceGeometry] = RectIndex(_GRID_CELL_MM)
    for source in sources:
        radius = source.collision_radius_mm
        index.set(
            source.id,
            PageRect(
                source.center.x_mm - radius,
                source.center.y_mm - radius,
                2.0 * radius,
                2.0 * radius,
            ),
            source,
        )
    if len(_SOURCE_INDEX_CACHE) >= 4:
        _SOURCE_INDEX_CACHE.pop(next(iter(_SOURCE_INDEX_CACHE)))
    _SOURCE_INDEX_CACHE[key] = (sources, index)
    return index


def _ownership_result(
    label: Label,
    bounds: PageRect,
    sources: tuple[SourceGeometry, ...],
    style: StyleConfig,
    *,
    all_sources: bool = False,
) -> tuple[float, float | None, SourceGeometry | None, bool]:
    considered = sources if all_sources else _nearby_sources(label, bounds, sources, style)
    owner = next((source for source in considered if source.id == label.target_id), None)
    if owner is None:
        return 0.0, None, None, False
    owner_gap = source_edge_distance(owner, bounds)
    competitors = tuple(
        source for source in considered if source.id != label.target_id
    )
    nearest = nearest_source_geometry(competitors, bounds)
    if nearest is None:
        return owner_gap, None, None, False
    foreign_gap = source_edge_distance(nearest, bounds)
    margin = foreign_gap - owner_gap
    isolated_galaxy = (
        owner.source_type == DsoType.GALAXY
        and nearest.source_type == DsoType.GALAXY
    )
    overlap_exception = isolated_galaxy and source_geometries_overlap(owner, nearest)
    near_hard_violation = (
        isolated_galaxy
        and margin < style.label.dso_placement.ownership_margin_hard_limit_mm
        and not overlap_exception
    )
    return owner_gap, margin, nearest, near_hard_violation


def _build_star_index(stars: tuple[StarCircle, ...]) -> RectIndex[StarCircle]:
    index: RectIndex[StarCircle] = RectIndex(_GRID_CELL_MM)
    for star in stars:
        index.set(star.id, star_source_bounds(star), star)
    return index


def _associated_star_ids(label: Label, stars: tuple[StarCircle, ...]) -> frozenset[str]:
    """Return the physical printed members owned by a label's source."""
    return source_member_star_ids(label.target_id, stars)


def _related_star_ids(label: Label, stars: tuple[StarCircle, ...]) -> frozenset[str]:
    """Return all printed components semantically related to a star label."""
    return related_member_star_ids(label.target_id, stars)


def _resolved_weights(style: StyleConfig, weights: CostWeights | None) -> CostWeights:
    if weights is not None:
        return weights
    clearance = style.label.star_clearance
    return CostWeights(
        label_foreign_star_clearance=clearance.foreign.weight,
        label_associated_star_clearance=clearance.associated.clearance_weight,
        label_association_distance=clearance.associated.distance_weight,
        label_source_distance=style.label.source_association.distance_weight,
        label_source_facing_edge_distance=0.0,
        label_source_corridor=style.label.source_association.corridor_weight,
        label_competing_source_ambiguity=style.label.source_association.ambiguity_weight,
        label_competing_owner=style.label.source_association.competing_owner_weight,
        label_glyph_proximity=style.label.source_association.glyph_weight,
        label_foreign_object_proximity=(
            style.label.source_association.foreign_object_weight
        ),
        label_ownership_margin=style.label.dso_placement.ownership_margin_weight,
    )


def _star_query_margin_mm(style: StyleConfig) -> float:
    foreign = style.label.star_clearance.foreign
    return max(
        foreign.soft_clear_mm + style.star.max_diameter_mm / 2.0 * foreign.radius_clearance_factor,
        style.label.star_clearance.associated.preferred_max_mm,
    )


def _nearby_stars(
    label: Label,
    bounds: PageRect,
    index: RectIndex[StarCircle],
    stars: tuple[StarCircle, ...],
    style: StyleConfig,
) -> tuple[StarCircle, ...]:
    queried = tuple(index.query(bounds, margin_mm=_star_query_margin_mm(style)))
    if not label.id.startswith("label:star:"):
        return tuple(sorted(queried, key=lambda star: star.id))
    known_ids = {star.id for star in queried}
    associated = tuple(
        star for star in stars if label.target_id in star.star_ids and star.id not in known_ids
    )
    related_ids = _related_star_ids(label, stars)
    related = tuple(
        star
        for star in stars
        if related_ids & star.star_ids and star.id not in known_ids
    )
    by_id = {star.id: star for star in (*queried, *associated, *related)}
    return tuple(sorted(by_id.values(), key=lambda star: star.id))


def _is_valid(
    label: Label,
    candidate: LabelCandidate,
    placed_bounds: tuple[PageRect, ...],
    printable: PageRect,
    symbols: tuple[SymbolCircle, ...],
    stars: tuple[StarCircle, ...],
    style: StyleConfig,
    furniture: tuple[PageRect, ...] = (),
    source_geometries: tuple[SourceGeometry, ...] | None = None,
    source_by_id: dict[str, SourceGeometry] | None = None,
) -> bool:
    bounds = candidate.bounds
    collision_bounds = _collision_bounds(label, candidate, style)
    if (
        bounds.left_mm < printable.left_mm
        or bounds.top_mm < printable.top_mm
        or bounds.right_mm > printable.right_mm
        or bounds.bottom_mm > printable.bottom_mm
    ):
        return False
    if any(rects_overlap(collision_bounds, other) for other in placed_bounds):
        return False
    if any(rects_overlap(bounds, obstacle) for obstacle in furniture):
        return False
    source_bounds = (
        candidate_ink_bounds(candidate) if label.id.startswith("label:dso:") else bounds
    )
    if source_geometries is None:
        if any(
            circle_intersects_rect(symbol.center, symbol.radius_mm, source_bounds)
            for symbol in symbols
        ):
            return False
    else:
        if source_by_id is None:
            source_by_id = {source.id: source for source in source_geometries}
        source_conflict = any(
            source_intersects_rect(source_by_id[symbol.id], source_bounds)
            for symbol in symbols
            if symbol.id in source_by_id
        )
        if source_conflict:
            return False
    if label.id.startswith("label:dso:") and source_geometries is not None:
        _, _, _, wrong_owner = _ownership_result(
            label, candidate_ink_bounds(candidate), source_geometries, style
        )
        if wrong_owner:
            return False
    related = _related_star_ids(label, stars)
    for star in stars:
        hard_min = style.label.star_clearance.associated.hard_min_mm if (
            related & star.star_ids
        ) else foreign_star_hard_min_mm(star.radius_mm, style.label.star_clearance)
        if candidate_star_edge_distance_mm(
            star,
            candidate,
            visible_text=label.id.startswith(("label:star:", "label:dso:")),
        ) < hard_min:
            return False
    return True


def _association_scale(label: Label, style: StyleConfig) -> float:
    compact_text = "".join(label.text.split())
    if label.id.startswith("label:star:") and len(compact_text) <= 3:
        return style.label.source_association.compact_label_factor
    if label.id.startswith("label:dso:") and len(compact_text) <= 4:
        return style.label.dso_placement.compact_label_factor
    return 1.0


def _association_source_id(label: Label) -> str | None:
    if label.id.startswith(("label:star:", "label:dso:")):
        return label.target_id
    return None


def _candidate_breakdown(
    label: Label,
    candidate: LabelCandidate,
    anchors: dict[str, PagePoint],
    printable: PageRect,
    placed_index: RectIndex[PageRect],
    symbols_index: RectIndex[SymbolCircle],
    sources: tuple[SourceGeometry, ...],
    stars_index: RectIndex[StarCircle],
    stars: tuple[StarCircle, ...],
    style: StyleConfig,
    weights: CostWeights,
    constellation_lines: tuple[tuple[PagePoint, PagePoint], ...],
    cost_cache: _CandidateScoreCache | None = None,
) -> CostBreakdown:
    nearby_bounds = tuple(
        placed_index.query(candidate.bounds, margin_mm=_CROWDING_RADIUS_MM, exclude=label.id)
    )
    if cost_cache is not None:
        return cost_cache.breakdown(label, candidate, nearby_bounds)
    nearby_symbols = tuple(symbols_index.query(candidate.bounds))
    nearby_stars = _nearby_stars(label, candidate.bounds, stars_index, stars, style)
    return score_candidate(
        candidate,
        target_anchor=_anchor_for(label, anchors, candidate),
        placed_bounds=nearby_bounds,
        symbols=nearby_symbols,
        stars=nearby_stars,
        associated_star_ids=_associated_star_ids(label, nearby_stars),
        related_star_ids=_related_star_ids(label, nearby_stars),
        star_clearance=style.label.star_clearance,
        target_source_id=_association_source_id(label),
        source_association=style.label.source_association,
        dso_placement=style.label.dso_placement,
        is_dso_label=label.id.startswith("label:dso:"),
        source_symbols=_nearby_sources(label, candidate.bounds, sources, style),
        association_scale=_association_scale(label, style),
        printable=printable,
        crowding_radius_mm=_CROWDING_RADIUS_MM,
        weights=weights,
        edge_margin_mm=_EDGE_MARGIN_MM,
        constellation_lines=constellation_lines,
    )


def _build_placed_index(
    labels: tuple[Label, ...], style: StyleConfig
) -> RectIndex[PageRect]:
    index: RectIndex[PageRect] = RectIndex(_GRID_CELL_MM)
    for label in labels:
        candidate = None if label.hidden else label.effective_candidate()
        if candidate is not None:
            bounds = _collision_bounds(label, candidate, style)
            index.set(label.id, bounds, bounds)
    return index


def _weighted_ownership_cost(
    breakdown: CostBreakdown,
    weights: CostWeights,
) -> float:
    return (
        breakdown.label_source_distance_mm * weights.label_source_distance
        + breakdown.label_source_corridor * weights.label_source_corridor
        + breakdown.label_competing_source_ambiguity
        * weights.label_competing_source_ambiguity
        + breakdown.label_competing_owner * weights.label_competing_owner
        + breakdown.label_ownership_margin_cost * weights.label_ownership_margin
    )


def _candidate_rejection_reason(
    label: Label,
    candidate: LabelCandidate,
    placed_index: RectIndex[PageRect],
    symbols_index: RectIndex[SymbolCircle],
    stars_index: RectIndex[StarCircle],
    stars: tuple[StarCircle, ...],
    printable: PageRect,
    style: StyleConfig,
    *,
    furniture: tuple[PageRect, ...],
    source_geometries: tuple[SourceGeometry, ...],
    cost_cache: _CandidateScoreCache | None = None,
) -> str | None:
    bounds = candidate.bounds
    collision_bounds = _collision_bounds(label, candidate, style)
    if (
        bounds.left_mm < printable.left_mm
        or bounds.top_mm < printable.top_mm
        or bounds.right_mm > printable.right_mm
        or bounds.bottom_mm > printable.bottom_mm
    ):
        return "outside_printable_area"
    if any(rects_overlap(bounds, obstacle) for obstacle in furniture):
        return "page_furniture_overlap"
    if any(
        rects_overlap(collision_bounds, other)
        for other in placed_index.query(
            collision_bounds,
            margin_mm=style.label.dso_placement.label_label_ink_clearance_mm or 0.0,
            exclude=label.id,
        )
    ):
        return "label_label_overlap"
    if cost_cache is not None:
        return cost_cache.source_rejection(label, candidate)
    return _source_candidate_rejection_reason(
        label, candidate, symbols_index, stars_index, stars, style, source_geometries
    )


def _source_candidate_rejection_reason(
    label: Label,
    candidate: LabelCandidate,
    symbols_index: RectIndex[SymbolCircle],
    stars_index: RectIndex[StarCircle],
    stars: tuple[StarCircle, ...],
    style: StyleConfig,
    source_geometries: tuple[SourceGeometry, ...],
) -> str | None:
    bounds = candidate.bounds
    visible_bounds = (
        candidate_ink_bounds(candidate)
        if label.id.startswith("label:dso:")
        else bounds
    )
    nearby_symbols = tuple(symbols_index.query(visible_bounds))
    nearby_source_ids = {symbol.id for symbol in nearby_symbols}
    if any(
        source.id in nearby_source_ids
        and source_outline_edge_distance(source, visible_bounds) <= 0.0
        for source in source_geometries
    ):
        return "dso_symbol_overlap"
    if label.id.startswith("label:dso:"):
        _, _, _, wrong_owner = _ownership_result(
            label, visible_bounds, source_geometries, style
        )
        if wrong_owner:
            return "foreign_source_closer_than_owner"
    nearby_stars = _nearby_stars(label, bounds, stars_index, stars, style)
    related = _related_star_ids(label, stars) if nearby_stars else frozenset()
    for star in nearby_stars:
        hard_min = (
            style.label.star_clearance.associated.hard_min_mm
            if related & star.star_ids
            else foreign_star_hard_min_mm(star.radius_mm, style.label.star_clearance)
        )
        if candidate_star_edge_distance_mm(
            star,
            candidate,
            visible_text=label.id.startswith(("label:star:", "label:dso:")),
        ) < hard_min:
            return "star_clearance"
    return None


def _evaluate(
    ordered: tuple[Label, ...],
    placements: dict[str, str | None],
    anchors: dict[str, PagePoint],
    printable: PageRect,
    symbols: tuple[SymbolCircle, ...],
    sources: tuple[SourceGeometry, ...],
    stars: tuple[StarCircle, ...],
    style: StyleConfig,
    weights: CostWeights,
    constellation_lines: tuple[tuple[PagePoint, PagePoint], ...] = (),
) -> tuple[float, dict[str, float]]:
    label_by_id = {label.id: label for label in ordered}
    placed_index: RectIndex[PageRect] = RectIndex(_GRID_CELL_MM)
    for label_id, candidate_id in placements.items():
        if candidate_id is None:
            continue
        placed_label = label_by_id[label_id]
        placed_candidate = placed_label.candidate(candidate_id)
        if placed_candidate is not None:
            bounds = _collision_bounds(placed_label, placed_candidate, style)
            placed_index.set(label_id, bounds, bounds)
    stars_index = _build_star_index(stars)
    total = 0.0
    totals: dict[str, float] = {}
    for label in ordered:
        candidate_id = placements.get(label.id)
        if candidate_id is None:
            continue
        candidate = label.candidate(candidate_id)
        if candidate is None:
            continue
        nearby_bounds = tuple(
            placed_index.query(candidate.bounds, margin_mm=_CROWDING_RADIUS_MM, exclude=label.id)
        )
        nearby_stars = _nearby_stars(label, candidate.bounds, stars_index, stars, style)
        breakdown = score_candidate(
            candidate,
            target_anchor=_anchor_for(label, anchors, candidate),
            placed_bounds=nearby_bounds,
            symbols=symbols,
            stars=nearby_stars,
            associated_star_ids=_associated_star_ids(label, nearby_stars),
            related_star_ids=_related_star_ids(label, nearby_stars),
            star_clearance=style.label.star_clearance,
            target_source_id=_association_source_id(label),
            source_association=style.label.source_association,
            dso_placement=style.label.dso_placement,
            is_dso_label=label.id.startswith("label:dso:"),
            source_symbols=_nearby_sources(label, candidate.bounds, sources, style),
            association_scale=_association_scale(label, style),
            printable=printable,
            crowding_radius_mm=_CROWDING_RADIUS_MM,
            weights=weights,
            edge_margin_mm=_EDGE_MARGIN_MM,
            constellation_lines=constellation_lines,
        )
        total += breakdown.total(weights)
        for name, value in breakdown.components().items():
            totals[name] = totals.get(name, 0.0) + value
    return total, totals


def translate_candidate(
    candidate: LabelCandidate,
    dx_mm: float,
    dy_mm: float,
    *,
    candidate_id: str | None = None,
) -> LabelCandidate:
    """Translate all measured placement geometry by a page-space offset."""
    return replace(
        candidate,
        id=candidate.id if candidate_id is None else candidate_id,
        anchor=PagePoint(candidate.anchor.x_mm + dx_mm, candidate.anchor.y_mm + dy_mm),
        bounds=_translate_rect(candidate.bounds, dx_mm, dy_mm),
        glyph_bounds=tuple(_translate_rect(rect, dx_mm, dy_mm) for rect in candidate.glyph_bounds),
        whitespace_bounds=tuple(
            _translate_rect(rect, dx_mm, dy_mm) for rect in candidate.whitespace_bounds
        ),
    )


def offset_label_placement(
    label: Label,
    candidate_id: str,
    dx_mm: float,
    dy_mm: float,
) -> Label:
    """Select a candidate translated by a reproducible physical page offset."""
    base = label.candidate(candidate_id)
    if base is None:
        raise ValueError(f"{label.id}: unknown base candidate {candidate_id!r}")
    if dx_mm == 0.0 and dy_mm == 0.0:
        return label.with_placement(candidate_id)
    adjusted_id = f"{candidate_id}:offset:{dx_mm:+.4f}:{dy_mm:+.4f}"
    adjusted = translate_candidate(base, dx_mm, dy_mm, candidate_id=adjusted_id)
    candidates = tuple(item for item in label.candidates if item.id != adjusted_id)
    return replace(
        label,
        candidates=(*candidates, adjusted),
        selected_candidate_id=adjusted_id,
        hidden=False,
    )


def _translate_rect(rect: PageRect, dx_mm: float, dy_mm: float) -> PageRect:
    return PageRect(
        rect.left_mm + dx_mm,
        rect.top_mm + dy_mm,
        rect.width_mm,
        rect.height_mm,
    )
