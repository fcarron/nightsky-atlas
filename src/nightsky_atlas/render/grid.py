"""Coordinate grid path generation.

Grid lines are generated in chart-plane degrees and mapped to page millimetres.
They are clipped by the renderer to the chart field; labels take priority over
them (``AGENTS.md`` section 5.2 / 14.4).

Coordinate edge labels are *furniture*: they are never collision-routed against
sky labels and are drawn beneath them.  ``grid.label_placement`` selects whether
they sit just inside the chart frame (``inside``) or beyond it in the page
margin (``outside``).
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

from nightsky_atlas.atlas.config import StyleConfig
from nightsky_atlas.chart.models import ChartDefinition
from nightsky_atlas.chart.page import PagePoint, PageRect, PageTransform
from nightsky_atlas.chart.presentation import format_dec_deg, format_ra_deg
from nightsky_atlas.projection.base import ProjectionError
from nightsky_atlas.projection.stereographic import StereographicProjection
from nightsky_atlas.render.text import TextMeasurer
from nightsky_atlas.scene.builder import default_projection

__all__ = [
    "GridLabel",
    "GridLine",
    "GridTick",
    "build_grid",
    "build_grid_labels",
    "build_grid_ticks",
    "format_dec_deg",
    "format_ra_deg",
]

_SAMPLES = 65
_EDGE_MARGIN_DEG = 1.0
_MULTIPLE_TOL = 1e-6
_OBSTACLE_CLEARANCE_MM = 0.5
_POLAR_DEC_TOLERANCE_DEG = 1.0
_RECT_HIT_TOLERANCE_MM = 0.5
_RA_LABEL_MAX_SHIFT_MM = 12.0


@dataclass(frozen=True, slots=True)
class GridLine:
    """One grid polyline: a meridian (``ra``) or parallel (``dec``)."""

    kind: str
    value_deg: float
    points: tuple[PagePoint, ...]
    polar: bool = False


@dataclass(frozen=True, slots=True)
class GridLabel:
    """A coordinate label placed inside or outside the chart frame."""

    id: str
    kind: str
    value_deg: float
    text: str
    bounds: PageRect


@dataclass(frozen=True, slots=True)
class GridTick:
    edge: str
    position_mm: float
    length_mm: float


def _ra_half_width_deg(definition: ChartDefinition, dec_deg: float) -> float:
    """Half-width in right ascension of the field at ``dec_deg``.

    Clamped to 180 deg: at or near a pole the field can wrap the whole sky, and
    the sampling must not run past a full turn (which would draw chords across
    the pole instead of the parallel).
    """
    cos_dec = math.cos(math.radians(min(89.9, abs(dec_deg))))
    return min(180.0, (definition.width_deg / 2.0) / max(cos_dec, 1e-6))


def _field_angular_radius_deg(definition: ChartDefinition) -> float:
    """Angular radius of the chart field, to its corner, in degrees.

    The field is a tangent-plane rectangle; its plane half-diagonal is
    ``2 tan(c / 2)`` for angular radius ``c``.
    """
    half_diagonal_deg = math.hypot(definition.width_deg / 2.0, definition.height_deg / 2.0)
    return math.degrees(2.0 * math.atan(math.radians(half_diagonal_deg) / 2.0))


def _is_polar_field(definition: ChartDefinition) -> bool:
    """Whether the field reaches the celestial pole it is closest to.

    Such fields wrap right ascension, so every meridian crosses the chart and
    the right-ascension grid needs the polar spacing instead of the equatorial
    one.  The pole lies within the field when the near declination edge is
    within a small tolerance of 90 deg.
    """
    near_edge = abs(definition.center_dec_deg) + definition.height_deg / 2.0
    return near_edge >= 90.0 - _POLAR_DEC_TOLERANCE_DEG


def _polyline_hits_rect(points: tuple[PagePoint, ...], rect: PageRect, margin_mm: float) -> bool:
    """Whether any point of a densely sampled polyline lies on the page rect."""
    return any(
        rect.left_mm - margin_mm <= point.x_mm <= rect.right_mm + margin_mm
        and rect.top_mm - margin_mm <= point.y_mm <= rect.bottom_mm + margin_mm
        for point in points
    )


def _project(
    projector: StereographicProjection,
    transform: PageTransform,
    ra_deg: float,
    dec_deg: float,
) -> PagePoint | None:
    try:
        chart_point = projector.project(ra_deg, dec_deg)
    except ProjectionError:
        return None
    return transform.to_page(chart_point)


def _first_multiple(start: float, step: float) -> float:
    return math.ceil(start / step - 1e-9) * step


def _step_for_minimum_grid_values(
    step: float, start_deg: float, end_deg: float, *, ra: bool
) -> float:
    """Densify a field only when its configured interval yields fewer than two values."""

    def value_count(candidate: float) -> int:
        first = _first_multiple(start_deg, candidate)
        return max(0, math.floor((end_deg - first) / candidate + 1e-9) + 1)

    if value_count(step) >= 2:
        return step
    for divisor in range(1, 121):
        candidate = step / divisor
        if value_count(candidate) < 2:
            continue
        display_units = candidate * (4.0 if ra else 10.0)
        if abs(display_units - round(display_units)) < 1e-8:
            return candidate
    return step / 120.0


def build_grid(
    definition: ChartDefinition,
    transform: PageTransform,
    style: StyleConfig,
    *,
    ra_step_deg: float | None = None,
    dec_step_deg: float | None = None,
    polar_ra_step_deg: float | None = None,
) -> tuple[GridLine, ...]:
    """Build RA/Dec grid polylines, subdividing narrow fields when needed.

    Grid intervals are divided into displayable coordinate steps when a small
    detail field would otherwise contain fewer than two distinct meridians or
    parallels.  The configured intervals remain the maximum spacing.
    """
    grid = style.grid
    if not grid.enabled:
        return ()

    projector = default_projection(definition)
    half_height = definition.height_deg / 2.0
    dec_min = max(-90.0, definition.center_dec_deg - half_height)
    dec_max = min(90.0, definition.center_dec_deg + half_height)
    worst_dec = min(89.9, max(abs(dec_min), abs(dec_max)))
    ra_half = _ra_half_width_deg(definition, worst_dec)
    polar = _is_polar_field(definition)
    rect = transform.chart_rect
    lines: list[GridLine] = []

    if polar:
        ra_step = polar_ra_step_deg or grid.polar_ra_step_deg
    else:
        ra_step = ra_step_deg or grid.ra_step_deg
    ra_step = _step_for_minimum_grid_values(
        ra_step,
        0.0 if polar else definition.center_ra_deg - ra_half,
        360.0 if polar else definition.center_ra_deg + ra_half,
        ra=True,
    )
    if polar:
        ra = 0.0
        ra_limit = 360.0 - 1e-9
        radius = _field_angular_radius_deg(definition)
        sample_dec_min = max(-90.0, definition.center_dec_deg - radius - _EDGE_MARGIN_DEG)
        sample_dec_max = min(90.0, definition.center_dec_deg + radius + _EDGE_MARGIN_DEG)
    else:
        ra = _first_multiple(definition.center_ra_deg - ra_half, ra_step)
        ra_limit = definition.center_ra_deg + ra_half + 1e-9
        sample_dec_min = dec_min - _EDGE_MARGIN_DEG
        sample_dec_max = dec_max + _EDGE_MARGIN_DEG
    while ra <= ra_limit:
        points = [
            point
            for index in range(_SAMPLES)
            if (
                point := _project(
                    projector,
                    transform,
                    ra,
                    sample_dec_min + (sample_dec_max - sample_dec_min) * index / (_SAMPLES - 1),
                )
            )
            is not None
        ]
        if len(points) >= 2 and (
            not polar or _polyline_hits_rect(tuple(points), rect, _RECT_HIT_TOLERANCE_MM)
        ):
            lines.append(
                GridLine(kind="ra", value_deg=ra % 360.0, points=tuple(points), polar=polar)
            )
        ra += ra_step

    dec_step = _step_for_minimum_grid_values(
        dec_step_deg or grid.dec_step_deg, dec_min, dec_max, ra=False
    )
    dec = _first_multiple(dec_min, dec_step)
    dec_limit = dec_max + 1e-9
    while dec <= dec_limit:
        ra_half_dec = _ra_half_width_deg(definition, dec)
        samples = max(_SAMPLES, int(2.0 * ra_half_dec) + 1)
        points = [
            point
            for index in range(samples)
            if (
                point := _project(
                    projector,
                    transform,
                    definition.center_ra_deg
                    - ra_half_dec
                    + 2.0 * ra_half_dec * index / (samples - 1),
                    dec,
                )
            )
            is not None
        ]
        if len(points) >= 2:
            lines.append(GridLine(kind="dec", value_deg=dec, points=tuple(points)))
        dec += dec_step

    return tuple(lines)


def _is_multiple(value: float, step: float) -> bool:
    ratio = value / step
    return abs(ratio - round(ratio)) < _MULTIPLE_TOL


def _clamp(value: float, low: float, high: float) -> float:
    if high < low:
        return low
    return min(max(value, low), high)


def _ra_label_left_positions(
    crossing_x: float,
    label_width: float,
    *,
    low: float,
    high: float,
) -> tuple[float, ...]:
    """Return progressively shifted positions close to an RA edge crossing."""
    centered = _clamp(crossing_x - label_width / 2.0, low, high)
    positions = [centered]
    max_shift = min(_RA_LABEL_MAX_SHIFT_MM, max(high - low, 0.0))
    shift_steps = int(math.ceil(max_shift))
    for shift in range(1, shift_steps + 1):
        distance = float(shift)
        for candidate in (centered - distance, centered + distance):
            if candidate < low or candidate > high:
                continue
            if not any(math.isclose(candidate, item, abs_tol=1e-9) for item in positions):
                positions.append(candidate)
    return tuple(positions)


def _overlaps(first: PageRect, second: PageRect, margin_mm: float = 0.0) -> bool:
    """Return whether two page rectangles overlap (optionally with clearance)."""
    return not (
        first.right_mm + margin_mm <= second.left_mm
        or second.right_mm + margin_mm <= first.left_mm
        or first.bottom_mm + margin_mm <= second.top_mm
        or second.bottom_mm + margin_mm <= first.top_mm
    )


def _scan_crossings(points: tuple[PagePoint, ...], edge_value: float, axis: str) -> list[float]:
    """Return perpendicular coordinates where a polyline crosses an edge.

    ``axis == "x"`` scans a vertical edge and returns page ``y`` positions;
    ``axis == "y"`` scans a horizontal edge and returns page ``x`` positions.
    Duplicate crossings at shared vertices are collapsed.
    """
    results: list[float] = []
    for first, second in zip(points, points[1:], strict=False):
        value_a = first.x_mm if axis == "x" else first.y_mm
        value_b = second.x_mm if axis == "x" else second.y_mm
        if value_a == value_b or (value_a - edge_value) * (value_b - edge_value) > 0.0:
            continue
        fraction = (edge_value - value_a) / (value_b - value_a)
        if not 0.0 <= fraction <= 1.0:
            continue
        if axis == "x":
            results.append(first.y_mm + fraction * (second.y_mm - first.y_mm))
        else:
            results.append(first.x_mm + fraction * (second.x_mm - first.x_mm))

    unique: list[float] = []
    seen: set[float] = set()
    for value in results:
        key = round(value, 4)
        if key not in seen:
            seen.add(key)
            unique.append(value)
    return unique


def build_grid_ticks(
    definition: ChartDefinition,
    transform: PageTransform,
    style: StyleConfig,
) -> tuple[GridTick, ...]:
    grid = style.grid
    if not grid.enabled or not grid.ticks_enabled:
        return ()
    polar = _is_polar_field(definition)
    lines = build_grid(
        definition,
        transform,
        style,
        ra_step_deg=grid.tick_ra_step_deg,
        dec_step_deg=grid.tick_dec_step_deg,
        polar_ra_step_deg=grid.tick_polar_ra_step_deg,
    )
    rect = transform.chart_rect
    candidates: dict[str, list[tuple[bool, int, float, GridTick]]] = {
        edge: [] for edge in ("top", "bottom", "left", "right")
    }
    for line in lines:
        if line.kind == "ra":
            major_step = grid.polar_ra_step_deg if polar else grid.ra_step_deg
            edges = (("top", rect.top_mm), ("bottom", rect.bottom_mm))
            axis = "y"
            lower, upper = rect.left_mm, rect.right_mm
        else:
            major_step = grid.dec_step_deg
            edges = (("left", rect.left_mm), ("right", rect.right_mm))
            axis = "x"
            lower, upper = rect.top_mm, rect.bottom_mm
        major = _is_multiple(line.value_deg, major_step)
        length = grid.tick_major_length_mm if major else grid.tick_length_mm
        for edge, edge_value in edges:
            for position in _scan_crossings(line.points, edge_value, axis):
                if not lower + length <= position <= upper - length:
                    continue
                candidates[edge].append(
                    (
                        major,
                        _label_tier(line.kind, line.value_deg),
                        position,
                        GridTick(edge=edge, position_mm=position, length_mm=length),
                    )
                )

    placed: list[GridTick] = []
    for edge_candidates in candidates.values():
        edge_candidates.sort(key=lambda item: (not item[0], item[1], item[2]))
        positions: list[float] = []
        for _, _, position, tick in edge_candidates:
            if any(abs(position - previous) < grid.tick_min_spacing_mm for previous in positions):
                continue
            positions.append(position)
            placed.append(tick)
    return tuple(placed)


def build_grid_labels(
    definition: ChartDefinition,
    transform: PageTransform,
    style: StyleConfig,
    *,
    lines: tuple[GridLine, ...] | None = None,
    avoid: Iterable[PageRect] = (),
) -> tuple[GridLabel, ...]:
    """Build RA/Dec edge labels inside or outside the chart frame.

    RA labels sit against the top and bottom edges; Dec labels against the left
    and right edges.  The set of labelled lines is controlled by
    ``grid.label_ra_step_deg`` / ``grid.label_dec_step_deg`` (with
    ``grid.label_polar_ra_step_deg`` replacing the RA step on polar fields, so
    the converging meridian fan is labelled sparsely) and the side by
    ``grid.label_placement``.  Independently of those steps,
    ``grid.label_min_spacing_mm`` drops labels that would print closer than that
    many millimetres to a neighbour on the same edge.  These are furniture, not
    sky labels, so they are not collision-routed against sky labels, but any
    placement overlapping one of the ``avoid`` rectangles (title, scale bar,
    ...) is dropped.
    """
    grid = style.grid
    if not grid.enabled or not grid.labels_enabled:
        return ()
    if lines is None:
        lines = build_grid(definition, transform, style)

    rect = transform.chart_rect
    page = transform.page
    measurer = TextMeasurer(style.label.font_family, grid.label_font_size_pt)
    polar = _is_polar_field(definition)
    if polar and grid.label_polar_ra_step_deg is not None:
        ra_step = grid.label_polar_ra_step_deg
    else:
        ra_step = grid.label_ra_step_deg or grid.ra_step_deg
    dec_step = grid.label_dec_step_deg or grid.dec_step_deg
    pad = grid.label_padding_mm
    outside = grid.label_placement == "outside"

    labels: list[tuple[str, float, GridLabel]] = []
    supplemental_labels: list[tuple[str, float, GridLabel]] = []
    target_labels = labels
    seen_ids: set[str] = set()
    obstacles = tuple(avoid)

    def add(
        edge: str,
        kind: str,
        value_deg: float,
        text: str,
        left: float,
        top: float,
        along: float,
    ) -> bool:
        label_id = f"grid:{kind}:{value_deg:g}:{edge}"
        if label_id in seen_ids:
            return False
        metrics = measurer.measure_mm(text)
        bounds = PageRect(
            left_mm=left,
            top_mm=top,
            width_mm=metrics.width_mm,
            height_mm=metrics.height_mm,
        )
        if any(
            _overlaps(bounds, obstacle, margin_mm=_OBSTACLE_CLEARANCE_MM) for obstacle in obstacles
        ):
            return False
        seen_ids.add(label_id)
        target_labels.append(
            (
                edge,
                along,
                GridLabel(
                    id=label_id,
                    kind=kind,
                    value_deg=value_deg,
                    text=text,
                    bounds=bounds,
                ),
            )
        )
        return True

    for line in lines:
        if line.kind == "ra":
            target_labels = (
                labels if _is_multiple(line.value_deg, ra_step) else supplemental_labels
            )
            text = format_ra_deg(line.value_deg)
            metrics = measurer.measure_mm(text)
            if outside:
                placements = (
                    ("top", rect.top_mm - pad - metrics.height_mm, rect.top_mm),
                    ("bottom", rect.bottom_mm + pad, page.height_mm - rect.bottom_mm),
                )
            else:
                placements = (
                    ("top", rect.top_mm + pad, rect.height_mm),
                    ("bottom", rect.bottom_mm - pad - metrics.height_mm, rect.height_mm),
                )
            for edge, top, available in placements:
                if outside and available < pad + metrics.height_mm - _MULTIPLE_TOL:
                    continue
                crossings = _scan_crossings(
                    line.points, rect.top_mm if edge == "top" else rect.bottom_mm, "y"
                )
                for x in crossings:
                    if not rect.left_mm <= x <= rect.right_mm:
                        continue
                    if outside:
                        low = 0.0
                        high = page.width_mm - metrics.width_mm
                    else:
                        low = rect.left_mm + pad
                        high = rect.right_mm - pad - metrics.width_mm
                    for left in _ra_label_left_positions(
                        x, metrics.width_mm, low=low, high=high
                    ):
                        if add(edge, "ra", line.value_deg, text, left, top, x):
                            break
        else:
            target_labels = (
                labels if _is_multiple(line.value_deg, dec_step) else supplemental_labels
            )
            text = format_dec_deg(line.value_deg)
            metrics = measurer.measure_mm(text)
            candidate_count = len(target_labels)
            if outside:
                placements = (
                    ("left", rect.left_mm - pad - metrics.width_mm, rect.left_mm),
                    ("right", rect.right_mm + pad, page.width_mm - rect.right_mm),
                )
            else:
                placements = (
                    ("left", rect.left_mm + pad, rect.width_mm),
                    ("right", rect.right_mm - pad - metrics.width_mm, rect.width_mm),
                )
            has_side_crossing = any(
                rect.top_mm <= y <= rect.bottom_mm
                for edge_x in (rect.left_mm, rect.right_mm)
                for y in _scan_crossings(line.points, edge_x, "x")
            )
            for edge, left, available in placements:
                if outside and available < pad + metrics.width_mm - _MULTIPLE_TOL:
                    continue
                crossings = _scan_crossings(
                    line.points, rect.left_mm if edge == "left" else rect.right_mm, "x"
                )
                for y in crossings:
                    if not rect.top_mm <= y <= rect.bottom_mm:
                        continue
                    if outside:
                        top = _clamp(
                            y - metrics.height_mm / 2.0,
                            0.0,
                            page.height_mm - metrics.height_mm,
                        )
                    else:
                        top = _clamp(
                            y - metrics.height_mm / 2.0,
                            rect.top_mm + pad,
                            rect.bottom_mm - pad - metrics.height_mm,
                        )
                    add(edge, "dec", line.value_deg, text, left, top, y)
            if not has_side_crossing:
                if outside:
                    horizontal_placements = (
                        ("top", rect.top_mm - pad - metrics.height_mm, rect.top_mm),
                        ("bottom", rect.bottom_mm + pad, page.height_mm - rect.bottom_mm),
                    )
                else:
                    horizontal_placements = (
                        ("top", rect.top_mm + pad, rect.height_mm),
                        ("bottom", rect.bottom_mm - pad - metrics.height_mm, rect.height_mm),
                    )
                for edge, top, available in horizontal_placements:
                    if outside and available < pad + metrics.height_mm - _MULTIPLE_TOL:
                        continue
                    edge_y = rect.top_mm if edge == "top" else rect.bottom_mm
                    for x in _scan_crossings(line.points, edge_y, "y"):
                        if not rect.left_mm <= x <= rect.right_mm:
                            continue
                        if outside:
                            left = _clamp(
                                x - metrics.width_mm / 2.0,
                                0.0,
                                page.width_mm - metrics.width_mm,
                            )
                        else:
                            left = _clamp(
                                x - metrics.width_mm / 2.0,
                                rect.left_mm + pad,
                                rect.right_mm - pad - metrics.width_mm,
                            )
                        add(edge, "dec", line.value_deg, text, left, top, x)
            if len(target_labels) == candidate_count and line.points:
                point = min(
                    line.points,
                    key=lambda item: min(
                        item.x_mm - rect.left_mm,
                        rect.right_mm - item.x_mm,
                        item.y_mm - rect.top_mm,
                        rect.bottom_mm - item.y_mm,
                    ),
                )
                left = _clamp(
                    point.x_mm + pad,
                    rect.left_mm + pad,
                    rect.right_mm - pad - metrics.width_mm,
                )
                top = _clamp(
                    point.y_mm + pad,
                    rect.top_mm + pad,
                    rect.bottom_mm - pad - metrics.height_mm,
                )
                add("inner", "dec", line.value_deg, text, left, top, point.y_mm)

    placed = list(_thin_labels(labels, spacing_mm=grid.label_min_spacing_mm))
    for kind in ("ra", "dec"):
        if len({_coordinate_value(label) for label in placed if label.kind == kind}) >= 2:
            continue
        candidates = sorted(
            (item for item in supplemental_labels if item[2].kind == kind),
            key=lambda item: (
                _label_tier(kind, item[2].value_deg),
                item[0],
                item[1],
                item[2].value_deg,
            ),
        )
        for enforce_spacing in (True, False):
            for edge, along, label in candidates:
                present_values = {_coordinate_value(item) for item in placed if item.kind == kind}
                if _coordinate_value(label) in present_values:
                    continue
                if (
                    enforce_spacing
                    and grid.label_min_spacing_mm > 0.0
                    and any(
                        item.id.rsplit(":", 1)[-1] == edge
                        and abs(along - _label_along_position(item, edge))
                        < grid.label_min_spacing_mm
                        for item in placed
                    )
                ):
                    continue
                if any(
                    _overlaps(label.bounds, item.bounds, margin_mm=_OBSTACLE_CLEARANCE_MM)
                    for item in placed
                ):
                    continue
                placed.append(label)
                if len({_coordinate_value(item) for item in placed if item.kind == kind}) >= 2:
                    break
            if len({_coordinate_value(item) for item in placed if item.kind == kind}) >= 2:
                break
    return tuple(placed)


def _coordinate_value(label: GridLabel) -> float:
    """Return a stable, wrap-safe value for counting distinct grid labels."""
    return round(label.value_deg % 360.0, 8) if label.kind == "ra" else round(label.value_deg, 8)


def _label_along_position(label: GridLabel, edge: str) -> float:
    """Return the along-edge coordinate used by grid-label spacing."""
    return label.bounds.center.x_mm if edge in ("top", "bottom") else label.bounds.center.y_mm


_LABEL_TIER_STEPS = (30.0, 10.0, 5.0, 2.0)


def _label_tier(kind: str, value_deg: float) -> int:
    """Priority tier of a coordinate value (0 = roundest, kept first).

    Round values (whole hours, tens of degrees) survive the spacing filter
    before odd ones, so thinning removes the forgettable lines rather than the
    navigation anchors.
    """
    value = abs(value_deg % 360.0) if kind == "ra" else abs(value_deg)
    for tier, step in enumerate(_LABEL_TIER_STEPS):
        ratio = value / step
        if abs(ratio - round(ratio)) < _MULTIPLE_TOL:
            return tier
    return len(_LABEL_TIER_STEPS)


def _thin_labels(
    candidates: list[tuple[str, float, GridLabel]], *, spacing_mm: float
) -> tuple[GridLabel, ...]:
    """Drop coordinate labels too close together along the same page edge.

    Grid *line* density is independent of label density: when meridians
    converge toward a pole, or a chart is far from the inner meridian, adjacent
    grid lines would print their values almost on top of each other.  Labels
    are grouped by edge, sorted roundest-first, and kept only when they clear
    ``spacing_mm`` from every label already kept on that edge (and do not
    overlap any kept label anywhere).
    """
    by_edge: dict[str, list[tuple[float, GridLabel]]] = {}
    for edge, along, label in candidates:
        by_edge.setdefault(edge, []).append((along, label))

    placed: list[GridLabel] = []
    for items in by_edge.values():
        items.sort(key=lambda item: (_label_tier(item[1].kind, item[1].value_deg), item[0]))
        kept_along: list[float] = []
        for along, label in items:
            if spacing_mm > 0.0 and any(abs(along - other) < spacing_mm for other in kept_along):
                continue
            if any(
                _overlaps(label.bounds, other.bounds, margin_mm=_OBSTACLE_CLEARANCE_MM)
                for other in placed
            ):
                continue
            kept_along.append(along)
            placed.append(label)
    return tuple(placed)
