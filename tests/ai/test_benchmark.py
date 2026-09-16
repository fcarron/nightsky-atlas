"""Tests for the AI review benchmark runner."""

from __future__ import annotations

from pathlib import Path

from nightsky_atlas.ai.base import MockReviewer
from nightsky_atlas.ai.benchmark import (
    BenchmarkCase,
    BenchmarkReport,
    CaseEvaluation,
    load_cases,
    run_benchmark,
)
from nightsky_atlas.catalog.dso_store import write_dso_catalog
from nightsky_atlas.catalog.openngc import iter_openngc_objects
from nightsky_atlas.review.schema import ReviewResult

REPO_ROOT = Path(__file__).resolve().parents[2]
ATLAS = REPO_ROOT / "atlas" / "standard.yaml"
STYLE = REPO_ROOT / "styles" / "standard.yaml"
STARS = REPO_ROOT / "data" / "fixtures" / "stars" / "test_virgo.csv"
DSOS = REPO_ROOT / "data" / "fixtures" / "openngc" / "sample.csv"
CASES = REPO_ROOT / "benchmarks" / "ai_review" / "cases.yaml"


def make_dso_json(tmp_path: Path) -> Path:
    path = tmp_path / "openngc.json"
    write_dso_catalog(path, iter_openngc_objects([DSOS]))
    return path


def test_load_committed_cases() -> None:
    cases = load_cases(CASES)
    assert len(cases) == 12
    assert cases[0].id == "virgo-raw-m9"
    assert cases[0].mode == "raw"
    assert any(case.magnitude_limit == 8.5 for case in cases)


def run(case: BenchmarkCase, reviewer, outdir: Path):
    return run_benchmark(
        [case],
        reviewer,
        atlas_path=ATLAS,
        style_path=STYLE,
        stars_csv=STARS,
        dsos_path=make_dso_json(outdir),
        outdir=outdir,
    )


def test_benchmark_writes_case_artifacts(tmp_path: Path) -> None:
    case = BenchmarkCase(id="t-opt", chart="test-virgo", mode="optimized")
    report = run(case, MockReviewer(), tmp_path)
    assert len(report.results) == 1
    assert report.results[0].schema_valid is True
    assert (tmp_path / "t-opt" / "case.json").exists()
    assert (tmp_path / "t-opt" / "review.png").exists()


def test_unknown_element_reference_fails_schema(tmp_path: Path) -> None:
    bad = ReviewResult(
        page_score=5.0,
        issues=[
            {
                "element_id": "label:dso:NOPE",
                "issue_type": "other",
                "severity": 5,
            }
        ],
    )
    case = BenchmarkCase(id="t-bad", chart="test-virgo", mode="optimized")
    report = run(case, MockReviewer(results=[bad]), tmp_path)
    assert report.results[0].schema_valid is False
    assert report.results[0].error is not None


def test_report_aggregates() -> None:
    report = BenchmarkReport(
        results=(
            CaseEvaluation("a", True, 3, 2, 1, 1, 0, 8.0, 0.1, 0.001),
            CaseEvaluation("b", False, 2, 0, 0, 0, 0, None, 0.2, None, "boom"),
        )
    )
    assert report.schema_compliance == 0.5
    assert report.total_known_problems == 5
    assert report.total_detected == 2
    assert report.total_false_positives == 1
    assert report.total_cost_usd == 0.001
    assert report.to_dict()["summary"]["cases"] == 2