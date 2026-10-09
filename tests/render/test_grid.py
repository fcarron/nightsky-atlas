"""Tests for coordinate grid generation."""

from __future__ import annotations

from pathlib import Path

import pytest

from nightsky_atlas.atlas.config import load_atlas_config, load_style_config
from nightsky_atlas.atlas.tiling import chart_definitions
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.chart.page import PageTransform
from nightsky_atlas.chart.presentation import presentation_from_edition
from nightsky_atlas.render.furniture import build_furniture_plan
from nightsky_atlas.render.grid import (
    build_grid,
    build_grid_labels,
    format_dec_deg,
    format_ra_deg,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
STYLE = load_style_config(REPO_ROOT / "styles" / "standard.yaml")

CHART = ChartDefinition(
    id="test", center_ra_deg=187.5, center_dec_deg=12.0, width_deg=20.0, height_deg=14.0
)
PAGE = PageGeometry(width_mm=297.0, height_mm=210.0, margin_mm=12.0)
TRANSFORM = PageTransform(chart=CHART, page=PAGE)


def test_grid_has_meridians_and_parallels() -> None:
    lines = build_grid(CHART, TRANSFORM, STYLE)
    kinds = {line.kind for line in lines}
    assert kinds == {"ra", "dec"}
    assert len(lines) > 4


def test_polar_grid_has_no_long_chords() -> None:
    """A near-pole field must not sample a parallel past a full turn of RA.

    Regression: using the pole's right-ascension half-width for every parallel
    sampled thousands of degrees of RA and drew chords across the chart.
    """
    chart = ChartDefinition(
        id="polar", center_ra_deg=0.0, center_dec_deg=80.75, width_deg=27.0, height_deg=18.5
    )
    transform = PageTransform(chart=chart, page=PAGE)
    lines = build_grid(chart, transform, STYLE)
    assert lines
    for line in lines:
        for first, second in zip(line.points, line.points[1:], strict=False):
            distance = ((first.x_mm - second.x_mm) ** 2 + (first.y_mm - second.y_mm) ** 2) ** 0.5
            assert distance < 50.0


def test_polar_grid_has_radial_meridians() -> None:
    """Polar fields wrap RA, so every meridian is drawn at the coarse step."""
    chart = ChartDefinition(
        id="polar", center_ra_deg=0.0, center_dec_deg=80.75, width_deg=27.0, height_deg=18.5
    )
    transform = PageTransform(chart=chart, page=PAGE)
    meridians = [line for line in build_grid(chart, transform, STYLE) if line.kind == "ra"]
    assert meridians
    step = STYLE.grid.polar_ra_step_deg
    assert step == pytest.approx(STYLE.grid.ra_step_deg)
    for line in meridians:
        assert line.value_deg % step == pytest.approx(0.0, abs=1e-9)
        assert line.polar
    parallels = [line for line in build_grid(chart, transform, STYLE) if line.kind == "dec"]
    assert parallels
    assert not any(line.polar for line in parallels)


@pytest.mark.parametrize("center_dec", [90.0, -90.0])
def test_polar_style_applies_to_north_and_south_polar_fields(center_dec: float) -> None:
    chart = ChartDefinition(
        id="polar", center_ra_deg=0.0, center_dec_deg=center_dec, width_deg=27.0, height_deg=18.5
    )
    transform = PageTransform(chart=chart, page=PAGE)
    lines = build_grid(chart, transform, STYLE)
    assert any(line.kind == "ra" and line.polar for line in lines)
    assert any(line.kind == "dec" and not line.polar for line in lines)
    assert STYLE.grid.polar_ra_line_width_mm == pytest.approx(0.08)
    assert STYLE.grid.polar_ra_gray == pytest.approx(0.87)


@pytest.mark.parametrize("center_dec", [90.0, -90.0])
def test_polar_grid_keeps_ra_labels_on_thirty_degree_intervals(center_dec: float) -> None:
    chart = ChartDefinition(
        id="polar", center_ra_deg=0.0, center_dec_deg=center_dec, width_deg=27.0, height_deg=18.5
    )
    transform = PageTransform(chart=chart, page=PAGE)
    labels = build_grid_labels(chart, transform, STYLE)
    ra_labels = [label for label in labels if label.kind == "ra"]
    assert ra_labels
    assert all(label.value_deg % 30.0 == pytest.approx(0.0, abs=1e-9) for label in ra_labels)


def test_polar_meridians_are_near_straight() -> None:
    """A meridian is a great circle through the pole, so it projects straight.

    The chart centre is 9.25 deg from the pole, so the meridians are very
    slightly curved, but nowhere near a parallel arc.
    """
    chart = ChartDefinition(
        id="polar", center_ra_deg=0.0, center_dec_deg=80.75, width_deg=27.0, height_deg=18.5
    )
    transform = PageTransform(chart=chart, page=PAGE)
    for line in build_grid(chart, transform, STYLE):
        if line.kind != "ra":
            continue
        first, last = line.points[0], line.points[-1]
        run_x = last.x_mm - first.x_mm
        run_y = last.y_mm - first.y_mm
        length = (run_x**2 + run_y**2) ** 0.5
        deviation = max(
            abs((point.x_mm - first.x_mm) * run_y - (point.y_mm - first.y_mm) * run_x)
            / length
            for point in line.points
        )
        assert deviation < 2.0


def test_grid_values_follow_step() -> None:
    for line in build_grid(CHART, TRANSFORM, STYLE):
        step = STYLE.grid.ra_step_deg if line.kind == "ra" else STYLE.grid.dec_step_deg
        assert line.value_deg % step == pytest.approx(0.0, abs=1e-9)


@pytest.mark.parametrize(
    (
        "edition",
        "ra_step_deg",
        "polar_ra_step_deg",
        "dec_step_deg",
        "label_ra_step_deg",
        "label_dec_step_deg",
    ),
    (
        ("pocket", 15.0, 30.0, 10.0, 15.0, 10.0),
        ("standard", 7.5, 7.5, 5.0, 15.0, 10.0),
        ("deep", 3.75, 3.75, 2.0, 7.5, 4.0),
    ),
)
def test_edition_coordinate_grid_intervals(
    edition: str,
    ra_step_deg: float,
    polar_ra_step_deg: float,
    dec_step_deg: float,
    label_ra_step_deg: float,
    label_dec_step_deg: float,
) -> None:
    style = load_style_config(REPO_ROOT / "styles" / f"{edition}.yaml")
    assert style.grid.ra_step_deg == pytest.approx(ra_step_deg)
    assert style.grid.polar_ra_step_deg == pytest.approx(polar_ra_step_deg)
    assert style.grid.dec_step_deg == pytest.approx(dec_step_deg)
    assert style.grid.label_ra_step_deg == pytest.approx(label_ra_step_deg)
    assert style.grid.label_dec_step_deg == pytest.approx(label_dec_step_deg)
    lines = build_grid(CHART, TRANSFORM, style)
    for kind, step in (("ra", ra_step_deg), ("dec", dec_step_deg)):
        kind_lines = [line for line in lines if line.kind == kind]

        subdivisions = [
            candidate
            for divisor in range(1, 121)
            if abs(
                (candidate := step / divisor) * (4.0 if kind == "ra" else 10.0)
                - round(candidate * (4.0 if kind == "ra" else 10.0))
            )
            < 1e-8
            and all(
                line.value_deg / candidate
                == pytest.approx(round(line.value_deg / candidate), abs=1e-8)
                for line in kind_lines
            )
        ]
        assert subdivisions, (
            f"{edition} {kind} lines do not follow a displayable subdivision of {step}°"
        )


def test_grid_points_are_finite() -> None:
    for line in build_grid(CHART, TRANSFORM, STYLE):
        assert len(line.points) >= 2
        for point in line.points:
            assert point.x_mm == point.x_mm  # not NaN
            assert point.y_mm == point.y_mm


def test_disabled_grid_is_empty() -> None:
    style = STYLE.model_copy(update={"grid": STYLE.grid.model_copy(update={"enabled": False})})
    assert build_grid(CHART, TRANSFORM, style) == ()


def test_format_ra_deg() -> None:
    assert format_ra_deg(0.0) == "00h00m"
    assert format_ra_deg(180.0) == "12h00m"
    assert format_ra_deg(187.5) == "12h30m"
    assert format_ra_deg(359.9) == "00h00m"


def test_format_dec_deg() -> None:
    assert format_dec_deg(12.0) == "+12\u00b0"
    assert format_dec_deg(0.0) == "+0\u00b0"
    assert format_dec_deg(-5.0) == "-5\u00b0"
    assert format_dec_deg(-5.5) == "-5.5\u00b0"


def test_grid_labels_cover_both_kinds() -> None:
    labels = build_grid_labels(CHART, TRANSFORM, STYLE)
    assert {label.kind for label in labels} == {"ra", "dec"}
    assert len({label.id for label in labels}) == len(labels)
    for label in labels:
        if label.kind == "ra":
            assert label.text.endswith("m")
        else:
            assert label.text.endswith("\u00b0")


@pytest.mark.parametrize("chart_number", (45, 50, 55, 60, 65, 70, 75, 80, 85))
def test_standard_whole_hour_charts_keep_ra_labels_clear_of_furniture(
    chart_number: int,
) -> None:
    atlas = load_atlas_config(REPO_ROOT / "atlas" / "standard.yaml")
    edition_style = load_style_config(REPO_ROOT / "styles" / "standard.yaml")
    chart = next(
        item for item in chart_definitions(atlas) if item.id == f"standard-{chart_number:03d}"
    )
    transform = PageTransform(
        chart=chart,
        page=atlas.page.to_geometry(),
        scale_mm_per_degree=atlas.mm_per_degree,
    )
    presentation = presentation_from_edition(chart, atlas.resolved_edition())
    furniture = build_furniture_plan(transform, chart, edition_style, presentation)
    lines = build_grid(chart, transform, edition_style)
    labels = build_grid_labels(
        chart, transform, edition_style, lines=lines, avoid=furniture.obstacles
    )
    ra_labels = [label for label in labels if label.kind == "ra"]

    assert ra_labels, f"{chart.id} has no accepted RA edge labels"
    assert format_ra_deg(chart.center_ra_deg) in {label.text for label in ra_labels}
    assert len({label.value_deg for label in ra_labels}) >= 2
    assert len({(label.value_deg, label.id.rsplit(":", 1)[-1]) for label in ra_labels}) == len(
        ra_labels
    ), f"{chart.id} has duplicate RA labels on an edge"
    for label in ra_labels:
        if label.text == format_ra_deg(chart.center_ra_deg):
            assert abs(label.bounds.center.x_mm - transform.center_page.x_mm) <= 12.5, (
                chart.id,
                label.text,
                label.bounds,
            )
        assert 0.0 <= label.bounds.left_mm
        assert label.bounds.right_mm <= transform.page.width_mm
        assert 0.0 <= label.bounds.top_mm
        assert label.bounds.bottom_mm <= transform.page.height_mm
        assert not any(
            _rectangles_overlap(label.bounds, obstacle, margin=0.5)
            for obstacle in furniture.obstacles
        ), f"{chart.id} RA label overlaps chart furniture: {label.text}"


@pytest.mark.parametrize("edition", ("pocket", "standard", "deep"))
def test_all_main_charts_have_two_ra_and_dec_coordinate_values(edition: str) -> None:
    atlas = load_atlas_config(REPO_ROOT / "atlas" / f"{edition}.yaml")
    style = load_style_config(REPO_ROOT / "styles" / f"{edition}.yaml")
    charts = [(chart, atlas.mm_per_degree) for chart in chart_definitions(atlas)]
    charts.extend(
        (detail.to_definition(atlas_id=atlas.id), detail.mm_per_degree)
        for detail in atlas.detail_charts
    )
    for chart, scale in charts:
        transform = PageTransform(
            chart=chart,
            page=atlas.page.to_geometry(),
            scale_mm_per_degree=scale,
        )
        presentation = presentation_from_edition(chart, atlas.resolved_edition())
        furniture = build_furniture_plan(transform, chart, style, presentation)
        lines = build_grid(chart, transform, style)
        labels = build_grid_labels(chart, transform, style, lines=lines, avoid=furniture.obstacles)
        ra_labels = [label for label in labels if label.kind == "ra"]
        dec_labels = [label for label in labels if label.kind == "dec"]
        assert len({round(label.value_deg % 360.0, 8) for label in ra_labels}) >= 2, (
            f"{chart.id} has fewer than two distinct RA coordinate annotations: "
            f"{[label.text for label in ra_labels]}"
        )
        assert len({round(label.value_deg, 8) for label in dec_labels}) >= 2, (
            f"{chart.id} has fewer than two distinct declination coordinate annotations: "
            f"{[label.text for label in dec_labels]}"
        )
        assert all(label.text == format_ra_deg(label.value_deg) for label in ra_labels)
        assert all(label.text == format_dec_deg(label.value_deg) for label in dec_labels)
        assert len({(label.text, label.id.rsplit(":", 1)[-1]) for label in ra_labels}) == len(
            ra_labels
        ), f"{chart.id} has duplicate RA edge labels"
        assert all(
            0.0 <= label.bounds.left_mm
            and label.bounds.right_mm <= transform.page.width_mm
            and 0.0 <= label.bounds.top_mm
            and label.bounds.bottom_mm <= transform.page.height_mm
            for label in (*ra_labels, *dec_labels)
        ), chart.id


@pytest.mark.parametrize("edition", ("eyepiece", "eyepiece_deep"))
def test_experimental_detail_scales_keep_two_coordinate_values(edition: str) -> None:
    style = load_style_config(REPO_ROOT / "styles" / f"{edition}.yaml")
    scale, width, height = (40.0, 6.75, 4.5) if edition == "eyepiece" else (80.0, 3.375, 2.25)
    chart = ChartDefinition(
        id=f"{edition}-label-check",
        center_ra_deg=359.8,
        center_dec_deg=0.0,
        width_deg=width,
        height_deg=height,
    )
    transform = PageTransform(chart=chart, page=PAGE, scale_mm_per_degree=scale)
    labels = build_grid_labels(chart, transform, style, lines=build_grid(chart, transform, style))
    for kind in ("ra", "dec"):
        values = {
            round(label.value_deg % 360.0, 8) if kind == "ra" else round(label.value_deg, 8)
            for label in labels
            if label.kind == kind
        }
        assert len(values) >= 2


def _rectangles_overlap(first, second, *, margin: float = 0.0) -> bool:
    return not (
        first.right_mm + margin <= second.left_mm
        or second.right_mm + margin <= first.left_mm
        or first.bottom_mm + margin <= second.top_mm
        or second.bottom_mm + margin <= first.top_mm
    )


@pytest.mark.parametrize(
    ("chart_id", "center_ra", "center_dec", "width", "height", "scale"),
    (
        ("ra-wrap", 359.999999, 0.0, 27.0, 18.5, 10.0),
        ("near-whole-hour", 15.000001, 0.0, 27.0, 18.5, 10.0),
        ("between-grid-hours", 74.2, 15.0, 27.0, 18.5, 10.0),
        ("north-ring", 180.0, 75.0, 27.0, 18.5, 10.0),
        ("south-ring", 180.0, -75.0, 27.0, 18.5, 10.0),
        ("pocket-scale", 0.1, 0.0, 54.0, 36.0, 5.0),
        ("deep-scale", 0.1, 0.0, 13.5, 9.0, 20.0),
        ("eyepiece-scale", 359.9, -15.0, 6.75, 4.5, 40.0),
        ("eyepiece-deep-scale", 359.9, 15.0, 3.375, 2.25, 80.0),
    ),
)
def test_ra_grid_labels_handle_wrap_declination_and_map_scales(
    chart_id: str,
    center_ra: float,
    center_dec: float,
    width: float,
    height: float,
    scale: float,
) -> None:
    chart = ChartDefinition(
        id=chart_id,
        center_ra_deg=center_ra,
        center_dec_deg=center_dec,
        width_deg=width,
        height_deg=height,
    )
    transform = PageTransform(chart=chart, page=PAGE, scale_mm_per_degree=scale)
    labels = build_grid_labels(chart, transform, STYLE, lines=build_grid(chart, transform, STYLE))
    ra_labels = [label for label in labels if label.kind == "ra"]

    assert ra_labels, f"{chart_id} has no RA label despite meridians crossing the frame"
    assert all(label.text == format_ra_deg(label.value_deg) for label in ra_labels)
    assert all(0.0 <= label.value_deg < 360.0 for label in ra_labels)
    assert len({(label.text, label.id.rsplit(":", 1)[-1]) for label in ra_labels}) == len(
        ra_labels
    )
    assert all(
        0.0 <= label.bounds.left_mm
        and label.bounds.right_mm <= PAGE.width_mm
        and 0.0 <= label.bounds.top_mm
        and label.bounds.bottom_mm <= PAGE.height_mm
        for label in ra_labels
    )


def test_grid_labels_stay_inside_chart_rect() -> None:
    style = STYLE.model_copy(
        update={"grid": STYLE.grid.model_copy(update={"label_placement": "inside"})}
    )
    rect = TRANSFORM.chart_rect
    labels = build_grid_labels(CHART, TRANSFORM, style)
    assert labels
    for label in labels:
        assert rect.left_mm <= label.bounds.left_mm
        assert label.bounds.right_mm <= rect.right_mm + 1e-6
        assert rect.top_mm <= label.bounds.top_mm
        assert label.bounds.bottom_mm <= rect.bottom_mm + 1e-6


def test_grid_labels_sit_outside_chart_rect() -> None:
    style = STYLE.model_copy(
        update={"grid": STYLE.grid.model_copy(update={"label_placement": "outside"})}
    )
    rect = TRANSFORM.chart_rect
    labels = build_grid_labels(CHART, TRANSFORM, style)
    assert labels
    assert {label.kind for label in labels} == {"ra", "dec"}
    for label in labels:
        bounds = label.bounds
        if label.kind == "ra":
            assert bounds.bottom_mm <= rect.top_mm + 1e-6 or bounds.top_mm >= rect.bottom_mm - 1e-6
        else:
            assert bounds.right_mm <= rect.left_mm + 1e-6 or bounds.left_mm >= rect.right_mm - 1e-6
        assert 0.0 <= bounds.left_mm
        assert bounds.right_mm <= PAGE.width_mm
        assert 0.0 <= bounds.top_mm
        assert bounds.bottom_mm <= PAGE.height_mm


def test_grid_labels_do_not_overlap() -> None:
    def overlaps(first, second) -> bool:
        return not (
            first.right_mm <= second.left_mm
            or second.right_mm <= first.left_mm
            or first.bottom_mm <= second.top_mm
            or second.bottom_mm <= first.top_mm
        )

    for placement in ("inside", "outside"):
        style = STYLE.model_copy(
            update={"grid": STYLE.grid.model_copy(update={"label_placement": placement})}
        )
        labels = build_grid_labels(CHART, TRANSFORM, style)
        assert labels
        for index, first in enumerate(labels):
            for second in labels[index + 1 :]:
                assert not overlaps(first.bounds, second.bounds)


def test_avoid_rect_relocates_or_drops_overlapping_labels() -> None:
    style = STYLE.model_copy(
        update={"grid": STYLE.grid.model_copy(update={"label_placement": "outside"})}
    )
    labels = build_grid_labels(CHART, TRANSFORM, style)
    assert labels
    obstacle = labels[0].bounds
    remaining = build_grid_labels(CHART, TRANSFORM, style, avoid=(obstacle,))
    original_by_id = {label.id: label.bounds for label in labels}
    assert len(remaining) <= len(labels)
    assert any(
        label.id not in original_by_id or label.bounds != original_by_id[label.id]
        for label in remaining
    )
    for label in remaining:
        assert not _rectangles_overlap(label.bounds, obstacle)


def test_label_step_reduces_label_count() -> None:
    every_line = STYLE.model_copy(
        update={
            "grid": STYLE.grid.model_copy(
                update={
                    "label_ra_step_deg": STYLE.grid.ra_step_deg,
                    "label_dec_step_deg": STYLE.grid.dec_step_deg,
                    "label_min_spacing_mm": 0.0,
                }
            )
        }
    )
    sparse_style = STYLE.model_copy(
        update={
            "grid": STYLE.grid.model_copy(
                    update={
                        "label_ra_step_deg": STYLE.grid.ra_step_deg * 2.0,
                        "label_dec_step_deg": STYLE.grid.dec_step_deg * 2.0,
                        "label_min_spacing_mm": 0.0,
                    }
            )
        }
    )
    sparse = build_grid_labels(CHART, TRANSFORM, sparse_style)
    dense = build_grid_labels(CHART, TRANSFORM, every_line)
    assert 0 < len(sparse) < len(dense)


def test_min_spacing_thins_crowded_polar_labels() -> None:
    """Near a pole, meridians converge and adjacent labels must be skipped."""
    chart = ChartDefinition(
        id="near-pole", center_ra_deg=0.0, center_dec_deg=72.0, width_deg=27.0, height_deg=18.5
    )
    transform = PageTransform(chart=chart, page=PAGE)
    dense = STYLE.model_copy(
        update={
            "grid": STYLE.grid.model_copy(
                update={
                    "label_min_spacing_mm": 0.0,
                    "label_polar_ra_step_deg": STYLE.grid.polar_ra_step_deg,
                }
            )
        }
    )
    thinned = STYLE.model_copy(
        update={"grid": STYLE.grid.model_copy(update={"label_min_spacing_mm": 50.0})}
    )
    dense_labels = build_grid_labels(chart, transform, dense)
    thinned_labels = build_grid_labels(chart, transform, thinned)
    assert 0 < len(thinned_labels) < len(dense_labels)
    # Labels on the same edge are at least the minimum spacing apart.
    by_edge: dict[str, list[float]] = {}
    for label in thinned_labels:
        edge = label.id.rsplit(":", 1)[-1]
        along = label.bounds.left_mm if label.kind == "ra" else label.bounds.top_mm
        by_edge.setdefault(edge, []).append(along)
    for positions in by_edge.values():
        ordered = sorted(positions)
        assert all(
            later - earlier >= 13.0 - 1e-6
            for earlier, later in zip(ordered, ordered[1:], strict=False)
        )


def test_polar_ra_labels_use_polar_step() -> None:
    chart = ChartDefinition(
        id="polar", center_ra_deg=0.0, center_dec_deg=90.0, width_deg=27.0, height_deg=18.5
    )
    transform = PageTransform(chart=chart, page=PAGE)
    labels = build_grid_labels(chart, transform, STYLE)
    ra_labels = [label for label in labels if label.kind == "ra"]
    assert ra_labels
    step = STYLE.grid.label_polar_ra_step_deg
    assert step is not None
    for label in ra_labels:
        assert label.value_deg % step == pytest.approx(0.0, abs=1e-9)


def test_disabled_grid_labels_are_empty() -> None:
    style = STYLE.model_copy(
        update={"grid": STYLE.grid.model_copy(update={"labels_enabled": False})}
    )
    assert build_grid_labels(CHART, TRANSFORM, style) == ()
