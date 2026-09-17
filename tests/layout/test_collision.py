"""Tests for hard label collision checks."""

from __future__ import annotations

from pathlib import Path

from nightsky_atlas.atlas.config import load_style_config
from nightsky_atlas.catalog.models import DeepSkyObject, DsoType, Provenance, Star
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.chart.page import PagePoint, PageRect, PageTransform
from nightsky_atlas.layout.collision import IssueType, find_hard_violations
from nightsky_atlas.layout.models import CompassPosition, Label, LabelCandidate
from nightsky_atlas.layout.validation import validate_layout
from nightsky_atlas.scene.builder import build_scene

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


def test_faint_star_is_not_important() -> None:
    scene = build_scene(CHART, [make_star(magnitude=11.0)], [])
    label = make_label("label:a", CENTER.x_mm - 4.0, CENTER.y_mm - 1.0)
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