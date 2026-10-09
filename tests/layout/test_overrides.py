"""Tests for manual, stable-ID label overrides."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from nightsky_atlas.atlas.config import load_style_config
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.chart.page import PagePoint, PageRect, PageTransform
from nightsky_atlas.layout.models import CompassPosition, Label, LabelCandidate
from nightsky_atlas.layout.optimizer import optimize_labels
from nightsky_atlas.layout.overrides import (
    OverrideError,
    apply_overrides,
    load_override_library,
    load_overrides,
    load_overrides_dir,
)
from nightsky_atlas.scene.builder import build_scene

REPO_ROOT = Path(__file__).resolve().parents[2]
STYLE = load_style_config(REPO_ROOT / "styles" / "standard.yaml")

CHART = ChartDefinition(
    id="c1", center_ra_deg=187.5, center_dec_deg=12.0, width_deg=20.0, height_deg=14.0
)
PAGE = PageGeometry(width_mm=297.0, height_mm=210.0, margin_mm=12.0)
TRANSFORM = PageTransform(chart=CHART, page=PAGE)
EMPTY_SCENE = build_scene(CHART, [], [])


def make_candidate(
    label_id: str, position: CompassPosition, left: float, top: float, *, ring: int = 0
) -> LabelCandidate:
    candidate_id = (
        f"{label_id}:{position.value}" if ring == 0 else f"{label_id}:{position.value}:{ring}"
    )
    return LabelCandidate(
        id=candidate_id,
        position=position,
        anchor=PagePoint(left, top),
        bounds=PageRect(left, top, 8.0, 2.5),
        ring=ring,
    )


def make_label(
    label_id: str = "label:dso:M87",
    *,
    candidates: tuple[LabelCandidate, ...] | None = None,
    mandatory: bool = True,
) -> Label:
    if candidates is None:
        candidates = (
            make_candidate(label_id, CompassPosition.N, 100.0, 100.0),
            make_candidate(label_id, CompassPosition.SW, 100.0, 110.0),
            make_candidate(label_id, CompassPosition.N, 100.0, 116.0, ring=1),
        )
    return Label(
        id=label_id,
        target_id="NGC4486",
        text="M87",
        priority=100,
        mandatory=mandatory,
        candidates=candidates,
    )


def write_override(tmp_path: Path, payload: dict, name: str = "chart.yaml") -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return path


def test_load_single_override(tmp_path: Path) -> None:
    path = write_override(
        tmp_path,
        {
            "chart": "c1",
            "labels": {"label:dso:M87": {"candidate": "SW", "locked": True}},
        },
    )
    overrides = load_overrides(path)
    assert overrides.chart == "c1"
    assert len(overrides) == 1
    spec = overrides.labels["label:dso:M87"]
    assert spec.candidate == "SW"
    assert spec.locked is True
    assert spec.hidden is None


def test_free_offset_and_leader_line_override_translates_all_measured_bounds(
    tmp_path: Path,
) -> None:
    label = make_label()
    original = label.candidates[0]
    original = replace(
        original,
        glyph_bounds=(PageRect(100.5, 100.4, 3.0, 1.2),),
        whitespace_bounds=(PageRect(100.0, 100.0, 8.0, 2.5),),
    )
    label = replace(label, candidates=(original, *label.candidates[1:]))
    path = write_override(
        tmp_path,
        {
            "chart": "c1",
            "labels": {
                "label:dso:M87": {
                    "candidate": "N",
                    "offset_mm": {"x": -1.0, "y": 1.5},
                    "leader_line": True,
                    "locked": True,
                }
            },
        },
    )

    edited = apply_overrides((label,), load_overrides(path))[0]
    candidate = edited.effective_candidate()
    assert candidate is not None
    assert edited.leader_line is True
    assert edited.locked is True
    assert candidate.bounds.left_mm == pytest.approx(99.0)
    assert candidate.bounds.top_mm == pytest.approx(101.5)
    assert candidate.glyph_bounds == (PageRect(99.5, 101.9, 3.0, 1.2),)
    assert candidate.whitespace_bounds == (PageRect(99.0, 101.5, 8.0, 2.5),)


def test_offset_override_requires_candidate_and_finite_values(tmp_path: Path) -> None:
    path = write_override(
        tmp_path,
        {"chart": "c1", "labels": {"label:dso:M87": {"offset_mm": {"x": 0, "y": 1}}}},
    )
    with pytest.raises(OverrideError, match="offset_mm requires"):
        load_overrides(path)

    path = write_override(
        tmp_path,
        {
            "chart": "c1",
            "labels": {
                "label:dso:M87": {"candidate": "N", "offset_mm": {"x": float("nan"), "y": 0}}
            },
        },
    )
    with pytest.raises(OverrideError):
        load_overrides(path)


def test_unknown_label_key_rejected(tmp_path: Path) -> None:
    path = write_override(
        tmp_path,
        {"chart": "c1", "labels": {"label:dso:M87": {"offset_mm": 2.0}}},
    )
    with pytest.raises(OverrideError):
        load_overrides(path)


def test_unknown_root_key_rejected(tmp_path: Path) -> None:
    path = write_override(
        tmp_path,
        {"chart": "c1", "labels": {}, "unexpected": True},
    )
    with pytest.raises(OverrideError):
        load_overrides(path)


def test_apply_by_compass_position(tmp_path: Path) -> None:
    path = write_override(
        tmp_path,
        {
            "chart": "c1",
            "labels": {"label:dso:M87": {"candidate": "SW", "locked": True}},
        },
    )
    labels = apply_overrides((make_label(),), load_overrides(path))
    assert labels[0].selected_candidate_id == "label:dso:M87:SW"
    assert labels[0].locked is True
    assert labels[0].hidden is False


def test_apply_by_explicit_candidate_id(tmp_path: Path) -> None:
    path = write_override(
        tmp_path,
        {"chart": "c1", "labels": {"label:dso:M87": {"candidate": "label:dso:M87:N:1"}}},
    )
    labels = apply_overrides((make_label(),), load_overrides(path))
    assert labels[0].selected_candidate_id == "label:dso:M87:N:1"
    assert labels[0].locked is False


def test_apply_hidden_override(tmp_path: Path) -> None:
    path = write_override(
        tmp_path,
        {"chart": "c1", "labels": {"label:dso:M87": {"hidden": True}}},
    )
    labels = apply_overrides((make_label(),), load_overrides(path))
    assert labels[0].hidden is True
    assert labels[0].selected_candidate_id is None


def test_unknown_label_rejected(tmp_path: Path) -> None:
    path = write_override(
        tmp_path,
        {"chart": "c1", "labels": {"label:dso:NGC999": {"candidate": "N"}}},
    )
    with pytest.raises(OverrideError, match="unknown label"):
        apply_overrides((make_label(),), load_overrides(path))


def test_invalid_candidate_rejected(tmp_path: Path) -> None:
    path = write_override(
        tmp_path,
        {"chart": "c1", "labels": {"label:dso:M87": {"candidate": "label:dso:M87:ZZ"}}},
    )
    with pytest.raises(OverrideError, match="not a valid candidate"):
        apply_overrides((make_label(),), load_overrides(path))


def test_locked_without_candidate_rejected(tmp_path: Path) -> None:
    path = write_override(
        tmp_path,
        {"chart": "c1", "labels": {"label:dso:M87": {"locked": True}}},
    )
    with pytest.raises(OverrideError, match="must specify a candidate"):
        apply_overrides((make_label(),), load_overrides(path))


def test_override_without_candidate_preserves_lock(tmp_path: Path) -> None:
    path = write_override(
        tmp_path,
        {"chart": "c1", "labels": {"label:a": {"hidden": False}}},
    )
    locked = make_label("label:a").with_placement("label:a:N", locked=True)
    labels = apply_overrides((locked,), load_overrides(path))
    assert labels[0].locked is True
    assert labels[0].selected_candidate_id == "label:a:N"
    assert labels[0].hidden is False


def test_empty_override_is_a_no_op(tmp_path: Path) -> None:
    path = write_override(
        tmp_path,
        {"chart": "c1", "labels": {"label:a": {}}},
    )
    locked = make_label("label:a").with_placement("label:a:N", locked=True)
    labels = apply_overrides((locked,), load_overrides(path))
    assert labels[0] == locked


def test_optimizer_respects_locked_placement(tmp_path: Path) -> None:
    path = write_override(
        tmp_path,
        {
            "chart": "c1",
            "labels": {"label:a": {"candidate": "N", "locked": True}},
        },
    )
    locked = make_label(
        "label:a",
        candidates=(
            make_candidate("label:a", CompassPosition.N, 100.0, 100.0),
            make_candidate("label:a", CompassPosition.S, 100.0, 140.0),
        ),
    )
    other = make_label(
        "label:b",
        candidates=(
            make_candidate("label:b", CompassPosition.N, 100.0, 100.0),
            make_candidate("label:b", CompassPosition.W, 220.0, 120.0),
        ),
    )
    labels = apply_overrides((locked, other), load_overrides(path))
    result = optimize_labels(labels, EMPTY_SCENE, TRANSFORM, STYLE)
    by_id = {label.id: label for label in result.labels}
    assert by_id["label:a"].selected_candidate_id == "label:a:N"
    assert by_id["label:a"].locked is True
    assert by_id["label:b"].selected_candidate_id == "label:b:W"


def test_load_overrides_dir(tmp_path: Path) -> None:
    write_override(tmp_path, {"chart": "c1", "labels": {}}, name="a.yaml")
    write_override(tmp_path, {"chart": "c2", "labels": {}}, name="b.yaml")
    library = load_overrides_dir(tmp_path)
    assert library.chart_ids() == ("c1", "c2")
    assert library.for_chart("c2") is not None
    assert library.for_chart("missing") is None


def test_duplicate_chart_in_dir_rejected(tmp_path: Path) -> None:
    write_override(tmp_path, {"chart": "c1", "labels": {}}, name="a.yaml")
    write_override(tmp_path, {"chart": "c1", "labels": {}}, name="b.yaml")
    with pytest.raises(OverrideError, match="duplicate overrides"):
        load_overrides_dir(tmp_path)


def test_load_library_from_file(tmp_path: Path) -> None:
    path = write_override(tmp_path, {"chart": "c1", "labels": {}})
    library = load_override_library(path)
    assert library.chart_ids() == ("c1",)
