from __future__ import annotations

import json
import threading
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from nightsky_atlas.chart.page import PagePoint, PageRect
from nightsky_atlas.layout.models import CompassPosition, Label, LabelCandidate
from nightsky_atlas.layout.placement import offset_label_placement
from nightsky_atlas.review.editor import (
    EditorError,
    EditorSession,
    _baseline_fingerprint,
    _Snapshot,
)


def _label(label_id: str, left: float, *, locked: bool = False) -> Label:
    candidate = LabelCandidate(
        id=f"{label_id}:E",
        position=CompassPosition.E,
        anchor=PagePoint(left, 20.0),
        bounds=PageRect(left, 20.0, 8.0, 2.0),
        glyph_bounds=(PageRect(left + 0.2, 20.1, 3.0, 1.1),),
        whitespace_bounds=(PageRect(left, 20.0, 8.0, 2.0),),
    )
    return Label(
        id=label_id,
        target_id=label_id.removeprefix("label:dso:"),
        text="Target",
        priority=10,
        mandatory=True,
        candidates=(candidate,),
        selected_candidate_id=candidate.id,
        locked=locked,
    )


def _session(labels: tuple[Label, ...]) -> EditorSession:
    session = EditorSession.__new__(EditorSession)
    session._baseline = labels
    return session


def test_group_move_uses_page_mm_and_translates_glyph_geometry() -> None:
    labels = (_label("label:dso:A", 10.0), _label("label:dso:B", 30.0))
    session = _session(labels)
    moved, bases = session._apply_operation(
        labels,
        {item.id: item.selected_candidate_id for item in labels},
        {
            "type": "group_move",
            "label_ids": [item.id for item in labels],
            "dx_mm": -2,
            "dy_mm": 1.5,
        },
    )
    assert bases == {item.id: item.selected_candidate_id for item in labels}
    for item, left in zip(moved, (8.0, 28.0), strict=True):
        candidate = item.effective_candidate()
        assert candidate is not None
        assert item.locked is True
        assert candidate.bounds == PageRect(left, 21.5, 8.0, 2.0)
        assert candidate.glyph_bounds == (PageRect(left + 0.2, 21.6, 3.0, 1.1),)
        assert candidate.whitespace_bounds == (PageRect(left, 21.5, 8.0, 2.0),)


def test_locked_labels_remain_manually_editable_in_a_group() -> None:
    labels = (_label("label:dso:A", 10.0), _label("label:dso:B", 30.0, locked=True))
    session = _session(labels)
    moved, _ = session._apply_operation(
        labels,
        {item.id: item.selected_candidate_id for item in labels},
        {
            "type": "group_move",
            "label_ids": [item.id for item in labels],
            "dx_mm": 1,
            "dy_mm": 0,
        },
    )
    assert moved[1].locked is True
    assert moved[1].effective_candidate().bounds.left_mm == 31.0


def test_locked_label_can_be_changed_by_a_manual_offset() -> None:
    label = _label("label:dso:A", 10.0, locked=True)
    moved, _ = _session((label,))._apply_operation(
        (label,),
        {label.id: label.selected_candidate_id},
        {"type": "offset", "label_id": label.id, "x": 0.5, "y": -0.25},
    )
    assert moved[0].locked is True
    assert moved[0].effective_candidate().bounds.left_mm == 10.5


def test_each_real_edit_is_one_undo_step_and_noop_adds_none() -> None:
    labels = (_label("label:dso:A", 10.0),)
    session = _session(labels)
    session._lock = threading.RLock()
    session._labels = labels
    session._base_ids = {labels[0].id: labels[0].selected_candidate_id}
    session._undo = []
    session._redo = []
    session._saved_state = _Snapshot(labels, dict(session._base_ids))
    session._saved_review_status = "unreviewed"
    session._saved_review_method = None
    session._review_status = "unreviewed"
    session._review_method = None
    session._pending_ai = None
    session._pending_ai_hard_issues = ()
    session._render_preview = lambda **kwargs: None
    session._persist_draft = lambda: None
    session.state = lambda: None
    operation = {"operations": [{"type": "offset", "label_id": labels[0].id, "x": 1, "y": 0}]}

    session.apply(operation)
    session.apply(operation)
    assert len(session._undo) == 1
    assert session._labels[0].effective_candidate().bounds.left_mm == 11.0
    session.undo()
    assert session._labels == labels
    assert session._redo
    session.redo()
    assert session._labels[0].effective_candidate().bounds.left_mm == 11.0


