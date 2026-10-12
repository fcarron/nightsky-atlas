"""Tests for atlas build orchestration."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
import yaml

from nightsky_atlas.atlas.config import load_atlas_config
from nightsky_atlas.build.atlas import (
    AtlasBuildResult,
    _detail_label_suppression_candidate,
    _detail_label_suppression_group,
    _require_mandatory_labels,
    build_atlas,
    chart_definitions,
)
from nightsky_atlas.build.chart import field_query_box, find_chart
from nightsky_atlas.build.preflight import validate_atlas_output
from nightsky_atlas.catalog.dso_store import write_dso_catalog
from nightsky_atlas.catalog.openngc import iter_openngc_objects
from nightsky_atlas.catalog.store import chart_query_box
from nightsky_atlas.chart.models import ChartDefinition
from nightsky_atlas.chart.page import PagePoint, PageRect
from nightsky_atlas.cli import main
from nightsky_atlas.layout.collision import IssueType, LayoutIssue
from nightsky_atlas.layout.models import CompassPosition, Label, LabelCandidate
from nightsky_atlas.layout.validation import ValidationResult

REPO_ROOT = Path(__file__).resolve().parents[2]
STYLE = REPO_ROOT / "styles" / "standard.yaml"
SHIPPED_ATLAS = REPO_ROOT / "atlas" / "standard.yaml"
STARS = REPO_ROOT / "data" / "fixtures" / "stars" / "test_virgo.csv"
DSO_FIXTURE = REPO_ROOT / "data" / "fixtures" / "openngc" / "sample.csv"


def make_atlas_file(tmp_path: Path) -> Path:
    path = tmp_path / "atlas.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "id": "test",
                "page": {"width_mm": 297.0, "height_mm": 210.0, "margin_mm": 12.0},
                "stellar_limit_magnitude": 9.0,
                "charts": [
                    {
                        "id": "c1",
                        "center_ra_deg": 187.5,
                        "center_dec_deg": 12.0,
                        "width_deg": 27.0,
                        "height_deg": 18.5,
                    },
                    {
                        "id": "c2",
                        "center_ra_deg": 307.0,
                        "center_dec_deg": 41.0,
                        "width_deg": 27.0,
                        "height_deg": 18.5,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def make_dso_json(tmp_path: Path) -> Path:
    path = tmp_path / "openngc.json"
    write_dso_catalog(path, iter_openngc_objects([DSO_FIXTURE]))
    return path


def test_detail_suppression_selects_lowest_priority_eligible_collision() -> None:
    def make_label(label_id: str, priority: int) -> Label:
        candidate = LabelCandidate(
            id=f"{label_id}:N",
            position=CompassPosition.N,
            anchor=PagePoint(100.0, 100.0),
            bounds=PageRect(100.0, 100.0, 8.0, 3.0),
        )
        return Label(
            id=label_id,
            target_id=label_id,
            text=label_id,
            priority=priority,
            mandatory=True,
            candidates=(candidate,),
        )

    lower = make_label("label:dso:lower", 30)
    higher = make_label("label:dso:higher", 100)
    issue = LayoutIssue(
        id="issue:label_label:lower:higher",
        issue_type=IssueType.LABEL_LABEL,
        element_ids=(lower.id, higher.id),
        message="labels overlap",
    )
    result = _detail_label_suppression_candidate(
        (higher, lower),
        ValidationResult(issues=(issue,)),
        {lower.id: "PD01", higher.id: "PD01"},
    )

    assert result is not None
    assert result[0].id == lower.id
    assert result[1] == "PD01"
    assert result[2] == (issue,)


def test_detail_suppression_does_not_remove_clear_or_uncovered_labels() -> None:
    clear = Label(
        id="label:dso:clear",
        target_id="clear",
        text="clear",
        priority=30,
        mandatory=True,
        candidates=(),
    )
    covered_but_clear = _detail_label_suppression_candidate(
        (clear,), ValidationResult(issues=()), {clear.id: "PD01"}
    )
    uncovered_collision = _detail_label_suppression_candidate(
        (clear,),
        ValidationResult(
            issues=(
                LayoutIssue(
                    id="issue:label_dso:clear",
                    issue_type=IssueType.LABEL_DSO,
                    element_ids=(clear.id, "NGC 1"),
                    message="label overlaps symbol",
                ),
            )
        ),
        {},
    )

    assert covered_but_clear is None
    assert uncovered_collision is None


def test_detail_suppression_preserves_manually_overridden_labels() -> None:
    label_id = "label:dso:NGC1"
    label = Label(
        id=label_id,
        target_id="NGC1",
        text="1",
        priority=30,
        mandatory=True,
        candidates=(),
    )
    issue = LayoutIssue(
        id="issue:label_dso:NGC1",
        issue_type=IssueType.LABEL_DSO,
        element_ids=(label_id, "NGC2"),
        message="label overlaps symbol",
    )

    assert (
        _detail_label_suppression_candidate(
            (label,),
            ValidationResult(issues=(issue,)),
            {label_id: "PD01"},
            protected_ids=frozenset({label_id}),
        )
        is None
    )


def test_detail_suppression_group_uses_minimum_deterministic_issue_cover() -> None:
    def make_label(label_id: str, priority: int) -> Label:
        candidate = LabelCandidate(
            id=f"{label_id}:N",
            position=CompassPosition.N,
            anchor=PagePoint(100.0, 100.0),
            bounds=PageRect(100.0, 100.0, 8.0, 3.0),
        )
        return Label(
            id=label_id,
            target_id=label_id,
            text=label_id,
            priority=priority,
            mandatory=True,
            candidates=(candidate,),
        )

    left, middle, right = (
        make_label("label:dso:left", 10),
        make_label("label:dso:middle", 100),
        make_label("label:dso:right", 10),
    )
    validation = ValidationResult(
        issues=(
            LayoutIssue(
                id="issue:left-middle",
                issue_type=IssueType.LABEL_LABEL,
                element_ids=(left.id, middle.id),
                message="labels overlap",
            ),
            LayoutIssue(
                id="issue:middle-right",
                issue_type=IssueType.LABEL_LABEL,
                element_ids=(middle.id, right.id),
                message="labels overlap",
            ),
        )
    )

    group = _detail_label_suppression_group(
        (left, middle, right),
        validation,
        {label.id: "PD01" for label in (left, middle, right)},
    )
    protected_middle_group = _detail_label_suppression_group(
        (left, middle, right),
        validation,
        {label.id: "PD01" for label in (left, middle, right)},
        protected_ids=frozenset({middle.id}),
    )

    assert tuple(item[0].id for item in group) == (middle.id,)
    assert tuple(item[0].id for item in protected_middle_group) == (left.id, right.id)


def test_missing_mandatory_label_fails_chart_build() -> None:
    label = Label(
        id="label:star:HIP 1",
        target_id="HIP 1",
        text="α",
        priority=55,
        mandatory=True,
        candidates=(),
    )

    with pytest.raises(ValueError, match="chart pocket-001 has missing mandatory labels"):
        _require_mandatory_labels("pocket-001", (label,))


def test_chart_definitions_for_tiled_atlas() -> None:
    charts = chart_definitions(load_atlas_config(SHIPPED_ATLAS))
    assert len(charts) > 50
    assert all(chart.neighbours for chart in charts)


def test_find_chart_resolves_tiled_id() -> None:
    atlas = load_atlas_config(SHIPPED_ATLAS)
    chart = find_chart(atlas, "standard-068")
    assert chart.id == "standard-068"
    assert chart.atlas_id == "standard"
    assert chart.neighbours


def test_field_query_box_reaches_projected_corners() -> None:
    definition = ChartDefinition(
        id="c", center_ra_deg=187.5, center_dec_deg=12.0, width_deg=27.0, height_deg=18.5
    )
    star_box = chart_query_box(definition, padding_deg=0.0)
    field_box = field_query_box(definition, padding_deg=0.0)
    corner_radius = math.hypot(definition.width_deg / 2.0, definition.height_deg / 2.0)
    assert field_box == star_box
    assert field_box.dec_max_deg == pytest.approx(12.0 + corner_radius)
    assert field_box.dec_min_deg == pytest.approx(12.0 - corner_radius)


def test_build_atlas_subset(tmp_path: Path) -> None:
    result = build_atlas(
        atlas_path=make_atlas_file(tmp_path),
        style_path=STYLE,
        outdir=tmp_path,
        stars_csv=STARS,
        dsos_path=make_dso_json(tmp_path),
        render_png=False,
        png_dpi=72.0,
    )
    assert len(result.pages) == 2
    assert result.total_hard_issues == 0
    assert result.combined_pdf.read_bytes().startswith(b"%PDF")
    assert (tmp_path / "test" / "charts" / "c1" / "chart.pdf").exists()
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["chart_count"] == 2
    assert manifest["page"]["width_mm"] == 297.0
    assert len(manifest["pages"]) == 2
    assert manifest["overview_pages"] == []
    assert result.front_matter_page_count == 2
    assert result.credits_page_count == 1
    assert manifest["credits_page_count"] == 1
    assert result.chart_directory_page_count == 1
    assert manifest["chart_directory"]["entries"][0]["chart_code"] == "c1"
    assert [source["kind"] for source in manifest["data_sources"]][:2] == [
        "stars",
        "deep_sky",
    ]
    assert manifest["data_sources"][0]["path"] == str(STARS)
    assert manifest["data_sources"][1]["path"].endswith("openngc.json")
    assert manifest["input_fingerprints"]["atlas_config"]["sha256"]
    assert manifest["input_fingerprints"]["style_config"]["sha256"]
    assert manifest["input_fingerprints"]["code"]["sha256"]
    assert manifest["publication_preflight"] == {
        "requested": False,
        "inputs_passed": None,
        "output_passed": None,
    }
    assert validate_atlas_output(tmp_path / "test") == ()


def test_atlas_validate_detects_changed_output(tmp_path: Path) -> None:
    atlas_path = make_atlas_file(tmp_path)
    result = build_atlas(
        atlas_path=atlas_path,
        style_path=STYLE,
        outdir=tmp_path,
        stars_csv=STARS,
        dsos_path=make_dso_json(tmp_path),
        render_png=False,
        write_draft_report=False,
    )
    assert main(["atlas", "validate", "--atlas", str(atlas_path), "--outdir", str(tmp_path)]) == 0
    assert (
        main(
            [
                "atlas",
                "validate",
                "--atlas",
                str(atlas_path),
                "--outdir",
                str(tmp_path),
                "--publication",
            ]
        )
        == 1
    )
    atlas_path.write_text(atlas_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert "atlas input fingerprints are stale" in validate_atlas_output(
        tmp_path / "test", publication=True
    )
    result.combined_pdf.write_bytes(b"changed")
    assert "output checksum mismatch: atlas.pdf" in validate_atlas_output(tmp_path / "test")


def test_build_rejects_unknown_or_empty_chart_selection(tmp_path: Path) -> None:
    atlas_path = make_atlas_file(tmp_path)
    for chart_ids, limit, message in (
        (("missing",), None, "unknown chart IDs"),
        ((), None, "no charts selected"),
        (None, 0, "limit must be positive"),
    ):
        with pytest.raises(ValueError, match=message):
            build_atlas(
                atlas_path=atlas_path,
                style_path=STYLE,
                outdir=tmp_path,
                stars_csv=STARS,
                chart_ids=chart_ids,
                limit=limit,
            )


def test_publication_rejects_partial_fixture_build(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="publication preflight failed"):
        build_atlas(
            atlas_path=SHIPPED_ATLAS,
            style_path=STYLE,
            outdir=tmp_path,
            stars_csv=STARS,
            dsos_path=make_dso_json(tmp_path),
            limit=1,
            publication=True,
        )
    assert not (tmp_path / "standard" / "atlas.pdf").exists()


def test_failed_publication_preserves_previous_atlas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    published = tmp_path / "standard"
    published.mkdir()
    (published / "atlas.pdf").write_bytes(b"old publication")

    def fail_build(**_kwargs: object) -> AtlasBuildResult:
        raise ValueError("render failed")

    monkeypatch.setattr("nightsky_atlas.build.atlas._build_atlas_impl", fail_build)
    with pytest.raises(ValueError, match="render failed"):
        build_atlas(
            atlas_path=SHIPPED_ATLAS,
            style_path=STYLE,
            outdir=tmp_path,
            publication=True,
        )
    assert (published / "atlas.pdf").read_bytes() == b"old publication"
    assert list(tmp_path.glob(".standard-staging-*")) == []


def test_successful_publication_swaps_complete_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    published = tmp_path / "standard"
    published.mkdir()
    (published / "atlas.pdf").write_bytes(b"old publication")

    def stage_build(**kwargs: object) -> AtlasBuildResult:
        staged = Path(kwargs["outdir"]) / "standard"
        staged.mkdir()
        (staged / "atlas.pdf").write_bytes(b"new publication")
        (staged / "manifest.json").write_text("{}", encoding="utf-8")
        return AtlasBuildResult(
            atlas_id="standard",
            pages=(),
            combined_pdf=staged / "atlas.pdf",
            manifest_path=staged / "manifest.json",
        )

    monkeypatch.setattr("nightsky_atlas.build.atlas._build_atlas_impl", stage_build)
    result = build_atlas(
        atlas_path=SHIPPED_ATLAS,
        style_path=STYLE,
        outdir=tmp_path,
        publication=True,
    )
    assert result.combined_pdf == published / "atlas.pdf"
    assert result.combined_pdf.read_bytes() == b"new publication"
    assert (tmp_path / ".standard-previous" / "atlas.pdf").read_bytes() == b"old publication"


def test_publication_requires_front_matter_and_overviews(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="front matter and overview maps"):
        build_atlas(
            atlas_path=SHIPPED_ATLAS,
            style_path=STYLE,
            outdir=tmp_path,
            stars_csv=STARS,
            publication=True,
            write_overviews=False,
        )


def test_build_writes_overview_pages_for_tiled_atlas(tmp_path: Path) -> None:
    result = build_atlas(
        atlas_path=SHIPPED_ATLAS,
        style_path=STYLE,
        outdir=tmp_path,
        stars_csv=STARS,
        dsos_path=make_dso_json(tmp_path),
        limit=1,
        render_png=False,
        png_dpi=72.0,
        write_front_matter=False,
    )
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert [page["hemisphere"] for page in manifest["overview_pages"]] == [
        "north",
        "south",
    ]
    assert all(page["chart_count"] > 0 for page in manifest["overview_pages"])


def test_build_can_skip_overview_pages(tmp_path: Path) -> None:
    result = build_atlas(
        atlas_path=SHIPPED_ATLAS,
        style_path=STYLE,
        outdir=tmp_path,
        stars_csv=STARS,
        dsos_path=make_dso_json(tmp_path),
        limit=1,
        render_png=False,
        png_dpi=72.0,
        write_front_matter=False,
        write_overviews=False,
    )
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["overview_pages"] == []


def test_build_respects_limit(tmp_path: Path) -> None:
    result = build_atlas(
        atlas_path=make_atlas_file(tmp_path),
        style_path=STYLE,
        outdir=tmp_path,
        stars_csv=STARS,
        dsos_path=make_dso_json(tmp_path),
        limit=1,
        render_png=False,
        png_dpi=72.0,
        write_front_matter=False,
    )
    assert len(result.pages) == 1


def test_build_applies_overrides(tmp_path: Path) -> None:
    overrides_path = tmp_path / "overrides.yaml"
    overrides_path.write_text(
        yaml.safe_dump(
            {
                "chart": "c1",
                "labels": {"label:dso:NGC4486": {"candidate": "N", "locked": True}},
            }
        ),
        encoding="utf-8",
    )
    result = build_atlas(
        atlas_path=make_atlas_file(tmp_path),
        style_path=STYLE,
        outdir=tmp_path,
        stars_csv=STARS,
        dsos_path=make_dso_json(tmp_path),
        overrides_path=overrides_path,
        render_png=False,
        png_dpi=72.0,
        write_front_matter=False,
    )
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["overrides"]["applied_charts"] == ["c1"]
    assert manifest["overrides"]["unused_charts"] == []
    page = next(item for item in manifest["pages"] if item["chart_id"] == "c1")
    assert page["overrides_applied"] == 1
    other = next(item for item in manifest["pages"] if item["chart_id"] == "c2")
    assert other["overrides_applied"] == 0
