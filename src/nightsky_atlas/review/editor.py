"""Local browser editor for deterministic chart-label placement."""

from __future__ import annotations

import hashlib
import json
import math
import threading
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

from nightsky_atlas.ai.actions import _apply_one, _fine_adjustments
from nightsky_atlas.ai.config import load_ai_config
from nightsky_atlas.ai.openrouter import OpenRouterError, OpenRouterReviewer
from nightsky_atlas.atlas.config import load_atlas_config, load_style_config
from nightsky_atlas.atlas.overview import build_overview, hemisphere_for
from nightsky_atlas.atlas.tiling import chart_definitions
from nightsky_atlas.build.chart import build_chart_context, find_chart, load_chart_inputs
from nightsky_atlas.catalog.models import DsoType
from nightsky_atlas.catalog.priority import HERSCHEL_400, messier_id
from nightsky_atlas.catalog.star_names import DEFAULT_FIXTURE_DIR, load_star_names
from nightsky_atlas.chart.models import ChartDefinition
from nightsky_atlas.chart.page import PageRect
from nightsky_atlas.chart.presentation import (
    ChartPresentation,
    constellation_context,
    presentation_from_edition,
    scene_constellation_area_fractions,
)
from nightsky_atlas.layout.labels import build_labels
from nightsky_atlas.layout.leader_lines import resolve_leader_lines
from nightsky_atlas.layout.models import Label
from nightsky_atlas.layout.optimizer import optimize_labels
from nightsky_atlas.layout.overrides import (
    apply_overrides,
    load_override_library,
)
from nightsky_atlas.layout.placement import offset_label_placement
from nightsky_atlas.layout.selection import select_labels
from nightsky_atlas.layout.validation import validate_layout
from nightsky_atlas.render.cairo import render_chart
from nightsky_atlas.render.detail_markers import build_detail_marker
from nightsky_atlas.render.furniture import furniture_obstacles
from nightsky_atlas.render.overview import LocatorInset
from nightsky_atlas.review.build import build_review_request
from nightsky_atlas.review.schema import ReviewActionType
from nightsky_atlas.scene.models import ChartScene

__all__ = ["EditorError", "EditorSession", "serve_editor"]

MAX_BODY_BYTES = 64_000
APP_ROOT = Path(__file__).resolve().parents[3] / "tools" / "label_editor"
FONT_ASSET_ROOT = Path(__file__).resolve().parents[1] / "assets" / "fonts"
EDITOR_ASSET_MIME_TYPES = {
    "/app.css": "text/css; charset=utf-8",
    "/app.js": "text/javascript; charset=utf-8",
}
EDITOR_FONT_ASSETS = {
    "/fonts/Lato-Regular.ttf": "Lato-Regular.ttf",
    "/fonts/Lato-Bold.ttf": "Lato-Bold.ttf",
}


class EditorError(ValueError):
    """An editor request cannot be applied safely."""


@dataclass(frozen=True, slots=True)
class _Snapshot:
    labels: tuple[Label, ...]
    base_ids: dict[str, str]


