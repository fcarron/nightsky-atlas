"""Atlas phase boundaries: prepare once, reuse layouts, preserve worker output."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from unittest.mock import Mock

import cairo
import pytest
import yaml

import nightsky_atlas.build.atlas as atlas_build
import nightsky_atlas.build.details as detail_build
from nightsky_atlas.atlas.config import DetailChartConfig, load_style_config
from nightsky_atlas.build.chart import build_chart_context
from nightsky_atlas.build.preflight import validate_atlas_output
from nightsky_atlas.catalog.dso_store import write_dso_catalog
from nightsky_atlas.catalog.openngc import iter_openngc_objects
from nightsky_atlas.chart.page import PagePoint, PageRect
from nightsky_atlas.layout.collision import IssueType, LayoutIssue
from nightsky_atlas.layout.models import CompassPosition, Label, LabelCandidate
from nightsky_atlas.layout.optimizer import optimize_labels

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def pipeline_inputs(tmp_path: Path):
    config_dir = tmp_path / "atlas"
    config_dir.mkdir()
    atlas_path = config_dir / "pipeline.yaml"
    atlas_path.write_text(
        yaml.safe_dump(
            {
                "id": "pipeline",
                "edition": {"name": "Pipeline", "code": "T"},
                "page": {"width_mm": 297.0, "height_mm": 210.0, "margin_mm": 12.0},
                "mm_per_degree": 10.0,
                "stellar_limit_magnitude": 9.0,
                "charts": [
                    {
                        "id": "pipeline-001",
                        "center_ra_deg": 187.5,
                        "center_dec_deg": 12.0,
                        "width_deg": 27.0,
                        "height_deg": 18.5,
                    },
                    {
                        "id": "pipeline-002",
                        "center_ra_deg": 195.0,
                        "center_dec_deg": 12.0,
                        "width_deg": 27.0,
                        "height_deg": 18.5,
                    },
                ],
                "detail_charts": [
                    {
                        "id": "pipeline-detail",
                        "code": "TD01",
                        "name": "Virgo detail",
                        "center_ra_deg": 187.5,
                        "center_dec_deg": 12.0,
                        "width_deg": 13.5,
                        "height_deg": 9.0,
                        "mm_per_degree": 20.0,
                        "star_profile": "deep",
                        "dso_profile": "deep",
                        "stars": {"include_ucac4": False},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    dsos = tmp_path / "dsos.json"
    write_dso_catalog(dsos, iter_openngc_objects([REPO_ROOT / "data/fixtures/openngc/sample.csv"]))
    return {
        "atlas_path": atlas_path,
        "style_path": REPO_ROOT / "styles/standard.yaml",
        "stars_csv": REPO_ROOT / "data/fixtures/stars/test_virgo.csv",
        "dsos_path": dsos,
        "constellations_dir": False,
        "outlines_dir": False,
        "star_names_dir": False,
        "observing_lists_dir": False,
        "double_stars_path": False,
        "write_front_matter": False,
        "write_overviews": False,
        "write_draft_report": False,
        "png_dpi": 72.0,
    }


@pytest.mark.parametrize("optimize", [False, True], ids=["initial-layout", "optimized-layout"])
def test_detail_layout_is_prepared_once_and_reused(
    pipeline_inputs, tmp_path, monkeypatch, optimize
):
    contexts = Mock(wraps=build_chart_context)
    optimizer = Mock(wraps=optimize_labels)
    for module in (atlas_build, detail_build):
        monkeypatch.setattr(module, "build_chart_context", contexts)
        monkeypatch.setattr(module, "optimize_labels", optimizer)
    overrides = tmp_path / "overrides.yaml"
    overrides.write_text("chart: pipeline-detail\nlabels: {}\n", encoding="utf-8")
    result = atlas_build.build_atlas(
        **pipeline_inputs,
        outdir=tmp_path / "proof",
        optimize=optimize,
        overrides_path=overrides,
    )
    assert Counter(c.kwargs["definition"].id for c in contexts.call_args_list) == {
        "pipeline-001": 1,
        "pipeline-002": 1,
        "pipeline-detail": 1,
    }
    calls = [c for c in optimizer.call_args_list if c.args[1].definition.id == "pipeline-detail"]
    assert len(calls) == int(optimize)
    manifest = json.loads(result.manifest_path.read_text())
    assert [p.chart_id for p in result.pages] == [
        "pipeline-001",
        "pipeline-002",
        "pipeline-detail",
    ]
    assert manifest["overrides"]["applied_charts"] == ["pipeline-detail"]
    assert manifest["overrides"]["unused_charts"] == []
    assert manifest["detail_charts"][0]["parent_chart_ids"] == ["pipeline-001", "pipeline-002"]
    assert manifest["detail_charts"][0]["stellar_limit_magnitude"] == 10.5
    assert manifest["detail_charts"][0]["faint_star_limit"] is None
    assert manifest["detail_charts"][0]["mm_per_degree"] == 20.0
    assert not validate_atlas_output(result.manifest_path.parent)


def test_serial_and_spawned_workers_preserve_pixels_and_diagnostics(pipeline_inputs, tmp_path):
    results = [
        atlas_build.build_atlas(
            **pipeline_inputs,
            outdir=tmp_path / f"jobs-{jobs}",
            jobs=jobs,
        )
        for jobs in (1, 2)
    ]
    manifests = [json.loads(r.manifest_path.read_text()) for r in results]
    for key in ("pages", "index", "detail_charts", "main_chart_ids", "detail_chart_ids"):
        assert manifests[0][key] == manifests[1][key], key
    assert [m["parallel_jobs"] for m in manifests] == [1, 2]
    for page in results[0].pages:
        images = [
            cairo.ImageSurface.create_from_png(
                str(result.manifest_path.parent / "charts" / page.chart_id / "preview.png")
            )
            for result in results
        ]
        assert images[0].get_width() == images[1].get_width(), page.chart_id
        assert images[0].get_height() == images[1].get_height(), page.chart_id
        assert bytes(images[0].get_data()) == bytes(images[1].get_data()), page.chart_id
    assert all(not validate_atlas_output(r.manifest_path.parent) for r in results)


@pytest.mark.parametrize(("dso_profile", "expected_loads"), [("deep", 1), ("standard", 2)])
def test_shared_detail_profiles_are_loaded_once(monkeypatch, dso_profile, expected_loads):
    detail = DetailChartConfig(
        id="detail",
        code="TD01",
        name="Detail",
        center_ra_deg=180.0,
        center_dec_deg=0.0,
        width_deg=13.5,
        height_deg=9.0,
        mm_per_degree=20.0,
        star_profile="deep",
        dso_profile=dso_profile,
    )
    parent = load_style_config(REPO_ROOT / "styles/color/pocket.yaml")
    loader = Mock(wraps=detail_build.load_style_config)
    monkeypatch.setattr(detail_build, "load_style_config", loader)
    star_profiles, dso_profiles = detail_build.resolve_detail_profiles(
        (detail,),
        REPO_ROOT / "atlas/pocket.yaml",
        REPO_ROOT / "styles/pocket.yaml",
        parent,
    )
    assert loader.call_count == expected_loads
    assert star_profiles["deep"][0] == 10.5
    assert star_profiles["deep"][1].color_atlas == parent.color_atlas
    assert star_profiles["deep"][1].dso == parent.dso
    assert dso_profiles[dso_profile].id == dso_profile


def test_layout_report_preserves_hard_issues_and_fallback_warnings():
    candidate = LabelCandidate(
        id="label:dso:TEST:N:fallback",
        position=CompassPosition.N,
        anchor=PagePoint(20.0, 20.0),
        bounds=PageRect(20.0, 20.0, 8.0, 3.0),
    )
    label = Label(
        id="label:dso:TEST",
        target_id="TEST",
        text="TEST",
        priority=50,
        mandatory=True,
        candidates=(candidate,),
    )
    issue = LayoutIssue(
        id="issue:page",
        issue_type=IssueType.LABEL_PAGE,
        element_ids=(label.id,),
        message="Outside chart",
    )
    records = atlas_build._layout_issue_records((issue,), (label,))
    assert records == (
        {
            "issue_id": "issue:page",
            "type": "label_page",
            "severity": "hard",
            "affected_ids": [label.id],
            "message": "Outside chart",
        },
        {
            "issue_id": f"issue:fallback_candidate:{label.id}",
            "type": "fallback_candidate",
            "severity": "warning",
            "affected_ids": [label.id],
            "message": (
                "No candidate fit inside the chart field; unrestricted candidates "
                "were generated."
            ),
        },
    )