def _draft_session(tmp_path: Path, labels: tuple[Label, ...]) -> EditorSession:
    session = EditorSession.__new__(EditorSession)
    session._baseline = labels
    session._labels = labels
    session._base_ids = {item.id: item.selected_candidate_id for item in labels}
    session._baseline_fingerprint = _baseline_fingerprint("chart-a", labels)
    session._saved_state = _Snapshot(labels, dict(session._base_ids))
    session._saved_review_status = "unreviewed"
    session._saved_review_method = None
    session._review_status = "unreviewed"
    session._review_method = None
    session._draft_recovered = False
    session._draft_warning = None
    session._undo = []
    session._redo = []
    session._pending_ai = None
    session._pending_ai_hard_issues = ()
    session.definition = SimpleNamespace(id="chart-a")
    session.outdir = tmp_path
    session._draft_path = session._draft_file_for_saved_state()
    session._render_preview = lambda **kwargs: None
    session.state = lambda: {"labels": session._labels}
    return session


def test_fresh_saved_workspace_state_is_clean_and_has_no_undo(tmp_path: Path) -> None:
    automatic = _label("label:dso:A", 10.0)
    saved = replace(automatic, locked=True)
    session = EditorSession.__new__(EditorSession)
    session._lock = threading.RLock()
    session._baseline = (automatic,)
    session._labels = (saved,)
    session._base_ids = {saved.id: saved.selected_candidate_id}
    session._saved_state = _Snapshot((saved,), dict(session._base_ids))
    session._baseline_fingerprint = _baseline_fingerprint("chart-a", (automatic,))
    session._baseline_optimizer_diagnostics = {}
    session._undo = []
    session._redo = []
    session._pending_ai = None
    session._pending_ai_hard_issues = ()
    session._review_status = "corrected"
    session._review_method = "loaded"
    session._saved_review_status = "corrected"
    session._saved_review_method = "loaded"
    session._draft_recovered = False
    session._draft_warning = None
    session.definition = SimpleNamespace(
        id="chart-a", center_ra_deg=0, center_dec_deg=0, width_deg=1, height_deg=1
    )
    session.atlas = SimpleNamespace(id="pocket")
    session.style = SimpleNamespace(label=SimpleNamespace(font_size_pt=8, font_family="Lato"))
    session.scene = SimpleNamespace(deep_sky_objects=(), stars=())
    session.transform = SimpleNamespace(
        page=SimpleNamespace(width_mm=297, height_mm=210), mm_per_deg=5
    )
    session.external_overrides_path = None
    session.override_path = tmp_path / "overrides.yaml"
    session.override_path.write_text("saved", encoding="utf-8")
    session._validate = lambda labels: SimpleNamespace(issues=())

    state = session.state()

    assert state["has_unsaved_changes"] is False
    assert state["undo_available"] is False
    assert state["redo_available"] is False
    assert state["baseline_origin"] == "saved_workspace_overrides"
    assert state["draft_status"] == "none"
    assert state["labels"][0]["locked"] is True


def test_local_draft_round_trip_is_recoverable_and_undoes_to_saved_state(tmp_path: Path) -> None:
    baseline = (_label("label:dso:A", 10.0),)
    original = _draft_session(tmp_path, baseline)
    placed = offset_label_placement(baseline[0], baseline[0].selected_candidate_id, 1.25, -0.5)
    original._labels = (replace(placed, locked=True, leader_line=True),)
    original._review_status = "corrected"
    original._review_method = "human"
    original._persist_draft()

    reopened = _draft_session(tmp_path, baseline)
    reopened._lock = threading.RLock()
    reopened._load_draft()

    assert reopened._draft_recovered is True
    assert reopened._labels[0].locked is True
    assert reopened._labels[0].leader_line is True
    assert reopened._labels[0].effective_candidate().bounds.left_mm == pytest.approx(11.25)
    assert len(reopened._undo) == 1
    reopened._restore_review_status_for_current_state = lambda: None
    reopened._persist_draft = lambda: None
    reopened.undo()
    assert reopened._labels == baseline
    assert reopened._redo


