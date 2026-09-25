"""Tests for separating rendered text ink from logical layout extents."""

from __future__ import annotations

import pytest

from nightsky_atlas.atlas.config import load_style_config
from nightsky_atlas.chart.page import PagePoint, PageRect
from nightsky_atlas.layout.models import CompassPosition, Label, LabelCandidate
from nightsky_atlas.layout.text_geometry import (
    candidate_ink_bounds,
    dso_collision_bounds,
    label_collision_bounds,
)
from nightsky_atlas.render.text import TextMeasurer


def test_candidate_ink_bounds_uses_measured_production_glyph_geometry() -> None:
    metrics = TextMeasurer("DejaVu Sans", 6.5).measure_mm("4387")
    logical = PageRect(40.0, 50.0, metrics.width_mm, metrics.height_mm)
    glyphs = tuple(
        PageRect(
            logical.left_mm + rect.left_mm,
            logical.top_mm + rect.top_mm,
            rect.width_mm,
            rect.height_mm,
        )
        for rect in metrics.ink_rects_mm
    )
    candidate = LabelCandidate(
        id="label:dso:NGC4387:N",
        position=CompassPosition.N,
        anchor=PagePoint(logical.left_mm, logical.top_mm),
        bounds=logical,
        glyph_bounds=glyphs,
    )

    ink = candidate_ink_bounds(candidate)

    assert ink.width_mm == pytest.approx(metrics.ink_bounds_mm.width_mm)
    assert ink.height_mm == pytest.approx(metrics.ink_bounds_mm.height_mm)
    assert ink.width_mm <= logical.width_mm + 1.0e-6
    assert ink.height_mm < logical.height_mm


def test_ink_clearance_is_total_edge_gap_and_not_applied_to_logical_bounds() -> None:
    candidate = LabelCandidate(
        id="label:dso:NGC4387:N",
        position=CompassPosition.N,
        anchor=PagePoint(40.0, 50.0),
        bounds=PageRect(40.0, 50.0, 8.0, 3.2),
        glyph_bounds=(PageRect(40.0, 50.7, 5.6, 2.1),),
    )

    collision = dso_collision_bounds(candidate, 0.2)
    assert collision.left_mm == 39.9
    assert collision.top_mm == 50.6
    assert collision.width_mm == pytest.approx(5.8)
    assert collision.height_mm == pytest.approx(2.3)
    assert dso_collision_bounds(candidate, None) == candidate.bounds


def test_missing_glyph_geometry_falls_back_to_logical_bounds() -> None:
    candidate = LabelCandidate(
        id="label:dso:NGC4387:N",
        position=CompassPosition.N,
        anchor=PagePoint(40.0, 50.0),
        bounds=PageRect(40.0, 50.0, 8.0, 3.2),
    )
    assert candidate_ink_bounds(candidate) == candidate.bounds


def test_star_label_collision_bounds_remain_logical() -> None:
    candidate = LabelCandidate(
        id="label:star:HIP1:N",
        position=CompassPosition.N,
        anchor=PagePoint(40.0, 50.0),
        bounds=PageRect(40.0, 50.0, 8.0, 3.2),
        glyph_bounds=(PageRect(40.0, 50.7, 5.6, 2.1),),
    )
    label = Label(
        id="label:star:HIP1",
        target_id="HIP1",
        text="Star",
        priority=50,
        mandatory=True,
        candidates=(candidate,),
    )
    assert label_collision_bounds(label, candidate, ink_clearance_mm=0.2) == candidate.bounds


def test_standard_dso_label_ink_clearance_is_explicitly_configured() -> None:
    style = load_style_config("styles/standard.yaml")
    assert style.label.dso_placement.label_label_ink_clearance_mm == 0.20
