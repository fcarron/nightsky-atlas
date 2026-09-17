"""Tests for coordinate grid generation."""

from __future__ import annotations

from pathlib import Path

import pytest

from nightsky_atlas.atlas.config import load_style_config
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.chart.page import PageTransform
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
    assert step > STYLE.grid.ra_step_deg
    for line in meridians:
        assert line.value_deg % step == pytest.approx(0.0, abs=1e-9)


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


def test_avoid_rect_drops_overlapping_labels() -> None:
    style = STYLE.model_copy(
        update={"grid": STYLE.grid.model_copy(update={"label_placement": "outside"})}
    )
    labels = build_grid_labels(CHART, TRANSFORM, style)
    assert labels
    obstacle = labels[0].bounds
    remaining = build_grid_labels(CHART, TRANSFORM, style, avoid=(obstacle,))
    assert len(remaining) < len(labels)
    for label in remaining:
        bounds = label.bounds
        overlaps = (
            bounds.left_mm < obstacle.right_mm
            and obstacle.left_mm < bounds.right_mm
            and bounds.top_mm < obstacle.bottom_mm
            and obstacle.top_mm < bounds.bottom_mm
        )
        assert not overlaps


def test_label_step_reduces_label_count() -> None:
    sparse_style = STYLE.model_copy(
        update={
            "grid": STYLE.grid.model_copy(
                update={"label_ra_step_deg": 10.0, "label_dec_step_deg": 10.0}
            )
        }
    )
    every_line = STYLE
    sparse = build_grid_labels(CHART, TRANSFORM, sparse_style)
    dense = build_grid_labels(CHART, TRANSFORM, every_line)
    assert 0 < len(sparse) < len(dense)


def test_disabled_grid_labels_are_empty() -> None:
    style = STYLE.model_copy(
        update={"grid": STYLE.grid.model_copy(update={"labels_enabled": False})}
    )
    assert build_grid_labels(CHART, TRANSFORM, style) == ()