def test_saved_leader_line_override_matches_normal_renderer_output(tmp_path: Path) -> None:
    from nightsky_atlas.atlas.config import load_style_config
    from nightsky_atlas.catalog.models import DeepSkyObject, DsoType, Provenance
    from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
    from nightsky_atlas.chart.page import PageTransform
    from nightsky_atlas.layout.leader_lines import resolve_leader_lines
    from nightsky_atlas.layout.overrides import apply_overrides, load_override_library
    from nightsky_atlas.render.cairo import render_chart
    from nightsky_atlas.scene.builder import build_scene

    root = Path(__file__).resolve().parents[2]
    style = load_style_config(root / "styles" / "standard.yaml")
    chart = ChartDefinition(
        id="chart-a", center_ra_deg=187.5, center_dec_deg=12.0, width_deg=20, height_deg=14
    )
    transform = PageTransform(chart, PageGeometry(297, 210, 12))
    dso = DeepSkyObject(
        id="NGC4486",
        ra_deg=chart.center_ra_deg,
        dec_deg=chart.center_dec_deg,
        object_type=DsoType.GALAXY,
        provenance=Provenance(catalogue="TEST", source_id="NGC4486"),
        magnitude=8.0,
    )
    scene = build_scene(chart, [], [dso])
    candidate = LabelCandidate(
        id="label:dso:NGC4486:E:2",
        position=CompassPosition.E,
        anchor=PagePoint(160, 104),
        bounds=PageRect(160, 104, 8, 2.5),
        ring=2,
    )
    baseline = Label(
        id="label:dso:NGC4486",
        target_id="NGC4486",
        text="M87",
        priority=100,
        mandatory=True,
        candidates=(candidate,),
        selected_candidate_id=candidate.id,
    )
    edited = replace(baseline, leader_line=True, leader_line_reason="manual", locked=True)
    session = EditorSession.__new__(EditorSession)
    session._lock = threading.RLock()
    session._baseline = (baseline,)
    session._labels = (edited,)
    session._base_ids = {baseline.id: candidate.id}
    session.scene = scene
    session.transform = transform
    session.style = style
    session.definition = chart
    session.atlas = SimpleNamespace(id="standard")
    session.outdir = tmp_path
    session.override_path = tmp_path / "overrides.yaml"
    session.review_path = tmp_path / "review.json"
    session._draft_path = tmp_path / "draft.json"
    session._baseline_fingerprint = _baseline_fingerprint(chart.id, (baseline,))
    session._saved_state = _Snapshot((baseline,), {baseline.id: candidate.id})
    session._saved_review_status = "unreviewed"
    session._saved_review_method = None
    session._review_status = "corrected"
    session._review_method = "human"
    session._draft_recovered = False
    session.external_overrides_path = None

    assert resolve_leader_lines((edited,), scene, transform, style)
    session.save()
    overrides = load_override_library(session.override_path).for_chart(chart.id)
    assert overrides is not None
    rendered_labels = apply_overrides((baseline,), overrides)
    assert rendered_labels == (edited,)
    assert resolve_leader_lines(rendered_labels, scene, transform, style)

    preview_png = tmp_path / "editor-preview.png"
    atlas_png = tmp_path / "atlas-output.png"
    atlas_pdf = tmp_path / "atlas-output.pdf"
    render_chart(scene, transform, style, labels=(edited,), png_path=preview_png, png_dpi=96)
    render_chart(
        scene,
        transform,
        style,
        labels=rendered_labels,
        png_path=atlas_png,
        pdf_path=atlas_pdf,
        png_dpi=96,
    )
    assert preview_png.read_bytes() == atlas_png.read_bytes()
    assert atlas_pdf.read_bytes().startswith(b"%PDF-")


