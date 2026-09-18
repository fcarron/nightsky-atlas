"""AI review benchmark dataset and runner.

Model choice must be empirical (``AGENTS.md`` sections 21 and M13).  A case
pairs a chart and layout mode with the known hard problems of that layout, so a
reviewer can be scored on true detection, false positives, action validity,
schema compliance, cost and latency.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from nightsky_atlas.ai.actions import apply_review_actions
from nightsky_atlas.ai.base import ChartReviewer
from nightsky_atlas.atlas.config import ConfigError
from nightsky_atlas.build.chart import ChartContext, build_chart_context
from nightsky_atlas.chart.presentation import presentation_from_edition
from nightsky_atlas.layout.collision import find_hard_violations
from nightsky_atlas.layout.labels import build_dso_labels
from nightsky_atlas.layout.models import Label
from nightsky_atlas.layout.optimizer import optimize_labels
from nightsky_atlas.layout.selection import select_labels
from nightsky_atlas.render.furniture import furniture_obstacles
from nightsky_atlas.render.review import render_review_png
from nightsky_atlas.review.build import build_review_request
from nightsky_atlas.review.schema import ReviewValidationError, validate_review

__all__ = [
    "BenchmarkCase",
    "BenchmarkReport",
    "CaseEvaluation",
    "load_cases",
    "run_benchmark",
    "run_case",
]

_MODES = {"raw", "optimized"}


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    """One curated page/problem example."""

    id: str
    chart: str
    mode: str = "optimized"
    magnitude_limit: float | None = None
    forbidden_actions: tuple[str, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        if self.mode not in _MODES:
            raise ValueError(f"mode must be one of {sorted(_MODES)}, got {self.mode!r}")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BenchmarkCase:
        return cls(
            id=str(data["id"]),
            chart=str(data["chart"]),
            mode=str(data.get("mode", "optimized")),
            magnitude_limit=_optional_float(data.get("magnitude_limit")),
            forbidden_actions=tuple(data.get("forbidden_actions", ())),
            notes=str(data.get("notes", "")),
        )


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


def load_cases(path: str | Path) -> list[BenchmarkCase]:
    """Load benchmark cases from a YAML file."""
    resolved = Path(path)
    if not resolved.exists():
        raise ConfigError(f"benchmark case file not found: {resolved}")
    raw = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "cases" not in raw:
        raise ConfigError(f"benchmark file must contain a 'cases' list: {resolved}")
    return [BenchmarkCase.from_dict(item) for item in raw["cases"]]


@dataclass(frozen=True, slots=True)
class CaseEvaluation:
    """Per-case benchmark metrics."""

    case_id: str
    schema_valid: bool
    known_problem_count: int
    detected_problems: int
    false_positives: int
    valid_actions: int
    forbidden_actions_used: int
    page_score: float | None
    latency_s: float | None
    cost_usd: float | None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "schema_valid": self.schema_valid,
            "known_problem_count": self.known_problem_count,
            "detected_problems": self.detected_problems,
            "false_positives": self.false_positives,
            "valid_actions": self.valid_actions,
            "forbidden_actions_used": self.forbidden_actions_used,
            "page_score": self.page_score,
            "latency_s": self.latency_s,
            "cost_usd": self.cost_usd,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    """Aggregate benchmark results."""

    results: tuple[CaseEvaluation, ...]

    @property
    def schema_compliance(self) -> float:
        if not self.results:
            return 1.0
        return sum(1 for item in self.results if item.schema_valid) / len(self.results)

    @property
    def total_cost_usd(self) -> float:
        return sum(item.cost_usd or 0.0 for item in self.results)

    @property
    def total_known_problems(self) -> int:
        return sum(item.known_problem_count for item in self.results)

    @property
    def total_detected(self) -> int:
        return sum(item.detected_problems for item in self.results)

    @property
    def total_false_positives(self) -> int:
        return sum(item.false_positives for item in self.results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": {
                "cases": len(self.results),
                "schema_compliance": self.schema_compliance,
                "known_problems": self.total_known_problems,
                "detected": self.total_detected,
                "false_positives": self.total_false_positives,
                "total_cost_usd": self.total_cost_usd,
            },
            "results": [item.to_dict() for item in self.results],
        }


def _furniture_obstacles(context: ChartContext) -> tuple:
    presentation = presentation_from_edition(
        context.definition, context.atlas.resolved_edition()
    )
    return furniture_obstacles(
        context.transform, context.definition, context.style, presentation
    )


def _case_labels(
    case: BenchmarkCase,
    *,
    atlas_path: str | Path,
    style_path: str | Path,
    star_store: str | Path | None,
    stars_csv: str | Path | None,
    dsos_path: str | Path | None,
):
    context = build_chart_context(
        atlas_path=atlas_path,
        style_path=style_path,
        chart_id=case.chart,
        star_store=star_store,
        stars_csv=stars_csv,
        dsos_path=dsos_path,
        magnitude_limit=case.magnitude_limit,
    )
    labels = build_dso_labels(context.scene, context.transform, context.style)
    labels = select_labels(
        labels, context.scene, context.transform, context.style
    )
    if case.mode == "optimized":
        labels = optimize_labels(
            labels,
            context.scene,
            context.transform,
            context.style,
            furniture=_furniture_obstacles(context),
        ).labels
    return context, labels


def _known_label_problems(
    labels: tuple[Label, ...], context: ChartContext
) -> set[str]:
    issues = find_hard_violations(
        labels,
        context.scene,
        context.transform,
        context.style,
        furniture=_furniture_obstacles(context),
    )
    return {
        element_id
        for issue in issues
        for element_id in issue.element_ids
        if element_id.startswith("label:")
    }


def run_case(
    case: BenchmarkCase,
    reviewer: ChartReviewer,
    *,
    atlas_path: str | Path,
    style_path: str | Path,
    star_store: str | Path | None = None,
    stars_csv: str | Path | None = None,
    dsos_path: str | Path | None = None,
    outdir: str | Path,
) -> CaseEvaluation:
    """Run one benchmark case and return its metrics."""
    context, labels = _case_labels(
        case,
        atlas_path=atlas_path,
        style_path=style_path,
        star_store=star_store,
        stars_csv=stars_csv,
        dsos_path=dsos_path,
    )
    case_dir = Path(outdir) / case.id
    case_dir.mkdir(parents=True, exist_ok=True)
    known = _known_label_problems(labels, context)

    review_png = case_dir / "review.png"
    render_review_png(
        context.scene, context.transform, context.style, labels, review_png
    )
    request = build_review_request(
        page_id=case.id,
        scene=context.scene,
        labels=labels,
        transform=context.transform,
        diagnostics={"known_problem_count": float(len(known))},
        images=(str(review_png),),
    )
    (case_dir / "case.json").write_text(
        json.dumps(
            {
                "id": case.id,
                "chart": case.chart,
                "mode": case.mode,
                "magnitude_limit": case.magnitude_limit,
                "known_problem_label_ids": sorted(known),
                "forbidden_actions": list(case.forbidden_actions),
                "notes": case.notes,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    started = time.perf_counter()
    try:
        review = reviewer.review(request)
        validate_review(
            review.model_dump(),
            known_element_ids={element.id for element in request.elements},
        )
        latency = time.perf_counter() - started
        schema_valid = True
    except (ReviewValidationError, ValueError) as exc:
        return CaseEvaluation(
            case_id=case.id,
            schema_valid=False,
            known_problem_count=len(known),
            detected_problems=0,
            false_positives=0,
            valid_actions=0,
            forbidden_actions_used=0,
            page_score=None,
            latency_s=time.perf_counter() - started,
            cost_usd=None,
            error=str(exc),
        )

    detected = sum(1 for issue in review.issues if issue.element_id in known)
    false_positives = sum(1 for issue in review.issues if issue.element_id not in known)
    forbidden_used = sum(
        1
        for issue in review.issues
        if issue.action is not None and issue.action.type.value in case.forbidden_actions
    )
    outcome = apply_review_actions(
        labels, review, context.scene, context.transform, context.style
    )
    usage = getattr(reviewer, "last_usage", None)

    return CaseEvaluation(
        case_id=case.id,
        schema_valid=schema_valid,
        known_problem_count=len(known),
        detected_problems=detected,
        false_positives=false_positives,
        valid_actions=len(outcome.applied),
        forbidden_actions_used=forbidden_used,
        page_score=review.page_score,
        latency_s=latency,
        cost_usd=getattr(usage, "cost_usd", None),
    )


def run_benchmark(
    cases: Iterable[BenchmarkCase],
    reviewer: ChartReviewer,
    *,
    atlas_path: str | Path,
    style_path: str | Path,
    star_store: str | Path | None = None,
    stars_csv: str | Path | None = None,
    dsos_path: str | Path | None = None,
    outdir: str | Path,
) -> BenchmarkReport:
    """Run all benchmark cases against a reviewer."""
    results = tuple(
        run_case(
            case,
            reviewer,
            atlas_path=atlas_path,
            style_path=style_path,
            star_store=star_store,
            stars_csv=stars_csv,
            dsos_path=dsos_path,
            outdir=outdir,
        )
        for case in cases
    )
    return BenchmarkReport(results=results)