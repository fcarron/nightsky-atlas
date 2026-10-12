"""Tests for hard label collision checks."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from nightsky_atlas.atlas.config import load_style_config
from nightsky_atlas.catalog.constellations import ConstellationSegment
from nightsky_atlas.catalog.models import DeepSkyObject, DsoType, Provenance, Star
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.chart.page import PagePoint, PageRect, PageTransform
from nightsky_atlas.layout.collision import IssueType, find_hard_violations
from nightsky_atlas.layout.models import CompassPosition, Label, LabelCandidate
from nightsky_atlas.layout.validation import validate_layout
from nightsky_atlas.projection.base import ChartPoint
from nightsky_atlas.render.symbols import StarSizeModel
from nightsky_atlas.scene.builder import build_scene
from nightsky_atlas.scene.models import SceneConstellationRegion

REPO_ROOT = Path(__file__).resolve().parents[2]
STYLE = load_style_config(REPO_ROOT / "styles" / "standard.yaml")

CHART = ChartDefinition(
    id="test", center_ra_deg=187.5, center_dec_deg=12.0, width_deg=20.0, height_deg=14.0
)
PAGE = PageGeometry(width_mm=297.0, height_mm=210.0, margin_mm=12.0)
TRANSFORM = PageTransform(chart=CHART, page=PAGE)
CENTER = TRANSFORM.center_page


def make_star(magnitude: float = 3.0) -> Star:
    return Star(
        id="s1",
        ra_deg=187.5,
        dec_deg=12.0,
        magnitude=magnitude,
        provenance=Provenance(catalogue="TEST", source_id="s1"),
    )


def make_dso() -> DeepSkyObject:
    return DeepSkyObject(
        id="NGC1",
        ra_deg=187.5,
        dec_deg=12.0,
        object_type=DsoType.GALAXY,
        provenance=Provenance(catalogue="TEST", source_id="NGC1"),
        magnitude=8.0,
    )


def make_label(label_id: str, left_mm: float, top_mm: float) -> Label:
    bounds = PageRect(left_mm=left_mm, top_mm=top_mm, width_mm=8.0, height_mm=2.5)
    candidate = LabelCandidate(
        id=f"{label_id}:N",
        position=CompassPosition.N,
        anchor=PagePoint(left_mm, top_mm),
        bounds=bounds,
    )
    return Label(
        id=label_id,
        target_id="NGC1",
        text="X",
        priority=50,
        mandatory=True,
        candidates=(candidate,),
    )


def make_dso_glyph_label(label_id: str, top_mm: float) -> Label:
    bounds = PageRect(left_mm=40.0, top_mm=top_mm, width_mm=8.0, height_mm=3.175)
    candidate = LabelCandidate(
        id=f"{label_id}:N",
        position=CompassPosition.N,
        anchor=PagePoint(bounds.left_mm, bounds.top_mm),
        bounds=bounds,
        glyph_bounds=(PageRect(40.0, top_mm + 0.706, 5.644, 2.117),),
    )
    return Label(
        id=label_id,
        target_id=label_id.removeprefix("label:dso:"),
        text="4387",
        priority=50,
        mandatory=True,
        candidates=(candidate,),
    )


def make_star_label_with_bounds(label_id: str, bounds: PageRect) -> Label:
    candidate = LabelCandidate(
        id=f"{label_id}:N",
        position=CompassPosition.N,
        anchor=PagePoint(bounds.left_mm, bounds.top_mm),
        bounds=bounds,
    )
    return Label(
        id=label_id,
        target_id="s1",
        text="Star",
        priority=50,
        mandatory=True,
        candidates=(candidate,),
    )


def scene_with_center_objects():
    return build_scene(CHART, [make_star()], [make_dso()])


def test_valid_layout_has_no_issues() -> None:
    scene = scene_with_center_objects()
    label = make_label("label:a", 20.0, 20.0)
    result = validate_layout((label,), scene, TRANSFORM, STYLE)
    assert result.is_valid


def test_label_overlapping_star_and_dso() -> None:
    scene = scene_with_center_objects()
    label = make_label("label:a", CENTER.x_mm - 4.0, CENTER.y_mm - 1.0)
    issues = find_hard_violations((label,), scene, TRANSFORM, STYLE)
    types = {issue.issue_type for issue in issues}
    assert IssueType.LABEL_STAR in types
    assert IssueType.LABEL_DSO in types


def test_elongated_galaxy_label_uses_ellipse_not_bounding_circle() -> None:
    galaxy = replace(
        make_dso(),
        major_axis_arcmin=40.0,
        minor_axis_arcmin=4.0,
        position_angle_deg=0.0,
    )
    scene = build_scene(CHART, (), (galaxy,))
    candidate = LabelCandidate(
        id="label:dso:NGC1:E",
        position=CompassPosition.E,
        anchor=PagePoint(CENTER.x_mm + 1.5, CENTER.y_mm - 1.0),
        bounds=PageRect(CENTER.x_mm + 1.5, CENTER.y_mm - 1.0, 2.0, 2.0),
    )
    label = replace(
        make_label("label:dso:NGC1", candidate.bounds.left_mm, candidate.bounds.top_mm),
        candidates=(candidate,),
    )
    issues = find_hard_violations((label,), scene, TRANSFORM, STYLE)
    assert IssueType.LABEL_DSO not in {issue.issue_type for issue in issues}


def test_nearby_rendered_faint_star_is_not_a_hard_blocker() -> None:
    scene = build_scene(CHART, [make_star(magnitude=11.0)], [])
    label = make_label("label:a", CENTER.x_mm - 4.0, CENTER.y_mm - 1.0)
    issues = find_hard_violations((label,), scene, TRANSFORM, STYLE)
    assert IssueType.LABEL_STAR not in {issue.issue_type for issue in issues}


def test_significant_foreign_star_with_subminimum_edge_clearance_is_illegal() -> None:
    star = make_star(magnitude=3.0)
    scene = build_scene(CHART, [star], [])
    radius = StarSizeModel.from_style(STYLE.star).radius_mm(3.0)
    label = make_label(
        "label:foreign",
        CENTER.x_mm + radius + 0.02,
        CENTER.y_mm - 1.25,
    )
    issues = find_hard_violations((label,), scene, TRANSFORM, STYLE)
    assert IssueType.LABEL_STAR in {issue.issue_type for issue in issues}


def test_associated_star_uses_its_own_smaller_clearance_rule() -> None:
    star = make_star(magnitude=6.0)
    scene = build_scene(CHART, [star], [])
    radius = StarSizeModel.from_style(STYLE.star).radius_mm(6.0)
    bounds = PageRect(CENTER.x_mm + radius + 0.36, CENTER.y_mm - 1.25, 8.0, 2.5)
    candidate = LabelCandidate(
        id="label:star:N", position=CompassPosition.N, anchor=bounds.center, bounds=bounds
    )
    label = Label(
        id="label:star",
        target_id="s1",
        text="Star",
        priority=50,
        mandatory=True,
        candidates=(candidate,),
    )
    issues = find_hard_violations((label,), scene, TRANSFORM, STYLE)
    assert IssueType.LABEL_STAR not in {issue.issue_type for issue in issues}


def test_label_label_overlap() -> None:
    scene = build_scene(CHART, [], [])
    first = make_label("label:a", 30.0, 30.0)
    second = make_label("label:b", 32.0, 30.5)
    issues = find_hard_violations((first, second), scene, TRANSFORM, STYLE)
    label_label = [issue for issue in issues if issue.issue_type == IssueType.LABEL_LABEL]
    assert len(label_label) == 1
    assert label_label[0].id == "issue:label_label:label:a:label:b"


def test_label_outside_printable_area() -> None:
    scene = build_scene(CHART, [], [])
    label = make_label("label:a", 2.0, 2.0)
    issues = find_hard_violations((label,), scene, TRANSFORM, STYLE)
    assert IssueType.LABEL_PAGE in {issue.issue_type for issue in issues}


def test_invalid_selection_is_reported() -> None:
    scene = build_scene(CHART, [], [])
    label = make_label("label:a", 30.0, 30.0).with_selection("label:a:ZZ")
    issues = find_hard_violations((label,), scene, TRANSFORM, STYLE)
    assert IssueType.INVALID_SELECTION in {issue.issue_type for issue in issues}


def test_mandatory_label_without_candidates() -> None:
    scene = build_scene(CHART, [], [])
    label = Label(
        id="label:empty",
        target_id="X",
        text="X",
        priority=50,
        mandatory=True,
        candidates=(),
    )
    issues = find_hard_violations((label,), scene, TRANSFORM, STYLE)
    assert IssueType.MISSING_CANDIDATE in {issue.issue_type for issue in issues}


def test_result_counts_by_type() -> None:
    scene = scene_with_center_objects()
    label = make_label("label:a", CENTER.x_mm - 4.0, CENTER.y_mm - 1.0)
    result = validate_layout((label,), scene, TRANSFORM, STYLE)
    counts = result.count_by_type()
    assert counts["label_star"] >= 1
    assert counts["label_dso"] >= 1


def test_duplicate_label_id_is_reported() -> None:
    scene = scene_with_center_objects()
    first = make_label("label:a", 20.0, 20.0)
    second = make_label("label:a", 60.0, 60.0)
    issues = find_hard_violations((first, second), scene, TRANSFORM, STYLE)
    assert IssueType.DUPLICATE_LABEL_ID in {issue.issue_type for issue in issues}


def test_dso_label_collisions_use_configured_ink_clearance() -> None:
    scene = build_scene(CHART, [], [])
    first = make_dso_glyph_label("label:dso:NGC4387", 40.0)
    second = make_dso_glyph_label("label:dso:NGC4438", 42.3)

    legacy_placement = STYLE.label.dso_placement.model_copy(
        update={"label_label_ink_clearance_mm": None}
    )
    legacy_label_style = STYLE.label.model_copy(update={"dso_placement": legacy_placement})
    legacy_style = STYLE.model_copy(update={"label": legacy_label_style})
    legacy_issues = find_hard_violations((first, second), scene, TRANSFORM, legacy_style)
    assert IssueType.LABEL_LABEL in {issue.issue_type for issue in legacy_issues}

    for clearance_mm in (0.10, 0.15):
        placement = STYLE.label.dso_placement.model_copy(
            update={"label_label_ink_clearance_mm": clearance_mm}
        )
        label_style = STYLE.label.model_copy(update={"dso_placement": placement})
        style = STYLE.model_copy(update={"label": label_style})
        issues = find_hard_violations((first, second), scene, TRANSFORM, style)
        assert IssueType.LABEL_LABEL not in {issue.issue_type for issue in issues}

    placement = STYLE.label.dso_placement.model_copy(
        update={"label_label_ink_clearance_mm": 0.20}
    )
    label_style = STYLE.label.model_copy(update={"dso_placement": placement})
    style = STYLE.model_copy(update={"label": label_style})
    issues = find_hard_violations((first, second), scene, TRANSFORM, style)
    assert IssueType.LABEL_LABEL in {issue.issue_type for issue in issues}


def test_dso_label_page_clipping_still_uses_logical_bounds() -> None:
    scene = build_scene(CHART, [], [])
    label = make_dso_glyph_label("label:dso:NGC4387", PAGE.margin_mm - 0.2)
    placement = STYLE.label.dso_placement.model_copy(
        update={"label_label_ink_clearance_mm": 0.15}
    )
    label_style = STYLE.label.model_copy(update={"dso_placement": placement})
    style = STYLE.model_copy(update={"label": label_style})

    issues = find_hard_violations((label,), scene, TRANSFORM, style)

    assert IssueType.LABEL_PAGE in {issue.issue_type for issue in issues}


def test_dso_ink_collision_geometry_interacts_with_star_logical_geometry() -> None:
    scene = build_scene(CHART, [], [])
    dso_label = make_dso_glyph_label("label:dso:NGC4387", 40.0)
    star_label = make_star_label_with_bounds(
        "label:star:test", PageRect(40.0, 37.9, 8.0, 2.5)
    )
    placement = STYLE.label.dso_placement.model_copy(
        update={"label_label_ink_clearance_mm": 0.15}
    )
    label_style = STYLE.label.model_copy(update={"dso_placement": placement})
    style = STYLE.model_copy(update={"label": label_style})

    issues = find_hard_violations((dso_label, star_label), scene, TRANSFORM, style)

    assert IssueType.LABEL_LABEL not in {issue.issue_type for issue in issues}


def test_unknown_target_is_reported() -> None:
    scene = build_scene(CHART, [], [])
    label = make_label("label:a", 20.0, 20.0)
    issues = find_hard_violations((label,), scene, TRANSFORM, STYLE)
    assert IssueType.UNKNOWN_TARGET in {issue.issue_type for issue in issues}


def test_known_target_is_accepted() -> None:
    scene = scene_with_center_objects()
    label = make_label("label:a", 20.0, 20.0)
    types = {
        issue.issue_type for issue in find_hard_violations((label,), scene, TRANSFORM, STYLE)
    }
    assert IssueType.UNKNOWN_TARGET not in types
    assert IssueType.DUPLICATE_LABEL_ID not in types


@pytest.mark.parametrize("object_type", (DsoType.GALAXY, DsoType.OPEN_CLUSTER))
def test_label_inside_large_dso_footprint_does_not_hit_its_outline(
    object_type: DsoType,
) -> None:
    dso = replace(
        make_dso(),
        object_type=object_type,
        major_axis_arcmin=500.0,
        minor_axis_arcmin=360.0,
    )
    scene = build_scene(CHART, [], [dso])
    label = make_label(
        "label:dso:NGC1",
        CENTER.x_mm - 4.0,
        CENTER.y_mm - 1.25,
    )

    issues = find_hard_violations((label,), scene, TRANSFORM, STYLE)

    assert not any(
        issue.issue_type == IssueType.LABEL_DSO
        and "NGC1" in issue.element_ids
        for issue in issues
    )


def test_constellation_layout_target_is_accepted() -> None:
    segment = ConstellationSegment(
        id="ori:line",
        ra1_deg=186.0,
        dec1_deg=11.0,
        ra2_deg=187.0,
        dec2_deg=12.0,
        provenance=Provenance(catalogue="TEST", source_id="ori:line"),
        constellation_id="Ori",
    )
    scene = build_scene(CHART, [], [], constellation_lines=(segment,))
    label = replace(
        make_label("label:constellation:Ori", 20.0, 20.0),
        target_id="constellation:Ori",
    )
    types = {
        issue.issue_type for issue in find_hard_violations((label,), scene, TRANSFORM, STYLE)
    }
    assert IssueType.UNKNOWN_TARGET not in types


def test_constellation_region_is_a_valid_label_target_without_local_lines() -> None:
    scene = replace(
        build_scene(CHART, [], []),
        constellation_regions=(
            SceneConstellationRegion(
                constellation_id="Com",
                rings=((ChartPoint(-1.0, -1.0), ChartPoint(1.0, -1.0), ChartPoint(0.0, 1.0)),),
                visible_area_fraction=0.5,
                centroid=ChartPoint(0.0, 0.0),
            ),
        ),
    )
    label = replace(
        make_label("label:constellation:Com", 20.0, 20.0),
        target_id="constellation:Com",
    )

    types = {
        issue.issue_type for issue in find_hard_violations((label,), scene, TRANSFORM, STYLE)
    }

    assert IssueType.UNKNOWN_TARGET not in types


def test_label_overlapping_furniture_is_reported() -> None:
    scene = build_scene(CHART, [], [])
    label = make_label("label:a", 20.0, 20.0)
    obstacle = PageRect(left_mm=18.0, top_mm=19.0, width_mm=10.0, height_mm=5.0)
    issues = find_hard_violations(
        (label,), scene, TRANSFORM, STYLE, furniture=(obstacle,)
    )
    assert IssueType.FURNITURE_OVERLAP in {issue.issue_type for issue in issues}


def test_label_clear_of_furniture_is_valid() -> None:
    scene = build_scene(CHART, [], [])
    label = make_label("label:a", 20.0, 20.0)
    obstacle = PageRect(left_mm=150.0, top_mm=150.0, width_mm=10.0, height_mm=5.0)
    issues = find_hard_violations(
        (label,), scene, TRANSFORM, STYLE, furniture=(obstacle,)
    )
    assert IssueType.FURNITURE_OVERLAP not in {issue.issue_type for issue in issues}
