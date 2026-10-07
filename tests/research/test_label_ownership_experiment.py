from __future__ import annotations

import importlib.util
from pathlib import Path

import cairo
import pytest

from nightsky_atlas.chart.page import PagePoint, PageRect
from nightsky_atlas.layout.models import CompassPosition, Label, LabelCandidate

TOOL = Path(__file__).resolve().parents[2] / "tools/label_review/make_ownership_experiment.py"
SPEC = importlib.util.spec_from_file_location("ownership_experiment", TOOL)
experiment = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(experiment)


def test_identical_crop_can_be_reused(tmp_path: Path) -> None:
    path = tmp_path / "crop.png"
    crop = cairo.ImageSurface(cairo.FORMAT_ARGB32, 4, 4)
    experiment.save_crop(path, crop)
    expected = path.read_bytes()
    experiment.save_crop(path, crop)
    assert path.read_bytes() == expected


def test_existing_review_image_cannot_be_replaced(tmp_path: Path) -> None:
    path = tmp_path / "crop.png"
    path.write_bytes(b"previous-review-image")
    crop = cairo.ImageSurface(cairo.FORMAT_ARGB32, 4, 4)
    with pytest.raises(ValueError, match="Refusing to change"):
        experiment.save_crop(path, crop)
    assert path.read_bytes() == b"previous-review-image"


def source(object_id: str, x_mm: float, radius_mm: float = 0.6) -> dict:
    return {
        "id": object_id,
        "center": {"x_mm": x_mm, "y_mm": 50.0},
        "radius_x_mm": radius_mm,
        "radius_y_mm": radius_mm,
        "shape": "circle",
        "outline_paths": [],
    }


def test_separated_small_target_is_click_evaluable() -> None:
    target = source("NGC1", 50.0)
    page = {"source_geometries": [target, source("NGC2", 53.0)], "printed_stars": []}
    assert experiment.isolated_target(target, page)


@pytest.mark.parametrize("distance_mm", [0.3, 1.99, 2.24])
def test_click_tolerance_neighbourhoods_do_not_overlap(distance_mm: float) -> None:
    target = source("NGC1", 50.0)
    page = {
        "source_geometries": [target, source("NGC2", 50.0 + distance_mm)],
        "printed_stars": [],
    }
    assert not experiment.isolated_target(target, page)


def test_large_foreign_footprint_is_rejected_despite_separated_centres() -> None:
    target = source("NGC1", 50.0)
    page = {"source_geometries": [target, source("NGC2", 55.0, 5.0)], "printed_stars": []}
    assert not experiment.isolated_target(target, page)


def test_collapsed_double_marker_is_included_in_click_safety() -> None:
    target = source("NGC1", 50.0)
    star = {
        "center": {"x_mm": 52.0, "y_mm": 50.0},
        "radius_mm": 0.1,
        "marker_length_mm": 2.0,
    }
    page = {"source_geometries": [target], "printed_stars": [star]}
    assert not experiment.isolated_target(target, page)


def test_weak_extent_does_not_override_foreign_contour() -> None:
    target = source("NGC1", 50.0)
    cloud = source("Cloud", 60.0)
    cloud["outline_paths"] = [
        [
            {"x_mm": 40.0, "y_mm": 40.0},
            {"x_mm": 65.0, "y_mm": 60.0},
        ]
    ]
    page = {"source_geometries": [target, cloud], "printed_stars": []}
    assert not experiment.isolated_target(target, page)


def test_hard_issue_outside_crop_does_not_contaminate_case() -> None:
    candidate = LabelCandidate(
        id="candidate",
        position=CompassPosition.E,
        anchor=PagePoint(50.0, 50.0),
        bounds=PageRect(60.0, 50.0, 4.0, 2.0),
    )
    label = Label(
        id="label:dso:NGC1",
        target_id="NGC1",
        text="1",
        priority=50,
        mandatory=False,
        candidates=(candidate,),
        selected_candidate_id="candidate",
    )
    page = {
        "labels": [label.to_dict()],
        "source_geometries": [],
        "printed_stars": [],
        "issues": [{"element_ids": [label.id]}],
    }
    assert not experiment.crop_has_issue(page, (10.0, 10.0, 20.0, 20.0))
    assert experiment.crop_has_issue(page, (59.0, 49.0, 10.0, 10.0))


def test_experiment_detects_unintended_second_parameter_change() -> None:
    baseline = {
        "label": {
            "source_association": {"ambiguity_weight": 20.0},
            "leader_lines": {"dso_length_weight": 4.0},
        }
    }
    trial = {
        "label": {
            "source_association": {"ambiguity_weight": 60.0},
            "leader_lines": {"dso_length_weight": 1.0},
        }
    }
    assert experiment.changed_paths(baseline, trial) == [
        "label.leader_lines.dso_length_weight",
        "label.source_association.ambiguity_weight",
    ]