def test_manual_position_operations_lock_labels_for_normal_atlas_builds() -> None:
    labels = (_label("label:dso:A", 10.0),)
    session = _session(labels)
    moved, _ = session._apply_operation(
        labels,
        {labels[0].id: labels[0].selected_candidate_id},
        {"type": "offset", "label_id": labels[0].id, "x": 1.0, "y": -0.5},
    )
    assert moved[0].locked is True

    selected, _ = session._apply_operation(
        labels,
        {labels[0].id: labels[0].selected_candidate_id},
        {"type": "candidate", "label_id": labels[0].id, "candidate": "label:dso:A:E"},
    )
    assert selected[0].locked is True


def test_offset_api_rejects_non_finite_coordinates() -> None:
    labels = (_label("label:dso:A", 10.0),)
    session = _session(labels)
    with pytest.raises(EditorError, match="finite"):
        session._apply_operation(
            labels,
            {labels[0].id: labels[0].selected_candidate_id},
            {"type": "offset", "label_id": labels[0].id, "x": float("inf"), "y": 0},
        )


def test_boolean_is_not_accepted_as_a_millimetre_offset() -> None:
    labels = (_label("label:dso:A", 10.0),)
    with pytest.raises(EditorError, match="finite"):
        _session(labels)._apply_operation(
            labels,
            {labels[0].id: labels[0].selected_candidate_id},
            {"type": "offset", "label_id": labels[0].id, "x": True, "y": 0},
        )


def test_review_status_is_reused_only_for_the_same_baseline(tmp_path: Path) -> None:
    labels = (_label("label:dso:A", 10.0),)
    fingerprint = _baseline_fingerprint("chart-a", labels)
    record = {
        "chart": "chart-a",
        "edition": "pocket",
        "status": "accepted_as_is",
        "method": "human",
        "baseline_fingerprint": fingerprint,
    }
    path = tmp_path / "review.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    session = EditorSession.__new__(EditorSession)
    session.review_path = path
    session.override_path = tmp_path / "overrides.yaml"
    session.definition = SimpleNamespace(id="chart-a")
    session.atlas = SimpleNamespace(id="pocket")
    session._baseline_fingerprint = fingerprint
    session._review_status = "unreviewed"
    session._review_method = None
    session.external_overrides_path = None

    session._load_review_record()

    assert session._review_status == "accepted_as_is"
    assert session._review_method == "human"

    session._baseline_fingerprint = "changed-baseline"
    session._review_status = "unreviewed"
    session._review_method = None
    session._load_review_record()

    assert session._review_status == "unreviewed"
    assert session._review_method is None


def test_accept_as_is_is_blocked_with_an_external_override_source() -> None:
    session = EditorSession.__new__(EditorSession)
    session.external_overrides_path = Path("overrides/review.yaml")

    with pytest.raises(EditorError, match="restart without --overrides"):
        session.accept_as_is()


def test_ai_proposal_with_new_hard_issues_cannot_be_accepted() -> None:
    session = EditorSession.__new__(EditorSession)
    session._lock = threading.RLock()
    session._pending_ai = ()
    session._pending_ai_hard_issues = (object(),)

    with pytest.raises(EditorError, match="adds hard layout issues"):
        session.accept_ai()


def test_ai_request_is_rejected_before_any_provider_without_configuration() -> None:
    session = EditorSession.__new__(EditorSession)
    session.ai_config_path = None
    with pytest.raises(EditorError, match="AI is not configured"):
        session.ai_suggest({"label_ids": ["label:dso:A"]})


def test_manual_leader_line_must_have_a_legal_route(monkeypatch: pytest.MonkeyPatch) -> None:
    import nightsky_atlas.review.editor as editor_module

    session = EditorSession.__new__(EditorSession)
    session.scene = object()
    session.transform = object()
    session.style = object()
    label = replace(_label("label:dso:A", 10.0), leader_line=True, leader_line_reason="manual")
    monkeypatch.setattr(editor_module, "resolve_leader_lines", lambda *args: ())

    with pytest.raises(EditorError, match="cannot be routed"):
        session._ensure_leader_lines_resolve((label,))
