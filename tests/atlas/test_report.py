"""Tests for the automatic draft report."""

from __future__ import annotations

from pathlib import Path

from nightsky_atlas.atlas.report import build_draft_report, render_text_summary

REPO_ROOT = Path(__file__).resolve().parents[2]
ATLAS = REPO_ROOT / "atlas" / "standard.yaml"


def test_draft_report_structure() -> None:
    report = build_draft_report(atlas_path=ATLAS, coverage_step_deg=5.0)
    assert report["chart_count"] == 118
    assert report["chart_order"] == "north-to-south"
    assert report["coverage"]["covers_all"] is True
    assert report["coverage"]["gap_count"] == 0
    assert len(report["polar_charts"]) == 2
    assert report["neighbours"]["missing_overlaps"] == 0
    assert report["ring_layout"][0] == {
        "center_dec_deg": 72.0,
        "chart_count": 10,
        "ra_step_deg": 36.0,
    }
    assert report["ring_layout"][-1]["center_dec_deg"] == -72.0


def test_draft_report_region_review_list() -> None:
    report = build_draft_report(atlas_path=ATLAS, coverage_step_deg=10.0)
    names = {region["name"] for region in report["review_regions"]}
    assert "Virgo Cluster" in names
    assert "Cygnus" in names
    assert "North Pole" in names
    assert "South Pole" in names
    for region in report["review_regions"]:
        assert region["chart_id"]


def test_draft_report_density_flags_outliers() -> None:
    pages = [
        {"chart_id": "c1", "star_count": 1, "dso_count": 1, "label_count": 1},
        {"chart_id": "c2", "star_count": 2, "dso_count": 2, "label_count": 2},
        {"chart_id": "c3", "star_count": 3, "dso_count": 3, "label_count": 3},
        {"chart_id": "c4", "star_count": 100, "dso_count": 100, "label_count": 100},
    ]
    report = build_draft_report(
        atlas_path=ATLAS, pages=pages, coverage_step_deg=10.0
    )
    density = report["density"]["dso_count"]
    assert density["highest_pages"][0] == "c4"
    assert density["lowest_pages"][0] == "c1"


def test_text_summary_mentions_key_facts() -> None:
    report = build_draft_report(atlas_path=ATLAS, coverage_step_deg=10.0)
    text = render_text_summary(report)
    assert "charts: 118" in text
    assert "gaps=0" in text
    assert "Virgo Cluster" in text
