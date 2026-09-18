"""Tests for atlas build orchestration."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
import yaml

from nightsky_atlas.atlas.config import load_atlas_config
from nightsky_atlas.build.atlas import build_atlas, chart_definitions
from nightsky_atlas.build.chart import field_query_box, find_chart
from nightsky_atlas.catalog.dso_store import write_dso_catalog
from nightsky_atlas.catalog.openngc import iter_openngc_objects
from nightsky_atlas.catalog.store import chart_query_box
from nightsky_atlas.chart.models import ChartDefinition

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
    assert field_box.dec_min_deg <= star_box.dec_min_deg
    assert field_box.dec_max_deg >= star_box.dec_max_deg
    assert field_box.dec_max_deg == pytest.approx(12.0 + corner_radius)
    assert field_box.dec_min_deg == pytest.approx(12.0 - corner_radius)
    assert field_box.ra_min_deg < star_box.ra_min_deg
    assert field_box.ra_max_deg > star_box.ra_max_deg


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
                "labels": {
                    "label:dso:NGC4486": {"candidate": "N", "locked": True}
                },
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