class EditorSession:
    """One chart's immutable scene and mutable, validated label presentation."""

    def __init__(
        self,
        *,
        atlas_path: Path,
        style_path: Path,
        chart_id: str,
        outdir: Path,
        star_store: Path | None = None,
        dsos_path: Path | None = None,
        overrides_path: Path | None = None,
        ai_config_path: Path | None = None,
        png_dpi: float = 150.0,
    ) -> None:
        atlas = load_atlas_config(atlas_path)
        style = load_style_config(style_path)
        definition, style, magnitude_limit, scale, detail = _resolve_chart(
            atlas, atlas_path, style_path, chart_id, style
        )
        inputs = load_chart_inputs(
            atlas_path=atlas_path,
            style_path=style_path,
            dsos_path=dsos_path,
            atlas=atlas,
            style=style,
        )
        context = build_chart_context(
            atlas_path=atlas_path,
            style_path=style_path,
            definition=definition,
            star_store=star_store,
            dsos_path=dsos_path,
            magnitude_limit=magnitude_limit,
            scale_mm_per_degree=scale,
            inputs=inputs,
        )
        self.star_store = star_store
        self.atlas = atlas
        self.definition = definition
        self.style = style
        self.scene = context.scene
        self.transform = context.transform
        self.detail_stellar_limit = magnitude_limit
        self.detail_config = detail
        self.detail_markers = tuple(
            build_detail_marker(item, definition, context.transform)
            for item in atlas.detail_charts
            if item.parent_chart_id == definition.id
        )
        self.locator = self._build_locator(context) if detail is None else None
        star_names = load_star_names(DEFAULT_FIXTURE_DIR)
        self.variable_star_hips = frozenset(
            hip for hip, entry in star_names.items() if entry.variable_marker
        )
        labels = build_labels(context.scene, context.transform, style, star_names)
        selection = select_labels(labels, context.scene, context.transform, style)
        if detail is None:
            fallback_ids = self._detail_fallback_ids(
                context, inputs, atlas, atlas_path, style_path, dsos_path
            )
            selection = tuple(label for label in selection if label.target_id not in fallback_ids)
        label_presentation = (
            self._presentation()
            if hasattr(self, "atlas")
            else presentation_from_edition(
                definition, atlas.resolved_edition(), scene=context.scene
            )
        )
        optimized = optimize_labels(
            selection,
            context.scene,
            context.transform,
            style,
            furniture=furniture_obstacles(
                context.transform,
                definition,
                style,
                label_presentation,
            ),
        )
        self._baseline = optimized.labels
        self._baseline_optimizer_diagnostics = optimized.label_diagnostics
        self.scene = context.scene
        self.transform = context.transform
        self.style = style
        self.definition = definition
        self.outdir = outdir.resolve()
        self.outdir.mkdir(parents=True, exist_ok=True)
        self.png_dpi = png_dpi
        self.ai_config_path = ai_config_path
        self.inputs = inputs
        self._scene_for_labels = context.scene
        self.preview_path = self.outdir / "preview.png"
        self.pdf_path = self.outdir / "edited-chart.pdf"
        self.review_path = self.outdir / "review.json"
        self.override_path = self.outdir / "overrides.yaml"
        self.external_overrides_path = (
            overrides_path.resolve()
            if overrides_path is not None and overrides_path.resolve() != self.override_path
            else None
        )
        self._lock = threading.RLock()
        self._labels = self._baseline
        self._base_ids = {
            label.id: candidate.id
            for label in self._baseline
            if (candidate := label.effective_candidate()) is not None
        }
        self._undo: list[_Snapshot] = []
        self._redo: list[_Snapshot] = []
        self._pending_ai: tuple[Label, ...] | None = None
        self._pending_ai_hard_issues: tuple[Any, ...] = ()
        self._review_status = "unreviewed"
        self._review_method: str | None = None
        self._render_preview()
        self._baseline_fingerprint = _baseline_fingerprint(self.definition.id, self._baseline)
        saved_overrides = overrides_path
        if saved_overrides is None and self.override_path.is_file():
            saved_overrides = self.override_path
        if saved_overrides is not None:
            self.load_saved_overrides(saved_overrides)
        self._load_review_record()
        self._saved_state = self._persistence_state()
        self._saved_review_status = self._review_status
        self._saved_review_method = self._review_method
        self._draft_recovered = False
        self._draft_warning: str | None = None
        self._draft_path = self._draft_file_for_saved_state()
        self._load_draft()

    @property
    def labels(self) -> tuple[Label, ...]:
        return self._labels

    def state(self) -> dict[str, Any]:
        with self._lock:
            result = self._validate(self._labels)
            dso_by_id = {item.dso.id: item for item in self.scene.deep_sky_objects}
            labels = []
            for label in self._labels:
                candidate = label.effective_candidate()
                if candidate is None:
                    continue
                base_id = self._base_ids.get(label.id, candidate.id)
                base = label.candidate(base_id) or candidate
                labels.append(
                    {
                        "id": label.id,
                        "target_id": label.target_id,
                        "text": label.text,
                        "font_size_pt": (
                            label.font_size_pt
                            if label.font_size_pt is not None
                            else self.style.label.font_size_pt
                        ),
                        "font_weight": label.font_weight,
                        "mandatory": label.mandatory,
                        "locked": label.locked,
                        "leader_line": label.leader_line,
                        "candidate": candidate.position.value,
                        "candidate_id": candidate.id,
                        "offset_mm": {
                            "x": round(candidate.bounds.left_mm - base.bounds.left_mm, 4),
                            "y": round(candidate.bounds.top_mm - base.bounds.top_mm, 4),
                        },
                        "bounds": _rect_dict(candidate.bounds),
                        "glyph_bounds": [_rect_dict(item) for item in candidate.glyph_bounds],
                        "anchor": {"x": candidate.anchor.x_mm, "y": candidate.anchor.y_mm},
                        "candidates": [
                            {
                                "id": item.id,
                                "position": item.position.value,
                                "ring": item.ring,
                                "bounds": _rect_dict(item.bounds),
                            }
                            for item in label.candidates
                            if ":offset:" not in item.id and ":fine:" not in item.id
                        ],
                        "object": _object_info(dso_by_id.get(label.target_id)),
                    }
                )
            symbol_anchors = _symbol_anchors(self.scene, self.transform)
            return {
                "chart_id": self.definition.id,
                "edition": self.atlas.id,
                "page": {
                    "width_mm": self.transform.page.width_mm,
                    "height_mm": self.transform.page.height_mm,
                },
                "chart": {
                    "center_ra_deg": self.definition.center_ra_deg,
                    "center_dec_deg": self.definition.center_dec_deg,
                    "width_deg": self.definition.width_deg,
                    "height_deg": self.definition.height_deg,
                    "scale_mm_per_degree": self.transform.mm_per_deg,
                },
                "label_font_family": self.style.label.font_family,
                "labels": labels,
                "symbols": symbol_anchors,
                "issues": [_issue_dict(issue) for issue in result.issues],
                "issue_count": len(result.issues),
                "optimizer_hints": self._optimizer_hints(),
                "preview_url": "/preview.png",
                "ai_preview_url": "/ai-preview.png" if self._pending_ai else None,
                "ai_new_issues": [_issue_dict(issue) for issue in self._pending_ai_hard_issues],
                "review_status": self._review_status,
                "review_method": self._review_method,
                "has_unsaved_changes": self._persistence_state() != self._saved_state,
                "draft_status": (
                    "recovered"
                    if self._draft_recovered
                    else "autosaved"
                    if self._persistence_state() != self._saved_state
                    else "none"
                ),
                "draft_warning": self._draft_warning,
                "baseline_origin": (
                    "external_overrides"
                    if self.external_overrides_path is not None
                    else "saved_workspace_overrides"
                    if self.override_path.is_file()
                    else "automatic"
                ),
                "local_overrides_path": (
                    str(self.override_path) if self.override_path.is_file() else None
                ),
                "external_overrides_path": (
                    str(self.external_overrides_path)
                    if self.external_overrides_path is not None
                    else None
                ),
                "undo_available": bool(self._undo),
                "redo_available": bool(self._redo),
            }

    def apply(self, payload: dict[str, Any]) -> dict[str, Any]:
        operations = payload.get("operations")
        if not isinstance(operations, list) or not operations:
            raise EditorError("operations must be a non-empty list")
        with self._lock:
            current = self._labels
            base_ids = dict(self._base_ids)
            for operation in operations:
                current, base_ids = self._apply_operation(current, base_ids, operation)
            if current == self._labels and base_ids == self._base_ids:
                return self.state()
            self._record_undo()
            self._labels = current
            self._base_ids = base_ids
            self._review_status = "corrected"
            self._review_method = "human" if payload.get("source") != "ai" else "ai"
            self._pending_ai = None
            self._pending_ai_hard_issues = ()
            self._render_preview()
            self._persist_draft()
            return self.state()

    def undo(self) -> dict[str, Any]:
        with self._lock:
            if self._undo:
                self._redo.append(_Snapshot(self._labels, dict(self._base_ids)))
                snapshot = self._undo.pop()
                self._labels, self._base_ids = snapshot.labels, dict(snapshot.base_ids)
                self._review_status = (
                    "corrected" if self._labels != self._baseline else "unreviewed"
                )
                self._pending_ai = None
                self._pending_ai_hard_issues = ()
                self._render_preview()
                self._restore_review_status_for_current_state()
                self._persist_draft()
            return self.state()

    def redo(self) -> dict[str, Any]:
        with self._lock:
            if self._redo:
                self._undo.append(_Snapshot(self._labels, dict(self._base_ids)))
                snapshot = self._redo.pop()
                self._labels, self._base_ids = snapshot.labels, dict(snapshot.base_ids)
                self._review_status = "corrected"
                self._pending_ai = None
                self._pending_ai_hard_issues = ()
                self._render_preview()
                self._restore_review_status_for_current_state()
                self._persist_draft()
            return self.state()

    def reset(self) -> dict[str, Any]:
        with self._lock:
            base_ids = {
                label.id: item.id
                for label in self._baseline
                if (item := label.effective_candidate()) is not None
            }
            if self._labels == self._baseline and self._base_ids == base_ids:
                return self.state()
            self._record_undo()
            self._labels = self._baseline
            self._base_ids = base_ids
            self._review_status = "unreviewed"
            self._review_method = None
            self._pending_ai = None
            self._pending_ai_hard_issues = ()
            self._render_preview()
            self._persist_draft()
            return self.state()

    def load_saved_overrides(self, path: Path) -> None:
        with self._lock:
            overrides = load_override_library(path).for_chart(self.definition.id)
            if overrides is None:
                raise EditorError(f"no overrides found for chart {self.definition.id!r} in {path}")
            self._labels = apply_overrides(self._baseline, overrides)
            for label_id, spec in overrides.labels.items():
                label = next(item for item in self._labels if item.id == label_id)
                candidate = label.effective_candidate()
                if candidate is None:
                    continue
                if spec.candidate is not None:
                    base_id = _resolve_base_candidate(self._baseline, label_id, spec.candidate)
                    self._base_ids[label_id] = base_id
            self._review_status = "corrected"
            self._review_method = "loaded"
            self._render_preview()

    def save(self, note: str = "") -> dict[str, Any]:
        with self._lock:
            self._ensure_leader_lines_resolve(self._labels)
            specs: dict[str, dict[str, Any]] = {}
            baseline_by_id = {item.id: item for item in self._baseline}
            for label in self._labels:
                baseline = baseline_by_id[label.id]
                if label == baseline:
                    continue
                if label.leader_line and not label.locked:
                    raise EditorError(
                        f"{label.id}: lock the label before saving an explicit leader line"
                    )
                candidate = label.effective_candidate()
                if candidate is None:
                    continue
                base_id = self._base_ids.get(label.id)
                if base_id is None:
                    continue
                base = label.candidate(base_id)
                if base is None:
                    continue
                dx = candidate.bounds.left_mm - base.bounds.left_mm
                dy = candidate.bounds.top_mm - base.bounds.top_mm
                position_changed = (
                    label.selected_candidate_id != baseline.selected_candidate_id
                    or abs(dx) > 1e-6
                    or abs(dy) > 1e-6
                )
                if position_changed and not label.locked:
                    raise EditorError(
                        f"{label.id}: lock a manually placed label before saving so the "
                        "normal atlas optimizer preserves its position"
                    )
                spec: dict[str, Any] = {"candidate": base_id}
                if abs(dx) > 1e-6 or abs(dy) > 1e-6:
                    spec["offset_mm"] = {"x": round(dx, 4), "y": round(dy, 4)}
                if label.locked != baseline.locked:
                    spec["locked"] = label.locked
                if label.leader_line != baseline.leader_line:
                    spec["leader_line"] = label.leader_line
                if spec != {"candidate": base_id} or base_id != baseline.selected_candidate_id:
                    specs[label.id] = spec
            self.override_path.parent.mkdir(parents=True, exist_ok=True)
            override_doc = {"chart": self.definition.id, "labels": specs}
            if specs:
                self.override_path.write_text(
                    yaml.safe_dump(override_doc, sort_keys=True, allow_unicode=True),
                    encoding="utf-8",
                )
                override_file = str(self.override_path)
            else:
                self.override_path.unlink(missing_ok=True)
                override_file = None
            self.review_path.write_text(
                json.dumps(
                    {
                        "chart": self.definition.id,
                        "edition": self.atlas.id,
                        "status": self._review_status,
                        "method": self._review_method,
                        "timestamp_utc": datetime.now(UTC).isoformat(),
                        "note": note,
                        "baseline_label_ids": [item.id for item in self._baseline],
                        "baseline_fingerprint": self._baseline_fingerprint,
                        "override_file": override_file,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            self._saved_state = self._persistence_state()
            self._saved_review_status = self._review_status
            self._saved_review_method = self._review_method
            self._draft_path.unlink(missing_ok=True)
            self._draft_path = self._draft_file_for_saved_state()
            self._draft_recovered = False
            return {"override_path": str(self.override_path), "review_path": str(self.review_path)}

    def accept_as_is(self, note: str = "") -> dict[str, Any]:
        if self.external_overrides_path is not None:
            raise EditorError(
                "cannot accept as-is while an external override source is loaded; "
                "restart without --overrides so the baseline is truly unchanged"
            )
        with self._lock:
            self._labels = self._baseline
            self._base_ids = {
                label.id: candidate.id
                for label in self._baseline
                if (candidate := label.effective_candidate()) is not None
            }
            self._review_status = "accepted_as_is"
            self._review_method = "human"
            self._pending_ai = None
            self._pending_ai_hard_issues = ()
            self._draft_path.unlink(missing_ok=True)
            self.override_path.unlink(missing_ok=True)
            self._render_preview()
            self.review_path.write_text(
                json.dumps(
                    {
                        "chart": self.definition.id,
                        "edition": self.atlas.id,
                        "status": "accepted_as_is",
                        "method": "human",
                        "timestamp_utc": datetime.now(UTC).isoformat(),
                        "note": note,
                        "baseline_label_ids": [item.id for item in self._baseline],
                        "baseline_fingerprint": self._baseline_fingerprint,
                        "override_file": None,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            self._saved_state = self._persistence_state()
            self._saved_review_status = self._review_status
            self._saved_review_method = self._review_method
            self._draft_path = self._draft_file_for_saved_state()
            self._draft_recovered = False
            self._draft_warning = None
            return {"review_path": str(self.review_path), "override_path": None}

    def _persistence_state(self) -> _Snapshot:
        return _Snapshot(self._labels, dict(self._base_ids))

    def _draft_file_for_saved_state(self) -> Path:
        key = _snapshot_fingerprint(self._baseline_fingerprint, self._saved_state)
        return self.outdir / f"draft-{key[:16]}.json"

    def _draft_layout(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for label in self._labels:
            candidate = label.effective_candidate()
            base_id = self._base_ids.get(label.id)
            base = label.candidate(base_id) if base_id is not None else None
            offset_x = offset_y = 0.0
            if candidate is not None and base is not None:
                offset_x = candidate.bounds.left_mm - base.bounds.left_mm
                offset_y = candidate.bounds.top_mm - base.bounds.top_mm
            result[label.id] = {
                "base_candidate_id": base_id,
                "offset_mm": {"x": round(offset_x, 4), "y": round(offset_y, 4)},
                "hidden": label.hidden,
                "locked": label.locked,
                "leader_line": label.leader_line,
            }
        return result

    def _load_draft(self) -> None:
        path = self._draft_path
        if not path.is_file():
            stale = sorted(self.outdir.glob("draft-*.json"))
            if stale:
                self._draft_warning = (
                    "A draft for a different saved override or chart baseline remains untouched: "
                    f"{stale[0].name}"
                )
            return
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            saved_fingerprint = _snapshot_fingerprint(self._baseline_fingerprint, self._saved_state)
            if (
                document.get("version") != 1
                or document.get("chart") != self.definition.id
                or document.get("baseline_fingerprint") != self._baseline_fingerprint
                or document.get("saved_state_fingerprint") != saved_fingerprint
            ):
                self._draft_warning = f"Draft not applied because its source changed: {path.name}"
                return
            baselines = {label.id: label for label in self._baseline}
            placements = document.get("labels")
            if not isinstance(placements, dict) or set(placements) != set(baselines):
                raise EditorError("draft label set does not match the chart baseline")
            recovered: list[Label] = []
            base_ids: dict[str, str] = {}
            for label_id, baseline in baselines.items():
                spec = placements[label_id]
                if not isinstance(spec, dict):
                    raise EditorError(f"draft placement for {label_id} is invalid")
                locked, hidden, leader_line = (
                    spec.get("locked"), spec.get("hidden"), spec.get("leader_line")
                )
                if not all(isinstance(value, bool) for value in (locked, hidden, leader_line)):
                    raise EditorError(f"draft flags for {label_id} are invalid")
                base_id = spec.get("base_candidate_id")
                if base_id is None:
                    if not hidden:
                        raise EditorError(f"visible draft label {label_id} has no placement")
                    updated = baseline.with_placement(None, hidden=True, locked=locked)
                else:
                    if not isinstance(base_id, str) or baseline.candidate(base_id) is None:
                        raise EditorError(f"draft candidate for {label_id} is unavailable")
                    offset = spec.get("offset_mm")
                    if not isinstance(offset, dict):
                        raise EditorError(f"draft offset for {label_id} is invalid")
                    dx = _finite_number(offset.get("x"))
                    dy = _finite_number(offset.get("y"))
                    updated = offset_label_placement(baseline, base_id, dx, dy)
                    updated = updated.with_placement(
                        updated.selected_candidate_id, hidden=hidden, locked=locked
                    )
                    base_ids[label_id] = base_id
                recovered.append(
                    replace(
                        updated,
                        leader_line=leader_line,
                        leader_line_reason="manual" if leader_line else None,
                    )
                )
            recovered_labels = tuple(recovered)
            if recovered_labels != self._labels or base_ids != self._base_ids:
                self._undo.append(_Snapshot(self._labels, dict(self._base_ids)))
                self._labels = recovered_labels
                self._base_ids = base_ids
            self._draft_recovered = True
            self._review_status = "corrected"
            self._review_method = "draft"
            self._render_preview()
        except (
            OSError,
            json.JSONDecodeError,
            EditorError,
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            self._draft_warning = f"Draft remains on disk but could not be applied: {error}"

    def _persist_draft(self) -> None:
        if self._persistence_state() == self._saved_state:
            self._draft_path.unlink(missing_ok=True)
            self._draft_recovered = False
            return
        document = {
            "version": 1,
            "chart": self.definition.id,
            "baseline_fingerprint": self._baseline_fingerprint,
            "saved_state_fingerprint": _snapshot_fingerprint(
                self._baseline_fingerprint, self._saved_state
            ),
            "labels": self._draft_layout(),
            "review_method": self._review_method,
        }
        temporary = self._draft_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        temporary.replace(self._draft_path)
        self._draft_recovered = False

    def _restore_review_status_for_current_state(self) -> None:
        if self._persistence_state() == self._saved_state:
            self._review_status = self._saved_review_status
            self._review_method = self._saved_review_method
        else:
            self._review_status = "corrected"
            self._review_method = "human"

    def export_pdf(self) -> str:
        with self._lock:
            self._ensure_leader_lines_resolve(self._labels)
            self._render_preview(pdf=True)
            return str(self.pdf_path)

    def _ensure_leader_lines_resolve(self, labels: tuple[Label, ...]) -> None:
        enabled = {label.id for label in labels if label.leader_line and not label.hidden}
        resolved = {
            item.label_id
            for item in resolve_leader_lines(labels, self.scene, self.transform, self.style)
        }
        missing = sorted(enabled - resolved)
        if missing:
            raise EditorError(
                "leader line cannot be routed for "
                + ", ".join(missing)
                + "; see the validation panel for the geometric issue"
            )

    def ai_suggest(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.ai_config_path is None or not self.ai_config_path.exists():
            raise EditorError(
                "AI is not configured; pass --ai-config with an enabled provider config"
            )
        ids = payload.get("label_ids")
        if not isinstance(ids, list) or not ids or not all(isinstance(item, str) for item in ids):
            raise EditorError("select one or more labels before asking AI for a suggestion")
        instruction = payload.get("instruction", "")
        if not isinstance(instruction, str) or len(instruction) > 2000:
            raise EditorError("instruction must be text of at most 2000 characters")
        with self._lock:
            selected = set(ids)
            known = {label.id for label in self._labels}
            if not selected <= known:
                raise EditorError("AI selection contains unknown label IDs")
            editable = {
                label.id for label in self._labels if label.id in selected and not label.locked
            }
            if not editable:
                raise EditorError("all selected labels are locked")
            self._render_preview()
            config = load_ai_config(self.ai_config_path)
            if not config.enabled:
                raise EditorError("AI is disabled in the selected AI configuration")
            reviewer = OpenRouterReviewer.from_config(config)
            validation = self._validate(self._labels)
            request = build_review_request(
                page_id=f"{self.atlas.id}:{self.definition.id}",
                scene=self.scene,
                labels=self._labels,
                transform=self.transform,
                diagnostics={
                    "label_count": float(len(self._labels)),
                    "hard_issue_count": float(len(validation.issues)),
                },
                images=(str(self.preview_path),),
            )
            scope = ", ".join(sorted(editable))
            request = replace(
                request,
                user_instruction=(
                    f"Only these labels may be changed: {scope}. "
                    "All other labels are fixed obstacles. "
                    "Do not hide or remove any label. Suggest a coordinated group placement; "
                    "the local editor validates the combined result. "
                    + (f"User request: {instruction}" if instruction else "")
                ),
            )
            result = reviewer.review(request)
            proposed = self._apply_ai_batch(result, editable)
            proposed_validation = self._validate(proposed)
            baseline_issue_ids = {item.id for item in validation.issues}
            added = [
                item for item in proposed_validation.issues if item.id not in baseline_issue_ids
            ]
            self._pending_ai = proposed
            self._pending_ai_hard_issues = tuple(added)
            self._render_preview(labels=proposed, path=self.outdir / "ai-preview.png")
            return {
                "page_score": result.page_score,
                "issues": [
                    {
                        "label_id": item.element_id,
                        "type": item.issue_type.value,
                        "severity": item.severity,
                    }
                    for item in result.issues
                    if item.element_id in editable and item.action is not None
                ],
                "applied_actions": len(
                    [item for item in result.issues if item.element_id in editable]
                ),
                "preview_url": "/ai-preview.png",
                "can_accept": not added,
                "new_hard_issues": [_issue_dict(item) for item in added],
                "usage": None
                if reviewer.last_usage is None
                else {
                    "model": reviewer.last_usage.model,
                    "cost_usd": reviewer.last_usage.cost_usd,
                    "latency_s": reviewer.last_usage.latency_s,
                },
            }

    def accept_ai(self) -> dict[str, Any]:
        with self._lock:
            if self._pending_ai is None:
                raise EditorError("there is no pending AI proposal")
            if self._pending_ai_hard_issues:
                raise EditorError(
                    "AI proposal adds hard layout issues; discard it or ask for another proposal"
                )
            if self._pending_ai == self._labels:
                self._pending_ai = None
                return self.state()
            self._record_undo()
            before = {label.id: label for label in self._labels}
            self._labels = tuple(
                replace(label, locked=True)
                if label.id in before and label != before[label.id]
                else label
                for label in self._pending_ai
            )
            for label in self._labels:
                selected_id = label.selected_candidate_id
                if selected_id is None or ":fine:" in selected_id:
                    continue
                if label.candidate(selected_id) is not None:
                    self._base_ids[label.id] = selected_id
            self._pending_ai = None
            self._pending_ai_hard_issues = ()
            self._review_status = "corrected"
            self._review_method = "mixed"
            self._render_preview()
            self._persist_draft()
            return self.state()

    def reject_ai(self) -> dict[str, Any]:
        with self._lock:
            self._pending_ai = None
            self._pending_ai_hard_issues = ()
            (self.outdir / "ai-preview.png").unlink(missing_ok=True)
            return self.state()

    def _apply_ai_batch(self, result: Any, editable: set[str]) -> tuple[Label, ...]:
        by_id = {label.id: label for label in self._labels}
        changes: dict[str, Label] = {}
        for issue in result.issues:
            if issue.element_id not in editable or issue.action is None:
                continue
            original = changes.get(issue.element_id, by_id[issue.element_id])
            if original.locked:
                continue
            action = issue.action
            if action.type == ReviewActionType.HIDE_OPTIONAL_LABEL:
                continue
            if action.type == ReviewActionType.FINE_ADJUST_LABEL:
                options = _fine_adjustments(original, action)
                updated = options[0] if options else None
            else:
                updated = _apply_one(original, action)
            if updated is not None and updated != original:
                changes[issue.element_id] = updated
        return tuple(changes.get(label.id, label) for label in self._labels)

    def _apply_operation(
        self,
        labels: tuple[Label, ...],
        base_ids: dict[str, str],
        operation: Any,
    ) -> tuple[tuple[Label, ...], dict[str, str]]:
        if not isinstance(operation, dict):
            raise EditorError("each operation must be an object")
        kind = operation.get("type")
        if kind == "group_move":
            ids = operation.get("label_ids")
            dx, dy = _finite_number(operation.get("dx_mm")), _finite_number(operation.get("dy_mm"))
            if not isinstance(ids, list) or not ids:
                raise EditorError("group_move requires label_ids")
            updated = list(labels)
            for label_id in ids:
                index = _label_index(updated, label_id)
                label = updated[index]
                candidate = label.effective_candidate()
                if candidate is None:
                    continue
                base_id = base_ids.get(label_id, candidate.id)
                base = label.candidate(base_id)
                if base is None:
                    raise EditorError(f"{label_id}: base candidate is no longer available")
                offset_x = candidate.bounds.left_mm + dx - base.bounds.left_mm
                offset_y = candidate.bounds.top_mm + dy - base.bounds.top_mm
                updated[index] = replace(
                    offset_label_placement(label, base_id, offset_x, offset_y), locked=True
                )
            return tuple(updated), base_ids

        label_id = operation.get("label_id")
        index = _label_index(list(labels), label_id)
        label = labels[index]
        updated = label
        new_base = base_ids.get(label_id, label.selected_candidate_id or "")
        if kind == "candidate":
            requested = operation.get("candidate")
            candidate = next(
                (
                    item
                    for item in label.candidates
                    if item.id == requested or (item.position.value == requested and item.ring == 0)
                ),
                None,
            )
            if candidate is None:
                raise EditorError(f"{label_id}: unavailable candidate {requested!r}")
            updated = label.with_placement(candidate.id, locked=True)
            new_base = candidate.id
        elif kind == "move":
            x, y = _finite_number(operation.get("x_mm")), _finite_number(operation.get("y_mm"))
            base = label.candidate(new_base)
            if base is None:
                raise EditorError(f"{label_id}: no selected candidate")
            updated = replace(
                offset_label_placement(
                    label,
                    new_base,
                    x - base.bounds.left_mm,
                    y - base.bounds.top_mm,
                ),
                locked=True,
            )
        elif kind == "offset":
            dx, dy = _finite_number(operation.get("x")), _finite_number(operation.get("y"))
            base = label.candidate(new_base)
            if base is None:
                raise EditorError(f"{label_id}: no selected candidate")
            updated = replace(offset_label_placement(label, new_base, dx, dy), locked=True)
        elif kind == "leader_line":
            enabled = operation.get("enabled")
            if not isinstance(enabled, bool):
                raise EditorError("leader_line.enabled must be boolean")
            updated = replace(
                label,
                leader_line=enabled,
                leader_line_reason="manual" if enabled else None,
                locked=label.locked or enabled,
            )
        elif kind == "lock":
            locked = operation.get("locked")
            if not isinstance(locked, bool):
                raise EditorError("lock.locked must be boolean")
            updated = replace(label, locked=locked)
        elif kind == "reset_position":
            original = next((item for item in self._baseline if item.id == label_id), None)
            if original is None:
                raise EditorError(f"unknown label {label_id!r}")
            updated = original
            new_base = original.selected_candidate_id or ""
        else:
            raise EditorError(f"unsupported operation {kind!r}")
        result = list(labels)
        result[index] = updated
        base_ids = dict(base_ids)
        base_ids[label_id] = new_base
        return tuple(result), base_ids

    def _record_undo(self) -> None:
        self._undo.append(_Snapshot(self._labels, dict(self._base_ids)))
        self._redo.clear()

    def _load_review_record(self) -> None:
        if not self.review_path.is_file():
            return
        try:
            record = json.loads(self.review_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if (
            record.get("chart") != self.definition.id
            or record.get("edition") != self.atlas.id
            or record.get("baseline_fingerprint") != self._baseline_fingerprint
            or record.get("status") not in {"accepted_as_is", "corrected"}
            or (
                record.get("status") == "accepted_as_is"
                and (
                    self.external_overrides_path is not None or self.override_path.is_file()
                )
            )
        ):
            return
        self._review_status = record["status"]
        self._review_method = record.get("method")

    def _validate(self, labels: tuple[Label, ...]):
        presentation = self._presentation()
        furniture = furniture_obstacles(self.transform, self.definition, self.style, presentation)
        return validate_layout(labels, self.scene, self.transform, self.style, furniture=furniture)

    def _optimizer_hints(self) -> dict[str, Any]:
        warnings: set[str] = set()
        dense: set[str] = set()
        ambiguous: set[str] = set()
        for label_id, item in self._baseline_optimizer_diagnostics.items():
            if (
                item.get("foreign_star_proximity_cost", 0.0) > 0.0
                or item.get("foreign_dso_proximity_cost", 0.0) > 0.0
                or item.get("ownership_margin_weak")
            ):
                warnings.add(label_id)
            if item.get("label_label_conflict_count", 0) or item.get("label_dso_conflicts"):
                dense.add(label_id)
            if (
                item.get("competing_source_ambiguity_cost", 0.0) > 0.0
                or item.get("foreign_source_closer_than_owner")
            ):
                ambiguous.add(label_id)
        return {
            "scope": "automatic baseline; hard errors below use the current edited layout",
            "warnings": sorted(warnings),
            "high_density": sorted(dense),
            "possible_ambiguity": sorted(ambiguous),
        }

    def _render_preview(
        self,
        *,
        labels: tuple[Label, ...] | None = None,
        path: Path | None = None,
        pdf: bool = False,
    ) -> None:
        presentation = self._presentation()
        render_chart(
            self.scene,
            self.transform,
            self.style,
            labels=self._labels if labels is None else labels,
            presentation=presentation,
            locator=self.locator,
            detail_markers=self.detail_markers,
            variable_star_hips=self.variable_star_hips,
            png_path=(self.preview_path if path is None else path),
            pdf_path=self.pdf_path if pdf else None,
            png_dpi=300.0 if pdf else self.png_dpi,
            debug=None,
        )

    def _presentation(self) -> ChartPresentation:
        if self.detail_config is None:
            return presentation_from_edition(
                self.definition, self.atlas.resolved_edition(), scene=self.scene
            )
        return ChartPresentation(
            edition_name=(
                f"Detail · {self.detail_config.name} · Stars to "
                f"{self.detail_stellar_limit or self.atlas.stellar_limit_magnitude:.1f}"
            ),
            edition_code="SD",
            chart_index=None,
            internal_chart_id=self.detail_config.code,
            constellation_context=constellation_context(
                scene_constellation_area_fractions(self.scene)
            ),
        )

    def _build_locator(self, context: Any) -> LocatorInset | None:
        if not self.style.locator.enabled:
            return None
        from nightsky_atlas.catalog.constellations import load_constellations

        constellations = load_constellations()
        overview = build_overview(
            chart_definitions(self.atlas),
            hemisphere=hemisphere_for(self.definition.center_dec_deg),
            constellations=constellations,
            edition=self.atlas.resolved_edition(),
            equatorial_extension_deg=self.style.overview.equatorial_extension_deg,
        )
        return LocatorInset(
            overview=overview,
            current_chart_id=self.definition.id,
            neighbour_ids=frozenset(item for _, item in self.definition.neighbours),
        )

    def _detail_fallback_ids(
        self,
        context: Any,
        inputs: Any,
        atlas: Any,
        atlas_path: Path,
        style_path: Path,
        dsos_path: Path | None,
    ) -> set[str]:
        result: set[str] = set()
        parent_galaxies = {
            item.dso.id: item
            for item in context.scene.deep_sky_objects
            if item.dso.object_type == DsoType.GALAXY and item.symbol_visible
        }
        for detail in atlas.detail_charts:
            if (
                detail.parent_chart_id != self.definition.id
                or not detail.fallback_parent_galaxy_labels
            ):
                continue
            profile_atlas = load_atlas_config(atlas_path.with_name(f"{detail.star_profile}.yaml"))
            profile_style = load_style_config(style_path.with_name(f"{detail.star_profile}.yaml"))
            from nightsky_atlas.build.atlas import _style_with_star_profile

            detail_style = _style_with_star_profile(self.style, profile_style)
            detail_context = build_chart_context(
                atlas_path=atlas_path,
                style_path=style_path,
                definition=detail.to_definition(atlas_id=atlas.id),
                star_store=self.star_store,
                dsos_path=dsos_path,
                magnitude_limit=profile_atlas.stellar_limit_magnitude,
                scale_mm_per_degree=detail.mm_per_degree,
                inputs=inputs,
            )
            detail_labels = select_labels(
                build_labels(
                    detail_context.scene,
                    detail_context.transform,
                    detail_style,
                    load_star_names(DEFAULT_FIXTURE_DIR),
                ),
                detail_context.scene,
                detail_context.transform,
                detail_style,
            )
            detail_presentation = ChartPresentation(
                edition_name=(
                    f"Detail · {detail.name} · Stars to {profile_atlas.stellar_limit_magnitude:.1f}"
                ),
                edition_code="SD",
                chart_index=None,
                internal_chart_id=detail.code,
                constellation_context=constellation_context(
                    scene_constellation_area_fractions(detail_context.scene)
                ),
            )
            detail_labels = optimize_labels(
                detail_labels,
                detail_context.scene,
                detail_context.transform,
                detail_style,
                furniture=furniture_obstacles(
                    detail_context.transform,
                    detail_context.definition,
                    detail_style,
                    detail_presentation,
                ),
            ).labels
            detail_validation = validate_layout(
                detail_labels,
                detail_context.scene,
                detail_context.transform,
                detail_style,
                furniture=furniture_obstacles(
                    detail_context.transform,
                    detail_context.definition,
                    detail_style,
                    detail_presentation,
                ),
            )
            problematic = {
                element_id
                for issue in detail_validation.issues
                for element_id in issue.element_ids
                if element_id.startswith("label:dso:")
            }
            available = {label.id for label in detail_labels if not label.hidden}
            for item in parent_galaxies.values():
                if (
                    messier_id(item.dso) is None
                    and HERSCHEL_400
                    not in (item.metadata.list_memberships if item.metadata is not None else ())
                    and f"label:dso:{item.dso.id}" in available
                    and f"label:dso:{item.dso.id}" not in problematic
                    and any(
                        dso.dso.id == item.dso.id for dso in detail_context.scene.deep_sky_objects
                    )
                ):
                    result.add(item.dso.id)
        return result


def serve_editor(session: EditorSession, *, host: str = "127.0.0.1", port: int = 8765) -> None:
    """Serve one editor session on the local machine only."""
    app_root = APP_ROOT.resolve()
    if not app_root.is_dir():
        raise EditorError(f"editor assets not found: {app_root}")

    class Handler(BaseHTTPRequestHandler):
        server_version = "NightSkyAtlasLabelEditor/1"

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            if path == "/api/state":
                self._json(session.state())
                return
            if path == "/preview.png":
                self._file(session.preview_path, "image/png")
                return
            if path == "/ai-preview.png":
                self._file(session.outdir / "ai-preview.png", "image/png")
                return
            if path in {"/", "/index.html"}:
                self._file(app_root / "index.html", "text/html; charset=utf-8")
                return
            if path in EDITOR_ASSET_MIME_TYPES:
                self._file(
                    app_root / path.lstrip("/"),
                    EDITOR_ASSET_MIME_TYPES[path],
                )
                return
            if path in EDITOR_FONT_ASSETS:
                self._file(FONT_ASSET_ROOT / EDITOR_FONT_ASSETS[path], "font/ttf")
                return
            self.send_error(404)

        def do_POST(self) -> None:
            path = urlsplit(self.path).path
            try:
                payload = self._read_json()
                if path == "/api/apply":
                    result = session.apply(payload)
                elif path == "/api/undo":
                    result = session.undo()
                elif path == "/api/redo":
                    result = session.redo()
                elif path == "/api/reset":
                    result = session.reset()
                elif path == "/api/save":
                    result = session.save(str(payload.get("note", "")))
                elif path == "/api/accept-as-is":
                    result = session.accept_as_is(str(payload.get("note", "")))
                elif path == "/api/export":
                    result = {"pdf_path": session.export_pdf()}
                elif path == "/api/ai/suggest":
                    result = session.ai_suggest(payload)
                elif path == "/api/ai/accept":
                    result = session.accept_ai()
                elif path == "/api/ai/reject":
                    result = session.reject_ai()
                else:
                    self.send_error(404)
                    return
                self._json(result)
            except (EditorError, OpenRouterError, OSError, ValueError) as exc:
                self._json({"error": str(exc)}, status=400)

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > MAX_BODY_BYTES:
                raise EditorError("request body is too large")
            try:
                value = json.loads(self.rfile.read(length))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise EditorError("request body must be valid JSON") from exc
            if not isinstance(value, dict):
                raise EditorError("request body must be a JSON object")
            return value

        def _json(self, value: object, *, status: int = 200) -> None:
            body = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _file(self, path: Path, mime: str) -> None:
            if not path.is_file():
                self.send_error(404)
                return
            body = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            print("label-editor: " + format % args)

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"NightSkyAtlas label editor: http://{host}:{server.server_port}/")
    print(f"Overrides and review state: {session.outdir}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def _resolve_chart(
    atlas: Any,
    atlas_path: Path,
    style_path: Path,
    chart_id: str,
    style: Any,
) -> tuple[ChartDefinition, Any, float | None, float | None, Any | None]:
    detail = next((item for item in atlas.detail_charts if chart_id in {item.id, item.code}), None)
    if detail is not None:
        definition = detail.to_definition(atlas_id=atlas.id)
        profile_atlas = load_atlas_config(atlas_path.with_name(f"{detail.star_profile}.yaml"))
        profile_style = load_style_config(style_path.with_name(f"{detail.star_profile}.yaml"))
        from nightsky_atlas.build.atlas import _style_with_star_profile

        return (
            definition,
            _style_with_star_profile(style, profile_style),
            profile_atlas.stellar_limit_magnitude,
            detail.mm_per_degree,
            detail,
        )
    definition = find_chart(atlas, chart_id)
    return definition, style, None, None, None


def _star_names() -> dict:
    from nightsky_atlas.catalog.star_names import DEFAULT_FIXTURE_DIR, load_star_names

    return load_star_names(DEFAULT_FIXTURE_DIR)


def _rect_dict(rect: PageRect) -> dict[str, float]:
    return {
        "left_mm": rect.left_mm,
        "top_mm": rect.top_mm,
        "width_mm": rect.width_mm,
        "height_mm": rect.height_mm,
    }


def _object_info(item: Any | None) -> dict[str, Any] | None:
    if item is None:
        return None
    return {
        "id": item.dso.id,
        "type": item.dso.object_type.value,
        "ra_deg": item.dso.ra_deg,
        "dec_deg": item.dso.dec_deg,
    }


def _symbol_anchors(scene: ChartScene, transform: Any) -> list[dict[str, Any]]:
    items = []
    for item in scene.deep_sky_objects:
        if not item.symbol_visible:
            continue
        point = transform.to_page(item.chart_point)
        items.append(
            {
                "id": item.dso.id,
                "kind": item.dso.object_type.value,
                "x_mm": point.x_mm,
                "y_mm": point.y_mm,
            }
        )
    for item in scene.stars:
        point = transform.to_page(item.chart_point)
        items.append(
            {
                "id": item.star.id,
                "kind": "star",
                "x_mm": point.x_mm,
                "y_mm": point.y_mm,
            }
        )
    return items


def _issue_dict(issue: Any) -> dict[str, Any]:
    return {
        "id": issue.id,
        "type": issue.issue_type.value,
        "elements": list(issue.element_ids),
        "message": issue.message,
    }


def _finite_number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise EditorError("page coordinates and offsets must be finite numbers")
    return float(value)


def _baseline_fingerprint(chart_id: str, labels: tuple[Label, ...]) -> str:
    payload = {
        "chart": chart_id,
        "labels": [
            {
                "id": label.id,
                "text": label.text,
                "target_id": label.target_id,
                "candidate_id": label.selected_candidate_id,
                "bounds": _rect_dict(label.effective_candidate().bounds)
                if label.effective_candidate() is not None
                else None,
                "anchor": (
                    {
                        "x_mm": label.effective_candidate().anchor.x_mm,
                        "y_mm": label.effective_candidate().anchor.y_mm,
                    }
                    if label.effective_candidate() is not None
                    else None
                ),
            }
            for label in labels
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _snapshot_fingerprint(baseline_fingerprint: str, snapshot: _Snapshot) -> str:
    payload = {
        "baseline_fingerprint": baseline_fingerprint,
        "base_ids": snapshot.base_ids,
        "labels": [label.to_dict() for label in snapshot.labels],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _label_index(labels: list[Label], label_id: Any) -> int:
    if not isinstance(label_id, str):
        raise EditorError("label_id is required")
    for index, label in enumerate(labels):
        if label.id == label_id:
            return index
    raise EditorError(f"unknown label {label_id!r}")


def _resolve_base_candidate(labels: tuple[Label, ...], label_id: str, requested: str) -> str:
    label = next(item for item in labels if item.id == label_id)
    for item in label.candidates:
        if requested == item.position.value and item.ring == 0:
            return item.id
        if requested == item.id:
            return item.id
    raise EditorError(f"{label_id}: saved candidate {requested!r} not found")
